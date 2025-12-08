"""
Impact Analysis Engine for Tracky PM.

Calculates the impact of delays based on reason category:
- SCOPE_INCREASE: More work discovered → extends duration
- STARTED_LATE: Couldn't begin on time → shifts window
- RESOURCE_PULLED: Team member reassigned → extends based on effort %
- TECHNICAL_BLOCKER: Complexity discovered → extends duration
- EXTERNAL_DEPENDENCY: Waiting on external → blocks until resolved

Key Features:
- Cascade calculation (downstream dependencies)
- Critical path impact detection
- Resource over-allocation warnings
- Milestone impact analysis
"""
from datetime import date, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
from dataclasses import dataclass
from enum import Enum

from app.core.database import get_supabase_client


class ReasonCategory(Enum):
    """Delay reason categories - determines recalculation math."""
    SCOPE_INCREASE = "SCOPE_INCREASE"
    STARTED_LATE = "STARTED_LATE"
    RESOURCE_PULLED = "RESOURCE_PULLED"
    TECHNICAL_BLOCKER = "TECHNICAL_BLOCKER"
    EXTERNAL_DEPENDENCY = "EXTERNAL_DEPENDENCY"
    SPECIFICATION_CHANGE = "SPECIFICATION_CHANGE"
    QUALITY_ISSUE = "QUALITY_ISSUE"
    OTHER = "OTHER"


@dataclass
class ImpactResult:
    """Result of impact analysis."""
    work_item_id: UUID
    work_item_name: str
    original_end: date
    proposed_end: date
    delay_days: int
    reason_category: str
    
    # Cascade impact
    affected_items: List[Dict[str, Any]]
    cascade_count: int
    
    # Critical path
    is_critical_path: bool
    critical_path_impact: Optional[str]
    
    # Resource impact
    resource_conflicts: List[Dict[str, Any]]
    
    # Milestone impact
    milestone_impacts: List[Dict[str, Any]]
    
    # Summary
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    recommendation: str


@dataclass
class DurationRecalculation:
    """Result of duration recalculation based on reason."""
    new_start: date
    new_end: date
    new_duration_days: int
    original_duration_days: int
    extension_days: int
    calculation_method: str
    explanation: str


def recalculate_duration(
    work_item_id: UUID,
    proposed_new_end: date,
    reason_category: ReasonCategory,
    reason_details: Optional[Dict[str, Any]] = None
) -> DurationRecalculation:
    """
    Recalculate work item duration based on delay reason.
    
    Different reasons require different math:
    
    SCOPE_INCREASE:
        - User provides: additional_work_percent (e.g., 25%)
        - Math: new_duration = original_duration * (1 + percent/100)
        - Result: Same start, extended end
    
    STARTED_LATE:
        - User provides: new_end_date
        - Math: Shift entire window (preserve duration)
        - Result: Both start and end shift
    
    RESOURCE_PULLED:
        - User provides: available_effort_percent (e.g., 50%)
        - Math: new_duration = original_duration / (effort_percent/100)
        - Result: Extended end based on reduced capacity
    
    TECHNICAL_BLOCKER / EXTERNAL_DEPENDENCY:
        - User provides: new_end_date
        - Math: Direct date override (blocker resolution unknown)
        - Result: New end date as provided
    
    Args:
        work_item_id: The work item to recalculate
        proposed_new_end: The proposed new end date
        reason_category: Why the delay occurred
        reason_details: Additional details based on reason type
    
    Returns:
        DurationRecalculation with new dates and explanation
    """
    db = get_supabase_client()
    
    # Get current work item data
    response = db.client.table("work_items").select(
        "current_start, current_end, planned_start, planned_end, "
        "planned_effort_hours, allocation_percent"
    ).eq("id", str(work_item_id)).execute()
    
    if not response.data:
        raise ValueError(f"Work item {work_item_id} not found")
    
    item = response.data[0]
    current_start = date.fromisoformat(item["current_start"])
    current_end = date.fromisoformat(item["current_end"])
    original_duration = (current_end - current_start).days
    
    reason_details = reason_details or {}
    
    # Calculate based on reason
    if reason_category == ReasonCategory.SCOPE_INCREASE:
        return _calc_scope_increase(
            current_start, current_end, original_duration,
            proposed_new_end, reason_details
        )
    
    elif reason_category == ReasonCategory.STARTED_LATE:
        return _calc_started_late(
            current_start, current_end, original_duration,
            proposed_new_end, reason_details
        )
    
    elif reason_category == ReasonCategory.RESOURCE_PULLED:
        return _calc_resource_pulled(
            current_start, current_end, original_duration,
            proposed_new_end, reason_details
        )
    
    elif reason_category in (
        ReasonCategory.TECHNICAL_BLOCKER,
        ReasonCategory.EXTERNAL_DEPENDENCY,
        ReasonCategory.SPECIFICATION_CHANGE,
        ReasonCategory.QUALITY_ISSUE,
        ReasonCategory.OTHER
    ):
        return _calc_direct_extension(
            current_start, current_end, original_duration,
            proposed_new_end, reason_category.value
        )
    
    else:
        # Default: direct date change
        return _calc_direct_extension(
            current_start, current_end, original_duration,
            proposed_new_end, "OTHER"
        )


