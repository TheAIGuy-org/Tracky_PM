"""
Tests for Import Routes (/import endpoints).
"""
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
import io

# ==========================================
# MOCK EXCEL FILE
# ==========================================

@pytest.fixture
def mock_excel_file():
    """Create a mock Excel file for upload."""
    return io.BytesIO(b"fake excel content")


# ==========================================
# IMPORT EXCEL TESTS (CORE)
# ==========================================

class TestImportExcel:
    """Test Excel import endpoint core functionality."""
    
    @pytest.mark.unit
    def test_import_excel_success(self, client, mock_data, mock_excel_file):
        """Successful import returns success status."""
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser, \
             patch("app.api.routes.import_routes.ImportValidator") as MockValidator, \
             patch("app.api.routes.import_routes.HierarchySyncService") as MockHierarchy, \
             patch("app.api.routes.import_routes.ResourceSyncService") as MockResource, \
             patch("app.api.routes.import_routes.SmartMergeEngine") as MockMerge, \
             patch("app.api.routes.import_routes.DependencySyncService") as MockDep:
            
            # Setup mocks
            parser_instance = MockParser.return_value
            parser_instance.parse.return_value = {
                "work_items": [], "resources": [], "dependencies": []
            }
            
            validator_instance = MockValidator.return_value
            validator_result = MagicMock()
            validator_result.is_valid = True
            validator_result.warnings = []
            validator_instance.validate_all.return_value = validator_result
            
            hierarchy_instance = MockHierarchy.return_value
            program_id = str(uuid4())
            hierarchy_instance.sync_hierarchy_from_work_items.return_value = (
                {"PROG-001": program_id}, {}, {}
            )
            
            resource_instance = MockResource.return_value
            resource_instance.bulk_sync_all.return_value = {}
            
            merge_instance = MockMerge.return_value
            merge_result = MagicMock()
            merge_result.tasks_created = 5
            merge_result.tasks_updated = 2
            merge_result.tasks_preserved = 10
            merge_result.tasks_cancelled = 0
            merge_result.tasks_flagged = 0
            merge_result.results = []
            merge_result.warnings = []
            merge_instance.merge_all.return_value = merge_result
            
            response = client.post(
                "/import/upload",
                files={"file": ("test.xlsx", mock_excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"author_email": "test@example.com"}
            )
            
            assert response.status_code == 200
            data = response.json()
            if data["status"] not in ("success", "partial_success"):
                 pytest.fail(f"Import failed with status {data['status']}. Errors: {data.get('errors')}")
            assert "import_batch_id" in data

    @pytest.mark.unit
    def test_import_dry_run(self, client, mock_data, mock_excel_file):
        """Dry run passes validation but does not execute merge."""
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser, \
             patch("app.api.routes.import_routes.ImportValidator") as MockValidator, \
             patch("app.api.routes.import_routes.SmartMergeEngine") as MockMerge:
             
            parser_instance = MockParser.return_value
            parser_instance.parse.return_value = {
                "work_items": [], "resources": [], "dependencies": []
            } 
            
            validator_instance = MockValidator.return_value
            validator_result = MagicMock()
            validator_result.is_valid = True
            validator_result.warnings = []
            validator_instance.validate_all.return_value = validator_result
            
            response = client.post(
                "/import/upload",
                files={"file": ("test.xlsx", mock_excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                params={"dry_run": True}
            )
            
            assert response.status_code == 200
            data = response.json()
            if data["status"] != "validation_passed":
                pytest.fail(f"Dry run failed with status {data['status']}. Errors: {data.get('errors')}")
            
            assert data["status"] == "validation_passed"
            MockMerge.return_value.merge_all.assert_not_called()

    @pytest.mark.unit
    def test_import_save_baseline_version(self, client, mock_data, mock_excel_file):
        """Import with save_baseline_version=True creates a baseline."""
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser, \
             patch("app.api.routes.import_routes.ImportValidator") as MockValidator, \
             patch("app.api.routes.import_routes.HierarchySyncService") as MockHierarchy, \
             patch("app.api.routes.import_routes.ResourceSyncService") as MockResource, \
             patch("app.api.routes.import_routes.SmartMergeEngine") as MockMerge, \
             patch("app.api.routes.import_routes.DependencySyncService") as MockDep:
            
            MockParser.return_value.parse.return_value = {"work_items": [], "resources": [], "dependencies": []}
            MockValidator.return_value.validate_all.return_value = MagicMock(is_valid=True, warnings=[])
            MockHierarchy.return_value.sync_hierarchy_from_work_items.return_value = ({ "P": str(uuid4()) }, {}, {})
            MockMerge.return_value.merge_all.return_value = MagicMock(
                tasks_created=0, tasks_updated=0, tasks_preserved=0, tasks_cancelled=0, tasks_flagged=0,
                results=[], warnings=[]
            )
            
            response = client.post(
                "/import/upload",
                files={"file": ("test.xlsx", mock_excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                params={"save_baseline_version": True}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "baseline_version_id" in data
            assert data["baseline_version_id"] is not None

    @pytest.mark.unit
    def test_import_large_excel(self, client, mock_data, mock_excel_file):
        """Simulate large file import (perf check via processing time mocking)."""
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser, \
             patch("app.api.routes.import_routes.ImportValidator") as MockValidator, \
             patch("app.api.routes.import_routes.HierarchySyncService") as MockHierarchy, \
             patch("app.api.routes.import_routes.ResourceSyncService") as MockResource, \
             patch("app.api.routes.import_routes.SmartMergeEngine") as MockMerge, \
             patch("app.api.routes.import_routes.DependencySyncService") as MockDep:
            
            MockParser.return_value.parse.return_value = {
                "work_items": [{"id": i} for i in range(1000)], 
                "resources": [], 
                "dependencies": []
            }
            MockValidator.return_value.validate_all.return_value = MagicMock(is_valid=True, warnings=[])
            MockHierarchy.return_value.sync_hierarchy_from_work_items.return_value = ({"P": "id"}, {}, {})
            MockMerge.return_value.merge_all.return_value = MagicMock(
                tasks_created=1000, tasks_updated=0, tasks_preserved=0, tasks_cancelled=0, tasks_flagged=0,
                results=[], warnings=[]
            )
            
            response = client.post(
                "/import/upload",
                files={"file": ("test.xlsx", mock_excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
            assert response.status_code == 200
            assert response.json()["summary"]["tasks_created"] == 1000

    @pytest.mark.unit
    def test_import_with_resources(self, client, mock_data, mock_excel_file):
        """Test import explicitly checking resource sync integration."""
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser, \
             patch("app.api.routes.import_routes.ImportValidator") as MockValidator, \
             patch("app.api.routes.import_routes.HierarchySyncService") as MockHierarchy, \
             patch("app.api.routes.import_routes.ResourceSyncService") as MockResource, \
             patch("app.api.routes.import_routes.SmartMergeEngine") as MockMerge:
            
            MockParser.return_value.parse.return_value = {
                "work_items": [], 
                "resources": [{"name": "Res1"}], 
                "dependencies": []
            }
            MockValidator.return_value.validate_all.return_value = MagicMock(is_valid=True, warnings=[])
            MockHierarchy.return_value.sync_hierarchy_from_work_items.return_value = ({"P": "id"}, {}, {})
            MockResource.return_value.bulk_sync_all.return_value = {"Res1": str(uuid4())}
            MockMerge.return_value.merge_all.return_value = MagicMock(
                tasks_created=0, tasks_updated=0, tasks_preserved=0, tasks_cancelled=0, tasks_flagged=0,
                results=[], warnings=[]
            )
            
            response = client.post(
                "/import/upload",
                files={"file": ("test.xlsx", mock_excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
            assert response.status_code == 200
            assert response.json()["summary"]["resources_synced"] == 1


# ==========================================
# IMPORT ERROR HANDLING
# ==========================================

class TestImportErrors:
    
    @pytest.mark.unit
    def test_import_invalid_file_extension(self, client):
        response = client.post(
            "/import/upload",
            files={"file": ("test.txt", io.BytesIO(b"text"), "text/plain")}
        )
        assert response.status_code == 415

    @pytest.mark.unit
    def test_import_empty_file(self, client, mock_excel_file):
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser:
            MockParser.side_effect = Exception("File is empty or corrupted")
            response = client.post(
                "/import/upload",
                files={"file": ("test.xlsx", mock_excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "failed"
            assert "File is empty" in str(data["errors"])

    @pytest.mark.unit
    def test_import_validation_errors(self, client, mock_excel_file):
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser, \
             patch("app.api.routes.import_routes.ImportValidator") as MockValidator:
            MockParser.return_value.parse.return_value = {"work_items": [], "resources": [], "dependencies": []}
            validator_result = MagicMock()
            validator_result.is_valid = False
            error = MagicMock()
            error.type = "validation_error"  # Ensure serialization works
            error.row_num = 1
            error.field = "start_date"
            error.value = "invalid"
            error.message = "Bad date"
            validator_result.errors = [error]
            validator_result.warnings = []
            MockValidator.return_value.validate_all.return_value = validator_result
            
            response = client.post(
                "/import/upload",
                files={"file": ("test.xlsx", mock_excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
            data = response.json()
            assert data["status"] == "validation_failed"

    @pytest.mark.unit
    def test_import_missing_program(self, client, mock_excel_file):
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser, \
             patch("app.api.routes.import_routes.ImportValidator") as MockValidator, \
             patch("app.api.routes.import_routes.HierarchySyncService") as MockHierarchy:
            MockParser.return_value.parse.return_value = {"work_items": [], "resources": [], "dependencies": []}
            MockValidator.return_value.validate_all.return_value = MagicMock(is_valid=True, warnings=[])
            MockHierarchy.return_value.sync_hierarchy_from_work_items.return_value = ({}, {}, {})
            
            response = client.post(
                "/import/upload",
                files={"file": ("test.xlsx", mock_excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
            assert response.json()["status"] == "failed"

    @pytest.mark.unit
    def test_import_invalid_dates(self, client, mock_excel_file):
        """Test with specific invalid date validation error."""
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser, \
             patch("app.api.routes.import_routes.ImportValidator") as MockValidator:
             
            MockParser.return_value.parse.return_value = {"work_items": [], "resources": [], "dependencies": []}
            
            val_res = MagicMock(is_valid=False)
            val_res.errors = [MagicMock(field="end_date", message="Invalid format", type="date_error")]
            MockValidator.return_value.validate_all.return_value = val_res
            
            response = client.post("/import/upload", files={"file": ("test.xlsx", mock_excel_file, "")})
            assert "Invalid format" in str(response.json()["errors"])

    @pytest.mark.unit
    def test_import_invalid_hierarchy(self, client, mock_excel_file):
        """Test with broken hierarchy validation error."""
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser, \
             patch("app.api.routes.import_routes.ImportValidator") as MockValidator:
             
            MockParser.return_value.parse.return_value = {"work_items": [], "resources": [], "dependencies": []}
            
            val_res = MagicMock(is_valid=False)
            val_res.errors = [MagicMock(field="parent_id", message="Parent loop detected", type="hierarchy_error")]
            MockValidator.return_value.validate_all.return_value = val_res
            response = client.post("/import/upload", files={"file": ("test.xlsx", mock_excel_file, "")})
            assert "Parent loop" in str(response.json()["errors"])
    
    @pytest.mark.unit
    def test_import_missing_required_columns(self, client, mock_excel_file):
        """Test failure when parser fails due to missing columns."""
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser:
            MockParser.side_effect = Exception("Missing required column: 'Task ID'")
            response = client.post(
                "/import/upload",
                files={"file": ("test.xlsx", mock_excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
            assert response.status_code == 200
            assert "Missing required column" in str(response.json()["errors"])


# ==========================================
# VALDIATION ENDPOINTS
# ==========================================

class TestValidateExcel:
    
    @pytest.mark.unit
    def test_validate_excel_valid(self, client, mock_excel_file):
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser, \
             patch("app.api.routes.import_routes.ImportValidator") as MockValidator:
            MockParser.return_value.parse.return_value = {"work_items": [], "resources": [], "dependencies": []}
            MockValidator.return_value.validate_all.return_value = MagicMock(is_valid=True, warnings=[])
            
            response = client.post(
                "/import/validate",
                files={"file": ("test.xlsx", mock_excel_file, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
            assert response.status_code == 200
            assert response.json()["valid"] == True

    @pytest.mark.unit
    def test_validate_excel_invalid(self, client, mock_excel_file):
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser, \
             patch("app.api.routes.import_routes.ImportValidator") as MockValidator:
            MockParser.return_value.parse.return_value = {"work_items": [], "resources": [], "dependencies": []}
            MockValidator.return_value.validate_all.return_value = MagicMock(
                is_valid=False, 
                errors=[MagicMock(message="Bad data")], 
                warnings=[]
            )
            response = client.post("/import/validate", files={"file": ("test.xlsx", mock_excel_file, "")})
            assert response.json()["valid"] == False

    @pytest.mark.unit
    def test_validate_excel_warnings(self, client, mock_excel_file):
        with patch("app.api.routes.import_routes.ExcelParser") as MockParser, \
             patch("app.api.routes.import_routes.ImportValidator") as MockValidator:
            
            MockParser.return_value.parse.return_value = {"work_items": [], "resources": [], "dependencies": []}
            
            val_res = MagicMock()
            val_res.is_valid = True
            val_res.errors = []
            val_res.warnings = ["Minor issue"]
            # Mock to_dict for the validation endpoint which calls it
            val_res.to_dict.return_value = {"is_valid": True, "errors": [], "warnings": ["Minor issue"]}
            MockValidator.return_value.validate_all.return_value = val_res
            
            response = client.post("/import/validate", files={"file": ("test.xlsx", mock_excel_file, "")})
            data = response.json()
            assert data["valid"] == True
            # Warnings are nested in "validation" key
            assert len(data["validation"]["warnings"]) > 0


# ==========================================
# SMART MERGE SIMULATIONS
# ==========================================

class TestSmartMergeScenarios:

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        # Explicit patching instead of loop to avoid attribute access issues
        self.parser_patch = patch("app.api.routes.import_routes.ExcelParser")
        self.validator_patch = patch("app.api.routes.import_routes.ImportValidator")
        self.hierarchy_patch = patch("app.api.routes.import_routes.HierarchySyncService")
        self.resource_patch = patch("app.api.routes.import_routes.ResourceSyncService")
        self.merge_patch = patch("app.api.routes.import_routes.SmartMergeEngine")
        self.dep_patch = patch("app.api.routes.import_routes.DependencySyncService")

        self.mock_parser = self.parser_patch.start()
        self.mock_validator = self.validator_patch.start()
        self.mock_hierarchy = self.hierarchy_patch.start()
        self.mock_resource = self.resource_patch.start()
        self.mock_merge = self.merge_patch.start()
        self.mock_dep = self.dep_patch.start()
        
        # Default happy paths
        self.mock_parser.return_value.parse.return_value = {"work_items": [], "resources": [], "dependencies": []}
        self.mock_validator.return_value.validate_all.return_value = MagicMock(is_valid=True, warnings=[])
        self.mock_hierarchy.return_value.sync_hierarchy_from_work_items.return_value = ({"P": "id"}, {}, {})
        self.mock_resource.return_value.bulk_sync_all.return_value = {}
        
        yield
        
        self.parser_patch.stop()
        self.validator_patch.stop()
        self.hierarchy_patch.stop()
        self.resource_patch.stop()
        self.merge_patch.stop()
        self.dep_patch.stop()

    def set_merge_result(self, created=0, updated=0, preserved=0, cancelled=0, flagged=0):
        merge_result = MagicMock()
        merge_result.tasks_created = created
        merge_result.tasks_updated = updated
        merge_result.tasks_preserved = preserved
        merge_result.tasks_cancelled = cancelled
        merge_result.tasks_flagged = flagged
        merge_result.results = []
        merge_result.warnings = []
        self.mock_merge.return_value.merge_all.return_value = merge_result
        return merge_result

    @pytest.mark.unit
    def test_smart_merge_case_a_insert(self, client, mock_excel_file):
        self.set_merge_result(created=10)
        response = client.post("/import/upload", files={"file": ("test.xlsx", mock_excel_file, "")})
        assert response.json()["summary"]["tasks_created"] == 10

    @pytest.mark.unit
    def test_smart_merge_case_b_update(self, client, mock_excel_file):
        self.set_merge_result(updated=5, preserved=2)
        response = client.post("/import/upload", files={"file": ("test.xlsx", mock_excel_file, "")})
        assert response.json()["summary"]["tasks_updated"] == 5

    @pytest.mark.unit
    def test_smart_merge_case_c_ghost_cancel(self, client, mock_excel_file):
        self.set_merge_result(cancelled=3)
        response = client.post(
            "/import/upload", 
            files={"file": ("test.xlsx", mock_excel_file, "")},
            params={"perform_ghost_check": True}
        )
        assert response.json()["summary"]["tasks_cancelled"] == 3

    @pytest.mark.unit
    def test_smart_merge_case_c_ghost_flag(self, client, mock_excel_file):
        res = self.set_merge_result(flagged=2)
        flag1 = MagicMock(action="flagged", external_id="T1", flag_message="Msg", work_item_id=str(uuid4()))
        flag1.to_dict.return_value = {"external_id": "T1", "decision": "FLAG"}
        flag1.external_id = "T1"
        flag1.decision = "FLAG"
        res.results = [flag1]
        
        response = client.post("/import/upload", files={"file": ("test.xlsx", mock_excel_file, "")})
        assert response.json()["summary"]["tasks_flagged"] == 2

    @pytest.mark.unit
    def test_smart_merge_preserve_status(self, client, mock_excel_file):
        self.set_merge_result(preserved=5)
        response = client.post("/import/upload", files={"file": ("test.xlsx", mock_excel_file, "")})
        assert response.json()["summary"]["tasks_preserved"] == 5

    @pytest.mark.unit
    def test_smart_merge_completed_preserved(self, client, mock_excel_file):
        res = self.set_merge_result(preserved=1)
        res.results = [MagicMock(action="preserved", external_id="T1", message="Completed task preserved")]
        response = client.post("/import/upload", files={"file": ("test.xlsx", mock_excel_file, "")})
        assert response.status_code == 200

    @pytest.mark.unit
    def test_smart_merge_resource_reassignment(self, client, mock_excel_file):
        """Test resource reassignment handling."""
        res = self.set_merge_result(updated=1)
        res.results = [MagicMock(action="updated", message="Resource re-assigned")]
        response = client.post("/import/upload", files={"file": ("test.xlsx", mock_excel_file, "")})
        assert response.status_code == 200

    @pytest.mark.unit
    def test_smart_merge_with_dependencies(self, client, mock_excel_file):
        """Test with dependencies."""
        self.mock_dep.return_value.sync_all.return_value = (5, [])
        self.mock_parser.return_value.parse.return_value = {
            "work_items": [], "resources": [], "dependencies": [{"id": 1}]
        }
        
        response = client.post("/import/upload", files={"file": ("test.xlsx", mock_excel_file, "")})
        assert response.status_code == 200
        assert response.json()["summary"]["dependencies_synced"] == 5

    @pytest.mark.unit
    def test_smart_merge_preserve_completion(self, client, mock_excel_file):
        """Test preservation of completion percentage (simulated via result)."""
        res = self.set_merge_result(preserved=1)
        res.results = [MagicMock(action="preserved", message="Completion % not overwritten")]
        response = client.post("/import/upload", files={"file": ("test.xlsx", mock_excel_file, "")})
        assert response.status_code == 200


# ==========================================
# IMPORT BATCHES TESTS
# ==========================================

class TestImportBatches:
    
    @pytest.mark.unit
    def test_list_batches_empty(self, client, mock_data):
        mock_data["import_batches"] = []
        response = client.get("/import/batches")
        assert len(response.json()["batches"]) == 0

    @pytest.mark.unit
    def test_list_batches_with_data(self, client, mock_data):
        mock_data["import_batches"] = [
            {"id": str(uuid4()), "status": "success", "created_at": "2024-01-01"},
            {"id": str(uuid4()), "status": "failed", "created_at": "2024-01-02"}
        ]
        response = client.get("/import/batches")
        assert len(response.json()["batches"]) == 2

    @pytest.mark.unit
    def test_get_batch_success(self, client, mock_data):
        batch_id = str(uuid4())
        mock_data["import_batches"] = [{"id": batch_id, "status": "success", "created_at": "2024-01-01"}]
        response = client.get(f"/import/batches/{batch_id}")
        assert response.json()["batch"]["id"] == batch_id
    
    @pytest.mark.unit
    def test_get_batch_not_found(self, client, mock_data):
        mock_data["import_batches"] = []
        response = client.get(f"/import/batches/{str(uuid4())}")
        assert response.status_code == 404


# ==========================================
# FLAGGED ITEMS TESTS
# ==========================================

class TestFlaggedItems:
    
    @pytest.mark.unit
    def test_get_flagged_items_empty(self, client, mock_data):
        response = client.get(f"/import/flagged?program_id={str(uuid4())}")
        assert len(response.json()["items"]) == 0
    
    @pytest.mark.unit
    def test_get_flagged_items_with_data(self, client, mock_data):
        mock_data["work_items"] = [
            {"id": str(uuid4()), "external_id": "FLAG-001", "review_message": "Needs Review", "status": "In Progress"}
        ]
        response = client.get(f"/import/flagged?program_id={str(uuid4())}")
        assert len(response.json()["items"]) == 1

    @pytest.mark.unit
    def test_resolve_flagged_item_cancel(self, client, mock_data):
        wid = str(uuid4())
        mock_data["work_items"] = [{"id": wid, "review_message": "Review", "status": "In Progress"}]
        
        # CORRECTED: Use Params and Title Case "Cancelled"
        response = client.post(
            f"/import/flagged/{wid}/resolve",
            params={"new_status": "Cancelled", "resolution_note": "Obsolete"}
        )
        assert response.status_code == 200
        assert response.json()["work_item"]["status"] == "Cancelled"

    @pytest.mark.unit
    def test_resolve_flagged_item_continue(self, client, mock_data):
        wid = str(uuid4())
        mock_data["work_items"] = [{"id": wid, "review_message": "Review", "status": "In Progress"}]
        
        # CORRECTED: Use Params and Title Case "In Progress"
        response = client.post(
            f"/import/flagged/{wid}/resolve",
            params={"new_status": "In Progress", "resolution_note": "Keep it"}
        )
        assert response.status_code == 200
        assert response.json()["work_item"]["status"] == "In Progress"

    @pytest.mark.unit
    def test_resolve_flagged_item_invalid_status(self, client, mock_data):
        wid = str(uuid4())
        # CORRECTED: Use Params and Title Case "In Progress"
        response = client.post(
            f"/import/flagged/{wid}/resolve",
            params={"new_status": "INVALID_STATUS"}
        )
        assert response.status_code == 400


# ==========================================
# BASELINE & UTILIZATION
# ==========================================

class TestBaselineVersions:
    @pytest.mark.unit
    def test_list_baselines_with_data(self, client, mock_data):
        pid = str(uuid4())
        mock_data["baseline_versions"] = [{"program_id": pid, "id": str(uuid4())}]
        response = client.get(f"/import/baseline-versions?program_id={pid}")
        assert len(response.json()["versions"]) == 1

    @pytest.mark.unit
    def test_list_baselines_empty(self, client, mock_data):
        response = client.get(f"/import/baseline-versions?program_id={str(uuid4())}")
        assert len(response.json()["versions"]) == 0

class TestResourceUtilization:
    @pytest.mark.unit
    def test_get_utilization(self, client, mock_data):
        mock_data["resource_utilization"] = [{"resource_name": "A", "utilization": 120, "utilization_status": "Over-Allocated"}]
        response = client.get("/import/resource-utilization")
        assert response.json()["over_allocated_count"] == 1

    @pytest.mark.unit
    def test_get_utilization_empty(self, client, mock_data):
        mock_data["resource_utilization"] = []
        response = client.get("/import/resource-utilization")
        assert response.json()["total_resources"] == 0
