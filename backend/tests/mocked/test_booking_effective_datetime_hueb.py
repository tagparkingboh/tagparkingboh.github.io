"""
HUEB tests for the report "effective booking date" basis (locked 2026-06-15).

Booking-count / revenue reports bucket a booking on its payment-success day in
UK time (`payment.paid_at`), falling back to `created_at` when there's no
settled payment. This file pins:

  * `booking_effective_datetime()` — the single helper every in-scope report
    routes through (HUEB + DST + UK-midnight boundary triplets).
  * `/api/admin/bookings/stats` — proves the wiring: a booking initiated at
    23:59 and paid at 00:12 lands on the paid day, not the initiated day.

TestClient-based for the endpoint so it executes main.py and counts toward
coverage (per SPEC test conventions).
"""
import sys
from datetime import datetime, date, time, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app, booking_effective_datetime  # noqa: E402
from database import get_db  # noqa: E402
from db_models import Booking, BookingStatus, AuditLog  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _booking(*, created_at=None, paid_at="__unset__", with_payment=True):
    """A booking stub the helper can read. paid_at='__unset__' means a payment
    row exists but its paid_at is None; with_payment=False means no payment."""
    payment = None
    if with_payment:
        pa = None if paid_at == "__unset__" else paid_at
        payment = SimpleNamespace(paid_at=pa, amount_pence=5000)
    return SimpleNamespace(created_at=created_at, payment=payment)


