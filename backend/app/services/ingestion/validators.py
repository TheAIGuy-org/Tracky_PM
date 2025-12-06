"""
Import Validation Service for Tracky PM.

Implements Three-Pass Validation:
1. PARSE: Parse Excel file (no DB writes)
2. VALIDATE ALL: Validate all data (no DB writes) - circular dependencies, resource allocation
3. SIMULATE: Test DB writes in transaction, rollback
4. EXECUTE: Real write (only if validation passes)

This prevents partial database corruption from failed imports.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Any
from uuid import UUID

from app.core.database import SupabaseClient, get_supabase_client


@dataclass
class ValidationError:
    """A validation error for a specific row/field."""
    row_num: int
    field: str
    value: Any
    message: str
    severity: str = "error"  # "error", "warning"


@dataclass
class ValidationResult:
    """Result of validation pass."""
    is_valid: bool = True
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    
    # Detected issues
    circular_dependencies: list[dict] = field(default_factory=list)
    over_allocated_resources: list[dict] = field(default_factory=list)
    orphaned_tasks: list[str] = field(default_factory=list)
    duplicate_external_ids: list[str] = field(default_factory=list)
    
    def add_error(self, row_num: int, field_name: str, value: Any, message: str) -> None:
        """Add an error and mark result as invalid."""
        self.errors.append(ValidationError(
            row_num=row_num,
            field=field_name,
            value=value,
            message=message,
            severity="error"
        ))
        self.is_valid = False
    
    def add_warning(self, row_num: int, field_name: str, value: Any, message: str) -> None:
        """Add a warning (doesn't invalidate result)."""
        self.warnings.append(ValidationError(
            row_num=row_num,
            field=field_name,
            value=value,
            message=message,
            severity="warning"
        ))
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [
                {
                    "row": e.row_num,
                    "field": e.field,
                    "value": e.value,
                    "message": e.message
                }
                for e in self.errors
            ],
            "warnings": [
                {
                    "row": w.row_num,
                    "field": w.field,
                    "value": w.value,
                    "message": w.message
                }
                for w in self.warnings
            ],
            "circular_dependencies": self.circular_dependencies,
            "over_allocated_resources": self.over_allocated_resources,
            "orphaned_tasks": self.orphaned_tasks,
            "duplicate_external_ids": self.duplicate_external_ids
        }


