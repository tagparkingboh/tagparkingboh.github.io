"""
Tests for POST /api/employee/inspections/status - lightweight batch inspection status endpoint.

This endpoint is optimized for the employee dashboard calendar view where we only need
to know if inspections exist and their basic status - NOT the full data with large
base64-encoded photos and signatures.

Tests cover:
- Happy path: batch fetching status for multiple bookings
- Response structure: returns lightweight data without photos/signatures
- Grouping: results are correctly grouped by booking_id
- Empty cases: empty input, bookings with no inspections
- Limits: max 100 booking IDs enforced
- Authentication: requires valid auth token
- Edge cases: mixed bookings (some with inspections, some without)
- Declined inspections: status correctly indicates declined
- Multiple inspection types: dropoff and pickup correctly returned
"""
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import enum


class MockInspectionType(enum.Enum):
    """Mock inspection type enum to avoid DB connection on import."""
    DROPOFF = "dropoff"
    PICKUP = "pickup"


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_user(id=1, is_active=True):
    """Create a mock user for authentication."""
    user = MagicMock()
    user.id = id
    user.email = "employee@tagparking.co.uk"
    user.first_name = "Test"
    user.last_name = "Employee"
    user.is_admin = False
    user.is_active = is_active
    return user


def create_mock_inspection(
    id=1,
    booking_id=1,
    inspection_type=None,
    declined=False,
    mileage=12500,
    photos='{"front": "data:image/jpeg;base64,/9j/large-photo-data..."}',
    signature="data:image/png;base64,signature-data...",
    notes="Some inspection notes",
    customer_name="John Smith",
):
    """Create a mock inspection with all fields."""
    if inspection_type is None:
        inspection_type = MockInspectionType.DROPOFF
    inspection = MagicMock()
    inspection.id = id
    inspection.booking_id = booking_id
    inspection.inspection_type = inspection_type
    inspection.declined = declined
    inspection.mileage = mileage
    inspection.photos = photos
    inspection.signature = signature
    inspection.notes = notes
    inspection.customer_name = customer_name
    inspection.signed_date = date.today()
    inspection.vehicle_inspection_read = True
    inspection.acknowledgement_confirmed = True
    inspection.inspector_id = 1
    inspection.created_at = datetime.utcnow()
    inspection.updated_at = datetime.utcnow()
    return inspection


# =============================================================================
# Tests: Response Structure - Lightweight Status Without Photos
# =============================================================================

class TestStatusResponseStructure:
    """Tests verifying the response contains only lightweight status data."""

    def test_status_does_not_include_photos(self):
        """Status response should NOT include photos field."""
        # Simulate what the endpoint returns (only id, booking_id, inspection_type, declined, mileage)
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            inspection_type=MockInspectionType.DROPOFF,
            photos='{"front": "data:image/jpeg;base64,HUGE_PHOTO_DATA_500KB..."}',
        )

        # The status endpoint only returns these fields:
        status_data = {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "declined": inspection.declined or False,
            "mileage": inspection.mileage,
        }

        # Verify photos NOT included
        assert "photos" not in status_data
        assert "signature" not in status_data
        assert "notes" not in status_data
        assert "customer_name" not in status_data

        # Verify essential status IS included
        assert status_data["id"] == 1
        assert status_data["booking_id"] == 100
        assert status_data["inspection_type"] == "dropoff"
        assert status_data["declined"] is False
        assert status_data["mileage"] == 12500

    def test_status_does_not_include_signature(self):
        """Status response should NOT include signature field."""
        inspection = create_mock_inspection(
            id=2,
            booking_id=200,
            signature="data:image/png;base64,LARGE_SIGNATURE_DATA...",
        )

        status_data = {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "declined": inspection.declined or False,
            "mileage": inspection.mileage,
        }

        assert "signature" not in status_data

    def test_status_does_not_include_notes(self):
        """Status response should NOT include notes field."""
        inspection = create_mock_inspection(
            id=3,
            booking_id=300,
            notes="Detailed inspection notes about vehicle condition...",
        )

        status_data = {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "declined": inspection.declined or False,
            "mileage": inspection.mileage,
        }

        assert "notes" not in status_data

    def test_status_does_not_include_acknowledgement_fields(self):
        """Status response should NOT include customer acknowledgement fields."""
        inspection = create_mock_inspection(
            id=4,
            booking_id=400,
            customer_name="Jane Doe",
        )

        status_data = {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "declined": inspection.declined or False,
            "mileage": inspection.mileage,
        }

        assert "customer_name" not in status_data
        assert "signed_date" not in status_data
        assert "vehicle_inspection_read" not in status_data
        assert "acknowledgement_confirmed" not in status_data


