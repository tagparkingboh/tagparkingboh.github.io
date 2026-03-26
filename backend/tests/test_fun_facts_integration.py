"""
Integration Tests for Admin Fun Facts Report.

Covers:
- GET /api/admin/reports/fun-facts - Integration tests with mocked database

Test categories:
- Happy path: Normal successful operations with valid data
- Edge cases: Boundary conditions
- Authentication: Admin-only access

All tests use mocked database to avoid real database dependencies.
"""
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app, require_admin
from database import get_db
from db_models import BookingStatus


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@tagparking.co.uk"
    user.role = "admin"
    user.first_name = "Admin"
    user.last_name = "User"
    return user


def create_mock_payment(amount_pence=None, paid_at=None):
    """Create a mock payment object."""
    if amount_pence is None and paid_at is None:
        return None
    payment = MagicMock()
    payment.amount_pence = amount_pence
    payment.paid_at = paid_at
    return payment


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    status=BookingStatus.CONFIRMED,
    dropoff_date=None,
    pickup_date=None,
    amount_pence=None,
    paid_at=None,
    dropoff_destination="Faro Airport",
):
    """Create a mock booking for database queries."""
    from datetime import datetime
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.status = status
    booking.dropoff_date = dropoff_date or date(2026, 3, 15)
    booking.pickup_date = pickup_date or date(2026, 3, 22)
    # Default paid_at to dropoff_date at noon if not provided
    default_paid_at = datetime.combine(booking.dropoff_date, datetime.min.time().replace(hour=12))
    booking.payment = create_mock_payment(amount_pence, paid_at or default_paid_at)
    booking.dropoff_destination = dropoff_destination
    return booking


# =============================================================================
# Integration Tests - Happy Path
# =============================================================================

