"""
Pytest fixtures and configuration for Tracky PM tests.

Provides:
- Mock Supabase client for isolated testing
- Test client with dependency overrides
- Time freezing utilities
- Sample data fixtures
- Cleanup utilities
"""
import pytest
from datetime import date, datetime, timedelta
from typing import Generator, Dict, Any, Optional, List
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from freezegun import freeze_time

# Import the FastAPI app
from app.main import app


# ==========================================
# MOCK SUPABASE RESPONSE & TABLE
# ==========================================

class MockSupabaseResponse:
    """Mock response from Supabase operations."""
    
    def __init__(self, data: list = None, error: dict = None, count: int = None):
        self.data = data or []
        self.error = error
        self.count = count if count is not None else len(self.data)
    
    def execute(self):
        return self


class MockNotFilter:
    """Helper class to handle negated filters like .not_.in_()."""
    
    def __init__(self, table: "MockSupabaseTable"):
        self._table = table
    
    def in_(self, column: str, values: list):
        """Add a NOT IN filter."""
        self._table._filters.append(("not_in", column, values))
        return self._table
    
    def eq(self, column: str, value: Any):
        """Add a NOT EQ filter."""
        self._table._filters.append(("not_eq", column, value))
        return self._table


class MockSupabaseTable:
    """Mock Supabase table operations."""
    
    def __init__(self, table_name: str, mock_data: Dict[str, list]):
        self.table_name = table_name
        self.mock_data = mock_data
        self._filters = []
        self._select_fields = "*"
        self._order_by = None
        self._order_desc = False
        self._limit = None
        self._range_start = 0
        self._range_end = None
        self._or_filter = None
    
    def select(self, fields: str = "*", count: str = None):
        self._select_fields = fields
        self._count_mode = count
        return self
    
    def eq(self, column: str, value: Any):
        self._filters.append(("eq", column, value))
        return self
    
    def neq(self, column: str, value: Any):
        self._filters.append(("neq", column, value))
        return self
    
    def in_(self, column: str, values: list):
        self._filters.append(("in", column, values))
        return self
    
    def or_(self, filter_str: str):
        self._or_filter = filter_str
        return self
    
    def gte(self, column: str, value: Any):
        """Greater than or equal filter."""
        self._filters.append(("gte", column, value))
        return self
    
    def lte(self, column: str, value: Any):
        """Less than or equal filter."""
        self._filters.append(("lte", column, value))
        return self
    
    def is_(self, column: str, value: Any):
        """IS filter (for null checks)."""
        self._filters.append(("is", column, value))
        return self
    
    @property
    def not_(self):
        """Return a MockNotFilter for negation chaining (e.g., .not_.in_())."""
        return MockNotFilter(self)
    
    def order(self, column: str, desc: bool = False):
        self._order_by = column
        self._order_desc = desc
        return self
    
    def limit(self, count: int):
        self._limit = count
        return self
    
    def range(self, start: int, end: int):
        self._range_start = start
        self._range_end = end
        return self
    
    def insert(self, data: Any):
        """Mock insert operation."""
        if isinstance(data, list):
            for item in data:
                if "id" not in item:
                    item["id"] = str(uuid4())
                item["created_at"] = datetime.utcnow().isoformat()
            self.mock_data.setdefault(self.table_name, []).extend(data)
            return MockSupabaseResponse(data)
        else:
            if "id" not in data:
                data["id"] = str(uuid4())
            data["created_at"] = datetime.utcnow().isoformat()
            self.mock_data.setdefault(self.table_name, []).append(data)
            return MockSupabaseResponse([data])
    
    def upsert(self, data: Any, on_conflict: str = None):
        """Mock upsert operation."""
        if isinstance(data, list):
            results = []
            for item in data:
                existing = None
                for existing_item in self.mock_data.get(self.table_name, []):
                    if existing_item.get("external_id") == item.get("external_id"):
                        existing = existing_item
                        break
                
                if existing:
                    existing.update(item)
                    results.append(existing)
                else:
                    if "id" not in item:
                        item["id"] = str(uuid4())
                    item["created_at"] = datetime.utcnow().isoformat()
                    self.mock_data.setdefault(self.table_name, []).append(item)
                    results.append(item)
            return MockSupabaseResponse(results)
        else:
            return self.insert(data)
    
    def update(self, data: dict):
        """Mock update operation - returns self for chaining."""
        self._update_data = data
        return self
    
    def delete(self):
        """Mock delete operation - returns self for chaining."""
        self._delete = True
        return self
    
    def _apply_filters(self, results: list) -> list:
        """Apply all filters to results."""
        for op, column, value in self._filters:
            # Handle nested column access (e.g., "phases.projects.program_id")
            if "." in column:
                # For nested filters, just pass through (complex to simulate)
                continue
            
            if op == "eq":
                results = [r for r in results if r.get(column) == value]
            elif op == "neq":
                results = [r for r in results if r.get(column) != value]
            elif op == "in":
                results = [r for r in results if r.get(column) in value]
            elif op == "not_in":
                results = [r for r in results if r.get(column) not in value]
            elif op == "not_eq":
                results = [r for r in results if r.get(column) != value]
        
        return results
    
    def execute(self):
        """Execute the query and return results."""
        table_data = list(self.mock_data.get(self.table_name, []))
        
        # Apply filters
        results = self._apply_filters(table_data)
        
        # Handle update
        if hasattr(self, "_update_data"):
            for result in results:
                result.update(self._update_data)
                result["updated_at"] = datetime.utcnow().isoformat()
            return MockSupabaseResponse(results, count=len(results))
        
        # Handle delete
        if hasattr(self, "_delete"):
            for result in results:
                if result in self.mock_data.get(self.table_name, []):
                    self.mock_data[self.table_name].remove(result)
            return MockSupabaseResponse(results, count=len(results))
        
        # Apply ordering
        if self._order_by:
            results.sort(
                key=lambda x: x.get(self._order_by) or "", 
                reverse=self._order_desc
            )
        
        # Calculate count before pagination
        total_count = len(results)
        
        # Apply pagination (range)
        if self._range_end is not None:
            results = results[self._range_start:self._range_end + 1]
        elif self._limit:
            results = results[:self._limit]
        
        return MockSupabaseResponse(results, count=total_count)


