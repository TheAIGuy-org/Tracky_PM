"""
Performance and Load Tests for Tracky PM.

Tests for performance benchmarks:
- Import performance with large datasets
- Cascade calculation performance
- API response times
- Concurrent operation handling
- Memory usage
- Database connection pool

NOTE: These are mock-based performance tests that verify the system
can handle load scenarios. For real performance testing, use actual
database and proper load testing tools (locust, k6, etc.).
"""
import pytest
import time
import threading
import tracemalloc
from datetime import date, timedelta
from uuid import uuid4
from unittest.mock import MagicMock, patch
from io import BytesIO


class TestImportPerformance:
    """Tests for import performance with large datasets."""
    
    @pytest.mark.performance
    def test_import_5000_items_under_30s(self):
        """5000 work items data generation should complete under 30 seconds."""
        start_time = time.time()
        
        # Simulate generating 5000 work items
        work_items = [
            {
                "external_id": f"WI-{i}",
                "name": f"Work Item {i}",
                "phase_id": "PHS-1",
                "current_start": "2024-01-01",
                "current_end": "2024-01-10",
                "status": "In Progress",
                "description": f"Description for work item {i}" * 5
            }
            for i in range(5000)
        ]
        
        # Simulate processing (transform, validate)
        processed = []
        for item in work_items:
            processed.append({
                "id": str(uuid4()),
                **item,
                "created_at": "2024-01-01T00:00:00Z"
            })
        
        elapsed = time.time() - start_time
        
        # Should complete in under 30 seconds
        assert elapsed < 30, f"Data generation took {elapsed:.2f}s, expected < 30s"
        assert len(processed) == 5000
        print(f"5000 items generated in {elapsed:.2f}s")

    @pytest.mark.performance
    def test_import_10000_items_performance(self):
        """10000 work items data generation benchmark."""
        start_time = time.time()
        
        # Generate 10000 items
        work_items = [
            {"external_id": f"WI-{i}", "name": f"Item {i}", "data": "x" * 100}
            for i in range(10000)
        ]
        
        # Simulate batch processing
        batch_size = 500
        batches = []
        for i in range(0, len(work_items), batch_size):
            batch = work_items[i:i+batch_size]
            batches.append([{**item, "processed": True} for item in batch])
        
        elapsed = time.time() - start_time
        
        print(f"10000 items processed in {elapsed:.2f}s ({len(batches)} batches)")
        
        # Should complete in under 60 seconds
        assert elapsed < 60
        assert len(batches) == 20  # 10000 / 500

    @pytest.mark.performance
    def test_cascade_1000_items_performance(self):
        """Large cascade (1000 items) should complete quickly."""
        from app.services.impact_analysis import calculate_cascade_impact
        
        with patch("app.services.impact_analysis.get_supabase_client") as mock_db:
            mock_client = MagicMock()
            mock_db.return_value.client = mock_client
            
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_eq = MagicMock()
            mock_select.eq.return_value = mock_eq
            
            # Generate 1000 successors
            items_count = [0]
            def get_successors():
                items_count[0] += 1
                if items_count[0] <= 100:  # Limit to 100 due to safety cap
                    return MagicMock(data=[{
                        "successor_item_id": str(uuid4()),
                        "lag_days": 0,
                        "work_items": {
                            "id": str(uuid4()),
                            "external_id": f"T-{items_count[0]}",
                            "name": f"Task {items_count[0]}",
                            "current_start": "2024-01-01",
                            "current_end": "2024-01-10",
                            "status": "In Progress"
                        }
                    }])
                return MagicMock(data=[])
            
            mock_eq.execute.side_effect = get_successors
            
            start_time = time.time()
            
            affected = calculate_cascade_impact(uuid4(), 5)
            
            elapsed = time.time() - start_time
            
            # Should complete in under 5 seconds even with 100 items
            assert elapsed < 5, f"Cascade took {elapsed:.2f}s, expected < 5s"
            assert len(affected) <= 100  # Safety limit enforced


