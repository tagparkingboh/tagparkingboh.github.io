"""QA hardening tests for the BOH flight board feature.

Complements tests/mocked/test_flight_board.py (do not duplicate its coverage).
Focus areas:
  - worker endpoint concurrency (429 busy, semaphore never leaked)
  - worker client normalisation, HTTP error propagation, timeout env boundaries
  - scheduler job failure modes end-to-end through the REAL client
    (unreachable worker, worker 429, commit failure, error truncation)
  - upsert statement shape: first_seen_at / identity columns must never be
    overwritten on conflict
  - history-row rules: direction separation, year-boundary end-to-end, DST days
  - parser resilience against malformed rows (missing cells, classless cells,
    entities, uppercase tags, multi-class time cells)
  - employee endpoint hardening (ok-only filter, missing/future created_at,
    seconds-level stale boundary, null JSON columns)
  - FLIGHT_BOARD_SCRAPE_ENABLED env parsing
"""
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import airport_quote_worker_client as worker_client
from flight_board_scraper import parse_boh_flight_board
from flight_board_service import (
    build_history_rows,
    is_flight_board_scrape_enabled,
    process_flight_board_scrape,
    upsert_flight_schedule_history,
)


# =============================================================================
# Helpers
# =============================================================================

def _arrivals_html(rows_html: str) -> str:
    """Wrap raw <tr> markup in the real widget's arrivals container."""
    return (
        '<html><body>'
        '<div id="widget-arrivals-content" class="widget-arrivals-departures-content">'
        f'<table class="arrivals-table"><tbody>{rows_html}</tbody></table></div>'
        '</body></html>'
    )


def _row(place="Faro", airline="Ryanair", flight="FR1", board_date="02/07",
         scheduled="14:00", status="As Scheduled"):
    return {
        "place": place, "airline": airline, "flight": flight,
        "date": board_date, "scheduled": scheduled, "status": status,
    }


def _http_response(status_code: int):
    return httpx.Response(
        status_code,
        request=httpx.Request("POST", "http://worker/internal/flight-board/scrape"),
        json={"detail": "busy"},
    )


# =============================================================================
# Worker endpoint — concurrency guard
# =============================================================================

class TestWorkerEndpointConcurrency:
    def _drain(self, semaphore) -> int:
        held = 0
        while semaphore.acquire(blocking=False):
            held += 1
        return held

    def test_U_returns_429_when_worker_is_busy(self):
        """All Chromium slots taken -> 429, and the scrape is never started."""
        import airport_quote_worker

        held = self._drain(airport_quote_worker.SCRAPE_SEMAPHORE)
        assert held >= 1
        try:
            with patch.object(
                airport_quote_worker, "fetch_bournemouth_flight_board"
            ) as fetch:
                resp = TestClient(airport_quote_worker.app).post(
                    "/internal/flight-board/scrape"
                )
            assert resp.status_code == 429
            assert not fetch.called
        finally:
            for _ in range(held):
                airport_quote_worker.SCRAPE_SEMAPHORE.release()

    def test_U_semaphore_is_released_after_scrape_failure(self):
        """A failing scrape must not leak a semaphore slot: the very next
        request has to succeed, not 429."""
        import airport_quote_worker

        client = TestClient(airport_quote_worker.app, raise_server_exceptions=False)
        with patch.object(
            airport_quote_worker,
            "fetch_bournemouth_flight_board",
            side_effect=RuntimeError("boom"),
        ):
            assert client.post("/internal/flight-board/scrape").status_code == 500

        board = {"arrivals": [_row()], "departures": [], "source_url": "u"}
        with patch.object(
            airport_quote_worker, "fetch_bournemouth_flight_board", return_value=board
        ):
            resp = client.post("/internal/flight-board/scrape")
        assert resp.status_code == 200
        assert len(resp.json()["arrivals"]) == 1


# =============================================================================
# Worker client — endpoint URL, payload normalisation, HTTP errors, timeout env
# =============================================================================

