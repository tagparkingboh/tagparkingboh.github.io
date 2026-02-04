"""
Tests for vehicle inspection and booking completion endpoints.

Covers:
- POST /api/employee/inspections (create inspection)
- GET /api/employee/inspections/{booking_id} (get inspections)
- PUT /api/employee/inspections/{inspection_id} (update inspection)
- POST /api/employee/bookings/{booking_id}/complete (mark booking completed)
- Customer acknowledgement fields (customer_name, signed_date)
- Photo data (dict format with labeled slots)
- Authentication and authorization
- Edge cases and error handling
"""
import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timedelta, date
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def employee_user(db_session):
    """Create an employee user for inspection tests."""
    from db_models import User
    unique = uuid.uuid4().hex[:8]
    user = User(
        email=f"inspector-{unique}@tagparking.co.uk",
        first_name="Inspector",
        last_name="Test",
        is_admin=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    yield user
    # Cleanup: remove inspections referencing this user, then sessions, then user
    from db_models import VehicleInspection, Session as DbSession
    db_session.query(VehicleInspection).filter(VehicleInspection.inspector_id == user.id).delete()
    db_session.query(DbSession).filter(DbSession.user_id == user.id).delete()
    db_session.commit()
    db_session.delete(user)
    db_session.commit()


@pytest.fixture
def employee_session(db_session, employee_user):
    """Create a valid session for the employee user."""
    from db_models import Session as DbSession
    unique = uuid.uuid4().hex
    session = DbSession(
        user_id=employee_user.id,
        token=f"insp_test_{unique}",
        expires_at=datetime.utcnow() + timedelta(hours=8),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    yield session
    # Session cleanup handled by employee_user fixture


@pytest.fixture
def auth_headers(employee_session):
    """Return authorization headers for the employee."""
    return {"Authorization": f"Bearer {employee_session.token}"}


@pytest.fixture
def test_customer(db_session):
    """Create a test customer."""
    from db_models import Customer
    unique = uuid.uuid4().hex[:8]
    customer = Customer(
        first_name="John",
        last_name="TestInspection",
        email=f"john-insp-{unique}@example.com",
        phone="+447000000000",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    yield customer
    db_session.delete(customer)
    db_session.commit()


@pytest.fixture
def test_vehicle(db_session, test_customer):
    """Create a test vehicle."""
    from db_models import Vehicle
    vehicle = Vehicle(
        customer_id=test_customer.id,
        registration="TS23 INS",
        make="Toyota",
        model="Corolla",
        colour="Blue",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)
    yield vehicle
    db_session.delete(vehicle)
    db_session.commit()


@pytest.fixture
def confirmed_booking(db_session, test_customer, test_vehicle):
    """Create a confirmed booking for inspection tests."""
    from db_models import Booking, BookingStatus
    unique = uuid.uuid4().hex[:6].upper()
    booking = Booking(
        reference=f"INS-{unique}",
        customer_id=test_customer.id,
        vehicle_id=test_vehicle.id,
        customer_first_name="John",
        customer_last_name="TestInspection",
        status=BookingStatus.CONFIRMED,
        dropoff_date=date.today(),
        dropoff_time=datetime.strptime("10:00", "%H:%M").time(),
        pickup_date=date.today() + timedelta(days=7),
        pickup_time=datetime.strptime("14:00", "%H:%M").time(),
        dropoff_destination="Alicante",
        pickup_origin="Alicante",
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)
    yield booking
    # Cleanup inspections first (FK constraint), then booking
    from db_models import VehicleInspection
    db_session.query(VehicleInspection).filter(
        VehicleInspection.booking_id == booking.id
    ).delete()
    db_session.commit()
    db_session.delete(booking)
    db_session.commit()


@pytest.fixture
def completed_booking(db_session, test_customer, test_vehicle):
    """Create a completed booking."""
    from db_models import Booking, BookingStatus
    unique = uuid.uuid4().hex[:6].upper()
    booking = Booking(
        reference=f"CMP-{unique}",
        customer_id=test_customer.id,
        vehicle_id=test_vehicle.id,
        customer_first_name="John",
        customer_last_name="TestInspection",
        status=BookingStatus.COMPLETED,
        dropoff_date=date.today() - timedelta(days=7),
        dropoff_time=datetime.strptime("10:00", "%H:%M").time(),
        pickup_date=date.today(),
        pickup_time=datetime.strptime("14:00", "%H:%M").time(),
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)
    yield booking
    from db_models import VehicleInspection
    db_session.query(VehicleInspection).filter(
        VehicleInspection.booking_id == booking.id
    ).delete()
    db_session.commit()
    db_session.delete(booking)
    db_session.commit()


@pytest.fixture
def pending_booking(db_session, test_customer, test_vehicle):
    """Create a pending (unpaid) booking."""
    from db_models import Booking, BookingStatus
    unique = uuid.uuid4().hex[:6].upper()
    booking = Booking(
        reference=f"PND-{unique}",
        customer_id=test_customer.id,
        vehicle_id=test_vehicle.id,
        status=BookingStatus.PENDING,
        dropoff_date=date.today(),
        dropoff_time=datetime.strptime("10:00", "%H:%M").time(),
        pickup_date=date.today() + timedelta(days=7),
        pickup_time=datetime.strptime("14:00", "%H:%M").time(),
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)
    yield booking
    from db_models import VehicleInspection
    db_session.query(VehicleInspection).filter(
        VehicleInspection.booking_id == booking.id
    ).delete()
    db_session.commit()
    db_session.delete(booking)
    db_session.commit()


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


# =============================================================================
# Create Inspection Tests
# =============================================================================

class TestCreateInspection:
    """Tests for POST /api/employee/inspections."""

    @pytest.mark.asyncio
    async def test_create_dropoff_inspection_success(self, client, auth_headers, confirmed_booking):
        """Should create a drop-off inspection with notes and photos."""
        response = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "notes": "Minor scratch on front bumper. Otherwise good condition.",
                "photos": MOCK_PHOTOS,
                "customer_name": "John TestInspection",
                "signed_date": date.today().isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        insp = data["inspection"]
        assert insp["booking_id"] == confirmed_booking.id
        assert insp["inspection_type"] == "dropoff"
        assert insp["notes"] == "Minor scratch on front bumper. Otherwise good condition."
        assert insp["photos"]["front"] == MOCK_PHOTOS["front"]
        assert insp["photos"]["rear"] == MOCK_PHOTOS["rear"]
        assert insp["customer_name"] == "John TestInspection"
        assert insp["signed_date"] == date.today().isoformat()
        assert insp["created_at"] is not None

    @pytest.mark.asyncio
    async def test_create_pickup_inspection_success(self, client, auth_headers, confirmed_booking):
        """Should create a pick-up (return) inspection."""
        response = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "pickup",
                "notes": "Vehicle returned in same condition.",
                "photos": MOCK_PHOTOS_PARTIAL,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["inspection"]["inspection_type"] == "pickup"
        assert len(data["inspection"]["photos"]) == 2

    @pytest.mark.asyncio
    async def test_create_inspection_minimal(self, client, auth_headers, confirmed_booking):
        """Should create inspection with only required fields."""
        response = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["inspection"]["notes"] is None
        assert data["inspection"]["photos"] == {}
        assert data["inspection"]["customer_name"] is None
        assert data["inspection"]["signed_date"] is None

    @pytest.mark.asyncio
    async def test_create_duplicate_inspection_rejected(self, client, auth_headers, confirmed_booking):
        """Should reject creating a second inspection of the same type for the same booking."""
        # Create first
        await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "notes": "First inspection",
            },
        )

        # Try duplicate
        response = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "notes": "Duplicate attempt",
            },
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_both_inspection_types(self, client, auth_headers, confirmed_booking):
        """Should allow both dropoff and pickup inspections for the same booking."""
        resp1 = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "notes": "Drop-off inspection",
            },
        )
        assert resp1.status_code == 200

        resp2 = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "pickup",
                "notes": "Pick-up inspection",
            },
        )
        assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_create_inspection_invalid_type(self, client, auth_headers, confirmed_booking):
        """Should reject invalid inspection type."""
        response = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "midway",
                "notes": "Invalid type",
            },
        )

        assert response.status_code == 400
        assert "Invalid inspection type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_inspection_nonexistent_booking(self, client, auth_headers):
        """Should reject inspection for a booking that doesn't exist."""
        response = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": 999999,
                "inspection_type": "dropoff",
            },
        )

        assert response.status_code == 404
        assert "Booking not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_inspection_no_auth(self, client, confirmed_booking):
        """Should reject unauthenticated request."""
        response = await client.post(
            "/api/employee/inspections",
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_inspection_invalid_signed_date(self, client, auth_headers, confirmed_booking):
        """Should reject malformed signed_date."""
        response = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "signed_date": "not-a-date",
            },
        )

        assert response.status_code == 400
        assert "Invalid signed_date" in response.json()["detail"]


