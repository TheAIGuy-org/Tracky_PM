"""
Import API Routes for Tracky PM.
Handles Excel file uploads and import orchestration.

Implements Three-Pass Import with Transaction Safety:
1. PARSE: Parse Excel file (no DB writes)
2. VALIDATE: Comprehensive validation (no DB writes)
3. EXECUTE: Atomic transaction (all-or-nothing)

Features:
- Full audit trail logging
- Baseline versioning
- Resource utilization checks
- Circular dependency detection
- Context-aware soft delete
- Transaction rollback on failure
"""
import hashlib
import io
import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, File, UploadFile, HTTPException, Query

from app.core.config import settings
from app.core.database import get_supabase_client
from app.core.exceptions import (
    TrackyException,
    ValidationError,
    ImportError,
    FileFormatError,
    DatabaseError,
)
from app.models.schemas import ImportResponse, ImportSummary
from app.services.parser import ExcelParser, DataValidator
from app.services.parser.validators import DependencyGraphValidator
from app.services.ingestion import (
    SmartMergeEngine,
    ResourceSyncService,
    HierarchySyncService,
    DependencySyncService,
)
from app.services.ingestion.validators import ImportValidator, ValidationResult
from app.services.recalculation import RecalculationEngine


router = APIRouter(prefix="/import", tags=["Import"])


