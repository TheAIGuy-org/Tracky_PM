"""
Tests for Resource Routes (/api/resources endpoints).

Based on actual resource_routes.py implementation analysis:
- Endpoints: list, get, update, hierarchy tree, set manager, set backup, set availability, escalation chain, direct reports
- Response formats verified from source code
- Validation logic: UUID format, circular hierarchy, self-backup prevention, ON_LEAVE date requirements
"""
import pytest
from datetime import date
from uuid import uuid4
from unittest.mock import MagicMock, patch


# ==========================================
# RESOURCE CRUD TESTS
# ==========================================

class TestResourceCRUD:
    
    @pytest.mark.unit
    def test_list_resources_empty(self, client, mock_data):
        """List resources when none exist."""
        mock_data["resources"] = []
        response = client.get("/api/resources")
        assert response.status_code == 200
        assert response.json()["resources"] == []
        assert response.json()["count"] == 0

    @pytest.mark.unit
    def test_list_resources_with_data(self, client, mock_data):
        """List resources with data."""
        mock_data["resources"] = [
            {"id": str(uuid4()), "name": "Alice", "email": "alice@test.com", "availability_status": "ACTIVE"},
            {"id": str(uuid4()), "name": "Bob", "email": "bob@test.com", "availability_status": "ON_LEAVE"}
        ]
        response = client.get("/api/resources")
        assert response.status_code == 200
        assert response.json()["count"] == 2

    @pytest.mark.unit
    def test_list_resources_search(self, client, mock_data):
        """Search resources by name/email."""
        mock_data["resources"] = [
            {"id": "1", "name": "Alice Smith", "email": "alice@test.com"},
            {"id": "2", "name": "Bob Jones", "email": "bob@test.com"}
        ]
        # Note: The actual search uses .or_() which mock_data may not fully support
        # This tests the endpoint structure
        response = client.get("/api/resources?search=Alice")
        assert response.status_code == 200

    @pytest.mark.unit
    def test_list_resources_filter_availability(self, client, mock_data):
        """Filter resources by availability status."""
        mock_data["resources"] = [
            {"id": "1", "name": "Alice", "availability_status": "ACTIVE"},
            {"id": "2", "name": "Bob", "availability_status": "ON_LEAVE"}
        ]
        response = client.get("/api/resources?availability_status=ACTIVE")
        assert response.status_code == 200
        # MockSupabaseClient should filter by availability_status
        assert all(r["availability_status"] == "ACTIVE" for r in response.json()["resources"])

    @pytest.mark.unit
    def test_get_resource_success(self, client, mock_data):
        """Get single resource by ID."""
        rid = str(uuid4())
        mock_data["resources"] = [{
            "id": rid, 
            "name": "Alice", 
            "email": "alice@test.com",
            "manager_id": None,
            "backup_resource_id": None,
            "manager": None,
            "backup": None
        }]
        response = client.get(f"/api/resources/{rid}")
        assert response.status_code == 200
        assert response.json()["name"] == "Alice"
        assert "direct_reports" in response.json()

    @pytest.mark.unit
    def test_get_resource_not_found(self, client, mock_data):
        """404 for non-existent resource."""
        mock_data["resources"] = []
        response = client.get(f"/api/resources/{str(uuid4())}")
        assert response.status_code == 404

    @pytest.mark.unit
    def test_get_resource_invalid_uuid(self, client):
        """422 for invalid UUID format."""
        response = client.get("/api/resources/not-a-uuid")
        assert response.status_code == 422
        assert "Invalid resource ID format" in response.json()["detail"]

    @pytest.mark.unit
    def test_update_resource_name(self, client, mock_data):
        """Update resource name."""
        rid = str(uuid4())
        mock_data["resources"] = [{"id": rid, "name": "Old Name", "email": "test@test.com"}]
        response = client.put(f"/api/resources/{rid}", json={"name": "New Name"})
        assert response.status_code == 200
        assert response.json()["success"] == True

    @pytest.mark.unit
    def test_update_resource_email(self, client, mock_data):
        """Update resource email."""
        rid = str(uuid4())
        mock_data["resources"] = [{"id": rid, "name": "Test", "email": "old@test.com"}]
        response = client.put(f"/api/resources/{rid}", json={"email": "new@test.com"})
        assert response.status_code == 200
        assert response.json()["success"] == True

    @pytest.mark.unit
    def test_update_resource_not_found(self, client, mock_data):
        """404 when updating non-existent resource."""
        mock_data["resources"] = []
        response = client.put(f"/api/resources/{str(uuid4())}", json={"name": "Test"})
        assert response.status_code == 404


