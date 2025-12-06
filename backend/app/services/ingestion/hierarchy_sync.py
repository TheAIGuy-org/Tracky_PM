"""
Hierarchy Sync Service for Tracky PM.
Handles synchronization of Programs, Projects, and Phases from Excel.
"""
from datetime import date
from typing import Optional, Any
from uuid import UUID

from app.core.database import SupabaseClient, get_supabase_client
from app.core.exceptions import DatabaseError


class HierarchySyncService:
    """
    Service for synchronizing the project hierarchy.
    
    Hierarchy: Program > Project > Phase
    
    Each level is synced based on external_id:
    - Programs: PROG-XXX
    - Projects: PROJ-XXX (unique within program)
    - Phases: PHASE-XXX (unique within project)
    """
    
    def __init__(self, db_client: Optional[SupabaseClient] = None):
        """
        Initialize Hierarchy Sync Service.
        
        Args:
            db_client: Supabase client (uses singleton if not provided)
        """
        self.db = db_client or get_supabase_client()
        
        # Caches for efficient lookups
        self._program_cache: dict[str, UUID] = {}
        self._project_cache: dict[str, UUID] = {}  # Key: "program_id:project_id"
        self._phase_cache: dict[str, UUID] = {}    # Key: "project_uuid:phase_id"
    
    # ==========================================
    # PROGRAM OPERATIONS
    # ==========================================
    
    def sync_program(
        self,
        external_id: str,
        name: Optional[str] = None,
        baseline_start: Optional[date] = None,
        baseline_end: Optional[date] = None,
        **kwargs: Any
    ) -> UUID:
        """
        Sync a program to the database.
        
        Args:
            external_id: Program external ID (e.g., PROG-001)
            name: Program name
            baseline_start: Program start date
            baseline_end: Program end date
            **kwargs: Additional program fields
            
        Returns:
            UUID of the program
        """
        # Check cache first
        if external_id in self._program_cache:
            return self._program_cache[external_id]
        
        # Check database
        existing = self.db.get_program_by_external_id(external_id)
        
        if existing:
            self._program_cache[external_id] = UUID(existing["id"])
            return self._program_cache[external_id]
        
        # Create new program
        program_data = {
            "external_id": external_id,
            "name": name or external_id,
            "baseline_start_date": str(baseline_start) if baseline_start else str(date.today()),
            "baseline_end_date": str(baseline_end) if baseline_end else str(date.today()),
        }
        
        # Add optional fields
        for key in ["description", "status", "program_owner", "priority", "budget", "strategic_goal"]:
            if key in kwargs and kwargs[key] is not None:
                value = kwargs[key]
                if key == "budget":
                    value = float(value)
                program_data[key] = value
        
        try:
            result = self.db.upsert_program(program_data)
            program_uuid = UUID(result["id"])
            self._program_cache[external_id] = program_uuid
            return program_uuid
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to sync program {external_id}",
                table="programs",
                operation="upsert",
                original_error=str(e)
            )
    
    # ==========================================
    # PROJECT OPERATIONS
    # ==========================================
    
    def sync_project(
        self,
        program_uuid: UUID,
        external_id: str,
        name: Optional[str] = None
    ) -> UUID:
        """
        Sync a project to the database.
        
        Args:
            program_uuid: UUID of parent program
            external_id: Project external ID (e.g., PROJ-001)
            name: Project name
            
        Returns:
            UUID of the project
        """
        cache_key = f"{program_uuid}:{external_id}"
        
        # Check cache first
        if cache_key in self._project_cache:
            return self._project_cache[cache_key]
        
        # Check database
        existing = self.db.get_project_by_external_id(str(program_uuid), external_id)
        
        if existing:
            self._project_cache[cache_key] = UUID(existing["id"])
            return self._project_cache[cache_key]
        
        # Create new project
        project_data = {
            "program_id": str(program_uuid),
            "external_id": external_id,
            "name": name or external_id,
        }
        
        try:
            result = self.db.upsert_project(project_data)
            project_uuid = UUID(result["id"])
            self._project_cache[cache_key] = project_uuid
            return project_uuid
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to sync project {external_id}",
                table="projects",
                operation="upsert",
                original_error=str(e)
            )
    
    # ==========================================
    # PHASE OPERATIONS
    # ==========================================
    
    def sync_phase(
        self,
        project_uuid: UUID,
        external_id: str,
        name: Optional[str] = None,
        sequence: int = 1,
        phase_type: Optional[str] = None
    ) -> UUID:
        """
        Sync a phase to the database.
        
        Args:
            project_uuid: UUID of parent project
            external_id: Phase external ID (e.g., PHASE-001)
            name: Phase name
            sequence: Phase sequence number
            phase_type: Type of phase (Design/Development/Testing)
            
        Returns:
            UUID of the phase
        """
        cache_key = f"{project_uuid}:{external_id}"
        
        # Check cache first
        if cache_key in self._phase_cache:
            return self._phase_cache[cache_key]
        
        # Check database
        existing = self.db.get_phase_by_external_id(str(project_uuid), external_id)
        
        if existing:
            self._phase_cache[cache_key] = UUID(existing["id"])
            return self._phase_cache[cache_key]
        
        # Create new phase
        phase_data = {
            "project_id": str(project_uuid),
            "external_id": external_id,
            "name": name or external_id,
            "sequence": sequence,
        }
        
        if phase_type:
            phase_data["phase_type"] = phase_type
        
        try:
            result = self.db.upsert_phase(phase_data)
            phase_uuid = UUID(result["id"])
            self._phase_cache[cache_key] = phase_uuid
            return phase_uuid
        except Exception as e:
            raise DatabaseError(
                message=f"Failed to sync phase {external_id}",
                table="phases",
                operation="upsert",
                original_error=str(e)
            )
    
    # ==========================================
    # BATCH OPERATIONS
    # ==========================================
    
    def sync_hierarchy_from_work_items(
        self,
        parsed_work_items: list[dict]
    ) -> tuple[dict[str, UUID], dict[str, UUID], dict[str, UUID]]:
        """
        Extract and sync the entire hierarchy from work items.
        
        This creates Programs, Projects, and Phases as needed
        based on the hierarchical IDs in work items.
        
        Args:
            parsed_work_items: List of parsed work items from Excel
            
        Returns:
            Tuple of (program_mapping, project_mapping, phase_mapping)
            Each mapping is external_id -> UUID
        """
        program_mapping: dict[str, UUID] = {}
        project_mapping: dict[str, UUID] = {}
        phase_mapping: dict[str, UUID] = {}
        
        # Track date ranges for programs
        program_date_ranges: dict[str, dict] = {}
        
        # First pass: collect date ranges for programs
        for item in parsed_work_items:
            prog_id = item["program_id"]
            
            if prog_id not in program_date_ranges:
                program_date_ranges[prog_id] = {
                    "name": item.get("program_name"),
                    "min_start": item["planned_start"],
                    "max_end": item["planned_end"],
                }
            else:
                ranges = program_date_ranges[prog_id]
                if item["planned_start"] < ranges["min_start"]:
                    ranges["min_start"] = item["planned_start"]
                if item["planned_end"] > ranges["max_end"]:
                    ranges["max_end"] = item["planned_end"]
        
        # Second pass: sync hierarchy
        for item in parsed_work_items:
            prog_id = item["program_id"]
            proj_id = item["project_id"]
            phase_id = item["phase_id"]
            
            # Sync Program (if not already done)
            if prog_id not in program_mapping:
                date_range = program_date_ranges[prog_id]
                program_uuid = self.sync_program(
                    external_id=prog_id,
                    name=date_range["name"],
                    baseline_start=date_range["min_start"],
                    baseline_end=date_range["max_end"],
                )
                program_mapping[prog_id] = program_uuid
            
            program_uuid = program_mapping[prog_id]
            
            # Sync Project (if not already done)
            project_key = f"{prog_id}:{proj_id}"
            if project_key not in project_mapping:
                project_uuid = self.sync_project(
                    program_uuid=program_uuid,
                    external_id=proj_id,
                    name=item.get("project_name"),
                )
                project_mapping[project_key] = project_uuid
                # Also store by just proj_id for simpler lookups
                project_mapping[proj_id] = project_uuid
            
            project_uuid = project_mapping[proj_id]
            
            # Sync Phase (if not already done)
            phase_key = f"{proj_id}:{phase_id}"
            if phase_key not in phase_mapping:
                phase_uuid = self.sync_phase(
                    project_uuid=project_uuid,
                    external_id=phase_id,
                    name=item.get("phase_name"),
                    sequence=item.get("phase_sequence", 1),
                )
                phase_mapping[phase_key] = phase_uuid
                # Also store by just phase_id for simpler lookups
                phase_mapping[phase_id] = phase_uuid
        
        return program_mapping, project_mapping, phase_mapping
    
    def clear_cache(self) -> None:
        """Clear all internal caches."""
        self._program_cache.clear()
        self._project_cache.clear()
        self._phase_cache.clear()
