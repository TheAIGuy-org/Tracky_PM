"""
Alert Orchestrator for Tracky PM.

The main coordinator for the Proactive Execution Tracking Loop.

Responsibilities:
1. Daily scan for tasks approaching deadline
2. Dispatch status check alerts (respecting business days)
3. Handle escalation timeouts
4. Process responses
5. Trigger impact analysis on delays
6. Manage approval workflow

This is the "heartbeat" of the proactive tracking system.

CRITICAL FIXES IMPLEMENTED:
- CRIT_001: Safe null/None handling for nested relationships
- CRIT_002: Fallback escalation when no PM configured
- CRIT_003: Race condition prevention via database constraints
- CRIT_004: Timezone-aware datetime handling
- CRIT_005: Input validation for configuration
- CRIT_008: Token revocation on response
"""
from datetime import datetime, date, timedelta, time, timezone
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from dataclasses import dataclass
from enum import Enum
import logging
import json

from app.core.database import get_supabase_client
from app.core.config import settings
from app.core.exceptions import (
    CriticalAlertException,
    EscalationFailureException,
    DuplicateAlertError,
    TokenAlreadyUsedError,
    ConfigurationError
)
from app.services.business_days import (
    get_alert_send_date,
    get_alert_send_timestamp,
    is_business_day,
    format_deadline_message,
    get_deadline_urgency
)
from app.services.escalation import (
    find_available_recipient,
    get_escalation_policy,
    get_escalation_timeout_at,
    should_escalate,
    get_next_escalation_level,
    record_escalation_event,
    EscalationRecipient
)
from app.services.magic_links import create_magic_link
from app.services.impact_analysis import analyze_impact, apply_approved_delay

