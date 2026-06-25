"""Postgres-backed integration tests for airport-quote conversion logging.

These cover the behaviours a MagicMock DB is blind to — the ones that depend on
the *real* engine enforcing the schema:

  * Dedup is real: the partial unique index + ON CONFLICT DO NOTHING actually
    collapse two inserts of the same snapshot id into one row, without resetting
    `converted` or re-stamping `shown_at` (mocks only prove the SQL *string*).
  * UPDATE is real: mark_airport_quote_converted flips false -> true on the
    matching row, and a 0-row call (unknown id) logs a warning and raises nothing.
  * Type match: the INTEGER snapshot id round-trips and matches (catches an
    int4/int8 surprise).
  * Free + paid both land their conversion through the same real helper.

Isolation (provably non-prod / non-staging): a disposable PostgreSQL cluster is
initdb'd into a pytest tmp dir, started on 127.0.0.1:<ephemeral-port> with
fsync off, used, then stopped and deleted at teardown. It never touches
DATABASE_URL / STAGING_DATABASE_URL — test_isolation_* asserts that explicitly.

Run:
  STAGING_DATABASE_URL= DATABASE_URL= \
    python3 -m pytest backend/tests/integration/test_conversion_log_pg_integration.py -q

Set PG_BIN_DIR to point at a Postgres bin dir if it is not auto-discovered;
the module skips cleanly when no server binaries are present.
"""
from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from airport_quote_service import (
    mark_airport_quote_converted,
    normalise_london_datetime,
    record_quote_conversion_log,
)


# ---------------------------------------------------------------------------
# Locate the Postgres server binaries (skip cleanly if none).
# ---------------------------------------------------------------------------

def _find_pg_bin() -> str | None:
    candidates = [
        os.environ.get("PG_BIN_DIR"),
        "/opt/homebrew/opt/postgresql@16/bin",
        "/opt/homebrew/opt/postgresql@15/bin",
        "/usr/local/opt/postgresql@16/bin",
        "/usr/local/opt/postgresql@15/bin",
        "/usr/lib/postgresql/16/bin",
        "/usr/lib/postgresql/15/bin",
    ]
    for cand in candidates:
        if cand and (Path(cand) / "initdb").exists():
            return cand
    found = shutil.which("initdb")
    return str(Path(found).parent) if found else None


def integration_gate(pg_bin, require_pg):
    """Decide how the suite behaves when Postgres may be absent.

    'run'  — binaries present, execute for real.
    'fail' — binaries absent but CI demanded them (REQUIRE_PG_INTEGRATION=1):
             must error loudly, never silently skip (a silent skip reads as a
             fake-green '7 passed' when it actually ran nothing).
    'skip' — binaries absent and not required (local dev convenience).
    """
    if pg_bin is not None:
        return "run"
    return "fail" if require_pg else "skip"


PG_BIN = _find_pg_bin()
REQUIRE_PG = os.environ.get("REQUIRE_PG_INTEGRATION") == "1"
_GATE = integration_gate(PG_BIN, REQUIRE_PG)

if _GATE == "fail":
    # Collection-time error -> CI run goes red. Set PG_BIN_DIR or provide a
    # Postgres service; do NOT let this suite silently skip in CI.
    raise RuntimeError(
        "REQUIRE_PG_INTEGRATION=1 but no PostgreSQL server binaries (initdb) were "
        "found. CI must provide Postgres for the conversion-log integration suite. "
        "Set PG_BIN_DIR to a Postgres bin directory."
    )

pytestmark = pytest.mark.skipif(
    _GATE == "skip",
    reason="no local PostgreSQL server binaries (initdb) found; set PG_BIN_DIR "
           "(or REQUIRE_PG_INTEGRATION=1 in CI to fail instead of skip)",
)


def test_integration_gate_fails_loud_when_required_and_missing():
    """#2: required-but-missing must FAIL, not skip."""
    assert integration_gate(None, True) == "fail"
    assert integration_gate(None, False) == "skip"
    assert integration_gate("/usr/bin", False) == "run"
    assert integration_gate("/usr/bin", True) == "run"

