"""
Tests for Scheduler Service.

Based on actual scheduler.py implementation analysis:
- TrackyScheduler class with APScheduler
- Jobs: daily_scan_job, escalation_checker_job, queue_processor_job, stale_cleanup_job
- JobFailureMonitor for CRIT_007 failure tracking
- FIX (D): Skips weekend runs to avoid Sunday Morning Alert Bug

NOTE: These tests use a simplified approach since the scheduler jobs have complex
internal imports that are difficult to mock. We test the core logic independently.
"""
import pytest
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import MagicMock, patch, AsyncMock


class TestSchedulerStructure:
    """Tests for scheduler structure and configuration."""
    
    @pytest.mark.unit
    def test_scheduler_job_configuration(self):
        """TrackyScheduler should have correct job configuration."""
        from app.services.scheduler import TrackyScheduler
        
        scheduler = TrackyScheduler()
        
        # Verify job config exists
        assert "daily_scan" in scheduler.jobs_config
        assert "escalation_checker" in scheduler.jobs_config
        assert "queue_processor" in scheduler.jobs_config
        assert "stale_cleanup" in scheduler.jobs_config
        assert "reminder_sender" in scheduler.jobs_config

    @pytest.mark.unit
    def test_scheduler_not_running_by_default(self):
        """TrackyScheduler should not be running by default."""
        from app.services.scheduler import TrackyScheduler
        
        scheduler = TrackyScheduler()
        
        assert scheduler.is_running == False
        assert scheduler.scheduler is None

    @pytest.mark.unit
    def test_get_jobs_status_empty_when_not_started(self):
        """get_jobs_status should return empty when scheduler not started."""
        from app.services.scheduler import TrackyScheduler
        
        scheduler = TrackyScheduler()
        
        status = scheduler.get_jobs_status()
        assert status == []

    @pytest.mark.unit
    def test_get_health_status_structure(self):
        """Health status should have correct structure."""
        from app.services.scheduler import TrackyScheduler
        
        scheduler = TrackyScheduler()
        
        health = scheduler.get_health_status()
        
        assert "status" in health
        assert "is_running" in health
        assert "jobs" in health
        assert "failures" in health
        assert "paused_jobs" in health
        assert health["is_running"] == False


class TestJobFailureMonitor:
    """Tests for job failure monitoring (CRIT_007)."""
    
    @pytest.mark.unit
    def test_record_success_resets_failure_count(self):
        """Recording success should reset failure count."""
        from app.services.scheduler import JobFailureMonitor
        import asyncio
        
        monitor = JobFailureMonitor(failure_threshold=3)
        
        # Simulate failures
        asyncio.get_event_loop().run_until_complete(
            monitor.record_failure("test_job", "error1")
        )
        asyncio.get_event_loop().run_until_complete(
            monitor.record_failure("test_job", "error2")
        )
        
        # Record success
        asyncio.get_event_loop().run_until_complete(
            monitor.record_success("test_job")
        )
        
        # Failures should be reset
        status = monitor.get_status()
        assert status.get("test_job", {}).get("failure_count", 0) == 0

    @pytest.mark.unit
    def test_failure_threshold_triggers_pause(self):
        """Exceeding failure threshold should pause job."""
        from app.services.scheduler import JobFailureMonitor
        import asyncio
        
        monitor = JobFailureMonitor(failure_threshold=2)
        
        # First failure - should not pause
        should_pause_1 = asyncio.get_event_loop().run_until_complete(
            monitor.record_failure("test_job", "error1")
        )
        assert should_pause_1 == False
        
        # Second failure - should pause
        with patch.object(monitor, "_send_critical_alert", new_callable=AsyncMock):
            should_pause_2 = asyncio.get_event_loop().run_until_complete(
                monitor.record_failure("test_job", "error2")
            )
            assert should_pause_2 == True
            assert "test_job" in monitor.paused_jobs

    @pytest.mark.unit
    def test_failure_monitor_get_status_empty(self):
        """New failure monitor should have empty status."""
        from app.services.scheduler import JobFailureMonitor
        
        monitor = JobFailureMonitor(failure_threshold=3)
        
        status = monitor.get_status()
        assert status == {}

    @pytest.mark.unit
    def test_failure_count_increments(self):
        """Failure count should increment on each failure."""
        from app.services.scheduler import JobFailureMonitor
        import asyncio
        
        monitor = JobFailureMonitor(failure_threshold=5)
        
        asyncio.get_event_loop().run_until_complete(
            monitor.record_failure("test_job", "error1")
        )
        
        status = monitor.get_status()
        assert status["test_job"]["failure_count"] == 1
        
        asyncio.get_event_loop().run_until_complete(
            monitor.record_failure("test_job", "error2")
        )
        
        status = monitor.get_status()
        assert status["test_job"]["failure_count"] == 2


class TestBusinessDayLogic:
    """Tests for business day skip logic used by scheduler."""
    
    @pytest.mark.unit
    def test_is_business_day_weekday(self):
        """Weekday should be a business day."""
        from app.services.business_days import is_weekend
        
        # 2024-01-08 is Monday
        monday = date(2024, 1, 8)
        
        assert is_weekend(monday) == False

    @pytest.mark.unit
    def test_is_business_day_weekend(self):
        """Weekend should not be a business day."""
        from app.services.business_days import is_weekend
        
        # 2024-01-06 is Saturday
        saturday = date(2024, 1, 6)
        # 2024-01-07 is Sunday
        sunday = date(2024, 1, 7)
        
        assert is_weekend(saturday) == True
        assert is_weekend(sunday) == True


class TestSchedulerDailyScan:
    """Tests for daily scan job behavior."""
    
    @pytest.mark.unit
    def test_daily_scan_job_exists(self):
        """daily_scan_job function should exist."""
        from app.services.scheduler import daily_scan_job
        
        assert callable(daily_scan_job)

    @pytest.mark.unit
    def test_escalation_checker_job_exists(self):
        """escalation_checker_job function should exist."""
        from app.services.scheduler import escalation_checker_job
        
        assert callable(escalation_checker_job)

    @pytest.mark.unit
    def test_queue_processor_job_exists(self):
        """queue_processor_job function should exist."""
        from app.services.scheduler import queue_processor_job
        
        assert callable(queue_processor_job)

    @pytest.mark.unit
    def test_stale_cleanup_job_exists(self):
        """stale_cleanup_job function should exist."""
        from app.services.scheduler import stale_cleanup_job
        
        assert callable(stale_cleanup_job)