class MockSupabaseClientInner:
    """Mock inner Supabase client (the actual client with table() method)."""
    
    def __init__(self, mock_data: Dict[str, list]):
        self.mock_data = mock_data
    
    def table(self, table_name: str) -> MockSupabaseTable:
        return MockSupabaseTable(table_name, self.mock_data)


class MockSupabaseClient:
    """
    Mock Supabase client wrapper (matches SupabaseClient class structure).
    This has a .client property that provides the actual table operations.
    """
    
    def __init__(self):
        self.mock_data: Dict[str, list] = {
            "programs": [],
            "projects": [],
            "phases": [],
            "work_items": [],
            "resources": [],
            "dependencies": [],
            "holidays": [],
            "audit_logs": [],
            "import_batches": [],
            "baseline_versions": [],
            "status_check_responses": [],
            "response_escalations": [],
            "resource_utilization": [],
        }
        # The .client property that routes expect
        self.client = MockSupabaseClientInner(self.mock_data)
    
    def table(self, table_name: str) -> MockSupabaseTable:
        """Direct table access (some code paths use this)."""
        return MockSupabaseTable(table_name, self.mock_data)
    
    def rpc(self, function_name: str, params: dict = None):
        """Mock RPC calls."""
        if function_name == "detect_circular_dependencies":
            return MockSupabaseResponse([])
        elif function_name == "calculate_critical_path":
            return MockSupabaseResponse([])
        elif function_name == "update_work_item_slack":
            return MockSupabaseResponse([], count=0)
        return MockSupabaseResponse([])
    
    def get_all_resource_utilization(self) -> List[Dict]:
        """Mock resource utilization query."""
        return self.mock_data.get("resource_utilization", [])
    
    def get_baseline_versions(self, program_id: str) -> List[Dict]:
        """Mock get baseline versions query."""
        return self.mock_data.get("baseline_versions", [])

    def transaction(self):
        """Mock transaction context manager."""
        return MockTransaction()
    
    def create_import_batch(self, **kwargs):
        """Mock create import batch."""
        batch = {
            "id": str(uuid4()),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            **kwargs
        }
        self.mock_data.setdefault("import_batches", []).append(batch)
        return batch
    
    def update_import_batch(self, batch_id: str, update_data: dict):
        """Mock update import batch."""
        for batch in self.mock_data.get("import_batches", []):
            if batch["id"] == batch_id:
                batch.update(update_data)
                return batch
        return None
        
    def set_current_batch_id(self, batch_id: str):
        """Mock setting current batch ID."""
        pass
        
    def create_baseline_version(self, **kwargs):
        """Mock create baseline version."""
        version = {
            "id": str(uuid4()),
            "created_at": datetime.utcnow().isoformat(),
            **kwargs
        }
        self.mock_data.setdefault("baseline_versions", []).append(version)
        return version

    def get_flagged_work_items(self, program_id: str) -> List[Dict]:
        """Mock get flagged items query."""
        # For simplicity, return items from mock data that have a review message
        flagged = []
        for item in self.mock_data.get("work_items", []):
            if item.get("review_message"):
                flagged.append(item)
        return flagged

    def resolve_flagged_item(self, work_item_id: str, new_status: str, resolution_note: str):
        """Mock resolve flagged item."""
        for item in self.mock_data.get("work_items", []):
            if item["id"] == work_item_id:
                item["status"] = new_status
                item["review_message"] = None  # Clear flag
                # Log resolution implicitly
                return item
        return None

    def log_audit(self, **kwargs):
        """Mock log audit."""
        log = {
            "id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            **kwargs
        }
        self.mock_data.setdefault("audit_logs", []).append(log)
        return log