@router.post(
    "/upload",
    response_model=ImportResponse,
    summary="Import Excel File",
    description="""
    Upload and import an Excel file containing project data.
    
    **Three-Pass Import Process:**
    1. **PARSE**: Parse Excel file, extract all data (no DB writes)
    2. **VALIDATE**: Comprehensive validation including:
       - Required fields and data types
       - Date logic (end >= start)
       - Circular dependency detection
       - Resource over-allocation warnings
    3. **EXECUTE**: Atomic transaction with rollback on failure
    
    **Smart Merge Algorithm:**
    - INSERT new tasks (baseline = current)
    - UPDATE existing tasks (baseline only, preserve current/actual)
    - Context-aware soft delete:
      - Not Started → Cancelled
      - In Progress → Flagged for PM review
      - Completed → Preserved
    
    **Compliance:**
    - Full audit trail for SOX/GDPR/ISO
    - Baseline versioning for scope tracking
    """
)
async def import_excel(
    file: UploadFile = File(..., description="Excel file (.xlsx, .xls)"),
    perform_ghost_check: bool = Query(
        True,
        description="Cancel tasks missing from Excel"
    ),
    trigger_recalculation: bool = Query(
        True,
        description="Trigger date recalculation after import"
    ),
    save_baseline_version: bool = Query(
        True,
        description="Save baseline snapshot before import"
    ),
    dry_run: bool = Query(
        False,
        description="Validate only, don't commit changes"
    ),
) -> ImportResponse:
    """
    Import an Excel file and sync data to database.
    
    This is the main entry point for the Ingestion Engine.
    Implements atomic transaction with full rollback on failure.
    """
    start_time = time.time()
    db = get_supabase_client()
    
    # Validate file extension
    filename = file.filename or ""
    if not filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Only .xlsx and .xls files are accepted."
        )
    
    # Initialize response structure
    response = ImportResponse(
        status="pending",
        summary=ImportSummary(),
        warnings=[],
        errors=[],
        flagged_items=[],
        execution_time_ms=0,
    )
    
    # Validate file size
    max_size = settings.max_upload_size_mb * 1024 * 1024
    contents = await file.read()
    
    if len(contents) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.max_upload_size_mb}MB"
        )
    
    # Calculate file hash for audit
    file_hash = hashlib.sha256(contents).hexdigest()
    
    try:
        # ==========================================
        # PASS 1: PARSE (No DB writes)
        # ==========================================
        file_obj = io.BytesIO(contents)
        parser = ExcelParser(file_obj, file.filename or "upload.xlsx")
        parsed_data = parser.parse()
        
        # ==========================================
        # PASS 2: VALIDATE ALL (No DB writes)
        # ==========================================
        validator = ImportValidator()
        validation_result = validator.validate_all(
            parsed_work_items=parsed_data["work_items"],
            parsed_resources=parsed_data["resources"],
            parsed_dependencies=parsed_data["dependencies"],
            program_id=""  # Will be determined during hierarchy sync
        )
        
        # Check for critical errors
        if not validation_result.is_valid:
            response.status = "validation_failed"
            response.errors = [
                {
                    "row": e.row_num,
                    "field": e.field,
                    "value": e.value,
                    "message": e.message
                }
                for e in validation_result.errors
            ]
            response.warnings = [
                {
                    "row": w.row_num,
                    "field": w.field,
                    "message": w.message
                }
                for w in validation_result.warnings
            ]
            response.execution_time_ms = int((time.time() - start_time) * 1000)
            return response
        
        # Add validation warnings to response
        for w in validation_result.warnings:
            # Determine warning type based on field
            warning_type = "validation"
            if "resource" in w.field.lower():
                warning_type = "resource"
            elif "depend" in w.field.lower():
                warning_type = "dependency"
            
            response.warnings.append({
                "type": warning_type,
                "row": w.row_num,
                "field": w.field,
                "message": w.message
            })
        
        # If dry run, return validation results without executing
        if dry_run:
            response.status = "validation_passed"
            response.summary.work_items_parsed = len(parsed_data["work_items"])
            response.summary.resources_parsed = len(parsed_data["resources"])
            response.summary.dependencies_parsed = len(parsed_data["dependencies"])
            response.execution_time_ms = int((time.time() - start_time) * 1000)
            return response
        
        # ==========================================
        # PASS 3: EXECUTE (Atomic Transaction)
        # ==========================================
        with db.transaction() as tx:
            try:
                # Initialize services
                resource_sync = ResourceSyncService()
                hierarchy_sync = HierarchySyncService()
                smart_merge = SmartMergeEngine()
                dependency_sync = DependencySyncService()
                
                # Step 3.1: Sync Resources
                resource_mapping = resource_sync.bulk_sync_all(parsed_data["resources"])
                response.summary.resources_synced = len(resource_mapping)
                
                # Step 3.2: Sync Hierarchy (Programs > Projects > Phases)
                program_mapping, project_mapping, phase_mapping = (
                    hierarchy_sync.sync_hierarchy_from_work_items(parsed_data["work_items"])
                )
                response.summary.programs_synced = len(program_mapping)
                response.summary.projects_synced = len(set(project_mapping.values()))
                response.summary.phases_synced = len(set(phase_mapping.values()))
                
                # Get the first program ID for subsequent operations
                program_id = next(iter(program_mapping.values())) if program_mapping else None
                
                # Store program_id for response
                self_program_id = program_id
                
                if not program_id:
                    raise ImportError(
                        message="No program found in import data",
                        file_name=file.filename or "unknown"
                    )
                
                # Step 3.3: Create Import Batch for audit trail
                import_batch = db.create_import_batch(
                    program_id=str(program_id),
                    file_name=file.filename or "unknown",
                    file_hash=file_hash,
                    imported_by="system:excel_import"
                )
                if import_batch:
                    response.import_batch_id = import_batch.get("id")
                    # Set the batch_id in transaction context for audit logging
                    db.set_current_batch_id(import_batch.get("id"))
                
                # Step 3.4: Save Baseline Version (before changes)
                if save_baseline_version:
                    baseline_version = db.create_baseline_version(
                        program_id=str(program_id),
                        reason="Pre-import baseline snapshot",
                        created_by="system:excel_import",
                        import_batch_id=response.import_batch_id  # Link to import batch
                    )
                    if baseline_version:
                        response.baseline_version_id = baseline_version.get("id")
                
                # Step 3.4: Smart Merge Work Items
                merge_result = smart_merge.merge_all(
                    parsed_items=parsed_data["work_items"],
                    phase_mapping=phase_mapping,
                    resource_mapping=resource_mapping,
                    program_id=program_id,
                    perform_ghost_check=perform_ghost_check,
                )
                
                response.summary.tasks_created = merge_result.tasks_created
                response.summary.tasks_updated = merge_result.tasks_updated
                response.summary.tasks_preserved = merge_result.tasks_preserved
                response.summary.tasks_cancelled = merge_result.tasks_cancelled
                response.summary.tasks_flagged = merge_result.tasks_flagged
                
                # Collect flagged items for response
                for result in merge_result.results:
                    if result.action == "flagged":
                        response.flagged_items.append({
                            "external_id": result.external_id,
                            "message": result.flag_message,
                            "work_item_id": str(result.work_item_id) if result.work_item_id else None
                        })
                
                # Add merge warnings
                for warning in merge_result.warnings:
                    response.warnings.append({
                        "type": "merge",
                        "message": warning
                    })
                
                # Step 3.5: Sync Dependencies
                if parsed_data["dependencies"]:
                    work_item_mapping = dependency_sync.build_work_item_mapping(
                        parsed_data["work_items"],
                        phase_mapping
                    )
                    
                    dep_count, dep_warnings = dependency_sync.sync_all(
                        parsed_data["dependencies"],
                        work_item_mapping
                    )
                    response.summary.dependencies_synced = dep_count
                    
                    for warning in dep_warnings:
                        response.warnings.append({
                            "type": "dependency",
                            "message": warning
                        })
                
                # Step 3.6: Trigger Recalculation
                if trigger_recalculation and program_id:
                    recalc_engine = RecalculationEngine()
                    recalc_result = recalc_engine.recalculate_program(program_id)
                    
                    response.summary.recalculation_time_ms = recalc_result.execution_time_ms
                    response.summary.critical_path_items = len(recalc_result.critical_path_items)
                    
                    # Add recalculation warnings/errors
                    for warning in recalc_result.warnings:
                        response.warnings.append({
                            "type": "recalculation",
                            "message": warning
                        })
                    
                    for error in recalc_result.errors:
                        response.errors.append({
                            "type": "recalculation",
                            "message": error
                        })
                
                # Step 3.7: Handle Baseline > Current Conflicts
                if trigger_recalculation and program_id:
                    conflict_result = recalc_engine.handle_baseline_conflict(
                        program_id=program_id,
                        apply_changes=True
                    )
                    
                    if conflict_result["conflicts_found"] > 0:
                        response.warnings.append({
                            "type": "conflict",
                            "message": f"Resolved {conflict_result['conflicts_found']} baseline/current date conflicts"
                        })
                
                # Success - transaction will commit
                response.status = "success"
                
                # Check for partial success (only if there are merge/sync errors, not just validation warnings)
                # Validation warnings (like resource over-allocation) are informational and don't affect success status
                critical_warnings = [
                    w for w in response.warnings 
                    if w.get('type') in ('merge', 'conflict', 'recalculation')
                ]
                if critical_warnings and not response.errors:
                    response.status = "partial_success"
                
                # Update import batch with final results
                if response.import_batch_id:
                    db.update_import_batch(
                        batch_id=response.import_batch_id,
                        update_data={
                            "status": response.status,
                            "tasks_created": response.summary.tasks_created,
                            "tasks_updated": response.summary.tasks_updated,
                            "tasks_preserved": response.summary.tasks_preserved,
                            "tasks_cancelled": response.summary.tasks_cancelled,
                            "tasks_flagged": response.summary.tasks_flagged,
                            "warnings": response.warnings,
                            "errors": response.errors,
                            "baseline_version_id": response.baseline_version_id
                        }
                    )
                
            except Exception as e:
                # Mark transaction for rollback
                tx.should_rollback = True
                raise
        
    except FileFormatError as e:
        response.status = "failed"
        response.errors.append({
            "type": "file_format",
            "message": str(e)
        })
    except ImportError as e:
        response.status = "failed"
        response.errors.append({
            "type": "import_error",
            "message": str(e)
        })
    except ValidationError as e:
        response.status = "failed"
        response.errors.append({
            "type": "validation",
            "message": str(e)
        })
    except DatabaseError as e:
        response.status = "failed"
        response.errors.append({
            "type": "database",
            "message": str(e),
            "table": e.table if hasattr(e, 'table') else None,
            "operation": e.operation if hasattr(e, 'operation') else None
        })
    except TrackyException as e:
        response.status = "failed"
        response.errors.append({
            "type": "application",
            "message": str(e)
        })
    except Exception as e:
        response.status = "failed"
        response.errors.append({
            "type": "internal",
            "message": f"Unexpected error: {str(e)}"
        })
    
    # Calculate execution time
    response.execution_time_ms = int((time.time() - start_time) * 1000)
    
    return response


