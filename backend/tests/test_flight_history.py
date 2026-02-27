"""
Tests for flight history audit functionality.

Covers:
- Recording history snapshots for departures and arrivals
- Retrieving history records
- History recorded when slots are booked/released
- History models and table structure

All tests use mocked data to avoid database state conflicts.
"""
import pytest
from datetime import date, time, datetime
from unittest.mock import MagicMock, patch, call

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db_models import (
    FlightDeparture, FlightArrival,
    FlightDepartureHistory, FlightArrivalHistory
)
from db_service import (
    record_departure_history, record_arrival_history,
    get_departure_history, get_arrival_history,
    book_departure_slot, release_departure_slot
)


# =============================================================================
# Unit Tests - Flight History Models
# =============================================================================

class TestFlightDepartureHistoryModel:
    """Unit tests for FlightDepartureHistory model."""

    def test_model_has_required_fields(self):
        """FlightDepartureHistory should have all required fields."""
        history = FlightDepartureHistory(
            flight_id=1,
            date=date(2026, 3, 15),
            flight_number="FR5523",
            airline_code="FR",
            airline_name="Ryanair",
            departure_time=time(10, 30),
            destination_code="AGP",
            destination_name="Malaga",
            capacity_tier=4,
            slots_booked_early=1,
            slots_booked_late=0,
            change_type="created",
            changed_by="admin@example.com"
        )

        assert history.flight_id == 1
        assert history.date == date(2026, 3, 15)
        assert history.flight_number == "FR5523"
        assert history.airline_code == "FR"
        assert history.airline_name == "Ryanair"
        assert history.departure_time == time(10, 30)
        assert history.destination_code == "AGP"
        assert history.destination_name == "Malaga"
        assert history.capacity_tier == 4
        assert history.slots_booked_early == 1
        assert history.slots_booked_late == 0
        assert history.change_type == "created"
        assert history.changed_by == "admin@example.com"

    def test_model_repr(self):
        """FlightDepartureHistory should have meaningful repr."""
        history = FlightDepartureHistory(
            id=1,
            flight_id=100,
            date=date(2026, 3, 15),
            flight_number="FR5523",
            airline_code="FR",
            airline_name="Ryanair",
            departure_time=time(10, 30),
            destination_code="AGP",
            destination_name="Malaga",
            capacity_tier=4,
            slots_booked_early=0,
            slots_booked_late=0,
            change_type="updated"
        )

        repr_str = repr(history)
        assert "100" in repr_str
        assert "updated" in repr_str


class TestFlightArrivalHistoryModel:
    """Unit tests for FlightArrivalHistory model."""

    def test_model_has_required_fields(self):
        """FlightArrivalHistory should have all required fields."""
        history = FlightArrivalHistory(
            flight_id=1,
            date=date(2026, 3, 22),
            flight_number="FR5524",
            airline_code="FR",
            airline_name="Ryanair",
            departure_time=time(8, 0),
            arrival_time=time(11, 30),
            origin_code="AGP",
            origin_name="Malaga",
            change_type="created",
            changed_by="system"
        )

        assert history.flight_id == 1
        assert history.date == date(2026, 3, 22)
        assert history.flight_number == "FR5524"
        assert history.airline_code == "FR"
        assert history.airline_name == "Ryanair"
        assert history.departure_time == time(8, 0)
        assert history.arrival_time == time(11, 30)
        assert history.origin_code == "AGP"
        assert history.origin_name == "Malaga"
        assert history.change_type == "created"
        assert history.changed_by == "system"

    def test_model_repr(self):
        """FlightArrivalHistory should have meaningful repr."""
        history = FlightArrivalHistory(
            id=1,
            flight_id=200,
            date=date(2026, 3, 22),
            flight_number="FR5524",
            airline_code="FR",
            airline_name="Ryanair",
            arrival_time=time(11, 30),
            origin_code="AGP",
            origin_name="Malaga",
            change_type="deleted"
        )

        repr_str = repr(history)
        assert "200" in repr_str
        assert "deleted" in repr_str


# =============================================================================
# Unit Tests - Record History Functions (Mocked)
# =============================================================================

