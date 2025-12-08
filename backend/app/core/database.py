"""
Supabase database client management.
Provides async-compatible client for database operations.

Features:
- Transaction management with rollback support
- Audit logging for compliance (SOX, GDPR, ISO)
- Baseline versioning for scope tracking
- Resource utilization checks
- Bulk operations for performance
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Any, Generator, Optional
from uuid import UUID, uuid4

from supabase import create_client, Client

from .config import settings


@dataclass
class TransactionContext:
    """
    Tracks operations within a transaction for potential rollback.
    
    Since Supabase REST API doesn't support native transactions,
    we implement application-level transaction management.
    """
    batch_id: str = field(default_factory=lambda: str(uuid4()))
    operations: list[dict] = field(default_factory=list)
    is_active: bool = True
    should_rollback: bool = False
    
    # Track created entity IDs for rollback
    created_work_items: list[str] = field(default_factory=list)
    created_phases: list[str] = field(default_factory=list)
    created_projects: list[str] = field(default_factory=list)
    created_dependencies: list[str] = field(default_factory=list)
    
    # Track updated entities for rollback (store original values)
    original_work_items: dict[str, dict] = field(default_factory=dict)
    
    def add_created(self, entity_type: str, entity_id: str) -> None:
        """Track a created entity for potential rollback."""
        if entity_type == "work_item":
            self.created_work_items.append(entity_id)
        elif entity_type == "phase":
            self.created_phases.append(entity_id)
        elif entity_type == "project":
            self.created_projects.append(entity_id)
        elif entity_type == "dependency":
            self.created_dependencies.append(entity_id)
    
    def store_original(self, entity_type: str, entity_id: str, original: dict) -> None:
        """Store original values for rollback."""
        if entity_type == "work_item":
            self.original_work_items[entity_id] = original


class SupabaseClient:
    """
    Singleton wrapper for Supabase client.
    Provides methods for common database operations.
    
    Features:
    - Transaction management with application-level rollback
    - Audit logging for all changes
    - Baseline versioning
    - Resource utilization queries
    """
    
    _instance: Optional["SupabaseClient"] = None
    _client: Optional[Client] = None
    _transaction: Optional[TransactionContext] = None
    
    def __new__(cls) -> "SupabaseClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self._client = create_client(
                settings.supabase_url,
                settings.supabase_anon_key
            )
    
    @property
    def client(self) -> Client:
        """Get the Supabase client instance."""
        if self._client is None:
            raise RuntimeError("Supabase client not initialized")
        return self._client
    
    # ==========================================
    # TRANSACTION MANAGEMENT
    # ==========================================
    
    @contextmanager
    def transaction(self) -> Generator[TransactionContext, None, None]:
        """
        Application-level transaction context manager.
        
        Since Supabase REST API doesn't support native transactions,
        we track operations and provide rollback capability.
        
        Usage:
            with db.transaction() as tx:
                # Operations here
                if error:
                    tx.should_rollback = True
        """
        self._transaction = TransactionContext()
        try:
            yield self._transaction
            
            if self._transaction.should_rollback:
                self._rollback_transaction()
        except Exception:
            self._rollback_transaction()
            raise
        finally:
            self._transaction = None
    
    def _rollback_transaction(self) -> None:
        """
        Rollback all operations in the current transaction.
        Deletes created entities and restores original values.
        """
        if not self._transaction:
            return
        
        tx = self._transaction
        
        # Delete created work items
        if tx.created_work_items:
            self.client.table("work_items").delete().in_("id", tx.created_work_items).execute()
        
        # Delete created dependencies
        if tx.created_dependencies:
            self.client.table("dependencies").delete().in_("id", tx.created_dependencies).execute()
        
        # Delete created phases
        if tx.created_phases:
            self.client.table("phases").delete().in_("id", tx.created_phases).execute()
        
        # Delete created projects
        if tx.created_projects:
            self.client.table("projects").delete().in_("id", tx.created_projects).execute()
        
        # Restore original work item values
        for entity_id, original in tx.original_work_items.items():
            self.client.table("work_items").update(original).eq("id", entity_id).execute()
    
    def get_current_batch_id(self) -> Optional[str]:
        """Get the current transaction batch ID."""
        return self._transaction.batch_id if self._transaction else None
    
    def set_current_batch_id(self, batch_id: str) -> None:
        """Set the current transaction batch ID (after creating import_batch in DB)."""
        if self._transaction:
            self._transaction.batch_id = batch_id
    
    # ==========================================
    # AUDIT LOGGING (Compliance: SOX, GDPR, ISO)
    # ==========================================
    
    def create_import_batch(
        self,
        program_id: str,
        file_name: str,
        file_hash: str,
        imported_by: str = "system:excel_import"
    ) -> dict:
        """Create a new import batch record."""
        batch_data = {
            "program_id": program_id,
            "file_name": file_name,
            "file_hash": file_hash,
            "imported_by": imported_by,
            "status": "pending"
        }
        response = self.client.table("import_batches").insert(batch_data).execute()
        return response.data[0] if response.data else {}
    
    def update_import_batch(self, batch_id: str, update_data: dict) -> dict:
        """Update import batch with results."""
        # CRIT_004: Use timezone-aware datetime
        update_data["completed_at"] = datetime.now(timezone.utc).isoformat()
        response = self.client.table("import_batches").update(update_data).eq("id", batch_id).execute()
        return response.data[0] if response.data else {}
    
    def log_audit(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        field_changed: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        change_source: str = "excel_import",
        changed_by: str = "system:excel_import",
        reason: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Log an audit entry for compliance tracking.
        
        Args:
            entity_type: 'work_item', 'phase', 'project', 'program'
            entity_id: UUID of the entity
            action: 'created', 'updated', 'cancelled', 'restored'
            field_changed: Name of field that changed (for updates)
            old_value: Previous value as string
            new_value: New value as string
            change_source: 'excel_import', 'api_update', 'manual', 'system'
            changed_by: User identifier or 'system:...'
            reason: Reason for change
            metadata: Additional context as JSON
        """
        audit_data = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "field_changed": field_changed,
            "old_value": old_value,
            "new_value": new_value,
            "change_source": change_source,
            "import_batch_id": self.get_current_batch_id(),
            "changed_by": changed_by,
            "reason": reason,
            "metadata": metadata
        }
        # Remove None values
        audit_data = {k: v for k, v in audit_data.items() if v is not None}
        
        response = self.client.table("audit_logs").insert(audit_data).execute()
        return response.data[0] if response.data else {}
    
    def bulk_log_audit(self, audit_entries: list[dict]) -> list[dict]:
        """Bulk insert multiple audit log entries."""
        if not audit_entries:
            return []
        
        # Add batch_id to all entries
        batch_id = self.get_current_batch_id()
        if batch_id:
            for entry in audit_entries:
                entry["import_batch_id"] = batch_id
        
        response = self.client.table("audit_logs").insert(audit_entries).execute()
        return response.data or []
    
    # ==========================================
    # BASELINE VERSIONING (Scope Tracking)
    # ==========================================
    
    def get_next_baseline_version(self, program_id: str) -> int:
        """Get the next baseline version number for a program."""
        response = (
            self.client.table("baseline_versions")
            .select("version_number")
            .eq("program_id", program_id)
            .order("version_number", desc=True)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]["version_number"] + 1
        return 1
    
    def create_baseline_version(
        self,
        program_id: str,
        reason: str,
        created_by: str = "system:excel_import",
        import_batch_id: Optional[str] = None
    ) -> dict:
        """
        Create a baseline version snapshot before import.
        Captures current state of all tasks in the program.
        
        Args:
            program_id: UUID of the program
            reason: Reason for creating baseline
            created_by: Who created the baseline
            import_batch_id: Optional import batch ID (if created during import)
        """
        # Get all work items for the program
        work_items = self.get_work_items_by_program(program_id)
        
        if not work_items:
            return {}
        
        # Calculate snapshot metrics
        total_tasks = len(work_items)
        total_effort = sum(wi.get("planned_effort_hours") or 0 for wi in work_items)
        
        planned_starts = [wi["planned_start"] for wi in work_items if wi.get("planned_start")]
        planned_ends = [wi["planned_end"] for wi in work_items if wi.get("planned_end")]
        
        if not planned_starts or not planned_ends:
            return {}
        
        planned_start = min(planned_starts)
        planned_end = max(planned_ends)
        
        # Calculate total days
        start_date = datetime.fromisoformat(str(planned_start).replace('Z', '+00:00')).date() if isinstance(planned_start, str) else planned_start
        end_date = datetime.fromisoformat(str(planned_end).replace('Z', '+00:00')).date() if isinstance(planned_end, str) else planned_end
        total_days = (end_date - start_date).days if start_date and end_date else 0
        
        # Create task snapshot
        task_snapshot = [
            {
                "external_id": wi["external_id"],
                "planned_start": str(wi.get("planned_start")),
                "planned_end": str(wi.get("planned_end")),
                "effort": wi.get("planned_effort_hours")
            }
            for wi in work_items
        ]
        
        version_data = {
            "program_id": program_id,
            "version_number": self.get_next_baseline_version(program_id),
            "total_tasks": total_tasks,
            "total_planned_effort_hours": total_effort,
            "planned_start_date": str(planned_start),
            "planned_end_date": str(planned_end),
            "total_planned_days": total_days,
            "reason_for_change": reason,
            "created_by": created_by,
            "task_snapshot": task_snapshot
        }
        
        # Only add import_batch_id if provided (it must exist in import_batches table)
        if import_batch_id:
            version_data["import_batch_id"] = import_batch_id
        
        response = self.client.table("baseline_versions").insert(version_data).execute()
        return response.data[0] if response.data else {}
    
    def get_baseline_versions(self, program_id: str) -> list[dict]:
        """Get all baseline versions for a program."""
        response = (
            self.client.table("baseline_versions")
            .select("*")
            .eq("program_id", program_id)
            .order("version_number", desc=True)
            .execute()
        )
        return response.data or []
    
    # ==========================================
    # RESOURCE UTILIZATION
    # ==========================================
    
    def get_resource_utilization(self, resource_id: str) -> Optional[dict]:
        """Get utilization data for a specific resource."""
        response = (
            self.client.table("resource_utilization")
            .select("*")
            .eq("id", resource_id)
            .execute()
        )
        return response.data[0] if response.data else None
    
    def get_all_resource_utilization(self) -> list[dict]:
        """Get utilization data for all resources."""
        response = self.client.table("resource_utilization").select("*").execute()
        return response.data or []
    
    def check_resource_overallocation(self, resource_ids: list[str]) -> list[dict]:
        """
        Check if any resources in the list are over-allocated.
        
        Returns list of over-allocated resources with details.
        """
        if not resource_ids:
            return []
        
        response = (
            self.client.table("resource_utilization")
            .select("*")
            .in_("id", resource_ids)
            .execute()
        )
        
        return [
            r for r in (response.data or [])
            if r.get("utilization_status") == "Over-Allocated"
        ]
    
    # ==========================================
    # CIRCULAR DEPENDENCY DETECTION
    # ==========================================
    
    def detect_circular_dependencies(self, program_id: str) -> list[dict]:
        """
        Detect circular dependencies in a program.
        Uses database function for efficiency.
        """
        response = self.client.rpc(
            "detect_circular_dependencies",
            {"p_program_id": program_id}
        ).execute()
        return response.data or []
    
    # ==========================================
    # CRITICAL PATH CALCULATION
    # ==========================================
    
    def calculate_critical_path(self, program_id: str) -> list[dict]:
        """
        Calculate critical path for all work items in a program.
        Uses database function with recursive CTE for efficiency.
        """
        response = self.client.rpc(
            "calculate_critical_path",
            {"p_program_id": program_id}
        ).execute()
        return response.data or []
    
    def update_work_item_slack(self, program_id: str) -> int:
        """
        Update slack_days and is_critical_path for all work items.
        Returns count of updated items.
        """
        response = self.client.rpc(
            "update_work_item_slack",
            {"p_program_id": program_id}
        ).execute()
        return response.data if isinstance(response.data, int) else 0
    
    # ==========================================
    # RESOURCE OPERATIONS
    # ==========================================
    
    def get_resource_by_external_id(self, external_id: str) -> Optional[dict]:
        """Fetch a resource by its external ID (e.g., 'RES-001')."""
        response = self.client.table("resources").select("*").eq("external_id", external_id).execute()
        return response.data[0] if response.data else None
    
    def get_all_resources(self) -> list[dict]:
        """Fetch all resources."""
        response = self.client.table("resources").select("*").execute()
        return response.data or []
    
    def upsert_resource(self, resource_data: dict) -> dict:
        """Insert or update a resource based on external_id."""
        response = self.client.table("resources").upsert(
            resource_data,
            on_conflict="external_id"
        ).execute()
        return response.data[0] if response.data else {}
    
    def bulk_upsert_resources(self, resources: list[dict]) -> list[dict]:
        """
        Bulk upsert multiple resources in a single database call.
        
        Args:
            resources: List of resource dictionaries
            
        Returns:
            List of upserted resource records
        """
        if not resources:
            return []
        
        response = self.client.table("resources").upsert(
            resources,
            on_conflict="external_id"
        ).execute()
        return response.data or []
    
    # ==========================================
    # PROGRAM OPERATIONS
    # ==========================================
    
    def get_program_by_external_id(self, external_id: str) -> Optional[dict]:
        """Fetch a program by its external ID (e.g., 'PROG-001')."""
        response = self.client.table("programs").select("*").eq("external_id", external_id).execute()
        return response.data[0] if response.data else None
    
    def upsert_program(self, program_data: dict) -> dict:
        """Insert or update a program based on external_id."""
        response = self.client.table("programs").upsert(
            program_data,
            on_conflict="external_id"
        ).execute()
        return response.data[0] if response.data else {}
    
    # ==========================================
    # PROJECT OPERATIONS
    # ==========================================
    
    def get_project_by_external_id(self, program_id: str, external_id: str) -> Optional[dict]:
        """Fetch a project by its external ID within a program."""
        response = (
            self.client.table("projects")
            .select("*")
            .eq("program_id", program_id)
            .eq("external_id", external_id)
            .execute()
        )
        return response.data[0] if response.data else None
    
    def get_projects_by_program(self, program_id: str) -> list[dict]:
        """Fetch all projects for a program."""
        response = self.client.table("projects").select("*").eq("program_id", program_id).execute()
        return response.data or []
    
    def upsert_project(self, project_data: dict) -> dict:
        """Insert or update a project."""
        # Projects use composite uniqueness (program_id, external_id)
        existing = self.get_project_by_external_id(
            project_data["program_id"],
            project_data["external_id"]
        )
        if existing:
            response = (
                self.client.table("projects")
                .update(project_data)
                .eq("id", existing["id"])
                .execute()
            )
        else:
            response = self.client.table("projects").insert(project_data).execute()
        return response.data[0] if response.data else {}
    
    # ==========================================
    # PHASE OPERATIONS
    # ==========================================
    
    def get_phase_by_external_id(self, project_id: str, external_id: str) -> Optional[dict]:
        """Fetch a phase by its external ID within a project."""
        response = (
            self.client.table("phases")
            .select("*")
            .eq("project_id", project_id)
            .eq("external_id", external_id)
            .execute()
        )
        return response.data[0] if response.data else None
    
    def get_phases_by_project(self, project_id: str) -> list[dict]:
        """Fetch all phases for a project."""
        response = self.client.table("phases").select("*").eq("project_id", project_id).execute()
        return response.data or []
    
    def upsert_phase(self, phase_data: dict) -> dict:
        """Insert or update a phase."""
        existing = self.get_phase_by_external_id(
            phase_data["project_id"],
            phase_data["external_id"]
        )
        if existing:
            response = (
                self.client.table("phases")
                .update(phase_data)
                .eq("id", existing["id"])
                .execute()
            )
        else:
            response = self.client.table("phases").insert(phase_data).execute()
        return response.data[0] if response.data else {}
    
    # ==========================================
    # WORK ITEM OPERATIONS (Critical for Smart Merge)
    # ==========================================
    
    def get_work_item_by_external_id(self, phase_id: str, external_id: str) -> Optional[dict]:
        """
        Fetch a work item by its external ID within a phase.
        This is the core lookup for Smart Merge.
        """
        response = (
            self.client.table("work_items")
            .select("*")
            .eq("phase_id", phase_id)
            .eq("external_id", external_id)
            .execute()
        )
        return response.data[0] if response.data else None
    
    def get_work_items_by_phase(self, phase_id: str) -> list[dict]:
        """Fetch all work items for a phase."""
        response = self.client.table("work_items").select("*").eq("phase_id", phase_id).execute()
        return response.data or []
    
    def get_work_items_by_program(self, program_id: str) -> list[dict]:
        """
        Fetch all work items for an entire program.
        Used for Ghost Check (finding items to cancel).
        """
        response = (
            self.client.table("work_items")
            .select("*, phases!inner(*, projects!inner(program_id))")
            .eq("phases.projects.program_id", program_id)
            .execute()
        )
        return response.data or []
    
    def insert_work_item(self, work_item_data: dict) -> dict:
        """Insert a new work item (Case A: New Task)."""
        response = self.client.table("work_items").insert(work_item_data).execute()
        return response.data[0] if response.data else {}
    
    def bulk_insert_work_items(self, work_items: list[dict]) -> list[dict]:
        """
        Bulk insert multiple work items in a single database call.
        
        Args:
            work_items: List of work item dictionaries
            
        Returns:
            List of inserted work item records
        """
        if not work_items:
            return []
        
        response = self.client.table("work_items").insert(work_items).execute()
        return response.data or []
    
    def bulk_update_work_items(self, updates: list[dict]) -> list[dict]:
        """
        Bulk update multiple work items.
        Each update dict must include 'id' field.
        
        Note: Supabase upsert with partial data doesn't work as expected,
        so we use individual UPDATE operations.
        
        Args:
            updates: List of update dictionaries with 'id' field
            
        Returns:
            List of updated work item records
        """
        if not updates:
            return []
        
        results = []
        for update_data in updates:
            item_id = update_data.pop("id", None)
            if not item_id or not update_data:
                continue
            
            # Add updated_at timestamp
            update_data["updated_at"] = "now()"
            
            response = self.client.table("work_items").update(
                update_data
            ).eq("id", item_id).execute()
            
            if response.data:
                results.extend(response.data)
        
        return results
    
    def update_work_item_baseline(self, work_item_id: str, baseline_data: dict) -> dict:
        """
        Update ONLY the baseline/plan fields of a work item.
        PRESERVES: current_start, current_end, status, completion_percent, actual_start/end
        This is the core of Smart Merge (Case B).
        """
        # Whitelist only the fields that should be updated from Excel
        allowed_fields = {
            "planned_start",
            "planned_end",
            "planned_effort_hours",
            "allocation_percent",
            "revenue_impact",
            "strategic_importance",
            "customer_impact",
            "is_critical_launch",
            "feature_name",
            "complexity",
            "name",  # Task name can be updated
            "resource_id",  # Resource assignment can change
        }
        
        # Filter to only allowed fields
        safe_update = {k: v for k, v in baseline_data.items() if k in allowed_fields}
        
        if not safe_update:
            return {}
        
        response = (
            self.client.table("work_items")
            .update(safe_update)
            .eq("id", work_item_id)
            .execute()
        )
        return response.data[0] if response.data else {}
    
    def cancel_work_item(
        self,
        work_item_id: str,
        reason: str = "Removed from updated plan"
    ) -> dict:
        """
        Soft delete a work item by setting status to 'Cancelled'.
        Used for Ghost Check when item is missing from Excel.
        """
        response = (
            self.client.table("work_items")
            .update({
                "status": "Cancelled",
                "cancellation_reason": reason
            })
            .eq("id", work_item_id)
            .execute()
        )
        return response.data[0] if response.data else {}
    
    def bulk_cancel_work_items(
        self,
        work_item_ids: list[str],
        reason: str = "Removed from updated plan"
    ) -> int:
        """Cancel multiple work items. Returns count of cancelled items."""
        if not work_item_ids:
            return 0
        
        response = (
            self.client.table("work_items")
            .update({
                "status": "Cancelled",
                "cancellation_reason": reason
            })
            .in_("id", work_item_ids)
            .execute()
        )
        return len(response.data) if response.data else 0
    
    def flag_work_item_for_review(
        self,
        work_item_id: str,
        review_message: str
    ) -> dict:
        """
        Flag a work item for PM review instead of auto-cancelling.
        Used when in-progress work is removed from Excel.
        """
        response = (
            self.client.table("work_items")
            .update({
                "status": "On Hold",
                "flag_for_review": True,
                "review_message": review_message
            })
            .eq("id", work_item_id)
            .execute()
        )
        return response.data[0] if response.data else {}
    
    def bulk_flag_for_review(
        self,
        items: list[dict]  # List of {id, review_message}
    ) -> int:
        """
        Bulk flag multiple work items for review.
        
        Args:
            items: List of dicts with 'id' and 'review_message' keys
            
        Returns:
            Count of flagged items
        """
        if not items:
            return 0
        
        count = 0
        for item in items:
            self.flag_work_item_for_review(
                item["id"],
                item["review_message"]
            )
            count += 1
        return count
    
    def get_flagged_work_items(self, program_id: str) -> list[dict]:
        """Get all work items flagged for review in a program."""
        response = (
            self.client.table("work_items")
            .select("*, phases!inner(*, projects!inner(program_id))")
            .eq("phases.projects.program_id", program_id)
            .eq("flag_for_review", True)
            .execute()
        )
        return response.data or []
    
    def resolve_flagged_item(
        self,
        work_item_id: str,
        new_status: str,
        resolution_note: str
    ) -> dict:
        """
        Resolve a flagged work item after PM review.
        
        Args:
            work_item_id: UUID of the work item
            new_status: New status ('Cancelled', 'In Progress', etc.)
            resolution_note: Note explaining the resolution
        """
        response = (
            self.client.table("work_items")
            .update({
                "status": new_status,
                "flag_for_review": False,
                "review_message": resolution_note
            })
            .eq("id", work_item_id)
            .execute()
        )
        return response.data[0] if response.data else {}
    
    # ==========================================
    # DEPENDENCY OPERATIONS
    # ==========================================
    
    def get_dependencies_for_work_item(self, work_item_id: str) -> list[dict]:
        """Fetch all dependencies where this work item is the successor."""
        response = (
            self.client.table("dependencies")
            .select("*")
            .eq("successor_item_id", work_item_id)
            .execute()
        )
        return response.data or []
    
    def upsert_dependency(self, dependency_data: dict) -> dict:
        """Insert or update a dependency."""
        response = self.client.table("dependencies").upsert(
            dependency_data,
            on_conflict="successor_item_id,predecessor_item_id"
        ).execute()
        return response.data[0] if response.data else {}
    
    def bulk_upsert_dependencies(self, dependencies: list[dict]) -> list[dict]:
        """
        Bulk upsert multiple dependencies in a single database call.
        
        Args:
            dependencies: List of dependency dictionaries
            
        Returns:
            List of upserted dependency records
        """
        if not dependencies:
            return []
        
        response = self.client.table("dependencies").upsert(
            dependencies,
            on_conflict="successor_item_id,predecessor_item_id"
        ).execute()
        return response.data or []
    
    def delete_dependency(self, successor_id: str, predecessor_id: str) -> bool:
        """Delete a specific dependency."""
        response = (
            self.client.table("dependencies")
            .delete()
            .eq("successor_item_id", successor_id)
            .eq("predecessor_item_id", predecessor_id)
            .execute()
        )
        return bool(response.data)


@lru_cache
def get_supabase_client() -> SupabaseClient:
    """Get the singleton Supabase client instance."""
    return SupabaseClient()