@router.post(
    "/validate",
    summary="Validate Excel File",
    description="""
    Validate an Excel file without importing data.
    
    Performs comprehensive validation including:
    - Required fields and data types
    - Date logic (end >= start)
    - Circular dependency detection
    - Resource over-allocation checks
    - Duplicate external ID detection
    
    Use this for pre-flight checks before actual import.
    """
)
async def validate_excel(
    file: UploadFile = File(..., description="Excel file to validate")
) -> dict:
    """
    Validate an Excel file structure and data without importing.
    """
    # Validate file extension
    filename = file.filename or ""
    if not filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Only .xlsx and .xls files are accepted."
        )
    
    contents = await file.read()
    file_obj = io.BytesIO(contents)
    
    try:
        parser = ExcelParser(file_obj, file.filename or "upload.xlsx")
        parsed_data = parser.parse()
        
        # Comprehensive validation
        validator = ImportValidator()
        result = validator.validate_all(
            parsed_work_items=parsed_data["work_items"],
            parsed_resources=parsed_data["resources"],
            parsed_dependencies=parsed_data["dependencies"],
            program_id=""
        )
        
        return {
            "valid": result.is_valid,
            "summary": {
                "work_items": len(parsed_data["work_items"]),
                "resources": len(parsed_data["resources"]),
                "dependencies": len(parsed_data["dependencies"]),
                "programs": len(parsed_data.get("programs", [])),
            },
            "validation": result.to_dict()
        }
    
    except TrackyException as e:
        return {
            "valid": False,
            "summary": {},
            "validation": {
                "is_valid": False,
                "errors": [{"message": str(e)}],
                "warnings": []
            }
        }
    except Exception as e:
        return {
            "valid": False,
            "summary": {},
            "validation": {
                "is_valid": False,
                "errors": [{"message": f"Parse error: {str(e)}"}],
                "warnings": []
            }
        }


