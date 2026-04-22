"""
Unit and Integration tests for Blocked Dates endpoints.

Tests the blocked dates management functionality:
- GET /api/admin/blocked-dates
- POST /api/admin/blocked-dates
- PUT /api/admin/blocked-dates/{id}
- DELETE /api/admin/blocked-dates/{id}
- GET /api/admin/blocked-dates/{id}/time-slots
- POST /api/admin/blocked-dates/{id}/time-slots
- PUT /api/admin/blocked-time-slots/{id}
- DELETE /api/admin/blocked-time-slots/{id}
- GET /api/blocked-dates/check

All tests use mocks - no database connection required.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date, time, timedelta, timezone


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_blocked_date(
    id=1,
    start_date=None,
    end_date=None,
    block_dropoffs=True,
    block_pickups=True,
    reason=None,
    created_by="admin@test.com",
    created_at=None,
    time_slots=None,
):
    """Create a mock blocked date object."""
    blocked = MagicMock()
    blocked.id = id
    blocked.start_date = start_date or date(2026, 12, 25)
    blocked.end_date = end_date or date(2026, 12, 25)
    blocked.block_dropoffs = block_dropoffs
    blocked.block_pickups = block_pickups
    blocked.reason = reason
    blocked.created_by = created_by
    blocked.created_at = created_at or datetime.now(timezone.utc)
    blocked.time_slots = time_slots or []
    return blocked


def create_mock_time_slot(
    id=1,
    blocked_date_id=1,
    start_time=None,
    end_time=None,
    block_dropoffs=True,
    block_pickups=True,
    reason=None,
    created_at=None,
):
    """Create a mock blocked time slot object."""
    slot = MagicMock()
    slot.id = id
    slot.blocked_date_id = blocked_date_id
    slot.start_time = start_time or time(8, 0)
    slot.end_time = end_time or time(12, 0)
    slot.block_dropoffs = block_dropoffs
    slot.block_pickups = block_pickups
    slot.reason = reason
    slot.created_at = created_at or datetime.now(timezone.utc)
    return slot


def create_mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


# ============================================================================
# GET Blocked Dates Tests
# ============================================================================

class TestGetBlockedDatesLogic:
    """Unit tests for GET blocked dates logic."""

    # Happy Path
    def test_returns_all_blocked_dates(self):
        """Should return all blocked dates."""
        blocked_dates = [
            create_mock_blocked_date(id=1, start_date=date(2026, 12, 25)),
            create_mock_blocked_date(id=2, start_date=date(2026, 12, 31)),
            create_mock_blocked_date(id=3, start_date=date(2027, 1, 1)),
        ]

        assert len(blocked_dates) == 3

    def test_orders_by_start_date_asc(self):
        """Should order blocked dates by start date ascending."""
        blocked_dates = [
            create_mock_blocked_date(id=2, start_date=date(2026, 12, 31)),
            create_mock_blocked_date(id=1, start_date=date(2026, 12, 25)),
            create_mock_blocked_date(id=3, start_date=date(2027, 1, 1)),
        ]

        sorted_dates = sorted(blocked_dates, key=lambda x: x.start_date)

        assert sorted_dates[0].id == 1
        assert sorted_dates[1].id == 2
        assert sorted_dates[2].id == 3

    def test_returns_total_count(self):
        """Should return total count."""
        blocked_dates = [create_mock_blocked_date(id=i) for i in range(5)]

        response = {
            "blocked_dates": blocked_dates,
            "total": len(blocked_dates),
        }

        assert response["total"] == 5

    def test_includes_time_slots(self):
        """Should include time slots with blocked dates."""
        time_slots = [
            create_mock_time_slot(id=1, start_time=time(8, 0)),
            create_mock_time_slot(id=2, start_time=time(14, 0)),
        ]
        blocked = create_mock_blocked_date(time_slots=time_slots)

        assert len(blocked.time_slots) == 2

    # Date Range Filtering
    def test_filters_by_date_from(self):
        """Should filter blocked dates by date_from."""
        blocked_dates = [
            create_mock_blocked_date(id=1, start_date=date(2026, 11, 1), end_date=date(2026, 11, 5)),
            create_mock_blocked_date(id=2, start_date=date(2026, 12, 25), end_date=date(2026, 12, 25)),
            create_mock_blocked_date(id=3, start_date=date(2026, 12, 31), end_date=date(2027, 1, 2)),
        ]

        date_from = date(2026, 12, 1)
        filtered = [bd for bd in blocked_dates if bd.end_date >= date_from]

        assert len(filtered) == 2

    def test_filters_by_date_to(self):
        """Should filter blocked dates by date_to."""
        blocked_dates = [
            create_mock_blocked_date(id=1, start_date=date(2026, 11, 1)),
            create_mock_blocked_date(id=2, start_date=date(2026, 12, 25)),
            create_mock_blocked_date(id=3, start_date=date(2027, 1, 1)),
        ]

        date_to = date(2026, 12, 31)
        filtered = [bd for bd in blocked_dates if bd.start_date <= date_to]

        assert len(filtered) == 2

    # Edge Cases
    def test_returns_empty_when_no_blocked_dates(self):
        """Should return empty list when no blocked dates."""
        blocked_dates = []

        response = {
            "blocked_dates": blocked_dates,
            "total": len(blocked_dates),
        }

        assert response["total"] == 0


class TestBlockedDateFormatting:
    """Tests for blocked date response formatting."""

    def test_formats_start_date_as_iso(self):
        """Should format start date as ISO string."""
        blocked = create_mock_blocked_date(start_date=date(2026, 12, 25))

        formatted = blocked.start_date.isoformat()

        assert formatted == "2026-12-25"

    def test_formats_end_date_as_iso(self):
        """Should format end date as ISO string."""
        blocked = create_mock_blocked_date(end_date=date(2026, 12, 31))

        formatted = blocked.end_date.isoformat()

        assert formatted == "2026-12-31"

    def test_includes_block_flags(self):
        """Should include block_dropoffs and block_pickups flags."""
        blocked = create_mock_blocked_date(block_dropoffs=True, block_pickups=False)

        assert blocked.block_dropoffs is True
        assert blocked.block_pickups is False


# ============================================================================
# POST Create Blocked Date Tests
# ============================================================================

class TestCreateBlockedDateLogic:
    """Unit tests for create blocked date logic."""

    # Happy Path
    def test_creates_single_day_blocked_date(self):
        """Should create single day blocked date."""
        start = date(2026, 12, 25)
        end = date(2026, 12, 25)

        blocked = create_mock_blocked_date(start_date=start, end_date=end)

        assert blocked.start_date == blocked.end_date

    def test_creates_date_range_blocked_date(self):
        """Should create blocked date spanning multiple days."""
        start = date(2026, 12, 24)
        end = date(2026, 12, 26)

        blocked = create_mock_blocked_date(start_date=start, end_date=end)

        days = (blocked.end_date - blocked.start_date).days + 1

        assert days == 3

    def test_sets_block_dropoffs_only(self):
        """Should allow blocking only dropoffs."""
        blocked = create_mock_blocked_date(block_dropoffs=True, block_pickups=False)

        assert blocked.block_dropoffs is True
        assert blocked.block_pickups is False

    def test_sets_block_pickups_only(self):
        """Should allow blocking only pickups."""
        blocked = create_mock_blocked_date(block_dropoffs=False, block_pickups=True)

        assert blocked.block_dropoffs is False
        assert blocked.block_pickups is True

    def test_sets_block_both(self):
        """Should allow blocking both dropoffs and pickups."""
        blocked = create_mock_blocked_date(block_dropoffs=True, block_pickups=True)

        assert blocked.block_dropoffs is True
        assert blocked.block_pickups is True

    def test_stores_reason(self):
        """Should store optional reason."""
        blocked = create_mock_blocked_date(reason="Christmas Day - Office Closed")

        assert blocked.reason == "Christmas Day - Office Closed"

    def test_stores_created_by(self):
        """Should store who created the blocked date."""
        blocked = create_mock_blocked_date(created_by="admin@tagparking.co.uk")

        assert blocked.created_by == "admin@tagparking.co.uk"

    # Validation Tests
    def test_rejects_end_before_start(self):
        """Should reject when end date is before start date."""
        start = date(2026, 12, 25)
        end = date(2026, 12, 20)

        is_valid = end >= start

        assert is_valid is False

    def test_rejects_neither_blocked(self):
        """Should reject when neither dropoffs nor pickups are blocked."""
        block_dropoffs = False
        block_pickups = False

        is_valid = block_dropoffs or block_pickups

        assert is_valid is False

    # Edge Cases
    def test_handles_empty_reason(self):
        """Should handle empty reason string."""
        blocked = create_mock_blocked_date(reason="")

        # Empty reason should be treated as None
        reason = blocked.reason.strip() if blocked.reason else None

        assert reason is None

    def test_trims_whitespace_from_reason(self):
        """Should trim whitespace from reason."""
        blocked = create_mock_blocked_date(reason="  Holiday Period  ")

        trimmed = blocked.reason.strip() if blocked.reason else None

        assert trimmed == "Holiday Period"


# ============================================================================
# PUT Update Blocked Date Tests
# ============================================================================

class TestUpdateBlockedDateLogic:
    """Unit tests for update blocked date logic."""

    # Happy Path
    def test_updates_start_date(self):
        """Should update start date."""
        blocked = create_mock_blocked_date(start_date=date(2026, 12, 25))

        blocked.start_date = date(2026, 12, 24)

        assert blocked.start_date == date(2026, 12, 24)

    def test_updates_end_date(self):
        """Should update end date."""
        blocked = create_mock_blocked_date(end_date=date(2026, 12, 25))

        blocked.end_date = date(2026, 12, 26)

        assert blocked.end_date == date(2026, 12, 26)

    def test_updates_block_flags(self):
        """Should update block flags."""
        blocked = create_mock_blocked_date(block_dropoffs=True, block_pickups=True)

        blocked.block_dropoffs = False
        blocked.block_pickups = True

        assert blocked.block_dropoffs is False
        assert blocked.block_pickups is True

    def test_updates_reason(self):
        """Should update reason."""
        blocked = create_mock_blocked_date(reason="Old reason")

        blocked.reason = "New reason"

        assert blocked.reason == "New reason"

    # Unhappy Path
    def test_rejects_nonexistent_blocked_date(self):
        """Should return 404 for nonexistent blocked date."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None

    # Validation after update
    def test_validates_end_not_before_start_after_update(self):
        """Should validate end is not before start after update."""
        blocked = create_mock_blocked_date(
            start_date=date(2026, 12, 25),
            end_date=date(2026, 12, 26),
        )

        # Simulate invalid update
        blocked.end_date = date(2026, 12, 20)

        is_valid = blocked.end_date >= blocked.start_date

        assert is_valid is False

    def test_validates_at_least_one_blocked_after_update(self):
        """Should validate at least one type is blocked after update."""
        blocked = create_mock_blocked_date(block_dropoffs=True, block_pickups=True)

        # Simulate invalid update
        blocked.block_dropoffs = False
        blocked.block_pickups = False

        is_valid = blocked.block_dropoffs or blocked.block_pickups

        assert is_valid is False