def _calc_scope_increase(
    current_start: date,
    current_end: date,
    original_duration: int,
    proposed_new_end: date,
    details: Dict[str, Any]
) -> DurationRecalculation:
    """Calculate duration for scope increase."""
    additional_percent = details.get("additional_work_percent", 0)
    
    if additional_percent > 0:
        # Calculate based on percentage increase
        new_duration = int(original_duration * (1 + additional_percent / 100))
        calculated_end = current_start + timedelta(days=new_duration)
        
        # Use whichever is later: calculated or proposed
        new_end = max(calculated_end, proposed_new_end)
    else:
        # No percentage given, use proposed date
        new_end = proposed_new_end
    
    new_duration = (new_end - current_start).days
    extension = new_duration - original_duration
    
    explanation = (
        f"Scope increased by {additional_percent}%. "
        f"Original duration: {original_duration} days → "
        f"New duration: {new_duration} days (+{extension} days)"
    )
    
    return DurationRecalculation(
        new_start=current_start,
        new_end=new_end,
        new_duration_days=new_duration,
        original_duration_days=original_duration,
        extension_days=extension,
        calculation_method="SCOPE_PERCENTAGE",
        explanation=explanation
    )


def _calc_started_late(
    current_start: date,
    current_end: date,
    original_duration: int,
    proposed_new_end: date,
    details: Dict[str, Any]
) -> DurationRecalculation:
    """Calculate duration for late start (shift window)."""
    # Preserve original duration, shift both start and end
    delay_days = (proposed_new_end - current_end).days
    new_start = current_start + timedelta(days=delay_days)
    new_end = proposed_new_end
    
    explanation = (
        f"Task started late. Window shifted by {delay_days} days. "
        f"Duration preserved at {original_duration} days."
    )
    
    return DurationRecalculation(
        new_start=new_start,
        new_end=new_end,
        new_duration_days=original_duration,  # Preserved
        original_duration_days=original_duration,
        extension_days=0,  # No extension, just shift
        calculation_method="WINDOW_SHIFT",
        explanation=explanation
    )


def _calc_resource_pulled(
    current_start: date,
    current_end: date,
    original_duration: int,
    proposed_new_end: date,
    details: Dict[str, Any]
) -> DurationRecalculation:
    """Calculate duration for reduced resource capacity."""
    effort_percent = details.get("available_effort_percent", 100)
    
    if effort_percent > 0 and effort_percent < 100:
        # Calculate based on reduced effort
        # If 50% effort, work takes 2x as long
        new_duration = int(original_duration / (effort_percent / 100))
        calculated_end = current_start + timedelta(days=new_duration)
        
        # Use whichever is later
        new_end = max(calculated_end, proposed_new_end)
    else:
        new_end = proposed_new_end
    
    new_duration = (new_end - current_start).days
    extension = new_duration - original_duration
    
    explanation = (
        f"Resource at {effort_percent}% capacity. "
        f"Duration extended from {original_duration} to {new_duration} days."
    )
    
    return DurationRecalculation(
        new_start=current_start,
        new_end=new_end,
        new_duration_days=new_duration,
        original_duration_days=original_duration,
        extension_days=extension,
        calculation_method="REDUCED_CAPACITY",
        explanation=explanation
    )


def _calc_direct_extension(
    current_start: date,
    current_end: date,
    original_duration: int,
    proposed_new_end: date,
    reason: str
) -> DurationRecalculation:
    """Calculate for direct date extension (blockers, etc.)."""
    new_duration = (proposed_new_end - current_start).days
    extension = new_duration - original_duration
    
    explanation = (
        f"Direct extension due to {reason}. "
        f"New end date: {proposed_new_end.isoformat()} (+{extension} days)"
    )
    
    return DurationRecalculation(
        new_start=current_start,
        new_end=proposed_new_end,
        new_duration_days=new_duration,
        original_duration_days=original_duration,
        extension_days=extension,
        calculation_method="DIRECT_EXTENSION",
        explanation=explanation
    )