class TestWorkerClient:
    def test_H_posts_to_flight_board_endpoint_and_normalises_payload(self, monkeypatch):
        monkeypatch.delenv("FLIGHT_BOARD_WORKER_TIMEOUT_SECONDS", raising=False)
        captured = {}

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                # arrivals explicitly null, departures/sourceUrl missing
                return {"arrivals": None}

        def fake_post(url, timeout):
            captured["url"] = url
            captured["timeout"] = timeout
            return _Resp()

        monkeypatch.setattr(worker_client.httpx, "post", fake_post)
        board = worker_client.fetch_flight_board_via_worker("http://worker/")
        assert captured["url"] == "http://worker/internal/flight-board/scrape"
        assert captured["timeout"] == 45.0  # default when env unset
        assert board == {"arrivals": [], "departures": [], "source_url": None}

    @pytest.mark.parametrize("status_code", [429, 500, 502])
    def test_U_http_error_statuses_raise(self, monkeypatch, status_code):
        monkeypatch.setattr(
            worker_client.httpx, "post", lambda url, timeout: _http_response(status_code)
        )
        with pytest.raises(httpx.HTTPStatusError):
            worker_client.fetch_flight_board_via_worker("http://worker")

    def test_H_timeout_env_boundaries(self, monkeypatch):
        # t-eps / t / t+eps around the 1-second floor, plus default and garbage.
        cases = [
            ("0.9", 1.0),    # below floor -> clamped up
            ("1", 1.0),      # exactly at floor
            ("1.1", 1.1),    # just above floor -> honoured
            ("60", 60.0),    # normal override
            ("abc", 45.0),   # unparseable -> default
            ("", 45.0),      # empty -> default
        ]
        for raw, expected in cases:
            monkeypatch.setenv("FLIGHT_BOARD_WORKER_TIMEOUT_SECONDS", raw)
            assert worker_client._flight_board_timeout_seconds() == expected, raw
        monkeypatch.delenv("FLIGHT_BOARD_WORKER_TIMEOUT_SECONDS")
        assert worker_client._flight_board_timeout_seconds() == 45.0


# =============================================================================
# Scheduler job failure modes — through the REAL client where possible
# =============================================================================

class TestProcessScrapeFailureModes:
    def _worker_env(self, monkeypatch):
        monkeypatch.setattr(
            "airport_quote_worker_client.get_airport_quote_worker_url",
            lambda: "http://worker",
        )

    def test_U_worker_unreachable_timeout_stores_error_snapshot(self, monkeypatch):
        """Connect timeout raised inside the real client function still ends
        as an error snapshot — no history writes, session closed."""
        db = MagicMock()
        self._worker_env(monkeypatch)

        def _post(url, timeout):
            raise httpx.ConnectTimeout("connection timed out")

        monkeypatch.setattr(worker_client.httpx, "post", _post)
        process_flight_board_scrape(lambda: db)
        snapshot = db.add.call_args[0][0]
        assert snapshot.status == "error"
        assert not db.execute.called
        assert db.commit.called
        assert db.close.called

    def test_U_worker_429_busy_stores_error_snapshot(self, monkeypatch):
        db = MagicMock()
        self._worker_env(monkeypatch)
        monkeypatch.setattr(
            worker_client.httpx, "post", lambda url, timeout: _http_response(429)
        )
        process_flight_board_scrape(lambda: db)
        snapshot = db.add.call_args[0][0]
        assert snapshot.status == "error"
        assert "429" in snapshot.error
        assert not db.execute.called

    def test_U_commit_failure_rolls_back_and_never_raises(self, monkeypatch):
        db = MagicMock()
        db.commit.side_effect = RuntimeError("db down")
        self._worker_env(monkeypatch)
        board = {"arrivals": [_row()], "departures": [], "source_url": "u"}
        monkeypatch.setattr(
            "airport_quote_worker_client.fetch_flight_board_via_worker",
            lambda url: board,
        )
        # Background scheduler job: must swallow the persistence failure.
        process_flight_board_scrape(lambda: db)
        assert db.rollback.called
        assert db.close.called

    def test_U_error_text_is_truncated_to_2000_chars(self, monkeypatch):
        db = MagicMock()
        self._worker_env(monkeypatch)

        def _boom(url):
            raise RuntimeError("x" * 5000)

        monkeypatch.setattr(
            "airport_quote_worker_client.fetch_flight_board_via_worker", _boom
        )
        process_flight_board_scrape(lambda: db)
        snapshot = db.add.call_args[0][0]
        assert snapshot.status == "error"
        assert len(snapshot.error) == 2000

    def test_U_ok_board_with_no_parseable_rows_still_stores_snapshot(self, monkeypatch):
        """Live board rows with TBA date/time can't enter history but the
        snapshot (drivers' live view) must still be stored as ok."""
        db = MagicMock()
        self._worker_env(monkeypatch)
        board = {
            "arrivals": [_row(board_date="TBA", scheduled="TBA")],
            "departures": [],
            "source_url": "u",
        }
        monkeypatch.setattr(
            "airport_quote_worker_client.fetch_flight_board_via_worker",
            lambda url: board,
        )
        process_flight_board_scrape(lambda: db)
        snapshot = db.add.call_args[0][0]
        assert snapshot.status == "ok"
        assert len(snapshot.arrivals_json) == 1
        assert not db.execute.called  # zero history rows -> no upsert statement
        assert db.commit.called

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "SUSPECTED GAP: session_factory() is called outside the try/except "
            "in process_flight_board_scrape, so a session-creation failure "
            "(e.g. exhausted pool) propagates out of the scheduler job. Brief "
            "invariant: the job must never raise. APScheduler catches job "
            "exceptions so impact is limited to an ugly traceback, but the "
            "stated invariant is violated."
        ),
    )
    def test_U_session_factory_failure_does_not_raise(self, monkeypatch):
        self._worker_env(monkeypatch)
        monkeypatch.setattr(
            "airport_quote_worker_client.fetch_flight_board_via_worker",
            lambda url: {"arrivals": [_row()], "departures": [], "source_url": "u"},
        )

        def _factory():
            raise RuntimeError("connection pool exhausted")

        process_flight_board_scrape(_factory)  # currently raises RuntimeError