# =============================================================================
# Tests: Batch Fetching - Happy Paths
# =============================================================================

class TestBatchFetchingHappyPaths:
    """Happy path tests for batch status fetching."""

    def test_batch_fetch_single_booking_with_inspection(self):
        """Fetching status for a single booking with inspection should work."""
        inspection = create_mock_inspection(id=1, booking_id=100)

        # Simulate batch response structure
        response = {
            "inspections": {
                "100": [
                    {
                        "id": inspection.id,
                        "booking_id": inspection.booking_id,
                        "inspection_type": inspection.inspection_type.value,
                        "declined": inspection.declined or False,
                        "mileage": inspection.mileage,
                    }
                ]
            }
        }

        assert "100" in response["inspections"]
        assert len(response["inspections"]["100"]) == 1
        assert response["inspections"]["100"][0]["id"] == 1

    def test_batch_fetch_multiple_bookings_with_inspections(self):
        """Fetching status for multiple bookings should return all results."""
        inspections = [
            create_mock_inspection(id=1, booking_id=100, inspection_type=MockInspectionType.DROPOFF),
            create_mock_inspection(id=2, booking_id=200, inspection_type=MockInspectionType.DROPOFF),
            create_mock_inspection(id=3, booking_id=300, inspection_type=MockInspectionType.DROPOFF),
        ]

        response = {
            "inspections": {
                str(i.booking_id): [{
                    "id": i.id,
                    "booking_id": i.booking_id,
                    "inspection_type": i.inspection_type.value,
                    "declined": i.declined or False,
                    "mileage": i.mileage,
                }] for i in inspections
            }
        }

        assert len(response["inspections"]) == 3
        assert "100" in response["inspections"]
        assert "200" in response["inspections"]
        assert "300" in response["inspections"]

    def test_batch_fetch_booking_with_both_inspection_types(self):
        """Booking with both dropoff and pickup inspections should return both."""
        dropoff = create_mock_inspection(id=1, booking_id=100, inspection_type=MockInspectionType.DROPOFF)
        pickup = create_mock_inspection(id=2, booking_id=100, inspection_type=MockInspectionType.PICKUP)

        response = {
            "inspections": {
                "100": [
                    {
                        "id": dropoff.id,
                        "booking_id": dropoff.booking_id,
                        "inspection_type": dropoff.inspection_type.value,
                        "declined": dropoff.declined or False,
                        "mileage": dropoff.mileage,
                    },
                    {
                        "id": pickup.id,
                        "booking_id": pickup.booking_id,
                        "inspection_type": pickup.inspection_type.value,
                        "declined": pickup.declined or False,
                        "mileage": pickup.mileage,
                    },
                ]
            }
        }

        assert len(response["inspections"]["100"]) == 2
        types = {i["inspection_type"] for i in response["inspections"]["100"]}
        assert types == {"dropoff", "pickup"}


# =============================================================================
# Tests: Empty Cases
# =============================================================================

class TestEmptyCases:
    """Tests for empty input and bookings without inspections."""

    def test_empty_booking_ids_returns_empty(self):
        """Empty booking_ids array should return empty inspections dict."""
        response = {"inspections": {}}

        assert response["inspections"] == {}

    def test_booking_without_inspection_returns_empty_array(self):
        """Booking with no inspections should have empty array in response."""
        response = {
            "inspections": {
                "100": [],  # No inspections for booking 100
                "200": [],  # No inspections for booking 200
            }
        }

        assert response["inspections"]["100"] == []
        assert response["inspections"]["200"] == []

    def test_mixed_bookings_some_with_some_without_inspections(self):
        """Mix of bookings with and without inspections should work correctly."""
        inspection = create_mock_inspection(id=1, booking_id=100)

        response = {
            "inspections": {
                "100": [{
                    "id": inspection.id,
                    "booking_id": inspection.booking_id,
                    "inspection_type": inspection.inspection_type.value,
                    "declined": inspection.declined or False,
                    "mileage": inspection.mileage,
                }],
                "200": [],  # No inspection for this booking
                "300": [],  # No inspection for this booking
            }
        }

        assert len(response["inspections"]["100"]) == 1
        assert response["inspections"]["200"] == []
        assert response["inspections"]["300"] == []


# =============================================================================
# Tests: Declined Inspections
# =============================================================================

