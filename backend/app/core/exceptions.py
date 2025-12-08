"""
Custom exceptions for Tracky PM application.
Provides meaningful error types for different failure scenarios.
"""
from typing import Any, Optional


class TrackyException(Exception):
    """Base exception for all Tracky PM errors."""
    
    def __init__(
        self,
        message: str,
        details: Optional[dict[str, Any]] = None,
        status_code: int = 500
    ):
        self.message = message
        self.details = details or {}
        self.status_code = status_code
        super().__init__(self.message)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API response."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


class ValidationError(TrackyException):
    """Raised when data validation fails."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        row: Optional[int] = None
    ):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)
        if row is not None:
            details["row"] = row
        
        super().__init__(message, details, status_code=422)


class ImportError(TrackyException):
    """Raised when file import fails."""
    
    def __init__(
        self,
        message: str,
        file_name: Optional[str] = None,
        sheet_name: Optional[str] = None,
        row_number: Optional[int] = None
    ):
        details = {}
        if file_name:
            details["file_name"] = file_name
        if sheet_name:
            details["sheet_name"] = sheet_name
        if row_number:
            details["row_number"] = row_number
        
        super().__init__(message, details, status_code=400)


class DatabaseError(TrackyException):
    """Raised when database operations fail."""
    
    def __init__(
        self,
        message: str,
        table: Optional[str] = None,
        operation: Optional[str] = None,
        original_error: Optional[str] = None
    ):
        details = {}
        if table:
            details["table"] = table
        if operation:
            details["operation"] = operation
        if original_error:
            details["original_error"] = original_error
        
        super().__init__(message, details, status_code=500)


class MergeConflictError(TrackyException):
    """Raised when Smart Merge encounters an unresolvable conflict."""
    
    def __init__(
        self,
        message: str,
        work_item_id: str,
        conflict_type: str,
        baseline_value: Any,
        current_value: Any
    ):
        details = {
            "work_item_id": work_item_id,
            "conflict_type": conflict_type,
            "baseline_value": str(baseline_value),
            "current_value": str(current_value),
        }
        super().__init__(message, details, status_code=409)


class DependencyCycleError(TrackyException):
    """Raised when a circular dependency is detected."""
    
    def __init__(
        self,
        message: str,
        cycle_path: list[str]
    ):
        details = {
            "cycle_path": cycle_path,
        }
        super().__init__(message, details, status_code=400)


class ResourceNotFoundError(TrackyException):
    """Raised when a referenced resource doesn't exist."""
    
    def __init__(
        self,
        message: str,
        resource_type: str,
        external_id: str
    ):
        details = {
            "resource_type": resource_type,
            "external_id": external_id,
        }
        super().__init__(message, details, status_code=404)


class FileFormatError(ImportError):
    """Raised when file format is invalid or unsupported."""
    
    def __init__(
        self,
        message: str,
        expected_format: str,
        actual_format: Optional[str] = None
    ):
        super().__init__(message)
        self.details["expected_format"] = expected_format
        if actual_format:
            self.details["actual_format"] = actual_format


# ==========================================
# CRITICAL ALERT EXCEPTIONS (CRIT_002, CRIT_005)
# ==========================================

class CriticalAlertException(TrackyException):
    """
    Raised when a critical alert cannot be delivered.
    
    This is a CRITICAL exception that requires immediate attention.
    Use when:
    - No PM found for escalation AND no fallback configured
    - Critical blocker cannot be communicated
    - System monitoring detects critical failure
    """
    
    def __init__(
        self,
        message: str,
        work_item_id: Optional[str] = None,
        alert_type: Optional[str] = None,
        attempted_recipients: Optional[list] = None
    ):
        details = {
            "severity": "CRITICAL",
            "requires_immediate_action": True
        }
        if work_item_id:
            details["work_item_id"] = work_item_id
        if alert_type:
            details["alert_type"] = alert_type
        if attempted_recipients:
            details["attempted_recipients"] = attempted_recipients
        
        super().__init__(message, details, status_code=500)


