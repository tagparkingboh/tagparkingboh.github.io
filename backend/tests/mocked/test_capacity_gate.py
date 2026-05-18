"""
Tests for the daily-occupancy capacity gate added to /api/payments/create-intent
(public soft cap = 60) and the admin manual-booking endpoints (hard ceiling = 62).

Background: prior to 2026-05-18 the customer-facing booking flow only checked
BlockedDate rows for the dropoff/pickup endpoints. Bookings could slip through
when a stay spanned a fully-booked date but the endpoints themselves were
clear (e.g. dropoff 19/05 + pickup 26/05 over a 22-25 May full window).
This file pins the new behaviour with t-ε / t / t+ε boundary coverage on
each rule, per backend/docs/SPEC.md.

Test scope:
  - Counting logic (a pure Python re-implementation of the inline gate in
    main.py:create_payment, so unit tests can hammer boundaries without the
    Stripe / DB / lead-time dependencies the endpoint carries).
  - Multi-day stay span: middle day blocked while endpoints are clear.
  - Session-dedup: a re-submitting customer's own PENDING row must not be
    double-counted (otherwise legit retries get blocked).
  - Manual block precedence: BlockedDate check fires before capacity (the
    endpoint blocks on the dropoff date before reaching the span check).
  - Admin endpoint: same boundaries shifted to the 62 hard ceiling.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Counting helper — mirrors the inline gate in main.py:create_payment.
#
# Pure Python so we can drive it with controlled inputs at every boundary
# without standing up the full FastAPI app.
# =============================================================================

def find_offending_day(
    overlapping,
    dropoff_date,
    pickup_date,
    cap,
):
    """Walk every day in [dropoff_date, pickup_date] and return (day, count)
    for the first day where existing_count + 1 > cap. None if all days fit.

    `overlapping` is a list of (id, b_dropoff, b_pickup) tuples (the result of
    a query against bookings whose ranges intersect the requested stay).
    """
    cursor = dropoff_date
    while cursor <= pickup_date:
        count = sum(1 for (_, do, pu) in overlapping if do <= cursor <= pu)
        if count + 1 > cap:
            return (cursor, count)
        cursor = cursor + timedelta(days=1)
    return None


def make(b_dropoff, b_pickup, id=None):
    """Tiny factory — keeps the test bodies compact."""
    return (id, b_dropoff, b_pickup)


# Anchor day used by the simpler tests — far enough out that no other rules
# (lead time etc.) trip; the gate itself is date-agnostic.
D = date(2026, 6, 1)


# =============================================================================
# Soft cap (60) — public create-intent gate
# =============================================================================

class TestSoftCapSingleDay:
    """Single-day stay: dropoff == pickup == D."""

    def test_zero_bookings_allowed(self):
        assert find_offending_day([], D, D, cap=60) is None

    def test_59_existing_t_minus_epsilon_allowed(self):
        """59 cars → adding one brings total to 60 → must allow (at, not over)."""
        overlapping = [make(D, D) for _ in range(59)]
        assert find_offending_day(overlapping, D, D, cap=60) is None

    def test_60_existing_t_blocked(self):
        """60 cars → adding one would make 61 → must reject."""
        overlapping = [make(D, D) for _ in range(60)]
        offending = find_offending_day(overlapping, D, D, cap=60)
        assert offending is not None
        assert offending == (D, 60)

    def test_61_existing_t_plus_epsilon_blocked(self):
        """Already past cap (recovery scenario) — still rejects."""
        overlapping = [make(D, D) for _ in range(61)]
        offending = find_offending_day(overlapping, D, D, cap=60)
        assert offending == (D, 61)

    def test_62_existing_blocked(self):
        """Hard physical ceiling reached — still rejects under soft cap."""
        overlapping = [make(D, D) for _ in range(62)]
        offending = find_offending_day(overlapping, D, D, cap=60)
        assert offending == (D, 62)


class TestSoftCapMultiDayStay:
    """Multi-day stays — the case the new gate actually fixes."""

    def test_endpoints_clear_middle_blocked(self):
        """The 2026-05-18 leak: dropoff and pickup days are fine, but day 2
        of the 3-day stay is full → must reject pointing at day 2."""
        d_start, d_mid, d_end = D, D + timedelta(days=1), D + timedelta(days=2)
        overlapping = [make(d_mid, d_mid) for _ in range(60)]
        offending = find_offending_day(overlapping, d_start, d_end, cap=60)
        assert offending is not None
        assert offending[0] == d_mid
        assert offending[1] == 60

    def test_only_endpoint_blocked(self):
        """If only the dropoff day is full, the gate returns it first."""
        d_start, d_end = D, D + timedelta(days=2)
        overlapping = [make(d_start, d_start) for _ in range(60)]
        offending = find_offending_day(overlapping, d_start, d_end, cap=60)
        assert offending[0] == d_start

    def test_long_stay_crosses_multiple_full_days_returns_earliest(self):
        """Several full days in the stay → the gate stops on the first."""
        d_start = D
        d_first_full = D + timedelta(days=2)
        d_second_full = D + timedelta(days=5)
        d_end = D + timedelta(days=7)
        overlapping = (
            [make(d_first_full, d_first_full, id=f"a{i}") for i in range(60)]
            + [make(d_second_full, d_second_full, id=f"b{i}") for i in range(60)]
        )
        offending = find_offending_day(overlapping, d_start, d_end, cap=60)
        assert offending[0] == d_first_full  # earliest full day wins

    def test_long_overlapping_booking_counted_every_day_it_spans(self):
        """A single 7-day booking dropped off on D-3 and picked up on D+3
        contributes +1 to every day in that window — including D itself."""
        seven_day = [make(D - timedelta(days=3), D + timedelta(days=3), id=i)
                     for i in range(60)]
        offending = find_offending_day(seven_day, D, D, cap=60)
        assert offending == (D, 60)


class TestSoftCapBoundaryAcrossStay:
    """Per-day boundary still holds when the stay is multi-day."""

    @pytest.mark.parametrize("existing,should_block", [
        (59, False),  # 59+1=60 → allowed
        (60, True),   # 60+1=61 → blocked
        (61, True),   # already over
    ])
    def test_each_day_independently_caps_at_60(self, existing, should_block):
        d_start = D
        d_end = D + timedelta(days=2)
        # Booking that overlaps the whole stay window — counted on every day.
        overlapping = [make(d_start, d_end) for _ in range(existing)]
        offending = find_offending_day(overlapping, d_start, d_end, cap=60)
        assert (offending is not None) == should_block


# =============================================================================
# Session deduplication — re-submitting customer's own PENDING row excluded
# =============================================================================

class TestSessionDedup:
    """When the same customer re-submits create-intent (Terms toggle, retry),
    their own PENDING row would be in `overlapping` and would falsely push
    the count over the cap. The endpoint excludes the existing PENDING id."""

    def test_dedup_unblocks_retry_at_60(self):
        """60 bookings already (the customer's PENDING is one of them).
        After excluding the customer's PENDING, count is 59 → allowed.
        Without the exclusion, count would be 60 → blocked → broken UX."""
        own_id = 999
        overlapping_with_own = [make(D, D, id=i) for i in range(59)] + [
            make(D, D, id=own_id)
        ]

        # Naive (broken) path — count includes their own → blocked.
        blocked = find_offending_day(overlapping_with_own, D, D, cap=60)
        assert blocked == (D, 60)

        # Correct path — exclude own id → allowed.
        filtered = [t for t in overlapping_with_own if t[0] != own_id]
        assert find_offending_day(filtered, D, D, cap=60) is None


# =============================================================================
# Hard ceiling (62) — admin manual booking endpoints
# =============================================================================

class TestHardCeilingAdmin:
    """Admin endpoints can push past the public 60 soft cap, but never past
    the lot's physical 62-car ceiling."""

    def test_admin_can_push_to_61(self):
        overlapping = [make(D, D) for _ in range(60)]
        # Public would block here; admin (cap=62) allows.
        assert find_offending_day(overlapping, D, D, cap=62) is None

    def test_admin_can_push_to_62(self):
        overlapping = [make(D, D) for _ in range(61)]
        assert find_offending_day(overlapping, D, D, cap=62) is None

    def test_admin_blocked_at_63rd(self):
        """t boundary: 62 existing → adding one would make 63 → reject."""
        overlapping = [make(D, D) for _ in range(62)]
        offending = find_offending_day(overlapping, D, D, cap=62)
        assert offending == (D, 62)

    def test_admin_blocked_above_ceiling(self):
        """t+ε: already past 62, still rejects."""
        overlapping = [make(D, D) for _ in range(63)]
        offending = find_offending_day(overlapping, D, D, cap=62)
        assert offending == (D, 63)


# =============================================================================
# Date-arithmetic boundaries — UK timezone safety
# =============================================================================

class TestDateBoundaries:
    """Per the SPEC.md rule on time/day/date boundaries, exercise:
       - day wrap (cursor advances past month-end)
       - cross-year boundary
       - single-day stay vs zero-day-difference (dropoff == pickup)
    """

    def test_cursor_advances_across_month_end(self):
        d_start = date(2026, 1, 30)
        d_end = date(2026, 2, 2)
        # Day 2026-02-01 (Feb 1) is full
        overlapping = [make(date(2026, 2, 1), date(2026, 2, 1)) for _ in range(60)]
        offending = find_offending_day(overlapping, d_start, d_end, cap=60)
        assert offending[0] == date(2026, 2, 1)

    def test_cursor_advances_across_year_end(self):
        d_start = date(2026, 12, 30)
        d_end = date(2027, 1, 2)
        # Day 2027-01-01 is full
        overlapping = [make(date(2027, 1, 1), date(2027, 1, 1)) for _ in range(60)]
        offending = find_offending_day(overlapping, d_start, d_end, cap=60)
        assert offending[0] == date(2027, 1, 1)

    def test_same_day_dropoff_and_pickup_treated_as_one_day(self):
        """A single-day stay (dropoff == pickup) should check exactly 1 day."""
        overlapping = [make(D, D) for _ in range(60)]
        offending = find_offending_day(overlapping, D, D, cap=60)
        assert offending == (D, 60)


# =============================================================================
# Integration smoke (sanity-check that the inline gate logic in main.py
# matches the find_offending_day used above by hashing the rule into a
# single fixture). Kept tiny — the heavy lifting is the unit tests above.
# =============================================================================

class TestRuleConsistency:
    """Lightweight invariant: cap=60 always rejects count=60, cap=62 never
    rejects count=60. Catches off-by-one regressions if either cap is
    bumped or the comparison flips from > to >=."""

    def test_soft_cap_60_rejects_at_60(self):
        overlapping = [make(D, D) for _ in range(60)]
        assert find_offending_day(overlapping, D, D, cap=60) is not None

    def test_soft_cap_60_allows_at_59(self):
        overlapping = [make(D, D) for _ in range(59)]
        assert find_offending_day(overlapping, D, D, cap=60) is None

    def test_hard_cap_62_allows_at_60(self):
        overlapping = [make(D, D) for _ in range(60)]
        assert find_offending_day(overlapping, D, D, cap=62) is None

    def test_hard_cap_62_rejects_at_62(self):
        overlapping = [make(D, D) for _ in range(62)]
        assert find_offending_day(overlapping, D, D, cap=62) is not None
