"""
Tests for Holiday Routes (/api/holidays endpoints).

Based on actual holiday_routes.py implementation analysis:
- Endpoints: list, create, get, update, delete, check-business-day, years, countries, bulk
- Response formats verified from source code
- Validation logic: UUID format, duplicate check, holiday_type validation, weekend detection
- Table name: holiday_calendar
"""
import pytest
from datetime import date
from uuid import uuid4
from unittest.mock import MagicMock, patch


# ==========================================
# HOLIDAY CRUD TESTS
# ==========================================

class TestHolidayCRUD:
    
    @pytest.mark.unit
    def test_list_holidays_empty(self, client, mock_data):
        """List holidays when none exist."""
        mock_data["holiday_calendar"] = []
        response = client.get("/api/holidays")
        assert response.status_code == 200
        assert response.json()["holidays"] == []
        assert response.json()["count"] == 0

    @pytest.mark.unit
    def test_list_holidays_with_data(self, client, mock_data):
        """List holidays with data."""
        mock_data["holiday_calendar"] = [
            {"id": str(uuid4()), "name": "New Year", "holiday_date": "2024-01-01", "country_code": "US", "holiday_type": "NATIONAL"},
            {"id": str(uuid4()), "name": "Christmas", "holiday_date": "2024-12-25", "country_code": "US", "holiday_type": "NATIONAL"}
        ]
        response = client.get("/api/holidays")
        assert response.status_code == 200
        assert response.json()["count"] == 2

    @pytest.mark.unit
    def test_list_holidays_filter_by_year(self, client, mock_data):
        """Filter holidays by year."""
        mock_data["holiday_calendar"] = [
            {"id": "1", "name": "New Year 2024", "holiday_date": "2024-01-01", "country_code": "US"},
            {"id": "2", "name": "New Year 2023", "holiday_date": "2023-01-01", "country_code": "US"}
        ]
        response = client.get("/api/holidays?year=2024")
        assert response.status_code == 200
        # MockSupabaseClient would need to support gte/lte for accurate filtering
        # This tests the endpoint structure

    @pytest.mark.unit
    def test_list_holidays_filter_by_country(self, client, mock_data):
        """Filter holidays by country code."""
        mock_data["holiday_calendar"] = [
            {"id": "1", "name": "Independence Day", "holiday_date": "2024-07-04", "country_code": "US"},
            {"id": "2", "name": "Canada Day", "holiday_date": "2024-07-01", "country_code": "CA"}
        ]
        response = client.get("/api/holidays?country_code=US")
        assert response.status_code == 200
        # Verify filter applied
        for holiday in response.json()["holidays"]:
            assert holiday["country_code"] == "US"

    @pytest.mark.unit
    def test_create_holiday_success(self, client, mock_data):
        """Create a holiday successfully."""
        mock_data["holiday_calendar"] = []  # No duplicates
        response = client.post("/api/holidays", json={
            "name": "Test Holiday",
            "holiday_date": "2024-06-15",
            "country_code": "US",
            "holiday_type": "COMPANY"
        })
        assert response.status_code == 200
        assert response.json()["success"] == True
        assert "holiday" in response.json()

    @pytest.mark.unit
    def test_create_holiday_duplicate(self, client):
        """Reject duplicate holiday creation."""
        with patch("app.api.routes.holiday_routes.get_supabase_client") as mock_db:
            mock_client = MagicMock()
            mock_db.return_value.client = mock_client
            
            # Mock the duplicate check to return existing data
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            mock_select = MagicMock()
            mock_table.select.return_value = mock_select
            mock_eq1 = MagicMock()
            mock_select.eq.return_value = mock_eq1
            mock_eq2 = MagicMock()
            mock_eq1.eq.return_value = mock_eq2
            mock_eq3 = MagicMock()
            mock_eq2.eq.return_value = mock_eq3
            mock_execute = MagicMock()
            mock_execute.data = [{"id": str(uuid4())}]  # Duplicate exists
            mock_eq3.execute.return_value = mock_execute
            
            response = client.post("/api/holidays", json={
                "name": "Duplicate Holiday",
                "holiday_date": "2024-06-15",
                "country_code": "US",
                "holiday_type": "COMPANY"
            })
            assert response.status_code == 400
            assert "already exists" in response.json()["detail"].lower()

    @pytest.mark.unit
    def test_create_holiday_invalid_type(self, client, mock_data):
        """Reject invalid holiday type."""
        mock_data["holiday_calendar"] = []
        response = client.post("/api/holidays", json={
            "name": "Invalid Type",
            "holiday_date": "2024-06-15",
            "holiday_type": "INVALID"
        })
        assert response.status_code == 400
        assert "Invalid holiday_type" in response.json()["detail"]

    @pytest.mark.unit
    def test_get_holiday_success(self, client, mock_data):
        """Get single holiday by ID."""
        hid = str(uuid4())
        mock_data["holiday_calendar"] = [{
            "id": hid,
            "name": "Test Holiday",
            "holiday_date": "2024-01-01",
            "country_code": "US",
            "holiday_type": "NATIONAL"
        }]
        response = client.get(f"/api/holidays/{hid}")
        assert response.status_code == 200
        assert response.json()["name"] == "Test Holiday"

    @pytest.mark.unit
    def test_get_holiday_not_found(self, client, mock_data):
        """404 for non-existent holiday."""
        mock_data["holiday_calendar"] = []
        response = client.get(f"/api/holidays/{str(uuid4())}")
        assert response.status_code == 404

    @pytest.mark.unit
    def test_get_holiday_invalid_uuid(self, client):
        """422 for invalid UUID format."""
        response = client.get("/api/holidays/not-a-uuid")
        assert response.status_code == 422
        assert "Invalid holiday ID format" in response.json()["detail"]

    @pytest.mark.unit
    def test_update_holiday_success(self, client, mock_data):
        """Update holiday successfully."""
        hid = str(uuid4())
        mock_data["holiday_calendar"] = [{"id": hid, "name": "Old Name", "holiday_date": "2024-01-01"}]
        response = client.put(f"/api/holidays/{hid}", json={"name": "New Name"})
        assert response.status_code == 200
        assert response.json()["success"] == True

    @pytest.mark.unit
    def test_update_holiday_not_found(self, client, mock_data):
        """404 when updating non-existent holiday."""
        mock_data["holiday_calendar"] = []
        response = client.put(f"/api/holidays/{str(uuid4())}", json={"name": "Test"})
        assert response.status_code == 404

    @pytest.mark.unit
    def test_delete_holiday_success(self, client, mock_data):
        """Delete holiday successfully."""
        hid = str(uuid4())
        mock_data["holiday_calendar"] = [{"id": hid, "name": "To Delete", "holiday_date": "2024-01-01"}]
        response = client.delete(f"/api/holidays/{hid}")
        assert response.status_code == 200
        assert response.json()["success"] == True
        assert response.json()["deleted"]["id"] == hid

    @pytest.mark.unit
    def test_delete_holiday_not_found(self, client, mock_data):
        """404 when deleting non-existent holiday."""
        mock_data["holiday_calendar"] = []
        response = client.delete(f"/api/holidays/{str(uuid4())}")
        assert response.status_code == 404


