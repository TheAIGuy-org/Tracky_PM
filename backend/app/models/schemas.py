"""
Pydantic schemas for data validation and serialization.
Covers all entities: Resources, Programs, Projects, Phases, Work Items, Dependencies.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from .enums import (
    DependencyType,
    WorkStatus,
    ProgramStatus,
    ComplexityLevel,
)


# ==========================================
# BASE SCHEMAS
# ==========================================

class TimestampMixin(BaseModel):
    """Mixin for created_at timestamp."""
    created_at: Optional[datetime] = None


class ExternalIdMixin(BaseModel):
    """Mixin for external_id field."""
    external_id: str = Field(..., min_length=1, max_length=50)


# ==========================================
# RESOURCE SCHEMAS (Sheet 3B)
# ==========================================

class ResourceBase(BaseModel):
    """Base resource fields."""
    name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., min_length=5, max_length=255)
    role: Optional[str] = None
    home_team: Optional[str] = None
    cost_per_hour: Optional[Decimal] = Field(None, ge=0)
    max_utilization: int = Field(100, ge=1, le=200)
    skill_level: Optional[str] = None
    location: Optional[str] = None
    availability_status: str = "Available"


class ResourceCreate(ResourceBase, ExternalIdMixin):
    """Schema for creating a resource from Excel import."""
    pass


class ResourceInDB(ResourceBase, ExternalIdMixin, TimestampMixin):
    """Schema for resource as stored in database."""
    id: UUID


# ==========================================
# PROGRAM SCHEMAS (Sheet 1)
# ==========================================

class ProgramBase(BaseModel):
    """Base program fields."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    status: ProgramStatus = ProgramStatus.PLANNED
    baseline_start_date: date
    baseline_end_date: date
    program_owner: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=5)
    budget: Optional[Decimal] = Field(None, ge=0)
    strategic_goal: Optional[str] = None
    noise_threshold_days: int = Field(2, ge=0)
    
    @model_validator(mode='after')
    def validate_dates(self) -> 'ProgramBase':
        """Ensure end date is not before start date."""
        if self.baseline_end_date < self.baseline_start_date:
            raise ValueError("baseline_end_date cannot be before baseline_start_date")
        return self


class ProgramCreate(ProgramBase, ExternalIdMixin):
    """Schema for creating a program from Excel import."""
    pass


class ProgramInDB(ProgramBase, ExternalIdMixin, TimestampMixin):
    """Schema for program as stored in database."""
    id: UUID


# ==========================================
# PROJECT SCHEMAS (Sheet 2 - Header)
# ==========================================

class ProjectBase(BaseModel):
    """Base project fields."""
    name: str = Field(..., min_length=1, max_length=200)


class ProjectCreate(ProjectBase, ExternalIdMixin):
    """Schema for creating a project from Excel import."""
    program_id: UUID


class ProjectInDB(ProjectBase, ExternalIdMixin):
    """Schema for project as stored in database."""
    id: UUID
    program_id: UUID


# ==========================================
# PHASE SCHEMAS (Sheet 2 - Header)
# ==========================================

class PhaseBase(BaseModel):
    """Base phase fields."""
    name: str = Field(..., min_length=1, max_length=200)
    sequence: int = Field(..., ge=1)
    phase_type: Optional[str] = None


class PhaseCreate(PhaseBase, ExternalIdMixin):
    """Schema for creating a phase from Excel import."""
    project_id: UUID


class PhaseInDB(PhaseBase, ExternalIdMixin):
    """Schema for phase as stored in database."""
    id: UUID
    project_id: UUID


# ==========================================
# WORK ITEM SCHEMAS (Sheet 2 - Main Data)
# THE MOST CRITICAL SCHEMA FOR SMART MERGE
# ==========================================