class TestFunFactsIntegrationHappyPath:
    """Integration tests for happy path scenarios."""

    def test_get_fun_facts_success(self, mock_admin_user):
        """Should return fun facts for confirmed/completed bookings."""
        # Create mock bookings
        mock_bookings = [
            create_mock_booking(id=1, dropoff_date=date(2026, 3, 15), pickup_date=date(2026, 3, 22), amount_pence=8500),   # £85.00
            create_mock_booking(id=2, dropoff_date=date(2026, 3, 15), pickup_date=date(2026, 3, 25), amount_pence=12000),  # £120.00
            create_mock_booking(id=3, dropoff_date=date(2026, 3, 16), pickup_date=date(2026, 3, 30), amount_pence=18900),  # £189.00
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 200
            data = response.json()

            assert "busiestDay" in data
            assert "busiestStreak" in data
            assert "longestTrip" in data
            assert "highestTransaction" in data
        finally:
            app.dependency_overrides.clear()

    def test_busiest_day_calculation(self, mock_admin_user):
        """Should correctly identify busiest day by payment/confirmation date."""
        from datetime import datetime
        # 3 bookings paid on Mar 15, 1 on Mar 16
        mock_bookings = [
            create_mock_booking(id=1, paid_at=datetime(2026, 3, 15, 10, 0, 0)),
            create_mock_booking(id=2, paid_at=datetime(2026, 3, 15, 11, 0, 0)),
            create_mock_booking(id=3, paid_at=datetime(2026, 3, 15, 12, 0, 0)),
            create_mock_booking(id=4, paid_at=datetime(2026, 3, 16, 10, 0, 0)),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 200
            data = response.json()

            assert data["busiestDay"]["count"] == 3
            assert any("15" in d for d in data["busiestDay"]["dates"])  # Mar 15
        finally:
            app.dependency_overrides.clear()

    def test_longest_trip_calculation(self, mock_admin_user):
        """Should correctly identify longest trip."""
        mock_bookings = [
            create_mock_booking(id=1, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 8), dropoff_destination="Faro"),   # 7 days
            create_mock_booking(id=2, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 22), dropoff_destination="Tenerife"),  # 21 days
            create_mock_booking(id=3, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 15), dropoff_destination="Malaga"),  # 14 days
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 200
            data = response.json()

            assert data["longestTrip"]["days"] == 21
            assert data["longestTrip"]["destination"] == "Tenerife"
        finally:
            app.dependency_overrides.clear()

    def test_highest_transaction_calculation(self, mock_admin_user):
        """Should correctly identify highest transaction."""
        mock_bookings = [
            create_mock_booking(id=1, amount_pence=8500, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 8)),    # £85.00
            create_mock_booking(id=2, amount_pence=18900, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 15)),  # £189.00
            create_mock_booking(id=3, amount_pence=12000, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 10)),  # £120.00
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 200
            data = response.json()

            assert data["highestTransaction"]["amount"] == "£189.00"
            assert data["highestTransaction"]["days"] == 14
        finally:
            app.dependency_overrides.clear()

    def test_busiest_streak_calculation(self, mock_admin_user):
        """Should correctly calculate busiest streak by payment/confirmation date."""
        from datetime import datetime
        # Create bookings paid on consecutive days: Mar 15, 16, 17, then gap, then Mar 20
        mock_bookings = [
            create_mock_booking(id=1, paid_at=datetime(2026, 3, 15, 10, 0, 0)),
            create_mock_booking(id=2, paid_at=datetime(2026, 3, 16, 10, 0, 0)),
            create_mock_booking(id=3, paid_at=datetime(2026, 3, 16, 11, 0, 0)),
            create_mock_booking(id=4, paid_at=datetime(2026, 3, 17, 10, 0, 0)),
            create_mock_booking(id=5, paid_at=datetime(2026, 3, 20, 10, 0, 0)),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 200
            data = response.json()

            assert data["busiestStreak"]["days"] == 3
            assert data["busiestStreak"]["bookings"] == 4  # 1 + 2 + 1 bookings
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# Integration Tests - Empty/Null Cases
# =============================================================================

class TestFunFactsIntegrationEmptyCases:
    """Integration tests for empty and null scenarios."""

    def test_no_bookings_returns_null_values(self, mock_admin_user):
        """Should return null values when no bookings exist."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 200
            data = response.json()

            assert data["busiestDay"] is None
            assert data["busiestStreak"] is None
            assert data["longestTrip"] is None
            assert data["highestTransaction"] is None
        finally:
            app.dependency_overrides.clear()

    def test_bookings_with_null_payments(self, mock_admin_user):
        """Should handle bookings with null payments gracefully."""
        mock_bookings = [
            create_mock_booking(id=1, amount_pence=None, dropoff_date=date(2026, 3, 15), pickup_date=date(2026, 3, 22)),
            create_mock_booking(id=2, amount_pence=None, dropoff_date=date(2026, 3, 16), pickup_date=date(2026, 3, 23)),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 200
            data = response.json()

            # Other fields should still work
            assert data["busiestDay"] is not None
            assert data["highestTransaction"] is None
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# Integration Tests - Edge Cases
# =============================================================================

class TestFunFactsIntegrationEdgeCases:
    """Integration tests for edge cases."""

    def test_single_booking(self, mock_admin_user):
        """Should handle single booking correctly."""
        mock_bookings = [
            create_mock_booking(
                id=1,
                dropoff_date=date(2026, 3, 15),
                pickup_date=date(2026, 3, 22),
                amount_pence=8500,  # £85.00
                dropoff_destination="Faro"
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 200
            data = response.json()

            assert data["busiestDay"]["count"] == 1
            assert data["busiestStreak"]["days"] == 1
            assert data["longestTrip"]["days"] == 7
            assert data["highestTransaction"]["amount"] == "£85.00"
        finally:
            app.dependency_overrides.clear()

    def test_missing_destination_shows_unknown(self, mock_admin_user):
        """Should show 'Unknown' for missing destination."""
        mock_bookings = [
            create_mock_booking(
                id=1,
                dropoff_date=date(2026, 3, 1),
                pickup_date=date(2026, 3, 22),
                amount_pence=18900,  # £189.00
                dropoff_destination=None
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 200
            data = response.json()

            assert data["longestTrip"]["destination"] == "Unknown"
        finally:
            app.dependency_overrides.clear()

    def test_same_day_trip(self, mock_admin_user):
        """Should handle same-day trips (0 days) - returns None since no actual trip duration."""
        mock_bookings = [
            create_mock_booking(
                id=1,
                dropoff_date=date(2026, 3, 15),
                pickup_date=date(2026, 3, 15),  # Same day
                amount_pence=5000,  # £50.00
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 200
            data = response.json()

            # 0-day trips don't count as having a "longest trip" since there's no duration
            assert data["longestTrip"] is None
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# Integration Tests - Authentication
# =============================================================================

class TestFunFactsIntegrationAuth:
    """Integration tests for authentication requirements."""

    def test_requires_authentication(self):
        """Should require authentication."""
        # Clear any overrides to test real auth
        app.dependency_overrides.clear()

        client = TestClient(app)
        response = client.get("/api/admin/reports/fun-facts")

        # Should return 401 for unauthenticated requests
        assert response.status_code == 401

    def test_requires_admin_role(self):
        """Should require admin role."""
        from fastapi import HTTPException

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            raise HTTPException(status_code=403, detail="Admin access required")

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# Integration Tests - Date Formatting
# =============================================================================

class TestFunFactsIntegrationDateFormatting:
    """Integration tests for date formatting in response."""

    def test_busiest_day_date_format(self, mock_admin_user):
        """Busiest day date should be in correct UK format."""
        from datetime import datetime
        mock_bookings = [
            create_mock_booking(id=1, paid_at=datetime(2026, 2, 24, 10, 0, 0)),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 200
            data = response.json()

            # Should be like "Tue 24 Feb 2026"
            assert len(data["busiestDay"]["dates"]) == 1
            busiest_date = data["busiestDay"]["dates"][0]
            assert "Tue" in busiest_date
            assert "24" in busiest_date
            assert "Feb" in busiest_date
            assert "2026" in busiest_date
        finally:
            app.dependency_overrides.clear()

    def test_streak_date_format(self, mock_admin_user):
        """Streak dates should be in correct format."""
        from datetime import datetime
        mock_bookings = [
            create_mock_booking(id=1, paid_at=datetime(2026, 2, 24, 10, 0, 0)),
            create_mock_booking(id=2, paid_at=datetime(2026, 2, 25, 10, 0, 0)),
            create_mock_booking(id=3, paid_at=datetime(2026, 2, 26, 10, 0, 0)),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings

        def mock_get_db():
            yield mock_db

        def mock_require_admin():
            return mock_admin_user

        app.dependency_overrides[get_db] = mock_get_db
        app.dependency_overrides[require_admin] = mock_require_admin

        try:
            client = TestClient(app)
            response = client.get("/api/admin/reports/fun-facts")

            assert response.status_code == 200
            data = response.json()

            # startDate should be like "24 Feb"
            assert "24" in data["busiestStreak"]["startDate"]
            assert "Feb" in data["busiestStreak"]["startDate"]

            # endDate should include year like "26 Feb 2026"
            assert "26" in data["busiestStreak"]["endDate"]
            assert "Feb" in data["busiestStreak"]["endDate"]
            assert "2026" in data["busiestStreak"]["endDate"]
        finally:
            app.dependency_overrides.clear()
