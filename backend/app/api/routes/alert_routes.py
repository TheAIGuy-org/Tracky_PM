"""
Alert API Routes for Tracky PM.

Provides endpoints for the Proactive Execution Tracking Loop:
- Status check response submission (via magic link)
- Alert management
- Approval workflow
- Escalation status
"""
from datetime import date, datetime, timedelta
from typing import Optional, List, TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Path, Header
from pydantic import BaseModel, Field

from app.services.magic_links import (
    validate_magic_link_token,
    get_token_info,
    record_token_use,
    TokenError,
    TokenExpiredError,
    TokenRevokedError
)
from app.services.alert_orchestrator import (
    process_status_response,
    approve_delay,
    reject_delay,
    get_pending_approvals as get_pending_approvals_service,
    run_daily_scan as run_daily_scan_service,
    scan_for_pending_status_checks,
    create_status_check_alert,
    check_and_escalate_timeouts
)
from app.services.impact_analysis import analyze_impact
from app.services.escalation import get_escalation_chain, get_escalation_summary
from app.core.database import get_supabase_client
from app.core.config import settings


router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


# ==========================================
# PYDANTIC MODELS
# ==========================================

class StatusResponseRequest(BaseModel):
    """Request body for status response submission."""
    token: str = Field(..., description="Magic link JWT token")
    reported_status: str = Field(
        ...,
        description="Status: ON_TRACK, DELAYED, BLOCKED, COMPLETED"
    )
    proposed_new_date: Optional[date] = Field(
        None,
        description="New end date if delayed"
    )
    reason_category: Optional[str] = Field(
        None,
        description="Why delayed: SCOPE_INCREASE, STARTED_LATE, etc."
    )
    reason_details: Optional[dict] = Field(
        None,
        description="Additional context based on reason"
    )
    comment: Optional[str] = Field(
        None,
        description="Free text comment"
    )


class ApprovalRequest(BaseModel):
    """Request body for delay approval."""
    response_id: str = Field(..., description="Response UUID to approve")
    cascade: bool = Field(True, description="Whether to cascade to dependencies")


class RejectionRequest(BaseModel):
    """Request body for delay rejection."""
    response_id: str = Field(..., description="Response UUID to reject")
    reason: str = Field(..., description="Rejection reason")


class ImpactAnalysisRequest(BaseModel):
    """Request body for impact analysis preview."""
    work_item_id: str = Field(..., description="Work item UUID")
    proposed_new_date: date = Field(..., description="Proposed new end date")
    reason_category: Optional[str] = Field(None, description="Delay reason")



class ManualAlertRequest(BaseModel):
    """Request body for manually creating an alert."""
    work_item_id: str = Field(..., description="Work item UUID")
    deadline: Optional[date] = Field(None, description="Override deadline")


# ==========================================
# FRONTEND-COMPATIBLE MAGIC LINK ENDPOINTS
# These endpoints match the frontend API expectations
# ==========================================