def _utc(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


# ===========================================================================
# Unit: booking_effective_datetime — HAPPY
# ===========================================================================

class TestEffectiveDatetimeHappy:

    def test_uses_paid_at_when_present(self):
        # Paid at 23:12 UTC on 14 Jun (BST) = 00:12 on 15 Jun UK.
        b = _booking(
            created_at=_utc(2026, 6, 14, 22, 59),
            paid_at=_utc(2026, 6, 14, 23, 12),
        )
        eff = booking_effective_datetime(b)
        assert eff.date() == date(2026, 6, 15)
        assert (eff.hour, eff.minute) == (0, 12)

    def test_paid_at_preferred_over_created_at(self):
        # created_at is a different day; paid_at must win.
        b = _booking(
            created_at=_utc(2026, 6, 10, 9, 0),
            paid_at=_utc(2026, 6, 12, 9, 0),
        )
        assert booking_effective_datetime(b).date() == date(2026, 6, 12)

    def test_naive_paid_at_treated_as_utc(self):
        # Stored naive (no tzinfo) — helper assumes UTC then converts to UK.
        b = _booking(
            created_at=datetime(2026, 6, 14, 22, 59),
            paid_at=datetime(2026, 6, 14, 23, 12),  # naive
        )
        assert booking_effective_datetime(b).date() == date(2026, 6, 15)


# ===========================================================================
# Unit: booking_effective_datetime — UNHAPPY (fallback)
# ===========================================================================

class TestEffectiveDatetimeFallback:

    def test_no_payment_falls_back_to_created_at(self):
        b = _booking(created_at=_utc(2026, 6, 14, 9, 0), with_payment=False)
        assert booking_effective_datetime(b).date() == date(2026, 6, 14)

    def test_payment_without_paid_at_falls_back_to_created_at(self):
        b = _booking(created_at=_utc(2026, 6, 14, 9, 0))  # paid_at None
        assert booking_effective_datetime(b).date() == date(2026, 6, 14)

    def test_non_datetime_paid_at_is_ignored(self):
        # A truthy-but-not-datetime paid_at (the MagicMock hazard) must not be
        # trusted — fall back to created_at.
        b = SimpleNamespace(
            created_at=_utc(2026, 6, 14, 9, 0),
            payment=SimpleNamespace(paid_at="not-a-datetime"),
        )
        assert booking_effective_datetime(b).date() == date(2026, 6, 14)


# ===========================================================================
# Unit: booking_effective_datetime — EDGE
# ===========================================================================

class TestEffectiveDatetimeEdge:

    def test_neither_timestamp_returns_none(self):
        b = _booking(created_at=None, with_payment=False)
        assert booking_effective_datetime(b) is None

    def test_payment_none_paid_at_and_no_created_at_returns_none(self):
        b = _booking(created_at=None)  # payment exists, paid_at None
        assert booking_effective_datetime(b) is None


# ===========================================================================
# Unit: booking_effective_datetime — BOUNDARY (UK midnight, BST + GMT)
# ===========================================================================

class TestEffectiveDatetimeBoundary:
    """UK midnight is 23:00 UTC in BST (summer) and 00:00 UTC in GMT (winter).
    t-ε / t / t+ε on the paid_at across that boundary."""

    # --- BST (June, UTC+1): UK midnight == 23:00 UTC ---
    def test_bst_just_before_uk_midnight(self):
        b = _booking(paid_at=_utc(2026, 6, 14, 22, 59, 59))
        assert booking_effective_datetime(b).date() == date(2026, 6, 14)

    def test_bst_at_uk_midnight(self):
        b = _booking(paid_at=_utc(2026, 6, 14, 23, 0, 0))
        assert booking_effective_datetime(b).date() == date(2026, 6, 15)

    def test_bst_just_after_uk_midnight(self):
        b = _booking(paid_at=_utc(2026, 6, 14, 23, 0, 1))
        assert booking_effective_datetime(b).date() == date(2026, 6, 15)

    # --- GMT (January, UTC+0): UK midnight == 00:00 UTC ---
    def test_gmt_just_before_uk_midnight(self):
        b = _booking(paid_at=_utc(2026, 1, 14, 23, 59, 59))
        assert booking_effective_datetime(b).date() == date(2026, 1, 14)

    def test_gmt_at_uk_midnight(self):
        b = _booking(paid_at=_utc(2026, 1, 15, 0, 0, 0))
        assert booking_effective_datetime(b).date() == date(2026, 1, 15)

    def test_gmt_just_after_uk_midnight(self):
        b = _booking(paid_at=_utc(2026, 1, 15, 0, 0, 1))
        assert booking_effective_datetime(b).date() == date(2026, 1, 15)


# ===========================================================================
# Endpoint: /api/admin/bookings/stats buckets on the paid (UK) day
# ===========================================================================

class _FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def order_by(self, *_, **__):
        return self

    def filter(self, *_, **__):
        return self

    def options(self, *_, **__):
        return self

    def join(self, *_, **__):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


def _stats_booking(ref, created_at, paid_at, status=BookingStatus.CONFIRMED):
    return SimpleNamespace(
        id=ref,
        reference=ref,
        status=status,
        created_at=created_at,
        payment=SimpleNamespace(paid_at=paid_at, amount_pence=5000),
        dropoff_date=date(2026, 7, 1),
        dropoff_time=time(8, 0),
        pickup_date=date(2026, 7, 8),
        pickup_time=time(18, 0),
    )


@pytest.fixture
def stats_client():
    bookings = [
        # Initiated 23:59 BST on 14 Jun, paid 00:12 BST on 15 Jun -> 15 Jun.
        _stats_booking("TAG-CROSS01", _utc(2026, 6, 14, 22, 59), _utc(2026, 6, 14, 23, 12)),
        # Plainly on 15 Jun.
        _stats_booking("TAG-SAME015", _utc(2026, 6, 15, 9, 0), _utc(2026, 6, 15, 9, 5)),
    ]

    db = SimpleNamespace()

    def _query(model):
        if model is AuditLog:
            return _FakeQuery([])
        return _FakeQuery(bookings)

    db.query = _query

    def _override_get_db():
        yield db

    from main import require_admin
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, email="admin@test", is_admin=True)
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestBookingStatsPaidDayBucketing:

    def test_cross_midnight_booking_counts_on_paid_day(self, stats_client):
        resp = stats_client.get("/api/admin/bookings/stats")
        assert resp.status_code == 200
        daily = {row["date"]: row for row in resp.json()["daily"]}

        # Both bookings land on the paid day (15 Jun); none on the 14th.
        assert "2026-06-14" not in daily
        assert daily["2026-06-15"]["confirmed"] == 2
        assert daily["2026-06-15"]["total"] == 2


def _build_stats_client(bookings):
    """A TestClient whose Booking queries return `bookings` and AuditLog []."""
    db = SimpleNamespace()
    db.query = lambda model: _FakeQuery([]) if model is AuditLog else _FakeQuery(bookings)

    def _override_get_db():
        yield db

    from main import require_admin
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, email="admin@test", is_admin=True)
    return TestClient(app)


class TestMonthlyPatternPaidBasis:
    """monthly_booking_pattern must bucket by the paid week, not the created
    week — the surface that showed Days 15-21 as 20 instead of 21."""

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_buckets_by_paid_week_not_created_week(self):
        from main import get_uk_now
        now = get_uk_now()
        y, m = now.year, now.month
        # Created on day 7 (W1, Days 1-7); paid on day 8 (W2, Days 8-14).
        b = _stats_booking("TAG-WK0001", _utc(y, m, 7, 10, 0), _utc(y, m, 8, 10, 0))
        resp = _build_stats_client([b]).get("/api/admin/bookings/stats")
        assert resp.status_code == 200

        months = resp.json()["monthly_booking_pattern"]["months"]
        this_month = next(mo for mo in months if mo["month"] == f"{y}-{m:02d}")
        counts = {x["key"]: x["count"] for x in this_month["buckets"]}
        assert counts["W2"] == 1   # paid week
        assert counts["W1"] == 0   # NOT the created week
