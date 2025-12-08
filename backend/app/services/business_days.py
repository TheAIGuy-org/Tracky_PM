"""
Business Day Calculator for Tracky PM.

Handles timezone-aware business day calculations with holiday support.
This is critical for determining when to send status check alerts.

Key Rules:
- Alert for Monday deadline → Send on Friday (not Sunday)
- Alert for Friday deadline → Send on Wednesday (1 business day before)
- Respect company holidays
- Respect resource timezones
"""
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, List, Tuple
from zoneinfo import ZoneInfo

from app.core.database import get_supabase_client


# Cache holidays to avoid repeated DB calls
_holiday_cache: dict[str, set[date]] = {}
_holiday_cache_expiry: datetime | None = None


def _load_holidays(country_code: str = "US") -> set[date]:
    """Load holidays from database into cache."""
    global _holiday_cache, _holiday_cache_expiry
    
    # Refresh cache every hour
    # CRIT_004: Use timezone-aware datetime
    now = datetime.now(timezone.utc)
    if _holiday_cache_expiry and now < _holiday_cache_expiry and country_code in _holiday_cache:
        return _holiday_cache[country_code]
    
    db = get_supabase_client()
    
    # Load holidays for next 2 years
    start_date = date.today() - timedelta(days=30)
    end_date = date.today() + timedelta(days=730)
    
    response = db.client.table("holiday_calendar").select("holiday_date").gte(
        "holiday_date", start_date.isoformat()
    ).lte(
        "holiday_date", end_date.isoformat()
    ).or_(
        f"country_code.eq.{country_code},country_code.is.null"
    ).execute()
    
    holidays = {
        date.fromisoformat(row["holiday_date"]) 
        for row in (response.data or [])
    }
    
    _holiday_cache[country_code] = holidays
    _holiday_cache_expiry = now + timedelta(hours=1)
    
    return holidays


def is_weekend(check_date: date) -> bool:
    """Check if date is a weekend (Saturday=5, Sunday=6)."""
    return check_date.weekday() >= 5


def is_holiday(check_date: date, country_code: str = "US") -> bool:
    """Check if date is a holiday."""
    holidays = _load_holidays(country_code)
    return check_date in holidays


def is_business_day(check_date: date, country_code: str = "US") -> bool:
    """
    Check if a date is a business day.
    
    Business day = Not weekend AND not holiday
    """
    if is_weekend(check_date):
        return False
    if is_holiday(check_date, country_code):
        return False
    return True


def business_days_before(
    target_date: date,
    num_days: int,
    country_code: str = "US"
) -> date:
    """
    Calculate N business days before a target date.
    
    Example:
        target_date = Monday April 15
        num_days = 1
        result = Friday April 12 (skips weekend)
    
    Args:
        target_date: The deadline date
        num_days: Number of business days to go back
        country_code: Country for holiday lookup
    
    Returns:
        Date that is N business days before target
    """
    if num_days <= 0:
        return target_date
    
    result_date = target_date
    days_counted = 0
    max_iterations = num_days * 3 + 30  # Safety limit
    iterations = 0
    
    while days_counted < num_days and iterations < max_iterations:
        result_date = result_date - timedelta(days=1)
        
        if is_business_day(result_date, country_code):
            days_counted += 1
        
        iterations += 1
    
    return result_date


def business_days_after(
    start_date: date,
    num_days: int,
    country_code: str = "US"
) -> date:
    """
    Calculate N business days after a start date.
    
    Args:
        start_date: The starting date
        num_days: Number of business days to add
        country_code: Country for holiday lookup
    
    Returns:
        Date that is N business days after start
    """
    if num_days <= 0:
        return start_date
    
    result_date = start_date
    days_counted = 0
    max_iterations = num_days * 3 + 30
    iterations = 0
    
    while days_counted < num_days and iterations < max_iterations:
        result_date = result_date + timedelta(days=1)
        
        if is_business_day(result_date, country_code):
            days_counted += 1
        
        iterations += 1
    
    return result_date


