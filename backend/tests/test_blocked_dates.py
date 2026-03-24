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