class WorkItemBase(BaseModel):
    """
    Base work item fields.
    Contains both Plan (Baseline) and Reality (Current/Actual) fields.
    """
    name: str = Field(..., min_length=1, max_length=500)
    
    # TIMELINE - Plan/Baseline (Updated from Excel)
    planned_start: date
    planned_end: date
    planned_effort_hours: Optional[int] = Field(None, ge=0)
    allocation_percent: int = Field(100, ge=0, le=100)
    
    # RISK & METADATA
    complexity: Optional[ComplexityLevel] = None
    revenue_impact: Optional[Decimal] = Field(None, ge=0)
    strategic_importance: Optional[str] = None
    customer_impact: Optional[str] = None
    is_critical_launch: bool = False
    feature_name: Optional[str] = None
    
    @model_validator(mode='after')
    def validate_dates(self) -> 'WorkItemBase':
        """Ensure end date is not before start date."""
        if self.planned_end < self.planned_start:
            raise ValueError("planned_end cannot be before planned_start")
        return self


class WorkItemCreate(WorkItemBase, ExternalIdMixin):
    """
    Schema for creating a NEW work item from Excel import.
    For new items: current dates = planned dates, status = Not Started
    """
    phase_id: UUID
    resource_id: Optional[UUID] = None
    
    # These will be set equal to planned dates on INSERT
    current_start: Optional[date] = None
    current_end: Optional[date] = None
    status: WorkStatus = WorkStatus.NOT_STARTED
    completion_percent: int = 0
    
    def model_post_init(self, __context: Any) -> None:
        """Set current dates equal to planned dates for new items."""
        if self.current_start is None:
            object.__setattr__(self, 'current_start', self.planned_start)
        if self.current_end is None:
            object.__setattr__(self, 'current_end', self.planned_end)


class WorkItemUpdate(BaseModel):
    """
    Schema for updating BASELINE ONLY fields via Smart Merge.
    EXCLUDES: current_start, current_end, status, completion_percent, actual_*
    This is the whitelist for Case B (Existing Task Update).
    """
    name: Optional[str] = None
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    planned_effort_hours: Optional[int] = None
    allocation_percent: Optional[int] = None
    resource_id: Optional[UUID] = None
    complexity: Optional[ComplexityLevel] = None
    revenue_impact: Optional[Decimal] = None
    strategic_importance: Optional[str] = None
    customer_impact: Optional[str] = None
    is_critical_launch: Optional[bool] = None
    feature_name: Optional[str] = None


class WorkItemInDB(WorkItemBase, ExternalIdMixin, TimestampMixin):
    """Schema for work item as stored in database."""
    id: UUID
    phase_id: UUID
    resource_id: Optional[UUID] = None
    
    # TIMELINE - Reality (PRESERVED during Smart Merge)
    current_start: date
    current_end: date
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None
    
    # STATUS (PRESERVED during Smart Merge)
    status: WorkStatus = WorkStatus.NOT_STARTED
    completion_percent: int = 0
    slack_days: int = 0
    
    updated_at: Optional[datetime] = None


# ==========================================
# DEPENDENCY SCHEMAS (Sheet 3A)
# ==========================================

class DependencyBase(BaseModel):
    """Base dependency fields."""
    dependency_type: DependencyType = DependencyType.FS
    lag_days: int = Field(0, ge=-365, le=365)
    notes: Optional[str] = None


class DependencyCreate(DependencyBase):
    """Schema for creating a dependency from Excel import."""
    successor_item_id: UUID  # The task that depends
    predecessor_item_id: UUID  # The prerequisite task
    
    @model_validator(mode='after')
    def validate_not_self_reference(self) -> 'DependencyCreate':
        """Ensure a task doesn't depend on itself."""
        if self.successor_item_id == self.predecessor_item_id:
            raise ValueError("A task cannot depend on itself")
        return self


class DependencyInDB(DependencyBase):
    """Schema for dependency as stored in database."""
    id: UUID
    successor_item_id: UUID
    predecessor_item_id: UUID


# ==========================================
# IMPORT RESPONSE SCHEMAS
# ==========================================

class ImportSummary(BaseModel):
    """
    Summary of import operation results.
    Matches the API Response Structure from requirements.
    """
    tasks_created: int = 0      # New items found in Excel
    tasks_updated: int = 0      # Existing items with new Baselines
    tasks_preserved: int = 0    # "Current" dates kept safe
    tasks_cancelled: int = 0    # Items missing from Excel (Ghost Check)
    tasks_flagged: int = 0      # Items flagged for PM review
    
    resources_synced: int = 0
    programs_synced: int = 0
    projects_synced: int = 0
    phases_synced: int = 0
    dependencies_synced: int = 0
    
    # Parsing stats
    work_items_parsed: int = 0
    resources_parsed: int = 0
    dependencies_parsed: int = 0
    
    # Recalculation stats
    recalculation_time_ms: int = 0
    critical_path_items: int = 0


