"""
FastAPI Main Application Entry Point for Tracky PM.

This is the Ingestion Engine backend service that handles:
- Excel file parsing and validation
- Smart Merge algorithm for data synchronization
- Database operations via Supabase
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import TrackyException
from app.api.routes import import_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    
    Startup:
    - Initialize database connections
    - Validate configuration
    
    Shutdown:
    - Clean up resources
    """
    # Startup
    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Debug mode: {settings.debug}")
    
    yield
    
    # Shutdown
    print("Shutting down...")


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


# Health check endpoint
@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns service status and configuration.
    """
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "debug": settings.debug,
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
