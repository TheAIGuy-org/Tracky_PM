"""
Holiday Calendar API Routes for Tracky PM.

Provides endpoints for managing the holiday calendar
used in business day calculations.
"""
from datetime import date
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

from app.core.database import get_supabase_client


router = APIRouter(prefix="/api/holidays", tags=["Holidays"])


# ==========================================
# PYDANTIC MODELS
# ==========================================

class HolidayCreate(BaseModel):
    """Request body for creating a holiday."""
    name: str = Field(..., description="Holiday name", min_length=1, max_length=100)
    holiday_date: date = Field(..., description="Date of the holiday")
    country_code: Optional[str] = Field(
        None, 
        description="Country code (e.g., 'US', 'IN'). NULL for company-wide",
        max_length=2
    )
    region_code: Optional[str] = Field(
        None,
        description="Region code (e.g., 'CA', 'NY'). NULL for nationwide",
        max_length=10
    )
    holiday_type: str = Field(
        "COMPANY",
        description="Type: COMPANY, NATIONAL, REGIONAL, OPTIONAL"
    )
    is_recurring: bool = Field(
        False,
        description="Whether this holiday repeats yearly"
    )
    recurrence_rule: Optional[str] = Field(
        None,
        description="Recurrence rule (e.g., 'YEARLY:MM-DD')"
    )


