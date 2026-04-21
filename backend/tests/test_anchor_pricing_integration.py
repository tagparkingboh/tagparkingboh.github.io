"""
Integration tests for anchor-based pricing API endpoints.

Tests cover:
- /api/pricing/calculate endpoint
- /api/pricing endpoint (admin pricing settings)
- /api/admin/pricing endpoint (update settings)
- End-to-end pricing workflow
- Happy paths, unhappy paths, edge cases, and boundary conditions

All tests use mocked database sessions to avoid external dependencies.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from decimal import Decimal
from fastapi.testclient import TestClient

# Import the FastAPI app
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import app

client = TestClient(app)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def default_pricing():
    """Default anchor pricing configuration."""
    return {
        "days_1_4_price": 65.0,       # 1-4 days anchor
        "week1_base_price": 85.0,     # 7 days anchor
        "week2_base_price": 150.0,    # 14 days anchor
        "daily_increment": 8.0,       # Daily increment between anchors
        "tier_increment": 5.0,        # Advance tier increment
        "peak_day_increment": 0.0,    # Peak day increment (Fri/Sat drop-off, Sun/Mon/Tue pickup)
    }


@pytest.fixture
def mock_db_session(default_pricing):
    """Mock get_pricing_from_db to return default pricing."""
    with patch('booking_service.get_pricing_from_db', return_value=default_pricing):
        yield default_pricing


# =============================================================================
# Integration Tests: /api/pricing/calculate - Happy Paths
# =============================================================================

class TestPricingCalculateEndpointHappy:
    """Happy path integration tests for pricing calculation endpoint."""

    def test_calculate_1_week_early_booking(self, mock_db_session):
        """Calculate price for 1 week, booked 20 days in advance."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=7)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        data = response.json()
        assert data["duration_days"] == 7
        assert data["advance_tier"] == "early"
        assert data["price"] == 85.0
        assert data["week1_price"] == 85.0

    def test_calculate_2_week_standard_booking(self, mock_db_session):
        """Calculate price for 2 weeks, booked 10 days in advance."""
        drop_off = date.today() + timedelta(days=10)
        pickup = drop_off + timedelta(days=14)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        data = response.json()
        assert data["duration_days"] == 14
        assert data["advance_tier"] == "standard"
        assert data["price"] == 155.0  # 150 + 5 tier increment

    def test_calculate_5_day_late_booking(self, mock_db_session):
        """Calculate price for 5 days, booked 3 days in advance."""
        drop_off = date.today() + timedelta(days=3)
        pickup = drop_off + timedelta(days=5)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        data = response.json()
        assert data["duration_days"] == 5
        assert data["advance_tier"] == "late"
        # 5 days = 65 + 8 = 73 base, + 10 late tier = 83
        assert data["price"] == 83.0

    def test_calculate_returns_all_prices(self, mock_db_session):
        """Response should include all tier prices for reference."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=7)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        data = response.json()
        assert "all_prices" in data
        assert data["all_prices"]["early"] == 85.0
        assert data["all_prices"]["standard"] == 90.0
        assert data["all_prices"]["late"] == 95.0

    def test_calculate_extended_stay_21_days(self, mock_db_session):
        """Calculate price for 21 days (3 weeks)."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=21)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        data = response.json()
        assert data["duration_days"] == 21
        # 21 days = 150 + 7*8 = 150 + 56 = 206
        assert data["price"] == 206.0
        assert data["package_name"] == "3 Week Trip"


# =============================================================================
# Integration Tests: /api/pricing/calculate - Boundary Cases
# =============================================================================

class TestPricingCalculateEndpointBoundaries:
    """Boundary integration tests for pricing calculation."""

    def test_minimum_duration_1_day(self, mock_db_session):
        """Minimum valid duration: 1 day."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=1)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        data = response.json()
        assert data["duration_days"] == 1
        assert data["price"] == 65.0

    def test_maximum_duration_60_days(self, mock_db_session):
        """Maximum valid duration: 60 days."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=60)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        data = response.json()
        assert data["duration_days"] == 60
        # 60 days = 150 + 46*8 = 150 + 368 = 518
        assert data["price"] == 518.0

    def test_advance_tier_boundary_14_days(self, mock_db_session):
        """Boundary: 14 days advance should be 'early' tier."""
        drop_off = date.today() + timedelta(days=14)
        pickup = drop_off + timedelta(days=7)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        data = response.json()
        assert data["advance_tier"] == "early"

    def test_advance_tier_boundary_13_days(self, mock_db_session):
        """Boundary: 13 days advance should be 'standard' tier."""
        drop_off = date.today() + timedelta(days=13)
        pickup = drop_off + timedelta(days=7)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        data = response.json()
        assert data["advance_tier"] == "standard"

    def test_advance_tier_boundary_7_days(self, mock_db_session):
        """Boundary: 7 days advance should be 'standard' tier."""
        drop_off = date.today() + timedelta(days=7)
        pickup = drop_off + timedelta(days=7)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        data = response.json()
        assert data["advance_tier"] == "standard"

    def test_advance_tier_boundary_6_days(self, mock_db_session):
        """Boundary: 6 days advance should be 'late' tier."""
        drop_off = date.today() + timedelta(days=6)
        pickup = drop_off + timedelta(days=7)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        data = response.json()
        assert data["advance_tier"] == "late"