class MockTransaction:
    """Mock transaction context manager."""
    def __init__(self):
        self.should_rollback = False
        self.mock_data = {}  # Prevent "no attribute mock_data" error
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
        """Mock get baseline versions query."""
        return self.mock_data.get("baseline_versions", [])
    
    def clear(self):
        """Clear all mock data."""
        for key in self.mock_data:
            self.mock_data[key] = []


# Global mock instance for patching
_mock_client = None


def get_mock_supabase_client():
    """Return the global mock client."""
    global _mock_client
    if _mock_client is None:
        _mock_client = MockSupabaseClient()
    return _mock_client


# ==========================================
# FIXTURES
# ==========================================

@pytest.fixture(scope="function")
def fresh_mock_client():
    """Function-scoped fresh mock client (clean for each test)."""
    global _mock_client
    _mock_client = MockSupabaseClient()
    return _mock_client


@pytest.fixture(scope="function")
def mock_data(fresh_mock_client) -> Dict[str, list]:
    """Access to the mock data store for direct manipulation."""
    return fresh_mock_client.mock_data


@pytest.fixture(scope="function")
def client(fresh_mock_client) -> Generator[TestClient, None, None]:
    """
    Create test client with mocked Supabase.
    
    Each test gets a fresh mock client with clean data.
    """
    # Patch at the module level where get_supabase_client is imported
    with patch("app.core.database.get_supabase_client", return_value=fresh_mock_client):
        with patch("app.api.routes.data_routes.get_supabase_client", return_value=fresh_mock_client):
            with patch("app.api.routes.import_routes.get_supabase_client", return_value=fresh_mock_client):
                with patch("app.api.routes.alert_routes.get_supabase_client", return_value=fresh_mock_client):
                    with patch("app.api.routes.resource_routes.get_supabase_client", return_value=fresh_mock_client):
                        with patch("app.api.routes.holiday_routes.get_supabase_client", return_value=fresh_mock_client):
                            with TestClient(app) as test_client:
                                yield test_client
    
    # Clear overrides after test
    app.dependency_overrides.clear()