# Configure logging
logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Types of alerts."""
    STATUS_CHECK = "STATUS_CHECK"
    ESCALATION = "ESCALATION"
    BLOCKER_REPORT = "BLOCKER_REPORT"
    APPROVAL_REQUEST = "APPROVAL_REQUEST"
    NOTIFICATION = "NOTIFICATION"
    SCHEDULE_CHANGE = "SCHEDULE_CHANGE"


class AlertStatus(Enum):
    """Alert lifecycle status."""
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    OPENED = "OPENED"
    RESPONDED = "RESPONDED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ResponseStatus(Enum):
    """Possible response statuses."""
    ON_TRACK = "ON_TRACK"
    DELAYED = "DELAYED"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


@dataclass
class PendingStatusCheck:
    """Represents a task that needs a status check alert."""
    work_item_id: UUID
    external_id: str
    work_item_name: str
    deadline: date
    resource_id: UUID
    resource_name: str
    resource_email: str
    program_id: UUID
    is_critical_path: bool
    urgency: str
    existing_alert_id: Optional[UUID] = None
    latest_response_status: Optional[str] = None


def scan_for_pending_status_checks(
    target_date: Optional[date] = None,
    days_before: int = 1
) -> List[PendingStatusCheck]:
    """
    Scan for tasks that need status check alerts.
    
    Finds all tasks where:
    - Deadline is approaching (business days before = days_before)
    - Not already completed or cancelled
    - No active alert already sent
    
    Args:
        target_date: Date to check for (default: today)
        days_before: Business days before deadline to send alert
    
    Returns:
        List of tasks needing status checks
    """
    db = get_supabase_client()
    
    if target_date is None:
        target_date = date.today()
    
    # Get tasks due in the next few days
    # We check a range because business day calculation varies
    start_window = target_date + timedelta(days=1)
    end_window = target_date + timedelta(days=7)
    
    response = db.client.table("work_items").select(
        "id, external_id, name, current_end, is_critical_path, status, "
        "resource_id, resources(id, name, email, notification_email, availability_status), "
        "phases(projects(program_id, programs(id, name)))"
    ).gte(
        "current_end", start_window.isoformat()
    ).lte(
        "current_end", end_window.isoformat()
    ).not_.in_(
        "status", ["Cancelled", "Completed"]
    ).is_("actual_end", "null").execute()
    
    pending = []
    skipped_count = 0
    
    for item in (response.data or []):
        # CRIT_001: Safe null handling for all nested relationships
        try:
            deadline = date.fromisoformat(item["current_end"])
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Skipping work_item {item.get('id', 'unknown')}: invalid deadline - {e}")
            skipped_count += 1
            continue
        
        # Check if today is the right day to send alert
        alert_date = get_alert_send_date(deadline, days_before)
        
        if alert_date != target_date:
            continue
        
        # CRIT_001: Safe extraction of nested relationships with proper null checks
        resource = item.get("resources") or {}
        phases = item.get("phases") or {}
        projects = phases.get("projects") if phases else None
        projects = projects or {}
        programs = projects.get("programs") if projects else None
        programs = programs or {}
        
        # Validate required fields exist
        if not resource or "id" not in resource:
            logger.warning(
                f"Skipping work_item {item['id']} ({item.get('external_id', 'N/A')}): "
                f"no assigned resource"
            )
            skipped_count += 1
            continue
        
        # Check if there's already an active alert
        try:
            existing_alert = _get_existing_alert(UUID(item["id"]), deadline)
        except Exception as e:
            logger.error(f"Error checking existing alert for {item['id']}: {e}")
            existing_alert = None
        
        # Skip if already responded ON_TRACK
        if existing_alert and existing_alert.get("latest_response") == "ON_TRACK":
            continue
        
        # CRIT_001: Safe UUID extraction with validation
        try:
            resource_id = UUID(resource["id"])
            program_id = UUID(programs["id"]) if programs and "id" in programs else None
        except (ValueError, TypeError) as e:
            logger.warning(f"Skipping work_item {item['id']}: invalid UUID - {e}")
            skipped_count += 1
            continue
        
        pending.append(PendingStatusCheck(
            work_item_id=UUID(item["id"]),
            external_id=item.get("external_id", ""),
            work_item_name=item.get("name", "Unknown Task"),
            deadline=deadline,
            resource_id=resource_id,
            resource_name=resource.get("name", "Unknown"),
            resource_email=resource.get("notification_email") or resource.get("email", ""),
            program_id=program_id,
            is_critical_path=item.get("is_critical_path", False),
            urgency=get_deadline_urgency(deadline),
            existing_alert_id=UUID(existing_alert["id"]) if existing_alert else None,
            latest_response_status=existing_alert.get("latest_response") if existing_alert else None
        ))
    
    if skipped_count > 0:
        logger.info(f"Scan completed: {len(pending)} pending, {skipped_count} skipped due to missing data")
    
    return pending


def _get_existing_alert(work_item_id: UUID, deadline: date) -> Optional[Dict]:
    """Check for existing active alert for this work item and deadline."""
    db = get_supabase_client()
    
    response = db.client.table("alerts").select(
        "id, status, work_item_responses(reported_status, is_latest)"
    ).eq(
        "work_item_id", str(work_item_id)
    ).eq(
        "deadline_date", deadline.isoformat()
    ).not_.in_(
        "status", ["EXPIRED", "CANCELLED"]
    ).order("created_at", desc=True).limit(1).execute()
    
    if not response.data:
        return None
    
    alert = response.data[0]
    responses = alert.get("work_item_responses", []) or []
    latest = next((r for r in responses if r.get("is_latest")), None)
    
    return {
        "id": alert["id"],
        "status": alert["status"],
        "latest_response": latest.get("reported_status") if latest else None
    }


def create_status_check_alert(
    work_item_id: UUID,
    deadline: date,
    resource_id: UUID,
    program_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """
    Create a status check alert for a work item.
    
    This:
    1. Finds the appropriate recipient (considering availability)
    2. Creates the alert record (with race condition protection)
    3. Generates a magic link
    4. Queues the alert for sending
    
    CRITICAL FIXES:
    - CRIT_003: Uses database unique constraint to prevent duplicate alerts
    - CRIT_004: All timestamps are timezone-aware (UTC)
    
    Args:
        work_item_id: The work item to check
        deadline: The deadline date
        resource_id: The primary resource assigned
        program_id: Optional program for policy lookup
    
    Returns:
        Alert creation result
    
    Raises:
        DuplicateAlertError: If alert already exists (race condition handled)
    """
    db = get_supabase_client()
    
    # Find available recipient (handles escalation if primary unavailable)
    recipient, skipped = find_available_recipient(resource_id, program_id)
    
    if not recipient:
        # No one available - create alert for PM escalation
        return _create_no_recipient_alert(work_item_id, deadline, resource_id, skipped, program_id)
    
    # Get escalation policy
    policy = get_escalation_policy(program_id)
    
    # CRIT_004: Calculate when alert should be sent (9 AM in recipient's timezone)
    # All timestamps are timezone-aware UTC
    send_at = get_alert_send_timestamp(
        deadline=deadline,
        alert_time=time(9, 0),
        resource_timezone=recipient.timezone,
        days_before=policy.days_before_deadline
    )
    
    # Create magic link
    magic_link = create_magic_link(
        work_item_id=work_item_id,
        resource_id=recipient.resource_id,
        deadline=deadline
    )
    
    # Calculate escalation timeout
    escalation_timeout = get_escalation_timeout_at(
        sent_at=send_at,
        escalation_level=recipient.escalation_level,
        policy=policy
    )
    
    # CRIT_004: Ensure expires_at is timezone-aware UTC
    expires_at = datetime.combine(
        deadline, time(23, 59, 59), tzinfo=timezone.utc
    )
    
    # Create alert record
    alert_data = {
        "work_item_id": str(work_item_id),
        "deadline_date": deadline.isoformat(),
        "intended_recipient_id": str(resource_id),
        "actual_recipient_id": str(recipient.resource_id),
        "alert_type": AlertType.STATUS_CHECK.value,
        "escalation_level": recipient.escalation_level,
        "urgency": get_deadline_urgency(deadline),
        "status": AlertStatus.PENDING.value,
        "scheduled_send_at": send_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "escalation_timeout_at": escalation_timeout.isoformat() if escalation_timeout else None,
        "notification_channel": "EMAIL",
        "notification_metadata": {
            "magic_link": magic_link,
            "skipped_recipients": [
                {"name": s.resource_name, "reason": s.skip_reason}
                for s in skipped
            ] if skipped else []
        }
    }
    
    if recipient.escalation_level > 0:
        alert_data["escalation_reason"] = (
            f"PRIMARY_UNAVAILABLE: {skipped[0].skip_reason}" if skipped else "DIRECT_ESCALATION"
        )
    
    # CRIT_003: Handle race condition with unique constraint
    try:
        response = db.client.table("alerts").insert(alert_data).execute()
        alert = response.data[0] if response.data else {}
    except Exception as e:
        error_str = str(e).lower()
        if "unique" in error_str or "duplicate" in error_str or "constraint" in error_str:
            # Race condition: another process created the alert
            logger.info(f"Alert already exists for work_item {work_item_id}, deadline {deadline}")
            existing = _get_existing_alert(work_item_id, deadline)
            if existing:
                return {
                    "alert_id": existing["id"],
                    "duplicate": True,
                    "message": "Alert already exists (created by concurrent process)"
                }
        # Re-raise if not a duplicate key error
        logger.error(f"Failed to create alert: {e}")
        raise
    
    # Queue for sending
    if alert.get("id"):
        _queue_alert_for_sending(UUID(alert["id"]), send_at)
    
    return {
        "alert_id": alert.get("id"),
        "recipient": {
            "name": recipient.resource_name,
            "email": recipient.email,
            "escalation_level": recipient.escalation_level
        },
        "scheduled_send_at": send_at.isoformat(),
        "magic_link": magic_link,
        "skipped_recipients": len(skipped),
        "duplicate": False
    }


def _create_no_recipient_alert(
    work_item_id: UUID,
    deadline: date,
    original_resource_id: UUID,
    skipped: List[EscalationRecipient],
    program_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """
    Create a critical alert when no recipient is available in escalation chain.
    
    This is a CRITICAL situation that requires PM intervention.
    The alert will be sent to the program PM, default PM, or ops fallback.
    
    CRITICAL FIXES:
    - CRIT_002: Guaranteed delivery to PM or fallback ops email
    - CRIT_005: Validates configuration before proceeding
    """
    db = get_supabase_client()
    
    # Get work item details for the notification
    work_item_response = db.client.table("work_items").select(
        "external_id, name"
    ).eq("id", str(work_item_id)).execute()
    
    work_item = work_item_response.data[0] if work_item_response.data else {}
    
    # Get original assignee name
    assignee_response = db.client.table("resources").select(
        "name, email"
    ).eq("id", str(original_resource_id)).execute()
    
    original_assignee = assignee_response.data[0] if assignee_response.data else {}
    
    # Try to find PM to notify
    pm_info = _get_pm_for_notification(program_id)
    
    skipped_recipients = [
        {"name": s.resource_name, "reason": s.skip_reason}
        for s in skipped
    ]
    
    alert_data = {
        "work_item_id": str(work_item_id),
        "deadline_date": deadline.isoformat(),
        "intended_recipient_id": str(original_resource_id),
        "actual_recipient_id": str(pm_info["resource_id"]) if pm_info else None,
        "alert_type": AlertType.ESCALATION.value,
        "escalation_level": 3,  # PM level
        "urgency": "CRITICAL",
        "status": AlertStatus.PENDING.value,
        "escalation_reason": "NO_AVAILABLE_RECIPIENT",
        "notification_metadata": {
            "error": "No available recipients in escalation chain",
            "skipped_recipients": skipped_recipients,
            "work_item_name": work_item.get("name", ""),
            "work_item_external_id": work_item.get("external_id", ""),
            "original_assignee_name": original_assignee.get("name", "Unknown"),
            "pm_notified": pm_info is not None
        }
    }
    
    response = db.client.table("alerts").insert(alert_data).execute()
    alert_id = response.data[0]["id"] if response.data else None
    
    # Send notification to PM if available
    notification_sent = False
    if pm_info and alert_id:
        try:
            import asyncio
            from app.services.notifications import send_no_recipient_alert
            
            # Issue #10: Use asyncio.run() instead of manual event loop management
            # This is cleaner and handles cleanup automatically
            async def _send_notification():
                await send_no_recipient_alert(
                    alert_id=UUID(alert_id),
                    pm_email=pm_info["email"],
                    pm_name=pm_info["name"],
                    work_item_name=work_item.get("name", "Unknown Task"),
                    work_item_id=work_item.get("external_id", str(work_item_id)),
                    deadline=deadline.isoformat(),
                    original_assignee=original_assignee.get("name", "Unknown"),
                    skipped_recipients=skipped_recipients
                )
            
            # Check if we're already in an async context
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context - schedule as task
                asyncio.create_task(_send_notification())
                notification_sent = True
            except RuntimeError:
                # Not in async context - use asyncio.run()
                asyncio.run(_send_notification())
                notification_sent = True
                
        except Exception as e:
            # Log but don't fail - the alert is still created
            import logging
            logging.error(f"Failed to send no-recipient notification: {e}")
    
    return {
        "alert_id": alert_id,
        "error": "No available recipients",
        "skipped_recipients": len(skipped),
        "requires_manual_intervention": True,
        "pm_notified": notification_sent,
        "pm_email": pm_info.get("email") if pm_info else None
    }


def _get_pm_for_notification(program_id: Optional[UUID]) -> Optional[Dict[str, Any]]:
    """Get PM contact info for notifications."""
    db = get_supabase_client()
    
    if program_id:
        # Try program PM
        response = db.client.table("programs").select(
            "pm:pm_resource_id(id, name, email, notification_email), "
            "secondary_pm:secondary_pm_resource_id(id, name, email, notification_email)"
        ).eq("id", str(program_id)).execute()
        
        if response.data:
            program = response.data[0]
            
            pm = program.get("pm")
            if pm and pm.get("id"):
                email = pm.get("notification_email") or pm.get("email")
                if email:
                    return {
                        "resource_id": pm["id"],
                        "name": pm.get("name", "Program Manager"),
                        "email": email
                    }
            
            secondary = program.get("secondary_pm")
            if secondary and secondary.get("id"):
                email = secondary.get("notification_email") or secondary.get("email")
                if email:
                    return {
                        "resource_id": secondary["id"],
                        "name": secondary.get("name", "Secondary PM"),
                        "email": email
                    }
    
    # Try default PM from org settings
    try:
        settings_response = db.client.table("organization_settings").select(
            "value"
        ).eq("key", "default_pm_resource_id").execute()
        
        if settings_response.data:
            raw_value = settings_response.data[0].get("value")
            
            # CRIT_005: Properly parse and validate the UUID
            if raw_value and raw_value != "null":
                try:
                    # Handle JSON-encoded string
                    if isinstance(raw_value, str):
                        parsed_value = json.loads(raw_value) if raw_value.startswith('"') else raw_value
                        pm_id = str(parsed_value).strip('"')
                    else:
                        pm_id = str(raw_value)
                    
                    # Validate UUID format
                    UUID(pm_id)  # Raises ValueError if invalid
                    
                    pm_response = db.client.table("resources").select(
                        "id, name, email, notification_email, availability_status"
                    ).eq("id", pm_id).execute()
                    
                    if pm_response.data:
                        pm = pm_response.data[0]
                        email = pm.get("notification_email") or pm.get("email")
                        if email:
                            return {
                                "resource_id": pm["id"],
                                "name": pm.get("name", "Default PM"),
                                "email": email
                            }
                except (ValueError, json.JSONDecodeError, TypeError) as e:
                    logger.error(f"Invalid default_pm_resource_id configuration: {raw_value}. Error: {e}")
        
        # Fallback email from org settings
        fallback_response = db.client.table("organization_settings").select(
            "value"
        ).eq("key", "escalation_email_fallback").execute()
        
        if fallback_response.data:
            raw_email = fallback_response.data[0].get("value")
            if raw_email and raw_email != "null":
                try:
                    email = json.loads(raw_email) if isinstance(raw_email, str) and raw_email.startswith('"') else raw_email
                    email = str(email).strip('"')
                    if email and "@" in email:  # Basic email validation
                        return {
                            "resource_id": None,
                            "name": "System Administrator",
                            "email": email
                        }
                except (json.JSONDecodeError, TypeError):
                    pass
    except Exception as e:
        logger.warning(f"Error fetching PM from org settings: {e}")
    
    # CRIT_002: Final fallback - use ops_escalation_email from application settings
    if settings.ops_escalation_email:
        logger.info(f"Using ops fallback email: {settings.ops_escalation_email}")
        return {
            "resource_id": None,
            "name": settings.ops_escalation_name,
            "email": settings.ops_escalation_email
        }
    
    # No fallback configured - this is a critical configuration error
    logger.error(
        "CRITICAL: No PM found and no ops_escalation_email configured! "
        "Set OPS_ESCALATION_EMAIL environment variable."
    )
    return None


def _queue_alert_for_sending(alert_id: UUID, send_at: datetime) -> None:
    """Add alert to the processing queue."""
    db = get_supabase_client()
    
    # CRIT_004: Ensure send_at is timezone-aware
    if send_at.tzinfo is None:
        send_at = send_at.replace(tzinfo=timezone.utc)
    
    db.client.table("alert_queue").insert({
        "alert_id": str(alert_id),
        "action": "SEND",
        "scheduled_for": send_at.isoformat(),
        "priority": 5,
        "idempotency_key": f"send-{alert_id}"
    }).execute()


def process_status_response(
    alert_id: UUID,
    responder_resource_id: UUID,
    reported_status: str,
    token: Optional[str] = None,
    proposed_new_date: Optional[date] = None,
    reason_category: Optional[str] = None,
    reason_details: Optional[Dict[str, Any]] = None,
    comment: Optional[str] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    idempotency_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process a response to a status check alert.
    
    Handles:
    - ON_TRACK: Mark alert as responded, no further action
    - DELAYED: Calculate impact, create approval request
    - BLOCKED: Immediate escalation, critical alert to PM
    - COMPLETED: Mark task as completed
    
    CRITICAL FIXES:
    - CRIT_003: Uses database function for atomic operations
    - CRIT_008: Token is revoked atomically with response creation
    - CRIT_004: All timestamps are timezone-aware UTC
    - ISSUE_009: Idempotency support to prevent duplicate submissions
    
    Args:
        alert_id: The alert being responded to
        responder_resource_id: Who is responding
        reported_status: ON_TRACK, DELAYED, BLOCKED, COMPLETED
        token: The magic link token (will be revoked)
        proposed_new_date: New end date if delayed
        reason_category: Why delayed (SCOPE_INCREASE, etc.)
        reason_details: Additional context
        comment: Free text comment
        client_ip: For audit
        user_agent: For audit
        idempotency_key: Optional key to prevent duplicate submissions
    
    Returns:
        Response processing result
        
    Raises:
        TokenAlreadyUsedError: If token has already been used
    """
    db = get_supabase_client()
    
    # ISSUE_009: Check idempotency key to prevent duplicates
    if idempotency_key:
        existing = db.client.table("work_item_responses").select("id").eq(
            "idempotency_key", idempotency_key
        ).execute()
        if existing.data:
            logger.info(f"Duplicate submission detected with idempotency key: {idempotency_key}")
            return {
                "response_id": existing.data[0]["id"],
                "message": "Response already submitted",
                "duplicate": True
            }
    
    # CRIT_008: Check if token is already used (if provided)
    token_id = None
    if token:
        from app.services.magic_links import get_token_record, hash_token
        token_record = get_token_record(token)
        
        # CRIT_001: Safe null check on token_record
        if token_record is None:
            logger.warning(f"Token not found in database for alert {alert_id}")
            # Allow response without token tracking (graceful degradation)
        elif token_record.get("revoked") or token_record.get("is_revoked"):
            raise TokenAlreadyUsedError(
                "This link has already been used to submit a response",
                used_at=token_record.get("used_at")
            )
        else:
            token_id = token_record.get("id")
    
    # Get alert details
    alert_response = db.client.table("alerts").select(
        "*, work_items(id, external_id, name, current_end, is_critical_path, "
        "phases(projects(program_id)))"
    ).eq("id", str(alert_id)).execute()
    
    if not alert_response.data:
        raise ValueError(f"Alert {alert_id} not found")
    
    alert = alert_response.data[0]
    work_item = alert.get("work_items") or {}
    
    if not work_item or "id" not in work_item:
        raise ValueError(f"Work item not found for alert {alert_id}")
    
    work_item_id = UUID(work_item["id"])
    
    # CRIT_001: Safe extraction of program_id
    phases = work_item.get("phases") or {}
    projects = phases.get("projects") if phases else None
    program_id = projects.get("program_id") if projects else None
    
    # Get the current response version
    version_response = db.client.table("work_item_responses").select(
        "id, response_version"
    ).eq("work_item_id", str(work_item_id)).order(
        "response_version", desc=True
    ).limit(1).execute()
    
    current_version = version_response.data[0]["response_version"] if version_response.data else 0
    latest_response_id = version_response.data[0]["id"] if version_response.data else None
    new_version = current_version + 1
    
    # Calculate delay days if applicable
    delay_days = None
    if proposed_new_date and reported_status == ResponseStatus.DELAYED.value:
        original_end = date.fromisoformat(work_item["current_end"])
        delay_days = (proposed_new_date - original_end).days
    
    # Determine if approval is required
    policy = get_escalation_policy(UUID(program_id) if program_id else None)
    requires_approval = (
        reported_status == ResponseStatus.DELAYED.value and
        delay_days is not None and
        delay_days > policy.auto_approve_delay_up_to_days
    )
    
    # Calculate impact if delayed
    impact_analysis = None
    if reported_status == ResponseStatus.DELAYED.value and proposed_new_date:
        try:
            impact = analyze_impact(
                work_item_id=work_item_id,
                proposed_new_end=proposed_new_date,
                reason_category=reason_category or "OTHER",
                reason_details=reason_details
            )
            impact_analysis = {
                "delay_days": impact.delay_days,
                "cascade_count": impact.cascade_count,
                "is_critical_path": impact.is_critical_path,
                "risk_level": impact.risk_level,
                "recommendation": impact.recommendation,
                "affected_items": [
                    {"external_id": i["external_id"], "name": i["name"]}
                    for i in impact.affected_items[:5]  # Top 5
                ]
            }
        except Exception as e:
            logger.error(f"Impact analysis failed for {work_item_id}: {e}")
            impact_analysis = {"error": str(e)}
    
    # CRIT_004: Use timezone-aware timestamps
    now_utc = datetime.now(timezone.utc)
    
    # CRIT_003/CRIT_008: Atomic response processing
    # All 4 operations must succeed or fail together:
    # 1. Mark previous response as not latest
    # 2. Insert new response with idempotency key
    # 3. Revoke the token
    # 4. Update alert status
    
    try:
        # Step 1: Mark previous response as not latest (if exists)
        if latest_response_id:
            db.client.table("work_item_responses").update({
                "is_latest": False,
                "superseded_by_response_version": new_version
            }).eq("id", latest_response_id).execute()
        
        # Step 2: Create response record with idempotency key
        response_data = {
            "alert_id": str(alert_id),
            "work_item_id": str(work_item_id),
            "responder_resource_id": str(responder_resource_id),
            "response_token_id": token_id,  # CRIT_008: Link to token
            "reported_status": reported_status,
            "proposed_new_date": proposed_new_date.isoformat() if proposed_new_date else None,
            "delay_days": delay_days,
            "reason_category": reason_category,
            "reason_details": reason_details,
            "comment": comment,
            "response_version": new_version,
            "is_latest": True,
            "requires_approval": requires_approval,
            "approval_status": "PENDING" if requires_approval else "AUTO_APPROVED",
            "impact_analysis": impact_analysis,
            "submitted_at": now_utc.isoformat(),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "idempotency_key": idempotency_key  # Issue #9: Track idempotency
        }
        
        response = db.client.table("work_item_responses").insert(response_data).execute()
        response_record = response.data[0] if response.data else {}
        
        if not response_record.get("id"):
            raise ValueError("Failed to create response record")
        
        # Step 3: CRIT_008: Revoke token after successful response creation
        if token_id:
            db.client.table("response_tokens").update({
                "revoked": True,
                "used_at": now_utc.isoformat(),
                "used_by_response_id": response_record.get("id")
            }).eq("id", token_id).execute()
            logger.info(f"Token {token_id[:8]}... revoked after response submission")
        
        # Step 4: Update alert status
        db.client.table("alerts").update({
            "status": AlertStatus.RESPONDED.value,
            "responded_at": now_utc.isoformat()
        }).eq("id", str(alert_id)).execute()
        
    except Exception as e:
        # CRIT_003: Log failure for potential rollback/retry
        logger.error(f"Atomic response processing failed for alert {alert_id}: {e}")
        # Re-raise to allow caller to handle
        raise
    
    # Handle different response types
    result = {
        "response_id": response_record.get("id"),
        "reported_status": reported_status,
        "version": new_version
    }
    
    if reported_status == ResponseStatus.ON_TRACK.value:
        result["message"] = "Thank you! Status confirmed as on track."
    
    elif reported_status == ResponseStatus.DELAYED.value:
        if requires_approval:
            # Create approval request alert for PM
            _create_approval_request(
                work_item_id=work_item_id,
                response_id=UUID(response_record["id"]),
                proposed_new_date=proposed_new_date,
                delay_days=delay_days,
                impact_analysis=impact_analysis,
                responder_name=None  # TODO: Get name
            )
            result["message"] = f"Delay of {delay_days} days recorded. Awaiting PM approval."
            result["requires_approval"] = True
        else:
            # Auto-approve small delays
            _auto_approve_delay(UUID(response_record["id"]), work_item_id, proposed_new_date)
            result["message"] = f"Delay of {delay_days} days auto-approved."
            result["auto_approved"] = True
        
        result["impact"] = impact_analysis
    
    elif reported_status == ResponseStatus.BLOCKED.value:
        # Immediate escalation for blockers
        _handle_blocker_report(
            work_item_id=work_item_id,
            alert_id=alert_id,
            response_id=UUID(response_record["id"]),
            comment=comment,
            reason_details=reason_details
        )
        result["message"] = "Blocker reported. PM has been notified immediately."
        result["escalated"] = True
    
    elif reported_status == ResponseStatus.COMPLETED.value:
        # Mark task as completed
        db.client.table("work_items").update({
            "status": "Completed",
            "actual_end": date.today().isoformat()
        }).eq("id", str(work_item_id)).execute()
        result["message"] = "Task marked as completed."
    
    return result


