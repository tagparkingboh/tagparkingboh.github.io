"""
Comprehensive unit and integration tests for dynamic pricing.

Tests cover:
- Boundary testing for advance booking tiers (0, 6, 7, 13, 14 days)
- All package types (quick/longer)
- Price calculation accuracy
- API endpoint validation
- Duration validation (7 or 14 days only)
"""
import pytest
from datetime import date, timedelta
from unittest.mock import patch

from booking_service import BookingService
from stripe_service import calculate_price_in_pence


# =============================================================================
# Unit Tests: BookingService.get_advance_tier()
# =============================================================================

class TestGetAdvanceTierBoundaries:
    """Boundary tests for advance booking tier determination."""

    def test_tier_at_exactly_14_days(self):
        """Exactly 14 days should be 'early' tier."""
        drop_off = date.today() + timedelta(days=14)
        assert BookingService.get_advance_tier(drop_off) == "early"

    def test_tier_at_15_days(self):
        """15 days should be 'early' tier."""
        drop_off = date.today() + timedelta(days=15)
        assert BookingService.get_advance_tier(drop_off) == "early"

    def test_tier_at_100_days(self):
        """100 days ahead should still be 'early' tier."""
        drop_off = date.today() + timedelta(days=100)
        assert BookingService.get_advance_tier(drop_off) == "early"

    def test_tier_at_exactly_13_days(self):
        """Exactly 13 days should be 'standard' tier (boundary: just under early)."""
        drop_off = date.today() + timedelta(days=13)
        assert BookingService.get_advance_tier(drop_off) == "standard"

    def test_tier_at_exactly_7_days(self):
        """Exactly 7 days should be 'standard' tier."""
        drop_off = date.today() + timedelta(days=7)
        assert BookingService.get_advance_tier(drop_off) == "standard"

    def test_tier_at_10_days(self):
        """10 days should be 'standard' tier (middle of range)."""
        drop_off = date.today() + timedelta(days=10)
        assert BookingService.get_advance_tier(drop_off) == "standard"

    def test_tier_at_exactly_6_days(self):
        """Exactly 6 days should be 'late' tier (boundary: just under standard)."""
        drop_off = date.today() + timedelta(days=6)
        assert BookingService.get_advance_tier(drop_off) == "late"

    def test_tier_at_1_day(self):
        """1 day ahead should be 'late' tier."""
        drop_off = date.today() + timedelta(days=1)
        assert BookingService.get_advance_tier(drop_off) == "late"

    def test_tier_at_0_days_same_day(self):
        """Same day booking should be 'late' tier."""
        drop_off = date.today()
        assert BookingService.get_advance_tier(drop_off) == "late"

    def test_tier_negative_days_past_date(self):
        """Past date should be 'late' tier (negative days)."""
        drop_off = date.today() - timedelta(days=1)
        assert BookingService.get_advance_tier(drop_off) == "late"


# =============================================================================
# Unit Tests: BookingService.calculate_price()
# =============================================================================

class TestCalculatePriceBoundaries:
    """Boundary tests for price calculation with all tier transitions."""

    # Quick package (1 week) tests
    def test_quick_early_at_14_days(self):
        """Quick package at exactly 14 days = early tier = £89."""
        drop_off = date.today() + timedelta(days=14)
        assert BookingService.calculate_price("quick", drop_off) == 89.0

    def test_quick_standard_at_13_days(self):
        """Quick package at exactly 13 days = standard tier = £99."""
        drop_off = date.today() + timedelta(days=13)
        assert BookingService.calculate_price("quick", drop_off) == 99.0

    def test_quick_standard_at_7_days(self):
        """Quick package at exactly 7 days = standard tier = £99."""
        drop_off = date.today() + timedelta(days=7)
        assert BookingService.calculate_price("quick", drop_off) == 99.0

    def test_quick_late_at_6_days(self):
        """Quick package at exactly 6 days = late tier = £109."""
        drop_off = date.today() + timedelta(days=6)
        assert BookingService.calculate_price("quick", drop_off) == 109.0

    def test_quick_late_at_0_days(self):
        """Quick package same day = late tier = £109."""
        drop_off = date.today()
        assert BookingService.calculate_price("quick", drop_off) == 109.0

    # Longer package (2 weeks) tests
    def test_longer_early_at_14_days(self):
        """Longer package at exactly 14 days = early tier = £140."""
        drop_off = date.today() + timedelta(days=14)
        assert BookingService.calculate_price("longer", drop_off) == 140.0

    def test_longer_standard_at_13_days(self):
        """Longer package at exactly 13 days = standard tier = £150."""
        drop_off = date.today() + timedelta(days=13)
        assert BookingService.calculate_price("longer", drop_off) == 150.0

    def test_longer_standard_at_7_days(self):
        """Longer package at exactly 7 days = standard tier = £150."""
        drop_off = date.today() + timedelta(days=7)
        assert BookingService.calculate_price("longer", drop_off) == 150.0

    def test_longer_late_at_6_days(self):
        """Longer package at exactly 6 days = late tier = £160."""
        drop_off = date.today() + timedelta(days=6)
        assert BookingService.calculate_price("longer", drop_off) == 160.0

    def test_longer_late_at_0_days(self):
        """Longer package same day = late tier = £160."""
        drop_off = date.today()
        assert BookingService.calculate_price("longer", drop_off) == 160.0