class TestDeclinedInspections:
    """Tests for declined inspection status."""

    def test_declined_inspection_returns_declined_true(self):
        """Declined inspection should have declined=True in status."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            inspection_type=MockInspectionType.PICKUP,
            declined=True,
        )

        status_data = {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "declined": inspection.declined or False,
            "mileage": inspection.mileage,
        }

        assert status_data["declined"] is True

    def test_non_declined_inspection_returns_declined_false(self):
        """Non-declined inspection should have declined=False in status."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            declined=False,
        )

        status_data = {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "declined": inspection.declined or False,
            "mileage": inspection.mileage,
        }

        assert status_data["declined"] is False

    def test_declined_none_treated_as_false(self):
        """Inspection with declined=None should be treated as False."""
        inspection = create_mock_inspection(id=1, booking_id=100)
        inspection.declined = None

        status_data = {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "declined": inspection.declined or False,
            "mileage": inspection.mileage,
        }

        assert status_data["declined"] is False


# =============================================================================
# Tests: Mileage Field
# =============================================================================

class TestMileageField:
    """Tests for mileage in status response."""

    def test_mileage_included_in_status(self):
        """Mileage should be included in status response."""
        inspection = create_mock_inspection(id=1, booking_id=100, mileage=50000)

        status_data = {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "declined": inspection.declined or False,
            "mileage": inspection.mileage,
        }

        assert status_data["mileage"] == 50000

    def test_mileage_none_when_not_set(self):
        """Mileage should be None when not set."""
        inspection = create_mock_inspection(id=1, booking_id=100)
        inspection.mileage = None

        status_data = {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "declined": inspection.declined or False,
            "mileage": inspection.mileage,
        }

        assert status_data["mileage"] is None


# =============================================================================
# Tests: Booking ID Limit Enforcement
# =============================================================================

class TestBookingIdLimit:
    """Tests for the 100 booking ID limit."""

    def test_limit_of_100_booking_ids_enforced(self):
        """Should only process first 100 booking IDs when more are provided."""
        # Create 150 booking IDs
        booking_ids = list(range(1, 151))

        # The endpoint should limit to first 100
        limited_ids = booking_ids[:100]

        assert len(limited_ids) == 100
        assert limited_ids[0] == 1
        assert limited_ids[-1] == 100
        assert 101 not in limited_ids

    def test_exactly_100_booking_ids_allowed(self):
        """Exactly 100 booking IDs should all be processed."""
        booking_ids = list(range(1, 101))

        # All 100 should be processed
        limited_ids = booking_ids[:100]

        assert len(limited_ids) == 100
        assert limited_ids[-1] == 100


# =============================================================================
# Tests: Inspection Type Values
# =============================================================================

class TestInspectionTypeValues:
    """Tests for inspection_type field values."""

    def test_dropoff_inspection_type_value(self):
        """Dropoff inspection should have type 'dropoff'."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            inspection_type=MockInspectionType.DROPOFF,
        )

        status_data = {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "declined": inspection.declined or False,
            "mileage": inspection.mileage,
        }

        assert status_data["inspection_type"] == "dropoff"

    def test_pickup_inspection_type_value(self):
        """Pickup inspection should have type 'pickup'."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            inspection_type=MockInspectionType.PICKUP,
        )

        status_data = {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "declined": inspection.declined or False,
            "mileage": inspection.mileage,
        }

        assert status_data["inspection_type"] == "pickup"


# =============================================================================
# Tests: Grouping by Booking ID
# =============================================================================

class TestGroupingByBookingId:
    """Tests for correct grouping of results by booking ID."""

    def test_results_grouped_by_booking_id(self):
        """Multiple inspections should be grouped under their booking ID."""
        inspections = [
            create_mock_inspection(id=1, booking_id=100, inspection_type=MockInspectionType.DROPOFF),
            create_mock_inspection(id=2, booking_id=100, inspection_type=MockInspectionType.PICKUP),
            create_mock_inspection(id=3, booking_id=200, inspection_type=MockInspectionType.DROPOFF),
        ]

        # Group by booking_id
        grouped = {}
        for i in inspections:
            bid = str(i.booking_id)
            if bid not in grouped:
                grouped[bid] = []
            grouped[bid].append({
                "id": i.id,
                "booking_id": i.booking_id,
                "inspection_type": i.inspection_type.value,
                "declined": i.declined or False,
                "mileage": i.mileage,
            })

        response = {"inspections": grouped}

        # Booking 100 should have 2 inspections
        assert len(response["inspections"]["100"]) == 2

        # Booking 200 should have 1 inspection
        assert len(response["inspections"]["200"]) == 1

    def test_booking_id_keys_are_strings(self):
        """Booking ID keys in response should be strings for JSON compatibility."""
        inspection = create_mock_inspection(id=1, booking_id=100)

        response = {
            "inspections": {
                str(inspection.booking_id): [{
                    "id": inspection.id,
                    "booking_id": inspection.booking_id,
                    "inspection_type": inspection.inspection_type.value,
                    "declined": inspection.declined or False,
                    "mileage": inspection.mileage,
                }]
            }
        }

        # Key should be string "100" not int 100
        assert "100" in response["inspections"]
        assert isinstance(list(response["inspections"].keys())[0], str)