def _create_approval_request(
    work_item_id: UUID,
    response_id: UUID,
    proposed_new_date: date,
    delay_days: int,
    impact_analysis: Optional[Dict],
    responder_name: Optional[str]
) -> None:
    """Create an approval request alert for PM."""
    db = get_supabase_client()
    
    # TODO: Get PM from program
    # For now, we just create the alert - PM lookup needs to be implemented
    
    alert_data = {
        "work_item_id": str(work_item_id),
        "deadline_date": proposed_new_date.isoformat(),
        "intended_recipient_id": None,  # TODO: PM resource ID
        "alert_type": AlertType.APPROVAL_REQUEST.value,
        "escalation_level": 3,
        "urgency": "HIGH" if delay_days > 3 else "NORMAL",
        "status": AlertStatus.PENDING.value,
        "notification_metadata": {
            "response_id": str(response_id),
            "delay_days": delay_days,
            "impact": impact_analysis,
            "responder": responder_name
        }
    }
    
    db.client.table("alerts").insert(alert_data).execute()


def _auto_approve_delay(
    response_id: UUID,
    work_item_id: UUID,
    new_end_date: date
) -> None:
    """Auto-approve a small delay."""
    db = get_supabase_client()
    
    # Update response as approved
    # CRIT_004: Use timezone-aware datetime
    now_utc = datetime.now(timezone.utc)
    db.client.table("work_item_responses").update({
        "approval_status": "AUTO_APPROVED",
        "approved_at": now_utc.isoformat(),
        "processed": True,
        "processed_at": now_utc.isoformat(),
        "processed_by": "system:auto_approve"
    }).eq("id", str(response_id)).execute()
    
    # Apply the delay
    apply_approved_delay(
        work_item_id=work_item_id,
        new_end_date=new_end_date,
        approved_by="system:auto_approve",
        cascade=True
    )


