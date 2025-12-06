"""
Dependency Sync Service for Tracky PM.
Handles synchronization of task dependencies from Excel.
"""
from typing import Optional
from uuid import UUID

from app.core.database import SupabaseClient, get_supabase_client
from app.core.exceptions import DatabaseError, ResourceNotFoundError
from app.models.enums import DependencyType


class DependencySyncService:
    """
    Service for synchronizing task dependencies.
    
    Dependencies link tasks via:
    - Successor (the task that depends)
    - Predecessor (the prerequisite task)
    - Type: FS, SS, FF, SF
    - Lag: days offset
    """
    
    def __init__(self, db_client: Optional[SupabaseClient] = None):
        """
        Initialize Dependency Sync Service.
        
        Args:
            db_client: Supabase client (uses singleton if not provided)
        """
        self.db = db_client or get_supabase_client()
    
    def sync_dependency(
        self,
        successor_uuid: UUID,
        predecessor_uuid: UUID,
        dependency_type: str = "FS",
        lag_days: int = 0,
        notes: Optional[str] = None
    ) -> dict:
        """
        Sync a single dependency.
        
        Args:
            successor_uuid: UUID of the successor task
            predecessor_uuid: UUID of the predecessor task
            dependency_type: Type of dependency (FS, SS, FF, SF)
            lag_days: Lag days (offset)
            notes: Optional notes
            
        Returns:
            The upserted dependency record
        """
        dependency_data = {
            "successor_item_id": str(successor_uuid),
            "predecessor_item_id": str(predecessor_uuid),
            "dependency_type": dependency_type,
            "lag_days": lag_days,
        }
        
        if notes:
            dependency_data["notes"] = notes
        
        try:
            result = self.db.upsert_dependency(dependency_data)
            return result
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to sync dependency",
                table="dependencies",
                operation="upsert",
                original_error=str(e)
            )
    
    def sync_all(
        self,
        parsed_dependencies: list[dict],
        work_item_mapping: dict[str, UUID]
    ) -> tuple[int, list[str]]:
        """
        Sync all dependencies using bulk upsert.
        
        Performance: 1 DB call instead of N calls.
        
        Args:
            parsed_dependencies: List of parsed dependencies
            work_item_mapping: Dict mapping work item external_id to UUID
            
        Returns:
            Tuple of (synced_count, warnings)
        """
        warnings = []
        dependencies_to_upsert = []
        
        # Prepare all valid dependencies
        for dep in parsed_dependencies:
            successor_ext_id = dep["successor_external_id"]
            predecessor_ext_id = dep["predecessor_external_id"]
            
            # Lookup UUIDs
            successor_uuid = work_item_mapping.get(successor_ext_id)
            predecessor_uuid = work_item_mapping.get(predecessor_ext_id)
            
            if not successor_uuid:
                warnings.append(
                    f"Dependency skipped: Successor task {successor_ext_id} not found"
                )
                continue
            
            if not predecessor_uuid:
                warnings.append(
                    f"Dependency skipped: Predecessor task {predecessor_ext_id} not found"
                )
                continue
            
            # Prepare dependency data for bulk upsert
            dependency_data = {
                "successor_item_id": str(successor_uuid),
                "predecessor_item_id": str(predecessor_uuid),
                "dependency_type": dep.get("dependency_type", "FS"),
                "lag_days": dep.get("lag_days", 0),
            }
            
            if dep.get("notes"):
                dependency_data["notes"] = dep["notes"]
            
            dependencies_to_upsert.append(dependency_data)
        
        # Bulk upsert all dependencies in single call
        if dependencies_to_upsert:
            try:
                results = self.db.bulk_upsert_dependencies(dependencies_to_upsert)
                synced_count = len(results)
            except Exception as e:
                raise DatabaseError(
                    message="Failed to bulk sync dependencies",
                    table="dependencies",
                    operation="bulk_upsert",
                    original_error=str(e)
                )
        else:
            synced_count = 0
        
        return synced_count, warnings
    
    def build_work_item_mapping(
        self,
        parsed_work_items: list[dict],
        phase_mapping: dict[str, UUID]
    ) -> dict[str, UUID]:
        """
        Build a mapping of work item external IDs to UUIDs.
        
        This queries the database after work items have been synced.
        
        Args:
            parsed_work_items: List of parsed work items
            phase_mapping: Dict mapping phase external_id to UUID
            
        Returns:
            Dict mapping work item external_id to UUID
        """
        mapping = {}
        
        for item in parsed_work_items:
            external_id = item["external_id"]
            phase_id = item["phase_id"]
            
            phase_uuid = phase_mapping.get(phase_id)
            if not phase_uuid:
                continue
            
            # Lookup the work item in database
            db_item = self.db.get_work_item_by_external_id(
                str(phase_uuid),
                external_id
            )
            
            if db_item:
                mapping[external_id] = UUID(db_item["id"])
        
        return mapping
