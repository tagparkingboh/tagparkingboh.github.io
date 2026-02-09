"""
Tests for concurrent booking scenarios.

Tests what happens when multiple users try to book the same time slot
simultaneously (race condition scenarios).

All tests use mocked data - no real database connections.
"""
import pytest
import pytest_asyncio
import asyncio
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import get_db
from booking_service import _booking_service, BookingService


# =============================================================================
# Mock Database Setup
# =============================================================================

class MockSession:
    """Mock database session that does nothing."""

    def query(self, model):
        return self

    def filter(self, *args):
        return self

    def first(self):
        return None

    def all(self):
        return []

    def add(self, obj):
        pass

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def get_mock_db():
    """Override for get_db dependency."""
    db = MockSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def reset_service():
    """Reset the booking service before each test."""
    global _booking_service
    import booking_service
    booking_service._booking_service = BookingService()
    yield
    booking_service._booking_service = None


@pytest.fixture(autouse=True)
def override_db_dependency():
    """Override the database dependency for all tests."""
    app.dependency_overrides[get_db] = get_mock_db
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def get_booking_data(user_number: int) -> dict:
    """Generate booking data for a specific user number."""
    return {
        "first_name": f"User{user_number}",
        "last_name": "Test",
        "email": f"user{user_number}@example.com",
        "phone": f"0770090000{user_number}",
        "drop_off_date": "2026-02-10",
        "drop_off_slot_type": "165",  # EARLY slot
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
        "registration": f"AB{user_number}2 CDE",
        "make": "Ford",
        "model": "Focus",
        "colour": "Blue",
        "package": "quick",
        "billing_address1": f"{user_number} Test Street",
        "billing_city": "London",
        "billing_postcode": "SW1A 1AA",
        "billing_country": "United Kingdom"
    }


# =============================================================================
# Concurrent Booking Tests
# =============================================================================

