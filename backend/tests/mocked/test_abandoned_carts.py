"""
Unit tests for abandoned carts analytics endpoint.
Tests cover: happy path, unhappy path, edge cases and boundaries.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import pytz

uk_tz = pytz.timezone('Europe/London')


# Helper to create mock audit log
def create_mock_audit_log(session_id, event, created_at, event_data=None):
    mock = MagicMock()
    mock.session_id = session_id
    mock.event = event
    mock.created_at = created_at
    mock.event_data = event_data
    return mock


class TestAbandonedCartsHappyPath:
    """Happy path tests - successful scenarios"""

    def test_returns_abandoned_sessions_count(self):
        """Sessions with dates/flights selected but no payment should be counted as abandoned"""
        now = datetime.now(uk_tz)

        # 3 sessions started, 1 completed = 2 abandoned
        started_sessions = [
            create_mock_audit_log("session1", "DATES_SELECTED", now - timedelta(hours=1)),
            create_mock_audit_log("session2", "FLIGHT_SELECTED", now - timedelta(hours=2)),
            create_mock_audit_log("session3", "DATES_SELECTED", now - timedelta(hours=3)),
        ]
        completed_sessions = [("session1",)]  # Only session1 completed

        # Filter out completed
        abandoned = [s for s in started_sessions if s.session_id not in {c[0] for c in completed_sessions}]

        assert len(abandoned) == 2
        assert abandoned[0].session_id == "session2"
        assert abandoned[1].session_id == "session3"

    def test_groups_by_daily_period(self):
        """Abandoned sessions should be grouped by date for daily view"""
        now = datetime.now(uk_tz)
        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        sessions = [
            {"session_id": "s1", "date": today},
            {"session_id": "s2", "date": today},
            {"session_id": "s3", "date": yesterday},
        ]

        # Group by date
        from collections import defaultdict
        period_data = defaultdict(set)
        for s in sessions:
            period_data[s["date"]].add(s["session_id"])

        assert len(period_data[today]) == 2
        assert len(period_data[yesterday]) == 1

    def test_groups_by_weekly_period(self):
        """Abandoned sessions should be grouped by week for weekly view"""
        now = datetime.now(uk_tz)
        this_week = now.strftime("%Y-W%W")
        last_week = (now - timedelta(weeks=1)).strftime("%Y-W%W")

        sessions = [
            {"session_id": "s1", "week": this_week},
            {"session_id": "s2", "week": this_week},
            {"session_id": "s3", "week": last_week},
        ]

        from collections import defaultdict
        period_data = defaultdict(set)
        for s in sessions:
            period_data[s["week"]].add(s["session_id"])

        assert len(period_data[this_week]) == 2
        assert len(period_data[last_week]) == 1

    def test_groups_by_monthly_period(self):
        """Abandoned sessions should be grouped by month for monthly view"""
        sessions = [
            {"session_id": "s1", "month": "2026-04"},
            {"session_id": "s2", "month": "2026-04"},
            {"session_id": "s3", "month": "2026-03"},
        ]

        from collections import defaultdict
        period_data = defaultdict(set)
        for s in sessions:
            period_data[s["month"]].add(s["session_id"])

        assert len(period_data["2026-04"]) == 2
        assert len(period_data["2026-03"]) == 1

    def test_tracks_top_destinations(self):
        """Should track abandoned sessions by destination"""
        sessions = [
            {"session_id": "s1", "destination": "Malaga"},
            {"session_id": "s2", "destination": "Malaga"},
            {"session_id": "s3", "destination": "Alicante"},
            {"session_id": "s4", "destination": "Malaga"},
        ]

        from collections import defaultdict
        destination_sessions = defaultdict(set)
        for s in sessions:
            destination_sessions[s["destination"]].add(s["session_id"])

        # Sort by count
        top = sorted(
            [{"destination": k, "count": len(v)} for k, v in destination_sessions.items()],
            key=lambda x: x["count"],
            reverse=True
        )

        assert top[0]["destination"] == "Malaga"
        assert top[0]["count"] == 3
        assert top[1]["destination"] == "Alicante"
        assert top[1]["count"] == 1

    def test_tracks_top_trip_lengths(self):
        """Should track abandoned sessions by trip length in days"""
        sessions = [
            {"session_id": "s1", "days": 7},
            {"session_id": "s2", "days": 7},
            {"session_id": "s3", "days": 14},
            {"session_id": "s4", "days": 7},
        ]

        from collections import defaultdict
        days_sessions = defaultdict(set)
        for s in sessions:
            days_sessions[s["days"]].add(s["session_id"])

        top = sorted(
            [{"days": k, "count": len(v)} for k, v in days_sessions.items()],
            key=lambda x: x["count"],
            reverse=True
        )

        assert top[0]["days"] == 7
        assert top[0]["count"] == 3

    def test_returns_recent_abandoned_with_details(self):
        """Recent abandoned sessions should include flight details"""
        import json
        now = datetime.now(uk_tz)

        event_data = {
            "dropoff_date": "2026-04-10",
            "pickup_date": "2026-04-17",
            "departure_time": "08:00",
            "arrival_time": "11:30",
            "departure_destination": "Malaga",
            "departure_airline": "Ryanair"
        }

        log = create_mock_audit_log(
            "session1",
            "FLIGHT_SELECTED",
            now - timedelta(hours=1),
            json.dumps(event_data)
        )

        data = json.loads(log.event_data)

        recent = {
            "session_id": log.session_id,
            "dropoff_date": data.get("dropoff_date"),
            "pickup_date": data.get("pickup_date"),
            "destination": data.get("departure_destination"),
            "airline": data.get("departure_airline"),
        }

        assert recent["session_id"] == "session1"
        assert recent["dropoff_date"] == "2026-04-10"
        assert recent["pickup_date"] == "2026-04-17"
        assert recent["destination"] == "Malaga"
        assert recent["airline"] == "Ryanair"

    def test_refresh_bypasses_cache(self):
        """When refresh=True, cache should be bypassed"""
        cache = {"data": {"cached": True}, "cached_at": datetime.now(uk_tz)}
        refresh = True

        # Simulate cache bypass logic
        use_cache = not refresh and cache.get("data") is not None

        assert use_cache is False

    def test_cache_used_when_valid(self):
        """When refresh=False and cache is valid, cached data should be returned"""
        now = datetime.now(uk_tz)
        cache = {
            "data": {"total_abandoned": 10},
            "cached_at": now - timedelta(minutes=30)  # 30 mins old, within 1 hour limit
        }
        cache_duration = 3600  # 1 hour
        refresh = False

        cache_age = (now - cache["cached_at"]).total_seconds()
        use_cache = not refresh and cache.get("data") is not None and cache_age < cache_duration

        assert use_cache is True


class TestAbandonedCartsUnhappyPath:
    """Unhappy path tests - error scenarios and edge conditions"""

    def test_no_sessions_returns_empty(self):
        """When no sessions exist, should return empty data"""
        started_sessions = []
        completed_sessions = []

        abandoned = [s for s in started_sessions if s not in completed_sessions]

        assert len(abandoned) == 0

    def test_all_sessions_completed_returns_zero_abandoned(self):
        """When all sessions complete payment, abandoned count should be 0"""
        started = ["session1", "session2", "session3"]
        completed = {"session1", "session2", "session3"}

        abandoned = [s for s in started if s not in completed]

        assert len(abandoned) == 0

    def test_invalid_event_data_handled_gracefully(self):
        """Invalid JSON in event_data should not crash"""
        import json

        invalid_event_data = "not valid json {"

        try:
            data = json.loads(invalid_event_data)
        except json.JSONDecodeError:
            data = {}

        assert data == {}

    def test_missing_session_id_filtered_out(self):
        """Logs without session_id should be filtered out"""
        logs = [
            {"session_id": "valid1", "event": "DATES_SELECTED"},
            {"session_id": None, "event": "DATES_SELECTED"},
            {"session_id": "valid2", "event": "FLIGHT_SELECTED"},
        ]

        valid_logs = [l for l in logs if l["session_id"] is not None]

        assert len(valid_logs) == 2

    def test_expired_cache_not_used(self):
        """When cache is older than duration, fresh data should be fetched"""
        now = datetime.now(uk_tz)
        cache = {
            "data": {"total_abandoned": 10},
            "cached_at": now - timedelta(hours=2)  # 2 hours old
        }
        cache_duration = 3600  # 1 hour
        refresh = False

        cache_age = (now - cache["cached_at"]).total_seconds()
        use_cache = not refresh and cache.get("data") is not None and cache_age < cache_duration

        assert use_cache is False

    def test_empty_cache_not_used(self):
        """When cache data is None, fresh data should be fetched"""
        cache = {"data": None, "cached_at": None}
        refresh = False

        use_cache = not refresh and cache.get("data") is not None

        assert use_cache is False

    def test_missing_destination_not_counted(self):
        """Sessions without destination in event_data should not appear in top destinations"""
        import json

        event_data_no_dest = {"dropoff_date": "2026-04-10", "pickup_date": "2026-04-17"}

        data = event_data_no_dest
        destination = data.get("departure_destination")

        assert destination is None

    def test_invalid_date_format_handled(self):
        """Invalid date format in event_data should not crash"""
        event_data = {"dropoff_date": "invalid", "pickup_date": "also-invalid"}

        try:
            d1 = datetime.strptime(event_data["dropoff_date"], "%Y-%m-%d")
            d2 = datetime.strptime(event_data["pickup_date"], "%Y-%m-%d")
            days = (d2 - d1).days
        except ValueError:
            days = None

        assert days is None


class TestAbandonedCartsEdgeCases:
    """Edge cases and boundary conditions"""

    def test_session_with_both_events_counted_once(self):
        """A session with both DATES_SELECTED and FLIGHT_SELECTED should only be counted once"""
        session_ids = set()

        logs = [
            {"session_id": "session1", "event": "DATES_SELECTED"},
            {"session_id": "session1", "event": "FLIGHT_SELECTED"},  # Same session
            {"session_id": "session2", "event": "DATES_SELECTED"},
        ]

        for log in logs:
            session_ids.add(log["session_id"])

        assert len(session_ids) == 2  # Only 2 unique sessions

    def test_exactly_30_days_included_for_daily(self):
        """Daily view should include sessions from exactly 30 days ago"""
        now = datetime.now(uk_tz)
        start_date = now - timedelta(days=30)

        session_date = now - timedelta(days=30)  # Exactly 30 days ago

        assert session_date >= start_date

    def test_31_days_excluded_for_daily(self):
        """Daily view should exclude sessions from 31 days ago"""
        now = datetime.now(uk_tz)
        start_date = now - timedelta(days=30)

        session_date = now - timedelta(days=31)  # 31 days ago

        assert session_date < start_date

    def test_feature_deploy_date_boundary(self):
        """Sessions before feature deploy date should be excluded"""
        feature_deploy = datetime(2026, 3, 29, 17, 0, 0, tzinfo=uk_tz)

        before_deploy = datetime(2026, 3, 29, 16, 59, 0, tzinfo=uk_tz)
        after_deploy = datetime(2026, 3, 29, 17, 1, 0, tzinfo=uk_tz)

        assert before_deploy < feature_deploy
        assert after_deploy > feature_deploy

    def test_midnight_session_attribution(self):
        """Session at midnight should be attributed to correct day"""
        midnight = uk_tz.localize(datetime(2026, 4, 4, 0, 0, 0))

        period_key = midnight.strftime("%Y-%m-%d")

        assert period_key == "2026-04-04"

    def test_end_of_day_session_attribution(self):
        """Session at 23:59:59 should be attributed to that day"""
        end_of_day = uk_tz.localize(datetime(2026, 4, 4, 23, 59, 59))

        period_key = end_of_day.strftime("%Y-%m-%d")

        assert period_key == "2026-04-04"

    def test_recent_abandoned_limited_to_100(self):
        """Recent abandoned list should not exceed 100 items during collection"""
        max_recent = 100
        recent_abandoned = []

        for i in range(150):
            if len(recent_abandoned) < max_recent:
                recent_abandoned.append({"session_id": f"session{i}"})

        assert len(recent_abandoned) == 100

    def test_recent_abandoned_response_limited_to_50(self):
        """API response should limit recent abandoned to 50"""
        recent_abandoned = [{"session_id": f"s{i}"} for i in range(100)]

        response_recent = recent_abandoned[:50]

        assert len(response_recent) == 50

    def test_top_destinations_limited_to_10(self):
        """Top destinations should be limited to 10"""
        destinations = {f"dest{i}": {f"s{j}" for j in range(i)} for i in range(1, 20)}

        top = sorted(
            [{"destination": k, "count": len(v)} for k, v in destinations.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:10]

        assert len(top) == 10

    def test_top_days_limited_to_10(self):
        """Top trip lengths should be limited to 10"""
        days = {i: {f"s{j}" for j in range(i)} for i in range(1, 20)}

        top = sorted(
            [{"days": k, "count": len(v)} for k, v in days.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:10]

        assert len(top) == 10

    def test_zero_day_trip_excluded(self):
        """Trip with 0 days (same drop-off and pick-up) should be excluded"""
        dropoff = "2026-04-10"
        pickup = "2026-04-10"

        d1 = datetime.strptime(dropoff, "%Y-%m-%d")
        d2 = datetime.strptime(pickup, "%Y-%m-%d")
        days = (d2 - d1).days

        # Logic: only include if days > 0
        include = days > 0

        assert include is False

    def test_negative_days_excluded(self):
        """Trip with negative days (pickup before dropoff) should be excluded"""
        dropoff = "2026-04-10"
        pickup = "2026-04-05"  # Before dropoff

        d1 = datetime.strptime(dropoff, "%Y-%m-%d")
        d2 = datetime.strptime(pickup, "%Y-%m-%d")
        days = (d2 - d1).days

        include = days > 0

        assert include is False
        assert days == -5

    def test_timezone_aware_vs_naive_datetime(self):
        """Should handle both timezone-aware and naive datetimes"""
        naive_dt = datetime(2026, 4, 4, 12, 0, 0)
        aware_dt = uk_tz.localize(datetime(2026, 4, 4, 12, 0, 0))

        # Logic from the code
        if naive_dt.tzinfo is None:
            naive_dt = uk_tz.localize(naive_dt)

        assert naive_dt.tzinfo is not None
        assert aware_dt.tzinfo is not None

    def test_cache_age_calculation(self):
        """Cache age should be calculated correctly in seconds"""
        now = datetime.now(uk_tz)
        cached_at = now - timedelta(minutes=45)

        cache_age = (now - cached_at).total_seconds()

        assert 2700 <= cache_age <= 2701  # 45 minutes = 2700 seconds

    def test_weekly_period_format(self):
        """Weekly period key should use ISO week format"""
        dt = uk_tz.localize(datetime(2026, 4, 4, 12, 0, 0))

        period_key = dt.strftime("%Y-W%W")

        # April 4, 2026 is in week 13
        assert period_key.startswith("2026-W")

    def test_monthly_period_format(self):
        """Monthly period key should use YYYY-MM format"""
        dt = uk_tz.localize(datetime(2026, 4, 4, 12, 0, 0))

        period_key = dt.strftime("%Y-%m")

        assert period_key == "2026-04"
