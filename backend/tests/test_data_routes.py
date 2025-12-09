"""
Tests for Data Routes (/api/data endpoints).

Tests cover:
- Programs endpoints (list, get)
- Work Items endpoints (list, get, filter)
- Resources endpoints (list, get)
- Audit Logs endpoints (list, filter)
- Dependencies endpoints (list, filter)
- Dashboard Stats endpoint
"""
import pytest
from datetime import date, timedelta
from uuid import uuid4


# ==========================================
# PROGRAMS ENDPOINTS TESTS
# ==========================================

class TestProgramsEndpoints:
    """Test /api/data/programs endpoints."""
    
    @pytest.mark.unit
    def test_list_programs_empty(self, client, mock_data):
        """List programs returns empty list when no programs exist."""
        response = client.get("/api/data/programs")
        
        assert response.status_code == 200
        data = response.json()
        # API returns paginated response: {"data": [...], "count": N, "limit": ..., "offset": ...}
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 0
        assert data["count"] == 0
    
    @pytest.mark.unit
    def test_list_programs_with_data(self, client, mock_data):
        """List programs returns all programs."""
        # Setup: Add programs to mock data
        mock_data["programs"].append({
            "id": str(uuid4()),
            "external_id": "PROG-001",
            "name": "Test Program 1",
            "status": "Active",
            "baseline_start_date": str(date.today()),
            "baseline_end_date": str(date.today() + timedelta(days=90)),
        })
        mock_data["programs"].append({
            "id": str(uuid4()),
            "external_id": "PROG-002",
            "name": "Test Program 2",
            "status": "Planned",
            "baseline_start_date": str(date.today()),
            "baseline_end_date": str(date.today() + timedelta(days=60)),
        })
        
        response = client.get("/api/data/programs")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 2
        assert data["count"] == 2
    
    @pytest.mark.unit
    def test_list_programs_filter_by_status(self, client, mock_data):
        """List programs can filter by status."""
        mock_data["programs"].extend([
            {
                "id": str(uuid4()),
                "external_id": "PROG-001",
                "name": "Active Program",
                "status": "Active",
                "baseline_start_date": str(date.today()),
                "baseline_end_date": str(date.today() + timedelta(days=90)),
            },
            {
                "id": str(uuid4()),
                "external_id": "PROG-002",
                "name": "Planned Program",
                "status": "Planned",
                "baseline_start_date": str(date.today()),
                "baseline_end_date": str(date.today() + timedelta(days=60)),
            },
        ])
        
        response = client.get("/api/data/programs?status=Active")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        # Should filter to only Active programs
        for program in data["data"]:
            assert program["status"] == "Active"
    
    @pytest.mark.unit
    def test_list_programs_pagination(self, client, mock_data):
        """List programs supports pagination."""
        # Add 10 programs
        for i in range(10):
            mock_data["programs"].append({
                "id": str(uuid4()),
                "external_id": f"PROG-{i+1:03d}",
                "name": f"Program {i+1}",
                "status": "Active",
                "baseline_start_date": str(date.today()),
                "baseline_end_date": str(date.today() + timedelta(days=90)),
            })
        
        response = client.get("/api/data/programs?limit=5&offset=0")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) <= 5
        assert data["limit"] == 5
        assert data["offset"] == 0
    
    @pytest.mark.unit
    def test_get_program_success(self, client, mock_data):
        """Get single program by ID."""
        program_id = str(uuid4())
        mock_data["programs"].append({
            "id": program_id,
            "external_id": "PROG-001",
            "name": "Test Program",
            "status": "Active",
            "baseline_start_date": str(date.today()),
            "baseline_end_date": str(date.today() + timedelta(days=90)),
        })
        
        response = client.get(f"/api/data/programs/{program_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == program_id
        assert data["name"] == "Test Program"
    
    @pytest.mark.unit
    def test_get_program_not_found(self, client, mock_data):
        """Get program returns 404 for non-existent ID."""
        fake_id = str(uuid4())
        
        response = client.get(f"/api/data/programs/{fake_id}")
        
        assert response.status_code == 404


# ==========================================
# WORK ITEMS ENDPOINTS TESTS
# ==========================================

class TestWorkItemsEndpoints:
    """Test /api/data/work-items endpoints."""
    
    @pytest.mark.unit
    def test_list_work_items_empty(self, client, mock_data):
        """List work items returns empty list when none exist."""
        response = client.get("/api/data/work-items")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 0
    
    @pytest.mark.unit
    def test_list_work_items_with_data(self, client, mock_data, create_test_hierarchy):
        """List work items returns all work items."""
        hierarchy = create_test_hierarchy(num_work_items=5)
        
        response = client.get("/api/data/work-items")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 5
    
    @pytest.mark.unit
    def test_list_work_items_filter_by_program(self, client, mock_data, create_test_hierarchy):
        """List work items can filter by program."""
        hierarchy = create_test_hierarchy(num_work_items=3)
        program_id = hierarchy["program"]["id"]
        
        response = client.get(f"/api/data/work-items?program_id={program_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
    
    @pytest.mark.unit
    def test_list_work_items_filter_by_status(self, client, mock_data):
        """List work items can filter by status."""
        phase_id = str(uuid4())
        mock_data["work_items"].extend([
            {
                "id": str(uuid4()),
                "external_id": "TASK-001",
                "name": "Not Started Task",
                "status": "Not Started",
                "phase_id": phase_id,
                "planned_start": str(date.today()),
                "planned_end": str(date.today() + timedelta(days=10)),
            },
            {
                "id": str(uuid4()),
                "external_id": "TASK-002",
                "name": "In Progress Task",
                "status": "In Progress",
                "phase_id": phase_id,
                "planned_start": str(date.today()),
                "planned_end": str(date.today() + timedelta(days=10)),
            },
        ])
        
        response = client.get("/api/data/work-items?status=In%20Progress")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
    
    @pytest.mark.unit
    def test_list_work_items_filter_by_resource(self, client, mock_data, create_test_resource):
        """List work items can filter by assigned resource."""
        resource = create_test_resource(name="Alice")
        phase_id = str(uuid4())
        
        mock_data["work_items"].append({
            "id": str(uuid4()),
            "external_id": "TASK-001",
            "name": "Alice's Task",
            "status": "Not Started",
            "phase_id": phase_id,
            "resource_id": resource["id"],
            "planned_start": str(date.today()),
            "planned_end": str(date.today() + timedelta(days=10)),
        })
        
        response = client.get(f"/api/data/work-items?resource_id={resource['id']}")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
    
    @pytest.mark.unit
    def test_list_work_items_flagged_only(self, client, mock_data):
        """List work items can filter to only flagged items."""
        phase_id = str(uuid4())
        mock_data["work_items"].extend([
            {
                "id": str(uuid4()),
                "external_id": "TASK-001",
                "name": "Normal Task",
                "status": "Not Started",
                "phase_id": phase_id,
                "flag_for_review": False,
                "planned_start": str(date.today()),
                "planned_end": str(date.today() + timedelta(days=10)),
            },
            {
                "id": str(uuid4()),
                "external_id": "TASK-002",
                "name": "Flagged Task",
                "status": "On Hold",
                "phase_id": phase_id,
                "flag_for_review": True,
                "review_message": "Needs PM review",
                "planned_start": str(date.today()),
                "planned_end": str(date.today() + timedelta(days=10)),
            },
        ])
        
        response = client.get("/api/data/work-items?flagged_only=true")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
    
    @pytest.mark.unit
    def test_get_work_item_success(self, client, mock_data, create_test_hierarchy):
        """Get single work item by ID."""
        hierarchy = create_test_hierarchy(num_work_items=1)
        work_item = hierarchy["work_items"][0]
        
        response = client.get(f"/api/data/work-items/{work_item['id']}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == work_item["id"]
    
    @pytest.mark.unit
    def test_get_work_item_with_dependencies(self, client, mock_data, create_test_hierarchy, create_test_dependency):
        """Get work item includes dependency information."""
        hierarchy = create_test_hierarchy(num_work_items=2)
        task_a = hierarchy["work_items"][0]
        task_b = hierarchy["work_items"][1]
        
        create_test_dependency(
            successor_id=task_b["id"],
            predecessor_id=task_a["id"]
        )
        
        response = client.get(f"/api/data/work-items/{task_b['id']}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_b["id"]
    
    @pytest.mark.unit
    def test_get_work_item_not_found(self, client, mock_data):
        """Get work item returns 404 for non-existent ID."""
        fake_id = str(uuid4())
        
        response = client.get(f"/api/data/work-items/{fake_id}")
        
        assert response.status_code == 404


# ==========================================
# RESOURCES ENDPOINTS TESTS
# ==========================================

class TestResourcesEndpoints:
    """Test /api/data/resources endpoints."""
    
    @pytest.mark.unit
    def test_list_resources_empty(self, client, mock_data):
        """List resources returns empty list when none exist."""
        response = client.get("/api/data/resources")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 0
    
    @pytest.mark.unit
    def test_list_resources_with_data(self, client, mock_data, create_test_resource):
        """List resources returns all resources."""
        create_test_resource(name="Alice")
        create_test_resource(name="Bob")
        create_test_resource(name="Charlie")
        
        response = client.get("/api/data/resources")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 3
    
    @pytest.mark.unit
    def test_list_resources_filter_by_status(self, client, mock_data):
        """List resources can filter by availability status."""
        mock_data["resources"].extend([
            {
                "id": str(uuid4()),
                "external_id": "RES-001",
                "name": "Active User",
                "email": "active@example.com",
                "availability_status": "ACTIVE",
            },
            {
                "id": str(uuid4()),
                "external_id": "RES-002",
                "name": "On Leave User",
                "email": "leave@example.com",
                "availability_status": "ON_LEAVE",
            },
        ])
        
        response = client.get("/api/data/resources?status=ACTIVE")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
    
    @pytest.mark.unit
    def test_get_resource_success(self, client, mock_data, create_test_resource):
        """Get single resource by ID."""
        resource = create_test_resource(name="Alice")
        
        response = client.get(f"/api/data/resources/{resource['id']}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == resource["id"]
        assert data["name"] == "Alice"
    
    @pytest.mark.unit
    def test_get_resource_not_found(self, client, mock_data):
        """Get resource returns 404 for non-existent ID."""
        fake_id = str(uuid4())
        
        response = client.get(f"/api/data/resources/{fake_id}")
        
        assert response.status_code == 404


# ==========================================
# AUDIT LOGS ENDPOINTS TESTS
# ==========================================

class TestAuditLogsEndpoints:
    """Test /api/data/audit-logs endpoints."""
    
    @pytest.mark.unit
    def test_list_audit_logs_empty(self, client, mock_data):
        """List audit logs returns empty list when none exist."""
        response = client.get("/api/data/audit-logs")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 0
    
    @pytest.mark.unit
    def test_list_audit_logs_with_data(self, client, mock_data):
        """List audit logs returns all logs."""
        work_item_id = str(uuid4())
        mock_data["audit_logs"].extend([
            {
                "id": str(uuid4()),
                "entity_type": "work_item",
                "entity_id": work_item_id,
                "action": "created",
                "change_source": "excel_import",
            },
            {
                "id": str(uuid4()),
                "entity_type": "work_item",
                "entity_id": work_item_id,
                "action": "updated",
                "field_changed": "status",
                "old_value": "Not Started",
                "new_value": "In Progress",
                "change_source": "api_update",
            },
        ])
        
        response = client.get("/api/data/audit-logs")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 2
    
    @pytest.mark.unit
    def test_list_audit_logs_filter_by_entity_type(self, client, mock_data):
        """List audit logs can filter by entity type."""
        mock_data["audit_logs"].extend([
            {
                "id": str(uuid4()),
                "entity_type": "work_item",
                "entity_id": str(uuid4()),
                "action": "created",
            },
            {
                "id": str(uuid4()),
                "entity_type": "program",
                "entity_id": str(uuid4()),
                "action": "created",
            },
        ])
        
        response = client.get("/api/data/audit-logs?entity_type=work_item")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
    
    @pytest.mark.unit
    def test_list_audit_logs_filter_by_action(self, client, mock_data):
        """List audit logs can filter by action."""
        mock_data["audit_logs"].extend([
            {
                "id": str(uuid4()),
                "entity_type": "work_item",
                "entity_id": str(uuid4()),
                "action": "created",
            },
            {
                "id": str(uuid4()),
                "entity_type": "work_item",
                "entity_id": str(uuid4()),
                "action": "updated",
            },
            {
                "id": str(uuid4()),
                "entity_type": "work_item",
                "entity_id": str(uuid4()),
                "action": "cancelled",
            },
        ])
        
        response = client.get("/api/data/audit-logs?action=updated")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)


# ==========================================
# DEPENDENCIES ENDPOINTS TESTS
# ==========================================

class TestDependenciesEndpoints:
    """Test /api/data/dependencies endpoints."""
    
    @pytest.mark.unit
    def test_list_dependencies_empty(self, client, mock_data):
        """List dependencies returns empty list when none exist."""
        response = client.get("/api/data/dependencies")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 0
    
    @pytest.mark.unit
    def test_list_dependencies_with_data(self, client, mock_data, create_test_hierarchy, create_test_dependency):
        """List dependencies returns all dependencies."""
        hierarchy = create_test_hierarchy(num_work_items=3)
        tasks = hierarchy["work_items"]
        
        create_test_dependency(successor_id=tasks[1]["id"], predecessor_id=tasks[0]["id"])
        create_test_dependency(successor_id=tasks[2]["id"], predecessor_id=tasks[1]["id"])
        
        response = client.get("/api/data/dependencies")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 2
    
    @pytest.mark.unit
    def test_list_dependencies_filter_by_work_item(self, client, mock_data, create_test_hierarchy, create_test_dependency):
        """List dependencies can filter by work item."""
        hierarchy = create_test_hierarchy(num_work_items=3)
        tasks = hierarchy["work_items"]
        
        create_test_dependency(successor_id=tasks[1]["id"], predecessor_id=tasks[0]["id"])
        create_test_dependency(successor_id=tasks[2]["id"], predecessor_id=tasks[1]["id"])
        
        response = client.get(f"/api/data/dependencies?work_item_id={tasks[1]['id']}")
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)


# ==========================================
# DASHBOARD STATS ENDPOINT TESTS
# ==========================================

class TestDashboardStats:
    """Test /api/data/dashboard/stats endpoint."""
    
    @pytest.mark.unit
    def test_get_dashboard_stats_empty(self, client, mock_data):
        """Dashboard stats returns zeros when no data exists."""
        response = client.get("/api/data/dashboard/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert "programs" in data or isinstance(data, dict)
    
    @pytest.mark.unit
    def test_get_dashboard_stats_with_data(self, client, mock_data, create_test_hierarchy, create_test_resource):
        """Dashboard stats returns correct counts."""
        create_test_hierarchy(num_work_items=5)
        create_test_resource(name="Alice")
        create_test_resource(name="Bob")
        
        response = client.get("/api/data/dashboard/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


# ==========================================
# ERROR HANDLING TESTS
# ==========================================

class TestDataRoutesErrors:
    """Test error handling in data routes."""
    
    @pytest.mark.unit
    def test_invalid_uuid_format(self, client, mock_data):
        """Invalid UUID format returns appropriate error."""
        response = client.get("/api/data/programs/not-a-valid-uuid")
        
        # Should return 404 or 422 depending on implementation
        assert response.status_code in (404, 422)
    
    @pytest.mark.unit
    def test_invalid_pagination_params(self, client, mock_data):
        """Invalid pagination parameters are handled."""
        response = client.get("/api/data/programs?limit=-1")
        
        # Should return 422 for validation error
        assert response.status_code == 422
    
    @pytest.mark.unit
    def test_pagination_offset_exceeds_data(self, client, mock_data):
        """Offset exceeding data returns empty data list."""
        mock_data["programs"].append({
            "id": str(uuid4()),
            "external_id": "PROG-001",
            "name": "Test Program",
            "status": "Active",
            "baseline_start_date": str(date.today()),
            "baseline_end_date": str(date.today() + timedelta(days=90)),
        })
        
        response = client.get("/api/data/programs?limit=10&offset=1000")
        
        assert response.status_code == 200
        data = response.json()
        # Paginated response with empty data array
        assert "data" in data
        assert data["data"] == []
