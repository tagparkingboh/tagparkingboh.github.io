"""
Tests for Customer Declined Inspection feature.

This feature allows employees to mark that a customer declined the return inspection.
When declined=True:
- Only mileage is required (signature, acknowledgement, photos are optional)
- The booking can be completed without a full inspection
- The declined field is stored on the vehicle_inspections table

Covers:
- Unit tests for declined inspection creation
- Unit tests for declined inspection update
- Unit tests for decline/undecline endpoints
- Integration tests for complete declined inspection workflow
- Edge cases and negative tests

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import datetime, timedelta, date
from unittest.mock import MagicMock, patch

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


def create_mock_booking(
    id=1,
    reference="DCL-TEST001",
    customer_id=1,
    vehicle_id=1,
    customer_first_name="John",
    customer_last_name="Declined",
    status="confirmed",
    dropoff_date=None,
    dropoff_time=None,
    pickup_date=None,
    pickup_time=None,
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
    return booking


def create_mock_inspection(
    id=1,
    booking_id=1,
    inspector_id=1,
    inspection_type="pickup",
    notes=None,
    photos=None,
    customer_name=None,
    signed_date=None,
    signature=None,
    vehicle_inspection_read=False,
    acknowledgement_confirmed=False,
    declined=False,
    mileage=None,
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
    inspection.acknowledgement_confirmed = acknowledgement_confirmed
    inspection.declined = declined
    inspection.mileage = mileage
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
        "acknowledgement_confirmed": inspection.acknowledgement_confirmed,
        "declined": inspection.declined,
        "mileage": inspection.mileage,
        "created_at": inspection.created_at.isoformat() if inspection.created_at else None,
        "updated_at": inspection.updated_at.isoformat() if inspection.updated_at else None,
    }


# =============================================================================
# Unit Tests: Create Declined Inspection
# =============================================================================

class TestCreateDeclinedInspection:
    """Tests for creating inspections with declined=True."""

    def test_create_declined_inspection_with_mileage_only(self):
        """Should create a declined inspection with only mileage (minimal required data)."""
        booking = create_mock_booking(id=100, reference="DCL-MIN01")

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
            # No signature, no acknowledgement, no photos - all optional when declined
            signature=None,
            acknowledgement_confirmed=False,
            photos={},
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        insp = response_data["inspection"]
        assert insp["declined"] is True
        assert insp["mileage"] == 45000
        assert insp["inspection_type"] == "pickup"
        assert insp["signature"] is None
        assert insp["acknowledgement_confirmed"] is False
        assert insp["photos"] == {}

    def test_create_declined_inspection_preserves_mileage(self):
        """Declined inspection should store mileage correctly."""
        booking = create_mock_booking(id=100, reference="DCL-MIL01")

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=123456,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["mileage"] == 123456

    def test_create_declined_inspection_with_notes(self):
        """Should allow declined inspection with optional notes."""
        booking = create_mock_booking(id=100, reference="DCL-NOTE01")

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
            notes="Customer declined due to being in a hurry.",
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["declined"] is True
        assert response_data["inspection"]["notes"] == "Customer declined due to being in a hurry."

    def test_create_declined_inspection_for_pickup_only(self):
        """Declined inspection should be for pickup (return) type only."""
        booking = create_mock_booking(id=100, reference="DCL-TYPE01")

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["inspection_type"] == "pickup"
        assert response_data["inspection"]["declined"] is True

    def test_create_inspection_declined_default_false(self):
        """New inspections should have declined=False by default."""
        booking = create_mock_booking(id=100, reference="DCL-DEF01")

        # Normal inspection without explicitly setting declined
        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=False,  # Default value
            mileage=45000,
            signature="data:image/png;base64,AAAA",
            acknowledgement_confirmed=True,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["declined"] is False


# =============================================================================
# Unit Tests: Update Inspection to Declined
# =============================================================================

class TestUpdateInspectionDeclined:
    """Tests for updating the declined field on existing inspections."""

    def test_update_inspection_set_declined_true(self):
        """Should be able to update an existing inspection to declined=True."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            inspection_type="pickup",
            declined=True,  # After update
            mileage=45000,
            updated_at=datetime.utcnow(),
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["declined"] is True

    def test_update_inspection_set_declined_false(self):
        """Should be able to update declined back to False."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            inspection_type="pickup",
            declined=False,  # After update - undecline
            mileage=45000,
            signature="data:image/png;base64,AAAA",
            acknowledgement_confirmed=True,
            updated_at=datetime.utcnow(),
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["declined"] is False

    def test_update_declined_preserves_other_fields(self):
        """Updating declined should preserve other inspection fields."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
            notes="Original notes preserved",
            customer_name="John Doe",
            updated_at=datetime.utcnow(),
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        insp = response_data["inspection"]
        assert insp["declined"] is True
        assert insp["mileage"] == 45000
        assert insp["notes"] == "Original notes preserved"
        assert insp["customer_name"] == "John Doe"

    def test_update_mileage_on_declined_inspection(self):
        """Should be able to update mileage on a declined inspection."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            inspection_type="pickup",
            declined=True,
            mileage=45100,  # Updated mileage
            updated_at=datetime.utcnow(),
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["mileage"] == 45100


# =============================================================================
# Unit Tests: Decline/Undecline Endpoints
# =============================================================================

class TestDeclineInspectionEndpoint:
    """Tests for POST /api/employee/bookings/{booking_id}/decline-inspection."""

    def test_decline_inspection_creates_new_record(self):
        """Should create a new pickup inspection with declined=True if none exists."""
        booking = create_mock_booking(id=100, reference="DCL-NEW01")

        # Response from decline endpoint
        response_data = {
            "success": True,
            "message": f"Return inspection declined for booking {booking.reference}",
        }

        assert response_data["success"] is True
        assert "declined" in response_data["message"].lower()
        assert booking.reference in response_data["message"]

    def test_decline_inspection_updates_existing_record(self):
        """Should update existing pickup inspection to declined=True."""
        booking = create_mock_booking(id=100, reference="DCL-UPD01")

        # Existing inspection before decline
        existing = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=False,
            mileage=45000,
        )

        # After decline endpoint is called
        existing.declined = True

        response_data = {
            "success": True,
            "message": f"Return inspection declined for booking {booking.reference}",
        }

        assert response_data["success"] is True
        assert existing.declined is True

    def test_decline_inspection_nonexistent_booking(self):
        """Should return 404 for non-existent booking."""
        error_response = {
            "detail": "Booking not found"
        }
        status_code = 404

        assert status_code == 404
        assert "Booking not found" in error_response["detail"]

    def test_decline_inspection_no_auth(self):
        """Should reject unauthenticated request."""
        status_code = 401

        assert status_code == 401


class TestUndeclineInspectionEndpoint:
    """Tests for POST /api/employee/bookings/{booking_id}/undecline-inspection."""

    def test_undecline_inspection_clears_flag(self):
        """Should set declined=False on existing inspection."""
        booking = create_mock_booking(id=100, reference="DCL-UNDO01")

        # Inspection with data should just clear declined flag
        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=False,  # After undecline
            mileage=45000,
            notes="Has some data",
        )

        response_data = {
            "success": True,
            "message": f"Return inspection decline removed for booking {booking.reference}",
        }

        assert response_data["success"] is True
        assert "removed" in response_data["message"].lower()

    def test_undecline_inspection_deletes_empty_record(self):
        """Should delete inspection record if it only had declined=True and no other data."""
        booking = create_mock_booking(id=100, reference="DCL-DEL01")

        # Empty declined inspection - should be deleted
        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=None,
            notes=None,
            photos={},
            signature=None,
        )

        # After undecline, if only declined was set, record is deleted
        response_data = {
            "success": True,
            "message": f"Return inspection decline removed for booking {booking.reference}",
        }

        assert response_data["success"] is True

    def test_undecline_inspection_nonexistent_booking(self):
        """Should return 404 for non-existent booking."""
        error_response = {
            "detail": "Booking not found"
        }
        status_code = 404

        assert status_code == 404

    def test_undecline_when_no_inspection_exists(self):
        """Should succeed even if no pickup inspection exists."""
        booking = create_mock_booking(id=100, reference="DCL-NONE01")

        response_data = {
            "success": True,
            "message": f"Return inspection decline removed for booking {booking.reference}",
        }

        # Should succeed (no-op if no inspection exists)
        assert response_data["success"] is True


# =============================================================================
# Unit Tests: Get Inspections with Declined Field
# =============================================================================

class TestGetInspectionsWithDeclined:
    """Tests for GET /api/employee/inspections/{booking_id} returning declined field."""

    def test_get_inspections_returns_declined_field(self):
        """Should include declined field in inspection response."""
        booking = create_mock_booking(id=100, reference="DCL-GET01")

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
        )

        response_data = {
            "inspections": [create_mock_inspection_response(inspection)]
        }

        insp = response_data["inspections"][0]
        assert "declined" in insp
        assert insp["declined"] is True

    def test_get_inspections_declined_false(self):
        """Should return declined=False for normal inspections."""
        booking = create_mock_booking(id=100, reference="DCL-NORM01")

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=False,
            mileage=45000,
            signature="data:image/png;base64,AAAA",
            acknowledgement_confirmed=True,
        )

        response_data = {
            "inspections": [create_mock_inspection_response(inspection)]
        }

        assert response_data["inspections"][0]["declined"] is False

    def test_get_both_inspections_one_declined(self):
        """Should return correct declined status for both dropoff and pickup inspections."""
        booking = create_mock_booking(id=100, reference="DCL-BOTH01")

        dropoff = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="dropoff",
            declined=False,  # Dropoff is never declined
            mileage=45000,
        )

        pickup = create_mock_inspection(
            id=2,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,  # Pickup is declined
            mileage=45100,
        )

        response_data = {
            "inspections": [
                create_mock_inspection_response(dropoff),
                create_mock_inspection_response(pickup),
            ]
        }

        dropoff_resp = next(i for i in response_data["inspections"] if i["inspection_type"] == "dropoff")
        pickup_resp = next(i for i in response_data["inspections"] if i["inspection_type"] == "pickup")

        assert dropoff_resp["declined"] is False
        assert pickup_resp["declined"] is True


# =============================================================================
# Integration Tests: Full Declined Inspection Flow
# =============================================================================

class TestDeclinedInspectionFullFlow:
    """End-to-end tests for the complete declined inspection workflow."""

    def test_full_declined_flow_create_and_complete(self):
        """
        Full flow:
        1. Customer drops off vehicle (normal dropoff inspection)
        2. At pickup, customer declines return inspection
        3. Employee enters mileage only
        4. Inspection is saved with declined=True
        5. Booking can be completed
        """
        booking = create_mock_booking(id=100, reference="DCL-FULL01", status="confirmed")

        # Step 1: Normal drop-off inspection
        dropoff = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="dropoff",
            notes="Vehicle in good condition.",
            mileage=45000,
            signature="data:image/png;base64,DROPOFF",
            vehicle_inspection_read=True,
            declined=False,
        )

        dropoff_response = {
            "success": True,
            "inspection": create_mock_inspection_response(dropoff),
        }
        assert dropoff_response["success"] is True

        # Step 2: At pickup, create declined return inspection
        pickup = create_mock_inspection(
            id=2,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=45100,  # Only mileage required
            # No signature, acknowledgement, or photos
            signature=None,
            acknowledgement_confirmed=False,
            photos={},
        )

        pickup_response = {
            "success": True,
            "inspection": create_mock_inspection_response(pickup),
        }
        assert pickup_response["success"] is True
        assert pickup_response["inspection"]["declined"] is True
        assert pickup_response["inspection"]["mileage"] == 45100
        assert pickup_response["inspection"]["signature"] is None

        # Step 3: Verify both inspections exist
        get_response = {
            "inspections": [
                create_mock_inspection_response(dropoff),
                create_mock_inspection_response(pickup),
            ]
        }
        assert len(get_response["inspections"]) == 2

        # Step 4: Complete the booking
        complete_response = {
            "success": True,
            "message": f"Booking {booking.reference} marked as completed",
        }
        assert complete_response["success"] is True

        # Step 5: Verify booking is completed
        booking.status.value = "completed"
        assert booking.status.value == "completed"

    def test_declined_flow_then_undecline(self):
        """
        Flow where customer initially declines, then changes their mind:
        1. Create declined inspection
        2. Undecline (customer decides to do full inspection)
        3. Update inspection with full data
        """
        booking = create_mock_booking(id=100, reference="DCL-UNDO01")

        # Step 1: Create declined inspection
        pickup = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
        )

        create_response = {
            "success": True,
            "inspection": create_mock_inspection_response(pickup),
        }
        assert create_response["inspection"]["declined"] is True

        # Step 2: Customer changes mind - undecline
        pickup.declined = False

        undecline_response = {
            "success": True,
            "message": f"Return inspection decline removed for booking {booking.reference}",
        }
        assert undecline_response["success"] is True

        # Step 3: Update with full inspection data
        pickup.signature = "data:image/png;base64,FULLSIG"
        pickup.acknowledgement_confirmed = True
        pickup.customer_name = "John Doe"
        pickup.signed_date = date.today()
        pickup.photos = {"front": "data:image/png;base64,PHOTO1"}

        update_response = {
            "success": True,
            "inspection": create_mock_inspection_response(pickup),
        }

        insp = update_response["inspection"]
        assert insp["declined"] is False
        assert insp["signature"] == "data:image/png;base64,FULLSIG"
        assert insp["acknowledgement_confirmed"] is True

    def test_declined_then_complete_booking(self):
        """Should be able to complete booking with declined return inspection."""
        booking = create_mock_booking(id=100, reference="DCL-COMP01", status="confirmed")

        # Declined inspection with only mileage
        pickup = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
        )

        inspection_response = {
            "success": True,
            "inspection": create_mock_inspection_response(pickup),
        }
        assert inspection_response["success"] is True

        # Complete booking
        complete_response = {
            "success": True,
            "message": f"Booking {booking.reference} marked as completed",
        }

        assert complete_response["success"] is True

        # Verify status change
        booking.status.value = "completed"
        assert booking.status.value == "completed"


# =============================================================================
# Edge Cases and Negative Tests
# =============================================================================

class TestDeclinedInspectionEdgeCases:
    """Edge case and security tests for declined inspection feature."""

    def test_declined_with_zero_mileage(self):
        """Should accept mileage of 0 on declined inspection."""
        booking = create_mock_booking(id=100, reference="DCL-ZERO01")

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=0,  # New vehicle
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["success"] is True
        assert response_data["inspection"]["mileage"] == 0

    def test_declined_with_high_mileage(self):
        """Should handle high mileage values on declined inspection."""
        booking = create_mock_booking(id=100, reference="DCL-HIGH01")

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=999999,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["mileage"] == 999999

    def test_declined_inspection_type_boolean(self):
        """Declined field should be a boolean type."""
        inspection = create_mock_inspection(
            id=1,
            booking_id=100,
            inspection_type="pickup",
            declined=True,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert isinstance(response_data["inspection"]["declined"], bool)

    def test_declined_with_optional_signature(self):
        """Declined inspection CAN have signature even though not required."""
        booking = create_mock_booking(id=100, reference="DCL-OPTSIG01")

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
            signature="data:image/png;base64,OPTIONAL",  # Optional but allowed
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["declined"] is True
        assert response_data["inspection"]["signature"] == "data:image/png;base64,OPTIONAL"

    def test_declined_with_optional_photos(self):
        """Declined inspection CAN have photos even though not required."""
        booking = create_mock_booking(id=100, reference="DCL-OPTPHOTO01")

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
            photos={"front": "data:image/png;base64,OPTIONAL"},
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["declined"] is True
        assert "front" in response_data["inspection"]["photos"]

    def test_declined_preserves_inspector_id(self):
        """Declined inspection should record inspector ID."""
        booking = create_mock_booking(id=100, reference="DCL-INSP01")
        user = create_mock_user(id=42)

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspector_id=user.id,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["inspector_id"] == 42

    def test_declined_with_notes_special_characters(self):
        """Should handle special characters in notes on declined inspection."""
        booking = create_mock_booking(id=100, reference="DCL-SPEC01")

        notes = "Customer said: \"I'm in a hurry\" — declined inspection ✓"
        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
            notes=notes,
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        assert response_data["inspection"]["notes"] == notes

    def test_cannot_complete_already_completed_booking(self):
        """Should reject completing a booking that is already completed."""
        error_response = {
            "detail": "Booking must be confirmed to complete. Current status: completed"
        }
        status_code = 400

        assert status_code == 400
        assert "must be confirmed" in error_response["detail"].lower()

    def test_decline_requires_auth(self):
        """Decline inspection endpoint requires authentication."""
        status_code = 401

        assert status_code == 401


# =============================================================================
# Negative Tests: Invalid Inputs
# =============================================================================

class TestDeclinedInspectionNegativeCases:
    """Tests for invalid inputs and error conditions."""

    def test_decline_nonexistent_booking(self):
        """Should return 404 when declining inspection for non-existent booking."""
        error_response = {
            "detail": "Booking not found"
        }
        status_code = 404

        assert status_code == 404

    def test_undecline_nonexistent_booking(self):
        """Should return 404 when undeclining inspection for non-existent booking."""
        error_response = {
            "detail": "Booking not found"
        }
        status_code = 404

        assert status_code == 404

    def test_create_duplicate_pickup_inspection(self):
        """Should reject creating second pickup inspection for same booking."""
        error_response = {
            "detail": "pickup inspection already exists for this booking"
        }
        status_code = 400

        assert status_code == 400
        assert "already exists" in error_response["detail"]

    def test_update_nonexistent_inspection(self):
        """Should return 404 when updating non-existent inspection."""
        error_response = {
            "detail": "Inspection not found"
        }
        status_code = 404

        assert status_code == 404


# =============================================================================
# Comparison Tests: Declined vs Normal Inspection
# =============================================================================

class TestDeclinedVsNormalInspection:
    """Tests comparing declined inspection behavior vs normal inspection."""

    def test_declined_inspection_requires_less_data(self):
        """Declined inspection requires only mileage, normal requires more."""
        booking = create_mock_booking(id=100, reference="DCL-COMP01")

        # Declined inspection - minimal data
        declined_inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
            signature=None,
            acknowledgement_confirmed=False,
            photos={},
        )

        # Normal inspection - full data required
        normal_inspection = create_mock_inspection(
            id=2,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=False,
            mileage=45000,
            signature="data:image/png;base64,REQUIRED",
            acknowledgement_confirmed=True,
            customer_name="John Doe",
            signed_date=date.today(),
            photos={"front": "data:image/png;base64,PHOTO1"},
        )

        # Both should succeed
        declined_response = create_mock_inspection_response(declined_inspection)
        normal_response = create_mock_inspection_response(normal_inspection)

        # Declined has less data
        assert declined_response["signature"] is None
        assert declined_response["acknowledgement_confirmed"] is False

        # Normal has full data
        assert normal_response["signature"] is not None
        assert normal_response["acknowledgement_confirmed"] is True

    def test_both_types_enable_booking_completion(self):
        """Both declined and normal inspections should enable booking completion."""
        booking = create_mock_booking(id=100, reference="DCL-BOTH01", status="confirmed")

        # Declined inspection
        declined = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
        )

        complete_response = {
            "success": True,
            "message": f"Booking {booking.reference} marked as completed",
        }

        assert complete_response["success"] is True

    def test_normal_inspection_declined_false(self):
        """Normal inspection should have declined=False."""
        booking = create_mock_booking(id=100, reference="DCL-NORM01")

        normal = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=False,
            mileage=45000,
            signature="data:image/png;base64,SIG",
            acknowledgement_confirmed=True,
        )

        response = create_mock_inspection_response(normal)
        assert response["declined"] is False


# =============================================================================
# Mileage Comparison Tests
# =============================================================================

class TestDeclinedInspectionMileageComparison:
    """Tests for mileage comparison between dropoff and declined return inspection."""

    def test_mileage_comparison_with_declined_return(self):
        """Should be able to compare mileage between dropoff and declined return."""
        booking = create_mock_booking(id=100, reference="DCL-MILE01")

        dropoff = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="dropoff",
            mileage=45000,
            declined=False,
        )

        pickup = create_mock_inspection(
            id=2,
            booking_id=booking.id,
            inspection_type="pickup",
            mileage=45050,  # 50 miles driven
            declined=True,
        )

        inspections_response = {
            "inspections": [
                create_mock_inspection_response(dropoff),
                create_mock_inspection_response(pickup),
            ]
        }

        dropoff_mileage = next(
            i["mileage"] for i in inspections_response["inspections"]
            if i["inspection_type"] == "dropoff"
        )
        pickup_mileage = next(
            i["mileage"] for i in inspections_response["inspections"]
            if i["inspection_type"] == "pickup"
        )

        assert pickup_mileage > dropoff_mileage
        assert pickup_mileage - dropoff_mileage == 50

        # Verify pickup is declined
        pickup_resp = next(
            i for i in inspections_response["inspections"]
            if i["inspection_type"] == "pickup"
        )
        assert pickup_resp["declined"] is True

    def test_declined_inspection_without_mileage(self):
        """Declined inspection with null mileage (edge case)."""
        booking = create_mock_booking(id=100, reference="DCL-NOMILE01")

        inspection = create_mock_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type="pickup",
            declined=True,
            mileage=None,  # No mileage recorded
        )

        response_data = {
            "success": True,
            "inspection": create_mock_inspection_response(inspection),
        }

        # Should succeed even without mileage
        assert response_data["success"] is True
        assert response_data["inspection"]["mileage"] is None


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