class TestRecordDepartureHistory:
    """Unit tests for record_departure_history function."""

    def test_creates_history_record_with_all_fields(self):
        """Should create history record capturing all flight fields."""
        mock_db = MagicMock()
        mock_flight = MagicMock(spec=FlightDeparture)
        mock_flight.id = 100
        mock_flight.date = date(2026, 3, 15)
        mock_flight.flight_number = "FR5523"
        mock_flight.airline_code = "FR"
        mock_flight.airline_name = "Ryanair"
        mock_flight.departure_time = time(10, 30)
        mock_flight.destination_code = "AGP"
        mock_flight.destination_name = "Malaga"
        mock_flight.capacity_tier = 4
        mock_flight.slots_booked_early = 1
        mock_flight.slots_booked_late = 2

        record_departure_history(mock_db, mock_flight, "updated", "admin@test.com")

        # Verify db.add was called
        mock_db.add.assert_called_once()

        # Get the history object that was added
        history = mock_db.add.call_args[0][0]

        assert history.flight_id == 100
        assert history.date == date(2026, 3, 15)
        assert history.flight_number == "FR5523"
        assert history.airline_code == "FR"
        assert history.airline_name == "Ryanair"
        assert history.departure_time == time(10, 30)
        assert history.destination_code == "AGP"
        assert history.destination_name == "Malaga"
        assert history.capacity_tier == 4
        assert history.slots_booked_early == 1
        assert history.slots_booked_late == 2
        assert history.change_type == "updated"
        assert history.changed_by == "admin@test.com"

    def test_records_created_change_type(self):
        """Should record 'created' change type."""
        mock_db = MagicMock()
        mock_flight = MagicMock(spec=FlightDeparture)
        mock_flight.id = 1
        mock_flight.date = date(2026, 3, 15)
        mock_flight.flight_number = "U21234"
        mock_flight.airline_code = "U2"
        mock_flight.airline_name = "easyJet"
        mock_flight.departure_time = time(14, 0)
        mock_flight.destination_code = "PMI"
        mock_flight.destination_name = "Palma"
        mock_flight.capacity_tier = 6
        mock_flight.slots_booked_early = 0
        mock_flight.slots_booked_late = 0

        record_departure_history(mock_db, mock_flight, "created", "import_script")

        history = mock_db.add.call_args[0][0]
        assert history.change_type == "created"
        assert history.changed_by == "import_script"

    def test_records_deleted_change_type(self):
        """Should record 'deleted' change type."""
        mock_db = MagicMock()
        mock_flight = MagicMock(spec=FlightDeparture)
        mock_flight.id = 50
        mock_flight.date = date(2026, 3, 15)
        mock_flight.flight_number = "LS123"
        mock_flight.airline_code = "LS"
        mock_flight.airline_name = "Jet2"
        mock_flight.departure_time = time(7, 0)
        mock_flight.destination_code = "TFS"
        mock_flight.destination_name = "Tenerife"
        mock_flight.capacity_tier = 2
        mock_flight.slots_booked_early = 0
        mock_flight.slots_booked_late = 1

        record_departure_history(mock_db, mock_flight, "deleted", "admin@test.com")

        history = mock_db.add.call_args[0][0]
        assert history.change_type == "deleted"

    def test_calls_flush_after_add(self):
        """Should call db.flush() after adding record."""
        mock_db = MagicMock()
        mock_flight = MagicMock(spec=FlightDeparture)
        mock_flight.id = 1
        mock_flight.date = date(2026, 3, 15)
        mock_flight.flight_number = "FR1234"
        mock_flight.airline_code = "FR"
        mock_flight.airline_name = "Ryanair"
        mock_flight.departure_time = time(10, 0)
        mock_flight.destination_code = "AGP"
        mock_flight.destination_name = "Malaga"
        mock_flight.capacity_tier = 4
        mock_flight.slots_booked_early = 0
        mock_flight.slots_booked_late = 0

        record_departure_history(mock_db, mock_flight, "updated")

        mock_db.flush.assert_called_once()


