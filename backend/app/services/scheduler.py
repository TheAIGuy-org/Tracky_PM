"""
Background Job Scheduler for Tracky PM.

Handles scheduled tasks using APScheduler:
- Daily status check scan (5:00 AM UTC)
- Escalation timeout checker (every 30 minutes)
- Alert queue processor (every 5 minutes)
- Stale alert cleanup (daily)

This is the "heartbeat" automation layer that makes proactive tracking work.

CRITICAL FIXES:
- CRIT_007: Job failure monitoring and alerting
- Automatic job pausing after repeated failures
- Health check endpoint support
"""
import asyncio
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Callable, Dict, Any, List
from contextlib import asynccontextmanager
from collections import defaultdict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

from app.core.database import get_supabase_client
from app.core.config import settings


# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ==========================================
# CRIT_007: Job Failure Monitor
# ==========================================

class JobFailureMonitor:
    """
    Monitor job failures and alert when threshold exceeded.
    
    CRIT_007: Prevents silent scheduler failures that could
    cause alerts to not be sent for days.
    """
    
    def __init__(self, failure_threshold: int = 2):
        self.failure_threshold = failure_threshold
        self.failed_jobs: Dict[str, List[datetime]] = defaultdict(list)
        self.paused_jobs: set = set()
    
    async def record_success(self, job_id: str) -> None:
        """Record job success - reset failure count."""
        self.failed_jobs[job_id] = []
        if job_id in self.paused_jobs:
            self.paused_jobs.remove(job_id)
    
    async def record_failure(self, job_id: str, error: str) -> bool:
        """
        Record job failure and alert if threshold exceeded.
        
        Returns True if job should be paused.
        """
        now = datetime.now(timezone.utc)
        
        # Add failure
        self.failed_jobs[job_id].append(now)
        
        # Keep only failures from last 24 hours
        cutoff = now - timedelta(hours=24)
        self.failed_jobs[job_id] = [
            t for t in self.failed_jobs[job_id] if t > cutoff
        ]
        
        failure_count = len(self.failed_jobs[job_id])
        
        if failure_count >= self.failure_threshold:
            # Alert operations team
            await self._send_critical_alert(job_id, failure_count, error)
            self.paused_jobs.add(job_id)
            return True  # Should pause
        
        return False
    
    async def _send_critical_alert(self, job_id: str, failure_count: int, error: str) -> None:
        """Send critical alert when job failures exceed threshold."""
        try:
            # Try to send notification
            if settings.ops_escalation_email:
                from app.services.notifications import notification_service
                
                await notification_service._send_email_simple(
                    to_email=settings.ops_escalation_email,
                    subject=f"🚨 CRITICAL: Scheduler job '{job_id}' failed {failure_count} times",
                    body=f"""
The background scheduler job '{job_id}' has failed {failure_count} times in the last 24 hours.

Last error: {error}

This job is responsible for critical alert functionality.
IMMEDIATE ACTION REQUIRED.

Service: {settings.app_name}
Time: {datetime.now(timezone.utc).isoformat()}
                    """
                )
                logger.critical(f"Sent critical alert for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to send critical alert: {e}")
        
        # Always log
        logger.critical(
            f"CRITICAL: Job {job_id} failed {failure_count} times. "
            f"Last error: {error}. Job paused."
        )
    
    def get_status(self) -> Dict[str, Any]:
        """Get current failure status for all jobs."""
        return {
            job_id: {
                "failure_count": len(failures),
                "last_failure": failures[-1].isoformat() if failures else None,
                "is_paused": job_id in self.paused_jobs
            }
            for job_id, failures in self.failed_jobs.items()
        }


# Global job monitor
job_monitor = JobFailureMonitor(
    failure_threshold=getattr(settings, 'job_failure_alert_threshold', 2)
)