class EscalationFailureException(TrackyException):
    """Raised when escalation chain is exhausted without finding a recipient."""
    
    def __init__(
        self,
        message: str,
        work_item_id: str,
        escalation_level: int,
        skipped_recipients: list
    ):
        details = {
            "work_item_id": work_item_id,
            "escalation_level": escalation_level,
            "skipped_recipients": skipped_recipients,
            "action_required": "Configure PM or fallback email"
        }
        super().__init__(message, details, status_code=500)


class TokenError(TrackyException):
    """Base exception for magic link token errors."""
    
    def __init__(self, message: str, token_hint: Optional[str] = None):
        details = {}
        if token_hint:
            details["token_hint"] = token_hint[:8] + "..."  # Only show prefix
        super().__init__(message, details, status_code=401)


class TokenExpiredError(TokenError):
    """Raised when a magic link token has expired."""
    
    def __init__(self, message: str = "Token has expired", expired_at: Optional[str] = None):
        super().__init__(message)
        if expired_at:
            self.details["expired_at"] = expired_at


class TokenAlreadyUsedError(TokenError):
    """Raised when a magic link token has already been used (CRIT_008)."""
    
    def __init__(self, message: str = "Token has already been used", used_at: Optional[str] = None):
        super().__init__(message)
        self.details["already_used"] = True
        if used_at:
            self.details["used_at"] = used_at


class TokenRevokedError(TokenError):
    """Raised when a magic link token has been revoked."""
    
    def __init__(self, message: str = "Token has been revoked"):
        super().__init__(message)
        self.details["revoked"] = True


class CascadeError(TrackyException):
    """
    Raised when cascade update fails partially (CRIT_006).
    
    This indicates data inconsistency - some items updated, others not.
    """
    
    def __init__(
        self,
        message: str,
        primary_work_item_id: str,
        successful_updates: list,
        failed_updates: list,
        rollback_attempted: bool = False
    ):
        details = {
            "primary_work_item_id": primary_work_item_id,
            "successful_count": len(successful_updates),
            "failed_count": len(failed_updates),
            "successful_updates": successful_updates,
            "failed_updates": failed_updates,
            "rollback_attempted": rollback_attempted,
            "data_consistency": "COMPROMISED" if not rollback_attempted else "RESTORED"
        }
        super().__init__(message, details, status_code=500)


class DuplicateAlertError(TrackyException):
    """Raised when attempting to create a duplicate alert (CRIT_003)."""
    
    def __init__(
        self,
        message: str,
        work_item_id: str,
        existing_alert_id: str,
        deadline_date: str
    ):
        details = {
            "work_item_id": work_item_id,
            "existing_alert_id": existing_alert_id,
            "deadline_date": deadline_date
        }
        super().__init__(message, details, status_code=409)


class SchedulerJobError(TrackyException):
    """Raised when a scheduler job fails (CRIT_007)."""
    
    def __init__(
        self,
        message: str,
        job_id: str,
        failure_count: int,
        last_error: Optional[str] = None
    ):
        details = {
            "job_id": job_id,
            "failure_count": failure_count,
            "threshold_exceeded": failure_count >= 2
        }
        if last_error:
            details["last_error"] = last_error
        
        super().__init__(message, details, status_code=500)


class ConfigurationError(TrackyException):
    """Raised when required configuration is missing or invalid (CRIT_005)."""
    
    def __init__(
        self,
        message: str,
        config_key: str,
        expected_type: Optional[str] = None,
        actual_value: Optional[str] = None
    ):
        details = {
            "config_key": config_key
        }
        if expected_type:
            details["expected_type"] = expected_type
        if actual_value:
            details["actual_value"] = actual_value[:50] if len(str(actual_value)) > 50 else actual_value
        
        super().__init__(message, details, status_code=500)