TABLE = "airport_quote_conversion_log"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Ephemeral cluster lifecycle.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    base = tmp_path_factory.mktemp("pg_conv_it")
    data_dir = base / "data"
    log_file = base / "pg.log"

    subprocess.run(
        [f"{PG_BIN}/initdb", "-D", str(data_dir), "-U", "qa",
         "--auth=trust", "-E", "UTF8", "--locale=C"],
        check=True, capture_output=True,
    )

    port = _free_port()
    with open(log_file, "w") as log:
        proc = subprocess.Popen(
            [f"{PG_BIN}/postgres", "-D", str(data_dir),
             "-p", str(port),
             "-c", "listen_addresses=127.0.0.1",
             "-c", "fsync=off",
             "-c", "synchronous_commit=off",
             "-c", "full_page_writes=off"],
            stdout=log, stderr=subprocess.STDOUT,
        )

    try:
        _wait_until_ready(port, log_file)
        subprocess.run(
            [f"{PG_BIN}/createdb", "-h", "127.0.0.1", "-p", str(port),
             "-U", "qa", "tag_qa_it"],
            check=True, capture_output=True,
        )
        yield f"postgresql+psycopg2://qa@127.0.0.1:{port}/tag_qa_it"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(base, ignore_errors=True)


def _wait_until_ready(port: int, log_file: Path, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            [f"{PG_BIN}/pg_isready", "-h", "127.0.0.1", "-p", str(port), "-U", "qa"],
            capture_output=True,
        )
        if result.returncode == 0:
            return
        time.sleep(0.25)
    raise RuntimeError(
        f"Postgres did not become ready on port {port}; log:\n{log_file.read_text()}"
    )


