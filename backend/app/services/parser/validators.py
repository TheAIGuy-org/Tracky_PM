"""
Data validators for Tracky PM.
Provides validation logic for parsed data before database operations.
"""
from datetime import date
from typing import Any, Optional

from app.core.exceptions import ValidationError, DependencyCycleError
from app.models.enums import (
    DependencyType,
    WorkStatus,
    ComplexityLevel,
)


class DataValidator:
    """
    Validator for parsed Excel data.
    Ensures data integrity before database operations.
    """
    
    @staticmethod
    def validate_date_range(
        start_date: date,
        end_date: date,
        field_prefix: str = "",
        row: Optional[int] = None
    ) -> None:
        """
        Validate that end date is not before start date.
        
        Args:
            start_date: Start date
            end_date: End date
            field_prefix: Prefix for field names in error messages
            row: Row number for error context
        """
        if end_date < start_date:
            raise ValidationError(
                message=f"{field_prefix}End date cannot be before start date",
                field=f"{field_prefix}end_date",
                value=f"{start_date} -> {end_date}",
                row=row
            )
    
    @staticmethod
    def validate_percentage(
        value: int,
        field_name: str,
        min_val: int = 0,
        max_val: int = 100,
        row: Optional[int] = None
    ) -> None:
        """Validate a percentage value is within bounds."""
        if not min_val <= value <= max_val:
            raise ValidationError(
                message=f"{field_name} must be between {min_val} and {max_val}",
                field=field_name,
                value=value,
                row=row
            )
    
    @staticmethod
    def validate_enum_value(
        value: str,
        enum_class: type,
        field_name: str,
        row: Optional[int] = None
    ) -> None:
        """Validate a value matches an enum."""
        valid_values = [e.value for e in enum_class]
        if value not in valid_values:
            raise ValidationError(
                message=f"Invalid {field_name}. Must be one of: {', '.join(valid_values)}",
                field=field_name,
                value=value,
                row=row
            )
    
    @staticmethod
    def validate_complexity(
        value: Optional[str],
        row: Optional[int] = None
    ) -> Optional[str]:
        """Validate and normalize complexity level."""
        if not value:
            return None
        
        normalized = value.strip().title()
        valid = [e.value for e in ComplexityLevel]
        
        if normalized not in valid:
            raise ValidationError(
                message=f"Invalid complexity level. Must be one of: {', '.join(valid)}",
                field="complexity",
                value=value,
                row=row
            )
        
        return normalized
    
    @staticmethod
    def validate_dependency_type(
        value: Optional[str],
        row: Optional[int] = None
    ) -> str:
        """Validate and normalize dependency type."""
        if not value:
            return DependencyType.FS.value
        
        normalized = value.strip().upper()
        valid = [e.value for e in DependencyType]
        
        if normalized not in valid:
            raise ValidationError(
                message=f"Invalid dependency type. Must be one of: {', '.join(valid)}",
                field="dependency_type",
                value=value,
                row=row
            )
        
        return normalized
    
    @staticmethod
    def validate_work_status(
        value: Optional[str],
        row: Optional[int] = None
    ) -> str:
        """Validate and normalize work status."""
        if not value:
            return WorkStatus.NOT_STARTED.value
        
        # Map common variations
        status_map = {
            "not started": WorkStatus.NOT_STARTED.value,
            "notstarted": WorkStatus.NOT_STARTED.value,
            "new": WorkStatus.NOT_STARTED.value,
            "in progress": WorkStatus.IN_PROGRESS.value,
            "inprogress": WorkStatus.IN_PROGRESS.value,
            "active": WorkStatus.IN_PROGRESS.value,
            "wip": WorkStatus.IN_PROGRESS.value,
            "completed": WorkStatus.COMPLETED.value,
            "done": WorkStatus.COMPLETED.value,
            "finished": WorkStatus.COMPLETED.value,
            "on hold": WorkStatus.ON_HOLD.value,
            "onhold": WorkStatus.ON_HOLD.value,
            "paused": WorkStatus.ON_HOLD.value,
            "cancelled": WorkStatus.CANCELLED.value,
            "canceled": WorkStatus.CANCELLED.value,
        }
        
        normalized = value.strip().lower()
        if normalized in status_map:
            return status_map[normalized]
        
        valid = [e.value for e in WorkStatus]
        raise ValidationError(
            message=f"Invalid work status. Must be one of: {', '.join(valid)}",
            field="status",
            value=value,
            row=row
        )
    
    @staticmethod
    def validate_external_id(
        value: str,
        entity_type: str,
        row: Optional[int] = None
    ) -> str:
        """
        Validate external ID format.
        
        Expected formats:
        - Programs: PROG-XXX
        - Projects: PROJ-XXX
        - Phases: PHASE-XXX
        - Tasks: TASK-XXX
        - Resources: RES-XXX
        """
        if not value or not value.strip():
            raise ValidationError(
                message=f"{entity_type} ID is required",
                field=f"{entity_type.lower()}_id",
                row=row
            )
        
        cleaned = value.strip()
        
        # Check for minimum length
        if len(cleaned) < 2:
            raise ValidationError(
                message=f"{entity_type} ID is too short",
                field=f"{entity_type.lower()}_id",
                value=cleaned,
                row=row
            )
        
        return cleaned
    
    @staticmethod
    def validate_email(
        value: str,
        row: Optional[int] = None
    ) -> str:
        """Basic email validation."""
        if not value or "@" not in value:
            raise ValidationError(
                message="Invalid email address",
                field="email",
                value=value,
                row=row
            )
        
        return value.strip().lower()
    
    @classmethod
    def validate_work_item(cls, item: dict, row: Optional[int] = None) -> dict:
        """
        Validate a complete work item dictionary.
        
        Args:
            item: Work item dictionary from parser
            row: Row number for error context
            
        Returns:
            Validated and cleaned work item
        """
        row = row or item.get("_row_number")
        
        # Validate required IDs
        item["program_id"] = cls.validate_external_id(
            item["program_id"], "Program", row
        )
        item["project_id"] = cls.validate_external_id(
            item["project_id"], "Project", row
        )
        item["phase_id"] = cls.validate_external_id(
            item["phase_id"], "Phase", row
        )
        item["external_id"] = cls.validate_external_id(
            item["external_id"], "Work Item", row
        )
        
        # Validate dates
        cls.validate_date_range(
            item["planned_start"],
            item["planned_end"],
            "planned_",
            row
        )
        
        # Validate percentages
        if item.get("allocation_percent") is not None:
            cls.validate_percentage(
                item["allocation_percent"],
                "Allocation %",
                0, 100,
                row
            )
        
        # Validate and normalize complexity
        if item.get("complexity"):
            item["complexity"] = cls.validate_complexity(item["complexity"], row)
        
        return item
    
    @classmethod
    def validate_dependency(cls, dep: dict, row: Optional[int] = None) -> dict:
        """
        Validate a dependency dictionary.
        
        Args:
            dep: Dependency dictionary from parser
            row: Row number for error context
            
        Returns:
            Validated dependency
        """
        row = row or dep.get("_row_number")
        
        # Validate IDs
        dep["successor_external_id"] = cls.validate_external_id(
            dep["successor_external_id"], "Successor Task", row
        )
        dep["predecessor_external_id"] = cls.validate_external_id(
            dep["predecessor_external_id"], "Predecessor Task", row
        )
        
        # Check self-reference
        if dep["successor_external_id"] == dep["predecessor_external_id"]:
            raise ValidationError(
                message="A task cannot depend on itself",
                field="predecessor_external_id",
                value=dep["predecessor_external_id"],
                row=row
            )
        
        # Validate dependency type
        dep["dependency_type"] = cls.validate_dependency_type(
            dep.get("dependency_type"),
            row
        )
        
        return dep
    
    @classmethod
    def validate_resource(cls, resource: dict, row: Optional[int] = None) -> dict:
        """
        Validate a resource dictionary.
        
        Args:
            resource: Resource dictionary from parser
            row: Row number for error context
            
        Returns:
            Validated resource
        """
        # Validate ID
        resource["external_id"] = cls.validate_external_id(
            resource["external_id"], "Resource", row
        )
        
        # Validate email
        if resource.get("email"):
            resource["email"] = cls.validate_email(resource["email"], row)
        
        # Validate utilization
        if resource.get("max_utilization") is not None:
            cls.validate_percentage(
                resource["max_utilization"],
                "Max Utilization",
                1, 200,  # Can go up to 200% for overtime
                row
            )
        
        return resource