def calculate_cascade_impact(
    work_item_id: UUID,
    delay_days: int
) -> List[Dict[str, Any]]:
    """
    Calculate cascade impact on downstream dependencies.
    
    Uses recursive CTE to find all affected items.
    
    Args:
        work_item_id: The delayed work item
        delay_days: Number of days of delay
    
    Returns:
        List of affected downstream items with new dates
    """
    db = get_supabase_client()
    
    # Get downstream dependencies recursively
    # Using a simple approach since Supabase doesn't support recursive CTEs directly
    affected = []
    visited = set()
    queue = [(str(work_item_id), 1)]  # (item_id, depth)
    
    while queue and len(affected) < 100:  # Safety limit
        current_id, depth = queue.pop(0)
        
        if current_id in visited:
            continue
        visited.add(current_id)
        
        # Get direct successors
        response = db.client.table("dependencies").select(
            "successor_item_id, lag_days, "
            "work_items:successor_item_id(id, external_id, name, current_start, current_end, status)"
        ).eq("predecessor_item_id", current_id).execute()
        
        for dep in (response.data or []):
            successor = dep.get("work_items")
            if not successor or successor.get("status") in ("Cancelled", "Completed"):
                continue
            
            succ_id = successor["id"]
            if succ_id in visited:
                continue
            
            lag = dep.get("lag_days", 0)
            current_start = date.fromisoformat(successor["current_start"])
            current_end = date.fromisoformat(successor["current_end"])
            duration = (current_end - current_start).days
            
            new_start = current_start + timedelta(days=delay_days)
            new_end = current_end + timedelta(days=delay_days)
            
            affected.append({
                "id": succ_id,
                "external_id": successor["external_id"],
                "name": successor["name"],
                "current_start": current_start.isoformat(),
                "current_end": current_end.isoformat(),
                "new_start": new_start.isoformat(),
                "new_end": new_end.isoformat(),
                "slip_days": delay_days,
                "depth": depth
            })
            
            queue.append((succ_id, depth + 1))
    
    return affected


def check_resource_conflicts(
    work_item_id: UUID,
    new_start: date,
    new_end: date
) -> List[Dict[str, Any]]:
    """
    Check if the new dates cause resource over-allocation.
    
    Args:
        work_item_id: The work item being rescheduled
        new_start: Proposed new start date
        new_end: Proposed new end date
    
    Returns:
        List of resource conflicts
    """
    db = get_supabase_client()
    
    # Get the resource for this work item
    response = db.client.table("work_items").select(
        "resource_id, allocation_percent, resources(name, max_utilization)"
    ).eq("id", str(work_item_id)).execute()
    
    if not response.data:
        return []
    
    item = response.data[0]
    resource_id = item["resource_id"]
    allocation = item.get("allocation_percent", 100)
    resource = item.get("resources", {})
    max_util = resource.get("max_utilization", 100)
    
    # Find other tasks for this resource that overlap with new dates
    response = db.client.table("work_items").select(
        "id, external_id, name, current_start, current_end, allocation_percent"
    ).eq("resource_id", resource_id).neq(
        "id", str(work_item_id)
    ).not_.in_(
        "status", ["Cancelled", "Completed"]
    ).lte("current_start", new_end.isoformat()).gte(
        "current_end", new_start.isoformat()
    ).execute()
    
    conflicts = []
    overlapping = response.data or []
    
    # Calculate total allocation during overlap period
    total_allocation = allocation
    for task in overlapping:
        total_allocation += task.get("allocation_percent", 100)
    
    if total_allocation > max_util:
        conflicts.append({
            "resource_id": resource_id,
            "resource_name": resource.get("name"),
            "total_allocation": total_allocation,
            "max_utilization": max_util,
            "over_by": total_allocation - max_util,
            "overlapping_tasks": [
                {"id": t["id"], "name": t["name"], "allocation": t.get("allocation_percent", 100)}
                for t in overlapping
            ]
        })
    
    return conflicts