# =============================================================================
# History upsert statement — first_seen_at / identity must survive conflicts
# =============================================================================

class TestUpsertStatement:
    def test_H_on_conflict_updates_mutable_columns_only(self):
        from sqlalchemy.dialects import postgresql

        db = MagicMock()
        board = {"arrivals": [_row(flight="FR3945", scheduled="20:20")], "departures": []}
        count = upsert_flight_schedule_history(db, board)
        assert count == 1
        assert db.execute.called
        stmt = db.execute.call_args[0][0]
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "ON CONFLICT ON CONSTRAINT uq_flight_schedule_direction_date_flight" in sql
        update_clause = sql.split("DO UPDATE SET", 1)[1]
        for updated in ("scheduled_time", "airline", "place", "last_seen_at"):
            assert updated in update_clause, updated
        # first sighting and row identity are never rewritten on re-scrape
        for preserved in ("first_seen_at", "flight_date", "flight_number", "direction"):
            assert preserved not in update_clause, preserved

    def test_U_empty_board_upserts_nothing(self):
        db = MagicMock()
        assert upsert_flight_schedule_history(db, {"arrivals": [], "departures": []}) == 0
        assert not db.execute.called


# =============================================================================
# History rows — direction separation, year boundary end-to-end, DST days
# =============================================================================

class TestHistoryRowRules:
    NOW = datetime(2026, 7, 2, 18, 0, tzinfo=timezone.utc)

    def test_H_same_flight_number_in_both_directions_kept_separately(self):
        board = {
            "arrivals": [_row(flight="FR3945", scheduled="20:20")],
            "departures": [_row(flight="FR3945", scheduled="06:25")],
        }
        rows = build_history_rows(board, today=date(2026, 7, 2), now=self.NOW)
        assert len(rows) == 2
        assert {r["direction"] for r in rows} == {"arrival", "departure"}

    def test_H_same_flight_number_on_two_dates_kept_separately(self):
        board = {
            "arrivals": [
                _row(flight="FR1", board_date="02/07", scheduled="10:00"),
                _row(flight="FR1", board_date="03/07", scheduled="10:00"),
            ],
            "departures": [],
        }
        rows = build_history_rows(board, today=date(2026, 7, 2), now=self.NOW)
        assert {r["flight_date"] for r in rows} == {date(2026, 7, 2), date(2026, 7, 3)}

    def test_H_year_boundary_end_to_end_through_build_history_rows(self):
        # New Year's Eve board showing both a today row and an after-midnight row.
        board = {
            "arrivals": [_row(flight="FR1", board_date="31/12", scheduled="23:55")],
            "departures": [_row(flight="FR2", board_date="01/01", scheduled="00:15")],
        }
        rows = build_history_rows(
            board,
            today=date(2026, 12, 31),
            now=datetime(2026, 12, 31, 23, 0, tzinfo=timezone.utc),
        )
        by_flight = {r["flight_number"]: r for r in rows}
        assert by_flight["FR1"]["flight_date"] == date(2026, 12, 31)
        assert by_flight["FR2"]["flight_date"] == date(2027, 1, 1)

    def test_H_dst_spring_forward_day_keeps_wall_clock_time(self):
        # 28/03/2027: UK clocks jump 01:00 -> 02:00, so 01:30 doesn't exist
        # locally. History stores board wall-clock verbatim (no tz math), so
        # the row must survive untouched.
        board = {"arrivals": [_row(board_date="28/03", scheduled="01:30")], "departures": []}
        rows = build_history_rows(
            board,
            today=date(2027, 3, 28),
            now=datetime(2027, 3, 28, 6, 0, tzinfo=timezone.utc),
        )
        assert rows[0]["flight_date"] == date(2027, 3, 28)
        assert rows[0]["scheduled_time"] == time(1, 30)

    def test_H_dst_fall_back_day_keeps_single_row(self):
        # 31/10/2027: 01:30 happens twice locally; still exactly one history row.
        board = {"arrivals": [_row(board_date="31/10", scheduled="01:30")], "departures": []}
        rows = build_history_rows(
            board,
            today=date(2027, 10, 31),
            now=datetime(2027, 10, 31, 6, 0, tzinfo=timezone.utc),
        )
        assert len(rows) == 1
        assert rows[0]["scheduled_time"] == time(1, 30)


