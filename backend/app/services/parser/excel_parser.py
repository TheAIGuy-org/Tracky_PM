"""
Excel file parser for Tracky PM.
Handles parsing of multi-sheet Excel files containing project data.
"""
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional, BinaryIO

import pandas as pd

from app.core.exceptions import FileFormatError, ImportError, ValidationError
from app.models.schemas import (
    ExcelWorkItemRow,
    ExcelResourceRow,
    ExcelDependencyRow,
)


class ExcelParser:
    """
    Parser for project management Excel files.
    
    Expected Sheets:
    - Sheet 1 (Programs): Program-level data
    - Sheet 2 (Work Items): Hierarchical task data with Program > Project > Phase > Task
    - Sheet 3A (Dependencies): Task dependencies
    - Sheet 3B (Resources): Resource/team member data
    """
    
    # Expected sheet names (case-insensitive matching)
    SHEET_PROGRAMS = ["programs", "program", "sheet1"]
    SHEET_WORK_ITEMS = ["work items", "workitems", "tasks", "sheet2"]
    SHEET_DEPENDENCIES = ["dependencies", "dependency", "sheet3a"]
    SHEET_RESOURCES = ["resources", "resource", "team", "sheet3b"]
    
    # Required columns for each sheet
    REQUIRED_WORK_ITEM_COLS = [
        "Program ID", "Project ID", "Phase ID", "Work Item ID",
        "Work Item Name", "Planned Start", "Planned End"
    ]
    REQUIRED_RESOURCE_COLS = ["Resource ID", "Resource Name", "Email"]
    REQUIRED_DEPENDENCY_COLS = ["Successor Task ID", "Predecessor Task ID"]
    
    def __init__(self, file: BinaryIO, filename: str):
        """
        Initialize parser with file content.
        
        Args:
            file: Binary file-like object (from upload)
            filename: Original filename for error messages
        """
        self.file = file
        self.filename = filename
        self._excel_file: Optional[pd.ExcelFile] = None
        self._sheet_mapping: dict[str, str] = {}
    
    def _validate_file_type(self) -> None:
        """Validate that the file is an Excel file."""
        valid_extensions = {".xlsx", ".xls", ".xlsm"}
        ext = Path(self.filename).suffix.lower()
        
        if ext not in valid_extensions:
            raise FileFormatError(
                message=f"Invalid file type: {ext}",
                expected_format=", ".join(valid_extensions),
                actual_format=ext
            )
    
    def _load_excel(self) -> pd.ExcelFile:
        """Load Excel file into memory."""
        if self._excel_file is None:
            try:
                self.file.seek(0)  # Reset file pointer
                self._excel_file = pd.ExcelFile(self.file)
            except Exception as e:
                raise ImportError(
                    message=f"Failed to read Excel file: {str(e)}",
                    file_name=self.filename
                )
        return self._excel_file
    
    def _find_sheet(self, possible_names: list[str]) -> Optional[str]:
        """
        Find a sheet by possible names (case-insensitive).
        
        Args:
            possible_names: List of possible sheet names to match
            
        Returns:
            Actual sheet name if found, None otherwise
        """
        excel = self._load_excel()
        sheet_names_lower = {name.lower(): name for name in excel.sheet_names}
        
        for possible in possible_names:
            if possible.lower() in sheet_names_lower:
                return sheet_names_lower[possible.lower()]
        
        return None
    
    def _map_sheets(self) -> dict[str, str]:
        """
        Map logical sheet names to actual sheet names in the file.
        
        Returns:
            Dictionary mapping logical names to actual sheet names
        """
        if self._sheet_mapping:
            return self._sheet_mapping
        
        mapping = {}
        
        # Find each sheet type
        programs_sheet = self._find_sheet(self.SHEET_PROGRAMS)
        if programs_sheet:
            mapping["programs"] = programs_sheet
        
        work_items_sheet = self._find_sheet(self.SHEET_WORK_ITEMS)
        if work_items_sheet:
            mapping["work_items"] = work_items_sheet
        else:
            raise ImportError(
                message="Work Items sheet not found. Expected one of: " + 
                        ", ".join(self.SHEET_WORK_ITEMS),
                file_name=self.filename
            )
        
        dependencies_sheet = self._find_sheet(self.SHEET_DEPENDENCIES)
        if dependencies_sheet:
            mapping["dependencies"] = dependencies_sheet
        
        resources_sheet = self._find_sheet(self.SHEET_RESOURCES)
        if resources_sheet:
            mapping["resources"] = resources_sheet
        
        self._sheet_mapping = mapping
        return mapping
    
    def _validate_columns(
        self,
        df: pd.DataFrame,
        required_cols: list[str],
        sheet_name: str
    ) -> None:
        """
        Validate that required columns exist in the dataframe.
        
        Args:
            df: DataFrame to validate
            required_cols: List of required column names
            sheet_name: Sheet name for error messages
        """
        # Handle empty DataFrames
        if df.empty or len(df.columns) == 0:
            if required_cols:
                raise ImportError(
                    message=f"Sheet '{sheet_name}' is empty or has no columns",
                    file_name=self.filename,
                    sheet_name=sheet_name
                )
            return
        
        # Normalize column names (strip whitespace)
        df.columns = df.columns.str.strip()
        
        missing_cols = set(required_cols) - set(df.columns)
        if missing_cols:
            raise ImportError(
                message=f"Missing required columns: {', '.join(missing_cols)}",
                file_name=self.filename,
                sheet_name=sheet_name
            )
    
    def _parse_date(self, value: Any, field_name: str, row_num: int) -> Optional[date]:
        """
        Parse a date value from Excel.
        
        Args:
            value: Raw value from Excel cell
            field_name: Field name for error messages
            row_num: Row number for error messages
            
        Returns:
            Parsed date or None if empty
        """
        if pd.isna(value) or value == "":
            return None
        
        # If already a datetime
        if isinstance(value, (datetime, pd.Timestamp)):
            return value.date()
        
        # If already a date
        if isinstance(value, date):
            return value
        
        # Try to parse string
        if isinstance(value, str):
            for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"]:
                try:
                    return datetime.strptime(value.strip(), fmt).date()
                except ValueError:
                    continue
        
        raise ValidationError(
            message=f"Invalid date format for {field_name}",
            field=field_name,
            value=value,
            row=row_num
        )
    
    def _parse_decimal(
        self,
        value: Any,
        field_name: str,
        row_num: int
    ) -> Optional[Decimal]:
        """Parse a decimal/currency value from Excel."""
        if pd.isna(value) or value == "":
            return None
        
        try:
            # Remove currency symbols and commas
            if isinstance(value, str):
                value = value.replace("$", "").replace(",", "").strip()
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValidationError(
                message=f"Invalid numeric value for {field_name}",
                field=field_name,
                value=value,
                row=row_num
            )
    
    def _parse_int(
        self,
        value: Any,
        field_name: str,
        row_num: int
    ) -> Optional[int]:
        """Parse an integer value from Excel."""
        if pd.isna(value) or value == "":
            return None
        
        try:
            return int(float(value))
        except (ValueError, TypeError):
            raise ValidationError(
                message=f"Invalid integer value for {field_name}",
                field=field_name,
                value=value,
                row=row_num
            )
    
    def _parse_bool(self, value: Any) -> bool:
        """Parse a boolean value from Excel."""
        if pd.isna(value) or value == "":
            return False
        
        if isinstance(value, bool):
            return value
        
        if isinstance(value, str):
            return value.lower() in ("yes", "true", "1", "y")
        
        return bool(value)
    
    def _clean_string(self, value: Any) -> Optional[str]:
        """Clean and validate a string value."""
        if pd.isna(value) or value == "":
            return None
        return str(value).strip()
    
    def parse(self) -> dict[str, list[dict]]:
        """
        Parse the entire Excel file.
        
        Returns:
            Dictionary with parsed data for each sheet type:
            {
                "programs": [...],
                "work_items": [...],
                "resources": [...],
                "dependencies": [...]
            }
        """
        self._validate_file_type()
        sheet_mapping = self._map_sheets()
        
        result = {
            "programs": [],
            "work_items": [],
            "resources": [],
            "dependencies": [],
        }
        
        # Parse Work Items (required)
        result["work_items"] = self.parse_work_items(sheet_mapping["work_items"])
        
        # Extract programs from work items (if no separate programs sheet)
        if "programs" not in sheet_mapping:
            result["programs"] = self._extract_programs_from_work_items(
                result["work_items"]
            )
        else:
            result["programs"] = self.parse_programs(sheet_mapping["programs"])
        
        # Parse Resources (optional)
        if "resources" in sheet_mapping:
            result["resources"] = self.parse_resources(sheet_mapping["resources"])
        
        # Parse Dependencies (optional)
        if "dependencies" in sheet_mapping:
            result["dependencies"] = self.parse_dependencies(
                sheet_mapping["dependencies"]
            )
        
        return result
    
    def parse_work_items(self, sheet_name: str) -> list[dict]:
        """
        Parse the Work Items sheet.
        
        This extracts the hierarchical structure:
        Program > Project > Phase > Work Item
        
        Args:
            sheet_name: Name of the work items sheet
            
        Returns:
            List of work item dictionaries
        """
        excel = self._load_excel()
        df = pd.read_excel(excel, sheet_name=sheet_name)
        
        # Validate required columns
        self._validate_columns(df, self.REQUIRED_WORK_ITEM_COLS, sheet_name)
        
        work_items = []
        
        for idx, row in df.iterrows():
            row_num = idx + 2  # Excel rows are 1-indexed, plus header
            
            try:
                # Required fields
                program_id = self._clean_string(row.get("Program ID"))
                project_id = self._clean_string(row.get("Project ID"))
                phase_id = self._clean_string(row.get("Phase ID"))
                work_item_id = self._clean_string(row.get("Work Item ID"))
                work_item_name = self._clean_string(row.get("Work Item Name"))
                
                # Skip empty rows
                if not all([program_id, project_id, phase_id, work_item_id, work_item_name]):
                    continue
                
                # Parse dates
                planned_start = self._parse_date(
                    row.get("Planned Start"), "Planned Start", row_num
                )
                planned_end = self._parse_date(
                    row.get("Planned End"), "Planned End", row_num
                )
                
                if not planned_start or not planned_end:
                    raise ValidationError(
                        message="Planned Start and Planned End are required",
                        row=row_num
                    )
                
                work_item = {
                    # Hierarchy
                    "program_id": program_id,
                    "program_name": self._clean_string(row.get("Program Name")),
                    "project_id": project_id,
                    "project_name": self._clean_string(row.get("Project Name")),
                    "phase_id": phase_id,
                    "phase_name": self._clean_string(row.get("Phase Name")),
                    "phase_sequence": self._parse_int(
                        row.get("Phase Sequence"), "Phase Sequence", row_num
                    ) or 1,
                    
                    # Work Item
                    "external_id": work_item_id,
                    "name": work_item_name,
                    "planned_start": planned_start,
                    "planned_end": planned_end,
                    
                    # Optional fields
                    "planned_effort_hours": self._parse_int(
                        row.get("Planned Effort"), "Planned Effort", row_num
                    ),
                    "assigned_resource": self._clean_string(row.get("Assigned Resource")),
                    "allocation_percent": self._parse_int(
                        row.get("Allocation %"), "Allocation %", row_num
                    ) or 100,
                    "complexity": self._clean_string(row.get("Complexity Level")),
                    "revenue_impact": self._parse_decimal(
                        row.get("Revenue Impact $"), "Revenue Impact $", row_num
                    ),
                    "strategic_importance": self._clean_string(
                        row.get("Strategic Importance")
                    ),
                    "customer_impact": self._clean_string(row.get("Customer Impact")),
                    "is_critical_launch": self._parse_bool(
                        row.get("Critical for Launch?")
                    ),
                    "feature_name": self._clean_string(row.get("Feature Name")),
                    
                    # Metadata
                    "_row_number": row_num,
                }
                
                work_items.append(work_item)
                
            except ValidationError:
                raise  # Re-raise validation errors with row context
            except Exception as e:
                raise ImportError(
                    message=f"Error parsing row: {str(e)}",
                    file_name=self.filename,
                    sheet_name=sheet_name,
                    row_number=row_num
                )
        
        return work_items
    
    def parse_programs(self, sheet_name: str) -> list[dict]:
        """Parse the Programs sheet."""
        excel = self._load_excel()
        df = pd.read_excel(excel, sheet_name=sheet_name)
        
        programs = []
        
        for idx, row in df.iterrows():
            row_num = idx + 2
            
            program_id = self._clean_string(row.get("Program ID"))
            if not program_id:
                continue
            
            program = {
                "external_id": program_id,
                "name": self._clean_string(row.get("Program Name")) or program_id,
                "description": self._clean_string(row.get("Description")),
                "status": self._clean_string(row.get("Status")) or "Planned",
                "baseline_start_date": self._parse_date(
                    row.get("Baseline Start"), "Baseline Start", row_num
                ),
                "baseline_end_date": self._parse_date(
                    row.get("Baseline End"), "Baseline End", row_num
                ),
                "program_owner": self._clean_string(row.get("Program Owner")),
                "priority": self._parse_int(row.get("Priority"), "Priority", row_num),
                "budget": self._parse_decimal(row.get("Budget"), "Budget", row_num),
                "strategic_goal": self._clean_string(row.get("Strategic Goal")),
            }
            
            programs.append(program)
        
        return programs
    
    def parse_resources(self, sheet_name: str) -> list[dict]:
        """Parse the Resources sheet."""
        excel = self._load_excel()
        df = pd.read_excel(excel, sheet_name=sheet_name)
        
        self._validate_columns(df, self.REQUIRED_RESOURCE_COLS, sheet_name)
        
        resources = []
        
        for idx, row in df.iterrows():
            row_num = idx + 2
            
            resource_id = self._clean_string(row.get("Resource ID"))
            if not resource_id:
                continue
            
            resource = {
                "external_id": resource_id,
                "name": self._clean_string(row.get("Resource Name")),
                "email": self._clean_string(row.get("Email")),
                "role": self._clean_string(row.get("Role")),
                "home_team": self._clean_string(row.get("Home Program/Team")),
                "cost_per_hour": self._parse_decimal(
                    row.get("Cost Per Hour"), "Cost Per Hour", row_num
                ),
                "max_utilization": self._parse_int(
                    row.get("Max Utilization"), "Max Utilization", row_num
                ) or 100,
                "skill_level": self._clean_string(row.get("Skill Level")),
                "location": self._clean_string(row.get("Location")),
            }
            
            resources.append(resource)
        
        return resources
    
    def parse_dependencies(self, sheet_name: str) -> list[dict]:
        """Parse the Dependencies sheet."""
        excel = self._load_excel()
        df = pd.read_excel(excel, sheet_name=sheet_name)
        
        # Handle empty sheets - dependencies are optional
        if df.empty or len(df.columns) == 0:
            return []
        
        self._validate_columns(df, self.REQUIRED_DEPENDENCY_COLS, sheet_name)
        
        dependencies = []
        
        for idx, row in df.iterrows():
            row_num = idx + 2
            
            successor_id = self._clean_string(row.get("Successor Task ID"))
            predecessor_id = self._clean_string(row.get("Predecessor Task ID"))
            
            if not successor_id or not predecessor_id:
                continue
            
            dependency = {
                "successor_external_id": successor_id,
                "predecessor_external_id": predecessor_id,
                "dependency_type": self._clean_string(
                    row.get("Dependency Type")
                ) or "FS",
                "lag_days": self._parse_int(
                    row.get("Lag Days"), "Lag Days", row_num
                ) or 0,
                "notes": self._clean_string(row.get("Notes")),
                "_row_number": row_num,
            }
            
            dependencies.append(dependency)
        
        return dependencies
    
    def _extract_programs_from_work_items(
        self,
        work_items: list[dict]
    ) -> list[dict]:
        """
        Extract unique programs from work items when no Programs sheet exists.
        Uses first work item's dates as program dates.
        """
        programs_map = {}
        
        for item in work_items:
            program_id = item["program_id"]
            
            if program_id not in programs_map:
                programs_map[program_id] = {
                    "external_id": program_id,
                    "name": item.get("program_name") or program_id,
                    "baseline_start_date": item["planned_start"],
                    "baseline_end_date": item["planned_end"],
                }
            else:
                # Update date ranges
                existing = programs_map[program_id]
                if item["planned_start"] < existing["baseline_start_date"]:
                    existing["baseline_start_date"] = item["planned_start"]
                if item["planned_end"] > existing["baseline_end_date"]:
                    existing["baseline_end_date"] = item["planned_end"]
        
        return list(programs_map.values())
    
    def get_external_ids(self) -> dict[str, set[str]]:
        """
        Get all external IDs from the file for Ghost Check.
        
        Returns:
            Dictionary with sets of external IDs by type:
            {
                "work_items": {"TASK-001", "TASK-002", ...},
                "resources": {"RES-001", ...},
            }
        """
        parsed = self.parse()
        
        return {
            "work_items": {item["external_id"] for item in parsed["work_items"]},
            "resources": {item["external_id"] for item in parsed["resources"]},
            "programs": {item["external_id"] for item in parsed["programs"]},
        }