def analyze_impact(
    work_item_id: UUID,
    proposed_new_end: date,
    reason_category: str,
    reason_details: Optional[Dict[str, Any]] = None
) -> ImpactResult:
    """
    Perform comprehensive impact analysis for a proposed delay.
    
    This is the main entry point that combines:
    - Duration recalculation
    - Cascade impact
    - Resource conflicts
    - Risk assessment
    
    Args:
        work_item_id: The work item being delayed
        proposed_new_end: Proposed new end date
        reason_category: Why the delay occurred
        reason_details: Additional context
    
    Returns:
        Complete ImpactResult with all analysis
    """
    db = get_supabase_client()
    
    # Get work item details
    response = db.client.table("work_items").select(
        "id, external_id, name, current_start, current_end, is_critical_path"
    ).eq("id", str(work_item_id)).execute()
    
    if not response.data:
        raise ValueError(f"Work item {work_item_id} not found")
    
    item = response.data[0]
    original_end = date.fromisoformat(item["current_end"])
    delay_days = (proposed_new_end - original_end).days
    is_critical = item.get("is_critical_path", False)
    
    # Calculate cascade
    affected_items = calculate_cascade_impact(work_item_id, delay_days)
    
    # Check resource conflicts
    current_start = date.fromisoformat(item["current_start"])
    resource_conflicts = check_resource_conflicts(work_item_id, current_start, proposed_new_end)
    
    # Determine risk level
    risk_level = _determine_risk_level(
        delay_days=delay_days,
        is_critical_path=is_critical,
        cascade_count=len(affected_items),
        has_resource_conflicts=len(resource_conflicts) > 0
    )
    
    # Generate recommendation
    recommendation = _generate_recommendation(
        delay_days=delay_days,
        reason_category=reason_category,
        is_critical_path=is_critical,
        cascade_count=len(affected_items),
        risk_level=risk_level
    )
    
    # Critical path impact message
    critical_path_impact = None
    if is_critical:
        critical_path_impact = (
            f"This task is on the critical path. "
            f"A {delay_days}-day delay will directly impact the project end date."
        )
    
    return ImpactResult(
        work_item_id=UUID(item["id"]),
        work_item_name=item["name"],
        original_end=original_end,
        proposed_end=proposed_new_end,
        delay_days=delay_days,
        reason_category=reason_category,
        affected_items=affected_items,
        cascade_count=len(affected_items),
        is_critical_path=is_critical,
        critical_path_impact=critical_path_impact,
        resource_conflicts=resource_conflicts,
        milestone_impacts=[],  # TODO: Add milestone tracking
        risk_level=risk_level,
        recommendation=recommendation
    )


def _determine_risk_level(
    delay_days: int,
    is_critical_path: bool,
    cascade_count: int,
    has_resource_conflicts: bool
) -> str:
    """Determine overall risk level."""
    score = 0
    
    # Delay severity
    if delay_days >= 7:
        score += 3
    elif delay_days >= 3:
        score += 2
    elif delay_days >= 1:
        score += 1
    
    # Critical path
    if is_critical_path:
        score += 3
    
    # Cascade impact
    if cascade_count >= 5:
        score += 2
    elif cascade_count >= 2:
        score += 1
    
    # Resource conflicts
    if has_resource_conflicts:
        score += 1
    
    if score >= 6:
        return "CRITICAL"
    elif score >= 4:
        return "HIGH"
    elif score >= 2:
        return "MEDIUM"
    else:
        return "LOW"


def _generate_recommendation(
    delay_days: int,
    reason_category: str,
    is_critical_path: bool,
    cascade_count: int,
    risk_level: str
) -> str:
    """Generate a recommendation based on impact analysis."""
    recommendations = []
    
    if risk_level == "CRITICAL":
        recommendations.append("🚨 CRITICAL: Immediate PM attention required.")
    
    if is_critical_path:
        recommendations.append(
            f"Consider adding resources to recover {delay_days} days on critical path."
        )
    
    if cascade_count > 3:
        recommendations.append(
            f"Review {cascade_count} downstream tasks for potential parallel work."
        )
    
    if reason_category == "RESOURCE_PULLED":
        recommendations.append(
            "Consider reassigning to dedicated resource to prevent further delays."
        )
    
    if reason_category == "SCOPE_INCREASE":
        recommendations.append(
            "Evaluate if new scope can be deferred to future phase."
        )
    
    if reason_category == "EXTERNAL_DEPENDENCY":
        recommendations.append(
            "Set up daily check-in with external party to track progress."
        )
    
    if not recommendations:
        recommendations.append(f"Approve {delay_days}-day schedule adjustment.")
    
    return " ".join(recommendations)