class DependencyGraphValidator:
    """
    Validates dependency graph for cycles.
    A circular dependency would cause infinite loops in recalculation.
    """
    
    def __init__(self, dependencies: list[dict]):
        """
        Initialize with list of dependencies.
        
        Args:
            dependencies: List of dependency dicts with successor/predecessor IDs
        """
        self.dependencies = dependencies
        self._graph: dict[str, set[str]] = {}
        self._build_graph()
    
    def _build_graph(self) -> None:
        """Build adjacency list representation of dependency graph."""
        for dep in self.dependencies:
            successor = dep["successor_external_id"]
            predecessor = dep["predecessor_external_id"]
            
            if successor not in self._graph:
                self._graph[successor] = set()
            self._graph[successor].add(predecessor)
    
    def detect_cycles(self) -> list[list[str]]:
        """
        Detect all cycles in the dependency graph.
        
        Returns:
            List of cycles (each cycle is a list of task IDs)
        """
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(node: str, path: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in self._graph.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path.copy())
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
            
            rec_stack.remove(node)
        
        for node in self._graph:
            if node not in visited:
                dfs(node, [])
        
        return cycles
    
    def validate_no_cycles(self) -> None:
        """
        Validate that there are no cycles in the dependency graph.
        
        Raises:
            DependencyCycleError if a cycle is detected
        """
        cycles = self.detect_cycles()
        
        if cycles:
            # Report the first cycle found
            cycle = cycles[0]
            raise DependencyCycleError(
                message="Circular dependency detected",
                cycle_path=cycle
            )