# =============================================================================
# Integration Tests: /api/pricing/calculate - Unhappy Paths
# =============================================================================

class TestPricingCalculateEndpointUnhappy:
    """Unhappy path integration tests for error handling."""

    def test_zero_duration_returns_error(self, mock_db_session):
        """0 day duration should return 400 error."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off  # Same day = 0 duration

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 400
        assert "at least" in response.json()["detail"].lower() or "1" in response.json()["detail"]

    def test_negative_duration_returns_error(self, mock_db_session):
        """Negative duration should return 400 error."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off - timedelta(days=1)  # Pickup before drop-off

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 400

    def test_61_day_duration_returns_error(self, mock_db_session):
        """61 day duration should return 400 error."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=61)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 400
        assert "60" in response.json()["detail"]

    def test_missing_drop_off_date(self, mock_db_session):
        """Missing drop_off_date should return validation error."""
        response = client.post("/api/pricing/calculate", json={
            "pickup_date": (date.today() + timedelta(days=7)).isoformat(),
        })

        assert response.status_code == 422  # Validation error

    def test_missing_pickup_date(self, mock_db_session):
        """Missing pickup_date should return validation error."""
        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": date.today().isoformat(),
        })

        assert response.status_code == 422  # Validation error

    def test_invalid_date_format(self, mock_db_session):
        """Invalid date format should return validation error."""
        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": "not-a-date",
            "pickup_date": "also-not-a-date",
        })

        assert response.status_code == 422


# =============================================================================
# Integration Tests: Package Name Generation
# =============================================================================

class TestPackageNameGeneration:
    """Tests for package name generation in API response."""

    def test_1_day_package_name(self, mock_db_session):
        """1 day should show '1 Day'."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=1)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        assert response.json()["package_name"] == "1 Day"

    def test_5_days_package_name(self, mock_db_session):
        """5 days should show '5 Days'."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=5)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        assert response.json()["package_name"] == "5 Days"

    def test_7_days_package_name(self, mock_db_session):
        """7 days should show '1 Week Trip'."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=7)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        assert response.json()["package_name"] == "1 Week Trip"

    def test_14_days_package_name(self, mock_db_session):
        """14 days should show '2 Week Trip'."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=14)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        assert response.json()["package_name"] == "2 Week Trip"

    def test_21_days_package_name(self, mock_db_session):
        """21 days should show '3 Week Trip'."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=21)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        assert response.json()["package_name"] == "3 Week Trip"

    def test_10_days_package_name(self, mock_db_session):
        """10 days should show '10 Days'."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=10)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        assert response.json()["package_name"] == "10 Days"


# =============================================================================
# Integration Tests: Full Pricing Matrix Verification
# =============================================================================

class TestFullPricingMatrixIntegration:
    """Integration tests verifying full pricing matrix through API."""

    @pytest.mark.parametrize("duration,expected_early_price", [
        (1, 65.0), (2, 65.0), (3, 65.0), (4, 65.0),  # 1-4 days anchor
        (5, 73.0), (6, 81.0),                         # 1-4 + increments
        (7, 85.0),                                    # week1 anchor
        (8, 93.0), (9, 101.0), (10, 109.0),          # week1 + increments
        (11, 117.0), (12, 125.0), (13, 133.0),
        (14, 150.0),                                  # week2 anchor
        (15, 158.0), (16, 166.0), (17, 174.0),       # week2 + increments
        (18, 182.0), (19, 190.0), (20, 198.0), (21, 206.0),
    ])
    def test_early_tier_prices(self, mock_db_session, duration, expected_early_price):
        """Verify early tier prices for all durations 1-21."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=duration)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        assert response.json()["price"] == expected_early_price, (
            f"Duration {duration}: expected {expected_early_price}, got {response.json()['price']}"
        )

    @pytest.mark.parametrize("duration", [1, 5, 7, 10, 14, 21])
    def test_standard_tier_adds_5(self, mock_db_session, duration):
        """Standard tier should add $5 to early price."""
        early_drop_off = date.today() + timedelta(days=20)
        standard_drop_off = date.today() + timedelta(days=10)
        pickup_early = early_drop_off + timedelta(days=duration)
        pickup_standard = standard_drop_off + timedelta(days=duration)

        early_response = client.post("/api/pricing/calculate", json={
            "drop_off_date": early_drop_off.isoformat(),
            "pickup_date": pickup_early.isoformat(),
        })
        standard_response = client.post("/api/pricing/calculate", json={
            "drop_off_date": standard_drop_off.isoformat(),
            "pickup_date": pickup_standard.isoformat(),
        })

        assert early_response.status_code == 200
        assert standard_response.status_code == 200

        early_price = early_response.json()["price"]
        standard_price = standard_response.json()["price"]

        assert standard_price == early_price + 5.0

    @pytest.mark.parametrize("duration", [1, 5, 7, 10, 14, 21])
    def test_late_tier_adds_10(self, mock_db_session, duration):
        """Late tier should add $10 to early price."""
        early_drop_off = date.today() + timedelta(days=20)
        late_drop_off = date.today() + timedelta(days=3)
        pickup_early = early_drop_off + timedelta(days=duration)
        pickup_late = late_drop_off + timedelta(days=duration)

        early_response = client.post("/api/pricing/calculate", json={
            "drop_off_date": early_drop_off.isoformat(),
            "pickup_date": pickup_early.isoformat(),
        })
        late_response = client.post("/api/pricing/calculate", json={
            "drop_off_date": late_drop_off.isoformat(),
            "pickup_date": pickup_late.isoformat(),
        })

        assert early_response.status_code == 200
        assert late_response.status_code == 200

        early_price = early_response.json()["price"]
        late_price = late_response.json()["price"]

        assert late_price == early_price + 10.0