# ==========================================
# MANAGER HIERARCHY TESTS
# ==========================================

class TestManagerHierarchy:
    
    @pytest.mark.unit
    def test_get_hierarchy_tree_empty(self, client, mock_data):
        """Get hierarchy tree when no resources exist."""
        mock_data["resources"] = []
        response = client.get("/api/resources/hierarchy/tree")
        assert response.status_code == 200
        assert response.json()["roots"] == []
        assert response.json()["total_resources"] == 0

    @pytest.mark.unit
    def test_get_hierarchy_tree_with_data(self, client, mock_data):
        """Get hierarchy tree with manager relationships."""
        mgr_id = str(uuid4())
        emp_id = str(uuid4())
        mock_data["resources"] = [
            {"id": mgr_id, "name": "Manager", "email": "mgr@test.com", "manager_id": None, "availability_status": "ACTIVE"},
            {"id": emp_id, "name": "Employee", "email": "emp@test.com", "manager_id": mgr_id, "availability_status": "ACTIVE"}
        ]
        response = client.get("/api/resources/hierarchy/tree")
        assert response.status_code == 200
        assert response.json()["total_resources"] == 2
        # Manager should be a root, employee should be child
        roots = response.json()["roots"]
        assert len(roots) == 1
        assert roots[0]["id"] == mgr_id
        assert len(roots[0]["children"]) == 1

    @pytest.mark.unit
    def test_set_manager_success(self, client, mock_data):
        """Set manager successfully."""
        rid = str(uuid4())
        mgr_id = str(uuid4())
        mock_data["resources"] = [
            {"id": rid, "name": "Employee", "manager_id": None},
            {"id": mgr_id, "name": "Manager", "manager_id": None}
        ]
        response = client.post(f"/api/resources/{rid}/manager", json={"manager_id": mgr_id})
        assert response.status_code == 200
        assert response.json()["success"] == True
        assert response.json()["manager_id"] == mgr_id

    @pytest.mark.unit
    def test_set_manager_remove(self, client, mock_data):
        """Remove manager (set to null)."""
        rid = str(uuid4())
        mgr_id = str(uuid4())
        mock_data["resources"] = [
            {"id": rid, "name": "Employee", "manager_id": mgr_id},
            {"id": mgr_id, "name": "Manager", "manager_id": None}
        ]
        response = client.post(f"/api/resources/{rid}/manager", json={"manager_id": None})
        assert response.status_code == 200
        assert response.json()["manager_id"] is None

    @pytest.mark.unit
    def test_set_manager_circular(self, client, mock_data):
        """Prevent circular manager hierarchy."""
        rid = str(uuid4())
        mgr_id = str(uuid4())
        # Employee manages Manager, trying to set Manager as Employee's manager would be circular
        mock_data["resources"] = [
            {"id": rid, "name": "Employee", "manager_id": None},
            {"id": mgr_id, "name": "Manager", "manager_id": rid}  # Mgr reports to Employee
        ]
        response = client.post(f"/api/resources/{rid}/manager", json={"manager_id": mgr_id})
        assert response.status_code == 400
        assert "circular" in response.json()["detail"].lower()

    @pytest.mark.unit
    def test_set_manager_self(self, client, mock_data):
        """Prevent setting self as manager."""
        rid = str(uuid4())
        mock_data["resources"] = [{"id": rid, "name": "Test", "manager_id": None}]
        response = client.post(f"/api/resources/{rid}/manager", json={"manager_id": rid})
        assert response.status_code == 400
        assert "own manager" in response.json()["detail"].lower()