class TestConcurrentBooking:
    """Tests for concurrent booking scenarios (race conditions)."""

    @pytest.mark.asyncio
    async def test_two_users_same_slot_one_succeeds(self, client):
        """
        When two users try to book the same slot simultaneously,
        exactly one should succeed and one should fail.
        """
        async def book_slot(user_num: int) -> dict:
            """Make a booking request for a user."""
            response = await client.post(
                "/api/bookings",
                json=get_booking_data(user_num)
            )
            return {
                "user": user_num,
                "status_code": response.status_code,
                "data": response.json()
            }

        # Run two booking requests concurrently
        results = await asyncio.gather(
            book_slot(1),
            book_slot(2),
            return_exceptions=True
        )

        # Analyze results
        successes = [r for r in results if isinstance(r, dict) and r["status_code"] == 200]
        failures = [r for r in results if isinstance(r, dict) and r["status_code"] == 400]

        # Exactly one should succeed, one should fail
        assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
        assert len(failures) == 1, f"Expected 1 failure, got {len(failures)}"

        # The successful one should have a booking ID
        assert successes[0]["data"]["success"] is True
        assert successes[0]["data"]["booking_id"] is not None

        # The failed one should mention "already booked"
        assert "already booked" in failures[0]["data"]["detail"].lower()

    @pytest.mark.asyncio
    async def test_three_users_same_slot_one_succeeds(self, client):
        """
        When three users try to book the same slot simultaneously,
        exactly one should succeed and two should fail.
        """
        async def book_slot(user_num: int) -> dict:
            response = await client.post(
                "/api/bookings",
                json=get_booking_data(user_num)
            )
            return {
                "user": user_num,
                "status_code": response.status_code,
                "data": response.json()
            }

        # Run three booking requests concurrently
        results = await asyncio.gather(
            book_slot(1),
            book_slot(2),
            book_slot(3),
            return_exceptions=True
        )

        successes = [r for r in results if isinstance(r, dict) and r["status_code"] == 200]
        failures = [r for r in results if isinstance(r, dict) and r["status_code"] == 400]

        # Exactly one should succeed, two should fail
        assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
        assert len(failures) == 2, f"Expected 2 failures, got {len(failures)}"

    @pytest.mark.asyncio
    async def test_two_users_different_slots_both_succeed(self, client):
        """
        When two users book different slots for the same flight,
        both should succeed.
        """
        booking_data_1 = get_booking_data(1)
        booking_data_1["drop_off_slot_type"] = "165"  # EARLY slot

        booking_data_2 = get_booking_data(2)
        booking_data_2["drop_off_slot_type"] = "120"  # LATE slot

        async def book_early():
            response = await client.post("/api/bookings", json=booking_data_1)
            return {"slot": "EARLY", "status_code": response.status_code, "data": response.json()}

        async def book_late():
            response = await client.post("/api/bookings", json=booking_data_2)
            return {"slot": "LATE", "status_code": response.status_code, "data": response.json()}

        # Run both requests concurrently
        results = await asyncio.gather(book_early(), book_late())

        # Both should succeed
        for result in results:
            assert result["status_code"] == 200, f"{result['slot']} slot booking failed"
            assert result["data"]["success"] is True

    @pytest.mark.asyncio
    async def test_concurrent_bookings_different_flights_all_succeed(self, client):
        """
        When multiple users book slots for different flights concurrently,
        all should succeed.
        """
        async def book_flight(user_num: int, flight_date: str) -> dict:
            data = get_booking_data(user_num)
            data["flight_date"] = flight_date
            data["drop_off_date"] = flight_date
            response = await client.post("/api/bookings", json=data)
            return {
                "user": user_num,
                "flight_date": flight_date,
                "status_code": response.status_code,
                "data": response.json()
            }

        # Book different flights concurrently
        results = await asyncio.gather(
            book_flight(1, "2026-02-10"),
            book_flight(2, "2026-02-11"),
            book_flight(3, "2026-02-12"),
        )

        # All should succeed since they're different flights
        for result in results:
            assert result["status_code"] == 200, \
                f"User {result['user']} booking for {result['flight_date']} failed"
            assert result["data"]["success"] is True

    @pytest.mark.asyncio
    async def test_five_users_same_slot_stress_test(self, client):
        """
        Stress test: Five users trying to book the exact same slot.
        Exactly one should succeed.
        """
        async def book_slot(user_num: int) -> dict:
            response = await client.post(
                "/api/bookings",
                json=get_booking_data(user_num)
            )
            return {
                "user": user_num,
                "status_code": response.status_code,
                "data": response.json()
            }

        # Run five booking requests concurrently
        results = await asyncio.gather(
            book_slot(1),
            book_slot(2),
            book_slot(3),
            book_slot(4),
            book_slot(5),
            return_exceptions=True
        )

        successes = [r for r in results if isinstance(r, dict) and r["status_code"] == 200]
        failures = [r for r in results if isinstance(r, dict) and r["status_code"] == 400]

        # Exactly one should succeed
        assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
        assert len(failures) == 4, f"Expected 4 failures, got {len(failures)}"

    @pytest.mark.asyncio
    async def test_slot_hidden_after_concurrent_booking(self, client):
        """
        After a concurrent booking race, the slot should be properly hidden.
        """
        # First, run concurrent bookings
        async def book_slot(user_num: int) -> dict:
            response = await client.post(
                "/api/bookings",
                json=get_booking_data(user_num)
            )
            return {
                "user": user_num,
                "status_code": response.status_code,
                "data": response.json()
            }

        await asyncio.gather(book_slot(1), book_slot(2))

        # Now check available slots - the EARLY slot should be taken
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
        # Only LATE slot (120) should be available
        assert len(data["slots"]) == 1
        assert data["slots"][0]["slot_type"] == "120"

    @pytest.mark.asyncio
    async def test_both_slots_booked_concurrently(self, client):
        """
        Two users booking different slots concurrently should result in
        both slots being booked and no slots available.
        """
        booking_data_1 = get_booking_data(1)
        booking_data_1["drop_off_slot_type"] = "165"

        booking_data_2 = get_booking_data(2)
        booking_data_2["drop_off_slot_type"] = "120"

        # Book both slots concurrently
        results = await asyncio.gather(
            client.post("/api/bookings", json=booking_data_1),
            client.post("/api/bookings", json=booking_data_2),
        )

        # Both should succeed
        assert all(r.status_code == 200 for r in results)

        # Check available slots - should be none
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
        assert data["all_slots_booked"] is True
        assert len(data["slots"]) == 0
        assert data["contact_message"] is not None

    @pytest.mark.asyncio
    async def test_third_user_rejected_after_both_slots_booked_concurrently(self, client):
        """
        After two slots are booked concurrently, a third user should get
        the contact message.
        """
        # Book both slots concurrently
        booking_data_1 = get_booking_data(1)
        booking_data_1["drop_off_slot_type"] = "165"

        booking_data_2 = get_booking_data(2)
        booking_data_2["drop_off_slot_type"] = "120"

        await asyncio.gather(
            client.post("/api/bookings", json=booking_data_1),
            client.post("/api/bookings", json=booking_data_2),
        )

        # Third user tries to book - should fail since both slots are taken
        booking_data_3 = get_booking_data(3)
        booking_data_3["drop_off_slot_type"] = "165"  # Try EARLY slot

        response = await client.post("/api/bookings", json=booking_data_3)
        assert response.status_code == 400
        assert "already booked" in response.json()["detail"].lower()


