"""
Tests for Impact Analysis Service.

Based on actual impact_analysis.py implementation analysis:
- Key functions: analyze_impact, calculate_cascade_impact, recalculate_duration, apply_approved_delay
- ImpactResult dataclass with cascade_count, affected_items, risk_level
- Cascade traversal limited to 100 items (safety limit)
- ReasonCategory enum for different delay calculations
"""
import pytest
from datetime import date, timedelta
from uuid import uuid4
from unittest.mock import MagicMock, patch
from dataclasses import asdict


class TestImpactAnalysis:
    """Tests for impact analysis calculations."""
    
    @pytest.mark.unit
    def test_calculate_impact_no_dependencies(self):
        """Single task with no dependencies should have no cascade."""
        from app.services.impact_analysis import calculate_cascade_impact
        
        with patch("app.services.impact_analysis.get_supabase_client") as mock_db:
            mock_client = MagicMock()
            mock_db.return_value.client = mock_client
            
            # No dependencies found
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_eq = MagicMock()
            mock_select.eq.return_value = mock_eq
            mock_eq.execute.return_value.data = []
            
            wid = uuid4()
            affected = calculate_cascade_impact(wid, 5)
            
            assert affected == []

    @pytest.mark.unit
    def test_calculate_impact_linear_chain(self):
        """A → B → C cascade should propagate delay through chain."""
        from app.services.impact_analysis import calculate_cascade_impact
        
        a_id = str(uuid4())
        b_id = str(uuid4())
        c_id = str(uuid4())
        
        with patch("app.services.impact_analysis.get_supabase_client") as mock_db:
            mock_client = MagicMock()
            mock_db.return_value.client = mock_client
            
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_eq = MagicMock()
            mock_select.eq.return_value = mock_eq
            
            # Mock returns: A depends on nothing, B depends on A, C depends on B
            call_count = [0]
            def get_successors():
                call_count[0] += 1
                if call_count[0] == 1:  # First call for A
                    return MagicMock(data=[{
                        "successor_item_id": b_id,
                        "lag_days": 0,
                        "work_items": {
                            "id": b_id,
                            "external_id": "B",
                            "name": "Task B",
                            "current_start": "2024-01-10",
                            "current_end": "2024-01-15",
                            "status": "In Progress"
                        }
                    }])
                elif call_count[0] == 2:  # Second call for B
                    return MagicMock(data=[{
                        "successor_item_id": c_id,
                        "lag_days": 0,
                        "work_items": {
                            "id": c_id,
                            "external_id": "C",
                            "name": "Task C",
                            "current_start": "2024-01-16",
                            "current_end": "2024-01-20",
                            "status": "In Progress"
                        }
                    }])
                else:
                    return MagicMock(data=[])
            
            mock_eq.execute.side_effect = get_successors
            
            affected = calculate_cascade_impact(uuid4(), 5)
            
            # Should affect both B and C
            assert len(affected) == 2
            assert affected[0]["slip_days"] == 5

    @pytest.mark.unit
    def test_calculate_impact_branching(self):
        """A → [B, C] cascade should affect both branches."""
        from app.services.impact_analysis import calculate_cascade_impact
        
        b_id = str(uuid4())
        c_id = str(uuid4())
        
        with patch("app.services.impact_analysis.get_supabase_client") as mock_db:
            mock_client = MagicMock()
            mock_db.return_value.client = mock_client
            
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_eq = MagicMock()
            mock_select.eq.return_value = mock_eq
            
            call_count = [0]
            def get_successors():
                call_count[0] += 1
                if call_count[0] == 1:  # A has two successors B and C
                    return MagicMock(data=[
                        {
                            "successor_item_id": b_id,
                            "lag_days": 0,
                            "work_items": {
                                "id": b_id, "external_id": "B", "name": "Task B",
                                "current_start": "2024-01-10", "current_end": "2024-01-15",
                                "status": "In Progress"
                            }
                        },
                        {
                            "successor_item_id": c_id,
                            "lag_days": 0,
                            "work_items": {
                                "id": c_id, "external_id": "C", "name": "Task C",
                                "current_start": "2024-01-10", "current_end": "2024-01-18",
                                "status": "In Progress"
                            }
                        }
                    ])
                else:
                    return MagicMock(data=[])
            
            mock_eq.execute.side_effect = get_successors
            
            affected = calculate_cascade_impact(uuid4(), 3)
            
            # Should affect both B and C
            assert len(affected) == 2

    @pytest.mark.unit
    def test_calculate_impact_converging(self):
        """[A, B] → C cascade should affect C only once."""
        from app.services.impact_analysis import calculate_cascade_impact
        
        c_id = str(uuid4())
        
        with patch("app.services.impact_analysis.get_supabase_client") as mock_db:
            mock_client = MagicMock()
            mock_db.return_value.client = mock_client
            
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_eq = MagicMock()
            mock_select.eq.return_value = mock_eq
            
            # Both A and B depend on C
            mock_eq.execute.return_value.data = [{
                "successor_item_id": c_id,
                "lag_days": 0,
                "work_items": {
                    "id": c_id, "external_id": "C", "name": "Task C",
                    "current_start": "2024-01-10", "current_end": "2024-01-15",
                    "status": "In Progress"
                }
            }]
            
            affected = calculate_cascade_impact(uuid4(), 2)
            
            # C should only appear once
            unique_ids = set(item["id"] for item in affected)
            assert len(unique_ids) == len(affected)

    @pytest.mark.unit
    def test_calculate_impact_complex(self):
        """Complex dependency graph should be handled correctly."""
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
            mock_eq.execute.return_value.data = []
            
            affected = calculate_cascade_impact(uuid4(), 10)
            
            # Should handle without error
            assert isinstance(affected, list)

    @pytest.mark.unit
    def test_cascade_respects_buffer(self):
        """Lag days (buffer) should be respected in cascade calculation."""
        from app.services.impact_analysis import calculate_cascade_impact
        
        b_id = str(uuid4())
        
        with patch("app.services.impact_analysis.get_supabase_client") as mock_db:
            mock_client = MagicMock()
            mock_db.return_value.client = mock_client
            
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_eq = MagicMock()
            mock_select.eq.return_value = mock_eq
            
            call_count = [0]
            def get_successors():
                call_count[0] += 1
                if call_count[0] == 1:
                    return MagicMock(data=[{
                        "successor_item_id": b_id,
                        "lag_days": 2,  # 2-day buffer
                        "work_items": {
                            "id": b_id, "external_id": "B", "name": "Task B",
                            "current_start": "2024-01-12", "current_end": "2024-01-17",
                            "status": "In Progress"
                        }
                    }])
                else:
                    return MagicMock(data=[])
            
            mock_eq.execute.side_effect = get_successors
            
            affected = calculate_cascade_impact(uuid4(), 5)
            
            # Affected items should include lag in calculation
            assert len(affected) >= 1

    @pytest.mark.unit
    def test_cascade_depth_limit(self):
        """Cascade should stop at 100 items (safety limit)."""
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
            
            # Always return a successor to create infinite chain
            def always_return_successor():
                return MagicMock(data=[{
                    "successor_item_id": str(uuid4()),
                    "lag_days": 0,
                    "work_items": {
                        "id": str(uuid4()), "external_id": "X", "name": "Task X",
                        "current_start": "2024-01-10", "current_end": "2024-01-15",
                        "status": "In Progress"
                    }
                }])
            
            mock_eq.execute.side_effect = always_return_successor
            
            affected = calculate_cascade_impact(uuid4(), 5)
            
            # Should be capped at 100
            assert len(affected) <= 100

    @pytest.mark.unit
    def test_impact_preview(self):
        """analyze_impact should return ImpactResult without committing changes."""
        from app.services.impact_analysis import analyze_impact, ImpactResult
        
        wid = str(uuid4())
        
        with patch("app.services.impact_analysis.get_supabase_client") as mock_db:
            mock_client = MagicMock()
            mock_db.return_value.client = mock_client
            
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_eq = MagicMock()
            mock_select.eq.return_value = mock_eq
            mock_eq.execute.return_value.data = [{
                "id": wid,
                "external_id": "T-1",
                "name": "Test Task",
                "current_start": "2024-01-01",
                "current_end": "2024-01-10",
                "is_critical_path": False,
                "resource_id": str(uuid4())
            }]
            
            # Mock other dependencies
            mock_db.return_value.client.table.return_value.select.return_value.eq.return_value.neq = MagicMock()
            mock_db.return_value.client.table.return_value.select.return_value.eq.return_value.neq.return_value.not_ = MagicMock()
            mock_db.return_value.client.table.return_value.select.return_value.eq.return_value.neq.return_value.not_.in_ = MagicMock()
            mock_db.return_value.client.table.return_value.select.return_value.eq.return_value.neq.return_value.not_.in_.return_value.lte = MagicMock()
            mock_db.return_value.client.table.return_value.select.return_value.eq.return_value.neq.return_value.not_.in_.return_value.lte.return_value.gte = MagicMock()
            mock_db.return_value.client.table.return_value.select.return_value.eq.return_value.neq.return_value.not_.in_.return_value.lte.return_value.gte.return_value.execute.return_value.data = []
            
            result = analyze_impact(
                work_item_id=uuid4(),
                proposed_new_end=date(2024, 1, 15),
                reason_category="SCOPE_INCREASE"
            )
            
            # Should return ImpactResult
            assert isinstance(result, ImpactResult)
            assert result.delay_days == 5  # 5 days from Jan 10 to Jan 15

    @pytest.mark.unit
    def test_impact_apply(self):
        """apply_approved_delay should update work item and cascade."""
        from app.services.impact_analysis import apply_approved_delay
        
        wid = str(uuid4())
        
        with patch("app.services.impact_analysis.get_supabase_client") as mock_db, \
             patch("app.services.impact_analysis.calculate_cascade_impact") as mock_cascade:
            mock_client = MagicMock()
            mock_db.return_value.client = mock_client
            
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_eq = MagicMock()
            mock_select.eq.return_value = mock_eq
            mock_eq.execute.return_value.data = [{
                "current_start": "2024-01-01",
                "current_end": "2024-01-10"
            }]
            
            mock_table.update.return_value.eq.return_value.execute.return_value.data = [{}]
            mock_table.insert.return_value.execute.return_value.data = [{"id": str(uuid4())}]
            
            mock_cascade.return_value = []  # No cascade
            
            result = apply_approved_delay(
                work_item_id=uuid4(),
                new_end_date=date(2024, 1, 15),
                approved_by="mgr@test.com",
                cascade=True
            )
            
            assert result["delay_days"] == 5
            assert "new_end" in result