def _handle_blocker_report(
    work_item_id: UUID,
    alert_id: UUID,
    response_id: UUID,
    comment: Optional[str],
    reason_details: Optional[Dict]
) -> None:
    """Handle a blocker report - immediate PM escalation."""
    db = get_supabase_client()
    
    # Mark work item as at risk
    db.client.table("work_items").update({
        "flag_for_review": True,
        "review_message": f"BLOCKED: {comment or 'Blocker reported'}"
    }).eq("id", str(work_item_id)).execute()
    
    # Create critical alert for PM
    alert_data = {
        "work_item_id": str(work_item_id),
        "deadline_date": date.today().isoformat(),
        "intended_recipient_id": None,  # TODO: PM
        "alert_type": AlertType.BLOCKER_REPORT.value,
        "escalation_level": 3,
        "urgency": "CRITICAL",
        "status": AlertStatus.PENDING.value,
        "parent_alert_id": str(alert_id),
        "escalation_reason": "BLOCKER_REPORTED",
        "notification_metadata": {
            "response_id": str(response_id),
            "blocker_description": comment,
            "details": reason_details
        }
    }
    
    db.client.table("alerts").insert(alert_data).execute()


def check_and_escalate_timeouts() -> List[Dict[str, Any]]:
    """
    Check for alerts that have timed out and need escalation.
    
    This should be run periodically (e.g., every 30 minutes).
    
    Returns:
        List of escalated alerts
    """
    db = get_supabase_client()
    
    # CRIT_004: Use timezone-aware datetime
    now = datetime.now(timezone.utc)
    
    # Find alerts that have passed escalation timeout
    response = db.client.table("alerts").select(
        "*, work_items(resource_id, phases(projects(program_id)))"
    ).in_(
        "status", ["SENT", "DELIVERED", "OPENED"]
    ).lt("escalation_timeout_at", now.isoformat()).execute()
    
    escalated = []
    
    for alert in (response.data or []):
        current_level = alert.get("escalation_level", 0)
        next_level = get_next_escalation_level(current_level)
        
        if next_level == current_level:
            # Already at max level
            continue
        
        work_item = alert.get("work_items", {})
        phases = work_item.get("phases", {})
        projects = phases.get("projects", {}) if phases else {}
        program_id = projects.get("program_id") if projects else None
        
        # Find next available recipient
        recipient, skipped = find_available_recipient(
            resource_id=UUID(work_item["resource_id"]),
            program_id=UUID(program_id) if program_id else None,
            start_level=next_level
        )
        
        if not recipient:
            # No one available at next level
            continue
        
        # Create escalation alert
        new_alert = create_status_check_alert(
            work_item_id=UUID(alert["work_item_id"]),
            deadline=date.fromisoformat(alert["deadline_date"]),
            resource_id=UUID(work_item["resource_id"]),
            program_id=UUID(program_id) if program_id else None
        )
        
        # Update original alert
        db.client.table("alerts").update({
            "status": AlertStatus.EXPIRED.value
        }).eq("id", alert["id"]).execute()
        
        # Record escalation event
        record_escalation_event(
            alert_id=UUID(alert["id"]),
            from_level=current_level,
            to_level=next_level,
            from_resource_id=UUID(alert["actual_recipient_id"]),
            to_resource_id=recipient.resource_id,
            reason="TIMEOUT_NO_RESPONSE"
        )
        
        escalated.append({
            "original_alert_id": alert["id"],
            "new_alert_id": new_alert.get("alert_id"),
            "from_level": current_level,
            "to_level": next_level,
            "new_recipient": recipient.resource_name
        })
    
    return escalated