def apply_approved_delay(
    work_item_id: UUID,
    new_end_date: date,
    approved_by: str,
    cascade: bool = True
) -> Dict[str, Any]:
    """
    Apply an approved delay to the work item and optionally cascade.
    
    CRIT_006: Uses atomic operations with rollback on failure.
    All updates succeed or all fail together.
    
    Args:
        work_item_id: The work item to update
        new_end_date: The approved new end date
        approved_by: Who approved the change
        cascade: Whether to propagate to downstream tasks
    
    Returns:
        Summary of changes made
        
    Raises:
        CascadeException: If cascade update fails (with rollback details)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    db = get_supabase_client()
    
    # Get current data
    response = db.client.table("work_items").select(
        "current_start, current_end"
    ).eq("id", str(work_item_id)).execute()
    
    if not response.data:
        raise ValueError(f"Work item {work_item_id} not found")
    
    item = response.data[0]
    old_end = item["current_end"]
    delay_days = (new_end_date - date.fromisoformat(old_end)).days
    
    # Track all changes for potential rollback
    rollback_log: List[Dict[str, Any]] = []
    
    try:
        # Step 1: Update the primary work item
        db.client.table("work_items").update({
            "current_end": new_end_date.isoformat()
        }).eq("id", str(work_item_id)).execute()
        
        rollback_log.append({
            "table": "work_items",
            "id": str(work_item_id),
            "field": "current_end",
            "old_value": old_end
        })
        
        # Step 2: Log the change
        audit_response = db.client.table("audit_logs").insert({
            "entity_type": "work_item",
            "entity_id": str(work_item_id),
            "action": "delay_approved",
            "field_changed": "current_end",
            "old_value": old_end,
            "new_value": new_end_date.isoformat(),
            "change_source": "status_response",
            "changed_by": approved_by
        }).execute()
        
        if audit_response.data:
            rollback_log.append({
                "table": "audit_logs",
                "id": audit_response.data[0].get("id"),
                "action": "delete"
            })
        
        # Step 3: Cascade to downstream tasks if requested
        cascaded = []
        if cascade and delay_days > 0:
            affected = calculate_cascade_impact(work_item_id, delay_days)
            
            for task in affected:
                # Store old values for potential rollback
                old_response = db.client.table("work_items").select(
                    "current_start, current_end"
                ).eq("id", task["id"]).execute()
                
                if old_response.data:
                    old_values = old_response.data[0]
                    
                    # Update the downstream task
                    db.client.table("work_items").update({
                        "current_start": task["new_start"],
                        "current_end": task["new_end"]
                    }).eq("id", task["id"]).execute()
                    
                    rollback_log.append({
                        "table": "work_items",
                        "id": task["id"],
                        "fields": {
                            "current_start": old_values["current_start"],
                            "current_end": old_values["current_end"]
                        }
                    })
                    
                    cascaded.append(task["external_id"])
        
        logger.info(
            f"Successfully applied delay to {work_item_id}: "
            f"{delay_days} days, {len(cascaded)} cascaded items"
        )
        
        return {
            "work_item_id": str(work_item_id),
            "old_end": old_end,
            "new_end": new_end_date.isoformat(),
            "delay_days": delay_days,
            "cascaded_tasks": cascaded,
            "cascade_count": len(cascaded)
        }
        
    except Exception as e:
        # CRIT_006: Rollback on failure
        logger.error(f"Cascade update failed, initiating rollback: {e}")
        
        rollback_errors = []
        for change in reversed(rollback_log):
            try:
                if change.get("action") == "delete":
                    db.client.table(change["table"]).delete().eq(
                        "id", change["id"]
                    ).execute()
                elif "fields" in change:
                    # Multi-field rollback
                    db.client.table(change["table"]).update(
                        change["fields"]
                    ).eq("id", change["id"]).execute()
                else:
                    # Single field rollback
                    db.client.table(change["table"]).update({
                        change["field"]: change["old_value"]
                    }).eq("id", change["id"]).execute()
            except Exception as rollback_error:
                rollback_errors.append({
                    "change": change,
                    "error": str(rollback_error)
                })
        
        # Import here to avoid circular imports
        from app.core.exceptions import CascadeError
        
        raise CascadeError(
            message=f"Cascade update failed: {e}",
            primary_work_item_id=str(work_item_id),
            successful_updates=[c.get("id") for c in rollback_log if c.get("table") == "work_items"],
            failed_updates=[],
            rollback_attempted=True
        )