@pytest.fixture(scope="module")
def engine(pg_url):
    eng = create_engine(pg_url)
    # Create ONLY the conversion-log table, from the real ORM definition, so the
    # INTEGER column + partial unique index match production exactly.
    from db_models import AirportQuoteConversionLog
    AirportQuoteConversionLog.__table__.create(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def db(engine):
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.rollback()
        session.execute(text(f"TRUNCATE {TABLE} RESTART IDENTITY"))
        session.commit()
        session.close()


# ---------------------------------------------------------------------------
# Small helpers.
# ---------------------------------------------------------------------------

def _insert(db, snapshot_id, *, lead_days=12, billing_days=7, band="flat",
            tag_pence=11103, cheapest=14805, shown_at=None):
    record_quote_conversion_log(
        db,
        airport_quote_snapshot_id=snapshot_id,
        lead_days=lead_days,
        billing_days=billing_days,
        discount_band=band,
        tag_pence=tag_pence,
        cheapest_boh_pence=cheapest,
        shown_at=shown_at or datetime(2026, 6, 24, 9, 0, tzinfo=timezone.utc),
    )


def _row(db, snapshot_id):
    return db.execute(
        text(f"""SELECT converted, shown_at, discount_band, lead_days, tag_pence
                 FROM {TABLE} WHERE airport_quote_snapshot_id = :s"""),
        {"s": snapshot_id},
    ).fetchall()


# ---------------------------------------------------------------------------
# Isolation guard — prove we are NOT on prod/staging.
# ---------------------------------------------------------------------------

def test_isolation_is_local_ephemeral_not_prod_or_staging(pg_url):
    lowered = pg_url.lower()
    assert "127.0.0.1" in pg_url
    assert "/tag_qa_it" in pg_url
    assert "railway" not in lowered and "rlwy" not in lowered
    for var in ("DATABASE_URL", "STAGING_DATABASE_URL", "PRODUCTION_DATABASE_URL"):
        configured = os.environ.get(var) or ""
        assert pg_url != configured


def test_schema_has_partial_unique_index_on_snapshot_id(db):
    indexdef = db.execute(
        text("""SELECT indexdef FROM pg_indexes
                WHERE tablename = :t
                  AND indexname = 'ux_airport_quote_conversion_log_snapshot_id'"""),
        {"t": TABLE},
    ).scalar()
    assert indexdef is not None, "partial unique index must exist"
    lowered = indexdef.lower()
    assert "unique" in lowered
    assert "airport_quote_snapshot_id is not null" in lowered


# ---------------------------------------------------------------------------
# Dedup is real.
# ---------------------------------------------------------------------------

def test_dedup_second_insert_is_noop_preserving_converted_and_shown_at(db):
    t1 = datetime(2026, 6, 24, 9, 0, tzinfo=timezone.utc)
    _insert(db, 777, lead_days=12, band="flat", tag_pence=11103, shown_at=t1)

    assert len(_row(db, 777)) == 1, "first insert must create exactly one row"

    # Promote it to converted=true, then attempt a second show with DIFFERENT
    # values. ON CONFLICT DO NOTHING must keep the original row untouched.
    mark_airport_quote_converted(db, 777)
    t2 = datetime(2026, 7, 1, 18, 30, tzinfo=timezone.utc)
    _insert(db, 777, lead_days=99, billing_days=14, band="near-long",
            tag_pence=99999, cheapest=88888, shown_at=t2)

    rows = _row(db, 777)
    assert len(rows) == 1, "partial unique index must enforce a single row"
    converted, shown_at, band, lead_days, tag_pence = rows[0]
    assert converted is True          # not reset by the re-show
    assert band == "flat"             # not clobbered
    assert lead_days == 12
    assert tag_pence == 11103
    assert shown_at == t1             # not re-stamped
    assert shown_at != t2


# ---------------------------------------------------------------------------
# UPDATE is real.
# ---------------------------------------------------------------------------

def test_mark_flips_false_to_true_on_matching_row(db):
    _insert(db, 778)
    assert _row(db, 778)[0][0] is False  # seeded not-converted

    mark_airport_quote_converted(db, 778)

    assert _row(db, 778)[0][0] is True


def test_mark_unknown_snapshot_logs_warning_and_does_not_raise(db, caplog):
    with caplog.at_level(logging.WARNING):
        mark_airport_quote_converted(db, 424242)  # no such row

    assert "matched 0 rows" in caplog.text
    # And it really did nothing — table still empty for that id.
    assert _row(db, 424242) == []


# ---------------------------------------------------------------------------
# Type match — INTEGER round-trip.
# ---------------------------------------------------------------------------

def test_integer_snapshot_id_roundtrips_and_matches(db):
    dtype = db.execute(
        text("""SELECT data_type FROM information_schema.columns
                WHERE table_name = :t AND column_name = 'airport_quote_snapshot_id'"""),
        {"t": TABLE},
    ).scalar()
    assert dtype == "integer"  # int4, matches the ORM Column(Integer)

    sid = 2_000_000_111  # large but within int4 (max 2,147,483,647)
    _insert(db, sid)
    got = db.execute(
        text(f"SELECT airport_quote_snapshot_id FROM {TABLE} "
             f"WHERE airport_quote_snapshot_id = :s"),
        {"s": sid},
    ).scalar()
    assert got == sid and isinstance(got, int)

    mark_airport_quote_converted(db, sid)  # match still works on the INTEGER key
    assert _row(db, sid)[0][0] is True


# ---------------------------------------------------------------------------
# Free + paid both land through the same real helper.
# ---------------------------------------------------------------------------

def test_free_and_paid_both_convert_through_same_real_helper(db):
    _insert(db, 901, band="flat")   # paid (webhook) entry point's row
    _insert(db, 902, band="flat")   # free-booking entry point's row

    # Both handlers call this one helper (airport_quote_service.py:623); here we
    # exercise its real-DB effect from both entry points.
    mark_airport_quote_converted(db, 901)  # webhook / paid
    mark_airport_quote_converted(db, 902)  # free booking

    state = dict(db.execute(
        text(f"SELECT airport_quote_snapshot_id, converted FROM {TABLE} "
             f"WHERE airport_quote_snapshot_id IN (901, 902)"),
    ).fetchall())
    assert state == {901: True, 902: True}