# =============================================================================
# Integration Tests: Price Pence Calculation
# =============================================================================

class TestPricePenceCalculation:
    """Tests for price_pence field in API response."""

    def test_price_pence_correct_for_whole_pounds(self, mock_db_session):
        """price_pence should be price * 100 for whole pounds."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=7)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        data = response.json()
        assert data["price"] == 85.0
        assert data["price_pence"] == 8500

    def test_price_pence_all_durations(self, mock_db_session):
        """price_pence should always be price * 100."""
        for duration in [1, 5, 7, 10, 14, 21, 30]:
            drop_off = date.today() + timedelta(days=20)
            pickup = drop_off + timedelta(days=duration)

            response = client.post("/api/pricing/calculate", json={
                "drop_off_date": drop_off.isoformat(),
                "pickup_date": pickup.isoformat(),
            })

            assert response.status_code == 200
            data = response.json()
            assert data["price_pence"] == int(data["price"] * 100)


# =============================================================================
# Integration Tests: Week1 Price for Promo Calculations
# =============================================================================

class TestWeek1PriceForPromo:
    """Tests for week1_price field used in free parking promo calculations."""

    def test_week1_price_present_in_response(self, mock_db_session):
        """week1_price should always be present in response."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=14)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        assert "week1_price" in response.json()

    def test_week1_price_equals_85(self, mock_db_session):
        """week1_price should be the early tier 7-day price ($85)."""
        drop_off = date.today() + timedelta(days=20)
        pickup = drop_off + timedelta(days=14)

        response = client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off.isoformat(),
            "pickup_date": pickup.isoformat(),
        })

        assert response.status_code == 200
        assert response.json()["week1_price"] == 85.0

    def test_week1_price_consistent_across_durations(self, mock_db_session):
        """week1_price should be consistent regardless of booking duration."""
        for duration in [1, 5, 7, 14, 21, 30]:
            drop_off = date.today() + timedelta(days=20)
            pickup = drop_off + timedelta(days=duration)

            response = client.post("/api/pricing/calculate", json={
                "drop_off_date": drop_off.isoformat(),
                "pickup_date": pickup.isoformat(),
            })

            assert response.status_code == 200
            assert response.json()["week1_price"] == 85.0


# =============================================================================
# Integration Tests: Legacy Package Field
# =============================================================================

class TestLegacyPackageField:
    """Tests for legacy 'package' field compatibility."""

    def test_1_to_7_days_returns_quick(self, mock_db_session):
        """1-7 days should return 'quick' package."""
        for duration in [1, 3, 5, 7]:
            drop_off = date.today() + timedelta(days=20)
            pickup = drop_off + timedelta(days=duration)

            response = client.post("/api/pricing/calculate", json={
                "drop_off_date": drop_off.isoformat(),
                "pickup_date": pickup.isoformat(),
            })

            assert response.status_code == 200
            assert response.json()["package"] == "quick"

    def test_8_to_60_days_returns_longer(self, mock_db_session):
        """8-60 days should return 'longer' package."""
        for duration in [8, 10, 14, 21, 30, 45, 60]:
            drop_off = date.today() + timedelta(days=20)
            pickup = drop_off + timedelta(days=duration)

            response = client.post("/api/pricing/calculate", json={
                "drop_off_date": drop_off.isoformat(),
                "pickup_date": pickup.isoformat(),
            })

            assert response.status_code == 200
            assert response.json()["package"] == "longer"
