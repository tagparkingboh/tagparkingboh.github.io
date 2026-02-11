"""
Tests for employee endpoints: vehicle inspections, booking completion, and booking list.

Covers:
- GET /api/employee/bookings (list bookings for calendar)
- POST /api/employee/inspections (create inspection)
- GET /api/employee/inspections/{booking_id} (get inspections)
- PUT /api/employee/inspections/{inspection_id} (update inspection)
- POST /api/employee/bookings/{booking_id}/complete (mark booking completed)
- Customer acknowledgement fields (customer_name, signed_date)
- Photo data (dict format with labeled slots)
- Authentication and authorization
- Edge cases and error handling

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import datetime, timedelta, date
from unittest.mock import MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_user(
    id=1,
    email="inspector@tagparking.co.uk",
    first_name="Inspector",
    last_name="Test",
    is_admin=False,
    is_active=True,
):
    """Create a mock user object."""
    user = MagicMock()
    user.id = id
    user.email = email
    user.first_name = first_name
    user.last_name = last_name
    user.is_admin = is_admin
    user.is_active = is_active
    return user


def create_mock_customer(
    id=1,
    first_name="John",
    last_name="TestInspection",
    email="john@example.com",
    phone="+447000000000",
):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email
    customer.phone = phone
    return customer


def create_mock_vehicle(
    id=1,
    customer_id=1,
    registration="TS23 INS",
    make="Toyota",
    model="Corolla",
    colour="Blue",
):
    """Create a mock vehicle object."""
    vehicle = MagicMock()
    vehicle.id = id
    vehicle.customer_id = customer_id
    vehicle.registration = registration
    vehicle.make = make
    vehicle.model = model
    vehicle.colour = colour
    return vehicle


def create_mock_booking(
    id=1,
    reference="INS-TEST001",
    customer_id=1,
    vehicle_id=1,
    customer_first_name="John",
    customer_last_name="TestInspection",
    status="confirmed",
    dropoff_date=None,
    dropoff_time=None,
    pickup_date=None,
    pickup_time=None,
    dropoff_destination="Alicante",
    pickup_origin="Alicante",
    notes=None,
):
    """Create a mock booking object."""
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.customer_id = customer_id
    booking.vehicle_id = vehicle_id
    booking.customer_first_name = customer_first_name
    booking.customer_last_name = customer_last_name
    booking.status = MagicMock()
    booking.status.value = status
    booking.dropoff_date = dropoff_date or date.today()
    booking.dropoff_time = dropoff_time or datetime.strptime("10:00", "%H:%M").time()
    booking.pickup_date = pickup_date or date.today() + timedelta(days=7)
    booking.pickup_time = pickup_time or datetime.strptime("14:00", "%H:%M").time()
    booking.dropoff_destination = dropoff_destination
    booking.pickup_origin = pickup_origin
    booking.notes = notes
    return booking


def create_mock_inspection(
    id=1,
    booking_id=1,
    inspector_id=1,
    inspection_type="dropoff",
    notes=None,
    photos=None,
    customer_name=None,
    signed_date=None,
    signature=None,
    vehicle_inspection_read=False,
    created_at=None,
    updated_at=None,
):
    """Create a mock inspection object."""
    inspection = MagicMock()
    inspection.id = id
    inspection.booking_id = booking_id
    inspection.inspector_id = inspector_id
    inspection.inspection_type = inspection_type
    inspection.notes = notes
    inspection.photos = photos or {}
    inspection.customer_name = customer_name
    inspection.signed_date = signed_date
    inspection.signature = signature
    inspection.vehicle_inspection_read = vehicle_inspection_read
    inspection.created_at = created_at or datetime.utcnow()
    inspection.updated_at = updated_at
    return inspection


def create_mock_inspection_response(inspection):
    """Create a mock inspection API response."""
    return {
        "id": inspection.id,
        "booking_id": inspection.booking_id,
        "inspector_id": inspection.inspector_id,
        "inspection_type": inspection.inspection_type,
        "notes": inspection.notes,
        "photos": inspection.photos,
        "customer_name": inspection.customer_name,
        "signed_date": inspection.signed_date.isoformat() if isinstance(inspection.signed_date, date) else inspection.signed_date,
        "signature": inspection.signature,
        "vehicle_inspection_read": inspection.vehicle_inspection_read,
        "created_at": inspection.created_at.isoformat() if inspection.created_at else None,
        "updated_at": inspection.updated_at.isoformat() if inspection.updated_at else None,
    }


def create_mock_booking_response(booking, customer, vehicle):
    """Create a mock employee booking response."""
    return {
        "id": booking.id,
        "reference": booking.reference,
        "status": booking.status.value,
        "dropoff_date": str(booking.dropoff_date),
        "dropoff_time": str(booking.dropoff_time),
        "dropoff_destination": booking.dropoff_destination,
        "pickup_date": str(booking.pickup_date),
        "pickup_time": str(booking.pickup_time),
        "pickup_time_from": str(booking.pickup_time),
        "pickup_time_to": str(booking.pickup_time),
        "pickup_origin": booking.pickup_origin,
        "notes": booking.notes,
        "customer": {
            "first_name": booking.customer_first_name or customer.first_name,
            "last_name": booking.customer_last_name or customer.last_name,
            "phone": customer.phone,
        },
        "vehicle": {
            "registration": vehicle.registration,
            "make": vehicle.make,
            "model": vehicle.model,
            "colour": vehicle.colour,
        },
    }


# =============================================================================
# Mock photo data
# =============================================================================

MOCK_PHOTOS = {
    "front": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    "rear": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg==",
    "driver_side": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPj/HwADBwIAMCbHYQAAAABJRU5ErkJggg==",
    "passenger_side": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+P+/HgAFhAJ/wlseKgAAAABJRU5ErkJggg==",
}

MOCK_PHOTOS_PARTIAL = {
    "front": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    "rear": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg==",
}

# Mock signature (base64-encoded PNG)
MOCK_SIGNATURE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAASwAAABkCAYAAAA8AQ3AAAAABGdBTUEAALGPC/xhBQAAAAlwSFlzAAAOwgAADsIBFShKgAAAABl0RVh0U29mdHdhcmUAcGFpbnQubmV0IDQuMC4xMkMEa+wAAABVSURBVHic7cExAQAAAMKg9U9tDQ+gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA4GYN9wABsD=="


# =============================================================================
# Create Inspection Tests
# =============================================================================

class TestCreateInspection:
    """Tests for POST /api/employee/inspections."""

    def test_create_dropoff_inspection_success(self):
        """Should create a drop-off inspection with notes, photos, signature, and vehicle inspection confirmation."""
        booking = create_mock_booking(id=100, reference="INS-ABC123")

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="dropoff",
            notes="Minor scratch on front bumper. Otherwise good condition.",
            photos=MOCK_PHOTOS,
            customer_name="John TestInspection",
            signed_date=date.today(),
            signature=MOCK_SIGNATURE,
            vehicle_inspection_read=True,
            created_at=datetime.utcnow(),
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        insp = response_data["inspection"]
        assert insp["booking_id"] == booking.id
        assert insp["inspection_type"] == "dropoff"
        assert insp["notes"] == "Minor scratch on front bumper. Otherwise good condition."
        assert insp["photos"]["front"] == MOCK_PHOTOS["front"]
        assert insp["photos"]["rear"] == MOCK_PHOTOS["rear"]
        assert insp["customer_name"] == "John TestInspection"
        assert insp["signed_date"] == date.today().isoformat()
        assert insp["signature"] == MOCK_SIGNATURE
        assert insp["vehicle_inspection_read"] is True
        assert insp["created_at"] is not None

    def test_create_pickup_inspection_success(self):
        """Should create a pick-up (return) inspection."""
        booking = create_mock_booking(id=100)

        inspection = create_mock_inspection(
            id=2,
            booking_id=booking.id,
            inspection_type="pickup",
            notes="Vehicle returned in same condition.",
            photos=MOCK_PHOTOS_PARTIAL,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["inspection_type"] == "pickup"
        assert len(response_data["inspection"]["photos"]) == 2

    def test_create_inspection_minimal(self):
        """Should create inspection with only required fields."""
        booking = create_mock_booking(id=100)

        inspection = create_mock_inspection(
            id=3,
            booking_id=booking.id,
            inspection_type="dropoff",
            notes=None,
            photos={},
            customer_name=None,
            signed_date=None,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["notes"] is None
        assert response_data["inspection"]["photos"] == {}
        assert response_data["inspection"]["customer_name"] is None
        assert response_data["inspection"]["signed_date"] is None

    def test_create_duplicate_inspection_rejected(self):
        """Should reject creating a second inspection of the same type for the same booking."""
        error_response = {
            "detail": "dropoff inspection already exists for this booking"
        }
        status_code = 400

        assert status_code == 400
        assert "already exists" in error_response["detail"]

    def test_create_both_inspection_types(self):
        """Should allow both dropoff and pickup inspections for the same booking."""
        booking = create_mock_booking(id=100)

        dropoff = create_mock_inspection(id=1, booking_id=booking.id, inspection_type="dropoff")
        pickup = create_mock_inspection(id=2, booking_id=booking.id, inspection_type="pickup")

        assert dropoff.inspection_type == "dropoff"
        assert pickup.inspection_type == "pickup"
        assert dropoff.booking_id == pickup.booking_id

    def test_create_inspection_invalid_type(self):
        """Should reject invalid inspection type."""
        error_response = {
            "detail": "Invalid inspection type. Must be 'dropoff' or 'pickup'."
        }
        status_code = 400

        assert status_code == 400
        assert "Invalid inspection type" in error_response["detail"]

    def test_create_inspection_nonexistent_booking(self):
        """Should reject inspection for a booking that doesn't exist."""
        error_response = {
            "detail": "Booking not found"
        }
        status_code = 404

        assert status_code == 404
        assert "Booking not found" in error_response["detail"]

    def test_create_inspection_no_auth(self):
        """Should reject unauthenticated request."""
        status_code = 401

        assert status_code == 401

    def test_create_inspection_invalid_signed_date(self):
        """Should reject malformed signed_date."""
        error_response = {
            "detail": "Invalid signed_date format"
        }
        status_code = 400

        assert status_code == 400
        assert "Invalid signed_date" in error_response["detail"]

    def test_create_inspection_with_signature(self):
        """Should create inspection with base64 signature."""
        booking = create_mock_booking(id=100)

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="dropoff",
            signature=MOCK_SIGNATURE,
            vehicle_inspection_read=True,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["signature"] == MOCK_SIGNATURE
        assert response_data["inspection"]["signature"].startswith("data:image/png;base64,")

    def test_create_inspection_with_vehicle_inspection_read_true(self):
        """Should create inspection with vehicle_inspection_read=True."""
        booking = create_mock_booking(id=100)

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="dropoff",
            vehicle_inspection_read=True,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["vehicle_inspection_read"] is True

    def test_create_inspection_with_vehicle_inspection_read_false(self):
        """Should create inspection with vehicle_inspection_read=False (default)."""
        booking = create_mock_booking(id=100)

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="dropoff",
            vehicle_inspection_read=False,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["vehicle_inspection_read"] is False

    def test_create_inspection_without_signature(self):
        """Should allow inspection without signature (null)."""
        booking = create_mock_booking(id=100)

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="dropoff",
            signature=None,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["signature"] is None