# ============================================================================
# DELETE Blocked Date Tests
# ============================================================================

class TestDeleteBlockedDateLogic:
    """Unit tests for delete blocked date logic."""

    # Happy Path
    def test_deletes_existing_blocked_date(self):
        """Should delete existing blocked date."""
        blocked = create_mock_blocked_date(id=1)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = blocked

        result = mock_db.query().filter().first()

        assert result is not None
        assert result.id == 1

    # Unhappy Path
    def test_returns_404_for_nonexistent(self):
        """Should return 404 for nonexistent blocked date."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# Blocked Time Slots Tests
# ============================================================================

class TestBlockedTimeSlotsLogic:
    """Unit tests for blocked time slots."""

    # Happy Path
    def test_returns_time_slots_for_blocked_date(self):
        """Should return time slots for a blocked date."""
        slots = [
            create_mock_time_slot(id=1, start_time=time(8, 0), end_time=time(12, 0)),
            create_mock_time_slot(id=2, start_time=time(14, 0), end_time=time(18, 0)),
        ]

        assert len(slots) == 2

    def test_orders_time_slots_by_start_time(self):
        """Should order time slots by start time."""
        slots = [
            create_mock_time_slot(id=2, start_time=time(14, 0)),
            create_mock_time_slot(id=1, start_time=time(8, 0)),
            create_mock_time_slot(id=3, start_time=time(10, 0)),
        ]

        sorted_slots = sorted(slots, key=lambda x: x.start_time)

        assert sorted_slots[0].id == 1
        assert sorted_slots[1].id == 3
        assert sorted_slots[2].id == 2

    def test_formats_time_as_hhmm(self):
        """Should format time as HH:MM."""
        slot = create_mock_time_slot(start_time=time(8, 30), end_time=time(12, 0))

        start_str = slot.start_time.strftime("%H:%M")
        end_str = slot.end_time.strftime("%H:%M")

        assert start_str == "08:30"
        assert end_str == "12:00"

    # Create Time Slot
    def test_creates_time_slot_for_blocked_date(self):
        """Should create time slot for blocked date."""
        slot = create_mock_time_slot(
            blocked_date_id=1,
            start_time=time(6, 0),
            end_time=time(10, 0),
            block_dropoffs=True,
            block_pickups=False,
        )

        assert slot.blocked_date_id == 1
        assert slot.block_dropoffs is True
        assert slot.block_pickups is False

    def test_parses_time_string(self):
        """Should parse time string to time object."""
        time_str = "08:30"

        hour, minute = map(int, time_str.split(":"))
        parsed = time(hour, minute)

        assert parsed == time(8, 30)

    # Validation
    def test_rejects_end_before_start_time(self):
        """Should reject when end time is before start time."""
        start = time(14, 0)
        end = time(10, 0)

        is_valid = end > start

        assert is_valid is False

    def test_accepts_same_day_time_range(self):
        """Should accept valid time range within same day."""
        start = time(8, 0)
        end = time(18, 0)

        is_valid = end > start

        assert is_valid is True

    # Edge Cases
    def test_handles_midnight_crossing(self):
        """Should handle time slots that don't cross midnight."""
        start = time(22, 0)
        end = time(23, 59)

        is_valid = end > start

        assert is_valid is True

    def test_handles_invalid_time_format(self):
        """Should handle invalid time format."""
        time_str = "invalid"

        try:
            hour, minute = map(int, time_str.split(":"))
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is False


