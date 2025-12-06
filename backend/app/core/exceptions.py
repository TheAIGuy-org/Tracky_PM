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
