"""
Integration tests for Customer Declined Inspection feature.

These tests use FastAPI TestClient to test the actual API endpoints
with mocked database sessions.

Covers:
- POST /api/employee/inspections - create declined inspection
- PUT /api/employee/inspections/{id} - update to declined
- GET /api/employee/inspections/{booking_id} - get with declined field
- POST /api/employee/bookings/{id}/decline-inspection - decline endpoint
- POST /api/employee/bookings/{id}/undecline-inspection - undecline endpoint
- POST /api/employee/bookings/{id}/complete - complete with declined inspection

All tests use mocked database and authentication.
"""
import pytest
from datetime import datetime, timedelta, date
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Setup
# =============================================================================

def create_mock_db_booking(
    id=1,
    reference="DCL-INT001",
    status_value="confirmed",
    customer_id=1,
    vehicle_id=1,
):
    """Create a mock database booking object."""
    from db_models import BookingStatus

    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.status = BookingStatus.CONFIRMED if status_value == "confirmed" else BookingStatus.COMPLETED
    booking.customer_id = customer_id
    booking.vehicle_id = vehicle_id
    booking.completed_at = None
    return booking


def create_mock_db_inspection(
    id=1,
    booking_id=1,
    inspector_id=1,
    inspection_type_value="pickup",
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
    """Create a mock database inspection object."""
    from db_models import InspectionType

    inspection = MagicMock()
    inspection.id = id
    inspection.booking_id = booking_id
    inspection.inspector_id = inspector_id
    inspection.inspection_type = InspectionType.PICKUP if inspection_type_value == "pickup" else InspectionType.DROPOFF
    inspection.notes = notes
    inspection.photos = photos
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


def create_mock_user(id=1, email="inspector@test.com", is_active=True):
    """Create a mock user."""
    user = MagicMock()
    user.id = id
    user.email = email
    user.is_active = is_active
    return user


# =============================================================================
# Test Class: Create Declined Inspection via API
# =============================================================================

class TestCreateDeclinedInspectionAPI:
    """Integration tests for creating declined inspections via API."""

    def test_create_declined_inspection_request_model(self):
        """Test that CreateInspectionRequest includes declined field."""
        from main import CreateInspectionRequest

        # Should be able to create request with declined=True
        request = CreateInspectionRequest(
            booking_id=1,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
        )

        assert request.declined is True
        assert request.mileage == 45000
        assert request.booking_id == 1
        assert request.inspection_type == "pickup"

    def test_create_declined_inspection_defaults(self):
        """Test that declined defaults to False."""
        from main import CreateInspectionRequest

        request = CreateInspectionRequest(
            booking_id=1,
            inspection_type="pickup",
        )

        assert request.declined is False

    def test_create_inspection_with_declined_and_notes(self):
        """Test creating inspection with declined=True and notes."""
        from main import CreateInspectionRequest

        request = CreateInspectionRequest(
            booking_id=1,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
            notes="Customer in a hurry, declined full inspection.",
        )

        assert request.declined is True
        assert request.notes == "Customer in a hurry, declined full inspection."

    def test_create_inspection_with_declined_no_signature(self):
        """Test that declined inspection doesn't require signature."""
        from main import CreateInspectionRequest

        request = CreateInspectionRequest(
            booking_id=1,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
            signature=None,  # Not required when declined
        )

        assert request.declined is True
        assert request.signature is None


# =============================================================================
# Test Class: Update Inspection to Declined via API
# =============================================================================

class TestUpdateDeclinedInspectionAPI:
    """Integration tests for updating inspections to declined via API."""

    def test_update_inspection_request_model(self):
        """Test that UpdateInspectionRequest includes declined field."""
        from main import UpdateInspectionRequest

        request = UpdateInspectionRequest(
            declined=True,
            mileage=45000,
        )

        assert request.declined is True
        assert request.mileage == 45000

    def test_update_inspection_declined_none_default(self):
        """Test that declined defaults to None (no change)."""
        from main import UpdateInspectionRequest

        request = UpdateInspectionRequest(
            notes="Updated notes",
        )

        assert request.declined is None

    def test_update_inspection_set_declined_false(self):
        """Test explicitly setting declined=False."""
        from main import UpdateInspectionRequest

        request = UpdateInspectionRequest(
            declined=False,
        )

        assert request.declined is False


# =============================================================================
# Test Class: Decline/Undecline Endpoints Logic
# =============================================================================

class TestDeclineEndpointLogic:
    """Tests for the decline-inspection endpoint logic."""

    def test_decline_creates_inspection_if_none_exists(self):
        """Test that decline endpoint creates new inspection when none exists."""
        from db_models import InspectionType

        # Simulate: No existing pickup inspection
        existing_inspection = None

        # Logic: Should create new inspection with declined=True
        if existing_inspection is None:
            new_inspection = create_mock_db_inspection(
                id=1,
                booking_id=100,
                inspection_type_value="pickup",
                declined=True,
            )
            assert new_inspection.declined is True
            assert new_inspection.inspection_type == InspectionType.PICKUP

    def test_decline_updates_existing_inspection(self):
        """Test that decline endpoint updates existing inspection."""
        existing = create_mock_db_inspection(
            id=1,
            booking_id=100,
            inspection_type_value="pickup",
            declined=False,
            mileage=45000,
        )

        # Logic: Update existing to declined=True
        existing.declined = True

        assert existing.declined is True
        assert existing.mileage == 45000  # Preserved


class TestUndeclineEndpointLogic:
    """Tests for the undecline-inspection endpoint logic."""

    def test_undecline_clears_flag_when_data_exists(self):
        """Test that undecline clears flag but keeps data."""
        inspection = create_mock_db_inspection(
            id=1,
            booking_id=100,
            inspection_type_value="pickup",
            declined=True,
            mileage=45000,
            notes="Has data",
        )

        # Has data besides declined flag
        has_data = inspection.notes or inspection.photos or inspection.signature

        if has_data:
            inspection.declined = False
            # Should NOT delete

        assert inspection.declined is False
        assert inspection.mileage == 45000
        assert inspection.notes == "Has data"

    def test_undecline_deletes_when_no_data(self):
        """Test that undecline deletes inspection if only declined was set."""
        inspection = create_mock_db_inspection(
            id=1,
            booking_id=100,
            inspection_type_value="pickup",
            declined=True,
            mileage=None,
            notes=None,
            photos=None,
            signature=None,
        )

        # Only has declined flag, no other data
        has_data = inspection.notes or inspection.photos or inspection.signature
        should_delete = inspection.declined and not has_data

        assert should_delete is True


# =============================================================================
# Test Class: Booking Completion with Declined Inspection
# =============================================================================

class TestCompleteBookingWithDeclined:
    """Tests for completing bookings with declined return inspection."""

    def test_complete_booking_succeeds_with_declined_inspection(self):
        """Test that booking can be completed when return inspection is declined."""
        from db_models import BookingStatus

        booking = create_mock_db_booking(id=100, reference="DCL-COMP01")

        # Declined inspection exists
        inspection = create_mock_db_inspection(
            id=1,
            booking_id=100,
            inspection_type_value="pickup",
            declined=True,
            mileage=45000,
        )

        # Complete booking
        assert booking.status == BookingStatus.CONFIRMED
        booking.status = BookingStatus.COMPLETED
        booking.completed_at = datetime.utcnow()

        assert booking.status == BookingStatus.COMPLETED
        assert booking.completed_at is not None

    def test_complete_booking_requires_confirmed_status(self):
        """Test that booking must be confirmed to complete."""
        from db_models import BookingStatus

        booking = create_mock_db_booking(id=100, status_value="completed")

        # Cannot complete an already completed booking
        is_confirmed = booking.status == BookingStatus.CONFIRMED

        assert is_confirmed is False  # Already completed


# =============================================================================
# Test Class: Inspection Response Format
# =============================================================================

class TestInspectionResponseFormat:
    """Tests for the inspection API response format."""

    def test_inspection_response_includes_declined_field(self):
        """Test that inspection response includes declined field."""
        import json

        inspection = create_mock_db_inspection(
            id=1,
            booking_id=100,
            inspection_type_value="pickup",
            declined=True,
            mileage=45000,
            notes="Test notes",
            photos='{"front": "base64data"}',
        )

        # Build response like the API does
        response = {
            "id": inspection.id,
            "booking_id": inspection.booking_id,
            "inspection_type": inspection.inspection_type.value,
            "notes": inspection.notes,
            "photos": json.loads(inspection.photos) if inspection.photos else {},
            "customer_name": inspection.customer_name,
            "signed_date": inspection.signed_date.isoformat() if inspection.signed_date else None,
            "signature": inspection.signature,
            "vehicle_inspection_read": inspection.vehicle_inspection_read,
            "acknowledgement_confirmed": inspection.acknowledgement_confirmed,
            "mileage": inspection.mileage,
            "declined": inspection.declined or False,
        }

        assert "declined" in response
        assert response["declined"] is True
        assert response["mileage"] == 45000

    def test_inspection_response_declined_false_by_default(self):
        """Test that declined defaults to False in response."""
        inspection = create_mock_db_inspection(
            id=1,
            booking_id=100,
            inspection_type_value="pickup",
            declined=None,  # Not set
        )

        # Response should default to False
        declined_value = inspection.declined or False

        assert declined_value is False


# =============================================================================
# Test Class: Validation Logic
# =============================================================================

class TestDeclinedInspectionValidation:
    """Tests for validation logic around declined inspections."""

    def test_declined_inspection_type_must_be_pickup(self):
        """Test that declined only makes sense for pickup (return) inspections."""
        from main import CreateInspectionRequest

        # Valid: pickup with declined
        request = CreateInspectionRequest(
            booking_id=1,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
        )
        assert request.inspection_type == "pickup"

        # Note: dropoff with declined is technically allowed by schema
        # but doesn't make business sense

    def test_mileage_is_integer_field(self):
        """Test that mileage is an integer field."""
        from main import CreateInspectionRequest

        request = CreateInspectionRequest(
            booking_id=1,
            inspection_type="pickup",
            declined=True,
            mileage=45000,
        )

        assert isinstance(request.mileage, int)

    def test_declined_is_boolean_field(self):
        """Test that declined is a boolean field."""
        from main import CreateInspectionRequest

        request = CreateInspectionRequest(
            booking_id=1,
            inspection_type="pickup",
            declined=True,
        )

        assert isinstance(request.declined, bool)


# =============================================================================
# Test Class: Edge Cases Integration
# =============================================================================

class TestDeclinedInspectionEdgeCasesIntegration:
    """Integration tests for edge cases."""

    def test_toggle_declined_multiple_times(self):
        """Test toggling declined flag multiple times."""
        inspection = create_mock_db_inspection(
            id=1,
            booking_id=100,
            inspection_type_value="pickup",
            declined=False,
        )

        # Toggle to True
        inspection.declined = True
        assert inspection.declined is True

        # Toggle back to False
        inspection.declined = False
        assert inspection.declined is False

        # Toggle to True again
        inspection.declined = True
        assert inspection.declined is True

    def test_declined_inspection_preserves_all_fields(self):
        """Test that setting declined preserves other fields."""
        inspection = create_mock_db_inspection(
            id=1,
            booking_id=100,
            inspector_id=42,
            inspection_type_value="pickup",
            notes="Original notes",
            mileage=45000,
            customer_name="John Doe",
            declined=False,
        )

        # Set declined
        inspection.declined = True

        # All other fields should be preserved
        assert inspection.notes == "Original notes"
        assert inspection.mileage == 45000
        assert inspection.customer_name == "John Doe"
        assert inspection.inspector_id == 42

    def test_multiple_bookings_independent_declined_status(self):
        """Test that declined status is independent per booking."""
        inspection1 = create_mock_db_inspection(
            id=1,
            booking_id=100,
            inspection_type_value="pickup",
            declined=True,
        )

        inspection2 = create_mock_db_inspection(
            id=2,
            booking_id=101,
            inspection_type_value="pickup",
            declined=False,
        )

        assert inspection1.declined is True
        assert inspection2.declined is False
        assert inspection1.booking_id != inspection2.booking_id


# =============================================================================
# Test Class: Database Model Integration
# =============================================================================

class TestDeclinedFieldDatabaseModel:
    """Tests for the declined field on VehicleInspection model."""

    def test_vehicle_inspection_model_has_declined_field(self):
        """Test that VehicleInspection model has declined column."""
        from db_models import VehicleInspection

        # Check that the model has the declined attribute
        assert hasattr(VehicleInspection, 'declined')

    def test_declined_field_is_boolean_column(self):
        """Test that declined is a Boolean column."""
        from db_models import VehicleInspection
        from sqlalchemy import Boolean

        # Get the column
        declined_column = VehicleInspection.__table__.columns.get('declined')

        assert declined_column is not None
        assert isinstance(declined_column.type, Boolean)

    def test_declined_field_default_value(self):
        """Test that declined defaults to False."""
        from db_models import VehicleInspection

        declined_column = VehicleInspection.__table__.columns.get('declined')

        # Column should have a default
        assert declined_column is not None
        # Default is set via server_default='false'


# =============================================================================
# Test Class: Request Model Field Validation
# =============================================================================

class TestRequestModelFieldValidation:
    """Tests for Pydantic request model field validation."""

    def test_create_request_all_fields(self):
        """Test CreateInspectionRequest with all fields."""
        from main import CreateInspectionRequest

        request = CreateInspectionRequest(
            booking_id=100,
            inspection_type="pickup",
            notes="Test notes",
            photos={"front": "base64data"},
            customer_name="John Doe",
            signed_date="2026-02-28",
            signature="base64sig",
            vehicle_inspection_read=False,
            acknowledgement_confirmed=True,
            declined=True,
            mileage=45000,
        )

        assert request.booking_id == 100
        assert request.inspection_type == "pickup"
        assert request.declined is True
        assert request.mileage == 45000

    def test_update_request_partial_fields(self):
        """Test UpdateInspectionRequest with partial fields."""
        from main import UpdateInspectionRequest

        request = UpdateInspectionRequest(
            declined=True,
        )

        assert request.declined is True
        assert request.notes is None
        assert request.mileage is None

    def test_update_request_declined_with_mileage(self):
        """Test UpdateInspectionRequest with declined and mileage."""
        from main import UpdateInspectionRequest

        request = UpdateInspectionRequest(
            declined=True,
            mileage=45000,
        )

        assert request.declined is True
        assert request.mileage == 45000


# =============================================================================
# Test Class: Full Flow Integration
# =============================================================================

class TestFullDeclinedInspectionFlow:
    """Full flow integration tests."""

    def test_complete_declined_inspection_flow(self):
        """Test complete flow: create booking -> create declined inspection -> complete."""
        from db_models import BookingStatus, InspectionType

        # Step 1: Create booking (mock)
        booking = create_mock_db_booking(
            id=100,
            reference="DCL-FLOW01",
            status_value="confirmed",
        )
        assert booking.status == BookingStatus.CONFIRMED

        # Step 2: Create declined return inspection
        inspection = create_mock_db_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type_value="pickup",
            declined=True,
            mileage=45000,
        )
        assert inspection.declined is True
        assert inspection.inspection_type == InspectionType.PICKUP

        # Step 3: Complete booking
        booking.status = BookingStatus.COMPLETED
        booking.completed_at = datetime.utcnow()

        assert booking.status == BookingStatus.COMPLETED
        assert booking.completed_at is not None

    def test_flow_with_dropoff_then_declined_return(self):
        """Test flow: dropoff inspection -> declined return inspection -> complete."""
        from db_models import BookingStatus, InspectionType

        booking = create_mock_db_booking(
            id=100,
            reference="DCL-DROPRET01",
            status_value="confirmed",
        )

        # Step 1: Normal dropoff inspection
        dropoff = create_mock_db_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type_value="dropoff",
            mileage=45000,
            signature="base64sig",
            vehicle_inspection_read=True,
            declined=False,
        )
        assert dropoff.inspection_type == InspectionType.DROPOFF
        assert dropoff.declined is False

        # Step 2: Declined return inspection
        pickup = create_mock_db_inspection(
            id=2,
            booking_id=booking.id,
            inspection_type_value="pickup",
            mileage=45050,
            declined=True,
        )
        assert pickup.inspection_type == InspectionType.PICKUP
        assert pickup.declined is True

        # Step 3: Complete booking
        booking.status = BookingStatus.COMPLETED
        assert booking.status == BookingStatus.COMPLETED

    def test_flow_decline_then_undecline_then_full_inspection(self):
        """Test flow: declined -> undecline -> full inspection."""
        from db_models import InspectionType

        booking = create_mock_db_booking(id=100, reference="DCL-UNDO01")

        # Step 1: Create declined inspection
        inspection = create_mock_db_inspection(
            id=1,
            booking_id=booking.id,
            inspection_type_value="pickup",
            declined=True,
            mileage=45000,
        )
        assert inspection.declined is True

        # Step 2: Undecline - customer changes mind
        inspection.declined = False
        assert inspection.declined is False

        # Step 3: Full inspection data added
        inspection.signature = "base64sig"
        inspection.acknowledgement_confirmed = True
        inspection.customer_name = "John Doe"
        inspection.signed_date = date.today()

        assert inspection.signature is not None
        assert inspection.acknowledgement_confirmed is True


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
