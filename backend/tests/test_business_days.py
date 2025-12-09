"""
Tests for Business Days Service.

Based on actual business_days.py implementation analysis:
- Key functions: is_business_day, is_weekend, is_holiday
- business_days_before, business_days_after, get_business_days_between
- get_alert_send_date, get_alert_send_timestamp
- Uses holiday_calendar table for holiday lookup
"""
import pytest
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
from unittest.mock import MagicMock, patch


class TestBusinessDays:
    """Tests for business day calculations."""
    
    @pytest.fixture(autouse=True)
    def clear_holiday_cache(self):
        """Clear holiday cache before each test."""
        from app.services import business_days
        business_days._holiday_cache = {}
        business_days._holiday_cache_expiry = None
        yield
    
    @pytest.mark.unit
    def test_is_business_day_monday(self):
        """Monday should be a business day."""
        from app.services.business_days import is_business_day, is_weekend
        
        # 2024-01-08 is Monday
        monday = date(2024, 1, 8)
        
        with patch("app.services.business_days._load_holidays") as mock_holidays:
            mock_holidays.return_value = set()  # No holidays
            
            assert is_weekend(monday) == False
            assert is_business_day(monday) == True

    @pytest.mark.unit
    def test_is_business_day_saturday(self):
        """Saturday should not be a business day."""
        from app.services.business_days import is_business_day, is_weekend
        
        # 2024-01-06 is Saturday
        saturday = date(2024, 1, 6)
        
        with patch("app.services.business_days._load_holidays") as mock_holidays:
            mock_holidays.return_value = set()
            
            assert is_weekend(saturday) == True
            assert is_business_day(saturday) == False

    @pytest.mark.unit
    def test_is_business_day_sunday(self):
        """Sunday should not be a business day."""
        from app.services.business_days import is_business_day, is_weekend
        
        # 2024-01-07 is Sunday
        sunday = date(2024, 1, 7)
        
        with patch("app.services.business_days._load_holidays") as mock_holidays:
            mock_holidays.return_value = set()
            
            assert is_weekend(sunday) == True
            assert is_business_day(sunday) == False

    @pytest.mark.unit
    def test_is_business_day_holiday(self):
        """Holiday on weekday should not be a business day."""
        from app.services.business_days import is_business_day, is_holiday
        
        # 2024-01-01 is Monday (New Year)
        new_year = date(2024, 1, 1)
        
        with patch("app.services.business_days._load_holidays") as mock_holidays:
            mock_holidays.return_value = {new_year}  # New Year is holiday
            
            assert is_holiday(new_year) == True
            assert is_business_day(new_year) == False

    @pytest.mark.unit
    def test_add_business_days_simple(self):
        """Adding business days on weekday should work correctly."""
        from app.services.business_days import business_days_after
        
        # Start on Monday, add 3 business days
        monday = date(2024, 1, 8)  # Monday
        
        with patch("app.services.business_days._load_holidays") as mock_holidays:
            mock_holidays.return_value = set()
            
            result = business_days_after(monday, 3)
            
            # Mon + 3 = Thu
            expected = date(2024, 1, 11)  # Thursday
            assert result == expected

    @pytest.mark.unit
    def test_add_business_days_over_weekend(self):
        """Adding business days should skip weekends."""
        from app.services.business_days import business_days_after
        
        # Start on Friday, add 1 business day → should be Monday
        friday = date(2024, 1, 5)  # Friday
        
        with patch("app.services.business_days._load_holidays") as mock_holidays:
            mock_holidays.return_value = set()
            
            result = business_days_after(friday, 1)
            
            # Fri + 1 = Mon (skipping Sat/Sun)
            expected = date(2024, 1, 8)  # Monday
            assert result == expected

    @pytest.mark.unit
    def test_add_business_days_over_holiday(self):
        """Adding business days should skip holidays."""
        from app.services.business_days import business_days_after
        
        # Start on Dec 31 (Tuesday), add 1 → should skip Jan 1 holiday
        nye_2024 = date(2024, 12, 31)  # Tuesday
        
        with patch("app.services.business_days._load_holidays") as mock_holidays:
            # Jan 1, 2025 is Wednesday but a holiday
            mock_holidays.return_value = {date(2025, 1, 1)}
            
            result = business_days_after(nye_2024, 1)
            
            # Dec 31 + 1 = Jan 2 (skipping Jan 1 holiday)
            expected = date(2025, 1, 2)  # Thursday
            assert result == expected

    @pytest.mark.unit
    def test_subtract_business_days(self):
        """Subtracting business days should work correctly."""
        from app.services.business_days import business_days_before
        
        # Start on Monday, go back 1 business day → should be Friday
        monday = date(2024, 1, 8)  # Monday
        
        with patch("app.services.business_days._load_holidays") as mock_holidays:
            mock_holidays.return_value = set()
            
            result = business_days_before(monday, 1)
            
            # Mon - 1 = Fri
            expected = date(2024, 1, 5)  # Friday
            assert result == expected

    @pytest.mark.unit
    def test_business_days_between(self):
        """Count business days between two dates."""
        from app.services.business_days import get_business_days_between
        
        # Mon Jan 8 to Fri Jan 12 = 4 business days (Mon, Tue, Wed, Thu)
        start = date(2024, 1, 8)  # Monday
        end = date(2024, 1, 12)  # Friday
        
        with patch("app.services.business_days._load_holidays") as mock_holidays:
            mock_holidays.return_value = set()
            
            result = get_business_days_between(start, end)
            
            # Mon, Tue, Wed, Thu (exclusive of end)
            assert result == 4

    @pytest.mark.unit
    def test_get_alert_send_date(self):
        """Get alert send date should be N business days before deadline."""
        from app.services.business_days import get_alert_send_date
        
        # Deadline on Monday, alert 1 day before → Friday
        deadline = date(2024, 1, 8)  # Monday
        
        with patch("app.services.business_days._load_holidays") as mock_holidays:
            mock_holidays.return_value = set()
            
            result = get_alert_send_date(deadline, days_before=1)
            
            expected = date(2024, 1, 5)  # Friday
            assert result == expected