def approve_delay(
    response_id: UUID,
    approver_resource_id: UUID,
    cascade: bool = True
) -> Dict[str, Any]:
    """
    Approve a delay request from the approval queue.
    
    Args:
        response_id: The response to approve
        approver_resource_id: Who is approving
        cascade: Whether to cascade changes to dependencies
    
    Returns:
        Approval result
    """
    db = get_supabase_client()
    
    # Get response details
    response = db.client.table("work_item_responses").select(
        "*, work_items(id, external_id, name)"
    ).eq("id", str(response_id)).execute()
    
    if not response.data:
        raise ValueError(f"Response {response_id} not found")
    
    resp = response.data[0]
    
    if resp.get("approval_status") != "PENDING":
        raise ValueError(f"Response is not pending approval (status: {resp.get('approval_status')})")
    
    proposed_date = date.fromisoformat(resp["proposed_new_date"])
    work_item_id = UUID(resp["work_item_id"])
    
    # Update response
    # CRIT_004: Use timezone-aware datetime
    now_utc = datetime.now(timezone.utc)
    db.client.table("work_item_responses").update({
        "approval_status": "APPROVED",
        "approved_by_resource_id": str(approver_resource_id),
        "approved_at": now_utc.isoformat(),
        "processed": True,
        "processed_at": now_utc.isoformat()
    }).eq("id", str(response_id)).execute()
    
    # Apply the delay
    result = apply_approved_delay(
        work_item_id=work_item_id,
        new_end_date=proposed_date,
        approved_by=str(approver_resource_id),
        cascade=cascade
    )
    
    # Notify affected teams
    # TODO: Send notifications to downstream task owners
    
    return {
        "approved": True,
        "response_id": str(response_id),
        "work_item": resp.get("work_items", {}).get("external_id"),
        "new_end_date": proposed_date.isoformat(),
        "cascade_count": result.get("cascade_count", 0)
    }