class HolidayUpdate(BaseModel):
    """Request body for updating a holiday."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    holiday_date: Optional[date] = None
    country_code: Optional[str] = Field(None, max_length=2)
    region_code: Optional[str] = Field(None, max_length=10)
    holiday_type: Optional[str] = None
    is_recurring: Optional[bool] = None
    recurrence_rule: Optional[str] = None


class BulkHolidayCreate(BaseModel):
    """Request body for creating multiple holidays."""
    holidays: List[HolidayCreate]


# ==========================================
# HOLIDAY CRUD ENDPOINTS
# ==========================================

@router.get(
    "",
    summary="List Holidays",
    description="Get holidays with optional filtering"
)
async def list_holidays(
    year: Optional[int] = Query(None, description="Filter by year"),
    country_code: Optional[str] = Query(None, description="Filter by country"),
    holiday_type: Optional[str] = Query(None, description="Filter by type"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
) -> dict:
    """List holidays with optional filters."""
    db = get_supabase_client()
    
    query = db.client.table("holiday_calendar").select("*")
    
    if year:
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        query = query.gte("holiday_date", start_date).lte("holiday_date", end_date)
    
    if country_code:
        query = query.eq("country_code", country_code)
    
    if holiday_type:
        query = query.eq("holiday_type", holiday_type)
    
    response = query.order("holiday_date").range(offset, offset + limit - 1).execute()
    
    return {
        "holidays": response.data or [],
        "count": len(response.data or [])
    }


@router.get(
    "/{holiday_id}",
    summary="Get Holiday",
    description="Get a specific holiday by ID"
)
async def get_holiday(holiday_id: str = Path(...)) -> dict:
    """Get a holiday by ID."""
    db = get_supabase_client()
    
    response = db.client.table("holiday_calendar").select("*").eq(
        "id", holiday_id
    ).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Holiday not found")
    
    return response.data[0]


@router.post(
    "",
    summary="Create Holiday",
    description="Add a new holiday to the calendar"
)
async def create_holiday(body: HolidayCreate) -> dict:
    """Create a new holiday."""
    db = get_supabase_client()
    
    # Validate holiday_type
    valid_types = ["COMPANY", "NATIONAL", "REGIONAL", "OPTIONAL"]
    if body.holiday_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid holiday_type. Must be one of: {', '.join(valid_types)}"
        )
    
    # Check for duplicate
    existing = db.client.table("holiday_calendar").select("id").eq(
        "holiday_date", body.holiday_date.isoformat()
    ).eq("country_code", body.country_code or "").eq(
        "region_code", body.region_code or ""
    ).execute()
    
    if existing.data:
        raise HTTPException(
            status_code=400,
            detail="A holiday already exists for this date and region"
        )
    
    holiday_data = {
        "name": body.name,
        "holiday_date": body.holiday_date.isoformat(),
        "country_code": body.country_code,
        "region_code": body.region_code,
        "holiday_type": body.holiday_type,
        "is_recurring": body.is_recurring,
        "recurrence_rule": body.recurrence_rule
    }
    
    response = db.client.table("holiday_calendar").insert(holiday_data).execute()
    
    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to create holiday")
    
    return {
        "success": True,
        "holiday": response.data[0]
    }


@router.post(
    "/bulk",
    summary="Create Multiple Holidays",
    description="Add multiple holidays at once"
)
async def create_holidays_bulk(body: BulkHolidayCreate) -> dict:
    """Create multiple holidays at once."""
    db = get_supabase_client()
    
    created = []
    errors = []
    
    for holiday in body.holidays:
        try:
            holiday_data = {
                "name": holiday.name,
                "holiday_date": holiday.holiday_date.isoformat(),
                "country_code": holiday.country_code,
                "region_code": holiday.region_code,
                "holiday_type": holiday.holiday_type,
                "is_recurring": holiday.is_recurring,
                "recurrence_rule": holiday.recurrence_rule
            }
            
            response = db.client.table("holiday_calendar").insert(holiday_data).execute()
            if response.data:
                created.append(response.data[0])
        except Exception as e:
            errors.append({
                "holiday": holiday.name,
                "date": holiday.holiday_date.isoformat(),
                "error": str(e)
            })
    
    return {
        "success": len(errors) == 0,
        "created_count": len(created),
        "created": created,
        "error_count": len(errors),
        "errors": errors
    }


@router.put(
    "/{holiday_id}",
    summary="Update Holiday",
    description="Update an existing holiday"
)
async def update_holiday(
    holiday_id: str = Path(...),
    body: HolidayUpdate = None
) -> dict:
    """Update a holiday."""
    db = get_supabase_client()
    
    # Check if exists
    existing = db.client.table("holiday_calendar").select("id").eq(
        "id", holiday_id
    ).execute()
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="Holiday not found")
    
    # Build update dict with only provided fields
    update_data = {}
    if body.name is not None:
        update_data["name"] = body.name
    if body.holiday_date is not None:
        update_data["holiday_date"] = body.holiday_date.isoformat()
    if body.country_code is not None:
        update_data["country_code"] = body.country_code or None
    if body.region_code is not None:
        update_data["region_code"] = body.region_code or None
    if body.holiday_type is not None:
        valid_types = ["COMPANY", "NATIONAL", "REGIONAL", "OPTIONAL"]
        if body.holiday_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid holiday_type. Must be one of: {', '.join(valid_types)}"
            )
        update_data["holiday_type"] = body.holiday_type
    if body.is_recurring is not None:
        update_data["is_recurring"] = body.is_recurring
    if body.recurrence_rule is not None:
        update_data["recurrence_rule"] = body.recurrence_rule
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    response = db.client.table("holiday_calendar").update(
        update_data
    ).eq("id", holiday_id).execute()
    
    return {
        "success": True,
        "holiday": response.data[0] if response.data else None
    }


@router.delete(
    "/{holiday_id}",
    summary="Delete Holiday",
    description="Remove a holiday from the calendar"
)
async def delete_holiday(holiday_id: str = Path(...)) -> dict:
    """Delete a holiday."""
    db = get_supabase_client()
    
    # Check if exists
    existing = db.client.table("holiday_calendar").select("id, name").eq(
        "id", holiday_id
    ).execute()
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="Holiday not found")
    
    db.client.table("holiday_calendar").delete().eq("id", holiday_id).execute()
    
    return {
        "success": True,
        "deleted": existing.data[0]
    }


# ==========================================
# BUSINESS DAY UTILITIES
# ==========================================

@router.get(
    "/check-business-day",
    summary="Check Business Day",
    description="Check if a date is a business day"
)
async def check_business_day(
    check_date: date = Query(..., description="Date to check"),
    country_code: str = Query("US", description="Country code")
) -> dict:
    """Check if a specific date is a business day."""
    db = get_supabase_client()
    
    # Check if weekend (Python: Monday=0, Sunday=6)
    weekday = check_date.weekday()
    is_weekend = weekday >= 5
    
    # Check if holiday
    holiday_resp = db.client.table("holiday_calendar").select(
        "id, name, holiday_type"
    ).eq("holiday_date", check_date.isoformat()).or_(
        f"country_code.eq.{country_code},country_code.is.null"
    ).execute()
    
    holiday = holiday_resp.data[0] if holiday_resp.data else None
    
    is_business_day = not is_weekend and not holiday
    
    return {
        "date": check_date.isoformat(),
        "day_of_week": check_date.strftime("%A"),
        "is_business_day": is_business_day,
        "is_weekend": is_weekend,
        "is_holiday": holiday is not None,
        "holiday_name": holiday["name"] if holiday else None,
        "holiday_type": holiday["holiday_type"] if holiday else None
    }


@router.get(
    "/years",
    summary="Get Available Years",
    description="Get list of years that have holidays defined"
)
async def get_holiday_years() -> dict:
    """Get distinct years that have holidays."""
    db = get_supabase_client()
    
    # Get all holidays and extract years
    response = db.client.table("holiday_calendar").select("holiday_date").execute()
    
    years = set()
    for holiday in (response.data or []):
        year = int(holiday["holiday_date"][:4])
        years.add(year)
    
    return {
        "years": sorted(list(years))
    }


@router.get(
    "/countries",
    summary="Get Country Codes",
    description="Get list of country codes that have holidays defined"
)
async def get_holiday_countries() -> dict:
    """Get distinct country codes with holidays."""
    db = get_supabase_client()
    
    response = db.client.table("holiday_calendar").select("country_code").execute()
    
    countries = set()
    for holiday in (response.data or []):
        if holiday["country_code"]:
            countries.add(holiday["country_code"])
    
    return {
        "countries": sorted(list(countries))
    }
