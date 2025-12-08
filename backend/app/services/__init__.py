# Services - Business Logic Layer
"""
Tracky PM Services Module.

This module provides the core business logic for:
- Proactive Execution Tracking Loop
- Alert & Escalation Management
- Notification Delivery
- Background Job Scheduling
"""

# Business Day Calculations
from .business_days import (
    is_business_day,
    is_weekend,
    is_holiday,
    business_days_before,
    business_days_after,
    get_alert_send_date,
    get_alert_send_timestamp,
    get_escalation_timeout,
    get_business_days_between,
    should_send_alert_today,
    get_deadline_urgency,
    format_deadline_message,
)

# Magic Link Authentication
from .magic_links import (
    generate_magic_link_token,
    validate_magic_link_token,
    get_token_info,
    record_token_use,
    create_magic_link,
    TokenError,
    TokenExpiredError,
    TokenRevokedError
)

# Escalation Management
from .escalation import (
    EscalationTarget,
    AvailabilityStatus,
    EscalationRecipient,
    EscalationPolicy,
    get_escalation_policy,
    get_escalation_chain,
    find_available_recipient,
    should_escalate,
    get_next_escalation_level,
    get_escalation_timeout_at,
    record_escalation_event,
    check_resource_availability,
    get_escalation_summary,
)

# Impact Analysis
from .impact_analysis import (
    ReasonCategory,
    ImpactResult,
    DurationRecalculation,
    recalculate_duration,
    calculate_cascade_impact,
    check_resource_conflicts,
    analyze_impact,
    apply_approved_delay,
)

# Alert Orchestration
from .alert_orchestrator import (
    AlertType,
    AlertStatus,
    ResponseStatus,
    PendingStatusCheck,
    scan_for_pending_status_checks,
    create_status_check_alert,
    process_status_response,
    check_and_escalate_timeouts,
    approve_delay,
    reject_delay,
    get_pending_approvals,
    run_daily_scan,
)

# Notification Services
from .notifications import (
    NotificationChannel,
    NotificationStatus,
    NotificationResult,
    NotificationService,
    send_status_check_alert,
    send_escalation_notice,
    send_approval_request,
    send_response_confirmation,
    send_no_recipient_alert,
)

# Background Job Scheduler
from .scheduler import (
    TrackyScheduler,
    get_scheduler,
    scheduler_lifespan
)


__all__ = [
    # Business Days
    "is_business_day",
    "is_weekend",
    "is_holiday",
    "business_days_before",
    "business_days_after",
    "get_alert_send_date",
    "get_alert_send_timestamp",
    "get_escalation_timeout",
    "get_business_days_between",
    "should_send_alert_today",
    "get_deadline_urgency",
    "format_deadline_message",
    
    # Magic Links
    "generate_magic_link_token",
    "validate_magic_link_token",
    "get_token_info",
    "record_token_use",
    "create_magic_link",
    "TokenError",
    "TokenExpiredError",
    "TokenRevokedError",
    
    # Escalation
    "EscalationTarget",
    "AvailabilityStatus",
    "EscalationRecipient",
    "EscalationPolicy",
    "get_escalation_policy",
    "get_escalation_chain",
    "find_available_recipient",
    "should_escalate",
    "get_next_escalation_level",
    "get_escalation_timeout_at",
    "record_escalation_event",
    "check_resource_availability",
    "get_escalation_summary",
    
    # Impact Analysis
    "ReasonCategory",
    "ImpactResult",
    "DurationRecalculation",
    "recalculate_duration",
    "calculate_cascade_impact",
    "check_resource_conflicts",
    "analyze_impact",
    "apply_approved_delay",
    
    # Alert Orchestration
    "AlertType",
    "AlertStatus",
    "ResponseStatus",
    "PendingStatusCheck",
    "scan_for_pending_status_checks",
    "create_status_check_alert",
    "process_status_response",
    "check_and_escalate_timeouts",
    "approve_delay",
    "reject_delay",
    "get_pending_approvals",
    "run_daily_scan",
    
    # Notifications
    "NotificationChannel",
    "NotificationStatus",
    "NotificationResult",
    "NotificationService",
    "send_status_check_alert",
    "send_escalation_notice",
    "send_approval_request",
    "send_response_confirmation",
    "send_no_recipient_alert",
    
    # Scheduler
    "TrackyScheduler",
    "get_scheduler",
    "scheduler_lifespan",
]