# =============================================================================
# Get Inspections Tests
# =============================================================================

class TestGetInspections:
    """Tests for GET /api/employee/inspections/{booking_id}."""

    @pytest.mark.asyncio
    async def test_get_inspections_returns_all(self, client, auth_headers, confirmed_booking):
        """Should return all inspections for a booking."""
        # Create both types
        await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "notes": "Drop-off notes",
                "photos": MOCK_PHOTOS,
                "customer_name": "John Smith",
                "signed_date": "2026-02-03",
            },
        )
        await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "pickup",
                "notes": "Pick-up notes",
            },
        )

        response = await client.get(
            f"/api/employee/inspections/{confirmed_booking.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["inspections"]) == 2

        types = {i["inspection_type"] for i in data["inspections"]}
        assert types == {"dropoff", "pickup"}

        # Verify dropoff has photos and customer acknowledgement
        dropoff = next(i for i in data["inspections"] if i["inspection_type"] == "dropoff")
        assert dropoff["photos"]["front"] == MOCK_PHOTOS["front"]
        assert dropoff["customer_name"] == "John Smith"
        assert dropoff["signed_date"] == "2026-02-03"

    @pytest.mark.asyncio
    async def test_get_inspections_empty(self, client, auth_headers, confirmed_booking):
        """Should return empty list when no inspections exist."""
        response = await client.get(
            f"/api/employee/inspections/{confirmed_booking.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["inspections"] == []

    @pytest.mark.asyncio
    async def test_get_inspections_no_auth(self, client, confirmed_booking):
        """Should reject unauthenticated request."""
        response = await client.get(
            f"/api/employee/inspections/{confirmed_booking.id}",
        )

        assert response.status_code == 401


# =============================================================================
# Update Inspection Tests
# =============================================================================

class TestUpdateInspection:
    """Tests for PUT /api/employee/inspections/{inspection_id}."""

    @pytest.mark.asyncio
    async def test_update_inspection_notes(self, client, auth_headers, confirmed_booking):
        """Should update inspection notes."""
        # Create first
        create_resp = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "notes": "Original notes",
            },
        )
        inspection_id = create_resp.json()["inspection"]["id"]

        # Update
        response = await client.put(
            f"/api/employee/inspections/{inspection_id}",
            headers=auth_headers,
            json={
                "notes": "Updated notes with more detail about scratches.",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["inspection"]["notes"] == "Updated notes with more detail about scratches."
        assert data["inspection"]["updated_at"] is not None

    @pytest.mark.asyncio
    async def test_update_inspection_photos(self, client, auth_headers, confirmed_booking):
        """Should update inspection photos."""
        create_resp = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "photos": MOCK_PHOTOS_PARTIAL,
            },
        )
        inspection_id = create_resp.json()["inspection"]["id"]

        # Update with full set of photos
        response = await client.put(
            f"/api/employee/inspections/{inspection_id}",
            headers=auth_headers,
            json={
                "photos": MOCK_PHOTOS,
            },
        )

        assert response.status_code == 200
        photos = response.json()["inspection"]["photos"]
        assert "front" in photos
        assert "rear" in photos
        assert "driver_side" in photos
        assert "passenger_side" in photos

    @pytest.mark.asyncio
    async def test_update_customer_acknowledgement(self, client, auth_headers, confirmed_booking):
        """Should update customer name and signed date."""
        create_resp = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
            },
        )
        inspection_id = create_resp.json()["inspection"]["id"]

        response = await client.put(
            f"/api/employee/inspections/{inspection_id}",
            headers=auth_headers,
            json={
                "customer_name": "Jane Doe",
                "signed_date": "2026-02-03",
            },
        )

        assert response.status_code == 200
        insp = response.json()["inspection"]
        assert insp["customer_name"] == "Jane Doe"
        assert insp["signed_date"] == "2026-02-03"

    @pytest.mark.asyncio
    async def test_update_inspection_not_found(self, client, auth_headers):
        """Should return 404 for non-existent inspection."""
        response = await client.put(
            "/api/employee/inspections/999999",
            headers=auth_headers,
            json={"notes": "Should fail"},
        )

        assert response.status_code == 404
        assert "Inspection not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_inspection_invalid_date(self, client, auth_headers, confirmed_booking):
        """Should reject invalid signed_date on update."""
        create_resp = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
            },
        )
        inspection_id = create_resp.json()["inspection"]["id"]

        response = await client.put(
            f"/api/employee/inspections/{inspection_id}",
            headers=auth_headers,
            json={"signed_date": "31/02/2026"},
        )

        assert response.status_code == 400
        assert "Invalid signed_date" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_inspection_no_auth(self, client, confirmed_booking, auth_headers):
        """Should reject unauthenticated update."""
        create_resp = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
            },
        )
        inspection_id = create_resp.json()["inspection"]["id"]

        response = await client.put(
            f"/api/employee/inspections/{inspection_id}",
            json={"notes": "No auth"},
        )

        assert response.status_code == 401


