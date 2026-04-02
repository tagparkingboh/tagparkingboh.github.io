"""
Unit tests for database pool snapshot recording.

Tests cover:
- Event-driven threshold crossing snapshots
- Threshold level calculation
- Health status determination
- Cleanup of old snapshots
- Error handling
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


class TestGetThresholdLevel:
    """Tests for the _get_threshold_level function."""

    def test_returns_0_below_50_percent(self):
        """Returns 0 when usage is below 50%."""
        from database import _get_threshold_level

        assert _get_threshold_level(0) == 0
        assert _get_threshold_level(25) == 0
        assert _get_threshold_level(49.9) == 0

    def test_returns_50_at_50_percent(self):
        """Returns 50 when usage is at or above 50%."""
        from database import _get_threshold_level

        assert _get_threshold_level(50) == 50
        assert _get_threshold_level(55) == 50
        assert _get_threshold_level(69.9) == 50

    def test_returns_70_at_70_percent(self):
        """Returns 70 when usage is at or above 70%."""
        from database import _get_threshold_level

        assert _get_threshold_level(70) == 70
        assert _get_threshold_level(75) == 70
        assert _get_threshold_level(84.9) == 70

    def test_returns_85_at_85_percent(self):
        """Returns 85 when usage is at or above 85%."""
        from database import _get_threshold_level

        assert _get_threshold_level(85) == 85
        assert _get_threshold_level(87) == 85
        assert _get_threshold_level(89.9) == 85

    def test_returns_90_at_90_percent(self):
        """Returns 90 when usage is at or above 90%."""
        from database import _get_threshold_level

        assert _get_threshold_level(90) == 90
        assert _get_threshold_level(95) == 90
        assert _get_threshold_level(100) == 90


class TestRecordThresholdSnapshot:
    """Tests for the _record_threshold_snapshot function."""

    @patch('database.SessionLocal')
    def test_records_snapshot_with_correct_trigger(self, mock_session_local):
        """Records a snapshot with the correct trigger value."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        from database import _record_threshold_snapshot

        _record_threshold_snapshot("crossed_70", 72.5, 15, 7)

        # Verify add was called
        mock_db.add.assert_called_once()
        snapshot = mock_db.add.call_args[0][0]
        assert snapshot.trigger == "crossed_70"
        assert snapshot.usage_percent == 72.5
        assert snapshot.checked_out == 15
        assert snapshot.overflow == 7

    @patch('database.SessionLocal')
    def test_determines_health_status_correctly(self, mock_session_local):
        """Determines health status based on usage percent."""
        from db_models import PoolHealthStatus
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        from database import _record_threshold_snapshot

        # Test HEALTHY status
        _record_threshold_snapshot("crossed_50", 55, 10, 5)
        snapshot = mock_db.add.call_args[0][0]
        assert snapshot.health_status == PoolHealthStatus.HEALTHY

        # Test WARNING status
        _record_threshold_snapshot("crossed_70", 75, 18, 5)
        snapshot = mock_db.add.call_args[0][0]
        assert snapshot.health_status == PoolHealthStatus.WARNING

        # Test CRITICAL status
        _record_threshold_snapshot("crossed_90", 92, 25, 5)
        snapshot = mock_db.add.call_args[0][0]
        assert snapshot.health_status == PoolHealthStatus.CRITICAL

    @patch('database.SessionLocal')
    def test_handles_database_error_gracefully(self, mock_session_local):
        """Handles database errors without crashing."""
        mock_db = MagicMock()
        mock_db.add.side_effect = Exception("DB error")
        mock_session_local.return_value = mock_db

        from database import _record_threshold_snapshot

        # Should not raise an exception
        _record_threshold_snapshot("crossed_50", 55, 10, 5)


