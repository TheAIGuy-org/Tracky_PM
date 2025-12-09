"""
Data API Routes for Tracky PM.
Direct data fetching endpoints for Programs, Work Items, Resources, and Audit Logs.

These endpoints provide real-time data access for the frontend UI.
"""
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

from app.core.database import get_supabase_client


router = APIRouter(prefix="/api/data", tags=["Data"])


# ==========================================
# PROGRAMS ENDPOINTS
# ==========================================

@router.get(
    "/programs",
    summary="List All Programs",
    description="Get all programs with their summary statistics"
)
async def list_programs(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
) -> dict:
    """
    List all programs with work item counts.
    """
    db = get_supabase_client()
    
    query = db.client.table("programs").select("*")
    
    if status:
        query = query.eq("status", status)
    
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    response = query.execute()
    
    programs = response.data or []
    
    # Get work item counts for each program
    for program in programs:
        # Get project count
        projects_response = (
            db.client.table("projects")
            .select("id", count="exact")
            .eq("program_id", program["id"])
            .execute()
        )
        program["project_count"] = projects_response.count or 0
        
        # Get work item count via phases and projects
        work_items_response = (
            db.client.table("work_items")
            .select("id, status, phases!inner(projects!inner(program_id))", count="exact")
            .eq("phases.projects.program_id", program["id"])
            .execute()
        )
        program["work_item_count"] = work_items_response.count or 0
        
        # Calculate progress (completed / total)
        if program["work_item_count"] > 0:
            completed_response = (
                db.client.table("work_items")
                .select("id, phases!inner(projects!inner(program_id))", count="exact")
                .eq("phases.projects.program_id", program["id"])
                .eq("status", "Completed")
                .execute()
            )
            completed = completed_response.count or 0
            program["progress"] = round((completed / program["work_item_count"]) * 100)
        else:
            program["progress"] = 0
    
    # Get total count
    count_query = db.client.table("programs").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    count_response = count_query.execute()
    
    return {
        "data": programs,
        "count": count_response.count or 0,
        "limit": limit,
        "offset": offset
    }


@router.get(
    "/programs/{program_id}",
    summary="Get Program Details",
    description="Get detailed information about a specific program"
)
async def get_program(program_id: str) -> dict:
    """
    Get program details with full statistics.
    """
    db = get_supabase_client()
    
    response = db.client.table("programs").select("*").eq("id", program_id).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Program not found")
    
    program = response.data[0]
    
    # Get detailed stats
    projects = db.client.table("projects").select("*").eq("program_id", program_id).execute()
    program["projects"] = projects.data or []
    
    return program


# ==========================================
# WORK ITEMS ENDPOINTS
# ==========================================