# ==========================================
# BACKUP ASSIGNMENT TESTS
# ==========================================

class TestBackupAssignment:
    
    @pytest.mark.unit
    def test_set_backup_success(self, client, mock_data):
        """Set backup resource successfully."""
        rid = str(uuid4())
        backup_id = str(uuid4())
        mock_data["resources"] = [
            {"id": rid, "name": "Primary", "backup_resource_id": None},
            {"id": backup_id, "name": "Backup", "backup_resource_id": None}
        ]
        response = client.post(f"/api/resources/{rid}/backup", json={"backup_resource_id": backup_id})
        assert response.status_code == 200
        assert response.json()["success"] == True
        assert response.json()["backup_resource_id"] == backup_id

    @pytest.mark.unit
    def test_set_backup_remove(self, client, mock_data):
        """Remove backup resource."""
        rid = str(uuid4())
        backup_id = str(uuid4())
        mock_data["resources"] = [
            {"id": rid, "name": "Primary", "backup_resource_id": backup_id},
            {"id": backup_id, "name": "Backup", "backup_resource_id": None}
        ]
        response = client.post(f"/api/resources/{rid}/backup", json={"backup_resource_id": None})
        assert response.status_code == 200
        assert response.json()["backup_resource_id"] is None

    @pytest.mark.unit
    def test_set_backup_self(self, client, mock_data):
        """Prevent setting self as backup."""
        rid = str(uuid4())
        mock_data["resources"] = [{"id": rid, "name": "Test", "backup_resource_id": None}]
        response = client.post(f"/api/resources/{rid}/backup", json={"backup_resource_id": rid})
        assert response.status_code == 400
        assert "own backup" in response.json()["detail"].lower()

    @pytest.mark.unit
    def test_set_backup_not_found(self, client, mock_data):
        """400 when backup resource doesn't exist."""
        rid = str(uuid4())
        mock_data["resources"] = [{"id": rid, "name": "Primary", "backup_resource_id": None}]
        response = client.post(f"/api/resources/{rid}/backup", json={"backup_resource_id": str(uuid4())})
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()


# ==========================================
# AVAILABILITY TESTS
# ==========================================

class TestAvailability:
    
    @pytest.mark.unit
    def test_set_availability_active(self, client, mock_data):
        """Set availability to ACTIVE."""
        rid = str(uuid4())
        mock_data["resources"] = [{"id": rid, "name": "Test", "availability_status": "ON_LEAVE"}]
        response = client.post(f"/api/resources/{rid}/availability", json={"availability_status": "ACTIVE"})
        assert response.status_code == 200
        assert response.json()["availability_status"] == "ACTIVE"

    @pytest.mark.unit
    def test_set_availability_on_leave(self, client, mock_data):
        """Set availability to ON_LEAVE with dates."""
        rid = str(uuid4())
        mock_data["resources"] = [{"id": rid, "name": "Test", "availability_status": "ACTIVE"}]
        response = client.post(f"/api/resources/{rid}/availability", json={
            "availability_status": "ON_LEAVE",
            "leave_start_date": "2024-01-15",
            "leave_end_date": "2024-01-20"
        })
        assert response.status_code == 200
        assert response.json()["availability_status"] == "ON_LEAVE"
        assert response.json()["leave_start_date"] == "2024-01-15"

    @pytest.mark.unit
    def test_set_availability_on_leave_missing_date(self, client, mock_data):
        """ON_LEAVE requires leave_start_date."""
        rid = str(uuid4())
        mock_data["resources"] = [{"id": rid, "name": "Test", "availability_status": "ACTIVE"}]
        response = client.post(f"/api/resources/{rid}/availability", json={"availability_status": "ON_LEAVE"})
        assert response.status_code == 400
        assert "start date is required" in response.json()["detail"].lower()

    @pytest.mark.unit
    def test_set_availability_unavailable(self, client, mock_data):
        """Set availability to UNAVAILABLE."""
        rid = str(uuid4())
        mock_data["resources"] = [{"id": rid, "name": "Test", "availability_status": "ACTIVE"}]
        response = client.post(f"/api/resources/{rid}/availability", json={"availability_status": "UNAVAILABLE"})
        assert response.status_code == 200
        assert response.json()["availability_status"] == "UNAVAILABLE"

    @pytest.mark.unit
    def test_set_availability_invalid_status(self, client, mock_data):
        """400 for invalid availability status."""
        rid = str(uuid4())
        mock_data["resources"] = [{"id": rid, "name": "Test", "availability_status": "ACTIVE"}]
        response = client.post(f"/api/resources/{rid}/availability", json={"availability_status": "INVALID"})
        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]