class TestCalculatePriceAllScenarios:
    """Test all 6 pricing scenarios (2 packages x 3 tiers)."""

    @pytest.mark.parametrize("days,expected_price", [
        (20, 89.0),   # Early
        (14, 89.0),   # Early boundary
        (13, 99.0),   # Standard boundary
        (10, 99.0),   # Standard middle
        (7, 99.0),    # Standard boundary
        (6, 109.0),   # Late boundary
        (3, 109.0),   # Late middle
        (0, 109.0),   # Same day
    ])
    def test_quick_package_prices(self, days, expected_price):
        """Test quick package pricing across all scenarios."""
        drop_off = date.today() + timedelta(days=days)
        assert BookingService.calculate_price("quick", drop_off) == expected_price

    @pytest.mark.parametrize("days,expected_price", [
        (20, 140.0),  # Early
        (14, 140.0),  # Early boundary
        (13, 150.0),  # Standard boundary
        (10, 150.0),  # Standard middle
        (7, 150.0),   # Standard boundary
        (6, 160.0),   # Late boundary
        (3, 160.0),   # Late middle
        (0, 160.0),   # Same day
    ])
    def test_longer_package_prices(self, days, expected_price):
        """Test longer package pricing across all scenarios."""
        drop_off = date.today() + timedelta(days=days)
        assert BookingService.calculate_price("longer", drop_off) == expected_price


# =============================================================================
# Unit Tests: BookingService.get_package_for_duration()
# =============================================================================

class TestGetPackageForDuration:
    """Tests for duration validation and package determination."""

    def test_7_days_returns_quick(self):
        """7 day duration should return 'quick' package."""
        drop_off = date.today()
        pickup = date.today() + timedelta(days=7)
        assert BookingService.get_package_for_duration(drop_off, pickup) == "quick"

    def test_14_days_returns_longer(self):
        """14 day duration should return 'longer' package."""
        drop_off = date.today()
        pickup = date.today() + timedelta(days=14)
        assert BookingService.get_package_for_duration(drop_off, pickup) == "longer"

    def test_6_days_raises_error(self):
        """6 day duration should raise ValueError."""
        drop_off = date.today()
        pickup = date.today() + timedelta(days=6)
        with pytest.raises(ValueError) as exc_info:
            BookingService.get_package_for_duration(drop_off, pickup)
        assert "6 days" in str(exc_info.value)
        assert "7 or 14" in str(exc_info.value)

    def test_8_days_raises_error(self):
        """8 day duration should raise ValueError."""
        drop_off = date.today()
        pickup = date.today() + timedelta(days=8)
        with pytest.raises(ValueError) as exc_info:
            BookingService.get_package_for_duration(drop_off, pickup)
        assert "8 days" in str(exc_info.value)

    def test_13_days_raises_error(self):
        """13 day duration should raise ValueError."""
        drop_off = date.today()
        pickup = date.today() + timedelta(days=13)
        with pytest.raises(ValueError) as exc_info:
            BookingService.get_package_for_duration(drop_off, pickup)
        assert "13 days" in str(exc_info.value)

    def test_15_days_raises_error(self):
        """15 day duration should raise ValueError."""
        drop_off = date.today()
        pickup = date.today() + timedelta(days=15)
        with pytest.raises(ValueError) as exc_info:
            BookingService.get_package_for_duration(drop_off, pickup)
        assert "15 days" in str(exc_info.value)

    def test_0_days_raises_error(self):
        """0 day duration (same day) should raise ValueError."""
        drop_off = date.today()
        pickup = date.today()
        with pytest.raises(ValueError) as exc_info:
            BookingService.get_package_for_duration(drop_off, pickup)
        assert "0 days" in str(exc_info.value)

    def test_negative_duration_raises_error(self):
        """Negative duration (pickup before dropoff) should raise ValueError."""
        drop_off = date.today()
        pickup = date.today() - timedelta(days=1)
        with pytest.raises(ValueError) as exc_info:
            BookingService.get_package_for_duration(drop_off, pickup)
        assert "-1 days" in str(exc_info.value)


# =============================================================================
# Unit Tests: calculate_price_in_pence() (Stripe integration)
# =============================================================================

class TestCalculatePriceInPence:
    """Tests for Stripe price calculation in pence."""

    def test_quick_early_in_pence(self):
        """Quick early = £89 = 8900 pence."""
        drop_off = date.today() + timedelta(days=20)
        assert calculate_price_in_pence("quick", drop_off_date=drop_off) == 8900

    def test_quick_standard_in_pence(self):
        """Quick standard = £99 = 9900 pence."""
        drop_off = date.today() + timedelta(days=10)
        assert calculate_price_in_pence("quick", drop_off_date=drop_off) == 9900

    def test_quick_late_in_pence(self):
        """Quick late = £109 = 10900 pence."""
        drop_off = date.today() + timedelta(days=3)
        assert calculate_price_in_pence("quick", drop_off_date=drop_off) == 10900

    def test_longer_early_in_pence(self):
        """Longer early = £140 = 14000 pence."""
        drop_off = date.today() + timedelta(days=20)
        assert calculate_price_in_pence("longer", drop_off_date=drop_off) == 14000

    def test_longer_standard_in_pence(self):
        """Longer standard = £150 = 15000 pence."""
        drop_off = date.today() + timedelta(days=10)
        assert calculate_price_in_pence("longer", drop_off_date=drop_off) == 15000

    def test_longer_late_in_pence(self):
        """Longer late = £160 = 16000 pence."""
        drop_off = date.today() + timedelta(days=3)
        assert calculate_price_in_pence("longer", drop_off_date=drop_off) == 16000

    def test_custom_price_override(self):
        """Custom price should override calculated price."""
        drop_off = date.today() + timedelta(days=20)  # Would be early tier
        assert calculate_price_in_pence("quick", drop_off_date=drop_off, custom_price=50.00) == 5000
        assert calculate_price_in_pence("longer", drop_off_date=drop_off, custom_price=75.50) == 7550

    def test_no_date_defaults_to_late(self):
        """Without drop_off_date, should default to late tier."""
        assert calculate_price_in_pence("quick") == 10900  # £109 late
        assert calculate_price_in_pence("longer") == 16000  # £160 late

    def test_boundary_14_days_in_pence(self):
        """Boundary: exactly 14 days = early tier."""
        drop_off = date.today() + timedelta(days=14)
        assert calculate_price_in_pence("quick", drop_off_date=drop_off) == 8900

    def test_boundary_13_days_in_pence(self):
        """Boundary: exactly 13 days = standard tier."""
        drop_off = date.today() + timedelta(days=13)
        assert calculate_price_in_pence("quick", drop_off_date=drop_off) == 9900

    def test_boundary_7_days_in_pence(self):
        """Boundary: exactly 7 days = standard tier."""
        drop_off = date.today() + timedelta(days=7)
        assert calculate_price_in_pence("quick", drop_off_date=drop_off) == 9900

    def test_boundary_6_days_in_pence(self):
        """Boundary: exactly 6 days = late tier."""
        drop_off = date.today() + timedelta(days=6)
        assert calculate_price_in_pence("quick", drop_off_date=drop_off) == 10900


