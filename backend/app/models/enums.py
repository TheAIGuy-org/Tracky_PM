"""
Enum types that match the PostgreSQL ENUM types in Supabase.
These must stay in sync with the database schema.
"""
from enum import Enum


class DependencyType(str, Enum):
    """
    Dependency types for task relationships.
    Matches: create type dependency_type as enum ('FS', 'SS', 'FF', 'SF');
    """
    FS = "FS"  # Finish-to-Start (default, most common)
    SS = "SS"  # Start-to-Start
    FF = "FF"  # Finish-to-Finish
    SF = "SF"  # Start-to-Finish (rare)


class WorkStatus(str, Enum):
    """
    Work item status values.
    Matches: create type work_status as enum ('Not Started', 'In Progress', 'Completed', 'On Hold', 'Cancelled');
    """
    NOT_STARTED = "Not Started"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    ON_HOLD = "On Hold"
    CANCELLED = "Cancelled"


class ProgramStatus(str, Enum):
    """
    Program status values.
    Matches: create type program_status as enum ('Planned', 'Active', 'Completed', 'Cancelled');
    """
    PLANNED = "Planned"
    ACTIVE = "Active"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class ComplexityLevel(str, Enum):
    """
    Complexity levels for work items.
    Matches: create type complexity_level as enum ('Low', 'Medium', 'High');
    """
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class StrategicImportance(str, Enum):
    """Strategic importance levels (not a DB enum, but used for validation)."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class CustomerImpact(str, Enum):
    """Customer impact levels (not a DB enum, but used for validation)."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
