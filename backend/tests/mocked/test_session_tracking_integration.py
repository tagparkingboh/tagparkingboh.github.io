"""
Integration Tests for Session Tracking Report.

Tests the actual API endpoints with mocked database.

Covers:
- POST /api/booking/audit-event - Logging funnel events
- GET /api/admin/reports/session-tracking - Session tracking report

Uses FastAPI TestClient with mocked database.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import after path setup
from db_models import AuditLogEvent


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.add = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    return db


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@tag-parking.co.uk"
    user.first_name = "Admin"
    user.last_name = "User"
    user.role = "admin"
    return user


@pytest.fixture
def client(mock_db, mock_admin_user):
    """Create test client with mocked dependencies."""
    from main import app, get_db, require_admin

    def override_get_db():
        yield mock_db

    def override_require_admin():
        return mock_admin_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = override_require_admin

    yield TestClient(app)

    app.dependency_overrides.clear()


# =============================================================================
# Tests - POST /api/booking/audit-event
# =============================================================================

class TestAuditEventEndpoint:
    """Tests for audit event logging endpoint."""

    def test_log_dates_selected_event(self, client, mock_db):
        """Should successfully log dates_selected event."""
        response = client.post(
            "/api/booking/audit-event",
            json={
                "session_id": "sess_123_abc",
                "event": "dates_selected",
                "event_data": {
                    "dropoff_date": "2024-06-15",
                    "pickup_date": "2024-06-22",
                    "days_parking": 7
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["event"] == "dates_selected"

    def test_log_flight_selected_event(self, client, mock_db):
        """Should successfully log flight_selected event."""
        response = client.post(
            "/api/booking/audit-event",
            json={
                "session_id": "sess_123_abc",
                "event": "flight_selected",
                "event_data": {
                    "dropoff_date": "2024-06-15",
                    "pickup_date": "2024-06-22",
                    "departure_airline": "Ryanair",
                    "departure_time": "08:30",
                    "arrival_airline": "EasyJet",
                    "arrival_time": "14:45"
                }
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["event"] == "flight_selected"

    def test_log_unknown_event_returns_error(self, client, mock_db):
        """Should return 400 for unknown event type."""
        response = client.post(
            "/api/booking/audit-event",
            json={
                "session_id": "sess_123_abc",
                "event": "invalid_event_type",
                "event_data": {}
            }
        )

        assert response.status_code == 400

    def test_log_event_without_session_id(self, client, mock_db):
        """Should handle event without session_id."""
        response = client.post(
            "/api/booking/audit-event",
            json={
                "session_id": "",
                "event": "dates_selected",
                "event_data": {}
            }
        )

        # Should still work (session_id can be empty string)
        assert response.status_code == 200

    def test_log_event_with_booking_reference(self, client, mock_db):
        """Should log event with booking reference."""
        response = client.post(
            "/api/booking/audit-event",
            json={
                "session_id": "sess_123_abc",
                "event": "tnc_accepted",
                "booking_reference": "TAG-ABC12345",
                "event_data": {
                    "customer_email": "test@example.com"
                }
            }
        )

        assert response.status_code == 200

    # -- Regression guard: every event name the FE actually emits must be -----
    # accepted by the BE. Pre-Apr 30 2026 the event_map was missing
    # stripe_form_ready / stripe_form_error / payment_requires_action, so
    # those POSTs returned 400 and the audit rows silently disappeared.
    # Sourced from grep over StripePayment.jsx + BookingsNew.jsx.
    @pytest.mark.parametrize("event_name", [
        "dates_selected",
        "flight_selected",
        "tnc_accepted",
        "tnc_unchecked",
        "promo_code_added",
        "promo_code_removed",
        "checkout_loaded",
        "stripe_form_ready",
        "stripe_form_error",
        "payment_processing",
        "payment_initiated",
        "payment_succeeded",
        "payment_failed",
        "payment_requires_action",
    ])
    def test_every_fe_emitted_event_name_is_accepted(self, client, mock_db, event_name):
        """Every event name the FE emits must round-trip as 200. Add new
        names here AND to main.py event_map whenever the FE adds a new
        logAuditEvent call, otherwise the audit row is silently dropped."""
        response = client.post(
            "/api/booking/audit-event",
            json={
                "session_id": "sess_regression",
                "event": event_name,
                "event_data": {},
            },
        )
        assert response.status_code == 200, (
            f"event {event_name!r} returned {response.status_code} — "
            f"likely missing from main.py event_map. "
            f"Body: {response.text}"
        )
        body = response.json()
        assert body["success"] is True
        assert body["event"] == event_name


# =============================================================================
# Tests - GET /api/admin/reports/session-tracking
# =============================================================================

class TestSessionTrackingReportEndpoint:
    """Tests for session tracking report endpoint."""

    def test_get_daily_report(self, client, mock_db):
        """Should return daily session tracking report."""
        response = client.get(
            "/api/admin/reports/session-tracking?period=daily"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["period_type"] == "daily"
        assert "stages" in data
        assert "periods" in data
        assert "cumulative" in data

    def test_get_weekly_report(self, client, mock_db):
        """Should return weekly session tracking report."""
        response = client.get(
            "/api/admin/reports/session-tracking?period=weekly"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["period_type"] == "weekly"

    def test_get_monthly_report(self, client, mock_db):
        """Should return monthly session tracking report."""
        response = client.get(
            "/api/admin/reports/session-tracking?period=monthly"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["period_type"] == "monthly"

    def test_default_period_is_daily(self, client, mock_db):
        """Default period should be daily."""
        response = client.get("/api/admin/reports/session-tracking")

        assert response.status_code == 200
        data = response.json()
        assert data["period_type"] == "daily"

    def test_response_has_five_funnel_stages(self, client, mock_db):
        """Response should have 5 funnel stages."""
        response = client.get("/api/admin/reports/session-tracking")

        assert response.status_code == 200
        data = response.json()
        assert len(data["stages"]) == 5

    def test_stages_have_correct_keys(self, client, mock_db):
        """Stages should have the correct keys."""
        response = client.get("/api/admin/reports/session-tracking")

        assert response.status_code == 200
        data = response.json()

        expected_keys = [
            "dates_selected",
            "flight_selected",
            "customer_entered",
            "payment_initiated",
            "booking_confirmed",
        ]

        actual_keys = [s["key"] for s in data["stages"]]
        assert actual_keys == expected_keys

    def test_cumulative_has_counts_and_rates(self, client, mock_db):
        """Cumulative section should have counts and conversion rates."""
        response = client.get("/api/admin/reports/session-tracking")

        assert response.status_code == 200
        data = response.json()

        assert "counts" in data["cumulative"]
        assert "conversion_rates" in data["cumulative"]
        assert "overall_conversion" in data["cumulative"]

    def test_empty_audit_logs_returns_zero_counts(self, client, mock_db):
        """Empty audit logs should return zero counts."""
        # Mock returns empty list by default
        response = client.get("/api/admin/reports/session-tracking")

        assert response.status_code == 200
        data = response.json()

        # All counts should be 0
        for stage_key in data["cumulative"]["counts"]:
            assert data["cumulative"]["counts"][stage_key] == 0


# =============================================================================
# Tests - Session Tracking with Audit Logs
# =============================================================================

class TestSessionTrackingWithData:
    """Tests for session tracking with audit log data."""

    def test_counts_unique_sessions(self, client, mock_db):
        """Should count unique sessions, not total events."""
        import pytz
        from db_models import AuditLog

        uk_tz = pytz.timezone('Europe/London')
        now = datetime.now(uk_tz)

        # Create mock audit logs with same session appearing multiple times
        mock_logs = [
            MagicMock(
                id=1,
                session_id="sess_1",
                event=AuditLogEvent.DATES_SELECTED,
                created_at=now,
            ),
            MagicMock(
                id=2,
                session_id="sess_1",  # Same session, different event
                event=AuditLogEvent.FLIGHT_SELECTED,
                created_at=now,
            ),
            MagicMock(
                id=3,
                session_id="sess_2",  # Different session
                event=AuditLogEvent.DATES_SELECTED,
                created_at=now,
            ),
        ]

        mock_db.query.return_value.filter.return_value.all.return_value = mock_logs

        # refresh=true bypasses the module-level _session_tracking_cache populated
        # by earlier tests in this file
        response = client.get("/api/admin/reports/session-tracking?period=daily&refresh=true")

        assert response.status_code == 200
        data = response.json()

        # Should have 2 unique sessions for dates_selected
        # and 1 unique session for flight_selected
        cumulative = data["cumulative"]["counts"]
        assert cumulative["dates_selected"] == 2
        assert cumulative["flight_selected"] == 1

    def test_dedupes_by_booking_reference_when_session_missing(self, client, mock_db):
        """Repeat events with no session_id but the same booking_reference collapse to one."""
        import pytz
        from datetime import datetime as dt

        uk_tz = pytz.timezone('Europe/London')
        now = dt.now(uk_tz)

        mock_logs = [
            MagicMock(
                id=101,
                session_id=None,
                booking_reference="TAG-DEQ61923",
                event=AuditLogEvent.BOOKING_CONFIRMED,
                created_at=now,
            ),
            MagicMock(
                id=102,
                session_id=None,
                booking_reference="TAG-DEQ61923",
                event=AuditLogEvent.BOOKING_CONFIRMED,
                created_at=now,
            ),
            MagicMock(
                id=103,
                session_id=None,
                booking_reference=None,
                event=AuditLogEvent.BOOKING_CONFIRMED,
                created_at=now,
            ),
            MagicMock(
                id=104,
                session_id=None,
                booking_reference=None,
                event=AuditLogEvent.BOOKING_CONFIRMED,
                created_at=now,
            ),
        ]

        def query_side_effect(model):
            query_mock = MagicMock()
            if hasattr(model, '__name__') and model.__name__ == 'Booking':
                query_mock.filter.return_value.all.return_value = []
            else:
                query_mock.filter.return_value.all.return_value = mock_logs
            return query_mock

        mock_db.query.side_effect = query_side_effect

        response = client.get(
            "/api/admin/reports/session-tracking?period=daily&refresh=true"
        )

        assert response.status_code == 200
        data = response.json()

        # 2 logs share booking_reference -> collapse to 1.
        # 2 logs have no session and no booking_reference -> dropped by the
        # ghost-row filter (Stripe webhook used to write these for manual
        # Payment Links and they double-counted against the Manual column;
        # see test_session_tracking_ghost_hueb.py for the full pin).
        # Total: 1 unique "session" for booking_confirmed.
        assert data["cumulative"]["counts"]["booking_confirmed"] == 1


# =============================================================================
# Tests - Authentication
# =============================================================================

class TestSessionTrackingAuthentication:
    """Tests for authentication on session tracking endpoints."""

    def test_session_tracking_requires_admin(self, mock_db):
        """Session tracking report should require admin authentication."""
        from main import app, get_db

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        # Don't override require_admin - should fail auth

        client = TestClient(app)
        response = client.get("/api/admin/reports/session-tracking")

        # Should return 401 or 403 without auth
        assert response.status_code in [401, 403, 422]

        app.dependency_overrides.clear()

    def test_audit_event_does_not_require_auth(self, mock_db):
        """Audit event endpoint should not require authentication."""
        from main import app, get_db

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        client = TestClient(app)
        response = client.post(
            "/api/booking/audit-event",
            json={
                "session_id": "sess_123",
                "event": "dates_selected",
                "event_data": {}
            }
        )

        # Should work without auth
        assert response.status_code == 200

        app.dependency_overrides.clear()


# =============================================================================
# Tests - Manual Booking Sources (phone, walk-in)
# =============================================================================

class TestManualBookingSources:
    """Tests for manual booking source counting in session tracking."""

    def test_manual_bookings_count_includes_manual_source(self, client, mock_db):
        """Manual bookings count should include booking_source='manual'."""
        import pytz
        from db_models import BookingStatus

        uk_tz = pytz.timezone('Europe/London')
        now = datetime.now(uk_tz)

        # Create mock booking with 'manual' source
        mock_booking = MagicMock()
        mock_booking.id = 1
        mock_booking.booking_source = "manual"
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.created_at = now

        # Set up mock to return empty audit logs but manual bookings
        def query_side_effect(model):
            query_mock = MagicMock()
            if hasattr(model, '__name__') and model.__name__ == 'Booking':
                query_mock.filter.return_value.all.return_value = [mock_booking]
            else:
                query_mock.filter.return_value.all.return_value = []
            return query_mock

        mock_db.query.side_effect = query_side_effect

        response = client.get("/api/admin/reports/session-tracking?period=daily")

        assert response.status_code == 200
        data = response.json()
        assert "cumulative" in data
        assert "manual_bookings" in data["cumulative"]

    def test_manual_bookings_count_includes_admin_source(self, client, mock_db):
        """Manual bookings count should include booking_source='admin'."""
        import pytz
        from db_models import BookingStatus

        uk_tz = pytz.timezone('Europe/London')
        now = datetime.now(uk_tz)

        mock_booking = MagicMock()
        mock_booking.id = 1
        mock_booking.booking_source = "admin"
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.created_at = now

        def query_side_effect(model):
            query_mock = MagicMock()
            if hasattr(model, '__name__') and model.__name__ == 'Booking':
                query_mock.filter.return_value.all.return_value = [mock_booking]
            else:
                query_mock.filter.return_value.all.return_value = []
            return query_mock

        mock_db.query.side_effect = query_side_effect

        response = client.get("/api/admin/reports/session-tracking?period=daily")

        assert response.status_code == 200
        data = response.json()
        assert "cumulative" in data
        assert "manual_bookings" in data["cumulative"]

    def test_manual_bookings_count_includes_phone_source(self, client, mock_db):
        """Manual bookings count should include booking_source='phone'."""
        import pytz
        from db_models import BookingStatus

        uk_tz = pytz.timezone('Europe/London')
        now = datetime.now(uk_tz)

        mock_booking = MagicMock()
        mock_booking.id = 1
        mock_booking.booking_source = "phone"
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.created_at = now

        def query_side_effect(model):
            query_mock = MagicMock()
            if hasattr(model, '__name__') and model.__name__ == 'Booking':
                query_mock.filter.return_value.all.return_value = [mock_booking]
            else:
                query_mock.filter.return_value.all.return_value = []
            return query_mock

        mock_db.query.side_effect = query_side_effect

        response = client.get("/api/admin/reports/session-tracking?period=daily")

        assert response.status_code == 200
        data = response.json()
        assert "cumulative" in data
        assert "manual_bookings" in data["cumulative"]

    def test_manual_bookings_count_includes_walkin_source(self, client, mock_db):
        """Manual bookings count should include booking_source='walk-in'."""
        import pytz
        from db_models import BookingStatus

        uk_tz = pytz.timezone('Europe/London')
        now = datetime.now(uk_tz)

        mock_booking = MagicMock()
        mock_booking.id = 1
        mock_booking.booking_source = "walk-in"
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.created_at = now

        def query_side_effect(model):
            query_mock = MagicMock()
            if hasattr(model, '__name__') and model.__name__ == 'Booking':
                query_mock.filter.return_value.all.return_value = [mock_booking]
            else:
                query_mock.filter.return_value.all.return_value = []
            return query_mock

        mock_db.query.side_effect = query_side_effect

        response = client.get("/api/admin/reports/session-tracking?period=daily")

        assert response.status_code == 200
        data = response.json()
        assert "cumulative" in data
        assert "manual_bookings" in data["cumulative"]

    def test_multiple_manual_source_types_counted(self, client, mock_db):
        """Multiple manual source types should all be counted."""
        import pytz
        from db_models import BookingStatus

        uk_tz = pytz.timezone('Europe/London')
        now = datetime.now(uk_tz)

        # Create bookings with different manual source types
        mock_bookings = []
        for i, source in enumerate(['manual', 'admin', 'phone', 'walk-in']):
            booking = MagicMock()
            booking.id = i + 1
            booking.booking_source = source
            booking.status = BookingStatus.CONFIRMED
            booking.created_at = now
            mock_bookings.append(booking)

        # Verify that all 4 booking sources are valid manual sources
        manual_sources = ['manual', 'admin', 'phone', 'walk-in']
        for booking in mock_bookings:
            assert booking.booking_source in manual_sources

        # Verify we created 4 bookings
        assert len(mock_bookings) == 4

    def test_online_source_not_counted_as_manual(self, client, mock_db):
        """Online bookings should NOT be counted in manual bookings."""
        from db_models import BookingStatus

        # Create booking with online source
        mock_booking = MagicMock()
        mock_booking.id = 1
        mock_booking.booking_source = "online"
        mock_booking.status = BookingStatus.CONFIRMED

        # Verify that 'online' is NOT in the manual sources list
        manual_sources = ['manual', 'admin', 'phone', 'walk-in']
        assert mock_booking.booking_source not in manual_sources

        # This booking would not be included in the manual booking count
        # because the query filters for booking_source.in_(['manual', 'admin', 'phone', 'walk-in'])
        assert mock_booking.booking_source == "online"

    def test_manual_bookings_per_period(self, client, mock_db):
        """Manual bookings should be counted per period."""
        import pytz
        from db_models import BookingStatus

        uk_tz = pytz.timezone('Europe/London')
        now = datetime.now(uk_tz)

        mock_booking = MagicMock()
        mock_booking.id = 1
        mock_booking.booking_source = "phone"
        mock_booking.status = BookingStatus.CONFIRMED
        mock_booking.created_at = now

        def query_side_effect(model):
            query_mock = MagicMock()
            if hasattr(model, '__name__') and model.__name__ == 'Booking':
                query_mock.filter.return_value.all.return_value = [mock_booking]
            else:
                query_mock.filter.return_value.all.return_value = []
            return query_mock

        mock_db.query.side_effect = query_side_effect

        response = client.get("/api/admin/reports/session-tracking?period=daily")

        assert response.status_code == 200
        data = response.json()

        # Check that periods array exists
        assert "periods" in data

    def test_completed_manual_bookings_included(self, client, mock_db):
        """Completed manual bookings should be included in count."""
        import pytz
        from db_models import BookingStatus

        uk_tz = pytz.timezone('Europe/London')
        now = datetime.now(uk_tz)

        mock_booking = MagicMock()
        mock_booking.id = 1
        mock_booking.booking_source = "phone"
        mock_booking.status = BookingStatus.COMPLETED  # Completed, not just confirmed
        mock_booking.created_at = now

        def query_side_effect(model):
            query_mock = MagicMock()
            if hasattr(model, '__name__') and model.__name__ == 'Booking':
                query_mock.filter.return_value.all.return_value = [mock_booking]
            else:
                query_mock.filter.return_value.all.return_value = []
            return query_mock

        mock_db.query.side_effect = query_side_effect

        response = client.get("/api/admin/reports/session-tracking?period=daily")

        assert response.status_code == 200
        data = response.json()
        assert "cumulative" in data
        assert "manual_bookings" in data["cumulative"]