# =============================================================================
# Complete Booking Tests
# =============================================================================

class TestCompleteBooking:
    """Tests for POST /api/employee/bookings/{booking_id}/complete."""

    @pytest.mark.asyncio
    async def test_complete_confirmed_booking(self, client, auth_headers, confirmed_booking, db_session):
        """Should mark a confirmed booking as completed."""
        response = await client.post(
            f"/api/employee/bookings/{confirmed_booking.id}/complete",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert confirmed_booking.reference in data["message"]

        # Verify in database
        db_session.refresh(confirmed_booking)
        from db_models import BookingStatus
        assert confirmed_booking.status == BookingStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_complete_already_completed_booking(self, client, auth_headers, completed_booking):
        """Should reject completing a booking that is already completed."""
        response = await client.post(
            f"/api/employee/bookings/{completed_booking.id}/complete",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "must be confirmed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_complete_pending_booking(self, client, auth_headers, pending_booking):
        """Should reject completing a pending (unpaid) booking."""
        response = await client.post(
            f"/api/employee/bookings/{pending_booking.id}/complete",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "must be confirmed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_complete_nonexistent_booking(self, client, auth_headers):
        """Should return 404 for non-existent booking."""
        response = await client.post(
            "/api/employee/bookings/999999/complete",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "Booking not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_complete_booking_no_auth(self, client, confirmed_booking):
        """Should reject unauthenticated request."""
        response = await client.post(
            f"/api/employee/bookings/{confirmed_booking.id}/complete",
        )

        assert response.status_code == 401


# =============================================================================
# Photo Data Format Tests
# =============================================================================

class TestPhotoDataFormat:
    """Tests for the labeled photo slot format."""

    @pytest.mark.asyncio
    async def test_photos_stored_as_dict(self, client, auth_headers, confirmed_booking):
        """Photos should be stored and returned as a dict with slot keys."""
        await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "photos": MOCK_PHOTOS,
            },
        )

        response = await client.get(
            f"/api/employee/inspections/{confirmed_booking.id}",
            headers=auth_headers,
        )

        photos = response.json()["inspections"][0]["photos"]
        assert isinstance(photos, dict)
        assert set(photos.keys()) == {"front", "rear", "driver_side", "passenger_side"}

    @pytest.mark.asyncio
    async def test_photos_with_additional_slots(self, client, auth_headers, confirmed_booking):
        """Should handle additional photo slots beyond the 4 core ones."""
        photos_with_extras = {
            **MOCK_PHOTOS,
            "additional_1": "data:image/png;base64,AAAA",
            "additional_2": "data:image/png;base64,BBBB",
        }
        await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "photos": photos_with_extras,
            },
        )

        response = await client.get(
            f"/api/employee/inspections/{confirmed_booking.id}",
            headers=auth_headers,
        )

        photos = response.json()["inspections"][0]["photos"]
        assert len(photos) == 6
        assert "additional_1" in photos
        assert "additional_2" in photos

    @pytest.mark.asyncio
    async def test_empty_photos_returns_empty_dict(self, client, auth_headers, confirmed_booking):
        """Inspection with no photos should return empty dict."""
        await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
            },
        )

        response = await client.get(
            f"/api/employee/inspections/{confirmed_booking.id}",
            headers=auth_headers,
        )

        photos = response.json()["inspections"][0]["photos"]
        assert photos == {}

    @pytest.mark.asyncio
    async def test_update_replaces_all_photos(self, client, auth_headers, confirmed_booking):
        """Updating photos should replace all slots, not merge."""
        create_resp = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "photos": MOCK_PHOTOS,
            },
        )
        inspection_id = create_resp.json()["inspection"]["id"]

        # Update with only partial photos — should replace entirely
        response = await client.put(
            f"/api/employee/inspections/{inspection_id}",
            headers=auth_headers,
            json={"photos": MOCK_PHOTOS_PARTIAL},
        )

        photos = response.json()["inspection"]["photos"]
        assert set(photos.keys()) == {"front", "rear"}
        assert "driver_side" not in photos


