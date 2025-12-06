"""
Smart Merge Engine for Tracky PM.

Core Philosophy: "The Excel File updates the Plan, but the System preserves the Truth."

This is the heart of the import process. It implements:
- Case A: INSERT new tasks (baseline = current = excel dates)
- Case B: UPDATE existing tasks (only baseline fields, preserve current/actual)
- Ghost Check: Context-aware soft delete (Not Started → Cancel, In Progress → Flag, Completed → Preserve)

Performance: Uses bulk operations (2 DB calls for 5000 tasks instead of 5000 calls)
Compliance: Full audit logging for SOX/GDPR/ISO compliance
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Any
from uuid import UUID

from app.core.database import SupabaseClient, get_supabase_client
from app.core.exceptions import DatabaseError, MergeConflictError
from app.models.enums import WorkStatus


@dataclass
class MergeResult:
    """
    Result of a single work item merge operation.
    Tracks what action was taken and preserves audit info.
    """
    external_id: str
    action: str  # "created", "updated", "preserved", "cancelled", "flagged", "skipped"
    work_item_id: Optional[UUID] = None
    
    # For updates, track what changed
    fields_updated: list[str] = field(default_factory=list)
    old_values: dict[str, Any] = field(default_factory=dict)  # For audit trail
    new_values: dict[str, Any] = field(default_factory=dict)  # For audit trail
    
    # For conflict detection
    baseline_changed: bool = False
    current_preserved: bool = False
    
    # Warnings (e.g., baseline now after current)
    warnings: list[str] = field(default_factory=list)
    
    # For flagged items
    flag_message: Optional[str] = None


@dataclass
class MergeSummary:
    """Summary of all merge operations in an import."""
    tasks_created: int = 0
    tasks_updated: int = 0
    tasks_preserved: int = 0
    tasks_cancelled: int = 0
    tasks_flagged: int = 0  # Items flagged for PM review
    
    results: list[MergeResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)  # Detailed error info
    
    # Audit trail references
    audit_entries: list[dict] = field(default_factory=list)
    
    def add_result(self, result: MergeResult) -> None:
        """Add a merge result and update counts."""
        self.results.append(result)
        
        if result.action == "created":
            self.tasks_created += 1
        elif result.action == "updated":
            self.tasks_updated += 1
            if result.current_preserved:
                self.tasks_preserved += 1
        elif result.action == "preserved":
            # Item existed and had no changes (same values as Excel)
            self.tasks_preserved += 1
        elif result.action == "cancelled":
            self.tasks_cancelled += 1
        elif result.action == "flagged":
            self.tasks_flagged += 1
        
        # Collect warnings
        self.warnings.extend(result.warnings)
    
    def add_error(self, row_num: int, field_name: str, value: Any, message: str) -> None:
        """Add a detailed error entry."""
        self.errors.append({
            "row": row_num,
            "field": field_name,
            "value": value,
            "message": message
        })
    
    def add_bulk_created(self, count: int, external_ids: list[str]) -> None:
        """Add results for bulk-created items."""
        for ext_id in external_ids:
            self.results.append(MergeResult(
                external_id=ext_id,
                action="created",
            ))
        self.tasks_created += count
    
    def add_bulk_updated(self, results: list[MergeResult]) -> None:
        """Add results for bulk-updated items."""
        for result in results:
            self.results.append(result)
            self.tasks_updated += 1
            if result.current_preserved:
                self.tasks_preserved += 1
            self.warnings.extend(result.warnings)


class SmartMergeEngine:
    """
    The Smart Merge Engine implements the core import logic.
    
    Key Principles:
    1. New tasks: Insert with current = planned (baseline)
    2. Existing tasks: Update ONLY baseline fields, PRESERVE current/actual
    3. Missing tasks: Context-aware soft delete
       - Not Started → Cancelled
       - In Progress → Flagged for PM review
       - Completed → Preserved with note
    4. After merge: Trigger recalculation if baseline > current
    
    Compliance: All changes logged to audit_logs table
    """
    
    # Fields that can be updated from Excel (the "Plan")
    BASELINE_FIELDS = {
        "name",
        "planned_start",
        "planned_end",
        "planned_effort_hours",
        "allocation_percent",
        "resource_id",
        "complexity",
        "revenue_impact",
        "strategic_importance",
        "customer_impact",
        "is_critical_launch",
        "feature_name",
    }
    
    # Fields that are NEVER updated from Excel (the "Reality")
    PRESERVED_FIELDS = {
        "current_start",
        "current_end",
        "actual_start",
        "actual_end",
        "status",
        "completion_percent",
        "slack_days",
    }
    
    def __init__(self, db_client: Optional[SupabaseClient] = None):
        """
        Initialize the Smart Merge Engine.
        
        Args:
            db_client: Supabase client (uses singleton if not provided)
        """
        self.db = db_client or get_supabase_client()
        
        # Bulk operation buffers
        self._to_insert: list[dict] = []
        self._to_update: list[dict] = []
        self._insert_external_ids: list[str] = []
        self._update_results: list[MergeResult] = []
        
        # Audit log buffer
        self._audit_entries: list[dict] = []
    
    def _reset_buffers(self) -> None:
        """Reset bulk operation buffers."""
        self._to_insert = []
        self._to_update = []
        self._insert_external_ids = []
        self._update_results = []
        self._audit_entries = []
    
    def _prepare_insert_data(
        self,
        parsed_item: dict,
        phase_uuid: UUID,
        resource_uuid: Optional[UUID]
    ) -> dict:
        """
        Prepare insert data for a new work item.
        
        Case A: New Task - baseline = current = excel dates
        """
        insert_data = {
            "phase_id": str(phase_uuid),
            "external_id": parsed_item["external_id"],
            "name": parsed_item["name"],
            
            # Baseline from Excel
            "planned_start": str(parsed_item["planned_start"]),
            "planned_end": str(parsed_item["planned_end"]),
            "planned_effort_hours": parsed_item.get("planned_effort_hours"),
            "allocation_percent": parsed_item.get("allocation_percent", 100),
            
            # Current = Baseline for new items
            "current_start": str(parsed_item["planned_start"]),
            "current_end": str(parsed_item["planned_end"]),
            
            # Initial status
            "status": WorkStatus.NOT_STARTED.value,
            "completion_percent": 0,
            
            # Resource assignment
            "resource_id": str(resource_uuid) if resource_uuid else None,
            
            # Risk & metadata
            "complexity": parsed_item.get("complexity"),
            "revenue_impact": float(parsed_item["revenue_impact"]) if parsed_item.get("revenue_impact") else None,
            "strategic_importance": parsed_item.get("strategic_importance"),
            "customer_impact": parsed_item.get("customer_impact"),
            "is_critical_launch": parsed_item.get("is_critical_launch", False),
            "feature_name": parsed_item.get("feature_name"),
        }
        
        # Remove None values to let DB defaults apply
        return {k: v for k, v in insert_data.items() if v is not None}
    
    def _prepare_update_data(
        self,
        parsed_item: dict,
        existing: dict,
        resource_uuid: Optional[UUID]
    ) -> tuple[dict, MergeResult]:
        """
        Prepare update data for an existing work item.
        
        Case B: Update ONLY baseline fields, PRESERVE current/actual
        
        Returns:
            Tuple of (update_data_dict, MergeResult)
        """
        external_id = parsed_item["external_id"]
        work_item_id = existing["id"]
        
        result = MergeResult(
            external_id=external_id,
            action="updated",
            work_item_id=UUID(work_item_id),
            current_preserved=True,
        )
        
        # Start with the ID for upsert
        update_data = {"id": work_item_id}
        
        # Check each baseline field for changes
        if parsed_item["name"] != existing.get("name"):
            update_data["name"] = parsed_item["name"]
            result.fields_updated.append("name")
            result.old_values["name"] = existing.get("name")
            result.new_values["name"] = parsed_item["name"]
        
        # Date comparisons
        new_planned_start = parsed_item["planned_start"]
        new_planned_end = parsed_item["planned_end"]
        
        existing_planned_start = self._parse_db_date(existing.get("planned_start"))
        existing_planned_end = self._parse_db_date(existing.get("planned_end"))
        
        if new_planned_start != existing_planned_start:
            update_data["planned_start"] = str(new_planned_start)
            result.fields_updated.append("planned_start")
            result.baseline_changed = True
            result.old_values["planned_start"] = str(existing_planned_start) if existing_planned_start else None
            result.new_values["planned_start"] = str(new_planned_start)
        
        if new_planned_end != existing_planned_end:
            update_data["planned_end"] = str(new_planned_end)
            result.fields_updated.append("planned_end")
            result.baseline_changed = True
            result.old_values["planned_end"] = str(existing_planned_end) if existing_planned_end else None
            result.new_values["planned_end"] = str(new_planned_end)
        
        # Other baseline fields
        baseline_mappings = [
            ("planned_effort_hours", "planned_effort_hours"),
            ("allocation_percent", "allocation_percent"),
            ("complexity", "complexity"),
            ("revenue_impact", "revenue_impact"),
            ("strategic_importance", "strategic_importance"),
            ("customer_impact", "customer_impact"),
            ("is_critical_launch", "is_critical_launch"),
            ("feature_name", "feature_name"),
        ]
        
        for parsed_key, db_key in baseline_mappings:
            new_value = parsed_item.get(parsed_key)
            existing_value = existing.get(db_key)
            
            # Handle Decimal conversion for revenue_impact
            if parsed_key == "revenue_impact" and new_value is not None:
                new_value = float(new_value)
                if existing_value is not None:
                    existing_value = float(existing_value)
            
            if new_value != existing_value:
                update_data[db_key] = new_value
                result.fields_updated.append(db_key)
                result.old_values[db_key] = existing_value
                result.new_values[db_key] = new_value
        
        # Resource assignment
        if resource_uuid:
            new_resource = str(resource_uuid)
            existing_resource = existing.get("resource_id")
            if new_resource != existing_resource:
                update_data["resource_id"] = new_resource
                result.fields_updated.append("resource_id")
                result.old_values["resource_id"] = existing_resource
                result.new_values["resource_id"] = new_resource
        
        # Check for Logic Conflict warnings (Baseline > Current)
        current_start = self._parse_db_date(existing.get("current_start"))
        current_end = self._parse_db_date(existing.get("current_end"))
        
        if current_start and new_planned_start > current_start:
            result.warnings.append(
                f"Task {external_id}: New baseline start ({new_planned_start}) "
                f"is later than current forecast ({current_start}). "
                f"Recalculation will adjust current dates."
            )
        
        if current_end and new_planned_end > current_end:
            result.warnings.append(
                f"Task {external_id}: New baseline end ({new_planned_end}) "
                f"is later than current end ({current_end}). "
                f"Recalculation will adjust current dates."
            )
        
        # If no changes beyond ID, mark as preserved
        if len(update_data) <= 1:
            result.action = "preserved"
        
        return update_data, result
    
    def _create_audit_entry(
        self,
        entity_id: str,
        action: str,
        field_changed: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        reason: Optional[str] = None
    ) -> dict:
        """Create an audit log entry dictionary."""
        return {
            "entity_type": "work_item",
            "entity_id": entity_id,
            "action": action,
            "field_changed": field_changed,
            "old_value": str(old_value) if old_value is not None else None,
            "new_value": str(new_value) if new_value is not None else None,
            "change_source": "excel_import",
            "changed_by": "system:excel_import",
            "reason": reason or "Excel import - Smart Merge"
        }
    
    def _parse_db_date(self, date_value: Any) -> Optional[date]:
        """Parse a date from database (handles string or date types)."""
        if date_value is None:
            return None
        if isinstance(date_value, date):
            return date_value
        if isinstance(date_value, str):
            # Handle ISO format with potential timezone
            date_str = date_value.split("T")[0]
            return date.fromisoformat(date_str)
        return None
    
    def _flush_bulk_operations(self, summary: MergeSummary) -> None:
        """
        Execute all pending bulk insert/update operations.
        
        Performance: 2 DB calls instead of N calls.
        """
        # Bulk INSERT new items
        if self._to_insert:
            try:
                inserted = self.db.bulk_insert_work_items(self._to_insert)
                summary.add_bulk_created(len(self._to_insert), self._insert_external_ids)
                
                # Create audit entries for new items
                for item in inserted:
                    self._audit_entries.append(
                        self._create_audit_entry(
                            entity_id=item.get("id", ""),
                            action="created",
                            reason="New task from Excel import"
                        )
                    )
            except Exception as e:
                raise DatabaseError(
                    message="Failed to bulk insert work items",
                    table="work_items",
                    operation="bulk_insert",
                    original_error=str(e)
                )
        
        # Bulk UPDATE existing items (only those with actual changes)
        updates_with_changes = [u for u in self._to_update if len(u) > 1]
        if updates_with_changes:
            try:
                self.db.bulk_update_work_items(updates_with_changes)
            except Exception as e:
                raise DatabaseError(
                    message="Failed to bulk update work items",
                    table="work_items",
                    operation="bulk_update",
                    original_error=str(e)
                )
        
        # Add update results to summary and create audit entries
        for result in self._update_results:
            summary.add_result(result)
            
            # Create audit entries for each changed field
            if result.action == "updated" and result.fields_updated:
                for field_name in result.fields_updated:
                    self._audit_entries.append(
                        self._create_audit_entry(
                            entity_id=str(result.work_item_id),
                            action="updated",
                            field_changed=field_name,
                            old_value=result.old_values.get(field_name),
                            new_value=result.new_values.get(field_name),
                            reason="Baseline updated from Excel import"
                        )
                    )
        
        # Bulk insert audit entries
        if self._audit_entries:
            try:
                self.db.bulk_log_audit(self._audit_entries)
            except Exception as e:
                # Don't fail the import for audit log issues, but log warning
                summary.warnings.append(f"Failed to write audit log: {str(e)}")
        
        summary.audit_entries = self._audit_entries.copy()
    
    def ghost_check(
        self,
        program_id: UUID,
        excel_external_ids: set[str]
    ) -> list[MergeResult]:
        """
        Step 3.3: The "Ghost" Check with Context-Aware Soft Delete
        
        Find tasks that exist in DB but are missing from the new Excel file.
        Apply context-aware deletion:
        - Not Started → Cancelled (safe to remove)
        - In Progress → Flagged for PM review (don't auto-cancel work in progress)
        - Completed → Preserved with note (never delete completed work)
        
        Args:
            program_id: UUID of the program being imported
            excel_external_ids: Set of external IDs present in Excel
            
        Returns:
            List of MergeResults for cancelled/flagged items
        """
        results = []
        
        # Get all work items for this program
        db_items = self.db.get_work_items_by_program(str(program_id))
        
        # Classify items missing from Excel by their status
        to_cancel: list[dict] = []      # Not Started → Can cancel
        to_flag: list[dict] = []         # In Progress → Flag for review
        to_preserve: list[dict] = []     # Completed → Preserve
        
        for item in db_items:
            external_id = item["external_id"]
            status = item.get("status")
            
            # Skip already cancelled items
            if status == WorkStatus.CANCELLED.value:
                continue
            
            # Skip items that ARE in Excel (not ghosts)
            if external_id in excel_external_ids:
                continue
            
            # Context-aware classification
            if status == WorkStatus.NOT_STARTED.value:
                # Safe to cancel
                to_cancel.append({
                    "id": item["id"],
                    "external_id": external_id,
                })
            elif status in (WorkStatus.IN_PROGRESS.value, WorkStatus.ON_HOLD.value):
                # Flag for review - don't auto-cancel work in progress
                completion = item.get("completion_percent", 0)
                to_flag.append({
                    "id": item["id"],
                    "external_id": external_id,
                    "status": status,
                    "completion_percent": completion,
                    "review_message": (
                        f"Task {external_id} was removed from Excel but is {completion}% complete "
                        f"(status: {status}). Requires PM decision to cancel or continue."
                    )
                })
            elif status == WorkStatus.COMPLETED.value:
                # Preserve completed work
                to_preserve.append({
                    "id": item["id"],
                    "external_id": external_id,
                })
        
        # Bulk cancel Not Started items
        if to_cancel:
            cancel_ids = [g["id"] for g in to_cancel]
            try:
                self.db.bulk_cancel_work_items(
                    cancel_ids,
                    reason="Removed from updated plan (was Not Started)"
                )
                
                for ghost in to_cancel:
                    results.append(MergeResult(
                        external_id=ghost["external_id"],
                        action="cancelled",
                        work_item_id=UUID(ghost["id"]),
                        warnings=[
                            f"Task {ghost['external_id']} was removed from Excel "
                            f"and has been cancelled (was Not Started)."
                        ]
                    ))
                    
                    # Audit entry for cancellation
                    self._audit_entries.append(
                        self._create_audit_entry(
                            entity_id=ghost["id"],
                            action="cancelled",
                            field_changed="status",
                            old_value="Not Started",
                            new_value="Cancelled",
                            reason="Removed from updated plan"
                        )
                    )
            except Exception as e:
                raise DatabaseError(
                    message="Failed to bulk cancel ghost items",
                    table="work_items",
                    operation="bulk_update",
                    original_error=str(e)
                )
        
        # Flag In Progress items for review (don't auto-cancel)
        if to_flag:
            try:
                self.db.bulk_flag_for_review(to_flag)
                
                for item in to_flag:
                    results.append(MergeResult(
                        external_id=item["external_id"],
                        action="flagged",
                        work_item_id=UUID(item["id"]),
                        flag_message=item["review_message"],
                        warnings=[
                            f"⚠️ REQUIRES REVIEW: {item['review_message']}"
                        ]
                    ))
                    
                    # Audit entry for flagging
                    self._audit_entries.append(
                        self._create_audit_entry(
                            entity_id=item["id"],
                            action="flagged",
                            field_changed="flag_for_review",
                            old_value="false",
                            new_value="true",
                            reason=item["review_message"]
                        )
                    )
            except Exception as e:
                raise DatabaseError(
                    message="Failed to flag items for review",
                    table="work_items",
                    operation="bulk_update",
                    original_error=str(e)
                )
        
        # Preserve completed items (just note, no status change)
        for item in to_preserve:
            results.append(MergeResult(
                external_id=item["external_id"],
                action="preserved",
                work_item_id=UUID(item["id"]),
                warnings=[
                    f"Task {item['external_id']} was removed from Excel but preserved "
                    f"(status: Completed). Historical data retained."
                ]
            ))
        
        return results
    
    def merge_all(
        self,
        parsed_items: list[dict],
        phase_mapping: dict[str, UUID],
        resource_mapping: dict[str, UUID],
        program_id: UUID,
        perform_ghost_check: bool = True
    ) -> MergeSummary:
        """
        Merge all work items from a parsed Excel file using bulk operations.
        
        Performance: 2-3 DB calls for N items instead of N calls.
        Compliance: Full audit logging for all changes.
        
        Args:
            parsed_items: List of parsed work items from Excel
            phase_mapping: Dict mapping phase external_id to UUID
            resource_mapping: Dict mapping resource external_id to UUID
            program_id: UUID of the program being imported
            perform_ghost_check: Whether to cancel missing items
            
        Returns:
            MergeSummary with all results
        """
        summary = MergeSummary()
        excel_external_ids = set()
        
        # Reset bulk operation buffers
        self._reset_buffers()
        
        # Build a cache of existing work items for faster lookups
        existing_items_cache = {}
        for phase_ext_id, phase_uuid in phase_mapping.items():
            items = self.db.get_work_items_by_phase(str(phase_uuid))
            for item in items:
                key = (str(phase_uuid), item["external_id"])
                existing_items_cache[key] = item
        
        # First pass: Classify items as INSERT or UPDATE
        for item in parsed_items:
            external_id = item["external_id"]
            excel_external_ids.add(external_id)
            
            # Get phase UUID
            phase_external_id = item["phase_id"]
            phase_uuid = phase_mapping.get(phase_external_id)
            
            if not phase_uuid:
                summary.warnings.append(
                    f"Skipped {external_id}: Phase {phase_external_id} not found"
                )
                continue
            
            # Get resource UUID (if assigned)
            resource_uuid = None
            resource_external_id = item.get("assigned_resource")
            if resource_external_id:
                resource_uuid = resource_mapping.get(resource_external_id)
                if not resource_uuid:
                    summary.warnings.append(
                        f"Task {external_id}: Resource {resource_external_id} not found, "
                        f"assignment skipped"
                    )
            
            # Check if item exists (using cache)
            cache_key = (str(phase_uuid), external_id)
            existing = existing_items_cache.get(cache_key)
            
            if existing is None:
                # Case A: New Task - prepare for bulk insert
                insert_data = self._prepare_insert_data(item, phase_uuid, resource_uuid)
                self._to_insert.append(insert_data)
                self._insert_external_ids.append(external_id)
            else:
                # Case B: Existing Task - prepare for bulk update
                update_data, result = self._prepare_update_data(item, existing, resource_uuid)
                self._to_update.append(update_data)
                self._update_results.append(result)
        
        # Execute bulk operations
        self._flush_bulk_operations(summary)
        
        # Step 3.3: Ghost Check with context-aware soft delete
        if perform_ghost_check:
            ghost_results = self.ghost_check(program_id, excel_external_ids)
            for result in ghost_results:
                summary.add_result(result)
        
        return summary
    
    def handle_baseline_current_conflict(
        self,
        work_item_id: UUID,
        new_baseline_start: date,
        new_baseline_end: date,
        existing: dict
    ) -> dict:
        """
        Handle conflict when new baseline > current dates.
        
        Rule: If new baseline is later than current, push current forward.
        The recalculation engine will handle cascading to dependents.
        
        Args:
            work_item_id: UUID of the work item
            new_baseline_start: New planned start from Excel
            new_baseline_end: New planned end from Excel
            existing: Current work item data
            
        Returns:
            Dict with current date adjustments (if any)
        """
        adjustments = {}
        
        current_start = self._parse_db_date(existing.get("current_start"))
        current_end = self._parse_db_date(existing.get("current_end"))
        
        # Only push forward if task hasn't started (actual_start is None)
        actual_start = existing.get("actual_start")
        
        if actual_start is None:
            # Task hasn't started - safe to push current dates forward
            if current_start and new_baseline_start > current_start:
                adjustments["current_start"] = str(new_baseline_start)
            
            if current_end and new_baseline_end > current_end:
                adjustments["current_end"] = str(new_baseline_end)
        else:
            # Task has started - only push end date if baseline extends beyond current
            if current_end and new_baseline_end > current_end:
                adjustments["current_end"] = str(new_baseline_end)
        
        return adjustments
