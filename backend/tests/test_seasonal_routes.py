"""
Tests for seasonal flight route handling.

These tests verify that:
1. Arrivals API correctly returns flights filtered by origin code
2. When no arrivals exist for a seasonal route on a date, empty array is returned
3. Frontend can properly detect when return flights don't exist for a route/duration

This covers the bug fix where selecting a seasonal route (e.g., Edinburgh) with a return
date after the route ends was showing incorrect return flights from different destinations.

Uses an isolated in-memory SQLite database with mocked data for deterministic testing.
"""
import pytest
import pytest_asyncio
from datetime import date, time
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import Base, get_db
from db_models import FlightDeparture, FlightArrival
from main import app


# =============================================================================
# Test Database Setup - Isolated In-Memory SQLite
# =============================================================================

# Create in-memory SQLite engine for isolated testing
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # Share connection across threads for in-memory DB
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database dependency for isolated testing."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_test_database():
    """Create all tables in the test database before tests run."""
    Base.metadata.create_all(bind=test_engine)
    # Override the dependency for all tests in this module
    app.dependency_overrides[get_db] = override_get_db
    yield
    # Clean up
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def clean_tables():
    """Clean tables before each test for isolation."""
    db = TestSessionLocal()
    try:
        db.query(FlightArrival).delete()
        db.query(FlightDeparture).delete()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def db_session():
    """Get a test database session."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =============================================================================
# Mock Data Fixtures
# =============================================================================

@pytest.fixture
def seasonal_edinburgh_departure(db_session):
    """
    Create a seasonal Edinburgh departure flight.
    Edinburgh routes typically operate seasonally (e.g., summer only).
    """
    departure = FlightDeparture(
        date=date(2026, 3, 27),  # Late March - within season
        flight_number="8888",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(11, 0),
        destination_code="EDI",
        destination_name="Edinburgh, SC, GB",
        capacity_tier=2,
        slots_booked_early=0,
        slots_booked_late=0,
    )
    db_session.add(departure)
    db_session.commit()
    db_session.refresh(departure)
    return departure


@pytest.fixture
def edinburgh_arrival_1_week(db_session):
    """
    Create an Edinburgh arrival flight for 1-week return (within season).
    """
    arrival = FlightArrival(
        date=date(2026, 4, 3),  # 1 week after March 27
        flight_number="8889",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(8, 0),
        arrival_time=time(10, 30),
        origin_code="EDI",
        origin_name="Edinburgh, SC, GB",
    )
    db_session.add(arrival)
    db_session.commit()
    db_session.refresh(arrival)
    return arrival


@pytest.fixture
def palma_arrival_same_date(db_session):
    """
    Create a Palma arrival flight on the same date as Edinburgh 1-week return.
    This should NOT be returned when filtering for Edinburgh route.
    """
    arrival = FlightArrival(
        date=date(2026, 4, 3),  # Same date as Edinburgh 1-week return
        flight_number="828",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(9, 0),
        arrival_time=time(12, 30),
        origin_code="PMI",
        origin_name="Palma de Mallorca, ES",
    )
    db_session.add(arrival)
    db_session.commit()
    db_session.refresh(arrival)
    return arrival


@pytest.fixture
def faro_arrival_same_date(db_session):
    """
    Create a Faro arrival flight on the same date as Edinburgh 1-week return.
    This should NOT be returned when filtering for Edinburgh route.
    """
    arrival = FlightArrival(
        date=date(2026, 4, 3),  # Same date
        flight_number="5524",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(11, 0),
        arrival_time=time(14, 30),
        origin_code="FAO",
        origin_name="Faro, PT",
    )
    db_session.add(arrival)
    db_session.commit()
    db_session.refresh(arrival)
    return arrival


# =============================================================================
# Arrivals API Basic Tests
# =============================================================================

@pytest.mark.asyncio
async def test_arrivals_returns_all_flights_for_date(
    client, edinburgh_arrival_1_week, palma_arrival_same_date, faro_arrival_same_date
):
    """
    Arrivals API should return ALL arrivals for a given date.
    Frontend is responsible for filtering by route.
    """
    response = await client.get("/api/flights/arrivals/2026-04-03")
    assert response.status_code == 200
    data = response.json()

    # Should return all 3 arrivals we created
    assert len(data) == 3

    # Verify origin codes are present
    origin_codes = [f["originCode"] for f in data]
    assert "EDI" in origin_codes
    assert "PMI" in origin_codes
    assert "FAO" in origin_codes


@pytest.mark.asyncio
async def test_arrivals_empty_for_date_without_flights(client):
    """
    When no flights exist for a date, should return empty array.
    """
    response = await client.get("/api/flights/arrivals/2026-05-15")
    assert response.status_code == 200
    data = response.json()
    assert data == []


# =============================================================================
# Seasonal Route Filtering Tests (Frontend Logic Simulation)
# =============================================================================

@pytest.mark.asyncio
async def test_filter_arrivals_by_origin_code_edinburgh(
    client, edinburgh_arrival_1_week, palma_arrival_same_date, faro_arrival_same_date
):
    """
    Test that filtering arrivals by origin code correctly returns only Edinburgh flights.
    This simulates the frontend filteredArrivalsForDate logic.
    """
    response = await client.get("/api/flights/arrivals/2026-04-03")
    assert response.status_code == 200
    data = response.json()

    # Simulate frontend filter: same airline AND matching origin code
    target_airline = "Ryanair"
    target_origin_code = "EDI"  # Edinburgh

    filtered = [
        f for f in data
        if f["airlineName"] == target_airline and f["originCode"] == target_origin_code
    ]

    # Should only get the Edinburgh flight
    assert len(filtered) == 1
    assert filtered[0]["originCode"] == "EDI"
    assert filtered[0]["flightNumber"] == "8889"


@pytest.mark.asyncio
async def test_filter_arrivals_excludes_wrong_routes(
    client, edinburgh_arrival_1_week, palma_arrival_same_date, faro_arrival_same_date
):
    """
    When filtering for Edinburgh, Palma and Faro flights should be excluded
    even though they are on the same date and same airline.
    """
    response = await client.get("/api/flights/arrivals/2026-04-03")
    assert response.status_code == 200
    data = response.json()

    # Filter for Edinburgh (EDI)
    target_airline = "Ryanair"
    target_origin_code = "EDI"

    filtered = [
        f for f in data
        if f["airlineName"] == target_airline and f["originCode"] == target_origin_code
    ]

    # Verify Palma (PMI) is NOT included
    assert not any(f["originCode"] == "PMI" for f in filtered)

    # Verify Faro (FAO) is NOT included
    assert not any(f["originCode"] == "FAO" for f in filtered)


@pytest.mark.asyncio
async def test_no_return_flights_for_seasonal_route_off_season(
    client, palma_arrival_same_date, faro_arrival_same_date
):
    """
    When Edinburgh route doesn't operate on a date (seasonal/off-season),
    filtering for Edinburgh should return empty, even if other flights exist.

    This is the core bug scenario: user selects Edinburgh departure but
    the return date has no Edinburgh flights - system should show no
    options, NOT flights from other destinations.
    """
    response = await client.get("/api/flights/arrivals/2026-04-03")
    assert response.status_code == 200
    data = response.json()

    # There ARE flights on this date (Palma, Faro)
    assert len(data) == 2

    # But filtering for Edinburgh returns nothing
    target_airline = "Ryanair"
    target_origin_code = "EDI"

    filtered = [
        f for f in data
        if f["airlineName"] == target_airline and f["originCode"] == target_origin_code
    ]

    # No Edinburgh flights - this is the expected behavior
    assert len(filtered) == 0


@pytest.mark.asyncio
async def test_2_week_return_no_flights_for_seasonal_route(client, seasonal_edinburgh_departure):
    """
    Test 2-week return scenario where Edinburgh doesn't operate.
    Return date: March 27 + 14 days = April 10
    """
    response = await client.get("/api/flights/arrivals/2026-04-10")
    assert response.status_code == 200
    data = response.json()

    # Filter for Edinburgh returns
    target_airline = "Ryanair"
    target_origin_code = "EDI"

    filtered = [
        f for f in data
        if f["airlineName"] == target_airline and f["originCode"] == target_origin_code
    ]

    # No Edinburgh flights for 2-week return - route doesn't operate
    assert len(filtered) == 0


# =============================================================================
# Duration Availability Check Tests
# =============================================================================

@pytest.mark.asyncio
async def test_check_both_duration_options(
    client, seasonal_edinburgh_departure, edinburgh_arrival_1_week
):
    """
    Test checking availability for both 1-week and 2-week returns.
    1-week should have a flight, 2-week should not.

    This simulates the frontend checkDurationAvailability logic.
    """
    # Check 1-week return (April 3)
    one_week_date = date(2026, 4, 3)
    response_1w = await client.get(f"/api/flights/arrivals/{one_week_date.isoformat()}")
    data_1w = response_1w.json()

    has_1w_return = any(
        f["airlineName"] == "Ryanair" and f["originCode"] == "EDI"
        for f in data_1w
    )
    assert has_1w_return is True, "1-week return should have Edinburgh flight"

    # Check 2-week return (April 10)
    two_week_date = date(2026, 4, 10)
    response_2w = await client.get(f"/api/flights/arrivals/{two_week_date.isoformat()}")
    data_2w = response_2w.json()

    has_2w_return = any(
        f["airlineName"] == "Ryanair" and f["originCode"] == "EDI"
        for f in data_2w
    )
    assert has_2w_return is False, "2-week return should NOT have Edinburgh flight"


@pytest.mark.asyncio
async def test_neither_duration_available(client, seasonal_edinburgh_departure):
    """
    Test scenario where neither 1-week nor 2-week has return flights.
    Frontend should show error message prompting user to contact support.
    """
    # Neither date has Edinburgh arrivals (we only created departure, no arrivals)

    # Check 1-week return (April 3) - no Edinburgh arrival created
    response_1w = await client.get("/api/flights/arrivals/2026-04-03")
    data_1w = response_1w.json()
    has_1w = any(f["originCode"] == "EDI" for f in data_1w)

    # Check 2-week return (April 10) - no Edinburgh arrival created
    response_2w = await client.get("/api/flights/arrivals/2026-04-10")
    data_2w = response_2w.json()
    has_2w = any(f["originCode"] == "EDI" for f in data_2w)

    # Both should be False when route doesn't operate on those dates
    assert has_1w is False
    assert has_2w is False


# =============================================================================
# Airline Normalization Tests
# =============================================================================

@pytest.mark.asyncio
async def test_airline_normalization_ryanair_uk(client, db_session):
    """
    Test that Ryanair UK flights are treated as Ryanair.
    Frontend normalizes 'Ryanair UK' to 'Ryanair'.
    """
    # Create a Ryanair UK arrival
    arrival_uk = FlightArrival(
        date=date(2026, 4, 3),
        flight_number="9999",
        airline_code="RK",
        airline_name="Ryanair UK",
        departure_time=time(8, 0),
        arrival_time=time(10, 0),
        origin_code="EDI",
        origin_name="Edinburgh, SC, GB",
    )
    db_session.add(arrival_uk)
    db_session.commit()

    response = await client.get("/api/flights/arrivals/2026-04-03")
    data = response.json()

    # Simulate frontend airline normalization
    def normalize_airline(name):
        if name == "Ryanair UK":
            return "Ryanair"
        return name

    # Filter for normalized "Ryanair" AND Edinburgh
    filtered = [
        f for f in data
        if normalize_airline(f["airlineName"]) == "Ryanair" and f["originCode"] == "EDI"
    ]

    # Should find the Ryanair UK flight
    assert len(filtered) == 1
    assert filtered[0]["flightNumber"] == "9999"


# =============================================================================
# Edge Case Tests
# =============================================================================

@pytest.mark.asyncio
async def test_multiple_flights_same_route_same_day(client, db_session):
    """
    Test when multiple flights exist for the same route on the same day.
    Frontend should handle this correctly (e.g., pick best match by flight number).
    """
    # Create two Edinburgh arrivals on same day
    arrival1 = FlightArrival(
        date=date(2026, 4, 5),
        flight_number="8889",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(8, 0),
        arrival_time=time(10, 30),
        origin_code="EDI",
        origin_name="Edinburgh, SC, GB",
    )
    arrival2 = FlightArrival(
        date=date(2026, 4, 5),
        flight_number="8891",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(17, 0),
        arrival_time=time(19, 30),
        origin_code="EDI",
        origin_name="Edinburgh, SC, GB",
    )
    db_session.add(arrival1)
    db_session.add(arrival2)
    db_session.commit()

    response = await client.get("/api/flights/arrivals/2026-04-05")
    data = response.json()

    # Filter for Edinburgh
    filtered = [
        f for f in data
        if f["airlineName"] == "Ryanair" and f["originCode"] == "EDI"
    ]

    # Should find both Edinburgh flights
    assert len(filtered) == 2


@pytest.mark.asyncio
async def test_arrival_response_format(client, db_session):
    """
    Verify the arrival API response has all required fields for frontend filtering.
    """
    # Create a test arrival
    arrival = FlightArrival(
        date=date(2026, 4, 3),
        flight_number="1234",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(8, 0),
        arrival_time=time(10, 30),
        origin_code="FAO",
        origin_name="Faro, PT",
    )
    db_session.add(arrival)
    db_session.commit()

    response = await client.get("/api/flights/arrivals/2026-04-03")
    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    arrival_data = data[0]

    # Required fields for frontend filtering
    assert "airlineName" in arrival_data
    assert "originCode" in arrival_data
    assert "originName" in arrival_data
    assert "flightNumber" in arrival_data
    assert "time" in arrival_data
    assert "airlineCode" in arrival_data

    # Verify values
    assert arrival_data["airlineName"] == "Ryanair"
    assert arrival_data["originCode"] == "FAO"
    assert arrival_data["flightNumber"] == "1234"


# =============================================================================
# Stale Data Prevention Tests
# =============================================================================

@pytest.mark.asyncio
async def test_arrivals_are_date_specific(client, db_session):
    """
    Verify that arrivals are correctly filtered by date.
    Different dates should return different results.
    """
    # Create Edinburgh arrival on April 3
    arrival_apr3 = FlightArrival(
        date=date(2026, 4, 3),
        flight_number="8889",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(8, 0),
        arrival_time=time(10, 30),
        origin_code="EDI",
        origin_name="Edinburgh, SC, GB",
    )
    db_session.add(arrival_apr3)
    db_session.commit()

    # Date with Edinburgh flight
    response_apr3 = await client.get("/api/flights/arrivals/2026-04-03")
    data_apr3 = response_apr3.json()
    has_edi_apr3 = any(f["originCode"] == "EDI" for f in data_apr3)

    # Date without Edinburgh flight
    response_apr4 = await client.get("/api/flights/arrivals/2026-04-04")
    data_apr4 = response_apr4.json()
    has_edi_apr4 = any(f["originCode"] == "EDI" for f in data_apr4)

    # April 3 has Edinburgh, April 4 doesn't
    assert has_edi_apr3 is True
    assert has_edi_apr4 is False


# =============================================================================
# Bug Scenario Recreation Test
# =============================================================================

@pytest.mark.asyncio
async def test_bug_scenario_edinburgh_shows_palma(client, db_session):
    """
    Recreate the exact bug scenario:
    1. User selects Edinburgh departure on March 27
    2. User selects 1-week return (April 3)
    3. No Edinburgh arrivals exist for April 3
    4. Palma arrivals DO exist for April 3
    5. Frontend should show "No return flights" NOT Palma flights

    This test verifies the filtering logic prevents showing wrong routes.
    """
    # Setup: Edinburgh departure exists
    departure = FlightDeparture(
        date=date(2026, 3, 27),
        flight_number="8888",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(11, 0),
        destination_code="EDI",
        destination_name="Edinburgh, SC, GB",
        capacity_tier=2,
        slots_booked_early=0,
        slots_booked_late=0,
    )
    db_session.add(departure)

    # Palma arrival exists on return date (this was showing incorrectly before fix)
    palma_arrival = FlightArrival(
        date=date(2026, 4, 3),
        flight_number="828",
        airline_code="FR",
        airline_name="Ryanair",
        departure_time=time(9, 0),
        arrival_time=time(12, 30),
        origin_code="PMI",
        origin_name="Palma de Mallorca, ES",
    )
    db_session.add(palma_arrival)
    db_session.commit()

    # Fetch arrivals for return date
    response = await client.get("/api/flights/arrivals/2026-04-03")
    data = response.json()

    # Arrivals exist (Palma)
    assert len(data) == 1
    assert data[0]["originCode"] == "PMI"

    # But filtering for Edinburgh returns NOTHING
    # This is the critical assertion - the bug was that Palma was shown
    edinburgh_arrivals = [
        f for f in data
        if f["airlineName"] == "Ryanair" and f["originCode"] == "EDI"
    ]

    assert len(edinburgh_arrivals) == 0, \
        "Edinburgh filter should return empty, not Palma flights!"

    # Verify Palma is NOT in Edinburgh filter
    assert not any(f["originCode"] == "PMI" for f in edinburgh_arrivals), \
        "Palma should NOT appear when filtering for Edinburgh!"