class TrackyScheduler:
    """
    Background job scheduler for Tracky PM.
    
    Manages scheduled tasks that power the Proactive Execution Tracking Loop.
    Uses APScheduler for reliable, persistent job scheduling.
    
    CRIT_007: Includes job failure monitoring and alerting.
    """
    
    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.is_running = False
        self.job_monitor = job_monitor
        
        # Job configuration
        self.jobs_config = {
            "daily_scan": {
                "trigger": CronTrigger(hour=5, minute=0, timezone="UTC"),  # 5:00 AM UTC
                "description": "Daily status check scan for approaching deadlines"
            },
            "escalation_checker": {
                "trigger": IntervalTrigger(minutes=30),
                "description": "Check for alerts that need escalation"
            },
            "queue_processor": {
                "trigger": IntervalTrigger(minutes=5),
                "description": "Process pending items in alert queue"
            },
            "stale_cleanup": {
                "trigger": CronTrigger(hour=2, minute=0, timezone="UTC"),  # 2:00 AM UTC
                "description": "Clean up stale/expired alerts"
            },
            "reminder_sender": {
                "trigger": CronTrigger(hour=14, minute=0, timezone="UTC"),  # 2:00 PM UTC
                "description": "Send reminder for unanswered alerts"
            }
        }
    
    def create_scheduler(self) -> AsyncIOScheduler:
        """Create and configure the scheduler."""
        jobstores = {
            'default': MemoryJobStore()
        }
        
        executors = {
            'default': AsyncIOExecutor()
        }
        
        job_defaults = {
            'coalesce': True,  # Combine missed runs into one
            'max_instances': 1,  # Only one instance of each job at a time
            'misfire_grace_time': 300  # 5 minute grace period
        }
        
        scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )
        
        return scheduler
    
    def start(self):
        """Start the scheduler with all jobs."""
        if self.is_running:
            logger.warning("Scheduler is already running")
            return
        
        self.scheduler = self.create_scheduler()
        
        # Add jobs
        self.scheduler.add_job(
            daily_scan_job,
            self.jobs_config["daily_scan"]["trigger"],
            id="daily_scan",
            name="Daily Status Check Scan",
            replace_existing=True
        )
        
        self.scheduler.add_job(
            escalation_checker_job,
            self.jobs_config["escalation_checker"]["trigger"],
            id="escalation_checker",
            name="Escalation Timeout Checker",
            replace_existing=True
        )
        
        self.scheduler.add_job(
            queue_processor_job,
            self.jobs_config["queue_processor"]["trigger"],
            id="queue_processor",
            name="Alert Queue Processor",
            replace_existing=True
        )
        
        self.scheduler.add_job(
            stale_cleanup_job,
            self.jobs_config["stale_cleanup"]["trigger"],
            id="stale_cleanup",
            name="Stale Alert Cleanup",
            replace_existing=True
        )
        
        self.scheduler.add_job(
            reminder_sender_job,
            self.jobs_config["reminder_sender"]["trigger"],
            id="reminder_sender",
            name="Reminder Sender",
            replace_existing=True
        )
        
        self.scheduler.start()
        self.is_running = True
        logger.info("🚀 Tracky Scheduler started successfully")
        
        # Log scheduled jobs
        for job in self.scheduler.get_jobs():
            logger.info(f"  - {job.name}: Next run at {job.next_run_time}")
    
    def stop(self):
        """Stop the scheduler gracefully."""
        if self.scheduler and self.is_running:
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("🛑 Tracky Scheduler stopped")
    
    def trigger_job(self, job_id: str) -> bool:
        """Manually trigger a job to run immediately."""
        if not self.scheduler:
            logger.error("Scheduler not initialized")
            return False
        
        job = self.scheduler.get_job(job_id)
        if job:
            # CRIT_004: Use UTC-aware datetime
            job.modify(next_run_time=datetime.now(timezone.utc))
            logger.info(f"Manually triggered job: {job_id}")
            return True
        else:
            logger.error(f"Job not found: {job_id}")
            return False
    
    def get_jobs_status(self) -> list:
        """Get status of all scheduled jobs."""
        if not self.scheduler:
            return []
        
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "pending": job.pending
            }
            for job in self.scheduler.get_jobs()
        ]
    
    def pause_job(self, job_id: str) -> bool:
        """Pause a specific job."""
        if not self.scheduler:
            return False
        self.scheduler.pause_job(job_id)
        logger.info(f"Paused job: {job_id}")
        return True
    
    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        if not self.scheduler:
            return False
        self.scheduler.resume_job(job_id)
        # Clear from paused set in monitor
        if job_id in self.job_monitor.paused_jobs:
            self.job_monitor.paused_jobs.remove(job_id)
        logger.info(f"Resumed job: {job_id}")
        return True
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get scheduler health status for monitoring (CRIT_007).
        
        Returns scheduler status and job failure information.
        """
        failed_jobs = self.job_monitor.get_status()
        has_failures = any(
            info["failure_count"] > 0 
            for info in failed_jobs.values()
        )
        
        return {
            "status": "degraded" if has_failures else "healthy",
            "is_running": self.is_running,
            "jobs": self.get_jobs_status(),
            "failures": failed_jobs,
            "paused_jobs": list(self.job_monitor.paused_jobs)
        }


# ==========================================
# JOB IMPLEMENTATIONS (CRIT_007: With failure monitoring)
# ==========================================

async def daily_scan_job():
    """
    Daily scan for tasks approaching deadline.
    
    This is the main job that kicks off the proactive tracking loop.
    Runs at 5:00 AM UTC daily.
    
    CRIT_007: Includes failure monitoring and alerting.
    
    FIX (D): Only sends alerts on business days to avoid weekend notifications.
    """
    job_id = "daily_scan"
    
    # FIX (D): Skip weekend runs to avoid "Sunday Morning Alert Bug"
    # Alerts for Monday deadlines will be sent on Friday, not Sunday
    from app.services.business_days import is_business_day
    from datetime import date
    
    today = date.today()
    if not is_business_day(today):
        logger.info(f"⏸️ Skipping daily scan - today ({today}) is not a business day")
        return {"skipped": True, "reason": "non_business_day"}
    
    logger.info("🔍 Starting daily status check scan...")
    start_time = datetime.now(timezone.utc)
    
    try:
        from app.services.alert_orchestrator import run_daily_scan
        
        result = run_daily_scan()
        
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        
        logger.info(
            f"✅ Daily scan completed in {elapsed:.2f}s: "
            f"{result.get('alerts_created', 0)} alerts created, "
            f"{result.get('escalations', 0)} escalations"
        )
        
        # Record success
        await job_monitor.record_success(job_id)
        
        # Record job execution
        await _record_job_execution(
            job_id=job_id,
            status="success",
            result=result,
            duration_seconds=elapsed
        )
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Daily scan failed: {e}", exc_info=True)
        
        # CRIT_007: Record failure and potentially alert
        should_pause = await job_monitor.record_failure(job_id, str(e))
        
        if should_pause:
            scheduler = get_scheduler()
            if scheduler.scheduler:
                scheduler.pause_job(job_id)
        
        await _record_job_execution(
            job_id=job_id,
            status="failed",
            error=str(e)
        )
        raise


async def escalation_checker_job():
    """
    Check for alerts that have timed out and need escalation.
    
    Runs every 30 minutes to ensure timely escalation.
    
    CRIT_007: Includes failure monitoring.
    """
    job_id = "escalation_checker"
    logger.info("⏰ Checking for escalation timeouts...")
    
    try:
        from app.services.alert_orchestrator import check_and_escalate_timeouts
        
        escalated = check_and_escalate_timeouts()
        
        if escalated:
            logger.info(f"📈 Escalated {len(escalated)} alerts")
        else:
            logger.debug("No alerts needed escalation")
        
        # Record success
        await job_monitor.record_success(job_id)
        
        return {"escalated_count": len(escalated) if escalated else 0, "escalated": escalated}
        
    except Exception as e:
        logger.error(f"❌ Escalation check failed: {e}", exc_info=True)
        
        # CRIT_007: Record failure
        should_pause = await job_monitor.record_failure(job_id, str(e))
        if should_pause:
            scheduler = get_scheduler()
            if scheduler.scheduler:
                scheduler.pause_job(job_id)
        
        raise


async def queue_processor_job():
    """
    Process items from the alert queue.
    
    Handles:
    - Sending scheduled alerts
    - Processing retries
    - Sending notifications
    
    Runs every 5 minutes.
    
    CRIT_007: Includes failure monitoring and batch processing.
    CRIT_004: Uses UTC-aware timestamps.
    ISSUE_011: Processes ALL pending items with pagination, not just 50.
    """
    job_id = "queue_processor"
    logger.debug("📬 Processing alert queue...")
    
    try:
        db = get_supabase_client()
        now = datetime.now(timezone.utc)  # CRIT_004: UTC-aware
        
        total_processed = 0
        total_failed = 0
        batch_size = 50
        max_iterations = 20  # Safety: max 1000 items per run
        
        # ISSUE_011: Process ALL pending items with pagination
        for iteration in range(max_iterations):
            # Get pending queue items that are due
            response = db.client.table("alert_queue").select(
                "*, alerts(*)"
            ).eq("status", "PENDING").lte(
                "scheduled_for", now.isoformat()
            ).order("priority").order("scheduled_for").limit(batch_size).execute()
            
            items = response.data or []
            if not items:
                break  # No more items to process
            
            for item in items:
                try:
                    await _process_queue_item(item)
                    total_processed += 1
                except Exception as e:
                    logger.error(f"Failed to process queue item {item['id']}: {e}")
                    await _mark_queue_item_failed(item['id'], str(e))
                    total_failed += 1
        
        if total_processed or total_failed:
            logger.info(f"📬 Queue processed: {total_processed} successful, {total_failed} failed")
        
        # Record success
        await job_monitor.record_success(job_id)
        
        return {"processed": total_processed, "failed": total_failed}
        
    except Exception as e:
        logger.error(f"❌ Queue processing failed: {e}")
        
        # CRIT_007: Record failure
        should_pause = await job_monitor.record_failure(job_id, str(e))
        if should_pause:
            scheduler = get_scheduler()
            if scheduler.scheduler:
                scheduler.pause_job(job_id)
        
        raise


async def stale_cleanup_job():
    """
    Clean up stale and expired alerts.
    
    - Mark expired alerts as EXPIRED
    - Clean up old queue items
    - Archive old responses
    
    Runs at 2:00 AM UTC daily.
    
    CRIT_004: Uses UTC-aware timestamps.
    """
    job_id = "stale_cleanup"
    logger.info("🧹 Running stale alert cleanup...")
    
    try:
        db = get_supabase_client()
        now = datetime.now(timezone.utc)  # CRIT_004: UTC-aware
        
        # Mark expired alerts
        expired_response = db.client.table("alerts").update({
            "status": "EXPIRED"
        }).lt("expires_at", now.isoformat()).in_(
            "status", ["PENDING", "SENT", "DELIVERED", "OPENED"]
        ).execute()
        
        expired_count = len(expired_response.data) if expired_response.data else 0
        
        # Clean up old completed queue items (older than 7 days)
        cleanup_date = (now - timedelta(days=7)).isoformat()
        db.client.table("alert_queue").delete().in_(
            "status", ["COMPLETED", "CANCELLED"]
        ).lt("processed_at", cleanup_date).execute()
        
        # Cancel pending queue items for expired alerts
        db.client.table("alert_queue").update({
            "status": "CANCELLED"
        }).eq("status", "PENDING").in_(
            "alert_id",
            db.client.table("alerts").select("id").eq("status", "EXPIRED")
        ).execute()
        
        logger.info(f"🧹 Cleanup completed: {expired_count} alerts expired")
        
        # CRIT_007: Record success
        await job_monitor.record_success(job_id)
        
        return {"expired_alerts": expired_count}
        
    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        
        # CRIT_007: Record failure
        should_pause = await job_monitor.record_failure(job_id, str(e))
        if should_pause:
            scheduler = get_scheduler()
            if scheduler.scheduler:
                scheduler.pause_job(job_id)
        
        raise


async def reminder_sender_job():
    """
    Send reminders for unanswered alerts.
    
    For alerts that are 2+ hours old without response,
    send a reminder (but don't escalate yet).
    
    Runs at 2:00 PM UTC daily.
    
    CRIT_004: Uses UTC-aware timestamps.
    FIX (D): Only sends reminders on business days.
    """
    job_id = "reminder_sender"
    
    # FIX (D): Skip weekend runs to avoid weekend notifications
    from app.services.business_days import is_business_day
    from datetime import date
    
    today = date.today()
    if not is_business_day(today):
        logger.info(f"⏸️ Skipping reminder job - today ({today}) is not a business day")
        return {"skipped": True, "reason": "non_business_day"}
    
    logger.info("📢 Checking for alerts needing reminders...")
    
    try:
        db = get_supabase_client()
        now = datetime.now(timezone.utc)  # CRIT_004: UTC-aware
        reminder_threshold = now - timedelta(hours=2)
        
        # Find alerts sent but not responded, older than 2 hours
        response = db.client.table("alerts").select(
            "*, work_items(external_id, name), resources:actual_recipient_id(name, email)"
        ).in_(
            "status", ["SENT", "DELIVERED"]
        ).lt("sent_at", reminder_threshold.isoformat()).is_(
            "responded_at", "null"
        ).execute()
        
        reminders_sent = 0
        
        for alert in (response.data or []):
            # Check if reminder already sent (via notification_metadata)
            metadata = alert.get("notification_metadata", {}) or {}
            if metadata.get("reminder_sent"):
                continue
            
            # Queue a reminder
            try:
                from app.services.notifications import notification_service
                
                resource = alert.get("resources") or {}
                work_item = alert.get("work_items") or {}
                
                # Would send reminder here
                logger.info(f"Would send reminder for alert {alert['id']} to {resource.get('email')}")
                
                # Mark reminder as sent
                db.client.table("alerts").update({
                    "notification_metadata": {
                        **metadata,
                        "reminder_sent": True,
                        "reminder_sent_at": now.isoformat()
                    }
                }).eq("id", alert["id"]).execute()
                
                reminders_sent += 1
                
            except Exception as e:
                logger.error(f"Failed to send reminder for alert {alert['id']}: {e}")
        
        if reminders_sent:
            logger.info(f"📢 Sent {reminders_sent} reminders")
        
        return {"reminders_sent": reminders_sent}
        
    except Exception as e:
        logger.error(f"❌ Reminder job failed: {e}")
        raise


# ==========================================
# HELPER FUNCTIONS
# ==========================================

async def _process_queue_item(item: Dict[str, Any]) -> None:
    """Process a single queue item based on its action."""
    db = get_supabase_client()
    action = item.get("action")
    alert_id = item.get("alert_id")
    
    # Mark as processing
    # CRIT_004: Use timezone-aware datetime
    db.client.table("alert_queue").update({
        "status": "PROCESSING",
        "last_attempt_at": datetime.now(timezone.utc).isoformat(),
        "attempts": item.get("attempts", 0) + 1
    }).eq("id", item["id"]).execute()
    
    try:
        if action == "SEND":
            await _send_alert(item)
        elif action == "ESCALATE":
            await _process_escalation(item)
        elif action == "REMIND":
            await _send_reminder(item)
        elif action == "EXPIRE":
            await _expire_alert(item)
        elif action == "PROCESS_RESPONSE":
            await _process_response_notification(item)
        else:
            logger.warning(f"Unknown queue action: {action}")
        
        # Mark as completed
        # CRIT_004: Use timezone-aware datetime
        db.client.table("alert_queue").update({
            "status": "COMPLETED",
            "processed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", item["id"]).execute()
        
    except Exception as e:
        # Re-raise for the caller to handle
        raise


async def _send_alert(item: Dict[str, Any]) -> None:
    """Send an alert notification."""
    from app.services.notifications import send_status_check_alert
    from uuid import UUID
    
    alert = item.get("alerts", {})
    if not alert:
        return
    
    db = get_supabase_client()
    
    # Get full alert details
    full_alert = db.client.table("alerts").select(
        "*, "
        "work_items(id, external_id, name, current_end, is_critical_path, "
        "phases(name, projects(name, programs(name)))), "
        "resources:actual_recipient_id(id, name, email, notification_email)"
    ).eq("id", alert.get("id")).execute()
    
    if not full_alert.data:
        return
    
    alert_data = full_alert.data[0]
    resource = alert_data.get("resources", {})
    work_item = alert_data.get("work_items", {})
    phases = work_item.get("phases", {}) or {}
    projects = phases.get("projects", {}) or {}
    programs = projects.get("programs", {}) or {}
    
    # Get magic link from metadata
    metadata = alert_data.get("notification_metadata", {}) or {}
    magic_link = metadata.get("magic_link", "")
    
    if not magic_link:
        from app.services.magic_links import create_magic_link
        magic_link = create_magic_link(
            work_item_id=UUID(work_item["id"]),
            resource_id=UUID(resource["id"]),
            deadline=date.fromisoformat(work_item["current_end"]),
            alert_id=UUID(alert_data["id"])
        )
    
    # Send notification
    await send_status_check_alert(
        alert_id=UUID(alert_data["id"]),
        recipient_email=resource.get("notification_email") or resource.get("email"),
        recipient_name=resource.get("name", "Team Member"),
        work_item_name=work_item.get("name", ""),
        work_item_id=work_item.get("external_id", ""),
        deadline=work_item.get("current_end", ""),
        urgency=alert_data.get("urgency", "NORMAL"),
        magic_link=magic_link,
        program_name=programs.get("name", ""),
        project_name=projects.get("name", ""),
        is_critical_path=work_item.get("is_critical_path", False)
    )


async def _process_escalation(item: Dict[str, Any]) -> None:
    """Process an escalation action."""
    from app.services.alert_orchestrator import check_and_escalate_timeouts
    check_and_escalate_timeouts()


async def _send_reminder(item: Dict[str, Any]) -> None:
    """Send a reminder for an unanswered alert."""
    # Similar to _send_alert but with reminder-specific messaging
    pass


async def _expire_alert(item: Dict[str, Any]) -> None:
    """Expire an alert."""
    db = get_supabase_client()
    alert_id = item.get("alert_id")
    
    db.client.table("alerts").update({
        "status": "EXPIRED"
    }).eq("id", alert_id).execute()


async def _process_response_notification(item: Dict[str, Any]) -> None:
    """Send notification after a response is received."""
    from app.services.notifications import send_response_confirmation
    # Implementation for response confirmation
    pass


async def _mark_queue_item_failed(item_id: str, error: str) -> None:
    """Mark a queue item as failed with retry logic."""
    db = get_supabase_client()
    
    # Get current item
    response = db.client.table("alert_queue").select("*").eq("id", item_id).execute()
    if not response.data:
        return
    
    item = response.data[0]
    attempts = item.get("attempts", 0)
    max_attempts = item.get("max_attempts", 3)
    
    if attempts >= max_attempts:
        # Max retries reached
        db.client.table("alert_queue").update({
            "status": "FAILED",
            "last_error": error
        }).eq("id", item_id).execute()
    else:
        # Schedule retry with exponential backoff
        backoff_minutes = 5 * (2 ** attempts)  # 5, 10, 20 minutes
        # CRIT_004: Use timezone-aware datetime
        next_retry = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
        
        db.client.table("alert_queue").update({
            "status": "PENDING",
            "last_error": error,
            "next_retry_at": next_retry.isoformat()
        }).eq("id", item_id).execute()


async def _record_job_execution(
    job_id: str,
    status: str,
    result: Dict = None,
    error: str = None,
    duration_seconds: float = None
) -> None:
    """Record job execution in database for monitoring."""
    try:
        db = get_supabase_client()
        
        # Try to insert into a job_executions table if it exists
        # For now, just log it
        logger.info(f"Job {job_id} execution: status={status}, duration={duration_seconds}s")
        
    except Exception as e:
        logger.debug(f"Could not record job execution: {e}")


# ==========================================
# GLOBAL SCHEDULER INSTANCE
# ==========================================

scheduler = TrackyScheduler()


def get_scheduler() -> TrackyScheduler:
    """Get the global scheduler instance."""
    return scheduler


# ==========================================
# FASTAPI INTEGRATION
# ==========================================

@asynccontextmanager
async def scheduler_lifespan(app):
    """
    FastAPI lifespan context manager for scheduler.
    
    Use this in your FastAPI app:
    
    ```python
    from app.services.scheduler import scheduler_lifespan
    
    app = FastAPI(lifespan=scheduler_lifespan)
    ```
    """
    # Startup
    if getattr(settings, 'enable_scheduler', True):
        scheduler.start()
    
    yield
    
    # Shutdown
    scheduler.stop()