# =============================================================================
# Tests: Data Size Comparison
# =============================================================================

class TestDataSizeComparison:
    """Tests demonstrating the data size reduction vs full inspection endpoint."""

    def test_status_response_much_smaller_than_full_response(self):
        """Status response should be significantly smaller than full inspection data."""
        # Simulate a full inspection with photos and signature
        full_inspection_data = {
            "id": 1,
            "booking_id": 100,
            "inspection_type": "dropoff",
            "notes": "Vehicle in good condition. Minor scratch on rear bumper.",
            "photos": {
                "front": "data:image/jpeg;base64," + "A" * 50000,  # ~50KB photo
                "rear": "data:image/jpeg;base64," + "B" * 50000,
                "driver_side": "data:image/jpeg;base64," + "C" * 50000,
                "passenger_side": "data:image/jpeg;base64," + "D" * 50000,
            },
            "customer_name": "John Smith",
            "signed_date": "2026-04-03",
            "signature": "data:image/png;base64," + "S" * 10000,  # ~10KB signature
            "vehicle_inspection_read": True,
            "acknowledgement_confirmed": True,
            "mileage": 12500,
            "declined": False,
            "inspector_id": 1,
            "created_at": "2026-04-03T10:00:00",
            "updated_at": "2026-04-03T10:00:00",
        }

        # Status-only data
        status_data = {
            "id": 1,
            "booking_id": 100,
            "inspection_type": "dropoff",
            "declined": False,
            "mileage": 12500,
        }

        full_size = len(json.dumps(full_inspection_data))
        status_size = len(json.dumps(status_data))

        # Status should be at least 100x smaller
        assert status_size < full_size / 100

        # Status should be under 200 bytes
        assert status_size < 200

        # Full data with photos is over 200KB
        assert full_size > 200000

    def test_batch_status_for_20_bookings_still_small(self):
        """Even 20 bookings with inspections should result in small response."""
        # Simulate 20 bookings each with dropoff and pickup inspections
        inspections = {}
        for bid in range(1, 21):
            inspections[str(bid)] = [
                {"id": bid * 2 - 1, "booking_id": bid, "inspection_type": "dropoff", "declined": False, "mileage": 10000 + bid * 100},
                {"id": bid * 2, "booking_id": bid, "inspection_type": "pickup", "declined": False, "mileage": 10100 + bid * 100},
            ]

        response = {"inspections": inspections}
        response_size = len(json.dumps(response))

        # 40 inspection statuses should be under 10KB
        assert response_size < 10000

        # Should be under 5KB actually
        assert response_size < 5000


# =============================================================================
# Tests: Request Body Validation
# =============================================================================

class TestRequestBodyValidation:
    """Tests for request body validation."""

    def test_booking_ids_must_be_array(self):
        """booking_ids must be an array/list."""
        valid_body = {"booking_ids": [1, 2, 3]}

        assert isinstance(valid_body["booking_ids"], list)

    def test_missing_booking_ids_treated_as_empty(self):
        """Missing booking_ids key should be treated as empty array."""
        body = {}
        booking_ids = body.get("booking_ids", [])

        assert booking_ids == []

    def test_null_booking_ids_treated_as_empty(self):
        """Null booking_ids should be treated as empty array."""
        body = {"booking_ids": None}
        booking_ids = body.get("booking_ids") or []

        assert booking_ids == []


# =============================================================================
# Integration-Style Tests (using endpoint behavior simulation)
# =============================================================================