@router.get(
    "/respond/{token}",
    summary="Validate Magic Link Token",
    description="Validates a magic link token and returns task details for the response form"
)
async def validate_response_token_by_path(
    token: str = Path(..., description="Magic link JWT token")
) -> dict:
    """
    Validate a magic link token before showing the response form.
    Returns task details if valid, error message if not.
    
    This endpoint matches frontend expectation: GET /api/alerts/respond/{token}
    """
    info = get_token_info(token)
    
    if not info.get("valid"):
        raise HTTPException(
            status_code=401,
            detail=info.get("error", "Invalid or expired link")
        )
    
    # Get work item details
    db = get_supabase_client()
    
    response = db.client.table("work_items").select(
        "id, external_id, name, current_start, current_end, status, completion_percent, "
        "is_critical_path, resources(id, name, email), "
        "phases(name, projects(name, programs(name)))"
    ).eq("id", info["work_item_id"]).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Work item not found")
    
    work_item = response.data[0]
    phases = work_item.get("phases") or {}
    projects = phases.get("projects") or {}
    programs = projects.get("programs") or {}
    resource = work_item.get("resources") or {}
    
    # Get any existing responses
    resp = db.client.table("work_item_responses").select(
        "id, reported_status, proposed_new_date, reason_category, comment, created_at"
    ).eq("work_item_id", info["work_item_id"]).eq(
        "is_latest", True
    ).execute()
    
    latest_response = resp.data[0] if resp.data else None
    
    return {
        "valid": True,
        "alert_id": info.get("alert_id"),
        "work_item_id": info["work_item_id"],
        "work_item": {
            "id": work_item["id"],
            "external_id": work_item["external_id"],
            "name": work_item["name"],
            "planned_end": work_item["current_end"],
            "current_end": work_item["current_end"],
            "deadline": work_item["current_end"],
            "status": work_item["status"],
            "completion_percent": work_item.get("completion_percent", 0),
            "is_critical_path": work_item.get("is_critical_path", False),
            "phase_name": phases.get("name"),
            "project_name": projects.get("name"),
            "program_name": programs.get("name")
        },
        "responder": {
            "id": resource.get("id"),
            "name": resource.get("name", "Unknown"),
            "email": resource.get("email", "")
        },
        "deadline": work_item["current_end"],
        "can_update": True,
        "token_expires_at": info.get("expires_at"),
        "previous_response": {
            "id": latest_response["id"],
            "reported_status": latest_response["reported_status"],
            "status": latest_response["reported_status"],  # alias for frontend
            "proposed_new_date": latest_response.get("proposed_new_date"),
            "proposed_date": latest_response.get("proposed_new_date"),  # alias
            "reason_category": latest_response.get("reason_category"),
            "comment": latest_response.get("comment"),
            "created_at": latest_response["created_at"],
            "submitted_at": latest_response["created_at"]  # alias
        } if latest_response else None
    }


class StatusResponseBodyRequest(BaseModel):
    """Request body for status response submission (without token in body)."""
    reported_status: str = Field(
        ...,
        description="Status: ON_TRACK, DELAYED, BLOCKED, COMPLETED"
    )
    proposed_new_date: Optional[date] = Field(
        None,
        description="New end date if delayed"
    )
    reason_category: Optional[str] = Field(
        None,
        description="Why delayed: SCOPE_INCREASE, STARTED_LATE, etc."
    )
    reason_details: Optional[dict] = Field(
        None,
        description="Additional context based on reason"
    )
    comment: Optional[str] = Field(
        None,
        description="Free text comment"
    )


