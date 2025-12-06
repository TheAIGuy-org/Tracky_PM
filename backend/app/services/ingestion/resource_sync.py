"""
Resource Sync Service for Tracky PM.
Handles synchronization of resources from Excel to database.
"""
from typing import Optional
from uuid import UUID

from app.core.database import SupabaseClient, get_supabase_client
from app.core.exceptions import DatabaseError


class ResourceSyncService:
    """
    Service for synchronizing resources from Excel imports.
    
    Resources are upserted based on external_id (e.g., RES-001).
    Uses bulk operations for performance (1 DB call vs N calls).
    """
    
    def __init__(self, db_client: Optional[SupabaseClient] = None):
        """
        Initialize Resource Sync Service.
        
        Args:
            db_client: Supabase client (uses singleton if not provided)
        """
        self.db = db_client or get_supabase_client()
    
    def _prepare_resource_data(self, parsed_resource: dict) -> dict:
        """
        Prepare a single resource for database upsert.
        
        Args:
            parsed_resource: Parsed resource data from Excel
            
        Returns:
            Cleaned resource dictionary ready for DB
        """
        resource_data = {
            "external_id": parsed_resource["external_id"],
            "name": parsed_resource["name"],
            "email": parsed_resource["email"],
            "role": parsed_resource.get("role"),
            "home_team": parsed_resource.get("home_team"),
            "cost_per_hour": float(parsed_resource["cost_per_hour"]) if parsed_resource.get("cost_per_hour") else None,
            "max_utilization": parsed_resource.get("max_utilization", 100),
            "skill_level": parsed_resource.get("skill_level"),
            "location": parsed_resource.get("location"),
        }
        
        # Remove None values
        return {k: v for k, v in resource_data.items() if v is not None}
    
    def sync_resource(self, parsed_resource: dict) -> dict:
        """
        Sync a single resource to the database.
        
        Args:
            parsed_resource: Parsed resource data from Excel
            
        Returns:
            The upserted resource record
        """
        external_id = parsed_resource["external_id"]
        resource_data = self._prepare_resource_data(parsed_resource)
        
        try:
            result = self.db.upsert_resource(resource_data)
            return result
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to sync resource {external_id}",
                table="resources",
                operation="upsert",
                original_error=str(e)
            )
    
    def sync_all(self, parsed_resources: list[dict]) -> dict[str, UUID]:
        """
        Sync all resources using bulk upsert and return mapping.
        
        Performance: 1 DB call instead of N calls.
        
        Args:
            parsed_resources: List of parsed resources from Excel
            
        Returns:
            Dictionary mapping external_id to database UUID
        """
        if not parsed_resources:
            return {}
        
        # Prepare all resources for bulk upsert
        resources_to_upsert = [
            self._prepare_resource_data(resource)
            for resource in parsed_resources
        ]
        
        try:
            # Single bulk upsert call
            results = self.db.bulk_upsert_resources(resources_to_upsert)
            
            # Build mapping from results
            mapping = {}
            for result in results:
                if result.get("id") and result.get("external_id"):
                    mapping[result["external_id"]] = UUID(result["id"])
            
            return mapping
        except Exception as e:
            raise DatabaseError(
                message="Failed to bulk sync resources",
                table="resources",
                operation="bulk_upsert",
                original_error=str(e)
            )
    
    def get_resource_mapping(self) -> dict[str, UUID]:
        """
        Get mapping of all existing resources.
        
        Returns:
            Dictionary mapping external_id to database UUID
        """
        resources = self.db.get_all_resources()
        return {r["external_id"]: UUID(r["id"]) for r in resources}
    
    def bulk_sync_all(self, parsed_resources: list[dict]) -> dict[str, UUID]:
        """
        Alias for sync_all() for API consistency.
        Sync all resources using bulk upsert and return mapping.
        
        Performance: 1 DB call instead of N calls.
        
        Args:
            parsed_resources: List of parsed resources from Excel
            
        Returns:
            Dictionary mapping external_id to database UUID
        """
        return self.sync_all(parsed_resources)
    
    def get_or_create_resource_mapping(
        self,
        parsed_resources: list[dict]
    ) -> dict[str, UUID]:
        """
        Get existing resource mapping and sync any new resources.
        
        Args:
            parsed_resources: List of parsed resources from Excel
            
        Returns:
            Dictionary mapping external_id to database UUID
        """
        # Get existing mapping
        mapping = self.get_resource_mapping()
        
        # Sync resources from Excel
        for resource in parsed_resources:
            external_id = resource["external_id"]
            if external_id not in mapping:
                result = self.sync_resource(resource)
                if result and result.get("id"):
                    mapping[external_id] = UUID(result["id"])
        
        return mapping