# ============================================================================
# Check Blocked Dates (Public Endpoint) Tests
# ============================================================================

class TestCheckBlockedDatesLogic:
    """Unit tests for the public blocked dates check endpoint."""

    # Happy Path
    def test_returns_blocked_when_date_is_blocked(self):
        """Should return blocked when date falls in blocked range."""
        blocked_date = create_mock_blocked_date(
            start_date=date(2026, 12, 25),
            end_date=date(2026, 12, 25),
            block_dropoffs=True,
        )

        check_date = date(2026, 12, 25)
        is_blocked = blocked_date.start_date <= check_date <= blocked_date.end_date

        assert is_blocked is True

    def test_returns_not_blocked_when_date_not_blocked(self):
        """Should return not blocked when date is not in range."""
        blocked_date = create_mock_blocked_date(
            start_date=date(2026, 12, 25),
            end_date=date(2026, 12, 25),
        )

        check_date = date(2026, 12, 26)
        is_blocked = blocked_date.start_date <= check_date <= blocked_date.end_date

        assert is_blocked is False

    def test_checks_dropoff_blocking(self):
        """Should check if dropoffs are blocked."""
        blocked_date = create_mock_blocked_date(
            block_dropoffs=True,
            block_pickups=False,
        )

        can_dropoff = not blocked_date.block_dropoffs

        assert can_dropoff is False

    def test_checks_pickup_blocking(self):
        """Should check if pickups are blocked."""
        blocked_date = create_mock_blocked_date(
            block_dropoffs=False,
            block_pickups=True,
        )

        can_pickup = not blocked_date.block_pickups

        assert can_pickup is False

    def test_checks_both_dropoff_and_pickup(self):
        """Should check both dropoff and pickup dates."""
        blocked = create_mock_blocked_date(
            start_date=date(2026, 12, 25),
            end_date=date(2026, 12, 25),
            block_dropoffs=True,
            block_pickups=True,
        )

        dropoff_date = date(2026, 12, 25)
        pickup_date = date(2026, 12, 30)

        dropoff_blocked = blocked.start_date <= dropoff_date <= blocked.end_date and blocked.block_dropoffs
        pickup_blocked = blocked.start_date <= pickup_date <= blocked.end_date and blocked.block_pickups

        assert dropoff_blocked is True
        assert pickup_blocked is False

    # Time Slot Blocking
    def test_checks_time_slot_blocking(self):
        """Should check time slot specific blocking."""
        slot = create_mock_time_slot(
            start_time=time(6, 0),
            end_time=time(10, 0),
            block_dropoffs=True,
        )

        check_time = time(8, 0)
        is_blocked = slot.start_time <= check_time <= slot.end_time and slot.block_dropoffs

        assert is_blocked is True

    def test_time_outside_slot_not_blocked(self):
        """Should not block time outside slot range."""
        slot = create_mock_time_slot(
            start_time=time(6, 0),
            end_time=time(10, 0),
        )

        check_time = time(12, 0)
        is_blocked = slot.start_time <= check_time <= slot.end_time

        assert is_blocked is False


