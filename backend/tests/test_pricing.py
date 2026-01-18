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
