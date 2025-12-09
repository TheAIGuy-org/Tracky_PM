"""
Resource Management API Routes for Tracky PM.

Provides endpoints for managing resources including:
- Manager hierarchy
- Backup resource assignment
- Availability status
- Escalation chain preview

IMPORTANT: Route ordering matters in FastAPI!
Specific paths like /hierarchy/tree must be defined BEFORE
parameterized paths like /{resource_id}
"""
from datetime import date, datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

from app.core.database import get_supabase_client
from app.services.escalation import get_escalation_chain


router = APIRouter(prefix="/api/resources", tags=["Resources"])


# ==========================================
# PYDANTIC MODELS
# ==========================================

class ResourceUpdate(BaseModel):
    """Request body for updating a resource."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    email: Optional[str] = Field(None)
    manager_id: Optional[str] = Field(None, description="Manager resource UUID")
    backup_resource_id: Optional[str] = Field(None, description="Backup resource UUID")
    availability_status: Optional[str] = Field(
        None,
        description="ACTIVE, ON_LEAVE, UNAVAILABLE, PARTIAL"
    )
    leave_start_date: Optional[date] = None
    leave_end_date: Optional[date] = None
    timezone: Optional[str] = Field(None, description="IANA timezone (e.g., 'America/New_York')")
    notification_email: Optional[str] = Field(None, description="Email for notifications")
    slack_user_id: Optional[str] = Field(None, description="Slack user ID")
    preferred_notification_channel: Optional[str] = Field(
        None,
        description="EMAIL, SLACK, or BOTH"
    )


class SetManagerRequest(BaseModel):
    """Request body for setting a resource's manager."""
    manager_id: Optional[str] = Field(None, description="Manager resource UUID (null to remove)")


class SetBackupRequest(BaseModel):
    """Request body for setting a resource's backup."""
    backup_resource_id: Optional[str] = Field(None, description="Backup resource UUID")


class SetAvailabilityRequest(BaseModel):
    """Request body for setting availability status."""
    availability_status: str = Field(
        ...,
        description="ACTIVE, ON_LEAVE, UNAVAILABLE, PARTIAL"
    )
    leave_start_date: Optional[date] = None
    leave_end_date: Optional[date] = None
    reason: Optional[str] = Field(None, description="Reason for status change")


# ==========================================
# SPECIFIC PATH ROUTES (MUST BE BEFORE /{resource_id})
# ==========================================

@router.get(
    "/hierarchy/tree",
    summary="Get Manager Hierarchy Tree",
    description="Get the complete manager hierarchy as a tree"
)
async def get_hierarchy_tree() -> dict:
    """Get the complete manager hierarchy."""
    db = get_supabase_client()
    
    # Get all resources
    response = db.client.table("resources").select(
        "id, external_id, name, email, role, manager_id, availability_status"
    ).execute()
    
    resources = response.data or []
    
    # Build tree
    resource_map = {r["id"]: r for r in resources}
    roots = []
    
    for resource in resources:
        resource["children"] = []
        resource["depth"] = 0
    
    for resource in resources:
        manager_id = resource.get("manager_id")
        if manager_id and manager_id in resource_map:
            resource_map[manager_id]["children"].append(resource)
        else:
            roots.append(resource)
    
    # Calculate depths
    def set_depth(node, depth=0):
        node["depth"] = depth
        for child in node.get("children", []):
            set_depth(child, depth + 1)
    
    for root in roots:
        set_depth(root)
    
    return {
        "roots": roots,
        "total_resources": len(resources),
        "resources_without_manager": len(roots)
    }


# ==========================================
# RESOURCE LIST (No path parameter)
# ==========================================