# =============================================================================
# Parser — malformed / hostile rows
# =============================================================================

class TestParserMalformedRows:
    def test_U_single_time_cell_yields_date_but_no_scheduled(self):
        html = _arrivals_html(
            '<tr><td class="place">Faro</td><td class="airline">Ryanair</td>'
            '<td class="flight">FR1</td><td class="time">02/07</td>'
            '<td class="status">On time</td></tr>'
        )
        row = parse_boh_flight_board(html)["arrivals"][0]
        assert row["date"] == "02/07"
        assert row["scheduled"] is None
        # ...and the history builder must then drop it (no scheduled time)
        board = parse_boh_flight_board(html)
        assert build_history_rows(
            board, today=date(2026, 7, 2), now=datetime(2026, 7, 2, tzinfo=timezone.utc)
        ) == []

    def test_U_row_without_time_cells_kept_for_display_but_not_history(self):
        html = _arrivals_html(
            '<tr><td class="place">Faro</td><td class="flight">FR1</td>'
            '<td class="status">Cancelled</td></tr>'
        )
        board = parse_boh_flight_board(html)
        assert board["arrivals"][0]["date"] is None
        assert build_history_rows(
            board, today=date(2026, 7, 2), now=datetime(2026, 7, 2, tzinfo=timezone.utc)
        ) == []

    def test_U_classless_cells_are_ignored(self):
        html = _arrivals_html("<tr><td>Faro</td><td>FR1</td><td>14:00</td></tr>")
        assert parse_boh_flight_board(html)["arrivals"] == []

    def test_U_status_only_row_is_dropped(self):
        html = _arrivals_html('<tr><td class="status">Cancelled</td></tr>')
        assert parse_boh_flight_board(html)["arrivals"] == []

    def test_H_html_entities_are_unescaped(self):
        html = _arrivals_html(
            '<tr><td class="place">Toulon &amp; Hy&egrave;res</td>'
            '<td class="airline">Jet2</td><td class="flight">LS1</td>'
            '<td class="time">02/07</td><td class="time">14:00</td>'
            '<td class="status">As Scheduled</td></tr>'
        )
        assert parse_boh_flight_board(html)["arrivals"][0]["place"] == "Toulon & Hyères"

    def test_H_uppercase_tags_are_parsed(self):
        html = _arrivals_html(
            '<TR><TD CLASS="place">Faro</TD><TD CLASS="airline">Ryanair</TD>'
            '<TD CLASS="flight">FR1</TD><TD CLASS="time">02/07</TD>'
            '<TD CLASS="time">14:00</TD><TD CLASS="status">On time</TD></TR>'
        )
        row = parse_boh_flight_board(html)["arrivals"][0]
        assert row["flight"] == "FR1"
        assert row["scheduled"] == "14:00"

    def test_H_multi_class_time_cells_still_map_date_then_scheduled(self):
        html = _arrivals_html(
            '<tr><td class="place">Faro</td><td class="airline">Ryanair</td>'
            '<td class="flight">FR1</td><td class="time details-for-big">02/07</td>'
            '<td class="time details-for-big">14:00</td>'
            '<td class="status">On time</td></tr>'
        )
        row = parse_boh_flight_board(html)["arrivals"][0]
        assert row["date"] == "02/07"
        assert row["scheduled"] == "14:00"