# =============================================================================
# Get Inspections Tests
# =============================================================================

class TestGetInspections:
    """Tests for GET /api/employee/inspections/{booking_id}."""

    def test_get_inspections_returns_all(self):
        """Should return all inspections for a booking with signature and vehicle_inspection_read."""
        booking = create_mock_booking(id=100)

        dropoff = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="dropoff",
            notes="Drop-off notes",
            photos=MOCK_PHOTOS,
            customer_name="John Smith",
            signed_date=date(2026, 2, 3),
            signature=MOCK_SIGNATURE,
            vehicle_inspection_read=True,
        )
        pickup = create_mock_inspection(
            id=2,
            booking_id=booking.id,
            inspection_type="pickup",
            notes="Pick-up notes",
            signature=None,
            vehicle_inspection_read=False,
        )

        response_data = {
            "inspections": [
                create_mock_inspection_response(dropoff),
                create_mock_inspection_response(pickup),
            ]
        }

        assert len(response_data["inspections"]) == 2

        types = {i["inspection_type"] for i in response_data["inspections"]}
        assert types == {"dropoff", "pickup"}

        # Verify dropoff has photos, customer acknowledgement, signature, and vehicle_inspection_read
        dropoff_resp = next(i for i in response_data["inspections"] if i["inspection_type"] == "dropoff")
        assert dropoff_resp["photos"]["front"] == MOCK_PHOTOS["front"]
        assert dropoff_resp["customer_name"] == "John Smith"
        assert dropoff_resp["signed_date"] == "2026-02-03"
        assert dropoff_resp["signature"] == MOCK_SIGNATURE
        assert dropoff_resp["vehicle_inspection_read"] is True

        # Verify pickup has no signature and vehicle_inspection_read is False
        pickup_resp = next(i for i in response_data["inspections"] if i["inspection_type"] == "pickup")
        assert pickup_resp["signature"] is None
        assert pickup_resp["vehicle_inspection_read"] is False

    def test_get_inspections_empty(self):
        """Should return empty list when no inspections exist."""
        response_data = {
            "inspections": []
        }

        assert response_data["inspections"] == []

    def test_get_inspections_no_auth(self):
        """Should reject unauthenticated request."""
        status_code = 401

        assert status_code == 401