@router.get(
    "/batches",
    summary="List Import Batches",
    description="Get a list of recent import operations for audit purposes"
)
async def list_import_batches(
    program_id: Optional[str] = Query(None, description="Filter by program ID"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results")
) -> dict:
    """
    List recent import batches for audit trail.
    """
    db = get_supabase_client()
    
    query = db.client.table("import_batches").select("*").order("started_at", desc=True).limit(limit)
    
    if program_id:
        query = query.eq("program_id", program_id)
    
    response = query.execute()
    
    return {
        "batches": response.data or [],
        "count": len(response.data) if response.data else 0
    }


@router.get(
    "/batches/{batch_id}",
    summary="Get Import Batch Details",
    description="Get detailed information about a specific import operation"
)
async def get_import_batch(batch_id: str) -> dict:
    """
    Get details of a specific import batch including audit logs.
    """
    db = get_supabase_client()
    
    # Get batch info
    batch_response = db.client.table("import_batches").select("*").eq("id", batch_id).execute()
    
    if not batch_response.data:
        raise HTTPException(status_code=404, detail="Import batch not found")
    
    batch = batch_response.data[0]
    
    # Get associated audit logs
    audit_response = (
        db.client.table("audit_logs")
        .select("*")
        .eq("import_batch_id", batch_id)
        .order("changed_at", desc=True)
        .limit(100)
        .execute()
    )
    
    return {
        "batch": batch,
        "audit_logs": audit_response.data or [],
        "audit_count": len(audit_response.data) if audit_response.data else 0
    }


@router.get(
    "/flagged",
    summary="Get Flagged Items",
    description="Get work items flagged for PM review (removed from Excel but in progress)"
)
async def get_flagged_items(
    program_id: str = Query(..., description="Program ID to check")
) -> dict:
    """
    Get work items flagged for review.
    
    These are tasks that were removed from the Excel file but were
    in progress, so they require manual PM decision.
    """
    db = get_supabase_client()
    
    flagged_items = db.get_flagged_work_items(program_id)
    
    return {
        "flagged_count": len(flagged_items),
        "items": [
            {
                "id": item["id"],
                "external_id": item["external_id"],
                "name": item.get("name"),
                "status": item.get("status"),
                "completion_percent": item.get("completion_percent"),
                "review_message": item.get("review_message"),
            }
            for item in flagged_items
        ]
    }


@router.post(
    "/flagged/{work_item_id}/resolve",
    summary="Resolve Flagged Item",
    description="Resolve a flagged work item with PM decision"
)
async def resolve_flagged_item(
    work_item_id: str,
    new_status: str = Query(..., description="New status: 'Cancelled', 'In Progress', etc."),
    resolution_note: str = Query("", description="Note explaining the resolution")
) -> dict:
    """
    Resolve a flagged work item after PM review.
    """
    db = get_supabase_client()
    
    # Validate status
    valid_statuses = {"Cancelled", "In Progress", "On Hold", "Not Started"}
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )
    
    result = db.resolve_flagged_item(
        work_item_id=work_item_id,
        new_status=new_status,
        resolution_note=resolution_note or f"Resolved by PM: status set to {new_status}"
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Work item not found")
    
    # Log the resolution
    db.log_audit(
        entity_type="work_item",
        entity_id=work_item_id,
        action="resolved",
        field_changed="flag_for_review",
        old_value="true",
        new_value="false",
        change_source="manual",
        changed_by="pm:manual_resolution",
        reason=resolution_note
    )
    
    return {
        "status": "resolved",
        "work_item": result
    }


@router.get(
    "/baseline-versions",
    summary="List Baseline Versions",
    description="Get baseline version history for a program (scope tracking)"
)
async def list_baseline_versions(
    program_id: str = Query(..., description="Program ID")
) -> dict:
    """
    Get all baseline versions for a program.
    
    Useful for tracking scope changes over time:
    - Original estimate vs current
    - Progressive elaboration history
    - Change request impact
    """
    db = get_supabase_client()
    
    versions = db.get_baseline_versions(program_id)
    
    return {
        "program_id": program_id,
        "version_count": len(versions),
        "versions": versions
    }


@router.get(
    "/resource-utilization",
    summary="Get Resource Utilization",
    description="Check resource allocation across all active tasks"
)
async def get_resource_utilization() -> dict:
    """
    Get current resource utilization.
    
    Shows:
    - Total allocation per resource
    - Over-allocated resources (> 100%)
    - At-risk resources (> 80%)
    """
    db = get_supabase_client()
    
    utilization = db.get_all_resource_utilization()
    
    over_allocated = [r for r in utilization if r.get("utilization_status") == "Over-Allocated"]
    at_risk = [r for r in utilization if r.get("utilization_status") == "At-Risk"]
    
    return {
        "total_resources": len(utilization),
        "over_allocated_count": len(over_allocated),
        "at_risk_count": len(at_risk),
        "over_allocated": over_allocated,
        "at_risk": at_risk,
        "all_resources": utilization
    }