# =============================================================================
# Employee endpoint hardening
# =============================================================================

class TestEmployeeEndpointHardening:
    def _client(self, snapshot):
        import main
        from database import get_db
        from main import app

        db = MagicMock()
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.first.return_value = snapshot
        db.query.return_value = chain

        def _get_db():
            yield db

        user = MagicMock()
        user.id = 7
        user.is_admin = False
        app.dependency_overrides[get_db] = _get_db
        app.dependency_overrides[main.get_current_user] = lambda: user
        return TestClient(app), app, chain

    def _teardown(self, app):
        app.dependency_overrides.clear()

    def _snapshot(self, created_at):
        snapshot = MagicMock()
        snapshot.status = "ok"
        snapshot.arrivals_json = [{"flight": "TOM6457"}]
        snapshot.departures_json = []
        snapshot.created_at = created_at
        return snapshot

    def test_H_query_serves_only_ok_snapshots_newest_first(self):
        """Error snapshots must never blank the board: the query itself has to
        filter status == 'ok' and order created_at DESC."""
        client, app, chain = self._client(None)
        try:
            client.get("/api/employee/flight-board")
            criterion = chain.filter.call_args[0][0]
            assert "status" in str(criterion)
            assert criterion.right.value == "ok"
            order = chain.order_by.call_args[0][0]
            assert "created_at" in str(order)
            assert "DESC" in str(order)
        finally:
            self._teardown(app)

    def test_U_snapshot_without_created_at_reports_stale(self):
        client, app, _ = self._client(self._snapshot(created_at=None))
        try:
            body = client.get("/api/employee/flight-board").json()
            assert body["available"] is True
            assert body["scraped_at"] is None
            assert body["age_minutes"] is None
            assert body["stale"] is True
        finally:
            self._teardown(app)

    def test_U_future_created_at_clamps_age_to_zero(self):
        # Clock skew between DB server and API must not produce negative ages.
        client, app, _ = self._client(
            self._snapshot(datetime.now(timezone.utc) + timedelta(minutes=5))
        )
        try:
            body = client.get("/api/employee/flight-board").json()
            assert body["age_minutes"] == 0
            assert body["stale"] is False
        finally:
            self._teardown(app)

    def test_H_stale_boundary_at_seconds_granularity(self):
        # Age floors to whole minutes: 45m30s -> 45 (fresh), 46m30s -> 46 (stale).
        for offset, expected_stale in (
            (timedelta(minutes=45, seconds=30), False),
            (timedelta(minutes=46, seconds=30), True),
        ):
            client, app, _ = self._client(
                self._snapshot(datetime.now(timezone.utc) - offset)
            )
            try:
                body = client.get("/api/employee/flight-board").json()
                assert body["stale"] is expected_stale, offset
            finally:
                self._teardown(app)

    def test_U_null_json_columns_serialise_as_empty_lists(self):
        snapshot = self._snapshot(datetime.now(timezone.utc))
        snapshot.arrivals_json = None
        snapshot.departures_json = None
        client, app, _ = self._client(snapshot)
        try:
            body = client.get("/api/employee/flight-board").json()
            assert body["available"] is True
            assert body["arrivals"] == []
            assert body["departures"] == []
        finally:
            self._teardown(app)


# =============================================================================
# Scheduler gate env parsing (Railway env values are literal strings)
# =============================================================================

class TestScrapeEnabledFlag:
    @pytest.mark.parametrize("raw", ["1", "true", "TRUE", "True", " yes ", "on", "On"])
    def test_H_enabled_values(self, monkeypatch, raw):
        monkeypatch.setenv("FLIGHT_BOARD_SCRAPE_ENABLED", raw)
        assert is_flight_board_scrape_enabled() is True

    @pytest.mark.parametrize("raw", ["", "0", "false", "off", "no", "enabled", '"true"'])
    def test_U_disabled_values(self, monkeypatch, raw):
        monkeypatch.setenv("FLIGHT_BOARD_SCRAPE_ENABLED", raw)
        assert is_flight_board_scrape_enabled() is False

    def test_U_unset_is_disabled(self, monkeypatch):
        monkeypatch.delenv("FLIGHT_BOARD_SCRAPE_ENABLED", raising=False)
        assert is_flight_board_scrape_enabled() is False