class TestRecordArrivalHistory:
    """Unit tests for record_arrival_history function."""

    def test_creates_history_record_with_all_fields(self):
        """Should create history record capturing all arrival fields."""
        mock_db = MagicMock()
        mock_flight = MagicMock(spec=FlightArrival)
        mock_flight.id = 200
        mock_flight.date = date(2026, 3, 22)
        mock_flight.flight_number = "FR5524"
        mock_flight.airline_code = "FR"
        mock_flight.airline_name = "Ryanair"
        mock_flight.departure_time = time(8, 0)
        mock_flight.arrival_time = time(11, 30)
        mock_flight.origin_code = "AGP"
        mock_flight.origin_name = "Malaga"

        record_arrival_history(mock_db, mock_flight, "updated", "admin@test.com")

        mock_db.add.assert_called_once()
        history = mock_db.add.call_args[0][0]

        assert history.flight_id == 200
        assert history.date == date(2026, 3, 22)
        assert history.flight_number == "FR5524"
        assert history.airline_code == "FR"
        assert history.airline_name == "Ryanair"
        assert history.departure_time == time(8, 0)
        assert history.arrival_time == time(11, 30)
        assert history.origin_code == "AGP"
        assert history.origin_name == "Malaga"
        assert history.change_type == "updated"
        assert history.changed_by == "admin@test.com"

    def test_handles_null_departure_time(self):
        """Should handle arrival with no departure_time."""
        mock_db = MagicMock()
        mock_flight = MagicMock(spec=FlightArrival)
        mock_flight.id = 201
        mock_flight.date = date(2026, 3, 22)
        mock_flight.flight_number = "U21234"
        mock_flight.airline_code = "U2"
        mock_flight.airline_name = "easyJet"
        mock_flight.departure_time = None  # No departure time
        mock_flight.arrival_time = time(14, 0)
        mock_flight.origin_code = "PMI"
        mock_flight.origin_name = "Palma"

        record_arrival_history(mock_db, mock_flight, "created", "system")

        history = mock_db.add.call_args[0][0]
        assert history.departure_time is None
        assert history.arrival_time == time(14, 0)


# =============================================================================
# Unit Tests - Get History Functions (Mocked)
# =============================================================================

class TestGetDepartureHistory:
    """Unit tests for get_departure_history function."""

    def test_queries_by_flight_id(self):
        """Should query history by flight_id."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        get_departure_history(mock_db, 100)

        mock_db.query.assert_called_once_with(FlightDepartureHistory)

    def test_returns_history_records(self):
        """Should return list of history records."""
        mock_db = MagicMock()
        mock_history_1 = MagicMock(spec=FlightDepartureHistory)
        mock_history_2 = MagicMock(spec=FlightDepartureHistory)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_history_1, mock_history_2]

        result = get_departure_history(mock_db, 100)

        assert len(result) == 2
        assert result[0] == mock_history_1
        assert result[1] == mock_history_2


class TestGetArrivalHistory:
    """Unit tests for get_arrival_history function."""

    def test_queries_by_flight_id(self):
        """Should query history by flight_id."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        get_arrival_history(mock_db, 200)

        mock_db.query.assert_called_once_with(FlightArrivalHistory)


# =============================================================================
# Unit Tests - History Recording on Slot Operations (Mocked)
# =============================================================================

class TestBookDepartureSlotHistory:
    """Tests that booking a slot records history."""

    @patch('db_service.record_departure_history')
    def test_records_history_on_early_slot_booking(self, mock_record_history):
        """Should record history when early slot is booked."""
        mock_db = MagicMock()
        mock_flight = MagicMock(spec=FlightDeparture)
        mock_flight.id = 100
        mock_flight.capacity_tier = 4  # max 2 per slot
        mock_flight.slots_booked_early = 0
        mock_flight.slots_booked_late = 0
        mock_flight.max_slots_per_time = 2

        mock_db.query.return_value.filter.return_value.first.return_value = mock_flight

        result = book_departure_slot(mock_db, 100, "early")

        assert result["success"] is True
        mock_record_history.assert_called_once_with(mock_db, mock_flight, 'updated', 'system')

    @patch('db_service.record_departure_history')
    def test_records_history_on_late_slot_booking(self, mock_record_history):
        """Should record history when late slot is booked."""
        mock_db = MagicMock()
        mock_flight = MagicMock(spec=FlightDeparture)
        mock_flight.id = 100
        mock_flight.capacity_tier = 4
        mock_flight.slots_booked_early = 0
        mock_flight.slots_booked_late = 0
        mock_flight.max_slots_per_time = 2

        mock_db.query.return_value.filter.return_value.first.return_value = mock_flight

        result = book_departure_slot(mock_db, 100, "late")

        assert result["success"] is True
        mock_record_history.assert_called_once_with(mock_db, mock_flight, 'updated', 'system')

    @patch('db_service.record_departure_history')
    def test_no_history_on_failed_booking(self, mock_record_history):
        """Should NOT record history when booking fails (no slots)."""
        mock_db = MagicMock()
        mock_flight = MagicMock(spec=FlightDeparture)
        mock_flight.id = 100
        mock_flight.capacity_tier = 4
        mock_flight.slots_booked_early = 2  # Already full
        mock_flight.slots_booked_late = 0
        mock_flight.max_slots_per_time = 2

        mock_db.query.return_value.filter.return_value.first.return_value = mock_flight

        result = book_departure_slot(mock_db, 100, "early")

        assert result["success"] is False
        mock_record_history.assert_not_called()

    @patch('db_service.record_departure_history')
    def test_no_history_on_call_us_flight(self, mock_record_history):
        """Should NOT record history for Call Us only flights."""
        mock_db = MagicMock()
        mock_flight = MagicMock(spec=FlightDeparture)
        mock_flight.id = 100
        mock_flight.capacity_tier = 0  # Call Us only

        mock_db.query.return_value.filter.return_value.first.return_value = mock_flight

        result = book_departure_slot(mock_db, 100, "early")

        assert result["success"] is False
        assert result.get("call_us") is True
        mock_record_history.assert_not_called()