# =============================================================================
# Integration Test - Full Inspection Flow
# =============================================================================

class TestInspectionFullFlow:
    """End-to-end test for the complete inspection workflow."""

    @pytest.mark.asyncio
    async def test_full_inspection_and_complete_flow(self, client, auth_headers, confirmed_booking, db_session):
        """
        Full flow:
        1. Create drop-off inspection with photos + customer acknowledgement
        2. Verify it shows in GET
        3. Create pick-up (return) inspection
        4. Update pick-up with customer name
        5. Complete the booking
        6. Verify booking status changed
        """
        # 1. Drop-off inspection
        dropoff_resp = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "notes": "Vehicle in good condition. Small dent on rear bumper.",
                "photos": MOCK_PHOTOS,
                "customer_name": "John TestInspection",
                "signed_date": date.today().isoformat(),
            },
        )
        assert dropoff_resp.status_code == 200
        assert dropoff_resp.json()["success"] is True

        # 2. Verify both appear in GET
        get_resp = await client.get(
            f"/api/employee/inspections/{confirmed_booking.id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200
        assert len(get_resp.json()["inspections"]) == 1

        # 3. Pick-up inspection
        pickup_resp = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "pickup",
                "notes": "Vehicle returned. Same dent on rear bumper, no new damage.",
                "photos": MOCK_PHOTOS_PARTIAL,
            },
        )
        assert pickup_resp.status_code == 200
        pickup_id = pickup_resp.json()["inspection"]["id"]

        # 4. Update pick-up with customer acknowledgement
        update_resp = await client.put(
            f"/api/employee/inspections/{pickup_id}",
            headers=auth_headers,
            json={
                "customer_name": "John TestInspection",
                "signed_date": date.today().isoformat(),
            },
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["inspection"]["customer_name"] == "John TestInspection"

        # Verify both inspections now present
        get_resp2 = await client.get(
            f"/api/employee/inspections/{confirmed_booking.id}",
            headers=auth_headers,
        )
        assert len(get_resp2.json()["inspections"]) == 2

        # 5. Complete booking
        complete_resp = await client.post(
            f"/api/employee/bookings/{confirmed_booking.id}/complete",
            headers=auth_headers,
        )
        assert complete_resp.status_code == 200
        assert complete_resp.json()["success"] is True

        # 6. Verify status in database
        db_session.refresh(confirmed_booking)
        from db_models import BookingStatus
        assert confirmed_booking.status == BookingStatus.COMPLETED

        # 7. Cannot complete again
        again_resp = await client.post(
            f"/api/employee/bookings/{confirmed_booking.id}/complete",
            headers=auth_headers,
        )
        assert again_resp.status_code == 400


# =============================================================================
# Edge Cases
# =============================================================================

class TestInspectionEdgeCases:
    """Edge case and security tests."""

    @pytest.mark.asyncio
    async def test_very_long_notes(self, client, auth_headers, confirmed_booking):
        """Should handle very long inspection notes."""
        long_notes = "x" * 5000
        response = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "notes": long_notes,
            },
        )

        assert response.status_code == 200
        assert len(response.json()["inspection"]["notes"]) == 5000

    @pytest.mark.asyncio
    async def test_special_characters_in_notes(self, client, auth_headers, confirmed_booking):
        """Should handle special characters and unicode in notes."""
        notes = "Scratch on driver's door — approx. 10cm. Customer said: \"it was already there\" ✓"
        response = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "notes": notes,
            },
        )

        assert response.status_code == 200
        assert response.json()["inspection"]["notes"] == notes

    @pytest.mark.asyncio
    async def test_html_in_notes_stored_as_text(self, client, auth_headers, confirmed_booking):
        """Notes with HTML should be stored as plain text (no XSS risk on backend)."""
        notes = '<script>alert("xss")</script>'
        response = await client.post(
            "/api/employee/inspections",
            headers=auth_headers,
            json={
                "booking_id": confirmed_booking.id,
                "inspection_type": "dropoff",
                "notes": notes,
            },
        )

        assert response.status_code == 200
        assert response.json()["inspection"]["notes"] == notes

    @pytest.mark.asyncio
    async def test_expired_session_rejected(self, client, db_session, employee_user):
        """Should reject request with expired session token."""
        from db_models import Session as DbSession
        expired = DbSession(
            user_id=employee_user.id,
            token=f"expired_insp_{uuid.uuid4().hex}",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        db_session.add(expired)
        db_session.commit()

        response = await client.get(
            "/api/employee/inspections/1",
            headers={"Authorization": f"Bearer {expired.token}"},
        )

        assert response.status_code == 401

        # Cleanup
        db_session.delete(expired)
        db_session.commit()