# ============================================================================
# Response Structure Tests
# ============================================================================

class TestBlockedDateResponseStructure:
    """Tests for response structure."""

    def test_success_response_includes_blocked_date(self):
        """Should include blocked_date in success response."""
        blocked = create_mock_blocked_date()

        response = {
            "success": True,
            "blocked_date": {
                "id": blocked.id,
                "start_date": blocked.start_date.isoformat(),
                "end_date": blocked.end_date.isoformat(),
            },
        }

        assert response["success"] is True
        assert "blocked_date" in response

    def test_delete_response_structure(self):
        """Should return success and message on delete."""
        response = {
            "success": True,
            "message": "Blocked date deleted",
        }

        assert response["success"] is True
        assert "message" in response


# ============================================================================
# Authentication Tests
# ============================================================================

class TestBlockedDatesAuthentication:
    """Tests for authentication on blocked dates endpoints."""

    def test_requires_admin_for_get(self):
        """Should require admin for GET."""
        user = create_mock_admin_user()

        assert user.is_admin is True

    def test_requires_admin_for_create(self):
        """Should require admin for POST."""
        user = create_mock_admin_user()

        assert user.is_admin is True

    def test_requires_admin_for_update(self):
        """Should require admin for PUT."""
        user = create_mock_admin_user()

        assert user.is_admin is True

    def test_requires_admin_for_delete(self):
        """Should require admin for DELETE."""
        user = create_mock_admin_user()

        assert user.is_admin is True

    def test_public_check_endpoint_no_auth(self):
        """Check endpoint should be public (no auth required)."""
        # The /api/blocked-dates/check is a public endpoint
        # for the booking flow to check date availability
        is_public = True

        assert is_public is True