@router.post(
    "/respond/{token}",
    summary="Submit Status Response",
    description="Submit a response to a status check alert via magic link"
)
async def submit_status_response_by_path(
    request: Request,
    token: str = Path(..., description="Magic link JWT token"),
    body: StatusResponseBodyRequest = None,
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key", description="Issue #9: Idempotency key to prevent duplicate submissions")
) -> dict:
    """
    Submit a response to a status check.
    
    This endpoint matches frontend expectation: POST /api/alerts/respond/{token}
    
    Supports X-Idempotency-Key header to prevent duplicate submissions.
    """
    # Validate token
    try:
        claims = validate_magic_link_token(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=401,
            detail="This link has expired. Please request a new status check."
        )
    except TokenRevokedError:
        raise HTTPException(
            status_code=401,
            detail="This link has been disabled. Please contact your PM."
        )
    except TokenError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    # CRITICAL FIX (C): Prevent "Time Travel" - check work item isn't already finalized
    # A user shouldn't be able to re-open a completed/cancelled task with an old link
    work_item_id = claims.get("wid")
    if work_item_id:
        db = get_supabase_client()
        work_item_check = db.client.table("work_items").select("status").eq(
            "id", work_item_id
        ).execute()
        
        if work_item_check.data:
            work_item_status = work_item_check.data[0].get("status")
            if work_item_status in ("Completed", "Cancelled"):
                raise HTTPException(
                    status_code=400,
                    detail=f"This task has already been {work_item_status.lower()}. No further updates are allowed."
                )
    
    # Record token use
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    record_token_use(token, client_ip)
    
    # Get alert ID from token or lookup
    alert_id = claims.get("aid")
    if not alert_id:
        db = get_supabase_client()
        resp = db.client.table("alerts").select("id").eq(
            "work_item_id", claims["wid"]
        ).order("created_at", desc=True).limit(1).execute()
        
        if resp.data:
            alert_id = resp.data[0]["id"]
    
    # Validate reported_status
    valid_statuses = ["ON_TRACK", "DELAYED", "BLOCKED", "COMPLETED", "CANCELLED"]
    if body.reported_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    # Validate delayed response has required fields
    if body.reported_status == "DELAYED":
        if not body.proposed_new_date:
            raise HTTPException(
                status_code=400,
                detail="New date is required when reporting a delay"
            )
    
    # Process the response
    try:
        # Issue #9: Pass idempotency key to prevent duplicate submissions
        result = process_status_response(
            alert_id=UUID(alert_id) if alert_id else None,
            responder_resource_id=UUID(claims["sub"]),
            reported_status=body.reported_status,
            proposed_new_date=body.proposed_new_date,
            reason_category=body.reason_category,
            reason_details=body.reason_details,
            comment=body.comment,
            client_ip=client_ip,
            user_agent=user_agent,
            idempotency_key=x_idempotency_key
        )
        return {
            "success": True,
            "response": result.get("response"),
            "impact_analysis": result.get("impact_analysis")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# FRONTEND-COMPATIBLE APPROVAL ENDPOINTS
# ==========================================

@router.get(
    "/pending-approvals",
    summary="Get Pending Approvals",
    description="Get all delay requests awaiting approval"
)
async def get_pending_approvals_frontend() -> dict:
    """
    List all pending delay approval requests.
    
    This endpoint matches frontend expectation: GET /api/alerts/pending-approvals
    """
    approvals = get_pending_approvals_service()
    
    return {
        "count": len(approvals),
        "approvals": approvals
    }


@router.post(
    "/responses/{response_id}/approval",
    summary="Process Approval",
    description="Approve or reject a delay request"
)
async def process_approval_frontend(
    response_id: str = Path(...),
    action: str = Query(..., description="approve or reject"),
    reason: Optional[str] = Query(None, description="Rejection reason")
) -> dict:
    """
    Approve or reject a delay request.
    
    This endpoint matches frontend expectation: 
    POST /api/alerts/responses/{responseId}/approval?action=approve|reject
    """
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    
    if action == "reject" and not reason:
        raise HTTPException(status_code=400, detail="Rejection reason is required")
    
    # TODO: Get approver from auth context
    approver_id = UUID("00000000-0000-0000-0000-000000000001")
    
    try:
        if action == "approve":
            result = approve_delay(
                response_id=UUID(response_id),
                approver_resource_id=approver_id,
                cascade=True
            )
        else:
            result = reject_delay(
                response_id=UUID(response_id),
                rejector_resource_id=approver_id,
                rejection_reason=reason
            )
        
        return {
            "success": True,
            "response": result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# FRONTEND-COMPATIBLE SCAN & TRIGGER ENDPOINTS
# ==========================================

@router.get(
    "/due-tomorrow",
    summary="Get Work Items Due Tomorrow",
    description="Get work items with deadlines tomorrow for daily scan preview"
)
async def get_due_tomorrow() -> dict:
    """
    Get work items due tomorrow.
    
    This endpoint matches frontend expectation: GET /api/alerts/due-tomorrow
    """
    db = get_supabase_client()
    
    tomorrow = date.today() + timedelta(days=1)
    
    response = db.client.table("work_items").select(
        "id, external_id, name, current_end, resource_id, "
        "resources(id, name, email)"
    ).eq("current_end", tomorrow.isoformat()).not_.in_(
        "status", ["Completed", "Cancelled"]
    ).execute()
    
    items = []
    for item in (response.data or []):
        resource = item.get("resources") or {}
        
        # Check if alert already exists
        alert_resp = db.client.table("alerts").select("id, status").eq(
            "work_item_id", item["id"]
        ).eq("deadline_date", tomorrow.isoformat()).execute()
        
        existing_alert = alert_resp.data[0] if alert_resp.data else None
        
        items.append({
            "work_item_id": item["id"],
            "work_item_external_id": item["external_id"],
            "work_item_name": item["name"],
            "deadline": item["current_end"],
            "resource_id": item.get("resource_id"),
            "resource_name": resource.get("name", "Unassigned"),
            "resource_email": resource.get("email", ""),
            "alert_exists": existing_alert is not None,
            "existing_alert_status": existing_alert["status"] if existing_alert else None
        })
    
    return {
        "date": tomorrow.isoformat(),
        "items": items,
        "count": len(items)
    }


@router.post(
    "/trigger",
    summary="Trigger Manual Alert",
    description="Manually trigger a status check alert for a work item"
)
async def trigger_manual_alert(
    work_item_id: str = Query(...),
    urgency: str = Query("NORMAL", description="NORMAL, HIGH, or CRITICAL")
) -> dict:
    """
    Manually trigger a status check alert.
    
    This endpoint matches frontend expectation: 
    POST /api/alerts/trigger?work_item_id=...&urgency=...
    """
    db = get_supabase_client()
    
    # Get work item details
    wi_resp = db.client.table("work_items").select(
        "id, resource_id, current_end, phases(projects(program_id)), resources(id, name, email)"
    ).eq("id", work_item_id).execute()
    
    if not wi_resp.data:
        raise HTTPException(status_code=404, detail="Work item not found")
    
    work_item = wi_resp.data[0]
    resource = work_item.get("resources") or {}
    deadline = date.fromisoformat(work_item["current_end"])
    program_id = work_item.get("phases", {}).get("projects", {}).get("program_id")
    
    # Create the alert using the existing service
    result = create_status_check_alert(
        work_item_id=UUID(work_item_id),
        deadline=deadline,
        resource_id=UUID(work_item["resource_id"]),
        program_id=UUID(program_id) if program_id else None
    )
    
    return {
        "success": True,
        "alert": {
            "id": result.get("alert_id"),
            "work_item_id": work_item_id,
            "recipient_name": resource.get("name"),
            "recipient_email": resource.get("email"),
            "urgency": urgency,
            "magic_link": result.get("magic_link")
        }
    }


@router.post(
    "/run-scan",
    summary="Run Daily Scan",
    description="Manually trigger the daily status check scan"
)
async def run_daily_scan_frontend() -> dict:
    """
    Run the daily scan for status checks.
    
    This endpoint matches frontend expectation: POST /api/alerts/run-scan
    """
    result = run_daily_scan_service()
    return {
        "success": True,
        "alerts_created": result.get("alerts_created", 0),
        "work_items_checked": result.get("work_items_checked", 0)
    }


# ==========================================
# LEGACY MAGIC LINK RESPONSE ENDPOINTS
# ==========================================

@router.get(
    "/respond/validate",
    summary="Validate Magic Link Token (Legacy)",
    description="Validates a magic link token and returns task details for the response form"
)
async def validate_response_token(
    token: str = Query(..., description="Magic link JWT token")
) -> dict:
    """
    Validate a magic link token before showing the response form.
    
    Returns task details if valid, error message if not.
    """
    info = get_token_info(token)
    
    if not info.get("valid"):
        raise HTTPException(
            status_code=401,
            detail=info.get("error", "Invalid or expired link")
        )
    
    # Get work item details
    db = get_supabase_client()
    
    response = db.client.table("work_items").select(
        "id, external_id, name, current_start, current_end, status, "
        "is_critical_path, resources(name, email), "
        "phases(name, projects(name, programs(name)))"
    ).eq("id", info["work_item_id"]).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Work item not found")
    
    work_item = response.data[0]
    
    # Get any existing responses
    resp = db.client.table("work_item_responses").select(
        "reported_status, proposed_new_date, created_at"
    ).eq("work_item_id", info["work_item_id"]).eq(
        "is_latest", True
    ).execute()
    
    latest_response = resp.data[0] if resp.data else None
    
    return {
        "valid": True,
        "work_item": {
            "id": work_item["id"],
            "external_id": work_item["external_id"],
            "name": work_item["name"],
            "deadline": work_item["current_end"],
            "status": work_item["status"],
            "is_critical_path": work_item.get("is_critical_path", False),
            "resource": work_item.get("resources", {}),
            "program": work_item.get("phases", {}).get("projects", {}).get("programs", {}).get("name")
        },
        "token_expires_at": info.get("expires_at"),
        "previous_response": {
            "status": latest_response["reported_status"],
            "proposed_date": latest_response.get("proposed_new_date"),
            "submitted_at": latest_response["created_at"]
        } if latest_response else None,
        "can_update": True  # Token is updateable until deadline
    }


@router.post(
    "/respond",
    summary="Submit Status Response",
    description="Submit a response to a status check alert via magic link"
)
async def submit_status_response(
    request: Request,
    body: StatusResponseRequest,
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key", description="Issue #9: Idempotency key to prevent duplicate submissions")
) -> dict:
    """
    Submit a response to a status check.
    
    This is the main endpoint called when a user clicks a magic link
    and submits their status update.
    
    Supports X-Idempotency-Key header to prevent duplicate submissions.
    """
    # Validate token
    try:
        claims = validate_magic_link_token(body.token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=401,
            detail="This link has expired. Please request a new status check."
        )
    except TokenRevokedError:
        raise HTTPException(
            status_code=401,
            detail="This link has been disabled. Please contact your PM."
        )
    except TokenError as e:
        raise HTTPException(status_code=401, detail=str(e))
    
    # CRITICAL FIX (C): Prevent "Time Travel" - check work item isn't already finalized
    work_item_id = claims.get("wid")
    if work_item_id:
        db = get_supabase_client()
        work_item_check = db.client.table("work_items").select("status").eq(
            "id", work_item_id
        ).execute()
        
        if work_item_check.data:
            work_item_status = work_item_check.data[0].get("status")
            if work_item_status in ("Completed", "Cancelled"):
                raise HTTPException(
                    status_code=400,
                    detail=f"This task has already been {work_item_status.lower()}. No further updates are allowed."
                )
    
    # Record token use
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    record_token_use(body.token, client_ip)
    
    # Get alert ID from token or lookup
    alert_id = claims.get("aid")
    if not alert_id:
        # Find the latest alert for this work item
        db = get_supabase_client()
        resp = db.client.table("alerts").select("id").eq(
            "work_item_id", claims["wid"]
        ).order("created_at", desc=True).limit(1).execute()
        
        if resp.data:
            alert_id = resp.data[0]["id"]
    
    # Validate reported_status
    valid_statuses = ["ON_TRACK", "DELAYED", "BLOCKED", "COMPLETED"]
    if body.reported_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    # Validate delayed response has required fields
    if body.reported_status == "DELAYED":
        if not body.proposed_new_date:
            raise HTTPException(
                status_code=400,
                detail="New date is required when reporting a delay"
            )
        if not body.reason_category:
            raise HTTPException(
                status_code=400,
                detail="Reason category is required when reporting a delay"
            )
    
    # Process the response
    try:
        # Issue #9: Pass idempotency key to prevent duplicate submissions
        result = process_status_response(
            alert_id=UUID(alert_id) if alert_id else None,
            responder_resource_id=UUID(claims["sub"]),
            reported_status=body.reported_status,
            proposed_new_date=body.proposed_new_date,
            reason_category=body.reason_category,
            reason_details=body.reason_details,
            comment=body.comment,
            client_ip=client_ip,
            user_agent=user_agent,
            idempotency_key=x_idempotency_key
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# IMPACT ANALYSIS ENDPOINTS
# ==========================================

@router.post(
    "/impact-analysis",
    summary="Preview Delay Impact",
    description="Calculate the impact of a proposed delay before submitting"
)
async def preview_impact_analysis(body: ImpactAnalysisRequest) -> dict:
    """
    Preview what impact a delay would have.
    
    Called by the response form to show cascade effects.
    """
    try:
        impact = analyze_impact(
            work_item_id=UUID(body.work_item_id),
            proposed_new_end=body.proposed_new_date,
            reason_category=body.reason_category or "OTHER"
        )
        
        return {
            "work_item_name": impact.work_item_name,
            "original_end": impact.original_end.isoformat(),
            "proposed_end": impact.proposed_end.isoformat(),
            "delay_days": impact.delay_days,
            "is_critical_path": impact.is_critical_path,
            "critical_path_impact": impact.critical_path_impact,
            "cascade_count": impact.cascade_count,
            "affected_items": impact.affected_items[:10],  # Top 10
            "resource_conflicts": impact.resource_conflicts,
            "risk_level": impact.risk_level,
            "recommendation": impact.recommendation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# APPROVAL WORKFLOW ENDPOINTS
# ==========================================

@router.get(
    "/approvals/pending",
    summary="Get Pending Approvals (Old)",
    description="Get all delay requests awaiting approval - legacy endpoint"
)
async def list_pending_approvals_old() -> dict:
    """List all pending delay approval requests (legacy endpoint)."""
    approvals = get_pending_approvals_service()
    
    return {
        "count": len(approvals),
        "approvals": approvals
    }


@router.post(
    "/approvals/approve",
    summary="Approve Delay",
    description="Approve a delay request and apply schedule changes"
)
async def approve_delay_request(body: ApprovalRequest) -> dict:
    """
    Approve a delay request.
    
    This updates the work item dates and cascades to dependencies.
    """
    # TODO: Get approver from auth context
    # For now, using a placeholder
    approver_id = UUID("00000000-0000-0000-0000-000000000001")
    
    try:
        result = approve_delay(
            response_id=UUID(body.response_id),
            approver_resource_id=approver_id,
            cascade=body.cascade
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/approvals/reject",
    summary="Reject Delay",
    description="Reject a delay request"
)
async def reject_delay_request(body: RejectionRequest) -> dict:
    """Reject a delay request with a reason."""
    # TODO: Get rejector from auth context
    rejector_id = UUID("00000000-0000-0000-0000-000000000001")
    
    try:
        result = reject_delay(
            response_id=UUID(body.response_id),
            rejector_resource_id=rejector_id,
            rejection_reason=body.reason
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ALERT MANAGEMENT ENDPOINTS
# ==========================================

@router.get(
    "/",
    summary="List Alerts",
    description="Get alerts with filtering options"
)
async def list_alerts(
    status: Optional[str] = Query(None, description="Filter by status"),
    work_item_id: Optional[str] = Query(None, description="Filter by work item"),
    resource_id: Optional[str] = Query(None, description="Filter by recipient"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
) -> dict:
    """List alerts with optional filters."""
    db = get_supabase_client()
    
    query = db.client.table("alerts").select(
        "*, work_items(external_id, name), resources:actual_recipient_id(name, email)"
    )
    
    if status:
        query = query.eq("status", status)
    if work_item_id:
        query = query.eq("work_item_id", work_item_id)
    if resource_id:
        query = query.eq("actual_recipient_id", resource_id)
    
    response = query.order("created_at", desc=True).range(
        offset, offset + limit - 1
    ).execute()
    
    return {
        "data": response.data or [],
        "count": len(response.data or []),
        "limit": limit,
        "offset": offset
    }


@router.get(
    "/responses",
    summary="List Responses",
    description="Get status responses with filtering"
)
async def list_responses(
    work_item_id: Optional[str] = Query(None),
    reported_status: Optional[str] = Query(None),
    approval_status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
) -> dict:
    """List status responses."""
    db = get_supabase_client()
    
    query = db.client.table("work_item_responses").select(
        "*, work_items(external_id, name), resources:responder_resource_id(name)"
    )
    
    if work_item_id:
        query = query.eq("work_item_id", work_item_id)
    if reported_status:
        query = query.eq("reported_status", reported_status)
    if approval_status:
        query = query.eq("approval_status", approval_status)
    
    response = query.order("created_at", desc=True).range(
        offset, offset + limit - 1
    ).execute()
    
    return {
        "data": response.data or [],
        "count": len(response.data or []),
        "limit": limit,
        "offset": offset
    }


@router.get(
    "/{alert_id}",
    summary="Get Alert Details",
    description="Get detailed information about a specific alert"
)
async def get_alert_details(alert_id: str) -> dict:
    """Get detailed alert information including escalation history."""
    db = get_supabase_client()
    
    response = db.client.table("alerts").select(
        "*, work_items(id, external_id, name, current_end, is_critical_path), "
        "resources:actual_recipient_id(name, email), "
        "work_item_responses(id, reported_status, proposed_new_date, created_at, is_latest)"
    ).eq("id", alert_id).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert = response.data[0]
    
    # Get escalation summary
    escalation = get_escalation_summary(UUID(alert_id))
    
    return {
        **alert,
        "escalation_history": escalation
    }


@router.post(
    "/manual",
    summary="Create Manual Alert",
    description="Manually create a status check alert for a work item"
)
async def create_manual_alert(body: ManualAlertRequest) -> dict:
    """
    Manually trigger a status check alert.
    
    Useful for ad-hoc status requests outside the normal schedule.
    """
    db = get_supabase_client()
    
    # Get work item details
    response = db.client.table("work_items").select(
        "id, resource_id, current_end, phases(projects(program_id))"
    ).eq("id", body.work_item_id).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Work item not found")
    
    work_item = response.data[0]
    deadline = body.deadline or date.fromisoformat(work_item["current_end"])
    program_id = work_item.get("phases", {}).get("projects", {}).get("program_id")
    
    result = create_status_check_alert(
        work_item_id=UUID(body.work_item_id),
        deadline=deadline,
        resource_id=UUID(work_item["resource_id"]),
        program_id=UUID(program_id) if program_id else None
    )
    
    return result


# ==========================================
# ESCALATION ENDPOINTS
# ==========================================

@router.get(
    "/escalation/chain/{resource_id}",
    summary="Get Escalation Chain",
    description="Get the escalation chain for a resource"
)
async def get_resource_escalation_chain(
    resource_id: str,
    program_id: Optional[str] = Query(None, description="Program for policy lookup")
) -> dict:
    """Get the full escalation chain for a resource."""
    chain = get_escalation_chain(
        resource_id=UUID(resource_id),
        program_id=UUID(program_id) if program_id else None
    )
    
    return {
        "resource_id": resource_id,
        "chain": [
            {
                "level": r.escalation_level,
                "type": r.target_type.value,
                "resource_id": str(r.resource_id),
                "name": r.resource_name,
                "email": r.email,
                "is_available": r.is_available,
                "availability_status": r.availability_status
            }
            for r in chain
        ]
    }


# ==========================================
# ADMIN / SCHEDULER ENDPOINTS
# ==========================================

@router.post(
    "/admin/run-scan",
    summary="Run Daily Scan (Admin)",
    description="Manually trigger the daily status check scan - admin endpoint"
)
async def trigger_daily_scan_admin() -> dict:
    """
    Manually run the daily scan for status checks (admin endpoint).
    
    This is normally run by a scheduled job but can be triggered manually.
    """
    result = run_daily_scan_service()
    return result


@router.post(
    "/admin/check-escalations",
    summary="Check Escalation Timeouts",
    description="Check for and process escalation timeouts"
)
async def trigger_escalation_check() -> dict:
    """
    Check for alerts that need escalation due to timeout.
    
    This is normally run periodically but can be triggered manually.
    """
    escalated = check_and_escalate_timeouts()
    return {
        "escalated_count": len(escalated),
        "escalated": escalated
    }


@router.get(
    "/admin/pending-checks",
    summary="Get Pending Status Checks",
    description="Preview which tasks would get status check alerts today"
)
async def preview_pending_checks(
    target_date: Optional[date] = Query(None, description="Date to check for")
) -> dict:
    """Preview tasks that need status checks for a given date."""
    pending = scan_for_pending_status_checks(target_date=target_date)
    
    return {
        "date": (target_date or date.today()).isoformat(),
        "count": len(pending),
        "tasks": [
            {
                "work_item_id": str(p.work_item_id),
                "external_id": p.external_id,
                "name": p.work_item_name,
                "deadline": p.deadline.isoformat(),
                "resource": p.resource_name,
                "is_critical_path": p.is_critical_path,
                "urgency": p.urgency,
                "has_existing_alert": p.existing_alert_id is not None
            }
            for p in pending
        ]
    }