# =============================================================================
# Integration Tests: Pricing API Endpoints
# =============================================================================

class TestPricingCalculateEndpoint:
    """Integration tests for POST /api/pricing/calculate endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from httpx import AsyncClient, ASGITransport
        from main import app
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_calculate_quick_early(self, client):
        """1 week package, 14+ days ahead = £89."""
        drop_off = (date.today() + timedelta(days=20)).isoformat()
        pickup = (date.today() + timedelta(days=27)).isoformat()  # 7 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["package"] == "quick"
        assert data["package_name"] == "1 Week"
        assert data["duration_days"] == 7
        assert data["advance_tier"] == "early"
        assert data["price"] == 89.0
        assert data["price_pence"] == 8900

    @pytest.mark.asyncio
    async def test_calculate_quick_standard(self, client):
        """1 week package, 7-13 days ahead = £99."""
        drop_off = (date.today() + timedelta(days=10)).isoformat()
        pickup = (date.today() + timedelta(days=17)).isoformat()  # 7 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["package"] == "quick"
        assert data["advance_tier"] == "standard"
        assert data["price"] == 99.0

    @pytest.mark.asyncio
    async def test_calculate_quick_late(self, client):
        """1 week package, <7 days ahead = £109."""
        drop_off = (date.today() + timedelta(days=3)).isoformat()
        pickup = (date.today() + timedelta(days=10)).isoformat()  # 7 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["package"] == "quick"
        assert data["advance_tier"] == "late"
        assert data["price"] == 109.0

    @pytest.mark.asyncio
    async def test_calculate_longer_early(self, client):
        """2 week package, 14+ days ahead = £140."""
        drop_off = (date.today() + timedelta(days=20)).isoformat()
        pickup = (date.today() + timedelta(days=34)).isoformat()  # 14 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["package"] == "longer"
        assert data["package_name"] == "2 Weeks"
        assert data["duration_days"] == 14
        assert data["advance_tier"] == "early"
        assert data["price"] == 140.0
        assert data["price_pence"] == 14000

    @pytest.mark.asyncio
    async def test_calculate_longer_standard(self, client):
        """2 week package, 7-13 days ahead = £150."""
        drop_off = (date.today() + timedelta(days=10)).isoformat()
        pickup = (date.today() + timedelta(days=24)).isoformat()  # 14 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["package"] == "longer"
        assert data["advance_tier"] == "standard"
        assert data["price"] == 150.0

    @pytest.mark.asyncio
    async def test_calculate_longer_late(self, client):
        """2 week package, <7 days ahead = £160."""
        drop_off = (date.today() + timedelta(days=3)).isoformat()
        pickup = (date.today() + timedelta(days=17)).isoformat()  # 14 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["package"] == "longer"
        assert data["advance_tier"] == "late"
        assert data["price"] == 160.0

    @pytest.mark.asyncio
    async def test_calculate_invalid_duration_6_days(self, client):
        """6 day duration should return 400 error."""
        drop_off = (date.today() + timedelta(days=10)).isoformat()
        pickup = (date.today() + timedelta(days=16)).isoformat()  # 6 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 400
        assert "6 days" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_calculate_invalid_duration_8_days(self, client):
        """8 day duration should return 400 error."""
        drop_off = (date.today() + timedelta(days=10)).isoformat()
        pickup = (date.today() + timedelta(days=18)).isoformat()  # 8 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 400
        assert "8 days" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_calculate_invalid_duration_21_days(self, client):
        """21 day duration (3 weeks) should return 400 error."""
        drop_off = (date.today() + timedelta(days=10)).isoformat()
        pickup = (date.today() + timedelta(days=31)).isoformat()  # 21 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 400
        assert "21 days" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_calculate_boundary_exactly_14_days_advance(self, client):
        """Boundary: exactly 14 days advance = early tier."""
        drop_off = (date.today() + timedelta(days=14)).isoformat()
        pickup = (date.today() + timedelta(days=21)).isoformat()  # 7 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["advance_tier"] == "early"
        assert data["days_in_advance"] == 14
        assert data["price"] == 89.0

    @pytest.mark.asyncio
    async def test_calculate_boundary_exactly_13_days_advance(self, client):
        """Boundary: exactly 13 days advance = standard tier."""
        drop_off = (date.today() + timedelta(days=13)).isoformat()
        pickup = (date.today() + timedelta(days=20)).isoformat()  # 7 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["advance_tier"] == "standard"
        assert data["days_in_advance"] == 13
        assert data["price"] == 99.0

    @pytest.mark.asyncio
    async def test_calculate_boundary_exactly_7_days_advance(self, client):
        """Boundary: exactly 7 days advance = standard tier."""
        drop_off = (date.today() + timedelta(days=7)).isoformat()
        pickup = (date.today() + timedelta(days=14)).isoformat()  # 7 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["advance_tier"] == "standard"
        assert data["days_in_advance"] == 7
        assert data["price"] == 99.0

    @pytest.mark.asyncio
    async def test_calculate_boundary_exactly_6_days_advance(self, client):
        """Boundary: exactly 6 days advance = late tier."""
        drop_off = (date.today() + timedelta(days=6)).isoformat()
        pickup = (date.today() + timedelta(days=13)).isoformat()  # 7 days later

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["advance_tier"] == "late"
        assert data["days_in_advance"] == 6
        assert data["price"] == 109.0

    @pytest.mark.asyncio
    async def test_calculate_includes_all_prices(self, client):
        """Response should include all tier prices for reference."""
        drop_off = (date.today() + timedelta(days=10)).isoformat()
        pickup = (date.today() + timedelta(days=17)).isoformat()

        response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert response.status_code == 200
        data = response.json()
        assert "all_prices" in data
        assert data["all_prices"]["early"] == 89.0
        assert data["all_prices"]["standard"] == 99.0
        assert data["all_prices"]["late"] == 109.0


class TestPricingTiersEndpoint:
    """Integration tests for GET /api/pricing/tiers endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from httpx import AsyncClient, ASGITransport
        from main import app
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_get_all_tiers(self, client):
        """Should return all pricing tiers for both packages."""
        response = await client.get("/api/pricing/tiers")

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "packages" in data
        assert "quick" in data["packages"]
        assert "longer" in data["packages"]

        # Check quick package prices (nested under "prices" key)
        assert data["packages"]["quick"]["prices"]["early"] == 89.0
        assert data["packages"]["quick"]["prices"]["standard"] == 99.0
        assert data["packages"]["quick"]["prices"]["late"] == 109.0

        # Check longer package prices (nested under "prices" key)
        assert data["packages"]["longer"]["prices"]["early"] == 140.0
        assert data["packages"]["longer"]["prices"]["standard"] == 150.0
        assert data["packages"]["longer"]["prices"]["late"] == 160.0

    @pytest.mark.asyncio
    async def test_tiers_include_tier_descriptions(self, client):
        """Should include descriptions of each tier."""
        response = await client.get("/api/pricing/tiers")

        assert response.status_code == 200
        data = response.json()

        assert "tiers" in data
        assert "early" in data["tiers"]
        assert "standard" in data["tiers"]
        assert "late" in data["tiers"]