# ==========================================
# ESCALATION CHAIN TESTS
# ==========================================

class TestEscalationChain:
    
    @pytest.mark.unit
    def test_get_escalation_chain_no_manager(self, client):
        """Get escalation chain when resource has no manager."""
        rid = str(uuid4())
        with patch("app.api.routes.resource_routes.get_escalation_chain") as mock_get_chain:
            mock_get_chain.return_value = []  # No escalation chain
            response = client.get(f"/api/resources/{rid}/escalation-chain")
            assert response.status_code == 200
            assert response.json()["chain"] == []

    @pytest.mark.unit
    def test_get_escalation_chain_with_manager(self, client):
        """Get escalation chain with manager."""
        rid = str(uuid4())
        with patch("app.api.routes.resource_routes.get_escalation_chain") as mock_get_chain:
            mock_target = MagicMock()
            mock_target.escalation_level = 1
            mock_target.target_type.value = "MANAGER"
            mock_target.resource_id = uuid4()
            mock_target.resource_name = "Manager Name"
            mock_target.email = "mgr@test.com"
            mock_target.is_available = True
            mock_target.availability_status = "ACTIVE"
            mock_get_chain.return_value = [mock_target]
            
            response = client.get(f"/api/resources/{rid}/escalation-chain")
            assert response.status_code == 200
            assert len(response.json()["chain"]) == 1
            assert response.json()["chain"][0]["level"] == 1


# ==========================================
# DIRECT REPORTS TESTS
# ==========================================

class TestDirectReports:
    
    @pytest.mark.unit
    def test_get_direct_reports_empty(self, client, mock_data):
        """Get direct reports when none exist."""
        rid = str(uuid4())
        mock_data["resources"] = [{"id": rid, "name": "Manager", "manager_id": None}]
        response = client.get(f"/api/resources/{rid}/direct-reports")
        assert response.status_code == 200
        assert response.json()["direct_reports"] == []
        assert response.json()["count"] == 0

    @pytest.mark.unit
    def test_get_direct_reports_with_data(self, client, mock_data):
        """List direct reports for a manager."""
        mgr_id = str(uuid4())
        emp1_id = str(uuid4())
        emp2_id = str(uuid4())
        mock_data["resources"] = [
            {"id": mgr_id, "name": "Manager", "manager_id": None},
            {"id": emp1_id, "name": "Employee 1", "manager_id": mgr_id, "email": "emp1@test.com", "availability_status": "ACTIVE"},
            {"id": emp2_id, "name": "Employee 2", "manager_id": mgr_id, "email": "emp2@test.com", "availability_status": "ON_LEAVE"}
        ]
        response = client.get(f"/api/resources/{mgr_id}/direct-reports")
        assert response.status_code == 200
        assert response.json()["count"] == 2
        assert response.json()["manager_id"] == mgr_id

    @pytest.mark.unit
    def test_get_direct_reports_not_found(self, client, mock_data):
        """404 when resource doesn't exist."""
        mock_data["resources"] = []
        response = client.get(f"/api/resources/{str(uuid4())}/direct-reports")
        assert response.status_code == 404