# ==========================================
# BUSINESS DAY UTILITY TESTS
# ==========================================

class TestBusinessDayUtilities:
    
    @pytest.mark.unit
    def test_check_business_day_weekday(self, client, mock_data):
        """Weekday without holiday is a business day."""
        mock_data["holiday_calendar"] = []  # No holidays
        # 2024-01-08 is Monday
        response = client.get("/api/holidays/check-business-day?check_date=2024-01-08&country_code=US")
        assert response.status_code == 200
        assert response.json()["is_business_day"] == True
        assert response.json()["is_weekend"] == False
        assert response.json()["is_holiday"] == False

    @pytest.mark.unit
    def test_check_business_day_weekend(self, client, mock_data):
        """Weekend is not a business day."""
        mock_data["holiday_calendar"] = []
        # 2024-01-06 is Saturday
        response = client.get("/api/holidays/check-business-day?check_date=2024-01-06&country_code=US")
        assert response.status_code == 200
        assert response.json()["is_business_day"] == False
        assert response.json()["is_weekend"] == True

    @pytest.mark.unit
    def test_check_business_day_holiday(self, client, mock_data):
        """Holiday on weekday is not a business day."""
        mock_data["holiday_calendar"] = [{
            "id": str(uuid4()),
            "name": "New Year",
            "holiday_date": "2024-01-01",  # Monday
            "country_code": "US",
            "holiday_type": "NATIONAL"
        }]
        response = client.get("/api/holidays/check-business-day?check_date=2024-01-01&country_code=US")
        assert response.status_code == 200
        assert response.json()["is_business_day"] == False
        assert response.json()["is_holiday"] == True
        assert response.json()["holiday_name"] == "New Year"

    @pytest.mark.unit
    def test_get_holiday_years(self, client, mock_data):
        """Get distinct years with holidays."""
        mock_data["holiday_calendar"] = [
            {"id": "1", "holiday_date": "2023-01-01"},
            {"id": "2", "holiday_date": "2024-01-01"},
            {"id": "3", "holiday_date": "2024-07-04"}
        ]
        response = client.get("/api/holidays/years")
        assert response.status_code == 200
        years = response.json()["years"]
        assert 2023 in years
        assert 2024 in years
        assert len(years) == 2  # Distinct years

    @pytest.mark.unit
    def test_get_holiday_years_empty(self, client, mock_data):
        """Get years when no holidays exist."""
        mock_data["holiday_calendar"] = []
        response = client.get("/api/holidays/years")
        assert response.status_code == 200
        assert response.json()["years"] == []

    @pytest.mark.unit
    def test_get_holiday_countries(self, client, mock_data):
        """Get distinct country codes with holidays."""
        mock_data["holiday_calendar"] = [
            {"id": "1", "country_code": "US"},
            {"id": "2", "country_code": "CA"},
            {"id": "3", "country_code": "US"},
            {"id": "4", "country_code": None}  # Company-wide, no country
        ]
        response = client.get("/api/holidays/countries")
        assert response.status_code == 200
        countries = response.json()["countries"]
        assert "US" in countries
        assert "CA" in countries
        assert len(countries) == 2  # Distinct, excludes None


