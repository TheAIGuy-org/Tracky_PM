"""
FastAPI Main Application Entry Point for Tracky PM.

This is the Ingestion Engine backend service that handles:
- Excel file parsing and validation
- Smart Merge algorithm for data synchronization
- Database operations via Supabase
- Proactive Execution Tracking Loop (alerts, escalations)
- Background job scheduling
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import TrackyException
from app.api.routes import (
    import_router, 
    data_router, 
    alert_router,
    holiday_router,
    resource_router
)


# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    
    Startup:
    - Initialize database connections
    - Validate configuration
    - Start background scheduler
    
    Shutdown:
    - Stop scheduler gracefully
    - Clean up resources
    """
    # Startup
    logger.info(f"🚀 Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Email enabled: {settings.email_enabled}")
    logger.info(f"Scheduler enabled: {settings.enable_scheduler}")
    logger.info(f"Run scheduler (this instance): {settings.run_scheduler}")
    
    # Initialize scheduler reference in app state
    app.state.scheduler = None
    
    # CRITICAL FIX (A): Only start scheduler if BOTH enabled AND run_scheduler is true
    # This prevents duplicate emails when running multiple workers (gunicorn -w 4)
    # Set RUN_SCHEDULER=true on only ONE worker/container in production
    should_run_scheduler = settings.enable_scheduler and settings.run_scheduler
    
    if should_run_scheduler:
        try:
            from app.services.scheduler import get_scheduler
            app.state.scheduler = get_scheduler()
            app.state.scheduler.start()
            logger.info("✅ Background scheduler started")
        except ImportError as e:
            logger.warning(f"⚠️ Scheduler not available (missing APScheduler?): {e}")
        except Exception as e:
            logger.error(f"❌ Failed to start scheduler: {e}")
    
    yield
    
    # Shutdown
    if app.state.scheduler and app.state.scheduler.is_running:
        app.state.scheduler.stop()
        logger.info("✅ Scheduler stopped")
    
    logger.info("👋 Shutting down...")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    # Tracky PM - Ingestion Engine
    
    The backend service for the Tracky Project Management system.
    
    ## Core Philosophy
    **"The Excel File updates the Plan, but the System preserves the Truth."**
    
    ## Features
    
    ### Smart Merge Algorithm
    - **INSERT**: New tasks are created with baseline = current dates
    - **UPDATE**: Existing tasks update baseline only, preserve current/actual
    - **CANCEL**: Tasks missing from Excel are soft-deleted
    
    ### Multi-Pass Import
    1. **Resources**: Sync team members
    2. **Hierarchy**: Programs > Projects > Phases
    3. **Work Items**: Smart Merge logic
    4. **Dependencies**: Task relationships
    5. **Recalculation**: Propagate date changes
    
    ## API Response Structure
    ```json
    {
      "status": "success",
      "summary": {
        "tasks_created": 5,
        "tasks_updated": 42,
        "tasks_preserved": 42,
        "tasks_cancelled": 1
      }
    }
    ```
    """,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)


# Configure CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler for TrackyExceptions
@app.exception_handler(TrackyException)
async def tracky_exception_handler(request, exc: TrackyException):
    """Handle all TrackyException subclasses."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


# Include API routers
app.include_router(import_router)
app.include_router(data_router)
app.include_router(alert_router)
app.include_router(holiday_router)
app.include_router(resource_router)


# Health check endpoint
@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns service status, scheduler health, and configuration.
    """
    scheduler = getattr(app.state, 'scheduler', None)
    
    scheduler_status = {
        "running": scheduler.is_running if scheduler else False,
        "jobs": [],
        "failed_jobs": {}
    }
    
    if scheduler and scheduler.is_running:
        scheduler_status["jobs"] = [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None
            }
            for job in scheduler.scheduler.get_jobs()
        ]
        scheduler_status["failed_jobs"] = {
            job_id: {
                "count": len(failures),
                "last_failure": str(failures[-1]["timestamp"]) if failures else None
            }
            for job_id, failures in scheduler.monitor.failed_jobs.items()
        }
    
    # Determine overall health
    failed_job_count = sum(
        len(failures) for failures in scheduler_status.get("failed_jobs", {}).values()
    )
    overall_status = "healthy" if failed_job_count < 5 else "degraded"
    
    return {
        "status": overall_status,
        "service": settings.app_name,
        "version": settings.app_version,
        "debug": settings.debug,
        "scheduler": scheduler_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Root endpoint
@app.get("/", tags=["System"])
async def root():
    """Root endpoint with API information."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs" if settings.debug else "Docs disabled in production",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
