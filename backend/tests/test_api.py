"""
Integration tests for the FastAPI endpoints.

Tests the full request/response cycle for the booking API.
"""
import pytest
import pytest_asyncio
from datetime import date
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from booking_service import _booking_service, BookingService


@pytest.fixture(autouse=True)
def reset_service():
    """Reset the booking service before each test."""
    global _booking_service
    import booking_service
    booking_service._booking_service = BookingService()
    yield
    booking_service._booking_service = None


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_check(client):
    """Root endpoint should return healthy status."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_get_available_slots(client):
    """Should return available slots for a flight."""
    response = await client.post(
        "/api/slots/available",
        json={
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["slots"]) == 2
    assert data["flight_number"] == "FR5523"


@pytest.mark.asyncio
async def test_get_drop_off_summary_normal(client):
    """Should return drop-off summary for normal flight."""
    response = await client.post(
        "/api/slots/summary",
        json={
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "slot_type": "165"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_overnight"] is False
    assert data["drop_off_date"] == "2026-02-10"
    assert data["drop_off_time"] == "07:15"


@pytest.mark.asyncio
async def test_get_drop_off_summary_overnight(client):
    """Should return overnight warning for early morning flight."""
    response = await client.post(
        "/api/slots/summary",
        json={
            "flight_date": "2026-02-10",
            "flight_time": "00:35",
            "slot_type": "165"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_overnight"] is True
    assert data["drop_off_date"] == "2026-02-09"
    assert data["drop_off_time"] == "21:50"
    assert "Monday" in data["display_message"]


@pytest.mark.asyncio
async def test_get_pickup_summary_normal(client):
    """Should return pickup summary with 35-minute buffer for normal arrival."""
    response = await client.post(
        "/api/pickup/summary",
        json={
            "arrival_date": "2026-02-10",
            "arrival_time": "14:30"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_overnight"] is False
    assert data["arrival_date"] == "2026-02-10"
    assert data["arrival_time"] == "14:30"
    assert data["pickup_date"] == "2026-02-10"
    assert data["pickup_time"] == "15:05"  # 14:30 + 35 min
    assert data["clearance_buffer_minutes"] == 35


@pytest.mark.asyncio
async def test_get_pickup_summary_overnight(client):
    """
    Should return overnight warning for late-night arrival.
    Flight at 23:55 + 35 min = pickup at 00:30 next day.
    """
    response = await client.post(
        "/api/pickup/summary",
        json={
            "arrival_date": "2026-02-10",
            "arrival_time": "23:55"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_overnight"] is True
    assert data["arrival_date"] == "2026-02-10"
    assert data["arrival_day"] == "Tuesday"
    assert data["pickup_date"] == "2026-02-11"
    assert data["pickup_day"] == "Wednesday"
    assert data["pickup_time"] == "00:30"
    assert "Wednesday" in data["display_message"]
    assert "after midnight" in data["display_message"]


@pytest.mark.asyncio
async def test_get_pickup_summary_2330_overnight(client):
    """
    Flight at 23:30 + 35 min = pickup at 00:05 next day.
    """
    response = await client.post(
        "/api/pickup/summary",
        json={
            "arrival_date": "2026-02-10",
            "arrival_time": "23:30"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_overnight"] is True
    assert data["pickup_date"] == "2026-02-11"
    assert data["pickup_time"] == "00:05"


@pytest.mark.asyncio
async def test_check_capacity(client):
    """Should return capacity information."""
    response = await client.post(
        "/api/capacity/check",
        json={
            "start_date": "2026-02-10",
            "end_date": "2026-02-17"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["all_available"] is True
    assert data["max_capacity"] == 60


@pytest.mark.asyncio
async def test_create_booking(client):
    """Should create a booking successfully."""
    response = await client.post(
        "/api/bookings",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "07700900000",
            "drop_off_date": "2026-02-10",
            "drop_off_slot_type": "165",
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "destination_code": "KRK",
            "destination_name": "Krakow, PL",
            "pickup_date": "2026-02-17",
            "return_flight_time": "14:30",
            "return_flight_number": "5524",
            "registration": "AB12 CDE",
            "make": "Ford",
            "model": "Focus",
            "colour": "Blue",
            "package": "quick",
            "billing_address1": "123 Test St",
            "billing_city": "London",
            "billing_postcode": "SW1A 1AA",
            "billing_country": "United Kingdom"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["booking_id"] is not None
    assert data["booking"]["price"] == 99.0


@pytest.mark.asyncio
async def test_slot_hidden_after_booking(client):
    """Booked slot should not appear in available slots."""
    # Create booking
    await client.post(
        "/api/bookings",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "07700900000",
            "drop_off_date": "2026-02-10",
            "drop_off_slot_type": "165",
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "destination_code": "KRK",
            "destination_name": "Krakow, PL",
            "pickup_date": "2026-02-17",
            "return_flight_time": "14:30",
            "return_flight_number": "5524",
            "registration": "AB12 CDE",
            "make": "Ford",
            "model": "Focus",
            "colour": "Blue",
            "package": "quick",
            "billing_address1": "123 Test St",
            "billing_city": "London",
            "billing_postcode": "SW1A 1AA",
            "billing_country": "United Kingdom"
        }
    )

    # Check available slots
    response = await client.post(
        "/api/slots/available",
        json={
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR"
        }
    )
    data = response.json()
    assert len(data["slots"]) == 1  # Only LATE slot available
    assert data["slots"][0]["slot_type"] == "120"


@pytest.mark.asyncio
async def test_duplicate_booking_fails(client):
    """Booking same slot twice should fail."""
    booking_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "phone": "07700900000",
        "drop_off_date": "2026-02-10",
        "drop_off_slot_type": "165",
        "flight_date": "2026-02-10",
        "flight_time": "10:00",
        "flight_number": "5523",
        "airline_code": "FR",
        "airline_name": "Ryanair",
        "destination_code": "KRK",
        "destination_name": "Krakow, PL",
        "pickup_date": "2026-02-17",
        "return_flight_time": "14:30",
        "return_flight_number": "5524",
        "registration": "AB12 CDE",
        "make": "Ford",
        "model": "Focus",
        "colour": "Blue",
        "package": "quick",
        "billing_address1": "123 Test St",
        "billing_city": "London",
        "billing_postcode": "SW1A 1AA",
        "billing_country": "United Kingdom"
    }

    # First booking should succeed
    response1 = await client.post("/api/bookings", json=booking_data)
    assert response1.status_code == 200

    # Second booking with same slot should fail
    booking_data["email"] = "other@example.com"
    response2 = await client.post("/api/bookings", json=booking_data)
    assert response2.status_code == 400
    assert "already booked" in response2.json()["detail"]


@pytest.mark.asyncio
async def test_get_booking(client):
    """Should retrieve a booking by ID."""
    # Create booking
    create_response = await client.post(
        "/api/bookings",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "07700900000",
            "drop_off_date": "2026-02-10",
            "drop_off_slot_type": "165",
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "destination_code": "KRK",
            "destination_name": "Krakow, PL",
            "pickup_date": "2026-02-17",
            "return_flight_time": "14:30",
            "return_flight_number": "5524",
            "registration": "AB12 CDE",
            "make": "Ford",
            "model": "Focus",
            "colour": "Blue",
            "package": "quick",
            "billing_address1": "123 Test St",
            "billing_city": "London",
            "billing_postcode": "SW1A 1AA",
            "billing_country": "United Kingdom"
        }
    )
    booking_id = create_response.json()["booking_id"]

    # Get booking
    response = await client.get(f"/api/bookings/{booking_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["booking"]["first_name"] == "John"


@pytest.mark.asyncio
async def test_get_nonexistent_booking(client):
    """Should return 404 for non-existent booking."""
    response = await client.get("/api/bookings/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_booking(client):
    """Should cancel a booking and release the slot."""
    # Create booking
    create_response = await client.post(
        "/api/bookings",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "07700900000",
            "drop_off_date": "2026-02-10",
            "drop_off_slot_type": "165",
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "destination_code": "KRK",
            "destination_name": "Krakow, PL",
            "pickup_date": "2026-02-17",
            "return_flight_time": "14:30",
            "return_flight_number": "5524",
            "registration": "AB12 CDE",
            "make": "Ford",
            "model": "Focus",
            "colour": "Blue",
            "package": "quick",
            "billing_address1": "123 Test St",
            "billing_city": "London",
            "billing_postcode": "SW1A 1AA",
            "billing_country": "United Kingdom"
        }
    )
    booking_id = create_response.json()["booking_id"]

    # Cancel booking
    cancel_response = await client.delete(f"/api/bookings/{booking_id}")
    assert cancel_response.status_code == 200

    # Check slot is available again
    slots_response = await client.post(
        "/api/slots/available",
        json={
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR"
        }
    )
    assert len(slots_response.json()["slots"]) == 2  # Both available again


@pytest.mark.asyncio
async def test_bookings_by_email(client):
    """Should find bookings by email."""
    # Create booking
    await client.post(
        "/api/bookings",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "07700900000",
            "drop_off_date": "2026-02-10",
            "drop_off_slot_type": "165",
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "destination_code": "KRK",
            "destination_name": "Krakow, PL",
            "pickup_date": "2026-02-17",
            "return_flight_time": "14:30",
            "return_flight_number": "5524",
            "registration": "AB12 CDE",
            "make": "Ford",
            "model": "Focus",
            "colour": "Blue",
            "package": "quick",
            "billing_address1": "123 Test St",
            "billing_city": "London",
            "billing_postcode": "SW1A 1AA",
            "billing_country": "United Kingdom"
        }
    )

    response = await client.get("/api/bookings/email/john@example.com")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["bookings"][0]["email"] == "john@example.com"


@pytest.mark.asyncio
async def test_admin_all_bookings(client):
    """Admin endpoint should return all bookings."""
    # Create booking
    await client.post(
        "/api/bookings",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "07700900000",
            "drop_off_date": "2026-02-10",
            "drop_off_slot_type": "165",
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "destination_code": "KRK",
            "destination_name": "Krakow, PL",
            "pickup_date": "2026-02-17",
            "return_flight_time": "14:30",
            "return_flight_number": "5524",
            "registration": "AB12 CDE",
            "make": "Ford",
            "model": "Focus",
            "colour": "Blue",
            "package": "quick",
            "billing_address1": "123 Test St",
            "billing_city": "London",
            "billing_postcode": "SW1A 1AA",
            "billing_country": "United Kingdom"
        }
    )

    response = await client.get("/api/admin/bookings")
    assert response.status_code == 200
    assert response.json()["count"] == 1


@pytest.mark.asyncio
async def test_admin_occupancy(client):
    """Admin endpoint should return daily occupancy."""
    response = await client.get("/api/admin/occupancy/2026-02-10")
    assert response.status_code == 200
    data = response.json()
    assert data["max_capacity"] == 60
    assert data["available"] == 60


@pytest.mark.asyncio
async def test_all_slots_booked_shows_contact_message(client):
    """When all slots are booked, should return contact message."""
    booking_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "phone": "07700900000",
        "drop_off_date": "2026-02-10",
        "drop_off_slot_type": "165",
        "flight_date": "2026-02-10",
        "flight_time": "10:00",
        "flight_number": "5523",
        "airline_code": "FR",
        "airline_name": "Ryanair",
        "destination_code": "KRK",
        "destination_name": "Krakow, PL",
        "pickup_date": "2026-02-17",
        "return_flight_time": "14:30",
        "return_flight_number": "5524",
        "registration": "AB12 CDE",
        "make": "Ford",
        "model": "Focus",
        "colour": "Blue",
        "package": "quick",
        "billing_address1": "123 Test St",
        "billing_city": "London",
        "billing_postcode": "SW1A 1AA",
        "billing_country": "United Kingdom"
    }

    # Book early slot
    await client.post("/api/bookings", json=booking_data)

    # Book late slot
    booking_data["email"] = "jane@example.com"
    booking_data["drop_off_slot_type"] = "120"
    await client.post("/api/bookings", json=booking_data)

    # Check available slots - should show contact message
    response = await client.post(
        "/api/slots/available",
        json={
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["all_slots_booked"] is True
    assert data["contact_message"] is not None
    assert "contact us" in data["contact_message"].lower()
    assert len(data["slots"]) == 0


@pytest.mark.asyncio
async def test_admin_create_booking(client):
    """Admin should be able to create a booking with custom time."""
    response = await client.post(
        "/api/admin/bookings",
        json={
            "first_name": "Admin",
            "last_name": "Created",
            "email": "customer@example.com",
            "phone": "07700900000",
            "drop_off_date": "2026-02-10",
            "drop_off_time": "08:30",
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "destination_code": "KRK",
            "destination_name": "Krakow, PL",
            "pickup_date": "2026-02-17",
            "return_flight_time": "14:30",
            "return_flight_number": "5524",
            "registration": "AB12 CDE",
            "make": "Ford",
            "model": "Focus",
            "colour": "Blue",
            "package": "quick",
            "booking_source": "phone"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["booking_id"] is not None
    assert "phone" in data["message"]


@pytest.mark.asyncio
async def test_admin_booking_with_custom_price(client):
    """Admin should be able to set a custom price."""
    response = await client.post(
        "/api/admin/bookings",
        json={
            "first_name": "Discount",
            "last_name": "Customer",
            "email": "discount@example.com",
            "phone": "07700900000",
            "drop_off_date": "2026-02-10",
            "drop_off_time": "08:30",
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "destination_code": "KRK",
            "destination_name": "Krakow, PL",
            "pickup_date": "2026-02-17",
            "return_flight_time": "14:30",
            "return_flight_number": "5524",
            "registration": "AB12 CDE",
            "make": "Ford",
            "model": "Focus",
            "colour": "Blue",
            "package": "quick",
            "custom_price": 75.00,
            "booking_source": "admin"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["booking"]["price"] == 75.00


@pytest.mark.asyncio
async def test_admin_booking_bypasses_slot_restrictions(client):
    """Admin can book even when regular slots are full."""
    booking_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "phone": "07700900000",
        "drop_off_date": "2026-02-10",
        "drop_off_slot_type": "165",
        "flight_date": "2026-02-10",
        "flight_time": "10:00",
        "flight_number": "5523",
        "airline_code": "FR",
        "airline_name": "Ryanair",
        "destination_code": "KRK",
        "destination_name": "Krakow, PL",
        "pickup_date": "2026-02-17",
        "return_flight_time": "14:30",
        "return_flight_number": "5524",
        "registration": "AB12 CDE",
        "make": "Ford",
        "model": "Focus",
        "colour": "Blue",
        "package": "quick",
        "billing_address1": "123 Test St",
        "billing_city": "London",
        "billing_postcode": "SW1A 1AA",
        "billing_country": "United Kingdom"
    }

    # Book both regular slots
    await client.post("/api/bookings", json=booking_data)
    booking_data["email"] = "jane@example.com"
    booking_data["drop_off_slot_type"] = "120"
    await client.post("/api/bookings", json=booking_data)

    # Verify slots are full
    slots_response = await client.post(
        "/api/slots/available",
        json={
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR"
        }
    )
    assert slots_response.json()["all_slots_booked"] is True

    # Admin can still create a booking
    admin_response = await client.post(
        "/api/admin/bookings",
        json={
            "first_name": "Walk-in",
            "last_name": "Customer",
            "email": "walkin@example.com",
            "phone": "07700900000",
            "drop_off_date": "2026-02-10",
            "drop_off_time": "09:00",
            "flight_date": "2026-02-10",
            "flight_time": "10:00",
            "flight_number": "5523",
            "airline_code": "FR",
            "airline_name": "Ryanair",
            "destination_code": "KRK",
            "destination_name": "Krakow, PL",
            "pickup_date": "2026-02-17",
            "return_flight_time": "14:30",
            "return_flight_number": "5524",
            "registration": "XY99 ZZZ",
            "make": "BMW",
            "model": "3 Series",
            "colour": "Silver",
            "package": "quick",
            "booking_source": "walk-in"
        }
    )
    assert admin_response.status_code == 200
    assert admin_response.json()["success"] is True