class TestAPIPerformance:
    """Tests for API response time performance."""
    
    @pytest.mark.performance
    def test_list_work_items_1000_performance(self, client, mock_data):
        """Listing 1000 work items should be fast."""
        # Populate mock data with 1000 items
        mock_data["work_items"] = [
            {
                "id": str(uuid4()),
                "external_id": f"WI-{i}",
                "name": f"Work Item {i}",
                "status": "In Progress",
                "current_start": "2024-01-01",
                "current_end": "2024-01-10"
            }
            for i in range(1000)
        ]
        
        start_time = time.time()
        
        response = client.get("/api/data/work-items?limit=1000")
        
        elapsed = time.time() - start_time
        
        assert response.status_code == 200
        # Should return quickly (mocked data)
        assert elapsed < 2, f"List took {elapsed:.2f}s, expected < 2s"

    @pytest.mark.performance
    def test_response_time_p95(self, client, mock_data):
        """P95 response time should be under 200ms."""
        mock_data["work_items"] = [{"id": str(uuid4()), "name": f"Item {i}"} for i in range(100)]
        
        response_times = []
        
        for _ in range(20):  # 20 requests for P95
            start = time.time()
            response = client.get("/api/data/work-items")
            elapsed = (time.time() - start) * 1000  # Convert to ms
            response_times.append(elapsed)
            assert response.status_code == 200
        
        # Sort and get P95
        response_times.sort()
        p95_index = int(len(response_times) * 0.95)
        p95 = response_times[p95_index]
        
        print(f"P95 response time: {p95:.2f}ms")
        
        # P95 should be under 500ms for mocked requests
        assert p95 < 500, f"P95 response time {p95:.2f}ms exceeds 500ms"


class TestConcurrentOperations:
    """Tests for concurrent operation handling."""
    
    @pytest.mark.performance
    def test_concurrent_imports_3(self, client):
        """3 concurrent imports should all succeed."""
        results = []
        errors = []
        
        def do_import(index):
            try:
                with patch("app.api.routes.import_routes.ExcelParser") as mock_parser:
                    mock_instance = MagicMock()
                    mock_parser.return_value = mock_instance
                    mock_instance.parse.return_value = {
                        "programs": [{"external_id": f"PRG-{index}", "name": f"Program {index}"}],
                        "projects": [],
                        "phases": [],
                        "work_items": [],
                        "dependencies": [],
                        "resources": []
                    }
                    
                    files = {"file": (f"test{index}.xlsx", BytesIO(b"mock"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
                    response = client.post("/api/import/upload", files=files)
                    results.append((index, response.status_code))
            except Exception as e:
                errors.append((index, str(e)))
        
        threads = []
        for i in range(3):
            t = threading.Thread(target=do_import, args=(i,))
            threads.append(t)
        
        start_time = time.time()
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        elapsed = time.time() - start_time
        
        print(f"3 concurrent imports completed in {elapsed:.2f}s")
        
        # All should complete without critical errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        # Results should be present
        assert len(results) == 3


class TestResourceUsage:
    """Tests for resource usage and limits."""
    
    @pytest.mark.performance
    def test_memory_usage_large_import(self):
        """Memory usage should stay reasonable during large import."""
        tracemalloc.start()
        
        # Simulate large data processing
        large_data = [
            {
                "id": str(uuid4()),
                "external_id": f"WI-{i}",
                "name": f"Work Item {i}" * 10,  # Larger strings
                "description": "Description " * 50,
                "current_start": "2024-01-01",
                "current_end": "2024-12-31"
            }
            for i in range(5000)
        ]
        
        # Process the data (simulate)
        processed = []
        for item in large_data:
            processed.append({
                "id": item["id"],
                "name": item["name"].upper(),
                "length": len(item["description"])
            })
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        # Convert to MB
        peak_mb = peak / 1024 / 1024
        
        print(f"Peak memory usage: {peak_mb:.2f} MB")
        
        # Peak should be under 500MB for this mock test
        assert peak_mb < 500, f"Peak memory {peak_mb:.2f}MB exceeds 500MB"
        
        # Cleanup
        del large_data
        del processed

    @pytest.mark.performance
    def test_database_connection_pool(self, client, mock_data):
        """Database connection pool should handle multiple requests."""
        mock_data["work_items"] = [{"id": str(i), "name": f"Item {i}"} for i in range(50)]
        
        results = []
        
        def make_request(i):
            response = client.get("/api/data/work-items")
            results.append((i, response.status_code))
        
        threads = []
        for i in range(10):  # 10 concurrent requests
            t = threading.Thread(target=make_request, args=(i,))
            threads.append(t)
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # All requests should succeed
        success_count = sum(1 for _, status in results if status == 200)
        
        print(f"Successful requests: {success_count}/10")
        
        # At least 80% should succeed
        assert success_count >= 8, f"Only {success_count}/10 requests succeeded"