# ==========================================
# TIME FIXTURES
# ==========================================

@pytest.fixture
def frozen_monday():
    """Freeze time at Monday 8:00 AM UTC (April 14, 2025)."""
    monday = datetime(2025, 4, 14, 8, 0, 0)
    with freeze_time(monday):
        yield monday


@pytest.fixture
def frozen_friday():
    """Freeze time at Friday 8:00 AM UTC (April 18, 2025)."""
    friday = datetime(2025, 4, 18, 8, 0, 0)
    with freeze_time(friday):
        yield friday


@pytest.fixture
def frozen_weekend():
    """Freeze time at Saturday 8:00 AM UTC (April 19, 2025)."""
    saturday = datetime(2025, 4, 19, 8, 0, 0)
    with freeze_time(saturday):
        yield saturday


@pytest.fixture
def next_monday_date() -> date:
    """Get the next Monday from today."""
    today = date.today()
    days_ahead = 0 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


@pytest.fixture
def next_friday_date() -> date:
    """Get the next Friday from today."""
    today = date.today()
    days_ahead = 4 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


# ==========================================
# SAMPLE DATA FIXTURES
# ==========================================

@pytest.fixture
def sample_program_data() -> Dict[str, Any]:
    """Sample program data."""
    return {
        "external_id": "PROG-001",
        "name": "Q2 Product Launch",
        "description": "Complete product launch initiative",
        "status": "Active",
        "baseline_start_date": str(date.today()),
        "baseline_end_date": str(date.today() + timedelta(days=90)),
        "program_owner": "John Smith",
        "priority": 1,
        "noise_threshold_days": 2,
    }


@pytest.fixture
def sample_project_data() -> Dict[str, Any]:
    """Sample project data."""
    return {
        "external_id": "PROJ-001",
        "name": "Backend Services",
        "program_id": None,
    }


@pytest.fixture
def sample_phase_data() -> Dict[str, Any]:
    """Sample phase data."""
    return {
        "external_id": "PHASE-001",
        "name": "Phase 1: Setup",
        "sequence": 1,
        "project_id": None,
    }


@pytest.fixture
def sample_work_item_data() -> Dict[str, Any]:
    """Sample work item data."""
    return {
        "external_id": "TASK-001",
        "name": "Database Migration",
        "planned_start": str(date.today()),
        "planned_end": str(date.today() + timedelta(days=10)),
        "current_start": str(date.today()),
        "current_end": str(date.today() + timedelta(days=10)),
        "planned_effort_hours": 40,
        "allocation_percent": 100,
        "status": "Not Started",
        "completion_percent": 0,
        "phase_id": None,
    }


@pytest.fixture
def sample_resource_data() -> Dict[str, Any]:
    """Sample resource data."""
    return {
        "external_id": "RES-001",
        "name": "Alice Johnson",
        "email": "alice@company.com",
        "role": "Senior Engineer",
        "availability_status": "ACTIVE",
        "max_utilization": 100,
    }


@pytest.fixture
def sample_holiday_data() -> Dict[str, Any]:
    """Sample holiday data."""
    return {
        "name": "Independence Day",
        "holiday_date": str(date(2025, 7, 4)),
        "country_code": "US",
        "holiday_type": "PUBLIC",
        "is_recurring": True,
    }


# ==========================================
# UTILITY FIXTURES
# ==========================================