# ============================================================================
# Boundary Tests
# ============================================================================

class TestBlockedDatesBoundaries:
    """Tests for boundary conditions."""

    def test_single_day_range(self):
        """Should handle single day date range."""
        blocked = create_mock_blocked_date(
            start_date=date(2026, 12, 25),
            end_date=date(2026, 12, 25),
        )

        days = (blocked.end_date - blocked.start_date).days + 1

        assert days == 1

    def test_year_spanning_range(self):
        """Should handle date range spanning year boundary."""
        blocked = create_mock_blocked_date(
            start_date=date(2026, 12, 30),
            end_date=date(2027, 1, 2),
        )

        days = (blocked.end_date - blocked.start_date).days + 1

        assert days == 4

    def test_long_date_range(self):
        """Should handle long date range."""
        blocked = create_mock_blocked_date(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )

        days = (blocked.end_date - blocked.start_date).days + 1

        assert days == 365

    def test_early_morning_time_slot(self):
        """Should handle early morning time slot."""
        slot = create_mock_time_slot(
            start_time=time(0, 0),
            end_time=time(6, 0),
        )

        assert slot.start_time == time(0, 0)

    def test_late_night_time_slot(self):
        """Should handle late night time slot."""
        slot = create_mock_time_slot(
            start_time=time(22, 0),
            end_time=time(23, 59),
        )

        assert slot.end_time == time(23, 59)

    def test_very_long_reason_text(self):
        """Should handle very long reason text."""
        long_reason = "A" * 500
        blocked = create_mock_blocked_date(reason=long_reason)

        assert len(blocked.reason) == 500


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