def get_alert_send_date(
    deadline: date,
    days_before: int = 1,
    country_code: str = "US"
) -> date:
    """
    Calculate when to send a status check alert for a deadline.
    
    Key Logic:
    - For Monday deadline → Alert on Friday (1 business day before)
    - For Friday deadline → Alert on Thursday
    - If holiday on alert day → Move to previous business day
    
    Args:
        deadline: The task deadline
        days_before: Business days before deadline to send alert
        country_code: Country for holiday/timezone lookup
    
    Returns:
        Date when alert should be sent
    """
    return business_days_before(deadline, days_before, country_code)


def get_alert_send_timestamp(
    deadline: date,
    alert_time: time = time(9, 0),  # 9:00 AM
    resource_timezone: str = "UTC",
    days_before: int = 1,
    country_code: str = "US"
) -> datetime:
    """
    Calculate exact timestamp when to send alert (in UTC).
    
    Combines:
    - Business day calculation
    - Time of day (9 AM in resource's timezone)
    - Timezone conversion to UTC
    
    Args:
        deadline: The task deadline
        alert_time: Time of day to send (default 9 AM)
        resource_timezone: Resource's timezone (e.g., "America/New_York")
        days_before: Business days before deadline
        country_code: Country for holiday lookup
    
    Returns:
        UTC datetime when alert should be sent
    """
    # Get the alert date (business day calculation)
    alert_date = get_alert_send_date(deadline, days_before, country_code)
    
    # Combine with time in resource's timezone
    try:
        tz = ZoneInfo(resource_timezone)
    except Exception:
        tz = ZoneInfo("UTC")
    
    local_datetime = datetime.combine(alert_date, alert_time, tzinfo=tz)
    
    # Convert to UTC
    utc_datetime = local_datetime.astimezone(ZoneInfo("UTC"))
    
    return utc_datetime


def get_escalation_timeout(
    sent_at: datetime,
    timeout_hours: int = 4
) -> datetime:
    """
    Calculate when to escalate if no response received.
    
    Args:
        sent_at: When the alert was sent
        timeout_hours: Hours to wait before escalating
    
    Returns:
        UTC datetime when escalation should trigger
    """
    return sent_at + timedelta(hours=timeout_hours)


def get_business_days_between(
    start_date: date,
    end_date: date,
    country_code: str = "US"
) -> int:
    """
    Count business days between two dates (exclusive of end).
    
    Args:
        start_date: Start date
        end_date: End date
        country_code: Country for holiday lookup
    
    Returns:
        Number of business days
    """
    if start_date >= end_date:
        return 0
    
    count = 0
    current = start_date
    
    while current < end_date:
        if is_business_day(current, country_code):
            count += 1
        current += timedelta(days=1)
    
    return count


def should_send_alert_today(
    deadline: date,
    days_before: int = 1,
    country_code: str = "US"
) -> bool:
    """
    Check if alert for this deadline should be sent today.
    
    Args:
        deadline: The task deadline
        days_before: Business days before deadline to send alert
        country_code: Country for holiday lookup
    
    Returns:
        True if alert should be sent today
    """
    alert_date = get_alert_send_date(deadline, days_before, country_code)
    return alert_date == date.today()


def get_deadline_urgency(deadline: date) -> str:
    """
    Determine urgency level based on deadline proximity.
    
    Returns:
        CRITICAL: Due today or overdue
        HIGH: Due tomorrow
        NORMAL: Due within 3 business days
        LOW: Due later
    """
    today = date.today()
    
    if deadline <= today:
        return "CRITICAL"
    
    days_until = (deadline - today).days
    
    if days_until == 1:
        return "HIGH"
    elif days_until <= 3:
        return "NORMAL"
    else:
        return "LOW"


# Utility for displaying dates in user-friendly format
def format_deadline_message(deadline: date) -> str:
    """
    Format deadline for user-friendly display.
    
    Examples:
        "Today (Apr 15)"
        "Tomorrow (Apr 16)"
        "Wednesday, Apr 17"
    """
    today = date.today()
    
    if deadline == today:
        return f"Today ({deadline.strftime('%b %d')})"
    elif deadline == today + timedelta(days=1):
        return f"Tomorrow ({deadline.strftime('%b %d')})"
    else:
        return deadline.strftime("%A, %b %d")