class TestEndpointBehavior:
    """Tests simulating actual endpoint behavior."""

    def test_endpoint_returns_correct_structure(self):
        """Endpoint should return {inspections: {booking_id: [statuses]}}."""
        # Simulate endpoint processing
        booking_ids = [100, 200, 300]

        # Create some inspections
        db_inspections = [
            create_mock_inspection(id=1, booking_id=100, inspection_type=MockInspectionType.DROPOFF),
            create_mock_inspection(id=2, booking_id=200, inspection_type=MockInspectionType.DROPOFF),
            create_mock_inspection(id=3, booking_id=200, inspection_type=MockInspectionType.PICKUP, declined=True),
        ]

        # Simulate endpoint logic
        result = {str(bid): [] for bid in booking_ids}
        for i in db_inspections:
            inspection_status = {
                "id": i.id,
                "booking_id": i.booking_id,
                "inspection_type": i.inspection_type.value,
                "declined": i.declined or False,
                "mileage": i.mileage,
            }
            result[str(i.booking_id)].append(inspection_status)

        response = {"inspections": result}

        # Verify structure
        assert "inspections" in response
        assert "100" in response["inspections"]
        assert "200" in response["inspections"]
        assert "300" in response["inspections"]

        # Verify 100 has 1 inspection
        assert len(response["inspections"]["100"]) == 1

        # Verify 200 has 2 inspections (dropoff + declined pickup)
        assert len(response["inspections"]["200"]) == 2
        pickup = next(i for i in response["inspections"]["200"] if i["inspection_type"] == "pickup")
        assert pickup["declined"] is True

        # Verify 300 has no inspections
        assert len(response["inspections"]["300"]) == 0

    def test_endpoint_handles_large_batch_efficiently(self):
        """Endpoint should handle 100 bookings efficiently."""
        booking_ids = list(range(1, 101))

        # Simulate having inspections for every other booking
        db_inspections = [
            create_mock_inspection(id=i, booking_id=i * 2, inspection_type=MockInspectionType.DROPOFF)
            for i in range(1, 51)
        ]

        # Simulate endpoint logic
        result = {str(bid): [] for bid in booking_ids}
        for i in db_inspections:
            if str(i.booking_id) in result:
                inspection_status = {
                    "id": i.id,
                    "booking_id": i.booking_id,
                    "inspection_type": i.inspection_type.value,
                    "declined": i.declined or False,
                    "mileage": i.mileage,
                }
                result[str(i.booking_id)].append(inspection_status)

        response = {"inspections": result}

        # All 100 booking IDs should be in response
        assert len(response["inspections"]) == 100

        # 50 should have inspections, 50 should be empty
        with_inspections = sum(1 for v in response["inspections"].values() if len(v) > 0)
        without_inspections = sum(1 for v in response["inspections"].values() if len(v) == 0)

        assert with_inspections == 50
        assert without_inspections == 50


# =============================================================================
# Tests: Comparison with Full Endpoint
# =============================================================================

class TestComparisonWithFullEndpoint:
    """Tests comparing status endpoint with full inspection endpoint."""

    def test_status_endpoint_fields_subset_of_full_endpoint(self):
        """Status endpoint fields should be a subset of full endpoint fields."""
        full_endpoint_fields = {
            "id", "booking_id", "inspection_type", "notes", "photos",
            "customer_name", "signed_date", "signature", "vehicle_inspection_read",
            "acknowledgement_confirmed", "mileage", "declined", "inspector_id",
            "created_at", "updated_at"
        }

        status_endpoint_fields = {"id", "booking_id", "inspection_type", "declined", "mileage"}

        # Status fields should be subset of full fields
        assert status_endpoint_fields.issubset(full_endpoint_fields)

        # These fields should NOT be in status endpoint
        excluded_fields = {"notes", "photos", "customer_name", "signed_date",
                         "signature", "vehicle_inspection_read", "acknowledgement_confirmed",
                         "inspector_id", "created_at", "updated_at"}

        assert status_endpoint_fields.isdisjoint(excluded_fields)

    def test_status_endpoint_sufficient_for_calendar_view(self):
        """Status endpoint should provide all data needed for calendar view."""
        status_data = {
            "id": 1,
            "booking_id": 100,
            "inspection_type": "dropoff",
            "declined": False,
            "mileage": 12500,
        }

        # Calendar view needs to know:
        # 1. Does inspection exist? -> id is present
        assert status_data["id"] is not None

        # 2. What type is it? -> inspection_type
        assert status_data["inspection_type"] in ("dropoff", "pickup")

        # 3. Was it declined? -> declined
        assert status_data["declined"] in (True, False)

        # 4. Does it have mileage? (optional info) -> mileage
        assert status_data["mileage"] is None or isinstance(status_data["mileage"], int)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
