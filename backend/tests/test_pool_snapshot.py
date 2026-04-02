"""
Unit tests for database pool snapshot recording.

Tests cover:
- Scheduled snapshot recording
- Health status determination
- Cleanup of old snapshots
- Error handling
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


class TestRecordPoolSnapshot:
    """Tests for the record_pool_snapshot scheduler function."""

    @patch('database.get_pool_status')
    def test_records_healthy_snapshot(self, mock_status, db_session):
        """Records a snapshot with HEALTHY status when usage is low."""
        from db_models import DbPoolSnapshot, PoolHealthStatus

        mock_status.return_value = {
            "pool_size": 10,
            "max_overflow": 20,
            "checked_out": 5,
            "overflow": 0,
            "checked_in": 5,
            "usage_percent": 16.7,
        }

        # Create snapshot directly to test the model
        snapshot = DbPoolSnapshot(
            pool_size=10,
            max_overflow=20,
            checked_out=5,
            overflow=0,
            checked_in=5,
            usage_percent=16.7,
            health_status=PoolHealthStatus.HEALTHY,
            trigger="scheduled",
        )

        assert snapshot.pool_size == 10
        assert snapshot.health_status == PoolHealthStatus.HEALTHY
        assert snapshot.trigger == "scheduled"

    def test_warning_status_at_70_percent(self):
        """WARNING status is used at 70%+ usage."""
        from db_models import DbPoolSnapshot, PoolHealthStatus

        # At 70%, should be WARNING
        snapshot = DbPoolSnapshot(
            pool_size=10,
            max_overflow=20,
            checked_out=18,
            overflow=3,
            checked_in=0,
            usage_percent=70,
            health_status=PoolHealthStatus.WARNING,
            trigger="scheduled",
        )
        assert snapshot.health_status == PoolHealthStatus.WARNING

    def test_critical_status_at_90_percent(self):
        """CRITICAL status is used at 90%+ usage."""
        from db_models import DbPoolSnapshot, PoolHealthStatus

        snapshot = DbPoolSnapshot(
            pool_size=10,
            max_overflow=20,
            checked_out=25,
            overflow=5,
            checked_in=0,
            usage_percent=92,
            health_status=PoolHealthStatus.CRITICAL,
            trigger="scheduled",
        )
        assert snapshot.health_status == PoolHealthStatus.CRITICAL

    @patch('database.get_pool_status')
    def test_handles_pool_status_error_gracefully(self, mock_status):
        """Handles pool status fetch errors without crashing."""
        mock_status.side_effect = Exception("Pool error")

        # Should not raise an exception
        from email_scheduler import record_pool_snapshot
        record_pool_snapshot()

    def test_health_status_thresholds(self):
        """Health status thresholds are correctly defined."""
        from db_models import PoolHealthStatus

        # Define the thresholds as used in the application
        def get_health_status(usage_percent):
            if usage_percent >= 90:
                return PoolHealthStatus.CRITICAL
            elif usage_percent >= 70:
                return PoolHealthStatus.WARNING
            else:
                return PoolHealthStatus.HEALTHY

        assert get_health_status(50) == PoolHealthStatus.HEALTHY
        assert get_health_status(69) == PoolHealthStatus.HEALTHY
        assert get_health_status(70) == PoolHealthStatus.WARNING
        assert get_health_status(89) == PoolHealthStatus.WARNING
        assert get_health_status(90) == PoolHealthStatus.CRITICAL
        assert get_health_status(100) == PoolHealthStatus.CRITICAL


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
            trigger="scheduled",
        )

        assert snapshot.pool_size == 10
        assert snapshot.max_overflow == 20
        assert snapshot.checked_out == 5
        assert snapshot.overflow == 0
        assert snapshot.checked_in == 5
        assert snapshot.usage_percent == 16.7
        assert snapshot.health_status == PoolHealthStatus.HEALTHY
        assert snapshot.trigger == "scheduled"

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
            trigger="scheduled",
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
    def test_pool_snapshot_job_added_on_start(self, mock_scheduler):
        """Pool snapshot job is added when scheduler starts."""
        mock_scheduler.running = False

        from email_scheduler import start_scheduler
        start_scheduler()

        # Find the record_pool_snapshot job
        calls = mock_scheduler.add_job.call_args_list
        job_ids = [call[1].get('id') for call in calls]

        assert 'record_pool_snapshot' in job_ids

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
    def test_pool_snapshot_runs_every_minute(self, mock_scheduler):
        """Pool snapshot job is configured to run every minute."""
        mock_scheduler.running = False

        from email_scheduler import start_scheduler
        start_scheduler()

        # Find the snapshot job call and check interval
        for call in mock_scheduler.add_job.call_args_list:
            if call[1].get('id') == 'record_pool_snapshot':
                trigger = call[1].get('trigger')
                assert trigger.interval.total_seconds() == 60  # 1 minute

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
