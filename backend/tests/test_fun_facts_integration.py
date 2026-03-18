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
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from db_models import BookingStatus


# =============================================================================
# Test Client Setup
# =============================================================================

client = TestClient(app)


def create_mock_user(id=1, email="admin@tagparking.co.uk", role="admin"):
    """Create a mock admin user."""
    user = MagicMock()
    user.id = id
    user.email = email
    user.role = role
    user.first_name = "Admin"
    user.last_name = "User"
    return user


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    status=BookingStatus.CONFIRMED,
    dropoff_date=None,
    pickup_date=None,
    total_price=None,
    dropoff_destination="Faro Airport",
):
    """Create a mock booking for database queries."""
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.status = status
    booking.dropoff_date = dropoff_date or date(2026, 3, 15)
    booking.pickup_date = pickup_date or date(2026, 3, 22)
    booking.total_price = total_price
    booking.dropoff_destination = dropoff_destination
    return booking


# =============================================================================
# Integration Tests - Happy Path
# =============================================================================

class TestFunFactsIntegrationHappyPath:
    """Integration tests for happy path scenarios."""

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_get_fun_facts_success(self, mock_require_admin, mock_get_db):
        """Should return fun facts for confirmed/completed bookings."""
        mock_user = create_mock_user()
        mock_require_admin.return_value = mock_user

        # Create mock bookings
        mock_bookings = [
            create_mock_booking(id=1, dropoff_date=date(2026, 3, 15), pickup_date=date(2026, 3, 22), total_price=85.00),
            create_mock_booking(id=2, dropoff_date=date(2026, 3, 15), pickup_date=date(2026, 3, 25), total_price=120.00),
            create_mock_booking(id=3, dropoff_date=date(2026, 3, 16), pickup_date=date(2026, 3, 30), total_price=189.00),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings
        mock_get_db.return_value = iter([mock_db])

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "busiestDay" in data
        assert "busiestStreak" in data
        assert "longestTrip" in data
        assert "highestTransaction" in data

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_busiest_day_calculation(self, mock_require_admin, mock_get_db):
        """Should correctly identify busiest day."""
        mock_user = create_mock_user()
        mock_require_admin.return_value = mock_user

        # 3 bookings on Mar 15, 1 on Mar 16
        mock_bookings = [
            create_mock_booking(id=1, dropoff_date=date(2026, 3, 15)),
            create_mock_booking(id=2, dropoff_date=date(2026, 3, 15)),
            create_mock_booking(id=3, dropoff_date=date(2026, 3, 15)),
            create_mock_booking(id=4, dropoff_date=date(2026, 3, 16)),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings
        mock_get_db.return_value = iter([mock_db])

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["busiestDay"]["count"] == 3
        assert "15" in data["busiestDay"]["date"]  # Mar 15

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_longest_trip_calculation(self, mock_require_admin, mock_get_db):
        """Should correctly identify longest trip."""
        mock_user = create_mock_user()
        mock_require_admin.return_value = mock_user

        mock_bookings = [
            create_mock_booking(id=1, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 8), dropoff_destination="Faro"),   # 7 days
            create_mock_booking(id=2, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 22), dropoff_destination="Tenerife"),  # 21 days
            create_mock_booking(id=3, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 15), dropoff_destination="Malaga"),  # 14 days
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings
        mock_get_db.return_value = iter([mock_db])

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["longestTrip"]["days"] == 21
        assert data["longestTrip"]["destination"] == "Tenerife"

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_highest_transaction_calculation(self, mock_require_admin, mock_get_db):
        """Should correctly identify highest transaction."""
        mock_user = create_mock_user()
        mock_require_admin.return_value = mock_user

        mock_bookings = [
            create_mock_booking(id=1, total_price=85.00, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 8)),
            create_mock_booking(id=2, total_price=189.00, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 15)),
            create_mock_booking(id=3, total_price=120.00, dropoff_date=date(2026, 3, 1), pickup_date=date(2026, 3, 10)),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings
        mock_get_db.return_value = iter([mock_db])

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["highestTransaction"]["amount"] == "£189.00"
        assert data["highestTransaction"]["days"] == 14

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_busiest_streak_calculation(self, mock_require_admin, mock_get_db):
        """Should correctly calculate busiest streak."""
        mock_user = create_mock_user()
        mock_require_admin.return_value = mock_user

        # Create bookings on consecutive days: Mar 15, 16, 17, then gap, then Mar 20
        mock_bookings = [
            create_mock_booking(id=1, dropoff_date=date(2026, 3, 15)),
            create_mock_booking(id=2, dropoff_date=date(2026, 3, 16)),
            create_mock_booking(id=3, dropoff_date=date(2026, 3, 16)),
            create_mock_booking(id=4, dropoff_date=date(2026, 3, 17)),
            create_mock_booking(id=5, dropoff_date=date(2026, 3, 20)),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings
        mock_get_db.return_value = iter([mock_db])

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["busiestStreak"]["days"] == 3
        assert data["busiestStreak"]["bookings"] == 4  # 1 + 2 + 1 bookings


# =============================================================================
# Integration Tests - Empty/Null Cases
# =============================================================================

class TestFunFactsIntegrationEmptyCases:
    """Integration tests for empty and null scenarios."""

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_no_bookings_returns_null_values(self, mock_require_admin, mock_get_db):
        """Should return null values when no bookings exist."""
        mock_user = create_mock_user()
        mock_require_admin.return_value = mock_user

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_get_db.return_value = iter([mock_db])

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["busiestDay"] is None
        assert data["busiestStreak"] is None
        assert data["longestTrip"] is None
        assert data["highestTransaction"] is None

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_bookings_with_null_prices(self, mock_require_admin, mock_get_db):
        """Should handle bookings with null prices gracefully."""
        mock_user = create_mock_user()
        mock_require_admin.return_value = mock_user

        mock_bookings = [
            create_mock_booking(id=1, total_price=None, dropoff_date=date(2026, 3, 15), pickup_date=date(2026, 3, 22)),
            create_mock_booking(id=2, total_price=None, dropoff_date=date(2026, 3, 16), pickup_date=date(2026, 3, 23)),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings
        mock_get_db.return_value = iter([mock_db])

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()

        # Other fields should still work
        assert data["busiestDay"] is not None
        assert data["highestTransaction"] is None


# =============================================================================
# Integration Tests - Edge Cases
# =============================================================================

class TestFunFactsIntegrationEdgeCases:
    """Integration tests for edge cases."""

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_single_booking(self, mock_require_admin, mock_get_db):
        """Should handle single booking correctly."""
        mock_user = create_mock_user()
        mock_require_admin.return_value = mock_user

        mock_bookings = [
            create_mock_booking(
                id=1,
                dropoff_date=date(2026, 3, 15),
                pickup_date=date(2026, 3, 22),
                total_price=85.00,
                dropoff_destination="Faro"
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings
        mock_get_db.return_value = iter([mock_db])

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["busiestDay"]["count"] == 1
        assert data["busiestStreak"]["days"] == 1
        assert data["longestTrip"]["days"] == 7
        assert data["highestTransaction"]["amount"] == "£85.00"

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_missing_destination_shows_unknown(self, mock_require_admin, mock_get_db):
        """Should show 'Unknown' for missing destination."""
        mock_user = create_mock_user()
        mock_require_admin.return_value = mock_user

        mock_bookings = [
            create_mock_booking(
                id=1,
                dropoff_date=date(2026, 3, 1),
                pickup_date=date(2026, 3, 22),
                total_price=189.00,
                dropoff_destination=None
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings
        mock_get_db.return_value = iter([mock_db])

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["longestTrip"]["destination"] == "Unknown"

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_same_day_trip(self, mock_require_admin, mock_get_db):
        """Should handle same-day trips (0 days)."""
        mock_user = create_mock_user()
        mock_require_admin.return_value = mock_user

        mock_bookings = [
            create_mock_booking(
                id=1,
                dropoff_date=date(2026, 3, 15),
                pickup_date=date(2026, 3, 15),  # Same day
                total_price=50.00,
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings
        mock_get_db.return_value = iter([mock_db])

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["longestTrip"]["days"] == 0


# =============================================================================
# Integration Tests - Authentication
# =============================================================================

class TestFunFactsIntegrationAuth:
    """Integration tests for authentication requirements."""

    def test_requires_authentication(self):
        """Should require authentication."""
        response = client.get("/api/admin/reports/fun-facts")

        # Should return 401 or redirect for unauthenticated requests
        assert response.status_code in [401, 403, 422]

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_requires_admin_role(self, mock_require_admin, mock_get_db):
        """Should require admin role."""
        from fastapi import HTTPException

        # Simulate non-admin user
        mock_require_admin.side_effect = HTTPException(status_code=403, detail="Admin access required")

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 403


# =============================================================================
# Integration Tests - Date Formatting
# =============================================================================

class TestFunFactsIntegrationDateFormatting:
    """Integration tests for date formatting in response."""

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_busiest_day_date_format(self, mock_require_admin, mock_get_db):
        """Busiest day date should be in correct UK format."""
        mock_user = create_mock_user()
        mock_require_admin.return_value = mock_user

        mock_bookings = [
            create_mock_booking(id=1, dropoff_date=date(2026, 2, 24)),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings
        mock_get_db.return_value = iter([mock_db])

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should be like "Tue 24 Feb 2026"
        assert "Tue" in data["busiestDay"]["date"]
        assert "24" in data["busiestDay"]["date"]
        assert "Feb" in data["busiestDay"]["date"]
        assert "2026" in data["busiestDay"]["date"]

    @patch('main.get_db')
    @patch('main.require_admin')
    def test_streak_date_format(self, mock_require_admin, mock_get_db):
        """Streak dates should be in correct format."""
        mock_user = create_mock_user()
        mock_require_admin.return_value = mock_user

        mock_bookings = [
            create_mock_booking(id=1, dropoff_date=date(2026, 2, 24)),
            create_mock_booking(id=2, dropoff_date=date(2026, 2, 25)),
            create_mock_booking(id=3, dropoff_date=date(2026, 2, 26)),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = mock_bookings
        mock_get_db.return_value = iter([mock_db])

        response = client.get(
            "/api/admin/reports/fun-facts",
            headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()

        # startDate should be like "24 Feb"
        assert "24" in data["busiestStreak"]["startDate"]
        assert "Feb" in data["busiestStreak"]["startDate"]

        # endDate should include year like "26 Feb 2026"
        assert "26" in data["busiestStreak"]["endDate"]
        assert "Feb" in data["busiestStreak"]["endDate"]
        assert "2026" in data["busiestStreak"]["endDate"]