@router.get(
    "/work-items",
    summary="List Work Items",
    description="Get work items with filtering and pagination"
)
async def list_work_items(
    program_id: Optional[str] = Query(None, description="Filter by program"),
    status: Optional[str] = Query(None, description="Filter by status"),
    resource_id: Optional[str] = Query(None, description="Filter by assigned resource"),
    flagged_only: bool = Query(False, description="Only return flagged items"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
) -> dict:
    """
    List work items with comprehensive filtering.
    """
    db = get_supabase_client()
    
    # Build query with joins to get hierarchy info
    query = db.client.table("work_items").select(
        "*, phases(id, name, external_id, projects(id, name, external_id, program_id, programs(id, name, external_id)))"
    )
    
    if status:
        query = query.eq("status", status)
    
    if resource_id:
        query = query.eq("resource_id", resource_id)
    
    if flagged_only:
        query = query.eq("flag_for_review", True)
    
    if program_id:
        # Filter by program via the nested join
        query = query.eq("phases.projects.program_id", program_id)
    
    query = query.order("updated_at", desc=True).range(offset, offset + limit - 1)
    response = query.execute()
    
    work_items = response.data or []
    
    # Get resource info for each work item
    resource_ids = list(set(wi.get("resource_id") for wi in work_items if wi.get("resource_id")))
    resources_map = {}
    
    if resource_ids:
        resources_response = (
            db.client.table("resources")
            .select("id, name, external_id, email")
            .in_("id", resource_ids)
            .execute()
        )
        resources_map = {r["id"]: r for r in (resources_response.data or [])}
    
    # Attach resource info
    for wi in work_items:
        if wi.get("resource_id") and wi["resource_id"] in resources_map:
            wi["resource"] = resources_map[wi["resource_id"]]
    
    # Get total count
    count_query = db.client.table("work_items").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    if resource_id:
        count_query = count_query.eq("resource_id", resource_id)
    if flagged_only:
        count_query = count_query.eq("flag_for_review", True)
    count_response = count_query.execute()
    
    return {
        "data": work_items,
        "count": count_response.count or 0,
        "limit": limit,
        "offset": offset
    }


@router.get(
    "/work-items/{work_item_id}",
    summary="Get Work Item Details",
    description="Get detailed information about a specific work item"
)
async def get_work_item(work_item_id: str) -> dict:
    """
    Get work item with full details including dependencies.
    """
    try:
        db = get_supabase_client()
        
        response = (
            db.client.table("work_items")
            .select("*, phases(*, projects(*, programs(*)))")
            .eq("id", work_item_id)
            .execute()
        )
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Work item not found")
        
        work_item = response.data[0]
        
        # Get dependencies (as successor)
        predecessors = (
            db.client.table("dependencies")
            .select("*, predecessor:predecessor_item_id(id, external_id, name, status)")
            .eq("successor_item_id", work_item_id)
            .execute()
        )
        work_item["predecessors"] = predecessors.data or []
        
        # Get dependencies (as predecessor)
        successors = (
            db.client.table("dependencies")
            .select("*, successor:successor_item_id(id, external_id, name, status)")
            .eq("predecessor_item_id", work_item_id)
            .execute()
        )
        work_item["successors"] = successors.data or []
        
        # Get resource info
        if work_item.get("resource_id"):
            resource_response = (
                db.client.table("resources")
                .select("*")
                .eq("id", work_item["resource_id"])
                .execute()
            )
            if resource_response.data:
                work_item["resource"] = resource_response.data[0]
        
        return work_item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")


# ==========================================
# RESOURCES ENDPOINTS
# ==========================================

@router.get(
    "/resources",
    summary="List Resources",
    description="Get all resources with their allocation status"
)
async def list_resources(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
) -> dict:
    """
    List all resources with work item assignments.
    """
    db = get_supabase_client()
    
    query = db.client.table("resources").select("*")
    
    if status:
        query = query.eq("status", status)
    
    query = query.order("name").range(offset, offset + limit - 1)
    response = query.execute()
    
    resources = response.data or []
    
    # Get assignment count for each resource
    for resource in resources:
        assignments = (
            db.client.table("work_items")
            .select("id", count="exact")
            .eq("resource_id", resource["id"])
            .neq("status", "Completed")
            .neq("status", "Cancelled")
            .execute()
        )
        resource["active_assignments"] = assignments.count or 0
    
    # Get total count
    count_query = db.client.table("resources").select("id", count="exact")
    if status:
        count_query = count_query.eq("status", status)
    count_response = count_query.execute()
    
    return {
        "data": resources,
        "count": count_response.count or 0,
        "limit": limit,
        "offset": offset
    }


@router.get(
    "/resources/{resource_id}",
    summary="Get Resource Details",
    description="Get detailed information about a specific resource"
)
async def get_resource(resource_id: str) -> dict:
    """
    Get resource with assigned work items.
    """
    db = get_supabase_client()
    
    response = db.client.table("resources").select("*").eq("id", resource_id).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    resource = response.data[0]
    
    # Get assigned work items
    work_items = (
        db.client.table("work_items")
        .select("id, external_id, name, status, completion_percent, current_start, current_end")
        .eq("resource_id", resource_id)
        .neq("status", "Cancelled")
        .order("current_start")
        .execute()
    )
    resource["work_items"] = work_items.data or []
    
    return resource


# ==========================================
# AUDIT LOGS ENDPOINTS
# ==========================================

@router.get(
    "/audit-logs",
    summary="List Audit Logs",
    description="Get audit logs for compliance tracking"
)
async def list_audit_logs(
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    action: Optional[str] = Query(None, description="Filter by action"),
    import_batch_id: Optional[str] = Query(None, description="Filter by import batch"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
) -> dict:
    """
    List audit logs with filtering.
    """
    db = get_supabase_client()
    
    query = db.client.table("audit_logs").select("*")
    
    if entity_type:
        query = query.eq("entity_type", entity_type)
    if entity_id:
        query = query.eq("entity_id", entity_id)
    if action:
        query = query.eq("action", action)
    if import_batch_id:
        query = query.eq("import_batch_id", import_batch_id)
    
    query = query.order("changed_at", desc=True).range(offset, offset + limit - 1)
    response = query.execute()
    
    # Get total count
    count_query = db.client.table("audit_logs").select("id", count="exact")
    if entity_type:
        count_query = count_query.eq("entity_type", entity_type)
    if entity_id:
        count_query = count_query.eq("entity_id", entity_id)
    if action:
        count_query = count_query.eq("action", action)
    if import_batch_id:
        count_query = count_query.eq("import_batch_id", import_batch_id)
    count_response = count_query.execute()
    
    return {
        "data": response.data or [],
        "count": count_response.count or 0,
        "limit": limit,
        "offset": offset
    }


# ==========================================
# DEPENDENCIES ENDPOINTS
# ==========================================

@router.get(
    "/dependencies",
    summary="List Dependencies",
    description="Get task dependencies"
)
async def list_dependencies(
    work_item_id: Optional[str] = Query(None, description="Filter by work item"),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0)
) -> dict:
    """
    List dependencies with work item info.
    """
    try:
        db = get_supabase_client()
        
        # FIXED: Correct column names are predecessor_item_id and successor_item_id
        query = db.client.table("dependencies").select(
            "*, predecessor:predecessor_item_id(id, external_id, name), successor:successor_item_id(id, external_id, name)"
        )
        
        if work_item_id:
            # FIXED: Use correct column names
            query = query.or_(f"predecessor_item_id.eq.{work_item_id},successor_item_id.eq.{work_item_id}")
        
        query = query.range(offset, offset + limit - 1)
        response = query.execute()
        
        # Get total count
        count_query = db.client.table("dependencies").select("id", count="exact")
        if work_item_id:
            count_query = count_query.or_(f"predecessor_item_id.eq.{work_item_id},successor_item_id.eq.{work_item_id}")
        count_response = count_query.execute()
        
        return {
            "data": response.data or [],
            "count": count_response.count or 0,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")


# ==========================================
# DASHBOARD STATS ENDPOINT
# ==========================================

@router.get(
    "/dashboard/stats",
    summary="Get Dashboard Statistics",
    description="Get aggregated statistics for the dashboard"
)
async def get_dashboard_stats() -> dict:
    """
    Get comprehensive dashboard statistics.
    """
    db = get_supabase_client()
    
    # Programs count
    programs = db.client.table("programs").select("id", count="exact").execute()
    
    # Work items by status
    work_items = db.client.table("work_items").select("id, status").execute()
    work_items_data = work_items.data or []
    
    status_counts = {}
    for wi in work_items_data:
        status = wi.get("status", "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Resources
    resources = db.client.table("resources").select("id", count="exact").execute()
    
    # Recent imports
    recent_imports = (
        db.client.table("import_batches")
        .select("*")
        .order("started_at", desc=True)
        .limit(5)
        .execute()
    )
    
    # Flagged items count
    flagged = (
        db.client.table("work_items")
        .select("id", count="exact")
        .eq("flag_for_review", True)
        .execute()
    )
    
    # Resource utilization
    utilization = db.get_all_resource_utilization()
    over_allocated = len([r for r in utilization if r.get("utilization_status") == "Over-Allocated"])
    
    return {
        "programs": {
            "total": programs.count or 0
        },
        "work_items": {
            "total": len(work_items_data),
            "by_status": status_counts,
            "flagged": flagged.count or 0
        },
        "resources": {
            "total": resources.count or 0,
            "over_allocated": over_allocated
        },
        "recent_imports": recent_imports.data or [],
        "last_updated": None
    }
