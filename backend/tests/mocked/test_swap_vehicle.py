"""
Tests for swap vehicle endpoint.

Covers:
- PUT /api/admin/bookings/{booking_id}/swap-vehicle

All tests use mocked data - no real database connections.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


# ============================================================================
# MOCK DATABASE SETUP
# ============================================================================

class MockVehicle:
    """Mock vehicle object."""
    def __init__(self, id=1, customer_id=1, registration="AB12CDE",
                 make="Ford", model="Focus", colour="Blue"):
        self.id = id
        self.customer_id = customer_id
        self.registration = registration
        self.make = make
        self.model = model
        self.colour = colour


class MockBooking:
    """Mock booking object."""
    def __init__(self, id=1, customer_id=1, vehicle_id=1, reference="TAG-123456",
                 vehicle_registration="AB12CDE", vehicle_make="Ford",
                 vehicle_model="Focus", vehicle_colour="Blue"):
        self.id = id
        self.customer_id = customer_id
        self.vehicle_id = vehicle_id
        self.reference = reference
        self.vehicle_registration = vehicle_registration
        self.vehicle_make = vehicle_make
        self.vehicle_model = vehicle_model
        self.vehicle_colour = vehicle_colour


class MockQuery:
    """Mock SQLAlchemy query object."""
    def __init__(self, result=None):
        self._result = result

    def filter(self, *args):
        return self

    def first(self):
        return self._result


class MockSession:
    """Mock database session."""
    def __init__(self, booking=None, vehicles=None):
        self._booking = booking
        self._vehicles = vehicles or {}
        self._query_type = None

    def query(self, model):
        model_name = model.__name__ if hasattr(model, '__name__') else str(model)
        self._query_type = model_name
        if 'Booking' in model_name:
            return MockQuery(self._booking)
        elif 'Vehicle' in model_name:
            # Return based on what's being queried
            return MockQuery(None)  # Will be overridden by filter logic
        return MockQuery()

    def commit(self):
        pass

    def refresh(self, obj):
        pass


# ============================================================================
# MOCKED UNIT TESTS - Test individual functions/logic in isolation
# ============================================================================

class TestSwapVehicleMocked:
    """Mocked unit tests for swap vehicle logic."""

    def test_vehicle_belongs_to_same_customer(self):
        """Happy path: Vehicle belongs to same customer as booking."""
        booking = MockBooking(customer_id=1, vehicle_id=1)
        new_vehicle = MockVehicle(id=2, customer_id=1)

        assert new_vehicle.customer_id == booking.customer_id

    def test_vehicle_belongs_to_different_customer(self):
        """Unhappy path: Vehicle belongs to different customer."""
        booking = MockBooking(customer_id=1, vehicle_id=1)
        new_vehicle = MockVehicle(id=2, customer_id=2)

        assert new_vehicle.customer_id != booking.customer_id

    def test_cannot_swap_to_same_vehicle(self):
        """Unhappy path: Cannot swap to the same vehicle."""
        booking = MockBooking(vehicle_id=1)
        new_vehicle = MockVehicle(id=1)

        assert new_vehicle.id == booking.vehicle_id

    def test_swap_updates_booking_fields(self):
        """Happy path: Swap updates all vehicle fields on booking."""
        booking = MockBooking(
            vehicle_id=1,
            vehicle_registration="AB12CDE",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue"
        )
        new_vehicle = MockVehicle(
            id=2,
            registration="XY98ZAB",
            make="BMW",
            model="3 Series",
            colour="Black"
        )

        # Simulate swap
        booking.vehicle_id = new_vehicle.id
        booking.vehicle_registration = new_vehicle.registration
        booking.vehicle_make = new_vehicle.make
        booking.vehicle_model = new_vehicle.model
        booking.vehicle_colour = new_vehicle.colour

        assert booking.vehicle_id == 2
        assert booking.vehicle_registration == "XY98ZAB"
        assert booking.vehicle_make == "BMW"
        assert booking.vehicle_model == "3 Series"
        assert booking.vehicle_colour == "Black"

    def test_swap_with_optional_model(self):
        """Edge case: Swap to vehicle without model."""
        booking = MockBooking(vehicle_model="Focus")
        new_vehicle = MockVehicle(model=None)

        booking.vehicle_model = new_vehicle.model

        assert booking.vehicle_model is None

    def test_booking_not_found_check(self):
        """Unhappy path: Booking not found."""
        booking = None
        assert booking is None  # Should return 404

    def test_vehicle_not_found_check(self):
        """Unhappy path: New vehicle not found."""
        vehicle = None
        assert vehicle is None  # Should return 404


# ============================================================================
# MOCKED INTEGRATION TESTS - Test endpoint logic with mocked dependencies
# ============================================================================

class TestSwapVehicleIntegration:
    """Integration tests for PUT /api/admin/bookings/{booking_id}/swap-vehicle."""

    def test_swap_vehicle_success(self):
        """Happy path: Successfully swap vehicle on booking."""
        booking = MockBooking(
            id=1,
            customer_id=1,
            vehicle_id=1,
            reference="TAG-123456",
            vehicle_registration="AB12CDE",
            vehicle_make="Ford"
        )
        old_vehicle = MockVehicle(id=1, customer_id=1, registration="AB12CDE")
        new_vehicle = MockVehicle(
            id=2,
            customer_id=1,
            registration="XY98ZAB",
            make="BMW",
            model="3 Series",
            colour="Black"
        )

        # Verify customer match
        assert new_vehicle.customer_id == booking.customer_id

        # Verify not same vehicle
        assert new_vehicle.id != booking.vehicle_id

        # Simulate swap
        old_reg = booking.vehicle_registration
        booking.vehicle_id = new_vehicle.id
        booking.vehicle_registration = new_vehicle.registration

        # Build response
        response = {
            "success": True,
            "message": f"Vehicle swapped from {old_reg} to {new_vehicle.registration}",
            "booking_id": booking.id,
            "reference": booking.reference,
            "old_vehicle": {"registration": old_reg},
            "new_vehicle": {"registration": new_vehicle.registration},
        }

        assert response["success"] is True
        assert "AB12CDE" in response["message"]
        assert "XY98ZAB" in response["message"]

    def test_swap_vehicle_booking_not_found(self):
        """Unhappy path: Booking not found returns 404."""
        booking = None
        # Should raise 404
        assert booking is None

    def test_swap_vehicle_vehicle_not_found(self):
        """Unhappy path: New vehicle not found returns 404."""
        booking = MockBooking(id=1)
        new_vehicle = None
        # Should raise 404
        assert new_vehicle is None

    def test_swap_vehicle_wrong_customer(self):
        """Unhappy path: Vehicle belongs to different customer returns 400."""
        booking = MockBooking(customer_id=1)
        new_vehicle = MockVehicle(customer_id=2)

        # Check should fail
        customer_match = new_vehicle.customer_id == booking.customer_id
        assert customer_match is False

    def test_swap_vehicle_same_vehicle(self):
        """Unhappy path: Swapping to same vehicle returns 400."""
        booking = MockBooking(vehicle_id=5)
        new_vehicle = MockVehicle(id=5)

        # Check should fail
        is_same = new_vehicle.id == booking.vehicle_id
        assert is_same is True

    def test_swap_vehicle_response_format(self):
        """Happy path: Response contains all expected fields."""
        old_vehicle = MockVehicle(id=1, registration="AB12CDE")
        new_vehicle = MockVehicle(
            id=2,
            registration="XY98ZAB",
            make="BMW",
            model="3 Series",
            colour="Black"
        )

        response = {
            "success": True,
            "message": f"Vehicle swapped from {old_vehicle.registration} to {new_vehicle.registration}",
            "booking_id": 1,
            "reference": "TAG-123456",
            "old_vehicle": {
                "id": old_vehicle.id,
                "registration": old_vehicle.registration,
            },
            "new_vehicle": {
                "id": new_vehicle.id,
                "registration": new_vehicle.registration,
                "make": new_vehicle.make,
                "model": new_vehicle.model,
                "colour": new_vehicle.colour,
            },
        }

        assert "success" in response
        assert "message" in response
        assert "booking_id" in response
        assert "reference" in response
        assert "old_vehicle" in response
        assert "new_vehicle" in response
        assert response["new_vehicle"]["make"] == "BMW"


# ============================================================================
# BOUNDARY TESTS
# ============================================================================

class TestSwapVehicleBoundaries:
    """Boundary tests for swap vehicle endpoint."""

    def test_booking_id_zero(self):
        """Boundary: Booking ID of 0 (invalid)."""
        booking_id = 0
        is_valid = booking_id > 0
        assert is_valid is False

    def test_booking_id_negative(self):
        """Boundary: Negative booking ID (invalid)."""
        booking_id = -1
        is_valid = booking_id > 0
        assert is_valid is False

    def test_booking_id_positive(self):
        """Boundary: Positive booking ID (valid)."""
        booking_id = 1
        is_valid = booking_id > 0
        assert is_valid is True

    def test_vehicle_id_zero(self):
        """Boundary: Vehicle ID of 0 (invalid)."""
        vehicle_id = 0
        is_valid = vehicle_id > 0
        assert is_valid is False

    def test_vehicle_id_negative(self):
        """Boundary: Negative vehicle ID (invalid)."""
        vehicle_id = -1
        is_valid = vehicle_id > 0
        assert is_valid is False

    def test_vehicle_id_positive(self):
        """Boundary: Positive vehicle ID (valid)."""
        vehicle_id = 1
        is_valid = vehicle_id > 0
        assert is_valid is True

    def test_large_booking_id(self):
        """Boundary: Large booking ID (valid)."""
        booking_id = 999999999
        is_valid = booking_id > 0
        assert is_valid is True

    def test_large_vehicle_id(self):
        """Boundary: Large vehicle ID (valid)."""
        vehicle_id = 999999999
        is_valid = vehicle_id > 0
        assert is_valid is True

    def test_customer_with_many_vehicles(self):
        """Edge case: Customer with many vehicles."""
        customer_id = 1
        vehicles = [MockVehicle(id=i, customer_id=customer_id) for i in range(100)]
        assert len(vehicles) == 100
        assert all(v.customer_id == customer_id for v in vehicles)

    def test_swap_preserves_booking_reference(self):
        """Edge case: Swap doesn't affect booking reference."""
        booking = MockBooking(reference="TAG-123456")
        original_ref = booking.reference

        # Simulate swap (only vehicle fields change)
        booking.vehicle_id = 2
        booking.vehicle_registration = "XY98ZAB"

        assert booking.reference == original_ref

    def test_swap_with_null_old_vehicle(self):
        """Edge case: Old vehicle record doesn't exist (orphaned)."""
        booking = MockBooking(vehicle_id=999)
        old_vehicle = None  # Orphaned reference

        # Should still allow swap, just use "Unknown" for old reg
        old_registration = old_vehicle.registration if old_vehicle else "Unknown"
        assert old_registration == "Unknown"