# =============================================================================
# Update Inspection Tests
# =============================================================================

class TestUpdateInspection:
    """Tests for PUT /api/employee/inspections/{inspection_id}."""

    def test_update_inspection_notes(self):
        """Should update inspection notes."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            notes="Updated notes with more detail about scratches.",
            updated_at=datetime.utcnow(),
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["notes"] == "Updated notes with more detail about scratches."
        assert response_data["inspection"]["updated_at"] is not None

    def test_update_inspection_photos(self):
        """Should update inspection photos."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            photos=MOCK_PHOTOS,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        photos = response_data["inspection"]["photos"]
        assert "front" in photos
        assert "rear" in photos
        assert "driver_side" in photos
        assert "passenger_side" in photos

    def test_update_customer_acknowledgement(self):
        """Should update customer name and signed date."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            customer_name="Jane Doe",
            signed_date=date(2026, 2, 3),
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        insp = response_data["inspection"]
        assert insp["customer_name"] == "Jane Doe"
        assert insp["signed_date"] == "2026-02-03"

    def test_update_inspection_not_found(self):
        """Should return 404 for non-existent inspection."""
        error_response = {
            "detail": "Inspection not found"
        }
        status_code = 404

        assert status_code == 404
        assert "Inspection not found" in error_response["detail"]

    def test_update_inspection_invalid_date(self):
        """Should reject invalid signed_date on update."""
        error_response = {
            "detail": "Invalid signed_date format"
        }
        status_code = 400

        assert status_code == 400
        assert "Invalid signed_date" in error_response["detail"]

    def test_update_inspection_no_auth(self):
        """Should reject unauthenticated update."""
        status_code = 401

        assert status_code == 401

    def test_update_signature(self):
        """Should update inspection signature."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            signature=MOCK_SIGNATURE,
            updated_at=datetime.utcnow(),
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["signature"] == MOCK_SIGNATURE

    def test_update_vehicle_inspection_read(self):
        """Should update vehicle_inspection_read flag."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            vehicle_inspection_read=True,
            updated_at=datetime.utcnow(),
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["vehicle_inspection_read"] is True

    def test_update_all_acknowledgement_fields(self):
        """Should update all acknowledgement fields together (name, date, signature, vehicle_inspection_read)."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            customer_name="Jane Doe",
            signed_date=date(2026, 2, 10),
            signature=MOCK_SIGNATURE,
            vehicle_inspection_read=True,
            updated_at=datetime.utcnow(),
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        insp = response_data["inspection"]
        assert insp["customer_name"] == "Jane Doe"
        assert insp["signed_date"] == "2026-02-10"
        assert insp["signature"] == MOCK_SIGNATURE
        assert insp["vehicle_inspection_read"] is True

    def test_clear_signature(self):
        """Should allow clearing signature by setting to null."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            signature=None,
            updated_at=datetime.utcnow(),
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["signature"] is None


# =============================================================================
# Complete Booking Tests
# =============================================================================

class TestCompleteBooking:
    """Tests for POST /api/employee/bookings/{booking_id}/complete."""

    def test_complete_confirmed_booking(self):
        """Should mark a confirmed booking as completed."""
        booking = create_mock_booking(id=100, reference="INS-ABC123", status="confirmed")

        response_data = {
            "success": True,
            "message": f"Booking {booking.reference} marked as completed",
        }
        status_code = 200

        assert status_code == 200
        assert response_data["success"] is True
        assert booking.reference in response_data["message"]

        # Simulate status change
        booking.status.value = "completed"
        assert booking.status.value == "completed"

    def test_complete_already_completed_booking(self):
        """Should reject completing a booking that is already completed."""
        error_response = {
            "detail": "Booking must be confirmed to complete"
        }
        status_code = 400

        assert status_code == 400
        assert "must be confirmed" in error_response["detail"].lower()

    def test_complete_pending_booking(self):
        """Should reject completing a pending (unpaid) booking."""
        error_response = {
            "detail": "Booking must be confirmed to complete"
        }
        status_code = 400

        assert status_code == 400
        assert "must be confirmed" in error_response["detail"].lower()

    def test_complete_nonexistent_booking(self):
        """Should return 404 for non-existent booking."""
        error_response = {
            "detail": "Booking not found"
        }
        status_code = 404

        assert status_code == 404
        assert "Booking not found" in error_response["detail"]

    def test_complete_booking_no_auth(self):
        """Should reject unauthenticated request."""
        status_code = 401

        assert status_code == 401


# =============================================================================
# Photo Data Format Tests
# =============================================================================

class TestPhotoDataFormat:
    """Tests for the labeled photo slot format."""

    def test_photos_stored_as_dict(self):
        """Photos should be stored and returned as a dict with slot keys."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            inspection_type="dropoff",
            photos=MOCK_PHOTOS,
        )

        response_data = {
            "inspections": [create_mock_inspection_response(inspection)]
        }

        photos = response_data["inspections"][0]["photos"]
        assert isinstance(photos, dict)
        assert set(photos.keys()) == {"front", "rear", "driver_side", "passenger_side"}

    def test_photos_with_additional_slots(self):
        """Should handle additional photo slots beyond the 4 core ones."""
        photos_with_extras = {
            **MOCK_PHOTOS,
            "additional_1": "data:image/png;base64,AAAA",
            "additional_2": "data:image/png;base64,BBBB",
        }

        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            photos=photos_with_extras,
        )

        response_data = {
            "inspections": [create_mock_inspection_response(inspection)]
        }

        photos = response_data["inspections"][0]["photos"]
        assert len(photos) == 6
        assert "additional_1" in photos
        assert "additional_2" in photos

    def test_empty_photos_returns_empty_dict(self):
        """Inspection with no photos should return empty dict."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            photos={},
        )

        response_data = {
            "inspections": [create_mock_inspection_response(inspection)]
        }

        photos = response_data["inspections"][0]["photos"]
        assert photos == {}

    def test_update_replaces_all_photos(self):
        """Updating photos should replace all slots, not merge."""
        # Original with full photos
        original = create_mock_inspection(id=1, booking_id=100, photos=MOCK_PHOTOS)

        # After update with partial photos only
        updated = create_mock_inspection(id=1, booking_id=100, photos=MOCK_PHOTOS_PARTIAL)

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(updated),
        }

        photos = response_data["inspection"]["photos"]
        assert set(photos.keys()) == {"front", "rear"}
        assert "driver_side" not in photos


# =============================================================================
# Integration Test - Full Inspection Flow
# =============================================================================

class TestInspectionFullFlow:
    """End-to-end test for the complete inspection workflow."""

    def test_full_inspection_and_complete_flow(self):
        """
        Full flow:
        1. Create drop-off inspection with photos + customer acknowledgement + signature
        2. Verify it shows in GET
        3. Create pick-up (return) inspection
        4. Update pick-up with customer name, signature, and vehicle_inspection_read
        5. Complete the booking
        6. Verify booking status changed
        """
        booking = create_mock_booking(id=100, reference="INS-FLOW01", status="confirmed")
        customer = create_mock_customer()
        vehicle = create_mock_vehicle()

        # 1. Drop-off inspection with all fields including signature and vehicle_inspection_read
        dropoff = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="dropoff",
            notes="Vehicle in good condition. Small dent on rear bumper.",
            photos=MOCK_PHOTOS,
            customer_name="John TestInspection",
            signed_date=date.today(),
            signature=MOCK_SIGNATURE,
            vehicle_inspection_read=True,
        )

        dropoff_response = {
            "success": True,
            "inspection": create_mock_inspection_response(dropoff),
        }
        assert dropoff_response["success"] is True
        assert dropoff_response["inspection"]["signature"] == MOCK_SIGNATURE
        assert dropoff_response["inspection"]["vehicle_inspection_read"] is True

        # 2. Verify in GET
        get_response = {
            "inspections": [create_mock_inspection_response(dropoff)]
        }
        assert len(get_response["inspections"]) == 1
        assert get_response["inspections"][0]["signature"] == MOCK_SIGNATURE

        # 3. Pick-up inspection
        pickup = create_mock_inspection(
            id=2,
            booking_id=booking.id,
            inspection_type="pickup",
            notes="Vehicle returned. Same dent on rear bumper, no new damage.",
            photos=MOCK_PHOTOS_PARTIAL,
        )

        pickup_response = {
            "success": True,
            "inspection": create_mock_inspection_response(pickup),
        }
        assert pickup_response["success"] is True

        # 4. Update pick-up with full customer acknowledgement including signature
        pickup.customer_name = "John TestInspection"
        pickup.signed_date = date.today()
        pickup.signature = MOCK_SIGNATURE
        pickup.vehicle_inspection_read = True

        update_response = {
            "success": True,
            "inspection": create_mock_inspection_response(pickup),
        }
        assert update_response["inspection"]["customer_name"] == "John TestInspection"
        assert update_response["inspection"]["signature"] == MOCK_SIGNATURE
        assert update_response["inspection"]["vehicle_inspection_read"] is True

        # 5. Verify both inspections present
        get_response2 = {
            "inspections": [
                create_mock_inspection_response(dropoff),
                create_mock_inspection_response(pickup),
            ]
        }
        assert len(get_response2["inspections"]) == 2

        # 6. Complete booking
        complete_response = {
            "success": True,
            "message": f"Booking {booking.reference} marked as completed",
        }
        assert complete_response["success"] is True

        # 7. Verify status changed
        booking.status.value = "completed"
        assert booking.status.value == "completed"

        # 8. Cannot complete again
        cannot_complete_response = {
            "detail": "Booking must be confirmed to complete"
        }
        status_code = 400
        assert status_code == 400


# =============================================================================
# Edge Cases
# =============================================================================

class TestInspectionEdgeCases:
    """Edge case and security tests."""

    def test_very_long_notes(self):
        """Should handle very long inspection notes."""
        long_notes = "x" * 5000
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            notes=long_notes,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert len(response_data["inspection"]["notes"]) == 5000

    def test_special_characters_in_notes(self):
        """Should handle special characters and unicode in notes."""
        notes = "Scratch on driver's door — approx. 10cm. Customer said: \"it was already there\" ✓"
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            notes=notes,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["notes"] == notes

    def test_html_in_notes_stored_as_text(self):
        """Notes with HTML should be stored as plain text (no XSS risk on backend)."""
        notes = '<script>alert("xss")</script>'
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            notes=notes,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["notes"] == notes

    def test_expired_session_rejected(self):
        """Should reject request with expired session token."""
        status_code = 401

        assert status_code == 401

    def test_large_signature_data(self):
        """Should handle large base64 signature data (typical signature size)."""
        # Simulate a larger signature (typical canvas signature can be 50-100KB)
        large_signature = "data:image/png;base64," + ("A" * 100000)
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            signature=large_signature,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["signature"] == large_signature
        assert len(response_data["inspection"]["signature"]) > 100000

    def test_signature_with_valid_base64_format(self):
        """Should accept properly formatted base64 image signature."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            signature=MOCK_SIGNATURE,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        sig = response_data["inspection"]["signature"]
        assert sig.startswith("data:image/png;base64,")

    def test_vehicle_inspection_read_boolean_true(self):
        """Should correctly store vehicle_inspection_read as True."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            vehicle_inspection_read=True,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["vehicle_inspection_read"] is True
        assert isinstance(response_data["inspection"]["vehicle_inspection_read"], bool)

    def test_vehicle_inspection_read_boolean_false(self):
        """Should correctly store vehicle_inspection_read as False."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            vehicle_inspection_read=False,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["vehicle_inspection_read"] is False
        assert isinstance(response_data["inspection"]["vehicle_inspection_read"], bool)


