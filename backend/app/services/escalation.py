"""
Escalation Chain Manager for Tracky PM.

Handles the escalation logic: Primary → Backup → Manager → PM

Key Features:
- Automatic escalation on timeout (4 hours default)
- Respects resource availability status
- Skips unavailable resources in chain
- Handles "ghost" resource (no one available) scenario
- Configurable per-program escalation policies
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple, Dict
from uuid import UUID
from dataclasses import dataclass
from enum import Enum

from app.core.database import get_supabase_client


class EscalationTarget(Enum):
    """Types of escalation targets."""
    PRIMARY = "PRIMARY"
    BACKUP = "BACKUP"
    MANAGER = "MANAGER"
    PM = "PM"


class AvailabilityStatus(Enum):
    """Resource availability status."""
    ACTIVE = "ACTIVE"
    ON_LEAVE = "ON_LEAVE"
    UNAVAILABLE = "UNAVAILABLE"
    PARTIAL = "PARTIAL"


@dataclass
class EscalationRecipient:
    """Represents a recipient in the escalation chain."""
    resource_id: UUID
    resource_name: str
    email: str
    escalation_level: int
    target_type: EscalationTarget
    is_available: bool
    availability_status: str
    skip_reason: Optional[str] = None
    timezone: str = "UTC"
    slack_user_id: Optional[str] = None


@dataclass
class EscalationPolicy:
    """Configuration for escalation behavior."""
    days_before_deadline: int = 1
    alert_time_of_day: str = "09:00"
    timeout_hours_per_level: dict = None  # {0: 4, 1: 4, 2: 2, 3: None}
    auto_approve_delay_up_to_days: int = 0
    blocker_immediate_escalation: bool = True
    
    def __post_init__(self):
        if self.timeout_hours_per_level is None:
            self.timeout_hours_per_level = {
                0: 4,  # Primary: 4 hours
                1: 4,  # Backup: 4 hours
                2: 2,  # Manager: 2 hours
                3: None  # PM: final, no timeout
            }


def get_escalation_policy(program_id: Optional[UUID] = None) -> EscalationPolicy:
    """
    Get the escalation policy for a program.
    
    Falls back to global default if no program-specific policy exists.
    
    Args:
        program_id: Optional program ID for program-specific policy
    
    Returns:
        EscalationPolicy configuration
    """
    db = get_supabase_client()
    
    # Query for program-specific or global policy
    query = db.client.table("escalation_policies").select("*").eq("is_active", True)
    
    if program_id:
        # Try program-specific first
        response = query.eq("program_id", str(program_id)).execute()
        if response.data:
            policy_data = response.data[0]
            return _parse_policy(policy_data)
    
    # Fall back to global (program_id IS NULL)
    response = db.client.table("escalation_policies").select("*").eq(
        "is_active", True
    ).is_("program_id", "null").execute()
    
    if response.data:
        return _parse_policy(response.data[0])
    
    # Return defaults if nothing in DB
    return EscalationPolicy()


def _parse_policy(policy_data: dict) -> EscalationPolicy:
    """Parse policy data from database into EscalationPolicy."""
    chain = policy_data.get("escalation_chain", [])
    timeout_hours = {}
    
    for level_config in chain:
        level = level_config.get("level", 0)
        timeout = level_config.get("timeout_hours")
        timeout_hours[level] = timeout
    
    return EscalationPolicy(
        days_before_deadline=policy_data.get("days_before_deadline", 1),
        alert_time_of_day=str(policy_data.get("alert_time_of_day", "09:00")),
        timeout_hours_per_level=timeout_hours,
        auto_approve_delay_up_to_days=policy_data.get("auto_approve_delay_up_to_days", 0),
        blocker_immediate_escalation=policy_data.get("blocker_immediate_escalation", True)
    )


def get_escalation_chain(
    resource_id: UUID,
    program_id: Optional[UUID] = None
) -> List[EscalationRecipient]:
    """
    Get the full escalation chain for a resource.
    
    Chain order: Primary → Backup → Manager → PM
    
    Args:
        resource_id: The primary resource (task owner)
        program_id: Optional program for PM lookup
    
    Returns:
        List of EscalationRecipient in escalation order
    """
    db = get_supabase_client()
    
    # Get the primary resource with their backup and manager
    response = db.client.table("resources").select(
        "*, backup:backup_resource_id(*), manager:manager_id(*)"
    ).eq("id", str(resource_id)).execute()
    
    if not response.data:
        return []
    
    primary = response.data[0]
    chain = []
    
    # CRIT_001: Validate primary resource has required fields
    if not primary.get("id") or not primary.get("name"):
        return []
    
    # CRIT_001: Safe email extraction with fallback
    primary_email = primary.get("notification_email") or primary.get("email") or ""
    if not primary_email:
        # Log but continue - we might still find a valid recipient in chain
        import logging
        logging.getLogger(__name__).warning(
            f"Resource {primary.get('id')} has no email configured"
        )
    
    # Level 0: Primary
    chain.append(EscalationRecipient(
        resource_id=UUID(primary["id"]),
        resource_name=primary["name"],
        email=primary_email,
        escalation_level=0,
        target_type=EscalationTarget.PRIMARY,
        is_available=primary.get("availability_status", "ACTIVE") == "ACTIVE",
        availability_status=primary.get("availability_status", "ACTIVE"),
        timezone=primary.get("timezone", "UTC"),
        slack_user_id=primary.get("slack_user_id")
    ))
    
    # Level 1: Backup - CRIT_001: Safe null checks
    backup = primary.get("backup")
    if backup and backup.get("id") and backup.get("name"):
        backup_email = backup.get("notification_email") or backup.get("email") or ""
        chain.append(EscalationRecipient(
            resource_id=UUID(backup["id"]),
            resource_name=backup["name"],
            email=backup_email,
            escalation_level=1,
            target_type=EscalationTarget.BACKUP,
            is_available=backup.get("availability_status", "ACTIVE") == "ACTIVE",
            availability_status=backup.get("availability_status", "ACTIVE"),
            timezone=backup.get("timezone", "UTC"),
            slack_user_id=backup.get("slack_user_id")
        ))
    
    # Level 2: Manager - CRIT_001: Safe null checks
    manager = primary.get("manager")
    if manager and manager.get("id") and manager.get("name"):
        manager_email = manager.get("notification_email") or manager.get("email") or ""
        chain.append(EscalationRecipient(
            resource_id=UUID(manager["id"]),
            resource_name=manager["name"],
            email=manager_email,
            escalation_level=2,
            target_type=EscalationTarget.MANAGER,
            is_available=manager.get("availability_status", "ACTIVE") == "ACTIVE",
            availability_status=manager.get("availability_status", "ACTIVE"),
            timezone=manager.get("timezone", "UTC"),
            slack_user_id=manager.get("slack_user_id")
        ))
    
    # Level 3: PM (from program) - CRIT_001: Safe null checks
    pm = _get_program_pm(program_id)
    if pm and pm.get("id") and pm.get("name"):
        pm_email = pm.get("notification_email") or pm.get("email") or ""
        chain.append(EscalationRecipient(
            resource_id=UUID(pm["id"]),
            resource_name=pm["name"],
            email=pm_email,
            escalation_level=3,
            target_type=EscalationTarget.PM,
            is_available=pm.get("availability_status", "ACTIVE") == "ACTIVE",
            availability_status=pm.get("availability_status", "ACTIVE"),
            timezone=pm.get("timezone", "UTC"),
            slack_user_id=pm.get("slack_user_id")
        ))
    
    return chain


def _get_program_pm(program_id: Optional[UUID]) -> Optional[Dict]:
    """
    Get the PM resource for a program.
    
    Tries in order:
    1. Primary PM from program.pm_resource_id
    2. Secondary PM from program.secondary_pm_resource_id
    3. Default PM from organization_settings
    
    Args:
        program_id: Optional program ID
    
    Returns:
        PM resource dict or None
    """
    db = get_supabase_client()
    
    if program_id:
        # Try primary PM
        response = db.client.table("programs").select(
            "pm_resource_id, secondary_pm_resource_id, "
            "pm:pm_resource_id(*), secondary_pm:secondary_pm_resource_id(*)"
        ).eq("id", str(program_id)).execute()
        
        if response.data:
            program = response.data[0]
            
            # Check primary PM
            pm = program.get("pm")
            if pm and pm.get("availability_status", "ACTIVE") == "ACTIVE":
                return pm
            
            # Check secondary PM
            secondary_pm = program.get("secondary_pm")
            if secondary_pm and secondary_pm.get("availability_status", "ACTIVE") == "ACTIVE":
                return secondary_pm
            
            # Return primary even if unavailable (better than nothing)
            if pm:
                return pm
    
    # Try default PM from org settings
    try:
        settings_response = db.client.table("organization_settings").select(
            "value"
        ).eq("key", "default_pm_resource_id").execute()
        
        if settings_response.data:
            value = settings_response.data[0].get("value")
            if value and value != "null":
                # Get the PM resource
                pm_id = value.strip('"') if isinstance(value, str) else str(value)
                pm_response = db.client.table("resources").select("*").eq("id", pm_id).execute()
                
                if pm_response.data:
                    return pm_response.data[0]
    except Exception:
        pass  # org_settings table might not exist yet
    
    return None


def find_available_recipient(
    resource_id: UUID,
    program_id: Optional[UUID] = None,
    start_level: int = 0
) -> Tuple[Optional[EscalationRecipient], List[EscalationRecipient]]:
    """
    Find the first available recipient in the escalation chain.
    
    Skips unavailable resources and returns who was skipped.
    
    Args:
        resource_id: The primary resource
        program_id: Optional program ID
        start_level: Start searching from this level (for re-escalation)
    
    Returns:
        Tuple of (available_recipient, list_of_skipped)
    """
    chain = get_escalation_chain(resource_id, program_id)
    skipped = []
    
    for recipient in chain:
        if recipient.escalation_level < start_level:
            continue
        
        if recipient.is_available:
            return recipient, skipped
        else:
            recipient.skip_reason = f"Resource is {recipient.availability_status}"
            skipped.append(recipient)
    
    # No one available!
    return None, skipped


def should_escalate(
    alert_sent_at: datetime,
    current_level: int,
    policy: Optional[EscalationPolicy] = None
) -> bool:
    """
    Check if an alert should be escalated based on timeout.
    
    CRIT_004: Uses UTC-aware timestamps for comparison.
    
    Args:
        alert_sent_at: When the alert was sent (should be UTC)
        current_level: Current escalation level
        policy: Escalation policy (uses default if None)
    
    Returns:
        True if alert should be escalated
    """
    from datetime import timezone as tz
    
    if policy is None:
        policy = EscalationPolicy()
    
    timeout_hours = policy.timeout_hours_per_level.get(current_level)
    
    # None means no further escalation (final level)
    if timeout_hours is None:
        return False
    
    # CRIT_004: Ensure alert_sent_at is timezone-aware
    if alert_sent_at.tzinfo is None:
        alert_sent_at = alert_sent_at.replace(tzinfo=tz.utc)
    
    timeout_at = alert_sent_at + timedelta(hours=timeout_hours)
    now = datetime.now(tz.utc)  # CRIT_004: UTC-aware
    
    return now > timeout_at


def get_next_escalation_level(current_level: int) -> int:
    """Get the next escalation level."""
    return min(current_level + 1, 3)  # Cap at PM level (3)


def get_escalation_timeout_at(
    sent_at: datetime,
    escalation_level: int,
    policy: Optional[EscalationPolicy] = None
) -> Optional[datetime]:
    """
    Calculate when an alert should escalate.
    
    Args:
        sent_at: When the alert was sent
        escalation_level: Current escalation level
        policy: Escalation policy
    
    Returns:
        Datetime when escalation should happen, or None if final level
    """
    if policy is None:
        policy = EscalationPolicy()
    
    timeout_hours = policy.timeout_hours_per_level.get(escalation_level)
    
    if timeout_hours is None:
        return None
    
    return sent_at + timedelta(hours=timeout_hours)


def record_escalation_event(
    alert_id: UUID,
    from_level: int,
    to_level: int,
    from_resource_id: UUID,
    to_resource_id: UUID,
    reason: str
) -> None:
    """
    Record an escalation event in the audit log.
    
    Args:
        alert_id: The alert being escalated
        from_level: Previous escalation level
        to_level: New escalation level
        from_resource_id: Who it was escalated from
        to_resource_id: Who it was escalated to
        reason: Why escalation happened
    """
    db = get_supabase_client()
    
    db.client.table("audit_logs").insert({
        "entity_type": "alert",
        "entity_id": str(alert_id),
        "action": "escalated",
        "field_changed": "escalation_level",
        "old_value": str(from_level),
        "new_value": str(to_level),
        "change_source": "system:escalation",
        "reason": reason,
        "metadata": {
            "from_resource_id": str(from_resource_id),
            "to_resource_id": str(to_resource_id)
        }
    }).execute()


def check_resource_availability(
    resource_id: UUID,
    check_date: Optional[datetime] = None
) -> Tuple[bool, str]:
    """
    Check if a resource is available on a specific date.
    
    Considers:
    - availability_status field
    - leave_start_date / leave_end_date
    
    Args:
        resource_id: Resource to check
        check_date: Date to check (defaults to now)
    
    Returns:
        Tuple of (is_available, reason)
    """
    if check_date is None:
        # CRIT_004: Use timezone-aware datetime
        check_date = datetime.now(timezone.utc)
    
    db = get_supabase_client()
    
    response = db.client.table("resources").select(
        "availability_status, leave_start_date, leave_end_date"
    ).eq("id", str(resource_id)).execute()
    
    if not response.data:
        return False, "Resource not found"
    
    resource = response.data[0]
    status = resource.get("availability_status", "ACTIVE")
    
    # Check explicit status
    if status == "UNAVAILABLE":
        return False, "Resource marked as unavailable"
    
    if status == "ON_LEAVE":
        return False, "Resource is on leave"
    
    # Check leave dates
    leave_start = resource.get("leave_start_date")
    leave_end = resource.get("leave_end_date")
    
    if leave_start and leave_end:
        leave_start_dt = datetime.fromisoformat(leave_start)
        leave_end_dt = datetime.fromisoformat(leave_end)
        
        if leave_start_dt <= check_date <= leave_end_dt:
            return False, f"Resource on leave until {leave_end}"
    
    return True, "Available"


def get_escalation_summary(alert_id: UUID) -> dict:
    """
    Get a summary of escalation history for an alert.
    
    Args:
        alert_id: The alert ID
    
    Returns:
        Dict with escalation history
    """
    db = get_supabase_client()
    
    # Get the alert chain (parent alerts)
    response = db.client.table("alerts").select(
        "id, escalation_level, actual_recipient_id, escalation_reason, "
        "sent_at, responded_at, status, "
        "resources:actual_recipient_id(name, email)"
    ).or_(
        f"id.eq.{alert_id},parent_alert_id.eq.{alert_id}"
    ).order("escalation_level").execute()
    
    alerts = response.data or []
    
    return {
        "alert_id": str(alert_id),
        "escalation_count": len(alerts) - 1 if alerts else 0,
        "current_level": max((a["escalation_level"] for a in alerts), default=0),
        "history": [
            {
                "level": a["escalation_level"],
                "recipient": a.get("resources", {}).get("name"),
                "sent_at": a["sent_at"],
                "responded_at": a["responded_at"],
                "status": a["status"],
                "reason": a["escalation_reason"]
            }
            for a in alerts
        ]
    }