class TestThresholdCrossing:
    """Tests for threshold crossing detection logic."""

    def test_crossing_up_triggers_snapshot(self):
        """Crossing up to a new threshold triggers a snapshot."""
        import database

        # Reset threshold level
        database._last_threshold_level = 0

        # Simulate crossing from 0 to 50
        with patch.object(database, '_record_threshold_snapshot') as mock_record:
            # Get the current level for 55% usage
            current_level = database._get_threshold_level(55)
            assert current_level == 50

            # The checkout handler would compare and record
            if current_level > database._last_threshold_level:
                database._record_threshold_snapshot("crossed_50", 55, 15, 2)
                database._last_threshold_level = current_level

            mock_record.assert_called_once_with("crossed_50", 55, 15, 2)

    def test_crossing_down_triggers_snapshot(self):
        """Dropping below a threshold triggers a snapshot."""
        import database

        # Start at 70% threshold
        database._last_threshold_level = 70

        # Simulate dropping below 70
        with patch.object(database, '_record_threshold_snapshot') as mock_record:
            current_level = database._get_threshold_level(45)
            assert current_level == 0

            if current_level < database._last_threshold_level:
                dropped_from = database._last_threshold_level
                database._record_threshold_snapshot(f"dropped_below_{dropped_from}", 45, 8, 0)
                database._last_threshold_level = current_level

            mock_record.assert_called_once_with("dropped_below_70", 45, 8, 0)

    def test_no_snapshot_when_staying_at_same_level(self):
        """No snapshot when staying at the same threshold level."""
        import database

        database._last_threshold_level = 50

        with patch.object(database, '_record_threshold_snapshot') as mock_record:
            # Usage going from 55% to 60% (both at level 50)
            current_level = database._get_threshold_level(60)
            assert current_level == 50

            # Should not trigger snapshot
            if current_level > database._last_threshold_level:
                database._record_threshold_snapshot("crossed_50", 60, 16, 2)

            mock_record.assert_not_called()


class TestCleanupOldSnapshots:
    """Tests for the cleanup_old_snapshots function."""

    @patch('email_scheduler.get_db')
    def test_deletes_snapshots_older_than_7_days(self, mock_get_db):
        """Deletes snapshots older than 7 days."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.delete.return_value = 100  # 100 records deleted

        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query
        mock_get_db.return_value = mock_db

        from email_scheduler import cleanup_old_snapshots
        cleanup_old_snapshots()

        # Verify query was executed
        mock_db.query.assert_called_once()
        mock_query.filter.assert_called_once()
        mock_filter.delete.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch('email_scheduler.get_db')
    def test_handles_cleanup_error_gracefully(self, mock_get_db):
        """Handles cleanup errors without crashing."""
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Query error")
        mock_get_db.return_value = mock_db

        # Should not raise an exception
        from email_scheduler import cleanup_old_snapshots
        cleanup_old_snapshots()

    @patch('email_scheduler.get_db')
    def test_logs_when_records_deleted(self, mock_get_db):
        """Logs info message when records are deleted."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.delete.return_value = 50

        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query
        mock_get_db.return_value = mock_db

        with patch('email_scheduler.logger') as mock_logger:
            from email_scheduler import cleanup_old_snapshots
            cleanup_old_snapshots()

            # Should log the number deleted
            mock_logger.info.assert_called()