# =============================================================================
# Race Condition Detection Tests
# =============================================================================

class TestRaceConditionDetection:
    """
    Tests to detect potential race conditions in the booking system.

    These tests intentionally create scenarios where race conditions
    could cause data corruption or double-booking.
    """

    @pytest.mark.asyncio
    async def test_rapid_sequential_booking_same_slot(self, client):
        """
        Rapid sequential booking attempts should be handled correctly.
        """
        results = []
        for i in range(5):
            response = await client.post(
                "/api/bookings",
                json=get_booking_data(i)
            )
            results.append({
                "user": i,
                "status_code": response.status_code,
                "data": response.json()
            })

        # Only first should succeed
        successes = [r for r in results if r["status_code"] == 200]
        assert len(successes) == 1

    @pytest.mark.asyncio
    async def test_no_double_booking_after_concurrent_attempts(self, client):
        """
        After concurrent booking attempts, verify no double-booking occurred.
        Uses in-memory BookingService to check bookings.
        """
        import booking_service

        # Run concurrent bookings
        async def book_slot(user_num: int):
            return await client.post(
                "/api/bookings",
                json=get_booking_data(user_num)
            )

        await asyncio.gather(
            book_slot(1),
            book_slot(2),
            book_slot(3),
        )

        # Check bookings from in-memory service
        all_bookings = booking_service._booking_service.get_all_active_bookings()

        # Should only have 1 booking for this slot
        flight_bookings = [
            b for b in all_bookings
            if b.flight_number == "5523"
            and str(b.flight_date) == "2026-02-10"
            and b.drop_off_slot_type == "165"
        ]

        assert len(flight_bookings) == 1, \
            f"Expected 1 booking for slot, got {len(flight_bookings)} - possible double booking!"

    @pytest.mark.asyncio
    async def test_occupancy_count_correct_after_concurrent_bookings(self, client):
        """
        After concurrent booking attempts, occupancy should reflect
        only the successful bookings.
        Uses in-memory BookingService to count bookings.
        """
        import booking_service

        # Try 5 concurrent bookings for the same slot
        async def book_slot(user_num: int):
            return await client.post(
                "/api/bookings",
                json=get_booking_data(user_num)
            )

        await asyncio.gather(*[book_slot(i) for i in range(5)])

        # Check bookings from in-memory service
        all_bookings = booking_service._booking_service.get_all_active_bookings()

        # Count bookings for the date
        bookings_for_date = [
            b for b in all_bookings
            if str(b.flight_date) == "2026-02-10"
        ]

        # Should have occupancy of 1 (only one booking succeeded for that slot)
        assert len(bookings_for_date) == 1, \
            f"Expected occupancy of 1, got {len(bookings_for_date)} - possible race condition!"