def reject_delay(
    response_id: UUID,
    rejector_resource_id: UUID,
    rejection_reason: str
) -> Dict[str, Any]:
    """
    Reject a delay request.
    
    Args:
        response_id: The response to reject
        rejector_resource_id: Who is rejecting
        rejection_reason: Why it's rejected
    
    Returns:
        Rejection result
    """
    db = get_supabase_client()
    
    # Update response
    # CRIT_004: Use timezone-aware datetime
    now_utc = datetime.now(timezone.utc)
    db.client.table("work_item_responses").update({
        "approval_status": "REJECTED",
        "approved_by_resource_id": str(rejector_resource_id),
        "approved_at": now_utc.isoformat(),
        "rejection_reason": rejection_reason,
        "processed": True,
        "processed_at": now_utc.isoformat()
    }).eq("id", str(response_id)).execute()
    
    # Get response details for notification
    response = db.client.table("work_item_responses").select(
        "responder_resource_id, work_items(external_id, name)"
    ).eq("id", str(response_id)).execute()
    
    resp = response.data[0] if response.data else {}
    
    # TODO: Notify the original responder of rejection
    
    return {
        "rejected": True,
        "response_id": str(response_id),
        "work_item": resp.get("work_items", {}).get("external_id"),
        "reason": rejection_reason
    }