# =============================================================================
# Integration Tests: End-to-End Pricing Flow
# =============================================================================

class TestEndToEndPricingFlow:
    """End-to-end tests verifying pricing through booking flow."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from httpx import AsyncClient, ASGITransport
        from main import app
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_pricing_matches_between_calculate_and_tiers(self, client):
        """Prices from /calculate should match /tiers."""
        # Get all tiers
        tiers_response = await client.get("/api/pricing/tiers")
        tiers = tiers_response.json()

        # Test early tier for quick
        drop_off = (date.today() + timedelta(days=20)).isoformat()
        pickup = (date.today() + timedelta(days=27)).isoformat()

        calc_response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert calc_response.json()["price"] == tiers["packages"]["quick"]["prices"]["early"]

        # Test late tier for longer
        drop_off = (date.today() + timedelta(days=3)).isoformat()
        pickup = (date.today() + timedelta(days=17)).isoformat()

        calc_response = await client.post("/api/pricing/calculate", json={
            "drop_off_date": drop_off,
            "pickup_date": pickup,
        })

        assert calc_response.json()["price"] == tiers["packages"]["longer"]["prices"]["late"]

    @pytest.mark.asyncio
    async def test_all_six_pricing_scenarios(self, client):
        """Verify all 6 pricing scenarios (2 packages x 3 tiers) via API."""
        scenarios = [
            # (days_advance, duration, expected_package, expected_tier, expected_price)
            (20, 7, "quick", "early", 89.0),
            (10, 7, "quick", "standard", 99.0),
            (3, 7, "quick", "late", 109.0),
            (20, 14, "longer", "early", 140.0),
            (10, 14, "longer", "standard", 150.0),
            (3, 14, "longer", "late", 160.0),
        ]

        for days_advance, duration, expected_package, expected_tier, expected_price in scenarios:
            drop_off = (date.today() + timedelta(days=days_advance)).isoformat()
            pickup = (date.today() + timedelta(days=days_advance + duration)).isoformat()

            response = await client.post("/api/pricing/calculate", json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            })

            assert response.status_code == 200, f"Failed for {days_advance}d advance, {duration}d duration"
            data = response.json()
            assert data["package"] == expected_package, f"Wrong package for {days_advance}d, {duration}d"
            assert data["advance_tier"] == expected_tier, f"Wrong tier for {days_advance}d, {duration}d"
            assert data["price"] == expected_price, f"Wrong price for {days_advance}d, {duration}d"


# =============================================================================
# Unit Tests: Dynamic Pricing from Database
# =============================================================================

class TestGetPricingFromDb:
    """Tests for get_pricing_from_db() function."""

    def test_returns_defaults_when_no_database_url(self):
        """Should return defaults when DATABASE_URL is not set."""
        import os
        from booking_service import get_pricing_from_db

        # Save original and clear
        original = os.environ.get("DATABASE_URL")
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

        try:
            pricing = get_pricing_from_db()
            assert pricing["week1_base_price"] == 89.0
            assert pricing["week2_base_price"] == 140.0
            assert pricing["tier_increment"] == 10.0
        finally:
            # Restore
            if original:
                os.environ["DATABASE_URL"] = original

    def test_returns_defaults_on_connection_error(self):
        """Should return defaults when database connection fails."""
        import os
        from booking_service import get_pricing_from_db

        # Save original and set invalid URL
        original = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "postgresql://invalid:invalid@localhost:9999/invalid"

        try:
            pricing = get_pricing_from_db()
            # Should gracefully fall back to defaults
            assert pricing["week1_base_price"] == 89.0
            assert pricing["week2_base_price"] == 140.0
            assert pricing["tier_increment"] == 10.0
        finally:
            # Restore
            if original:
                os.environ["DATABASE_URL"] = original
            else:
                del os.environ["DATABASE_URL"]


class TestGetPackagePrices:
    """Tests for BookingService.get_package_prices() dynamic pricing."""

    def test_returns_dict_with_correct_structure(self):
        """Should return dict with quick and longer packages, each with 3 tiers."""
        prices = BookingService.get_package_prices()

        assert "quick" in prices
        assert "longer" in prices

        for package in ["quick", "longer"]:
            assert "early" in prices[package]
            assert "standard" in prices[package]
            assert "late" in prices[package]

    def test_tier_increment_applied_correctly(self):
        """Standard = base + increment, Late = base + 2*increment."""
        prices = BookingService.get_package_prices()

        # Quick package
        quick_base = prices["quick"]["early"]
        quick_increment = prices["quick"]["standard"] - quick_base
        assert prices["quick"]["late"] == quick_base + (quick_increment * 2)

        # Longer package
        longer_base = prices["longer"]["early"]
        longer_increment = prices["longer"]["standard"] - longer_base
        assert prices["longer"]["late"] == longer_base + (longer_increment * 2)

    def test_prices_are_positive_numbers(self):
        """All prices should be positive numbers."""
        prices = BookingService.get_package_prices()

        for package in ["quick", "longer"]:
            for tier in ["early", "standard", "late"]:
                assert isinstance(prices[package][tier], (int, float))
                assert prices[package][tier] > 0

    def test_longer_prices_greater_than_quick(self):
        """2-week prices should be greater than 1-week prices at each tier."""
        prices = BookingService.get_package_prices()

        for tier in ["early", "standard", "late"]:
            assert prices["longer"][tier] > prices["quick"][tier]


class TestDynamicPricingWithMock:
    """Tests for dynamic pricing with mocked database values."""

    def test_custom_prices_from_database(self):
        """Should use custom prices when fetched from database."""
        custom_pricing = {
            "week1_base_price": 100.0,
            "week2_base_price": 180.0,
            "tier_increment": 15.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            prices = BookingService.get_package_prices()

            # Quick package with £15 increment
            assert prices["quick"]["early"] == 100.0
            assert prices["quick"]["standard"] == 115.0  # 100 + 15
            assert prices["quick"]["late"] == 130.0      # 100 + 30

            # Longer package with £15 increment
            assert prices["longer"]["early"] == 180.0
            assert prices["longer"]["standard"] == 195.0  # 180 + 15
            assert prices["longer"]["late"] == 210.0      # 180 + 30

    def test_calculate_price_uses_dynamic_pricing(self):
        """calculate_price() should use dynamic prices from database."""
        custom_pricing = {
            "week1_base_price": 75.0,
            "week2_base_price": 125.0,
            "tier_increment": 20.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            # Test early tier (14+ days)
            early_date = date.today() + timedelta(days=20)
            assert BookingService.calculate_price("quick", early_date) == 75.0
            assert BookingService.calculate_price("longer", early_date) == 125.0

            # Test standard tier (7-13 days)
            standard_date = date.today() + timedelta(days=10)
            assert BookingService.calculate_price("quick", standard_date) == 95.0   # 75 + 20
            assert BookingService.calculate_price("longer", standard_date) == 145.0  # 125 + 20

            # Test late tier (<7 days)
            late_date = date.today() + timedelta(days=3)
            assert BookingService.calculate_price("quick", late_date) == 115.0   # 75 + 40
            assert BookingService.calculate_price("longer", late_date) == 165.0  # 125 + 40

    def test_zero_tier_increment(self):
        """Edge case: tier increment of 0 means all tiers same price."""
        custom_pricing = {
            "week1_base_price": 99.0,
            "week2_base_price": 149.0,
            "tier_increment": 0.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            prices = BookingService.get_package_prices()

            # All quick tiers should be same
            assert prices["quick"]["early"] == 99.0
            assert prices["quick"]["standard"] == 99.0
            assert prices["quick"]["late"] == 99.0

            # All longer tiers should be same
            assert prices["longer"]["early"] == 149.0
            assert prices["longer"]["standard"] == 149.0
            assert prices["longer"]["late"] == 149.0

    def test_large_tier_increment(self):
        """Edge case: large tier increment."""
        custom_pricing = {
            "week1_base_price": 50.0,
            "week2_base_price": 100.0,
            "tier_increment": 50.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            prices = BookingService.get_package_prices()

            assert prices["quick"]["early"] == 50.0
            assert prices["quick"]["standard"] == 100.0  # 50 + 50
            assert prices["quick"]["late"] == 150.0      # 50 + 100


# =============================================================================
# Integration Tests: Public Pricing API
# =============================================================================

class TestPublicPricingEndpoint:
    """Integration tests for GET /api/pricing public endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from httpx import AsyncClient, ASGITransport
        from main import app
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_get_public_pricing_returns_all_fields(self, client):
        """Public endpoint should return week1, week2, and tier_increment."""
        response = await client.get("/api/pricing")

        assert response.status_code == 200
        data = response.json()

        assert "week1_base_price" in data
        assert "week2_base_price" in data
        assert "tier_increment" in data

    @pytest.mark.asyncio
    async def test_get_public_pricing_returns_positive_numbers(self, client):
        """All pricing values should be positive numbers."""
        response = await client.get("/api/pricing")

        assert response.status_code == 200
        data = response.json()

        assert data["week1_base_price"] > 0
        assert data["week2_base_price"] > 0
        assert data["tier_increment"] >= 0

    @pytest.mark.asyncio
    async def test_public_pricing_no_auth_required(self, client):
        """Public pricing endpoint should not require authentication."""
        response = await client.get("/api/pricing")
        # Should not return 401 or 403
        assert response.status_code == 200