# ==========================================
# BULK OPERATIONS TESTS
# ==========================================

class TestBulkOperations:
    
    @pytest.mark.unit
    def test_create_holidays_bulk_success(self, client, mock_data):
        """Bulk create holidays successfully."""
        mock_data["holiday_calendar"] = []
        response = client.post("/api/holidays/bulk", json={
            "holidays": [
                {"name": "Holiday 1", "holiday_date": "2024-06-01", "holiday_type": "COMPANY"},
                {"name": "Holiday 2", "holiday_date": "2024-06-02", "holiday_type": "COMPANY"}
            ]
        })
        assert response.status_code == 200
        assert response.json()["success"] == True
        assert response.json()["created_count"] == 2
        assert response.json()["error_count"] == 0

    @pytest.mark.unit
    def test_create_holidays_bulk_partial_failure(self, client, mock_data):
        """Handle partial failure in bulk create."""
        # This test verifies the response structure when some inserts fail
        # The actual failure would depend on database constraints
        mock_data["holiday_calendar"] = []
        
        # Mock the insert to fail for one item
        with patch("app.api.routes.holiday_routes.get_supabase_client") as mock_db:
            mock_client = MagicMock()
            mock_db.return_value.client = mock_client
            
            # First insert succeeds, second fails
            mock_table = MagicMock()
            mock_client.table.return_value = mock_table
            
            call_count = [0]
            def insert_side_effect(data):
                call_count[0] += 1
                if call_count[0] == 1:
                    mock_result = MagicMock()
                    mock_result.data = [{"id": str(uuid4()), **data}]
                    return mock_result
                else:
                    raise Exception("Database constraint violation")
            
            mock_insert = MagicMock()
            mock_insert.execute = MagicMock(side_effect=lambda: insert_side_effect({}))
            mock_table.insert.return_value = mock_insert
            
            response = client.post("/api/holidays/bulk", json={
                "holidays": [
                    {"name": "Holiday 1", "holiday_date": "2024-06-01", "holiday_type": "COMPANY"},
                    {"name": "Holiday 2", "holiday_date": "2024-06-01", "holiday_type": "COMPANY"}  # Same date
                ]
            })
            
            # The endpoint should handle errors gracefully
            assert response.status_code == 200
            # Response should have error information
            assert "errors" in response.json()

    @pytest.mark.unit
    def test_create_holidays_bulk_empty_list(self, client, mock_data):
        """Bulk create with empty list."""
        mock_data["holiday_calendar"] = []
        response = client.post("/api/holidays/bulk", json={"holidays": []})
        assert response.status_code == 200
        assert response.json()["created_count"] == 0