@router.get(
    "",
    summary="List Resources",
    description="Get resources with optional filtering"
)
async def list_resources(
    search: Optional[str] = Query(None, description="Search by name or email"),
    availability_status: Optional[str] = Query(None, description="Filter by status"),
    has_manager: Optional[bool] = Query(None, description="Filter by has manager"),
    manager_id: Optional[str] = Query(None, description="Filter by specific manager"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
) -> dict:
    """List resources with optional filters."""
    try:
        db = get_supabase_client()
        
        query = db.client.table("resources").select(
            "id, external_id, name, email, role, "
            "manager_id, backup_resource_id, availability_status, "
            "leave_start_date, leave_end_date, timezone, "
            "preferred_notification_channel, created_at"
        )
        
        if search:
            query = query.or_(f"name.ilike.%{search}%,email.ilike.%{search}%")
        
        if availability_status:
            query = query.eq("availability_status", availability_status)
        
        if has_manager is not None:
            if has_manager:
                query = query.not_.is_("manager_id", "null")
            else:
                query = query.is_("manager_id", "null")
        
        if manager_id:
            query = query.eq("manager_id", manager_id)
        
        response = query.order("name").range(offset, offset + limit - 1).execute()
        
        return {
            "resources": response.data or [],
            "count": len(response.data or [])
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")


# ==========================================
# RESOURCE CRUD WITH PATH PARAMETER (MUST BE AFTER SPECIFIC ROUTES)
# ==========================================

@router.get(
    "/{resource_id}",
    summary="Get Resource Details",
    description="Get detailed information about a resource"
)
async def get_resource(resource_id: str = Path(...)) -> dict:
    """Get a resource by ID with manager and backup info."""
    db = get_supabase_client()
    
    # Validate UUID format to give better error message
    try:
        UUID(resource_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid resource ID format. Must be a valid UUID.")
    
    response = db.client.table("resources").select(
        "*, "
        "manager:manager_id(id, name, email), "
        "backup:backup_resource_id(id, name, email)"
    ).eq("id", resource_id).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    resource = response.data[0]
    
    # Get direct reports
    reports_resp = db.client.table("resources").select(
        "id, name, email, availability_status"
    ).eq("manager_id", resource_id).execute()
    
    resource["direct_reports"] = reports_resp.data or []
    resource["direct_reports_count"] = len(reports_resp.data or [])
    
    return resource


@router.put(
    "/{resource_id}",
    summary="Update Resource",
    description="Update resource details"
)
async def update_resource(
    resource_id: str = Path(...),
    body: ResourceUpdate = None
) -> dict:
    """Update a resource."""
    db = get_supabase_client()
    
    # Validate UUID format
    try:
        UUID(resource_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid resource ID format. Must be a valid UUID.")
    
    # Check if exists
    existing = db.client.table("resources").select("id").eq(
        "id", resource_id
    ).execute()
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    # Build update dict
    update_data = {}
    
    if body.name is not None:
        update_data["name"] = body.name
    if body.email is not None:
        update_data["email"] = body.email
    if body.manager_id is not None:
        # Validate manager exists and is not self
        if body.manager_id:
            if body.manager_id == resource_id:
                raise HTTPException(
                    status_code=400,
                    detail="Resource cannot be its own manager"
                )
            mgr = db.client.table("resources").select("id").eq(
                "id", body.manager_id
            ).execute()
            if not mgr.data:
                raise HTTPException(status_code=400, detail="Manager not found")
        update_data["manager_id"] = body.manager_id or None
    if body.backup_resource_id is not None:
        if body.backup_resource_id:
            if body.backup_resource_id == resource_id:
                raise HTTPException(
                    status_code=400,
                    detail="Resource cannot be its own backup"
                )
            backup = db.client.table("resources").select("id").eq(
                "id", body.backup_resource_id
            ).execute()
            if not backup.data:
                raise HTTPException(status_code=400, detail="Backup resource not found")
        update_data["backup_resource_id"] = body.backup_resource_id or None
    if body.availability_status is not None:
        valid_statuses = ["ACTIVE", "ON_LEAVE", "UNAVAILABLE", "PARTIAL"]
        if body.availability_status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        update_data["availability_status"] = body.availability_status
    if body.leave_start_date is not None:
        update_data["leave_start_date"] = body.leave_start_date.isoformat()
    if body.leave_end_date is not None:
        update_data["leave_end_date"] = body.leave_end_date.isoformat()
    if body.timezone is not None:
        update_data["timezone"] = body.timezone
    if body.notification_email is not None:
        update_data["notification_email"] = body.notification_email
    if body.slack_user_id is not None:
        update_data["slack_user_id"] = body.slack_user_id
    if body.preferred_notification_channel is not None:
        valid_channels = ["EMAIL", "SLACK", "BOTH"]
        if body.preferred_notification_channel not in valid_channels:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid channel. Must be one of: {', '.join(valid_channels)}"
            )
        update_data["preferred_notification_channel"] = body.preferred_notification_channel
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # CRIT_004: Use timezone-aware datetime
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    response = db.client.table("resources").update(
        update_data
    ).eq("id", resource_id).execute()
    
    return {
        "success": True,
        "resource": response.data[0] if response.data else None
    }


# ==========================================
# MANAGER HIERARCHY ENDPOINTS
# ==========================================

@router.post(
    "/{resource_id}/manager",
    summary="Set Manager",
    description="Set or remove a resource's manager"
)
async def set_resource_manager(
    resource_id: str = Path(...),
    body: SetManagerRequest = None
) -> dict:
    """Set or remove a resource's manager."""
    db = get_supabase_client()
    
    # Check resource exists
    existing = db.client.table("resources").select("id, name").eq(
        "id", resource_id
    ).execute()
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    # Validate manager if provided
    manager_name = None
    if body.manager_id:
        if body.manager_id == resource_id:
            raise HTTPException(
                status_code=400,
                detail="Resource cannot be its own manager"
            )
        
        # Check for circular reference
        current_manager = body.manager_id
        visited = {resource_id}
        while current_manager:
            if current_manager in visited:
                raise HTTPException(
                    status_code=400,
                    detail="This would create a circular manager reference"
                )
            visited.add(current_manager)
            
            mgr_resp = db.client.table("resources").select(
                "id, name, manager_id"
            ).eq("id", current_manager).execute()
            
            if not mgr_resp.data:
                raise HTTPException(status_code=400, detail="Manager not found")
            
            if current_manager == body.manager_id:
                manager_name = mgr_resp.data[0]["name"]
            
            current_manager = mgr_resp.data[0].get("manager_id")
    
    # Update
    # CRIT_004: Use timezone-aware datetime
    db.client.table("resources").update({
        "manager_id": body.manager_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", resource_id).execute()
    
    return {
        "success": True,
        "resource_id": resource_id,
        "resource_name": existing.data[0]["name"],
        "manager_id": body.manager_id,
        "manager_name": manager_name
    }


@router.post(
    "/{resource_id}/backup",
    summary="Set Backup Resource",
    description="Set or remove a resource's backup"
)
async def set_resource_backup(
    resource_id: str = Path(...),
    body: SetBackupRequest = None
) -> dict:
    """Set or remove a resource's backup."""
    db = get_supabase_client()
    
    existing = db.client.table("resources").select("id, name").eq(
        "id", resource_id
    ).execute()
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    backup_name = None
    if body.backup_resource_id:
        if body.backup_resource_id == resource_id:
            raise HTTPException(
                status_code=400,
                detail="Resource cannot be its own backup"
            )
        
        backup_resp = db.client.table("resources").select("id, name").eq(
            "id", body.backup_resource_id
        ).execute()
        
        if not backup_resp.data:
            raise HTTPException(status_code=400, detail="Backup resource not found")
        
        backup_name = backup_resp.data[0]["name"]
    
    # CRIT_004: Use timezone-aware datetime
    db.client.table("resources").update({
        "backup_resource_id": body.backup_resource_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", resource_id).execute()
    
    return {
        "success": True,
        "resource_id": resource_id,
        "resource_name": existing.data[0]["name"],
        "backup_resource_id": body.backup_resource_id,
        "backup_name": backup_name
    }


# ==========================================
# AVAILABILITY ENDPOINTS
# ==========================================

@router.post(
    "/{resource_id}/availability",
    summary="Set Availability",
    description="Set a resource's availability status"
)
async def set_resource_availability(
    resource_id: str = Path(...),
    body: SetAvailabilityRequest = None
) -> dict:
    """Set a resource's availability status."""
    db = get_supabase_client()
    
    existing = db.client.table("resources").select("id, name").eq(
        "id", resource_id
    ).execute()
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    valid_statuses = ["ACTIVE", "ON_LEAVE", "UNAVAILABLE", "PARTIAL"]
    if body.availability_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    # Validate leave dates if on leave
    if body.availability_status == "ON_LEAVE":
        if not body.leave_start_date:
            raise HTTPException(
                status_code=400,
                detail="Leave start date is required when status is ON_LEAVE"
            )
    
    update_data = {
        "availability_status": body.availability_status,
        "leave_start_date": body.leave_start_date.isoformat() if body.leave_start_date else None,
        "leave_end_date": body.leave_end_date.isoformat() if body.leave_end_date else None,
        "updated_at": datetime.now(timezone.utc).isoformat()  # CRIT_004: Use timezone-aware datetime
    }
    
    # Clear leave dates if becoming active
    if body.availability_status == "ACTIVE":
        update_data["leave_start_date"] = None
        update_data["leave_end_date"] = None
    
    db.client.table("resources").update(update_data).eq("id", resource_id).execute()
    
    return {
        "success": True,
        "resource_id": resource_id,
        "resource_name": existing.data[0]["name"],
        "availability_status": body.availability_status,
        "leave_start_date": body.leave_start_date.isoformat() if body.leave_start_date else None,
        "leave_end_date": body.leave_end_date.isoformat() if body.leave_end_date else None
    }


# ==========================================
# ESCALATION CHAIN PREVIEW
# ==========================================

@router.get(
    "/{resource_id}/escalation-chain",
    summary="Get Escalation Chain",
    description="Preview the escalation chain for a resource"
)
async def get_resource_escalation_chain(
    resource_id: str = Path(...),
    program_id: Optional[str] = Query(None, description="Program for policy lookup")
) -> dict:
    """Get the escalation chain for a resource."""
    try:
        chain = get_escalation_chain(
            resource_id=UUID(resource_id),
            program_id=UUID(program_id) if program_id else None
        )
        
        return {
            "resource_id": resource_id,
            "chain": [
                {
                    "level": r.escalation_level,
                    "type": r.target_type.value if hasattr(r.target_type, 'value') else str(r.target_type),
                    "resource_id": str(r.resource_id),
                    "name": r.resource_name,
                    "email": r.email,
                    "is_available": r.is_available,
                    "availability_status": r.availability_status
                }
                for r in chain
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{resource_id}/direct-reports",
    summary="Get Direct Reports",
    description="Get resources that report directly to this resource"
)
async def get_direct_reports(resource_id: str = Path(...)) -> dict:
    """Get direct reports for a resource."""
    db = get_supabase_client()
    
    # Verify resource exists
    existing = db.client.table("resources").select("id, name").eq(
        "id", resource_id
    ).execute()
    
    if not existing.data:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    # Get direct reports
    response = db.client.table("resources").select(
        "id, external_id, name, email, role, availability_status, "
        "backup_resource_id"
    ).eq("manager_id", resource_id).order("name").execute()
    
    return {
        "manager_id": resource_id,
        "manager_name": existing.data[0]["name"],
        "direct_reports": response.data or [],
        "count": len(response.data or [])
    }
