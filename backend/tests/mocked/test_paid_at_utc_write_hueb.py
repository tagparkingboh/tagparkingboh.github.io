"""
HUEB tests for the paid_at write fix (locked 2026-06-15).

`payment.paid_at` was written with naive `datetime.utcnow()` into a
`timestamptz` column. Postgres interprets a NAIVE datetime in the DB session's
timezone, so under a Europe/London session it stored the value one hour early
in BST (and correctly in GMT) — skewing 128 rows. The fix is `utc_now()`, an
AWARE UTC datetime, which Postgres stores as the exact instant regardless of
session timezone or DST.

These tests:
  * pin `utc_now()`'s invariant (aware, zero UTC offset);
  * reproduce the old bug and prove the fix via a faithful simulation of how
    Postgres ingests a datetime into timestamptz;
  * assert correctness on BOTH sides of the clock change, so a future "clocks
    go back" never lands us in the opposite (one-hour-late) position.
"""
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import utc_now  # noqa: E402

LONDON = "Europe/London"
UTC = timezone.utc


def pg_store_timestamptz(value: datetime, session_tz: str) -> datetime:
    """Faithfully mimic how Postgres ingests a Python datetime into a
    `timestamptz` column, returning the UTC instant it would persist:

      * AWARE value  -> converted to UTC by its own offset (session tz ignored).
      * NAIVE value  -> ASSUMED to be in the session TimeZone, then to UTC.
    """
    if value.tzinfo is not None:
        return value.astimezone(UTC)
    return value.replace(tzinfo=ZoneInfo(session_tz)).astimezone(UTC)


# A real instant: 14 Jun 2026 23:12:57 UTC (BST -> 15 Jun 00:12 UK).
TRUE_BST = datetime(2026, 6, 14, 23, 12, 57, tzinfo=UTC)
# A real instant in winter: 14 Jan 2026 23:30:00 UTC (GMT, no offset).
TRUE_GMT = datetime(2026, 1, 14, 23, 30, 0, tzinfo=UTC)


# ===========================================================================
# HAPPY — utc_now() is aware UTC
# ===========================================================================

class TestUtcNowInvariant:

    def test_is_timezone_aware(self):
        assert utc_now().tzinfo is not None

    def test_offset_is_zero(self):
        assert utc_now().utcoffset() == timedelta(0)

    def test_is_not_naive_utcnow(self):
        # The whole point: it must NOT be a naive datetime.
        n = utc_now()
        assert n.tzinfo is not None and n.utcoffset() == timedelta(0)


# ===========================================================================
# UNHAPPY / regression — the old naive write was wrong in BST
# ===========================================================================

class TestNaiveWriteBugReproduced:

    def test_naive_utcnow_shifts_back_one_hour_in_bst(self):
        # Old code stored `datetime.utcnow()` — naive wall-clock UTC.
        naive = TRUE_BST.replace(tzinfo=None)  # 23:12:57, no tz
        stored = pg_store_timestamptz(naive, LONDON)
        # Postgres read it as 23:12:57 BST -> 22:12:57 UTC: one hour early.
        assert stored == TRUE_BST - timedelta(hours=1)
        assert stored.hour == 22

    def test_naive_stored_under_utc_session_is_correct(self):
        # Same naive value is fine IF the session happens to be UTC — which is
        # exactly why the bug only hit some rows.
        naive = TRUE_BST.replace(tzinfo=None)
        assert pg_store_timestamptz(naive, "UTC") == TRUE_BST


# ===========================================================================
# Fix — aware UTC stores the exact instant regardless of session tz
# ===========================================================================

class TestAwareWriteIsRobust:

    @pytest.mark.parametrize("session_tz", [LONDON, "UTC", "America/New_York"])
    def test_aware_bst_instant_preserved(self, session_tz):
        assert pg_store_timestamptz(TRUE_BST, session_tz) == TRUE_BST

    @pytest.mark.parametrize("session_tz", [LONDON, "UTC", "America/New_York"])
    def test_aware_gmt_instant_preserved(self, session_tz):
        assert pg_store_timestamptz(TRUE_GMT, session_tz) == TRUE_GMT


# ===========================================================================
# Clocks go back — we must not end up in the OPPOSITE position
# ===========================================================================

class TestClocksGoBack:

    def test_naive_bug_does_not_exist_in_gmt(self):
        # In winter London == UTC, so the naive write is (coincidentally) fine.
        naive = TRUE_GMT.replace(tzinfo=None)
        assert pg_store_timestamptz(naive, LONDON) == TRUE_GMT

    def test_aware_is_correct_in_both_seasons(self):
        # The fix is symmetric: exact instant in summer AND winter, so a
        # naive "always subtract an hour" would have been wrong in GMT but the
        # aware write never is.
        assert pg_store_timestamptz(TRUE_BST, LONDON) == TRUE_BST   # summer
        assert pg_store_timestamptz(TRUE_GMT, LONDON) == TRUE_GMT   # winter

    def test_aware_write_never_shifts_relative_to_naive_bug(self):
        # Summer: aware is 1h later than what the naive bug stored (i.e. correct).
        naive_summer = pg_store_timestamptz(TRUE_BST.replace(tzinfo=None), LONDON)
        aware_summer = pg_store_timestamptz(TRUE_BST, LONDON)
        assert aware_summer - naive_summer == timedelta(hours=1)
        # Winter: aware and the (correct) naive store agree — no opposite shift.
        naive_winter = pg_store_timestamptz(TRUE_GMT.replace(tzinfo=None), LONDON)
        aware_winter = pg_store_timestamptz(TRUE_GMT, LONDON)
        assert aware_winter - naive_winter == timedelta(0)


# ===========================================================================
# BOUNDARY — DST transition instants store exactly under the aware write
# ===========================================================================

class TestDstTransitionBoundary:
    """2026 UK DST: clocks forward 29 Mar 01:00 UTC, back 25 Oct 01:00 UTC.
    The aware write must persist the exact instant on either side of each."""

    @pytest.mark.parametrize("instant", [
        datetime(2026, 3, 29, 0, 59, 59, tzinfo=UTC),   # just before spring-forward
        datetime(2026, 3, 29, 1, 0, 0, tzinfo=UTC),     # at spring-forward
        datetime(2026, 3, 29, 1, 0, 1, tzinfo=UTC),     # just after
        datetime(2026, 10, 25, 0, 59, 59, tzinfo=UTC),  # just before fall-back
        datetime(2026, 10, 25, 1, 0, 0, tzinfo=UTC),    # at fall-back
        datetime(2026, 10, 25, 1, 0, 1, tzinfo=UTC),    # just after
    ])
    def test_aware_instant_round_trips_under_london_session(self, instant):
        assert pg_store_timestamptz(instant, LONDON) == instant