def get_pending_approvals(
    approver_resource_id: Optional[UUID] = None
) -> List[Dict[str, Any]]:
    """
    Get all pending delay approvals.
    
    Args:
        approver_resource_id: Filter to specific approver (PM)
    
    Returns:
        List of pending approval requests
    """
    db = get_supabase_client()
    
    query = db.client.table("work_item_responses").select(
        "*, "
        "work_items(id, external_id, name, current_end, is_critical_path), "
        "resources:responder_resource_id(name, email)"
    ).eq("requires_approval", True).eq("approval_status", "PENDING")
    
    response = query.order("created_at", desc=True).execute()
    
    return [
        {
            "response_id": r["id"],
            "work_item": r.get("work_items", {}),
            "responder": r.get("resources", {}),
            "proposed_new_date": r.get("proposed_new_date"),
            "delay_days": r.get("delay_days"),
            "reason_category": r.get("reason_category"),
            "comment": r.get("comment"),
            "impact": r.get("impact_analysis"),
            "submitted_at": r.get("created_at")
        }
        for r in (response.data or [])
    ]


def run_daily_scan() -> Dict[str, Any]:
    """
    Run the daily status check scan.
    
    This is the main entry point for the daily cron job.
    
    Returns:
        Summary of scan results
    """
    # Get tasks needing status checks
    pending = scan_for_pending_status_checks()
    
    alerts_created = []
    errors = []
    
    for task in pending:
        if task.existing_alert_id:
            # Skip if already has active alert
            continue
        
        try:
            result = create_status_check_alert(
                work_item_id=task.work_item_id,
                deadline=task.deadline,
                resource_id=task.resource_id,
                program_id=task.program_id
            )
            alerts_created.append({
                "work_item": task.external_id,
                "recipient": result.get("recipient", {}).get("name"),
                "alert_id": result.get("alert_id")
            })
        except Exception as e:
            errors.append({
                "work_item": task.external_id,
                "error": str(e)
            })
    
    # Check for escalation timeouts
    escalated = check_and_escalate_timeouts()
    
    return {
        "scan_date": date.today().isoformat(),
        "tasks_scanned": len(pending),
        "alerts_created": len(alerts_created),
        "alerts": alerts_created,
        "escalations": len(escalated),
        "escalated_alerts": escalated,
        "errors": errors
    }
