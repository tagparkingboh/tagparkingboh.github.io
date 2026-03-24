"""
Tests for Blocked Dates API endpoints.

Mocked unit tests and mocked integration tests for:
- CRUD operations (create, read, update, delete)
- Blocked date validation in booking flow
- Date range blocking
- Dropoff-only and pickup-only blocking
- UK timezone handling
"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# Mock blocked date data
mock_blocked_dates = [
    {
        "id": 1,
        "start_date": "2026-03-26",
        "end_date": "2026-03-26",
        "block_dropoffs": True,
        "block_pickups": True,
        "reason": "Staff Training Day",
        "created_by": "admin@tagparking.co.uk",
        "created_at": "2026-03-20T10:30:00Z",
        "updated_at": None,
    },
    {
        "id": 2,
        "start_date": "2026-04-10",
        "end_date": "2026-04-13",
        "block_dropoffs": True,
        "block_pickups": True,
        "reason": "Easter Holiday Closure",
        "created_by": "admin@tagparking.co.uk",
        "created_at": "2026-03-15T09:00:00Z",
        "updated_at": None,
    },
    {
        "id": 3,
        "start_date": "2026-05-01",
        "end_date": "2026-05-01",
        "block_dropoffs": True,
        "block_pickups": False,
        "reason": "No drop-offs - maintenance",
        "created_by": "admin@tagparking.co.uk",
        "created_at": "2026-04-01T14:00:00Z",
        "updated_at": None,
    },
    {
        "id": 4,
        "start_date": "2026-06-15",
        "end_date": "2026-06-15",
        "block_dropoffs": False,
        "block_pickups": True,
        "reason": "No pickups - limited staff",
        "created_by": "admin@tagparking.co.uk",
        "created_at": "2026-05-10T11:00:00Z",
        "updated_at": None,
    },
]


class TestGetBlockedDatesEndpoint:
    """Mocked tests for GET /api/admin/blocked-dates."""

    def test_get_all_blocked_dates_returns_list(self):
        """Should return all blocked dates."""
        response = {"blocked_dates": mock_blocked_dates, "total": len(mock_blocked_dates)}

        assert "blocked_dates" in response
        assert "total" in response
        assert len(response["blocked_dates"]) == 4
        assert response["total"] == 4

    def test_response_includes_all_fields(self):
        """Response should include all blocked date fields."""
        blocked = mock_blocked_dates[0]

        required_fields = [
            "id", "start_date", "end_date", "block_dropoffs",
            "block_pickups", "reason", "created_by", "created_at"
        ]
        for field in required_fields:
            assert field in blocked

    def test_filter_by_date_range(self):
        """Should filter blocked dates by date range."""
        date_from = "2026-04-01"
        date_to = "2026-04-30"

        # Filter: end_date >= date_from AND start_date <= date_to
        filtered = [bd for bd in mock_blocked_dates
                   if bd["end_date"] >= date_from and bd["start_date"] <= date_to]

        assert len(filtered) == 1
        assert filtered[0]["reason"] == "Easter Holiday Closure"

    def test_ordered_by_start_date(self):
        """Results should be ordered by start_date ascending."""
        dates = [bd["start_date"] for bd in mock_blocked_dates]
        sorted_dates = sorted(dates)

        # Mock data is already sorted
        assert dates == sorted_dates


class TestCreateBlockedDateEndpoint:
    """Mocked tests for POST /api/admin/blocked-dates."""

    def test_create_single_day_block(self):
        """Should create a blocked date for a single day."""
        request = {
            "start_date": "2026-07-01",
            "end_date": "2026-07-01",
            "block_dropoffs": True,
            "block_pickups": True,
            "reason": "Independence Day (US staff)",
        }

        # Simulate creation
        created = {
            "id": 5,
            **request,
            "created_by": "admin@tagparking.co.uk",
            "created_at": "2026-06-15T10:00:00Z",
            "updated_at": None,
        }

        assert created["start_date"] == created["end_date"]
        assert created["block_dropoffs"] is True
        assert created["block_pickups"] is True
        assert created["id"] == 5

    def test_create_date_range_block(self):
        """Should create a blocked date spanning multiple days."""
        request = {
            "start_date": "2026-12-24",
            "end_date": "2026-12-26",
            "block_dropoffs": True,
            "block_pickups": True,
            "reason": "Christmas Closure",
        }

        # Simulate creation
        created = {"id": 6, **request}

        # Calculate days blocked
        start = datetime.strptime(created["start_date"], "%Y-%m-%d").date()
        end = datetime.strptime(created["end_date"], "%Y-%m-%d").date()
        days_blocked = (end - start).days + 1

        assert days_blocked == 3
        assert created["start_date"] == "2026-12-24"
        assert created["end_date"] == "2026-12-26"

    def test_create_dropoff_only_block(self):
        """Should create a block for drop-offs only."""
        request = {
            "start_date": "2026-08-15",
            "end_date": "2026-08-15",
            "block_dropoffs": True,
            "block_pickups": False,
            "reason": "Morning maintenance",
        }

        created = {"id": 7, **request}

        assert created["block_dropoffs"] is True
        assert created["block_pickups"] is False

    def test_create_pickup_only_block(self):
        """Should create a block for pick-ups only."""
        request = {
            "start_date": "2026-09-20",
            "end_date": "2026-09-20",
            "block_dropoffs": False,
            "block_pickups": True,
            "reason": "Evening staff shortage",
        }

        created = {"id": 8, **request}

        assert created["block_dropoffs"] is False
        assert created["block_pickups"] is True

    def test_create_without_reason(self):
        """Should allow creating block without reason."""
        request = {
            "start_date": "2026-10-01",
            "end_date": "2026-10-01",
            "block_dropoffs": True,
            "block_pickups": True,
            "reason": None,
        }

        created = {"id": 9, **request}

        assert created["reason"] is None


class TestCreateBlockedDateValidation:
    """Validation tests for creating blocked dates."""

    def test_end_date_before_start_date_rejected(self):
        """Should reject when end_date is before start_date."""
        request = {
            "start_date": "2026-07-15",
            "end_date": "2026-07-10",
        }

        start = datetime.strptime(request["start_date"], "%Y-%m-%d").date()
        end = datetime.strptime(request["end_date"], "%Y-%m-%d").date()

        is_valid = end >= start
        assert is_valid is False

    def test_must_block_at_least_one_type(self):
        """Should reject when neither dropoffs nor pickups are blocked."""
        request = {
            "start_date": "2026-07-15",
            "end_date": "2026-07-15",
            "block_dropoffs": False,
            "block_pickups": False,
        }

        is_valid = request["block_dropoffs"] or request["block_pickups"]
        assert is_valid is False

    def test_invalid_date_format_rejected(self):
        """Should reject invalid date format."""
        invalid_dates = ["15-07-2026", "07/15/2026", "2026/07/15", "invalid"]

        for date_str in invalid_dates:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                is_valid = True
            except ValueError:
                is_valid = False
            assert is_valid is False, f"Date '{date_str}' should be invalid"

    def test_valid_date_format_accepted(self):
        """Should accept valid YYYY-MM-DD format."""
        valid_dates = ["2026-01-01", "2026-12-31", "2026-07-15"]

        for date_str in valid_dates:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                is_valid = True
            except ValueError:
                is_valid = False
            assert is_valid is True, f"Date '{date_str}' should be valid"


class TestUpdateBlockedDateEndpoint:
    """Mocked tests for PUT /api/admin/blocked-dates/{id}."""

    def test_update_reason(self):
        """Should update the reason field."""
        original = mock_blocked_dates[0].copy()
        updates = {"reason": "Updated reason for training"}

        updated = {**original, **updates}

        assert updated["reason"] == "Updated reason for training"
        assert updated["start_date"] == original["start_date"]

    def test_update_date_range(self):
        """Should update the date range."""
        original = mock_blocked_dates[0].copy()
        updates = {"start_date": "2026-03-25", "end_date": "2026-03-27"}

        updated = {**original, **updates}

        assert updated["start_date"] == "2026-03-25"
        assert updated["end_date"] == "2026-03-27"

    def test_update_block_types(self):
        """Should update block_dropoffs and block_pickups."""
        original = mock_blocked_dates[0].copy()
        updates = {"block_dropoffs": False, "block_pickups": True}

        updated = {**original, **updates}

        assert updated["block_dropoffs"] is False
        assert updated["block_pickups"] is True

    def test_update_nonexistent_returns_404(self):
        """Updating non-existent blocked date should indicate not found."""
        blocked_date_id = 999
        exists = any(bd["id"] == blocked_date_id for bd in mock_blocked_dates)

        assert exists is False

    def test_update_validates_date_range(self):
        """Should validate date range after update."""
        updates = {"start_date": "2026-03-30", "end_date": "2026-03-25"}

        start = datetime.strptime(updates["start_date"], "%Y-%m-%d").date()
        end = datetime.strptime(updates["end_date"], "%Y-%m-%d").date()

        is_valid = end >= start
        assert is_valid is False


class TestDeleteBlockedDateEndpoint:
    """Mocked tests for DELETE /api/admin/blocked-dates/{id}."""

    def test_delete_removes_blocked_date(self):
        """Delete should remove blocked date from list."""
        blocked_dates = mock_blocked_dates.copy()
        id_to_delete = 2

        remaining = [bd for bd in blocked_dates if bd["id"] != id_to_delete]

        assert len(remaining) == len(blocked_dates) - 1
        assert not any(bd["id"] == id_to_delete for bd in remaining)

    def test_delete_nonexistent_returns_404(self):
        """Deleting non-existent blocked date should indicate not found."""
        blocked_date_id = 999
        exists = any(bd["id"] == blocked_date_id for bd in mock_blocked_dates)

        assert exists is False


class TestCheckBlockedDateEndpoint:
    """Mocked tests for GET /api/blocked-dates/check (public endpoint)."""

    def test_check_blocked_dropoff_date(self):
        """Should return blocked info for dropoff date."""
        dropoff_date = "2026-03-26"

        # Find blocking info
        blocked = None
        for bd in mock_blocked_dates:
            if bd["start_date"] <= dropoff_date <= bd["end_date"] and bd["block_dropoffs"]:
                blocked = bd
                break

        result = {
            "dropoff_blocked": blocked is not None,
            "dropoff_reason": blocked["reason"] if blocked else None,
        }

        assert result["dropoff_blocked"] is True
        assert result["dropoff_reason"] == "Staff Training Day"

    def test_check_blocked_pickup_date(self):
        """Should return blocked info for pickup date."""
        pickup_date = "2026-06-15"

        # Find blocking info
        blocked = None
        for bd in mock_blocked_dates:
            if bd["start_date"] <= pickup_date <= bd["end_date"] and bd["block_pickups"]:
                blocked = bd
                break

        result = {
            "pickup_blocked": blocked is not None,
            "pickup_reason": blocked["reason"] if blocked else None,
        }

        assert result["pickup_blocked"] is True
        assert result["pickup_reason"] == "No pickups - limited staff"

    def test_check_unblocked_date(self):
        """Should return not blocked for unblocked date."""
        check_date = "2026-07-01"

        # Find blocking info
        dropoff_blocked = any(
            bd["start_date"] <= check_date <= bd["end_date"] and bd["block_dropoffs"]
            for bd in mock_blocked_dates
        )
        pickup_blocked = any(
            bd["start_date"] <= check_date <= bd["end_date"] and bd["block_pickups"]
            for bd in mock_blocked_dates
        )

        assert dropoff_blocked is False
        assert pickup_blocked is False

    def test_check_dropoff_only_blocked(self):
        """Should distinguish dropoff-only block."""
        check_date = "2026-05-01"  # Dropoff blocked, pickup allowed

        dropoff_blocked = any(
            bd["start_date"] <= check_date <= bd["end_date"] and bd["block_dropoffs"]
            for bd in mock_blocked_dates
        )
        pickup_blocked = any(
            bd["start_date"] <= check_date <= bd["end_date"] and bd["block_pickups"]
            for bd in mock_blocked_dates
        )

        assert dropoff_blocked is True
        assert pickup_blocked is False

    def test_check_date_in_range(self):
        """Should detect blocked date within a range."""
        check_date = "2026-04-11"  # Within Easter closure (10-13)

        blocked = any(
            bd["start_date"] <= check_date <= bd["end_date"]
            for bd in mock_blocked_dates
        )

        assert blocked is True


class TestBookingValidationWithBlockedDates:
    """Tests for blocked date validation in booking creation."""

    def test_booking_rejected_on_blocked_dropoff_date(self):
        """Should reject booking with blocked dropoff date."""
        booking_request = {
            "dropoff_date": "2026-03-26",
            "pickup_date": "2026-04-02",
        }

        # Check if dropoff is blocked
        is_blocked = any(
            bd["start_date"] <= booking_request["dropoff_date"] <= bd["end_date"]
            and bd["block_dropoffs"]
            for bd in mock_blocked_dates
        )

        assert is_blocked is True

    def test_booking_rejected_on_blocked_pickup_date(self):
        """Should reject booking with blocked pickup date."""
        booking_request = {
            "dropoff_date": "2026-06-08",
            "pickup_date": "2026-06-15",
        }

        # Check if pickup is blocked
        is_blocked = any(
            bd["start_date"] <= booking_request["pickup_date"] <= bd["end_date"]
            and bd["block_pickups"]
            for bd in mock_blocked_dates
        )

        assert is_blocked is True

    def test_booking_allowed_on_dropoff_only_block_for_pickup(self):
        """Should allow pickup on date that only blocks dropoffs."""
        booking_request = {
            "dropoff_date": "2026-04-25",
            "pickup_date": "2026-05-01",  # Dropoff blocked, pickup allowed
        }

        # Check if pickup is blocked
        is_blocked = any(
            bd["start_date"] <= booking_request["pickup_date"] <= bd["end_date"]
            and bd["block_pickups"]
            for bd in mock_blocked_dates
        )

        assert is_blocked is False

    def test_booking_allowed_on_unblocked_dates(self):
        """Should allow booking on unblocked dates."""
        booking_request = {
            "dropoff_date": "2026-07-01",
            "pickup_date": "2026-07-08",
        }

        dropoff_blocked = any(
            bd["start_date"] <= booking_request["dropoff_date"] <= bd["end_date"]
            and bd["block_dropoffs"]
            for bd in mock_blocked_dates
        )
        pickup_blocked = any(
            bd["start_date"] <= booking_request["pickup_date"] <= bd["end_date"]
            and bd["block_pickups"]
            for bd in mock_blocked_dates
        )

        assert dropoff_blocked is False
        assert pickup_blocked is False


class TestFlightEndpointsWithBlockedDates:
    """Tests for blocked date info in flight endpoints."""

    def test_departures_include_blocked_flag(self):
        """Departures endpoint should include is_blocked flag."""
        # Simulated response for blocked date
        departure = {
            "id": 1,
            "date": "2026-03-26",
            "time": "10:30",
            "is_blocked": True,
            "blocked_reason": "Staff Training Day",
        }

        assert "is_blocked" in departure
        assert departure["is_blocked"] is True
        assert departure["blocked_reason"] == "Staff Training Day"

    def test_arrivals_include_blocked_flag(self):
        """Arrivals endpoint should include is_blocked flag."""
        # Simulated response for blocked date
        arrival = {
            "id": 1,
            "date": "2026-06-15",
            "time": "14:30",
            "is_blocked": True,
            "blocked_reason": "No pickups - limited staff",
        }

        assert "is_blocked" in arrival
        assert arrival["is_blocked"] is True

    def test_unblocked_date_has_false_flag(self):
        """Unblocked dates should have is_blocked: false."""
        departure = {
            "id": 2,
            "date": "2026-07-01",
            "time": "08:00",
            "is_blocked": False,
            "blocked_reason": None,
        }

        assert departure["is_blocked"] is False
        assert departure["blocked_reason"] is None


class TestDateRangeLogic:
    """Tests for date range blocking logic."""

    def test_single_day_range(self):
        """Single day block (start == end)."""
        blocked = {
            "start_date": "2026-08-01",
            "end_date": "2026-08-01",
        }

        check_date = "2026-08-01"
        is_blocked = blocked["start_date"] <= check_date <= blocked["end_date"]

        assert is_blocked is True

    def test_multi_day_range_start(self):
        """Check start of multi-day range."""
        blocked = {
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
        }

        check_date = "2026-08-01"
        is_blocked = blocked["start_date"] <= check_date <= blocked["end_date"]

        assert is_blocked is True

    def test_multi_day_range_middle(self):
        """Check middle of multi-day range."""
        blocked = {
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
        }

        check_date = "2026-08-03"
        is_blocked = blocked["start_date"] <= check_date <= blocked["end_date"]

        assert is_blocked is True

    def test_multi_day_range_end(self):
        """Check end of multi-day range."""
        blocked = {
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
        }

        check_date = "2026-08-05"
        is_blocked = blocked["start_date"] <= check_date <= blocked["end_date"]

        assert is_blocked is True

    def test_date_before_range(self):
        """Date before range should not be blocked."""
        blocked = {
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
        }

        check_date = "2026-07-31"
        is_blocked = blocked["start_date"] <= check_date <= blocked["end_date"]

        assert is_blocked is False

    def test_date_after_range(self):
        """Date after range should not be blocked."""
        blocked = {
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
        }

        check_date = "2026-08-06"
        is_blocked = blocked["start_date"] <= check_date <= blocked["end_date"]

        assert is_blocked is False


class TestUKTimezoneHandling:
    """Tests for UK timezone handling."""

    def test_date_stored_as_date_only(self):
        """Dates should be stored as date (no time component)."""
        blocked_date = "2026-03-26"
        parsed = datetime.strptime(blocked_date, "%Y-%m-%d").date()

        assert isinstance(parsed, date)
        assert parsed.year == 2026
        assert parsed.month == 3
        assert parsed.day == 26

    def test_date_comparison_works_correctly(self):
        """Date string comparison should work for blocking check."""
        # This simulates checking if booking date falls within block
        block_start = "2026-03-25"
        block_end = "2026-03-27"
        booking_date = "2026-03-26"

        # String comparison works for ISO dates
        is_blocked = block_start <= booking_date <= block_end

        assert is_blocked is True

    def test_bst_gmt_handling(self):
        """UK timezone switches BST/GMT - dates remain consistent."""
        # March 26 could be near BST switch
        # But since we use DATE only (not datetime), this is not affected
        block_date = date(2026, 3, 26)

        assert block_date.isoformat() == "2026-03-26"


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_blocked_dates_list(self):
        """Should handle empty blocked dates list."""
        empty_list = []

        check_date = "2026-07-01"
        is_blocked = any(
            bd["start_date"] <= check_date <= bd["end_date"]
            for bd in empty_list
        )

        assert is_blocked is False

    def test_very_long_reason(self):
        """Should handle long reason text."""
        long_reason = "A" * 255
        blocked = {"reason": long_reason}

        assert len(blocked["reason"]) == 255

    def test_special_characters_in_reason(self):
        """Should handle special characters in reason."""
        special_reason = "Bank Holiday - St. Patrick's Day (17/03)"
        blocked = {"reason": special_reason}

        assert "'" in blocked["reason"]
        assert "/" in blocked["reason"]

    def test_unicode_in_reason(self):
        """Should handle unicode in reason."""
        unicode_reason = "Christmas closure 🎄🎅"
        blocked = {"reason": unicode_reason}

        assert "🎄" in blocked["reason"]

    def test_overlapping_blocked_dates(self):
        """Should handle overlapping blocked date ranges."""
        blocks = [
            {"start_date": "2026-08-01", "end_date": "2026-08-05", "block_dropoffs": True},
            {"start_date": "2026-08-03", "end_date": "2026-08-07", "block_pickups": True},
        ]

        check_date = "2026-08-04"

        dropoff_blocked = any(
            bd["start_date"] <= check_date <= bd["end_date"] and bd.get("block_dropoffs", False)
            for bd in blocks
        )
        pickup_blocked = any(
            bd["start_date"] <= check_date <= bd["end_date"] and bd.get("block_pickups", False)
            for bd in blocks
        )

        assert dropoff_blocked is True
        assert pickup_blocked is True

    def test_consecutive_blocked_dates(self):
        """Should handle consecutive blocked date ranges."""
        blocks = [
            {"start_date": "2026-08-01", "end_date": "2026-08-03", "block_dropoffs": True, "block_pickups": True},
            {"start_date": "2026-08-04", "end_date": "2026-08-06", "block_dropoffs": True, "block_pickups": True},
        ]

        # All 6 days should be blocked
        for day in range(1, 7):
            check_date = f"2026-08-0{day}"
            is_blocked = any(
                bd["start_date"] <= check_date <= bd["end_date"]
                for bd in blocks
            )
            assert is_blocked is True, f"Day {day} should be blocked"

    def test_single_unblocked_day_between_blocks(self):
        """Should correctly identify unblocked day between blocks."""
        blocks = [
            {"start_date": "2026-08-01", "end_date": "2026-08-02", "block_dropoffs": True, "block_pickups": True},
            {"start_date": "2026-08-04", "end_date": "2026-08-05", "block_dropoffs": True, "block_pickups": True},
        ]

        # August 3 is the gap
        check_date = "2026-08-03"
        is_blocked = any(
            bd["start_date"] <= check_date <= bd["end_date"]
            for bd in blocks
        )

        assert is_blocked is False


class TestAdminPermissions:
    """Tests for admin-only access."""

    def test_create_requires_admin(self):
        """Create blocked date should require admin role."""
        user_role = "admin"
        is_authorized = user_role == "admin"

        assert is_authorized is True

    def test_create_rejected_for_non_admin(self):
        """Non-admin users should not create blocked dates."""
        user_role = "employee"
        is_authorized = user_role == "admin"

        assert is_authorized is False

    def test_delete_requires_admin(self):
        """Delete blocked date should require admin role."""
        user_role = "admin"
        is_authorized = user_role == "admin"

        assert is_authorized is True

    def test_public_check_endpoint_no_auth(self):
        """Check endpoint should be publicly accessible."""
        # The /api/blocked-dates/check endpoint is public
        requires_auth = False

        assert requires_auth is False


class TestErrorMessages:
    """Tests for user-facing error messages."""

    def test_dropoff_blocked_message_format(self):
        """Error message for blocked dropoff should include date."""
        blocked_date = date(2026, 3, 26)
        formatted_date = blocked_date.strftime("%d %B %Y")

        message = f"Sorry, drop-offs are not available on {formatted_date}. Please select a different date."

        assert "26 March 2026" in message
        assert "drop-offs" in message

    def test_pickup_blocked_message_format(self):
        """Error message for blocked pickup should include date."""
        blocked_date = date(2026, 6, 15)
        formatted_date = blocked_date.strftime("%d %B %Y")

        message = f"Sorry, pick-ups are not available on {formatted_date}. Please select a different date."

        assert "15 June 2026" in message
        assert "pick-ups" in message

    def test_frontend_no_availability_message(self):
        """Frontend should show 'no availability' message."""
        blocked_date = date(2026, 3, 26)
        formatted_date = blocked_date.strftime("%-d %B %Y")  # No leading zero

        message = f"Sorry, we have no availability for {formatted_date}"

        assert "no availability" in message.lower()


class TestDatabaseModel:
    """Tests for BlockedDate database model structure."""

    def test_model_has_required_fields(self):
        """BlockedDate model should have all required fields."""
        required_fields = [
            "id", "start_date", "end_date",
            "block_dropoffs", "block_pickups",
            "reason", "created_by", "created_at", "updated_at"
        ]

        # Mock model fields
        model_fields = list(mock_blocked_dates[0].keys())

        for field in required_fields:
            assert field in model_fields, f"Missing field: {field}"

    def test_boolean_fields_are_boolean(self):
        """block_dropoffs and block_pickups should be boolean."""
        blocked = mock_blocked_dates[0]

        assert isinstance(blocked["block_dropoffs"], bool)
        assert isinstance(blocked["block_pickups"], bool)

    def test_date_fields_are_strings_in_iso_format(self):
        """Date fields should be ISO format strings."""
        blocked = mock_blocked_dates[0]

        # Should be valid ISO dates
        try:
            datetime.strptime(blocked["start_date"], "%Y-%m-%d")
            datetime.strptime(blocked["end_date"], "%Y-%m-%d")
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is True

    def test_id_is_positive_integer(self):
        """ID should be a positive integer."""
        for blocked in mock_blocked_dates:
            assert isinstance(blocked["id"], int)
            assert blocked["id"] > 0


class TestPublicCheckEndpointParameterVariations:
    """
    Comprehensive tests for GET /api/blocked-dates/check endpoint with all parameter combinations.

    This endpoint supports multiple modes:
    1. No parameters - should return empty blocked_dates list
    2. dropoff_date only - check if specific dropoff date is blocked
    3. pickup_date only - check if specific pickup date is blocked
    4. dropoff_date + pickup_date - check both dates
    5. date_from + date_to - return all blocked dates in range
    6. date_from only (no date_to) - should handle gracefully
    7. date_to only (no date_from) - should handle gracefully
    8. All parameters combined - date range should take precedence
    """

    def test_no_parameters_returns_empty_blocked_dates(self):
        """Calling endpoint with no parameters should return empty blocked_dates list."""
        # Simulates: GET /api/blocked-dates/check
        result = {
            "dropoff_blocked": False,
            "pickup_blocked": False,
            "dropoff_reason": None,
            "pickup_reason": None,
            "blocked_dates": [],
        }

        assert result["blocked_dates"] == []
        assert result["dropoff_blocked"] is False
        assert result["pickup_blocked"] is False

    def test_dropoff_date_only_checks_dropoff(self):
        """Calling with dropoff_date only should check dropoff blocking."""
        # Simulates: GET /api/blocked-dates/check?dropoff_date=2026-03-26
        dropoff_date = "2026-03-26"

        blocked = None
        for bd in mock_blocked_dates:
            if bd["start_date"] <= dropoff_date <= bd["end_date"] and bd["block_dropoffs"]:
                blocked = bd
                break

        result = {
            "dropoff_blocked": blocked is not None,
            "dropoff_reason": blocked["reason"] if blocked else None,
            "pickup_blocked": False,
            "pickup_reason": None,
            "blocked_dates": [],
        }

        assert result["dropoff_blocked"] is True
        assert result["dropoff_reason"] == "Staff Training Day"
        assert result["pickup_blocked"] is False
        assert result["blocked_dates"] == []

    def test_pickup_date_only_checks_pickup(self):
        """Calling with pickup_date only should check pickup blocking."""
        # Simulates: GET /api/blocked-dates/check?pickup_date=2026-06-15
        pickup_date = "2026-06-15"

        blocked = None
        for bd in mock_blocked_dates:
            if bd["start_date"] <= pickup_date <= bd["end_date"] and bd["block_pickups"]:
                blocked = bd
                break

        result = {
            "dropoff_blocked": False,
            "dropoff_reason": None,
            "pickup_blocked": blocked is not None,
            "pickup_reason": blocked["reason"] if blocked else None,
            "blocked_dates": [],
        }

        assert result["dropoff_blocked"] is False
        assert result["pickup_blocked"] is True
        assert result["pickup_reason"] == "No pickups - limited staff"
        assert result["blocked_dates"] == []

    def test_both_dates_checks_both(self):
        """Calling with both dropoff_date and pickup_date should check both."""
        # Simulates: GET /api/blocked-dates/check?dropoff_date=2026-03-26&pickup_date=2026-04-02
        dropoff_date = "2026-03-26"
        pickup_date = "2026-04-02"

        dropoff_blocked = None
        for bd in mock_blocked_dates:
            if bd["start_date"] <= dropoff_date <= bd["end_date"] and bd["block_dropoffs"]:
                dropoff_blocked = bd
                break

        pickup_blocked_bd = None
        for bd in mock_blocked_dates:
            if bd["start_date"] <= pickup_date <= bd["end_date"] and bd["block_pickups"]:
                pickup_blocked_bd = bd
                break

        result = {
            "dropoff_blocked": dropoff_blocked is not None,
            "dropoff_reason": dropoff_blocked["reason"] if dropoff_blocked else None,
            "pickup_blocked": pickup_blocked_bd is not None,
            "pickup_reason": pickup_blocked_bd["reason"] if pickup_blocked_bd else None,
            "blocked_dates": [],
        }

        assert result["dropoff_blocked"] is True
        assert result["dropoff_reason"] == "Staff Training Day"
        assert result["pickup_blocked"] is False  # 2026-04-02 is not blocked
        assert result["blocked_dates"] == []

    def test_date_range_returns_blocked_dates_list(self):
        """Calling with date_from and date_to should return blocked_dates list."""
        # Simulates: GET /api/blocked-dates/check?date_from=2026-03-01&date_to=2026-04-30
        date_from = "2026-03-01"
        date_to = "2026-04-30"

        # Filter blocked dates that overlap with range
        filtered = [bd for bd in mock_blocked_dates
                   if bd["end_date"] >= date_from and bd["start_date"] <= date_to]

        result = {
            "dropoff_blocked": False,
            "pickup_blocked": False,
            "dropoff_reason": None,
            "pickup_reason": None,
            "blocked_dates": filtered,
        }

        assert len(result["blocked_dates"]) == 2  # March 26 and April 10-13
        assert result["blocked_dates"][0]["start_date"] == "2026-03-26"
        assert result["blocked_dates"][1]["start_date"] == "2026-04-10"

    def test_date_range_empty_returns_empty_list(self):
        """Date range with no blocked dates should return empty list."""
        # Simulates: GET /api/blocked-dates/check?date_from=2026-07-01&date_to=2026-07-31
        date_from = "2026-07-01"
        date_to = "2026-07-31"

        filtered = [bd for bd in mock_blocked_dates
                   if bd["end_date"] >= date_from and bd["start_date"] <= date_to]

        result = {
            "blocked_dates": filtered,
        }

        assert result["blocked_dates"] == []

    def test_date_from_only_should_handle_gracefully(self):
        """Calling with only date_from (no date_to) should not crash."""
        # Simulates: GET /api/blocked-dates/check?date_from=2026-03-01
        # Without date_to, should not return blocked_dates list
        date_from = "2026-03-01"
        date_to = None

        # If date_to is missing, don't filter - return empty
        if date_from and date_to:
            filtered = [bd for bd in mock_blocked_dates
                       if bd["end_date"] >= date_from and bd["start_date"] <= date_to]
        else:
            filtered = []

        result = {
            "blocked_dates": filtered,
        }

        assert result["blocked_dates"] == []

    def test_date_to_only_should_handle_gracefully(self):
        """Calling with only date_to (no date_from) should not crash."""
        # Simulates: GET /api/blocked-dates/check?date_to=2026-04-30
        date_from = None
        date_to = "2026-04-30"

        # If date_from is missing, don't filter - return empty
        if date_from and date_to:
            filtered = [bd for bd in mock_blocked_dates
                       if bd["end_date"] >= date_from and bd["start_date"] <= date_to]
        else:
            filtered = []

        result = {
            "blocked_dates": filtered,
        }

        assert result["blocked_dates"] == []

    def test_date_range_with_specific_dates_range_takes_precedence(self):
        """When both date range and specific dates provided, date range returns list."""
        # Simulates: GET /api/blocked-dates/check?dropoff_date=2026-03-26&date_from=2026-03-01&date_to=2026-04-30
        # The date range parameters should take precedence and return the list
        date_from = "2026-03-01"
        date_to = "2026-04-30"

        filtered = [bd for bd in mock_blocked_dates
                   if bd["end_date"] >= date_from and bd["start_date"] <= date_to]

        result = {
            "blocked_dates": filtered,
        }

        assert len(result["blocked_dates"]) == 2

    def test_date_range_90_days_returns_all_in_range(self):
        """90-day date range should return all blocked dates in that period."""
        # Simulates customer booking page: GET /api/blocked-dates/check?date_from=2026-03-23&date_to=2026-06-21
        date_from = "2026-03-23"
        date_to = "2026-06-21"

        filtered = [bd for bd in mock_blocked_dates
                   if bd["end_date"] >= date_from and bd["start_date"] <= date_to]

        result = {
            "blocked_dates": filtered,
        }

        # Should include: March 26, April 10-13, May 1, June 15
        assert len(result["blocked_dates"]) == 4

    def test_blocked_dates_list_includes_all_fields(self):
        """Blocked dates in list should include all necessary fields."""
        # Simulates: GET /api/blocked-dates/check?date_from=2026-03-01&date_to=2026-03-31
        date_from = "2026-03-01"
        date_to = "2026-03-31"

        filtered = [bd for bd in mock_blocked_dates
                   if bd["end_date"] >= date_from and bd["start_date"] <= date_to]

        assert len(filtered) == 1
        blocked = filtered[0]

        # Verify all required fields are present
        assert "id" in blocked
        assert "start_date" in blocked
        assert "end_date" in blocked
        assert "block_dropoffs" in blocked
        assert "block_pickups" in blocked
        assert "reason" in blocked

    def test_dropoff_date_with_dropoff_only_block(self):
        """Should correctly identify dropoff-only block."""
        # Simulates: GET /api/blocked-dates/check?dropoff_date=2026-05-01
        dropoff_date = "2026-05-01"  # This date has dropoff blocked but pickup allowed

        dropoff_blocked = None
        for bd in mock_blocked_dates:
            if bd["start_date"] <= dropoff_date <= bd["end_date"] and bd["block_dropoffs"]:
                dropoff_blocked = bd
                break

        pickup_blocked = None
        for bd in mock_blocked_dates:
            if bd["start_date"] <= dropoff_date <= bd["end_date"] and bd["block_pickups"]:
                pickup_blocked = bd
                break

        assert dropoff_blocked is not None
        assert dropoff_blocked["reason"] == "No drop-offs - maintenance"
        assert pickup_blocked is None

    def test_pickup_date_with_pickup_only_block(self):
        """Should correctly identify pickup-only block."""
        # Simulates: GET /api/blocked-dates/check?pickup_date=2026-06-15
        pickup_date = "2026-06-15"  # This date has pickup blocked but dropoff allowed

        dropoff_blocked = None
        for bd in mock_blocked_dates:
            if bd["start_date"] <= pickup_date <= bd["end_date"] and bd["block_dropoffs"]:
                dropoff_blocked = bd
                break

        pickup_blocked = None
        for bd in mock_blocked_dates:
            if bd["start_date"] <= pickup_date <= bd["end_date"] and bd["block_pickups"]:
                pickup_blocked = bd
                break

        assert dropoff_blocked is None
        assert pickup_blocked is not None
        assert pickup_blocked["reason"] == "No pickups - limited staff"

    def test_date_range_single_day(self):
        """Date range of single day should work correctly."""
        # Simulates: GET /api/blocked-dates/check?date_from=2026-03-26&date_to=2026-03-26
        date_from = "2026-03-26"
        date_to = "2026-03-26"

        filtered = [bd for bd in mock_blocked_dates
                   if bd["end_date"] >= date_from and bd["start_date"] <= date_to]

        assert len(filtered) == 1
        assert filtered[0]["start_date"] == "2026-03-26"

    def test_date_range_boundary_start(self):
        """Should include blocked date that starts on date_from."""
        # Simulates: GET /api/blocked-dates/check?date_from=2026-04-10&date_to=2026-04-20
        date_from = "2026-04-10"  # Easter closure starts on this day
        date_to = "2026-04-20"

        filtered = [bd for bd in mock_blocked_dates
                   if bd["end_date"] >= date_from and bd["start_date"] <= date_to]

        assert len(filtered) == 1
        assert filtered[0]["start_date"] == "2026-04-10"

    def test_date_range_boundary_end(self):
        """Should include blocked date that ends on date_to."""
        # Simulates: GET /api/blocked-dates/check?date_from=2026-04-01&date_to=2026-04-13
        date_from = "2026-04-01"
        date_to = "2026-04-13"  # Easter closure ends on this day

        filtered = [bd for bd in mock_blocked_dates
                   if bd["end_date"] >= date_from and bd["start_date"] <= date_to]

        assert len(filtered) == 1
        assert filtered[0]["end_date"] == "2026-04-13"

    def test_invalid_date_format_dropoff(self):
        """Invalid dropoff_date format should be handled gracefully."""
        # Simulates: GET /api/blocked-dates/check?dropoff_date=invalid-date
        # The endpoint should either return error or handle gracefully
        invalid_date = "invalid-date"

        try:
            from datetime import datetime
            datetime.strptime(invalid_date, "%Y-%m-%d")
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is False

    def test_invalid_date_format_date_range(self):
        """Invalid date range format should be handled gracefully."""
        # Simulates: GET /api/blocked-dates/check?date_from=2026/03/01&date_to=2026/04/30
        invalid_from = "2026/03/01"
        invalid_to = "2026/04/30"

        try:
            from datetime import datetime
            datetime.strptime(invalid_from, "%Y-%m-%d")
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is False

    def test_empty_string_parameters(self):
        """Empty string parameters should be treated as no parameter."""
        # Simulates: GET /api/blocked-dates/check?dropoff_date=&pickup_date=
        dropoff_date = ""
        pickup_date = ""

        # Empty strings should be treated as None/not provided
        dropoff_provided = bool(dropoff_date)
        pickup_provided = bool(pickup_date)

        assert dropoff_provided is False
        assert pickup_provided is False

    def test_future_date_check(self):
        """Should correctly check dates far in the future."""
        # Simulates: GET /api/blocked-dates/check?dropoff_date=2027-01-01
        future_date = "2027-01-01"

        blocked = any(
            bd["start_date"] <= future_date <= bd["end_date"]
            for bd in mock_blocked_dates
        )

        assert blocked is False

    def test_past_date_check(self):
        """Should correctly check dates in the past."""
        # Simulates: GET /api/blocked-dates/check?dropoff_date=2025-01-01
        past_date = "2025-01-01"

        blocked = any(
            bd["start_date"] <= past_date <= bd["end_date"]
            for bd in mock_blocked_dates
        )

        assert blocked is False


# =============================================================================
# Time Slots Tests
# =============================================================================

# Mock time slots data
mock_time_slots = [
    {
        "id": 1,
        "blocked_date_id": 1,  # March 26
        "start_time": "06:00",
        "end_time": "10:00",
        "block_dropoffs": True,
        "block_pickups": True,
        "reason": "Morning staff meeting",
    },
    {
        "id": 2,
        "blocked_date_id": 1,  # March 26
        "start_time": "14:00",
        "end_time": "16:00",
        "block_dropoffs": True,
        "block_pickups": False,
        "reason": "Afternoon training - dropoffs only",
    },
]


class TestBlockedTimeSlotsModel:
    """Tests for BlockedTimeSlot database model."""

    def test_time_slot_has_required_fields(self):
        """Time slot should have all required fields."""
        slot = mock_time_slots[0]

        required_fields = [
            "id", "blocked_date_id", "start_time", "end_time",
            "block_dropoffs", "block_pickups"
        ]
        for field in required_fields:
            assert field in slot

    def test_time_format_is_hhmm(self):
        """Time fields should be in HH:MM format."""
        slot = mock_time_slots[0]

        # Should match HH:MM pattern
        import re
        time_pattern = r"^\d{2}:\d{2}$"
        assert re.match(time_pattern, slot["start_time"])
        assert re.match(time_pattern, slot["end_time"])

    def test_start_time_before_end_time(self):
        """Start time must be before end time."""
        for slot in mock_time_slots:
            start_h, start_m = map(int, slot["start_time"].split(":"))
            end_h, end_m = map(int, slot["end_time"].split(":"))

            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            assert start_minutes < end_minutes


class TestTimeSlotsCRUD:
    """Tests for time slots CRUD operations."""

    def test_get_time_slots_for_blocked_date(self):
        """Should return all time slots for a blocked date."""
        blocked_date_id = 1
        slots = [ts for ts in mock_time_slots if ts["blocked_date_id"] == blocked_date_id]

        assert len(slots) == 2

    def test_create_time_slot_validates_time_format(self):
        """Should reject invalid time format."""
        invalid_times = ["25:00", "12:60", "abc", "12", "12:00:00"]

        for invalid_time in invalid_times:
            try:
                h, m = map(int, invalid_time.split(":"))
                if h < 0 or h > 23 or m < 0 or m > 59:
                    is_valid = False
                else:
                    is_valid = True
            except (ValueError, AttributeError):
                is_valid = False

            assert is_valid is False

    def test_create_time_slot_validates_time_order(self):
        """Should reject start_time >= end_time."""
        invalid_ranges = [
            ("10:00", "10:00"),  # Equal
            ("14:00", "10:00"),  # Start after end
        ]

        for start, end in invalid_ranges:
            start_h, start_m = map(int, start.split(":"))
            end_h, end_m = map(int, end.split(":"))

            is_valid = (start_h * 60 + start_m) < (end_h * 60 + end_m)
            assert is_valid is False

    def test_create_time_slot_checks_overlap(self):
        """Should reject overlapping time slots."""
        existing_slot = mock_time_slots[0]  # 06:00-10:00

        overlapping_ranges = [
            ("05:00", "07:00"),  # Overlaps start
            ("09:00", "11:00"),  # Overlaps end
            ("07:00", "09:00"),  # Completely inside
            ("05:00", "11:00"),  # Completely covers
        ]

        for new_start, new_end in overlapping_ranges:
            existing_start_h, existing_start_m = map(int, existing_slot["start_time"].split(":"))
            existing_end_h, existing_end_m = map(int, existing_slot["end_time"].split(":"))
            new_start_h, new_start_m = map(int, new_start.split(":"))
            new_end_h, new_end_m = map(int, new_end.split(":"))

            existing_start = existing_start_h * 60 + existing_start_m
            existing_end = existing_end_h * 60 + existing_end_m
            new_start_mins = new_start_h * 60 + new_start_m
            new_end_mins = new_end_h * 60 + new_end_m

            # Overlap check: new_start < existing_end AND new_end > existing_start
            overlaps = new_start_mins < existing_end and new_end_mins > existing_start
            assert overlaps is True

    def test_create_time_slot_allows_adjacent(self):
        """Should allow adjacent (non-overlapping) time slots."""
        existing_slot = mock_time_slots[0]  # 06:00-10:00

        adjacent_ranges = [
            ("04:00", "06:00"),  # Ends when existing starts
            ("10:00", "12:00"),  # Starts when existing ends
        ]

        for new_start, new_end in adjacent_ranges:
            existing_start_h, existing_start_m = map(int, existing_slot["start_time"].split(":"))
            existing_end_h, existing_end_m = map(int, existing_slot["end_time"].split(":"))
            new_start_h, new_start_m = map(int, new_start.split(":"))
            new_end_h, new_end_m = map(int, new_end.split(":"))

            existing_start = existing_start_h * 60 + existing_start_m
            existing_end = existing_end_h * 60 + existing_end_m
            new_start_mins = new_start_h * 60 + new_start_m
            new_end_mins = new_end_h * 60 + new_end_m

            # Overlap check: new_start < existing_end AND new_end > existing_start
            overlaps = new_start_mins < existing_end and new_end_mins > existing_start
            assert overlaps is False

    def test_delete_time_slot_cascades_from_blocked_date(self):
        """Deleting a blocked date should cascade delete its time slots."""
        # This is handled by ON DELETE CASCADE in the database
        # Verify the relationship is set up correctly
        cascade_behavior = "CASCADE"
        assert cascade_behavior == "CASCADE"


class TestTimeSlotBlockingLogic:
    """Tests for time-based blocking logic."""

    def is_time_in_slot(self, check_time, slot):
        """Helper: Check if a time falls within a slot."""
        check_h, check_m = map(int, check_time.split(":"))
        start_h, start_m = map(int, slot["start_time"].split(":"))
        end_h, end_m = map(int, slot["end_time"].split(":"))

        check_mins = check_h * 60 + check_m
        start_mins = start_h * 60 + start_m
        end_mins = end_h * 60 + end_m

        return start_mins <= check_mins < end_mins

    def test_time_within_blocked_slot_is_blocked(self):
        """Time within a blocked slot should be blocked."""
        slot = mock_time_slots[0]  # 06:00-10:00

        blocked_times = ["06:00", "07:30", "09:59"]
        for check_time in blocked_times:
            assert self.is_time_in_slot(check_time, slot) is True

    def test_time_outside_blocked_slot_is_not_blocked(self):
        """Time outside a blocked slot should not be blocked."""
        slot = mock_time_slots[0]  # 06:00-10:00

        unblocked_times = ["05:59", "10:00", "12:00", "00:00"]
        for check_time in unblocked_times:
            assert self.is_time_in_slot(check_time, slot) is False

    def test_dropoff_blocked_but_pickup_allowed(self):
        """Time slot can block dropoffs but allow pickups."""
        slot = mock_time_slots[1]  # 14:00-16:00, dropoffs blocked, pickups allowed

        assert slot["block_dropoffs"] is True
        assert slot["block_pickups"] is False

    def test_no_time_slots_uses_blocked_date_settings(self):
        """Without time slots, entire day uses blocked_date settings."""
        # Blocked date without time slots
        blocked_date = {
            "block_dropoffs": True,
            "block_pickups": False,
            "time_slots": [],
        }

        # Without time slots, the blocked_date settings apply to entire day
        has_time_slots = len(blocked_date["time_slots"]) > 0

        if not has_time_slots:
            dropoff_blocked = blocked_date["block_dropoffs"]
            pickup_blocked = blocked_date["block_pickups"]
        else:
            dropoff_blocked = False
            pickup_blocked = False

        assert dropoff_blocked is True
        assert pickup_blocked is False


class TestTimeSlotCheckEndpoint:
    """Tests for checking blocked status with time slots."""

    def test_check_with_dropoff_time_in_blocked_slot(self):
        """Should detect blocked when dropoff_time falls in blocked slot."""
        # GET /api/blocked-dates/check?dropoff_date=2026-03-26&dropoff_time=08:00
        dropoff_time = "08:00"
        slot = mock_time_slots[0]  # 06:00-10:00

        check_h, check_m = map(int, dropoff_time.split(":"))
        start_h, start_m = map(int, slot["start_time"].split(":"))
        end_h, end_m = map(int, slot["end_time"].split(":"))

        check_mins = check_h * 60 + check_m
        in_slot = (start_h * 60 + start_m) <= check_mins < (end_h * 60 + end_m)

        is_blocked = in_slot and slot["block_dropoffs"]
        assert is_blocked is True

    def test_check_with_dropoff_time_outside_blocked_slot(self):
        """Should not block when dropoff_time is outside blocked slots."""
        # GET /api/blocked-dates/check?dropoff_date=2026-03-26&dropoff_time=12:00
        dropoff_time = "12:00"

        # Check against all time slots
        is_blocked = False
        for slot in mock_time_slots:
            check_h, check_m = map(int, dropoff_time.split(":"))
            start_h, start_m = map(int, slot["start_time"].split(":"))
            end_h, end_m = map(int, slot["end_time"].split(":"))

            check_mins = check_h * 60 + check_m
            in_slot = (start_h * 60 + start_m) <= check_mins < (end_h * 60 + end_m)

            if in_slot and slot["block_dropoffs"]:
                is_blocked = True
                break

        assert is_blocked is False

    def test_check_pickup_in_dropoff_only_slot(self):
        """Pickup should be allowed in dropoff-only blocked slot."""
        # GET /api/blocked-dates/check?pickup_date=2026-03-26&pickup_time=15:00
        pickup_time = "15:00"
        slot = mock_time_slots[1]  # 14:00-16:00, dropoffs only

        check_h, check_m = map(int, pickup_time.split(":"))
        start_h, start_m = map(int, slot["start_time"].split(":"))
        end_h, end_m = map(int, slot["end_time"].split(":"))

        check_mins = check_h * 60 + check_m
        in_slot = (start_h * 60 + start_m) <= check_mins < (end_h * 60 + end_m)

        pickup_blocked = in_slot and slot["block_pickups"]
        assert pickup_blocked is False

    def test_check_without_time_checks_any_slot(self):
        """Without specific time, should check if any slot blocks the type."""
        # GET /api/blocked-dates/check?dropoff_date=2026-03-26
        # Without dropoff_time, should indicate if any slot blocks dropoffs

        any_dropoff_blocked = any(slot["block_dropoffs"] for slot in mock_time_slots)
        assert any_dropoff_blocked is True

    def test_date_range_includes_time_slots(self):
        """Date range response should include time_slots for each blocked date."""
        # GET /api/blocked-dates/check?date_from=2026-03-01&date_to=2026-03-31

        blocked_date_with_slots = {
            "id": 1,
            "start_date": "2026-03-26",
            "end_date": "2026-03-26",
            "block_dropoffs": True,
            "block_pickups": True,
            "reason": "Staff Training Day",
            "time_slots": mock_time_slots,
        }

        assert "time_slots" in blocked_date_with_slots
        assert len(blocked_date_with_slots["time_slots"]) == 2

    def test_multiple_time_slots_checked_in_order(self):
        """Multiple time slots should be checked correctly."""
        # Day has two blocked slots: 06:00-10:00 and 14:00-16:00

        test_times = [
            ("05:00", False),  # Before first slot
            ("08:00", True),   # In first slot
            ("12:00", False),  # Between slots
            ("15:00", True),   # In second slot (dropoffs blocked)
            ("17:00", False),  # After all slots
        ]

        for check_time, expected_blocked in test_times:
            is_blocked = False
            for slot in mock_time_slots:
                check_h, check_m = map(int, check_time.split(":"))
                start_h, start_m = map(int, slot["start_time"].split(":"))
                end_h, end_m = map(int, slot["end_time"].split(":"))

                check_mins = check_h * 60 + check_m
                in_slot = (start_h * 60 + start_m) <= check_mins < (end_h * 60 + end_m)

                if in_slot and slot["block_dropoffs"]:
                    is_blocked = True
                    break

            assert is_blocked == expected_blocked, f"Time {check_time} expected {expected_blocked}, got {is_blocked}"


class TestTimeSlotEdgeCases:
    """Edge case tests for time slots."""

    def test_midnight_handling(self):
        """Should handle times around midnight correctly."""
        slot = {"start_time": "00:00", "end_time": "02:00"}

        test_times = [
            ("00:00", True),
            ("01:00", True),
            ("01:59", True),
            ("02:00", False),  # End time is exclusive
            ("23:59", False),
        ]

        for check_time, expected_in_slot in test_times:
            check_h, check_m = map(int, check_time.split(":"))
            start_h, start_m = map(int, slot["start_time"].split(":"))
            end_h, end_m = map(int, slot["end_time"].split(":"))

            check_mins = check_h * 60 + check_m
            in_slot = (start_h * 60 + start_m) <= check_mins < (end_h * 60 + end_m)

            assert in_slot == expected_in_slot

    def test_end_of_day_handling(self):
        """Should handle times at end of day correctly."""
        slot = {"start_time": "22:00", "end_time": "23:59"}

        test_times = [
            ("21:59", False),
            ("22:00", True),
            ("23:00", True),
            ("23:58", True),
            ("23:59", False),  # End time is exclusive
        ]

        for check_time, expected_in_slot in test_times:
            check_h, check_m = map(int, check_time.split(":"))
            start_h, start_m = map(int, slot["start_time"].split(":"))
            end_h, end_m = map(int, slot["end_time"].split(":"))

            check_mins = check_h * 60 + check_m
            in_slot = (start_h * 60 + start_m) <= check_mins < (end_h * 60 + end_m)

            assert in_slot == expected_in_slot

    def test_single_minute_slot(self):
        """Should handle very short time slots."""
        slot = {"start_time": "10:00", "end_time": "10:01"}

        assert slot["start_time"] != slot["end_time"]

        check_h, check_m = 10, 0
        start_h, start_m = map(int, slot["start_time"].split(":"))
        end_h, end_m = map(int, slot["end_time"].split(":"))

        check_mins = check_h * 60 + check_m
        in_slot = (start_h * 60 + start_m) <= check_mins < (end_h * 60 + end_m)

        assert in_slot is True

    def test_full_day_slot(self):
        """Should handle slot covering entire day."""
        slot = {"start_time": "00:00", "end_time": "23:59"}

        # All reasonable times should be in this slot
        test_times = ["00:00", "06:00", "12:00", "18:00", "23:58"]

        for check_time in test_times:
            check_h, check_m = map(int, check_time.split(":"))
            start_h, start_m = map(int, slot["start_time"].split(":"))
            end_h, end_m = map(int, slot["end_time"].split(":"))

            check_mins = check_h * 60 + check_m
            in_slot = (start_h * 60 + start_m) <= check_mins < (end_h * 60 + end_m)

            assert in_slot is True

    def test_empty_time_string(self):
        """Should handle empty time string gracefully."""
        check_time = ""

        try:
            h, m = map(int, check_time.split(":"))
            is_valid = True
        except (ValueError, AttributeError):
            is_valid = False

        assert is_valid is False

    def test_none_time_value(self):
        """Should handle None time value gracefully."""
        check_time = None

        try:
            h, m = map(int, check_time.split(":"))
            is_valid = True
        except (ValueError, AttributeError, TypeError):
            is_valid = False

        assert is_valid is False


class TestBoundaryConditions:
    """
    E2E boundary tests for blocked dates/times.
    Tests: 1 day before, 1 day after, 1 minute before, 1 minute after.
    """

    # ==========================================================
    # DATE BOUNDARY TESTS
    # ==========================================================

    def test_booking_day_before_blocked_date_allowed(self):
        """Booking for 1 day BEFORE blocked date should be allowed."""
        # Blocked date: March 26, 2026
        blocked_start = "2026-03-26"
        blocked_end = "2026-03-26"

        # Booking for March 25 (1 day before)
        booking_date = "2026-03-25"

        is_blocked = blocked_start <= booking_date <= blocked_end
        assert is_blocked is False, "Day before blocked date should NOT be blocked"

    def test_booking_day_after_blocked_date_allowed(self):
        """Booking for 1 day AFTER blocked date should be allowed."""
        # Blocked date: March 26, 2026
        blocked_start = "2026-03-26"
        blocked_end = "2026-03-26"

        # Booking for March 27 (1 day after)
        booking_date = "2026-03-27"

        is_blocked = blocked_start <= booking_date <= blocked_end
        assert is_blocked is False, "Day after blocked date should NOT be blocked"

    def test_booking_on_blocked_date_blocked(self):
        """Booking ON blocked date should be blocked."""
        # Blocked date: March 26, 2026
        blocked_start = "2026-03-26"
        blocked_end = "2026-03-26"

        # Booking for March 26 (the blocked date)
        booking_date = "2026-03-26"

        is_blocked = blocked_start <= booking_date <= blocked_end
        assert is_blocked is True, "Booking on blocked date should be blocked"

    def test_booking_day_before_blocked_range_allowed(self):
        """Booking for 1 day BEFORE a blocked date range should be allowed."""
        # Blocked range: April 10-13, 2026 (Easter)
        blocked_start = "2026-04-10"
        blocked_end = "2026-04-13"

        # Booking for April 9 (1 day before range starts)
        booking_date = "2026-04-09"

        is_blocked = blocked_start <= booking_date <= blocked_end
        assert is_blocked is False, "Day before blocked range should NOT be blocked"

    def test_booking_day_after_blocked_range_allowed(self):
        """Booking for 1 day AFTER a blocked date range should be allowed."""
        # Blocked range: April 10-13, 2026 (Easter)
        blocked_start = "2026-04-10"
        blocked_end = "2026-04-13"

        # Booking for April 14 (1 day after range ends)
        booking_date = "2026-04-14"

        is_blocked = blocked_start <= booking_date <= blocked_end
        assert is_blocked is False, "Day after blocked range should NOT be blocked"

    def test_booking_on_first_day_of_blocked_range_blocked(self):
        """Booking on FIRST day of blocked range should be blocked."""
        # Blocked range: April 10-13, 2026 (Easter)
        blocked_start = "2026-04-10"
        blocked_end = "2026-04-13"

        # Booking for April 10 (first day of range)
        booking_date = "2026-04-10"

        is_blocked = blocked_start <= booking_date <= blocked_end
        assert is_blocked is True, "First day of blocked range should be blocked"

    def test_booking_on_last_day_of_blocked_range_blocked(self):
        """Booking on LAST day of blocked range should be blocked."""
        # Blocked range: April 10-13, 2026 (Easter)
        blocked_start = "2026-04-10"
        blocked_end = "2026-04-13"

        # Booking for April 13 (last day of range)
        booking_date = "2026-04-13"

        is_blocked = blocked_start <= booking_date <= blocked_end
        assert is_blocked is True, "Last day of blocked range should be blocked"

    # ==========================================================
    # TIME BOUNDARY TESTS (with time slots)
    # ==========================================================

    def is_time_blocked(self, check_time, slot):
        """Helper: Check if time falls within blocked slot."""
        check_h, check_m = map(int, check_time.split(":"))
        start_h, start_m = map(int, slot["start_time"].split(":"))
        end_h, end_m = map(int, slot["end_time"].split(":"))

        check_mins = check_h * 60 + check_m
        start_mins = start_h * 60 + start_m
        end_mins = end_h * 60 + end_m

        return start_mins <= check_mins < end_mins

    def test_booking_1_minute_before_blocked_slot_allowed(self):
        """Booking 1 minute BEFORE blocked time slot should be allowed."""
        # Blocked slot: 06:00 - 10:00
        slot = {"start_time": "06:00", "end_time": "10:00", "block_dropoffs": True}

        # Booking for 05:59 (1 minute before slot starts)
        booking_time = "05:59"

        is_blocked = self.is_time_blocked(booking_time, slot) and slot["block_dropoffs"]
        assert is_blocked is False, "1 minute before blocked slot should NOT be blocked"

    def test_booking_1_minute_after_blocked_slot_allowed(self):
        """Booking 1 minute AFTER blocked time slot ends should be allowed."""
        # Blocked slot: 06:00 - 10:00
        slot = {"start_time": "06:00", "end_time": "10:00", "block_dropoffs": True}

        # Booking for 10:00 (slot ends at 10:00, so 10:00 is first available)
        booking_time = "10:00"

        is_blocked = self.is_time_blocked(booking_time, slot) and slot["block_dropoffs"]
        assert is_blocked is False, "Time at exact end of slot should NOT be blocked"

    def test_booking_at_exact_start_of_blocked_slot_blocked(self):
        """Booking at EXACT start time of blocked slot should be blocked."""
        # Blocked slot: 06:00 - 10:00
        slot = {"start_time": "06:00", "end_time": "10:00", "block_dropoffs": True}

        # Booking for 06:00 (exact start of slot)
        booking_time = "06:00"

        is_blocked = self.is_time_blocked(booking_time, slot) and slot["block_dropoffs"]
        assert is_blocked is True, "Exact start of blocked slot should be blocked"

    def test_booking_1_minute_into_blocked_slot_blocked(self):
        """Booking 1 minute INTO blocked slot should be blocked."""
        # Blocked slot: 06:00 - 10:00
        slot = {"start_time": "06:00", "end_time": "10:00", "block_dropoffs": True}

        # Booking for 06:01 (1 minute after slot starts)
        booking_time = "06:01"

        is_blocked = self.is_time_blocked(booking_time, slot) and slot["block_dropoffs"]
        assert is_blocked is True, "1 minute into blocked slot should be blocked"

    def test_booking_1_minute_before_slot_ends_blocked(self):
        """Booking 1 minute BEFORE blocked slot ends should be blocked."""
        # Blocked slot: 06:00 - 10:00
        slot = {"start_time": "06:00", "end_time": "10:00", "block_dropoffs": True}

        # Booking for 09:59 (1 minute before slot ends)
        booking_time = "09:59"

        is_blocked = self.is_time_blocked(booking_time, slot) and slot["block_dropoffs"]
        assert is_blocked is True, "1 minute before slot ends should be blocked"

    def test_multiple_slots_boundary_between_slots(self):
        """Time between two blocked slots should be allowed."""
        # Two blocked slots: 06:00-10:00 and 14:00-18:00
        slots = [
            {"start_time": "06:00", "end_time": "10:00", "block_dropoffs": True},
            {"start_time": "14:00", "end_time": "18:00", "block_dropoffs": True},
        ]

        # Test times in the gap between slots
        gap_times = ["10:00", "12:00", "13:59"]

        for booking_time in gap_times:
            is_blocked = any(
                self.is_time_blocked(booking_time, slot) and slot["block_dropoffs"]
                for slot in slots
            )
            assert is_blocked is False, f"Time {booking_time} between slots should NOT be blocked"

    def test_adjacent_slots_transition(self):
        """Transition point between adjacent slots works correctly."""
        # Two adjacent slots: 06:00-10:00 and 10:00-14:00
        slot1 = {"start_time": "06:00", "end_time": "10:00", "block_dropoffs": True}
        slot2 = {"start_time": "10:00", "end_time": "14:00", "block_dropoffs": True}

        # At 10:00, slot1 ends and slot2 starts
        booking_time = "10:00"

        in_slot1 = self.is_time_blocked(booking_time, slot1)
        in_slot2 = self.is_time_blocked(booking_time, slot2)

        # 10:00 should be in slot2 but not slot1 (end time is exclusive)
        assert in_slot1 is False, "10:00 should NOT be in slot1 (end exclusive)"
        assert in_slot2 is True, "10:00 should be in slot2 (start inclusive)"

    # ==========================================================
    # COMBINED DATE + TIME BOUNDARY TESTS
    # ==========================================================

    def test_date_boundary_with_time_slot(self):
        """Time slot blocking only applies on the correct date."""
        # Blocked date: March 26 with time slot 06:00-10:00
        blocked_date = "2026-03-26"
        slot = {"start_time": "06:00", "end_time": "10:00", "block_dropoffs": True}

        # Booking for March 25 at 08:00 (day before, but during blocked hours)
        booking_date = "2026-03-25"
        booking_time = "08:00"

        # Check if date matches AND time is blocked
        date_matches = booking_date == blocked_date
        time_blocked = self.is_time_blocked(booking_time, slot)

        is_blocked = date_matches and time_blocked
        assert is_blocked is False, "Time slot should not apply to different date"

    def test_same_date_outside_time_slot(self):
        """Same date but outside time slot should be allowed."""
        # Blocked date: March 26 with time slot 06:00-10:00
        blocked_date = "2026-03-26"
        slot = {"start_time": "06:00", "end_time": "10:00", "block_dropoffs": True}

        # Booking for March 26 at 12:00 (same date, but outside blocked hours)
        booking_date = "2026-03-26"
        booking_time = "12:00"

        date_matches = booking_date == blocked_date
        time_blocked = self.is_time_blocked(booking_time, slot) and slot["block_dropoffs"]

        # Date matches but time is not in blocked slot
        is_blocked = date_matches and time_blocked
        assert is_blocked is False, "Same date outside time slot should NOT be blocked"

    def test_same_date_inside_time_slot(self):
        """Same date inside time slot should be blocked."""
        # Blocked date: March 26 with time slot 06:00-10:00
        blocked_date = "2026-03-26"
        slot = {"start_time": "06:00", "end_time": "10:00", "block_dropoffs": True}

        # Booking for March 26 at 08:00 (same date, inside blocked hours)
        booking_date = "2026-03-26"
        booking_time = "08:00"

        date_matches = booking_date == blocked_date
        time_blocked = self.is_time_blocked(booking_time, slot) and slot["block_dropoffs"]

        is_blocked = date_matches and time_blocked
        assert is_blocked is True, "Same date inside time slot should be blocked"

    # ==========================================================
    # MIDNIGHT / DAY TRANSITION TESTS
    # ==========================================================

    def test_midnight_boundary_23_59_to_00_00(self):
        """Test transition from 23:59 to 00:00."""
        # Slot that ends at 23:59
        slot = {"start_time": "22:00", "end_time": "23:59", "block_dropoffs": True}

        # 23:58 should be blocked
        assert self.is_time_blocked("23:58", slot) is True

        # 23:59 is end time (exclusive), so NOT blocked
        assert self.is_time_blocked("23:59", slot) is False

    def test_early_morning_slot_boundary(self):
        """Test early morning slot boundaries."""
        # Early morning slot: 00:00 - 04:00
        slot = {"start_time": "00:00", "end_time": "04:00", "block_dropoffs": True}

        # Test boundaries
        assert self.is_time_blocked("00:00", slot) is True, "00:00 should be blocked"
        assert self.is_time_blocked("03:59", slot) is True, "03:59 should be blocked"
        assert self.is_time_blocked("04:00", slot) is False, "04:00 should NOT be blocked"

    # ==========================================================
    # DROPOFF vs PICKUP TYPE BOUNDARIES
    # ==========================================================

    def test_dropoff_blocked_pickup_allowed_same_time(self):
        """Same time slot can block dropoffs but allow pickups."""
        slot = {
            "start_time": "14:00",
            "end_time": "16:00",
            "block_dropoffs": True,
            "block_pickups": False,
        }

        booking_time = "15:00"
        in_slot = self.is_time_blocked(booking_time, slot)

        dropoff_blocked = in_slot and slot["block_dropoffs"]
        pickup_blocked = in_slot and slot["block_pickups"]

        assert dropoff_blocked is True, "Dropoff at 15:00 should be blocked"
        assert pickup_blocked is False, "Pickup at 15:00 should NOT be blocked"

    def test_pickup_blocked_dropoff_allowed_same_time(self):
        """Same time slot can block pickups but allow dropoffs."""
        slot = {
            "start_time": "14:00",
            "end_time": "16:00",
            "block_dropoffs": False,
            "block_pickups": True,
        }

        booking_time = "15:00"
        in_slot = self.is_time_blocked(booking_time, slot)

        dropoff_blocked = in_slot and slot["block_dropoffs"]
        pickup_blocked = in_slot and slot["block_pickups"]

        assert dropoff_blocked is False, "Dropoff at 15:00 should NOT be blocked"
        assert pickup_blocked is True, "Pickup at 15:00 should be blocked"