# =============================================================================
# Edge Cases for Concurrent Scenarios
# =============================================================================

class TestConcurrentEdgeCases:
    """Edge cases for concurrent booking scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_booking_and_slot_check(self, client):
        """
        If a user checks slots while another books, the slot check
        should reflect the booking once complete.
        """
        booking_data = get_booking_data(1)

        async def check_slots():
            return await client.post(
                "/api/slots/available",
                json={
                    "flight_date": "2026-02-10",
                    "flight_time": "10:00",
                    "flight_number": "5523",
                    "airline_code": "FR"
                }
            )

        async def make_booking():
            return await client.post("/api/bookings", json=booking_data)

        # Run concurrently
        slots_response, booking_response = await asyncio.gather(
            check_slots(),
            make_booking()
        )

        # Booking should succeed
        assert booking_response.status_code == 200

        # Now check slots again - EARLY should be gone
        final_slots = await check_slots()
        data = final_slots.json()

        # Only LATE slot should be available
        slot_types = [s["slot_type"] for s in data["slots"]]
        assert "165" not in slot_types  # EARLY slot should be taken

    @pytest.mark.asyncio
    async def test_concurrent_booking_and_cancel(self, client):
        """
        If user 1 books and user 2 cancels almost simultaneously,
        the system should handle it correctly.
        """
        # First create a booking
        booking_data = get_booking_data(1)
        create_response = await client.post("/api/bookings", json=booking_data)
        booking_id = create_response.json()["booking_id"]

        # Now try to cancel while someone else books the same slot
        booking_data_2 = get_booking_data(2)

        async def cancel():
            return await client.delete(f"/api/bookings/{booking_id}")

        async def book():
            return await client.post("/api/bookings", json=booking_data_2)

        cancel_response, book_response = await asyncio.gather(cancel(), book())

        # Cancel should succeed
        assert cancel_response.status_code == 200

        # The second booking might succeed or fail depending on timing
        # If it succeeds, slot is properly released and re-booked
        # If it fails, the slot wasn't released in time
        # Both are acceptable outcomes
        assert book_response.status_code in [200, 400]

    @pytest.mark.asyncio
    async def test_concurrent_multiple_different_dates(self, client):
        """
        Concurrent bookings for different dates should all succeed.
        """
        dates = ["2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13", "2026-02-14"]

        async def book_date(user_num: int, date: str):
            data = get_booking_data(user_num)
            data["flight_date"] = date
            data["drop_off_date"] = date
            response = await client.post("/api/bookings", json=data)
            return {
                "user": user_num,
                "date": date,
                "status_code": response.status_code
            }

        # Book 5 different dates concurrently
        results = await asyncio.gather(*[
            book_date(i, date) for i, date in enumerate(dates)
        ])

        # All should succeed
        for result in results:
            assert result["status_code"] == 200, \
                f"Booking for {result['date']} failed unexpectedly"

    @pytest.mark.asyncio
    async def test_same_user_cannot_double_book(self, client):
        """
        Same user trying to book twice should fail on second attempt.
        """
        booking_data = get_booking_data(1)

        # First booking should succeed
        response1 = await client.post("/api/bookings", json=booking_data)
        assert response1.status_code == 200

        # Same user trying again should fail
        response2 = await client.post("/api/bookings", json=booking_data)
        assert response2.status_code == 400
        assert "already booked" in response2.json()["detail"].lower()