@pytest.fixture
def create_test_hierarchy(mock_data):
    """
    Factory fixture to create a complete test hierarchy.
    
    Returns a function that creates program -> project -> phase -> work items.
    """
    def _create(
        num_work_items: int = 5,
        program_id: str = None,
        project_id: str = None,
        phase_id: str = None,
    ) -> Dict[str, Any]:
        program_id = program_id or str(uuid4())
        project_id = project_id or str(uuid4())
        phase_id = phase_id or str(uuid4())
        
        # Create program
        program = {
            "id": program_id,
            "external_id": "PROG-001",
            "name": "Test Program",
            "status": "Active",
            "baseline_start_date": str(date.today()),
            "baseline_end_date": str(date.today() + timedelta(days=90)),
            "created_at": datetime.utcnow().isoformat(),
        }
        mock_data["programs"].append(program)
        
        # Create project
        project = {
            "id": project_id,
            "external_id": "PROJ-001",
            "name": "Test Project",
            "program_id": program_id,
            "created_at": datetime.utcnow().isoformat(),
        }
        mock_data["projects"].append(project)
        
        # Create phase
        phase = {
            "id": phase_id,
            "external_id": "PHASE-001",
            "name": "Phase 1",
            "sequence": 1,
            "project_id": project_id,
            "created_at": datetime.utcnow().isoformat(),
        }
        mock_data["phases"].append(phase)
        
        # Create work items
        work_items = []
        for i in range(num_work_items):
            work_item = {
                "id": str(uuid4()),
                "external_id": f"TASK-{i+1:04d}",
                "name": f"Test Task {i+1}",
                "planned_start": str(date.today() + timedelta(days=i * 5)),
                "planned_end": str(date.today() + timedelta(days=i * 5 + 10)),
                "current_start": str(date.today() + timedelta(days=i * 5)),
                "current_end": str(date.today() + timedelta(days=i * 5 + 10)),
                "planned_effort_hours": 40,
                "allocation_percent": 100,
                "status": "Not Started",
                "completion_percent": 0,
                "phase_id": phase_id,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            mock_data["work_items"].append(work_item)
            work_items.append(work_item)
        
        return {
            "program": program,
            "project": project,
            "phase": phase,
            "work_items": work_items,
        }
    
    return _create


@pytest.fixture
def create_test_resource(mock_data):
    """Factory fixture to create test resources."""
    def _create(
        name: str = "Test User",
        email: str = None,
        role: str = "Developer",
    ) -> Dict[str, Any]:
        resource_id = str(uuid4())
        resource = {
            "id": resource_id,
            "external_id": f"RES-{resource_id[:8]}",
            "name": name,
            "email": email or f"{name.lower().replace(' ', '.')}@example.com",
            "role": role,
            "availability_status": "ACTIVE",
            "max_utilization": 100,
            "created_at": datetime.utcnow().isoformat(),
        }
        mock_data["resources"].append(resource)
        return resource
    
    return _create


@pytest.fixture
def create_test_dependency(mock_data):
    """Factory fixture to create test dependencies."""
    def _create(
        successor_id: str,
        predecessor_id: str,
        dependency_type: str = "FS",
        lag_days: int = 0,
    ) -> Dict[str, Any]:
        dependency = {
            "id": str(uuid4()),
            "successor_item_id": successor_id,
            "predecessor_item_id": predecessor_id,
            "dependency_type": dependency_type,
            "lag_days": lag_days,
            "created_at": datetime.utcnow().isoformat(),
        }
        mock_data["dependencies"].append(dependency)
        return dependency
    
    return _create


# ==========================================
# CLEANUP
# ==========================================

@pytest.fixture(autouse=True)
def cleanup_overrides():
    """Reset dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


# ==========================================
# MARKERS
# ==========================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (isolated, fast)")
    config.addinivalue_line("markers", "integration: Integration tests (database required)")
    config.addinivalue_line("markers", "e2e: End-to-end tests (full workflow)")
    config.addinivalue_line("markers", "slow: Slow tests (>5 seconds)")
    config.addinivalue_line("markers", "edge: Edge case tests")
    config.addinivalue_line("markers", "security: Security-related tests")
    config.addinivalue_line("markers", "performance: Performance/load tests")