class ImportValidator:
    """
    Comprehensive validation for import operations.
    
    Validates:
    1. Required fields
    2. Data types and formats
    3. Date logic (end >= start)
    4. Foreign key references (phases, resources exist)
    5. Circular dependencies
    6. Resource over-allocation
    7. Duplicate external IDs
    """
    
    REQUIRED_WORK_ITEM_FIELDS = {
        "external_id": str,
        "name": str,
        "planned_start": date,
        "planned_end": date,
        "phase_id": str,
    }
    
    REQUIRED_RESOURCE_FIELDS = {
        "external_id": str,
        "name": str,
        "email": str,
    }
    
    REQUIRED_DEPENDENCY_FIELDS = {
        "successor_external_id": str,
        "predecessor_external_id": str,
    }
    
    def __init__(self, db_client: Optional[SupabaseClient] = None):
        """Initialize the validator."""
        self.db = db_client or get_supabase_client()
    
    def validate_all(
        self,
        parsed_work_items: list[dict],
        parsed_resources: list[dict],
        parsed_dependencies: list[dict],
        program_id: str
    ) -> ValidationResult:
        """
        Comprehensive validation of all parsed data.
        
        This is PASS 2 of the three-pass import:
        - No database writes
        - Validates all data before any changes
        - Detects circular dependencies
        - Checks resource allocation
        
        Args:
            parsed_work_items: List of parsed work items from Excel
            parsed_resources: List of parsed resources from Excel
            parsed_dependencies: List of parsed dependencies from Excel
            program_id: UUID of the program being imported
            
        Returns:
            ValidationResult with all errors and warnings
        """
        result = ValidationResult()
        
        # 1. Validate work items
        self._validate_work_items(parsed_work_items, result)
        
        # 2. Validate resources
        self._validate_resources(parsed_resources, result)
        
        # 3. Validate dependencies
        self._validate_dependencies(parsed_dependencies, parsed_work_items, result)
        
        # 4. Check for duplicate external IDs
        self._check_duplicate_external_ids(parsed_work_items, result)
        
        # 5. Check for circular dependencies
        self._check_circular_dependencies(parsed_dependencies, parsed_work_items, result)
        
        # 6. Check resource allocation
        self._check_resource_allocation(parsed_work_items, result)
        
        # 7. Check for orphaned tasks (no dependencies)
        self._check_orphaned_tasks(parsed_work_items, parsed_dependencies, result)
        
        return result
    
    def _validate_work_items(
        self,
        work_items: list[dict],
        result: ValidationResult
    ) -> None:
        """Validate all work item fields."""
        for idx, item in enumerate(work_items):
            row_num = idx + 2  # Excel rows start at 2 (after header)
            
            # Check required fields
            for field_name, field_type in self.REQUIRED_WORK_ITEM_FIELDS.items():
                value = item.get(field_name)
                
                if value is None or value == "":
                    result.add_error(
                        row_num, field_name, value,
                        f"Required field '{field_name}' is missing"
                    )
                    continue
                
                # Type validation
                if field_type == date and not isinstance(value, date):
                    if isinstance(value, str):
                        try:
                            date.fromisoformat(value)
                        except ValueError:
                            result.add_error(
                                row_num, field_name, value,
                                f"Invalid date format for '{field_name}': {value}"
                            )
            
            # Date logic validation
            planned_start = item.get("planned_start")
            planned_end = item.get("planned_end")
            
            if planned_start and planned_end:
                start = planned_start if isinstance(planned_start, date) else date.fromisoformat(str(planned_start))
                end = planned_end if isinstance(planned_end, date) else date.fromisoformat(str(planned_end))
                
                if end < start:
                    result.add_error(
                        row_num, "planned_end", str(planned_end),
                        f"End date ({end}) cannot be before start date ({start})"
                    )
            
            # Allocation validation
            allocation = item.get("allocation_percent")
            if allocation is not None:
                try:
                    alloc_int = int(allocation)
                    if not 0 <= alloc_int <= 100:
                        result.add_error(
                            row_num, "allocation_percent", allocation,
                            f"Allocation must be between 0-100%, got {allocation}%"
                        )
                except (ValueError, TypeError):
                    result.add_error(
                        row_num, "allocation_percent", allocation,
                        f"Invalid allocation value: {allocation}"
                    )
    
    def _validate_resources(
        self,
        resources: list[dict],
        result: ValidationResult
    ) -> None:
        """Validate all resource fields."""
        for idx, resource in enumerate(resources):
            row_num = idx + 2
            
            for field_name in self.REQUIRED_RESOURCE_FIELDS:
                value = resource.get(field_name)
                
                if value is None or value == "":
                    result.add_error(
                        row_num, field_name, value,
                        f"Required field '{field_name}' is missing for resource"
                    )
            
            # Email validation
            email = resource.get("email")
            if email and "@" not in str(email):
                result.add_error(
                    row_num, "email", email,
                    f"Invalid email format: {email}"
                )
            
            # Max utilization validation
            max_util = resource.get("max_utilization")
            if max_util is not None:
                try:
                    util_int = int(max_util)
                    if not 1 <= util_int <= 200:
                        result.add_warning(
                            row_num, "max_utilization", max_util,
                            f"Unusual max utilization: {max_util}% (expected 1-200%)"
                        )
                except (ValueError, TypeError):
                    result.add_error(
                        row_num, "max_utilization", max_util,
                        f"Invalid max utilization value: {max_util}"
                    )
    
    def _validate_dependencies(
        self,
        dependencies: list[dict],
        work_items: list[dict],
        result: ValidationResult
    ) -> None:
        """Validate all dependencies."""
        # Build set of valid work item IDs
        valid_ids = {item["external_id"] for item in work_items}
        
        for idx, dep in enumerate(dependencies):
            # Use row number from parser if available, otherwise calculate
            row_num = dep.get("_row_number", idx + 2)
            
            # Parser uses successor_external_id and predecessor_external_id
            successor_id = dep.get("successor_external_id")
            predecessor_id = dep.get("predecessor_external_id")
            
            # Check required fields
            if not successor_id:
                result.add_error(
                    row_num, "successor_external_id", successor_id,
                    "Dependency requires a successor task ID"
                )
            
            if not predecessor_id:
                result.add_error(
                    row_num, "predecessor_external_id", predecessor_id,
                    "Dependency requires a predecessor task ID"
                )
            
            # Check references exist
            if successor_id and successor_id not in valid_ids:
                result.add_error(
                    row_num, "successor_external_id", successor_id,
                    f"Successor task '{successor_id}' not found in work items"
                )
            
            if predecessor_id and predecessor_id not in valid_ids:
                result.add_error(
                    row_num, "predecessor_external_id", predecessor_id,
                    f"Predecessor task '{predecessor_id}' not found in work items"
                )
            
            # Self-reference check
            if successor_id and predecessor_id and successor_id == predecessor_id:
                result.add_error(
                    row_num, "successor_external_id", successor_id,
                    f"Task cannot depend on itself: {successor_id}"
                )
            
            # Validate dependency type
            dep_type = dep.get("dependency_type", "FS")
            valid_types = {"FS", "SS", "FF", "SF"}
            if dep_type not in valid_types:
                result.add_error(
                    row_num, "dependency_type", dep_type,
                    f"Invalid dependency type: {dep_type}. Must be one of {valid_types}"
                )
            
            # Validate lag days
            lag = dep.get("lag_days", 0)
            try:
                lag_int = int(lag)
                if lag_int < -365 or lag_int > 365:
                    result.add_warning(
                        row_num, "lag_days", lag,
                        f"Unusual lag value: {lag} days"
                    )
            except (ValueError, TypeError):
                result.add_error(
                    row_num, "lag_days", lag,
                    f"Invalid lag days value: {lag}"
                )
    
    def _check_duplicate_external_ids(
        self,
        work_items: list[dict],
        result: ValidationResult
    ) -> None:
        """Check for duplicate external IDs within the import."""
        seen = {}
        for idx, item in enumerate(work_items):
            ext_id = item.get("external_id")
            if ext_id in seen:
                result.add_error(
                    idx + 2, "external_id", ext_id,
                    f"Duplicate external ID: '{ext_id}' (first seen at row {seen[ext_id]})"
                )
                result.duplicate_external_ids.append(ext_id)
            else:
                seen[ext_id] = idx + 2
    
    def _check_circular_dependencies(
        self,
        dependencies: list[dict],
        work_items: list[dict],
        result: ValidationResult
    ) -> None:
        """
        Detect circular dependencies using DFS.
        
        A circular dependency occurs when:
        A -> B -> C -> A
        
        This would cause infinite loops in recalculation.
        """
        # Build adjacency list: predecessor -> [successors]
        graph: dict[str, list[str]] = {}
        for dep in dependencies:
            pred = dep.get("predecessor_external_id")
            succ = dep.get("successor_external_id")
            if pred and succ:
                if pred not in graph:
                    graph[pred] = []
                graph[pred].append(succ)
        
        # DFS to detect cycles
        visited = set()
        rec_stack = set()
        
        def dfs(node: str, path: list[str]) -> Optional[list[str]]:
            """DFS with path tracking to find cycle."""
            if node in rec_stack:
                # Found cycle - return the cycle path
                cycle_start = path.index(node)
                return path[cycle_start:] + [node]
            
            if node in visited:
                return None
            
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in graph.get(node, []):
                cycle = dfs(neighbor, path)
                if cycle:
                    return cycle
            
            path.pop()
            rec_stack.remove(node)
            return None
        
        # Check all nodes
        all_nodes = set(graph.keys())
        for dep in dependencies:
            all_nodes.add(dep.get("successor_external_id", ""))
        
        for node in all_nodes:
            if node and node not in visited:
                cycle = dfs(node, [])
                if cycle:
                    cycle_str = " -> ".join(cycle)
                    result.add_error(
                        0, "dependencies", cycle_str,
                        f"Circular dependency detected: {cycle_str}"
                    )
                    result.circular_dependencies.append({
                        "cycle": cycle,
                        "description": f"Circular: {cycle_str}"
                    })
    
    def _check_resource_allocation(
        self,
        work_items: list[dict],
        result: ValidationResult
    ) -> None:
        """
        Check if any resource will be over-allocated after import.
        
        Sums allocation_percent for each resource across all active tasks.
        """
        # Build resource allocation map
        resource_allocation: dict[str, int] = {}
        resource_tasks: dict[str, list[str]] = {}
        
        for item in work_items:
            resource_id = item.get("assigned_resource")
            allocation = item.get("allocation_percent", 100)
            
            if resource_id:
                if resource_id not in resource_allocation:
                    resource_allocation[resource_id] = 0
                    resource_tasks[resource_id] = []
                
                resource_allocation[resource_id] += int(allocation)
                resource_tasks[resource_id].append(item.get("external_id", ""))
        
        # Check for over-allocation (> 100%)
        for resource_id, total_alloc in resource_allocation.items():
            if total_alloc > 100:
                tasks = resource_tasks[resource_id]
                result.add_warning(
                    0, "resource_allocation", resource_id,
                    f"Resource '{resource_id}' will be {total_alloc}% allocated "
                    f"across {len(tasks)} tasks: {', '.join(tasks[:5])}"
                    + (f"... and {len(tasks) - 5} more" if len(tasks) > 5 else "")
                )
                result.over_allocated_resources.append({
                    "resource_id": resource_id,
                    "total_allocation": total_alloc,
                    "task_count": len(tasks),
                    "tasks": tasks
                })
    
    def _check_orphaned_tasks(
        self,
        work_items: list[dict],
        dependencies: list[dict],
        result: ValidationResult
    ) -> None:
        """
        Check for tasks with no dependencies (orphaned).
        
        These might be intentional (milestones, independent tasks)
        or might indicate missing data.
        """
        # Build sets of tasks with dependencies
        has_predecessor = {dep.get("successor_id") for dep in dependencies}
        has_successor = {dep.get("predecessor_id") for dep in dependencies}
        has_any_dependency = has_predecessor | has_successor
        
        # Find orphaned tasks
        for item in work_items:
            ext_id = item.get("external_id")
            if ext_id and ext_id not in has_any_dependency:
                result.orphaned_tasks.append(ext_id)
        
        # Only warn if there are many orphaned tasks
        orphan_count = len(result.orphaned_tasks)
        total_count = len(work_items)
        
        if orphan_count > 0 and orphan_count > total_count * 0.2:  # More than 20% orphaned
            result.add_warning(
                0, "dependencies", orphan_count,
                f"{orphan_count} of {total_count} tasks ({orphan_count*100//total_count}%) "
                f"have no dependencies. This may indicate missing dependency data."
            )


def validate_import_data(
    parsed_work_items: list[dict],
    parsed_resources: list[dict],
    parsed_dependencies: list[dict],
    program_id: str
) -> ValidationResult:
    """
    Convenience function to validate import data.
    
    Args:
        parsed_work_items: List of parsed work items from Excel
        parsed_resources: List of parsed resources from Excel
        parsed_dependencies: List of parsed dependencies from Excel
        program_id: UUID of the program being imported
        
    Returns:
        ValidationResult with all errors and warnings
    """
    validator = ImportValidator()
    return validator.validate_all(
        parsed_work_items,
        parsed_resources,
        parsed_dependencies,
        program_id
    )