class FlaggedItem(BaseModel):
    """A work item flagged for PM review."""
    external_id: str
    message: Optional[str] = None
    work_item_id: Optional[str] = None


class ImportResponse(BaseModel):
    """
    Full API response for import operation.
    
    Includes comprehensive error handling, warnings,
    flagged items, and audit information.
    """
    status: str = "success"  # "success", "partial_success", "validation_failed", "failed"
    summary: ImportSummary
    warnings: list[Any] = []  # Can be strings or dicts with details
    errors: list[Any] = []    # Can be strings or dicts with details
    
    # Flagged items requiring PM review
    flagged_items: list[dict] = []
    
    # Audit trail
    baseline_version_id: Optional[str] = None
    import_batch_id: Optional[str] = None
    
    # Performance
    execution_time_ms: int = 0
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    
    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0
    
    @property
    def has_flagged_items(self) -> bool:
        return len(self.flagged_items) > 0


# ==========================================
# EXCEL ROW SCHEMAS (For Parsing)
# ==========================================

class ExcelWorkItemRow(BaseModel):
    """
    Schema representing a single row from the Work Items sheet.
    Used during parsing before database operations.
    """
    # Hierarchy IDs
    program_id: str = Field(..., alias="Program ID")
    project_id: str = Field(..., alias="Project ID")
    phase_id: str = Field(..., alias="Phase ID")
    work_item_id: str = Field(..., alias="Work Item ID")
    
    # Names
    program_name: Optional[str] = Field(None, alias="Program Name")
    project_name: Optional[str] = Field(None, alias="Project Name")
    phase_name: Optional[str] = Field(None, alias="Phase Name")
    work_item_name: str = Field(..., alias="Work Item Name")
    
    # Dates
    planned_start: date = Field(..., alias="Planned Start")
    planned_end: date = Field(..., alias="Planned End")
    
    # Optional fields
    planned_effort: Optional[int] = Field(None, alias="Planned Effort")
    assigned_resource: Optional[str] = Field(None, alias="Assigned Resource")
    complexity: Optional[str] = Field(None, alias="Complexity Level")
    revenue_impact: Optional[Decimal] = Field(None, alias="Revenue Impact $")
    strategic_importance: Optional[str] = Field(None, alias="Strategic Importance")
    customer_impact: Optional[str] = Field(None, alias="Customer Impact")
    is_critical_launch: Optional[bool] = Field(None, alias="Critical for Launch?")
    feature_name: Optional[str] = Field(None, alias="Feature Name")
    phase_sequence: Optional[int] = Field(None, alias="Phase Sequence")
    
    class Config:
        populate_by_name = True


class ExcelResourceRow(BaseModel):
    """Schema representing a single row from the Resources sheet."""
    resource_id: str = Field(..., alias="Resource ID")
    name: str = Field(..., alias="Resource Name")
    email: str = Field(..., alias="Email")
    role: Optional[str] = Field(None, alias="Role")
    home_team: Optional[str] = Field(None, alias="Home Program/Team")
    cost_per_hour: Optional[Decimal] = Field(None, alias="Cost Per Hour")
    max_utilization: Optional[int] = Field(None, alias="Max Utilization")
    skill_level: Optional[str] = Field(None, alias="Skill Level")
    location: Optional[str] = Field(None, alias="Location")
    
    class Config:
        populate_by_name = True


class ExcelDependencyRow(BaseModel):
    """Schema representing a single row from the Dependencies sheet."""
    successor_id: str = Field(..., alias="Successor Task ID")
    predecessor_id: str = Field(..., alias="Predecessor Task ID")
    dependency_type: str = Field("FS", alias="Dependency Type")
    lag_days: int = Field(0, alias="Lag Days")
    notes: Optional[str] = Field(None, alias="Notes")
    
    class Config:
        populate_by_name = True