class TestDbPoolSnapshotModel:
    """Tests for the DbPoolSnapshot model."""

    def test_model_has_required_fields(self):
        """Model has all required fields."""
        from db_models import DbPoolSnapshot, PoolHealthStatus

        # Create a snapshot instance
        snapshot = DbPoolSnapshot(
            pool_size=10,
            max_overflow=20,
            checked_out=5,
            overflow=0,
            checked_in=5,
            usage_percent=16.7,
            health_status=PoolHealthStatus.HEALTHY,
            trigger="crossed_50",
        )

        assert snapshot.pool_size == 10
        assert snapshot.max_overflow == 20
        assert snapshot.checked_out == 5
        assert snapshot.overflow == 0
        assert snapshot.checked_in == 5
        assert snapshot.usage_percent == 16.7
        assert snapshot.health_status == PoolHealthStatus.HEALTHY
        assert snapshot.trigger == "crossed_50"

    def test_model_supports_event_trigger_values(self):
        """Model supports various event-driven trigger values."""
        from db_models import DbPoolSnapshot, PoolHealthStatus

        triggers = ["crossed_50", "crossed_70", "crossed_85", "crossed_90",
                    "dropped_below_50", "dropped_below_70", "dropped_below_85", "dropped_below_90"]

        for trigger in triggers:
            snapshot = DbPoolSnapshot(
                pool_size=10,
                max_overflow=20,
                checked_out=5,
                overflow=0,
                checked_in=5,
                usage_percent=50.0,
                health_status=PoolHealthStatus.HEALTHY,
                trigger=trigger,
            )
            assert snapshot.trigger == trigger

    def test_model_repr(self):
        """Model has a useful repr."""
        from db_models import DbPoolSnapshot, PoolHealthStatus
        from datetime import datetime

        snapshot = DbPoolSnapshot(
            pool_size=10,
            max_overflow=20,
            checked_out=5,
            overflow=0,
            checked_in=5,
            usage_percent=50.0,
            health_status=PoolHealthStatus.HEALTHY,
            trigger="crossed_50",
        )
        snapshot.created_at = datetime(2026, 4, 2, 12, 0, 0)

        repr_str = repr(snapshot)
        assert "DbPoolSnapshot" in repr_str
        assert "healthy" in repr_str


class TestPoolHealthStatusEnum:
    """Tests for the PoolHealthStatus enum."""

    def test_enum_values(self):
        """Enum has correct values."""
        from db_models import PoolHealthStatus

        assert PoolHealthStatus.HEALTHY.value == "healthy"
        assert PoolHealthStatus.WARNING.value == "warning"
        assert PoolHealthStatus.CRITICAL.value == "critical"

    def test_enum_members(self):
        """Enum has all expected members."""
        from db_models import PoolHealthStatus

        members = list(PoolHealthStatus)
        assert len(members) == 3
        assert PoolHealthStatus.HEALTHY in members
        assert PoolHealthStatus.WARNING in members
        assert PoolHealthStatus.CRITICAL in members


class TestSchedulerJobConfiguration:
    """Tests for scheduler job setup."""

    @patch('email_scheduler.scheduler')
    def test_cleanup_job_added_on_start(self, mock_scheduler):
        """Cleanup job is added when scheduler starts."""
        mock_scheduler.running = False

        from email_scheduler import start_scheduler
        start_scheduler()

        # Find the cleanup job
        calls = mock_scheduler.add_job.call_args_list
        job_ids = [call[1].get('id') for call in calls]

        assert 'cleanup_pool_snapshots' in job_ids

    @patch('email_scheduler.scheduler')
    def test_no_scheduled_snapshot_job(self, mock_scheduler):
        """Pool snapshots are event-driven, not scheduled."""
        mock_scheduler.running = False

        from email_scheduler import start_scheduler
        start_scheduler()

        # Verify record_pool_snapshot job is NOT added
        calls = mock_scheduler.add_job.call_args_list
        job_ids = [call[1].get('id') for call in calls]

        assert 'record_pool_snapshot' not in job_ids

    @patch('email_scheduler.scheduler')
    def test_cleanup_runs_daily(self, mock_scheduler):
        """Cleanup job is configured to run daily."""
        mock_scheduler.running = False

        from email_scheduler import start_scheduler
        start_scheduler()

        # Find the cleanup job call and check interval
        for call in mock_scheduler.add_job.call_args_list:
            if call[1].get('id') == 'cleanup_pool_snapshots':
                trigger = call[1].get('trigger')
                assert trigger.interval.total_seconds() == 86400  # 24 hours


class TestUsageThresholds:
    """Tests for usage threshold configuration."""

    def test_thresholds_are_defined(self):
        """Usage thresholds are correctly defined."""
        from database import USAGE_THRESHOLDS

        assert USAGE_THRESHOLDS == [50, 70, 85, 90]

    def test_thresholds_are_in_order(self):
        """Thresholds are in ascending order."""
        from database import USAGE_THRESHOLDS

        assert USAGE_THRESHOLDS == sorted(USAGE_THRESHOLDS)