# =============================================================================
# Integration Tests: Admin Pricing API
# =============================================================================

class TestAdminPricingEndpoint:
    """Integration tests for admin pricing endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from httpx import AsyncClient, ASGITransport
        from main import app
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_get_admin_pricing_requires_auth(self, client):
        """Admin pricing endpoint should require authentication."""
        response = await client.get("/api/admin/pricing")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_put_admin_pricing_requires_auth(self, client):
        """Updating pricing should require authentication."""
        response = await client.put("/api/admin/pricing", json={
            "week1_base_price": 100.0,
            "week2_base_price": 160.0,
            "tier_increment": 15.0,
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_put_admin_pricing_invalid_data(self, client):
        """Should reject invalid pricing data."""
        # Missing fields
        response = await client.put("/api/admin/pricing", json={
            "week1_base_price": 100.0,
            # Missing week2_base_price and tier_increment
        })
        assert response.status_code in [401, 422]  # 401 for auth, 422 for validation


class TestAdminPricingValidation:
    """Tests for pricing update validation."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from httpx import AsyncClient, ASGITransport
        from main import app
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_pricing_update_requires_all_fields(self, client):
        """Update should require all three pricing fields."""
        # Without auth, but testing validation
        test_cases = [
            {"week1_base_price": 100},  # Missing 2 fields
            {"week2_base_price": 160},  # Missing 2 fields
            {"tier_increment": 10},     # Missing 2 fields
            {"week1_base_price": 100, "week2_base_price": 160},  # Missing 1 field
        ]

        for test_case in test_cases:
            response = await client.put("/api/admin/pricing", json=test_case)
            # Should fail with either auth error or validation error
            assert response.status_code in [401, 422]


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestPricingEdgeCases:
    """Edge case tests for pricing system."""

    def test_decimal_prices(self):
        """Should handle decimal prices correctly."""
        custom_pricing = {
            "week1_base_price": 89.99,
            "week2_base_price": 139.50,
            "tier_increment": 9.99,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            prices = BookingService.get_package_prices()

            assert prices["quick"]["early"] == 89.99
            assert abs(prices["quick"]["standard"] - 99.98) < 0.01  # 89.99 + 9.99

    def test_very_small_increment(self):
        """Should handle very small increments."""
        custom_pricing = {
            "week1_base_price": 100.0,
            "week2_base_price": 150.0,
            "tier_increment": 0.01,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            prices = BookingService.get_package_prices()

            assert prices["quick"]["early"] == 100.0
            assert prices["quick"]["standard"] == 100.01
            assert prices["quick"]["late"] == 100.02

    def test_prices_consistent_across_calls(self):
        """Multiple calls should return consistent prices."""
        prices1 = BookingService.get_package_prices()
        prices2 = BookingService.get_package_prices()

        assert prices1 == prices2

    def test_calculate_price_invalid_package(self):
        """Should raise KeyError for invalid package name."""
        drop_off = date.today() + timedelta(days=10)

        with pytest.raises(KeyError):
            BookingService.calculate_price("invalid_package", drop_off)

        with pytest.raises(KeyError):
            BookingService.calculate_price("", drop_off)


# =============================================================================
# Stripe Integration with Dynamic Pricing
# =============================================================================

class TestStripeWithDynamicPricing:
    """Tests for Stripe price calculation with dynamic pricing."""

    def test_calculate_price_in_pence_uses_dynamic_pricing(self):
        """calculate_price_in_pence should use dynamic prices."""
        custom_pricing = {
            "week1_base_price": 100.0,
            "week2_base_price": 175.0,
            "tier_increment": 25.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            drop_off = date.today() + timedelta(days=20)  # Early tier

            # Quick early = £100 = 10000 pence
            assert calculate_price_in_pence("quick", drop_off_date=drop_off) == 10000

            # Longer early = £175 = 17500 pence
            assert calculate_price_in_pence("longer", drop_off_date=drop_off) == 17500

    def test_custom_price_overrides_dynamic_pricing(self):
        """Custom price should override even dynamic pricing."""
        custom_pricing = {
            "week1_base_price": 100.0,
            "week2_base_price": 175.0,
            "tier_increment": 25.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            drop_off = date.today() + timedelta(days=20)

            # Custom price should override
            assert calculate_price_in_pence("quick", drop_off_date=drop_off, custom_price=50.0) == 5000
            assert calculate_price_in_pence("longer", drop_off_date=drop_off, custom_price=80.0) == 8000


# =============================================================================
# End-to-End Integration Tests: Full Booking Flow with Dynamic Pricing
# =============================================================================

class TestFullBookingFlowWithDynamicPricing:
    """
    End-to-end tests verifying dynamic pricing flows through the entire
    booking journey from Admin settings to Stripe payment amount.
    """

    @pytest.fixture
    def client(self):
        """Create test client."""
        from httpx import AsyncClient, ASGITransport
        from main import app
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_dynamic_pricing_flows_to_payment_calculation(self, client):
        """
        Verify that dynamic pricing from get_package_prices() flows through
        to calculate_price_in_pence() used in payment creation.
        """
        # Custom pricing: £100 base, £15 increment
        custom_pricing = {
            "week1_base_price": 100.0,
            "week2_base_price": 175.0,
            "tier_increment": 15.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            # Test early tier (14+ days advance)
            drop_off = date.today() + timedelta(days=20)

            # 1. Verify calculate_price returns custom price
            price = BookingService.calculate_price("quick", drop_off)
            assert price == 100.0, "calculate_price should use custom base price"

            # 2. Verify calculate_price_in_pence returns correct pence
            price_pence = calculate_price_in_pence("quick", drop_off_date=drop_off)
            assert price_pence == 10000, "calculate_price_in_pence should return 10000 pence (£100)"

            # 3. Verify standard tier (7-13 days) uses increment
            standard_date = date.today() + timedelta(days=10)
            standard_price = BookingService.calculate_price("quick", standard_date)
            assert standard_price == 115.0, "Standard tier should be base + increment (100 + 15)"

            standard_pence = calculate_price_in_pence("quick", drop_off_date=standard_date)
            assert standard_pence == 11500, "Standard tier should be 11500 pence (£115)"

            # 4. Verify late tier (<7 days) uses 2x increment
            late_date = date.today() + timedelta(days=3)
            late_price = BookingService.calculate_price("quick", late_date)
            assert late_price == 130.0, "Late tier should be base + 2*increment (100 + 30)"

            late_pence = calculate_price_in_pence("quick", drop_off_date=late_date)
            assert late_pence == 13000, "Late tier should be 13000 pence (£130)"

    @pytest.mark.asyncio
    async def test_pricing_api_uses_dynamic_prices(self, client):
        """
        Verify /api/pricing/calculate endpoint uses dynamic pricing.
        """
        custom_pricing = {
            "week1_base_price": 95.0,
            "week2_base_price": 155.0,
            "tier_increment": 12.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            # 1 week, early tier
            drop_off = (date.today() + timedelta(days=20)).isoformat()
            pickup = (date.today() + timedelta(days=27)).isoformat()

            response = await client.post("/api/pricing/calculate", json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            })

            assert response.status_code == 200
            data = response.json()

            # Should use custom pricing
            assert data["price"] == 95.0, "API should return custom early price"
            assert data["price_pence"] == 9500, "API should return correct pence"
            assert data["all_prices"]["early"] == 95.0
            assert data["all_prices"]["standard"] == 107.0  # 95 + 12
            assert data["all_prices"]["late"] == 119.0      # 95 + 24

    @pytest.mark.asyncio
    async def test_pricing_tiers_endpoint_uses_dynamic_prices(self, client):
        """
        Verify /api/pricing/tiers endpoint uses dynamic pricing.
        """
        custom_pricing = {
            "week1_base_price": 80.0,
            "week2_base_price": 130.0,
            "tier_increment": 20.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            response = await client.get("/api/pricing/tiers")

            assert response.status_code == 200
            data = response.json()

            # Check quick package uses custom prices
            assert data["packages"]["quick"]["prices"]["early"] == 80.0
            assert data["packages"]["quick"]["prices"]["standard"] == 100.0  # 80 + 20
            assert data["packages"]["quick"]["prices"]["late"] == 120.0      # 80 + 40

            # Check longer package uses custom prices
            assert data["packages"]["longer"]["prices"]["early"] == 130.0
            assert data["packages"]["longer"]["prices"]["standard"] == 150.0  # 130 + 20
            assert data["packages"]["longer"]["prices"]["late"] == 170.0      # 130 + 40

    @pytest.mark.asyncio
    async def test_public_pricing_endpoint_uses_dynamic_prices(self, client):
        """
        Verify /api/pricing (public endpoint) returns dynamic prices.
        """
        custom_pricing = {
            "week1_base_price": 99.0,
            "week2_base_price": 169.0,
            "tier_increment": 15.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            response = await client.get("/api/pricing")

            assert response.status_code == 200
            data = response.json()

            assert data["week1_base_price"] == 99.0
            assert data["week2_base_price"] == 169.0
            assert data["tier_increment"] == 15.0

    @pytest.mark.asyncio
    async def test_all_endpoints_consistent_with_same_pricing(self, client):
        """
        Verify all pricing endpoints return consistent prices when
        using the same dynamic pricing configuration.
        """
        custom_pricing = {
            "week1_base_price": 85.0,
            "week2_base_price": 145.0,
            "tier_increment": 10.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            # Get from public endpoint
            public_response = await client.get("/api/pricing")
            public_data = public_response.json()

            # Get from tiers endpoint
            tiers_response = await client.get("/api/pricing/tiers")
            tiers_data = tiers_response.json()

            # Get from calculate endpoint
            drop_off = (date.today() + timedelta(days=20)).isoformat()
            pickup = (date.today() + timedelta(days=27)).isoformat()
            calc_response = await client.post("/api/pricing/calculate", json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            })
            calc_data = calc_response.json()

            # All should be consistent
            assert public_data["week1_base_price"] == 85.0
            assert tiers_data["packages"]["quick"]["prices"]["early"] == 85.0
            assert calc_data["price"] == 85.0
            assert calc_data["all_prices"]["early"] == 85.0

    @pytest.mark.asyncio
    async def test_price_change_reflects_immediately(self, client):
        """
        Verify that a price change is reflected immediately in subsequent requests.
        """
        # First pricing configuration
        pricing_v1 = {
            "week1_base_price": 89.0,
            "week2_base_price": 140.0,
            "tier_increment": 10.0,
        }

        # Updated pricing configuration
        pricing_v2 = {
            "week1_base_price": 99.0,
            "week2_base_price": 160.0,
            "tier_increment": 15.0,
        }

        drop_off = (date.today() + timedelta(days=20)).isoformat()
        pickup = (date.today() + timedelta(days=27)).isoformat()

        # First request with v1 pricing
        with patch("booking_service.get_pricing_from_db", return_value=pricing_v1):
            response1 = await client.post("/api/pricing/calculate", json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            })
            assert response1.json()["price"] == 89.0

        # Second request with v2 pricing (simulating admin update)
        with patch("booking_service.get_pricing_from_db", return_value=pricing_v2):
            response2 = await client.post("/api/pricing/calculate", json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            })
            assert response2.json()["price"] == 99.0

    @pytest.mark.asyncio
    async def test_longer_package_pricing_flow(self, client):
        """
        Verify 2-week package uses dynamic pricing correctly.
        """
        custom_pricing = {
            "week1_base_price": 90.0,
            "week2_base_price": 150.0,
            "tier_increment": 10.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            # 2 weeks, late tier (3 days advance)
            drop_off = (date.today() + timedelta(days=3)).isoformat()
            pickup = (date.today() + timedelta(days=17)).isoformat()  # 14 days

            response = await client.post("/api/pricing/calculate", json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            })

            assert response.status_code == 200
            data = response.json()

            assert data["package"] == "longer"
            assert data["advance_tier"] == "late"
            # Late tier = base + 2*increment = 150 + 20 = 170
            assert data["price"] == 170.0
            assert data["price_pence"] == 17000


class TestDynamicPricingBoundaryConditions:
    """
    Test boundary conditions with dynamic pricing to ensure
    tier calculations work correctly at edges.
    """

    def test_tier_boundaries_with_custom_increment(self):
        """Test tier boundaries still work with custom increment."""
        custom_pricing = {
            "week1_base_price": 100.0,
            "week2_base_price": 180.0,
            "tier_increment": 25.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            # Boundary: exactly 14 days = early
            day_14 = date.today() + timedelta(days=14)
            assert BookingService.calculate_price("quick", day_14) == 100.0

            # Boundary: exactly 13 days = standard
            day_13 = date.today() + timedelta(days=13)
            assert BookingService.calculate_price("quick", day_13) == 125.0  # 100 + 25

            # Boundary: exactly 7 days = standard
            day_7 = date.today() + timedelta(days=7)
            assert BookingService.calculate_price("quick", day_7) == 125.0

            # Boundary: exactly 6 days = late
            day_6 = date.today() + timedelta(days=6)
            assert BookingService.calculate_price("quick", day_6) == 150.0  # 100 + 50

    def test_same_day_booking_uses_late_tier(self):
        """Same day booking should use late tier with custom pricing."""
        custom_pricing = {
            "week1_base_price": 75.0,
            "week2_base_price": 125.0,
            "tier_increment": 20.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            today = date.today()
            # Late tier = 75 + 40 = 115
            assert BookingService.calculate_price("quick", today) == 115.0

    def test_far_future_booking_uses_early_tier(self):
        """Booking 6 months ahead should use early tier."""
        custom_pricing = {
            "week1_base_price": 85.0,
            "week2_base_price": 145.0,
            "tier_increment": 12.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            far_future = date.today() + timedelta(days=180)
            assert BookingService.calculate_price("quick", far_future) == 85.0
            assert BookingService.calculate_price("longer", far_future) == 145.0


class TestDynamicPricingWithPromoCode:
    """
    Test that promo code discounts are applied correctly
    on top of dynamic pricing.
    """

    def test_promo_discount_applied_to_dynamic_price(self):
        """10% promo discount should apply to dynamic price."""
        custom_pricing = {
            "week1_base_price": 100.0,
            "week2_base_price": 160.0,
            "tier_increment": 10.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            drop_off = date.today() + timedelta(days=20)  # Early tier

            # Get base price in pence
            original_pence = calculate_price_in_pence("quick", drop_off_date=drop_off)
            assert original_pence == 10000  # £100

            # 10% discount = £10 off = £90 final
            discount_pence = int(original_pence * 10 / 100)
            final_pence = original_pence - discount_pence

            assert discount_pence == 1000
            assert final_pence == 9000

    def test_free_promo_zeroes_dynamic_price(self):
        """100% promo discount should result in £0."""
        custom_pricing = {
            "week1_base_price": 150.0,
            "week2_base_price": 200.0,
            "tier_increment": 25.0,
        }

        with patch("booking_service.get_pricing_from_db", return_value=custom_pricing):
            drop_off = date.today() + timedelta(days=5)  # Late tier

            # Late tier = 150 + 50 = 200
            original_pence = calculate_price_in_pence("quick", drop_off_date=drop_off)
            assert original_pence == 20000  # £200

            # 100% discount = £200 off = £0 final
            discount_pence = int(original_pence * 100 / 100)
            final_pence = original_pence - discount_pence

            assert discount_pence == 20000
            assert final_pence == 0