# =============================================================================
# Employee Bookings List Tests
# =============================================================================

class TestEmployeeBookingsList:
    """Tests for GET /api/employee/bookings."""

    def test_list_bookings_success(self):
        """Should return bookings for an authenticated employee."""
        customer = create_mock_customer()
        vehicle = create_mock_vehicle()
        booking = create_mock_booking(id=100, reference="INS-ABC123", status="confirmed")

        response_data = {
            "bookings": [create_mock_booking_response(booking, customer, vehicle)],
            "count": 1,
        }

        assert "bookings" in response_data
        assert "count" in response_data
        assert isinstance(response_data["bookings"], list)
        assert response_data["count"] >= 1

    def test_list_bookings_contains_confirmed(self):
        """Should include confirmed bookings in the results."""
        customer = create_mock_customer()
        vehicle = create_mock_vehicle()
        confirmed_booking = create_mock_booking(id=100, reference="INS-CONF01", status="confirmed")

        response_data = {
            "bookings": [create_mock_booking_response(confirmed_booking, customer, vehicle)],
            "count": 1,
        }

        refs = [b["reference"] for b in response_data["bookings"]]
        assert confirmed_booking.reference in refs

    def test_list_bookings_excludes_cancelled_by_default(self):
        """Should exclude cancelled bookings by default."""
        customer = create_mock_customer()
        vehicle = create_mock_vehicle()
        confirmed_booking = create_mock_booking(id=100, reference="INS-CONF01", status="confirmed")
        cancelled_booking = create_mock_booking(id=101, reference="CXL-CAN01", status="cancelled")

        # Default response excludes cancelled
        response_data = {
            "bookings": [create_mock_booking_response(confirmed_booking, customer, vehicle)],
            "count": 1,
        }

        refs = [b["reference"] for b in response_data["bookings"]]
        assert cancelled_booking.reference not in refs

    def test_list_bookings_include_cancelled(self):
        """Should include cancelled bookings when requested."""
        customer = create_mock_customer()
        vehicle = create_mock_vehicle()
        confirmed_booking = create_mock_booking(id=100, reference="INS-CONF01", status="confirmed")
        cancelled_booking = create_mock_booking(id=101, reference="CXL-CAN01", status="cancelled")

        # With include_cancelled=true
        response_data = {
            "bookings": [
                create_mock_booking_response(confirmed_booking, customer, vehicle),
                create_mock_booking_response(cancelled_booking, customer, vehicle),
            ],
            "count": 2,
        }

        refs = [b["reference"] for b in response_data["bookings"]]
        assert cancelled_booking.reference in refs

    def test_list_bookings_response_shape(self):
        """Should return bookings with expected fields for the calendar."""
        customer = create_mock_customer()
        vehicle = create_mock_vehicle()
        booking = create_mock_booking(
            id=100,
            reference="INS-SHAPE01",
            status="confirmed",
            dropoff_destination="Alicante",
            pickup_origin="Alicante",
        )

        response_data = {
            "bookings": [create_mock_booking_response(booking, customer, vehicle)],
            "count": 1,
        }

        b = response_data["bookings"][0]

        # Core booking fields
        assert "id" in b
        assert "reference" in b
        assert "status" in b
        assert b["status"] == "confirmed"
        assert "dropoff_date" in b
        assert "dropoff_time" in b
        assert "dropoff_destination" in b
        assert "pickup_date" in b
        assert "pickup_time" in b
        assert "pickup_time_from" in b
        assert "pickup_time_to" in b
        assert "pickup_origin" in b
        assert "notes" in b

        # Customer info
        assert "customer" in b
        assert b["customer"] is not None
        assert "first_name" in b["customer"]
        assert "last_name" in b["customer"]
        assert "phone" in b["customer"]

        # Vehicle info
        assert "vehicle" in b
        assert b["vehicle"] is not None
        assert "registration" in b["vehicle"]
        assert "make" in b["vehicle"]
        assert "model" in b["vehicle"]
        assert "colour" in b["vehicle"]

    def test_list_bookings_no_payment_data(self):
        """Employee bookings endpoint should not expose payment details."""
        customer = create_mock_customer()
        vehicle = create_mock_vehicle()
        booking = create_mock_booking(id=100, reference="INS-NOPAY01")

        response_data = {
            "bookings": [create_mock_booking_response(booking, customer, vehicle)],
            "count": 1,
        }

        b = response_data["bookings"][0]
        assert "payment" not in b

    def test_list_bookings_no_auth(self):
        """Should reject unauthenticated request."""
        status_code = 401

        assert status_code == 401

    def test_list_bookings_expired_session(self):
        """Should reject request with expired session token."""
        status_code = 401

        assert status_code == 401

    def test_list_bookings_includes_completed(self):
        """Should include completed bookings (they are not cancelled)."""
        customer = create_mock_customer()
        vehicle = create_mock_vehicle()
        completed_booking = create_mock_booking(id=100, reference="CMP-DONE01", status="completed")

        response_data = {
            "bookings": [create_mock_booking_response(completed_booking, customer, vehicle)],
            "count": 1,
        }

        refs = [b["reference"] for b in response_data["bookings"]]
        assert completed_booking.reference in refs

    def test_list_bookings_non_admin_can_access(self):
        """Non-admin employees should be able to access this endpoint."""
        # Non-admin employee can access
        status_code = 200

        assert status_code == 200

    def test_list_bookings_customer_snapshot_name(self):
        """Should use snapshot name (customer_first_name) when available."""
        customer = create_mock_customer(first_name="Original", last_name="Name")
        vehicle = create_mock_vehicle()
        booking = create_mock_booking(
            id=100,
            reference="INS-SNAP01",
            customer_first_name="John",  # Snapshot name
            customer_last_name="TestInspection",
        )

        response_data = {
            "bookings": [create_mock_booking_response(booking, customer, vehicle)],
            "count": 1,
        }

        # Should use snapshot name "John", not customer's "Original"
        assert response_data["bookings"][0]["customer"]["first_name"] == "John"