class TestReleaseDepartureSlotHistory:
    """Tests that releasing a slot records history."""

    @patch('db_service.record_departure_history')
    def test_records_history_on_slot_release(self, mock_record_history):
        """Should record history when slot is released."""
        mock_db = MagicMock()
        mock_flight = MagicMock(spec=FlightDeparture)
        mock_flight.id = 100
        mock_flight.slots_booked_early = 1
        mock_flight.slots_booked_late = 0

        mock_db.query.return_value.filter.return_value.first.return_value = mock_flight

        result = release_departure_slot(mock_db, 100, "early")

        assert result["success"] is True
        mock_record_history.assert_called_once_with(mock_db, mock_flight, 'updated', 'system')

    @patch('db_service.record_departure_history')
    def test_no_history_on_failed_release(self, mock_record_history):
        """Should NOT record history when release fails (no slots to release)."""
        mock_db = MagicMock()
        mock_flight = MagicMock(spec=FlightDeparture)
        mock_flight.id = 100
        mock_flight.slots_booked_early = 0  # No slots to release
        mock_flight.slots_booked_late = 0

        mock_db.query.return_value.filter.return_value.first.return_value = mock_flight

        result = release_departure_slot(mock_db, 100, "early")

        assert result["success"] is False
        mock_record_history.assert_not_called()


# =============================================================================
# Integration Tests - With Database (Marked for conditional execution)
# =============================================================================

@pytest.mark.integration
class TestFlightHistoryIntegration:
    """Integration tests with actual database."""

    def test_record_and_retrieve_departure_history(self, db_session):
        """Should record and retrieve departure history from database."""
        # This test uses the real database - requires flight_departure_history table
        # Skip if table doesn't exist
        from sqlalchemy import inspect
        inspector = inspect(db_session.bind)
        if 'flight_departure_history' not in inspector.get_table_names():
            pytest.skip("flight_departure_history table not created yet")

        # Create a test flight first (or use existing)
        flight = db_session.query(FlightDeparture).first()
        if not flight:
            pytest.skip("No departure flights in database")

        # Record history
        history = record_departure_history(db_session, flight, "updated", "test@example.com")
        db_session.commit()

        # Retrieve and verify
        records = get_departure_history(db_session, flight.id)
        assert len(records) > 0
        latest = records[0]
        assert latest.flight_id == flight.id
        assert latest.change_type == "updated"

    def test_record_and_retrieve_arrival_history(self, db_session):
        """Should record and retrieve arrival history from database."""
        from sqlalchemy import inspect
        inspector = inspect(db_session.bind)
        if 'flight_arrival_history' not in inspector.get_table_names():
            pytest.skip("flight_arrival_history table not created yet")

        flight = db_session.query(FlightArrival).first()
        if not flight:
            pytest.skip("No arrival flights in database")

        history = record_arrival_history(db_session, flight, "updated", "test@example.com")
        db_session.commit()

        records = get_arrival_history(db_session, flight.id)
        assert len(records) > 0
        latest = records[0]
        assert latest.flight_id == flight.id
        assert latest.change_type == "updated"
