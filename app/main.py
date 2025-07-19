"""
Main FastAPI application
Aquaculture Management System for Algeria
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import Depends, FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import and_
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.models.pond import Pond, User, UserRole
from app.models.sensor import SensorData
from sqlalchemy.orm import Session
from app.api.deps import get_current_active_user
import time


from app.config import settings
from app.database import engine, Base, get_db
from app.api.endpoints import auth, ponds, sensors, alerts, simulation, users, api_key
from app.tasks.data_aggregation import (
    aggregate_hourly_data,
    aggregate_daily_data,
    cleanup_old_data,
    system_health_check
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global scheduler
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    Handles startup and shutdown events
    """
    # Startup
    logger.info("Starting Aquaculture Management System")
    
    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")
    
    # Start scheduler for background tasks
    scheduler.start()
    logger.info("Background task scheduler started")
    
    # Schedule background tasks
    _schedule_background_tasks()
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")
    scheduler.shutdown()
    logger.info("Background task scheduler stopped")


def _schedule_background_tasks():
    """
    Schedule all background tasks
    """
    # Hourly data aggregation (every hour at minute 5)
    scheduler.add_job(
        aggregate_hourly_data,
        CronTrigger(minute=5),
        id="hourly_aggregation",
        name="Hourly Data Aggregation",
        replace_existing=True
    )
    
    # Daily data aggregation (every day at 00:10)
    scheduler.add_job(
        aggregate_daily_data,
        CronTrigger(hour=0, minute=10),
        id="daily_aggregation",
        name="Daily Data Aggregation",
        replace_existing=True
    )
    
    # Weekly data cleanup (every Sunday at 02:00)
    scheduler.add_job(
        cleanup_old_data,
        CronTrigger(day_of_week=6, hour=2, minute=0),
        id="data_cleanup",
        name="Data Cleanup",
        replace_existing=True
    )
    
    # System health check (every 15 minutes)
    scheduler.add_job(
        system_health_check,
        CronTrigger(minute="*/15"),
        id="health_check",
        name="System Health Check",
        replace_existing=True
    )
    
    logger.info("Background tasks scheduled")


# Create FastAPI application
app = FastAPI(
    title="Aquaculture Management System",
    description="""
    Comprehensive aquaculture pond management system for Algeria
    
    Features:
    - Real-time water quality monitoring
    - Intelligent health assessment
    - Multi-language support (French/Arabic)
    - Advanced alerting system
    - IoT sensor integration
    - Data analytics and reporting
    """,
    version="1.0.0",
    contact={
        "name": "Aquaculture System Support",
        "email": "support@aquaculture-algeria.com"
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    lifespan=lifespan
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Custom middleware for request logging and monitoring
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Log all requests for monitoring
    """
    start_time = time.time()
    
    # Process request
    response = await call_next(request)
    
    # Log request details
    process_time = time.time() - start_time
    logger.info(
        f"{request.method} {request.url} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.3f}s"
    )
    
    # Add custom headers
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-API-Version"] = "1.0.0"
    
    return response


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Custom HTTP exception handler
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.utcnow().isoformat(),
            "path": str(request.url)
        }
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """
    Handle validation errors
    """
    return JSONResponse(
        status_code=400,
        content={
            "error": True,
            "message": f"Validation error: {str(exc)}",
            "status_code": 400,
            "timestamp": datetime.utcnow().isoformat(),
            "path": str(request.url)
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Handle unexpected errors
    """
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": "Internal server error. Please try again later.",
            "status_code": 500,
            "timestamp": datetime.utcnow().isoformat(),
            "path": str(request.url)
        }
    )


# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(ponds.router, prefix="/api/v1")
app.include_router(sensors.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(api_key.router, prefix="/api-keys", tags=["api-keys"])
app.include_router(simulation.router, prefix="/simulation", tags=["simulation"])




# Health check endpoints
@app.get("/health")
async def health_check():
    """
    Simple health check endpoint
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT
    }


@app.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check with system information"""
    from app.database import get_db
    from sqlalchemy import text
    
    try:
        # Test database connection with proper SQLAlchemy syntax
        db = next(get_db())
        result = db.execute(text("SELECT 1"))  # Use text() wrapper
        result.fetchone()  # Actually fetch the result
        db.close()
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "components": {
            "database": db_status,
            "scheduler": "running" if scheduler.running else "stopped",
            "scheduled_jobs": len(scheduler.get_jobs())
        }
    }


# Root endpoint
@app.get("/")
async def root():
    """
    API root endpoint
    """
    return {
        "message": "Aquaculture Management System API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "health_check": "/health",
        "environment": settings.ENVIRONMENT
    }


# Dashboard summary endpoint
@app.get("/api/v1/dashboard")
async def get_dashboard_summary(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get dashboard summary data
    """
    # Get user's ponds
    user_ponds = db.query(Pond).filter(Pond.assigned_users.any(id=current_user.id)).all()


    # Calculate summary statistics
    total_ponds = len(user_ponds)
    active_ponds = len([p for p in user_ponds if p.is_active])
    
    # Get active alerts
    from app.models.alert import Alert, AlertStatus, AlertSeverity
    if current_user.role != UserRole.ADMIN:
        # Non-admin users can only see their own ponds' alerts
        active_alerts = db.query(Alert).join(Pond).filter(
            and_(
                Pond.assigned_users.any(id=current_user.id),
                Alert.status == AlertStatus.ACTIVE
            )
        ).count()
    else:
        # Admins can see all active alerts
        active_alerts = db.query(Alert).filter(Alert.status == AlertStatus.ACTIVE).count()
    
    if current_user.role == UserRole.ADMIN:
        # Admins can see all ponds' critical alerts
        critical_alerts = db.query(Alert).filter(
            and_(
                Alert.status == AlertStatus.ACTIVE,
                Alert.severity == AlertSeverity.CRITICAL
            )
        ).count()
    else:
        # Non-admin users only see critical alerts for their ponds

        critical_alerts = db.query(Alert).join(Pond).filter(
            and_(
                Pond.assigned_users.any(id=current_user.id),
                Alert.status == AlertStatus.ACTIVE,
                Alert.severity == AlertSeverity.CRITICAL
            )
        ).count()
    
    # Get recent readings count
    recent_threshold = datetime.utcnow() - timedelta(hours=24)
    if current_user.role != UserRole.ADMIN:        
        recent_readings = db.query(SensorData).join(Pond).filter(
            and_(
                Pond.assigned_users.any(id=current_user.id),
                SensorData.timestamp >= recent_threshold
            )
        ).count()
    
    # Get health distribution (simplified)
    health_distribution = {
        "excellent": 0,
        "good": 0,
        "fair": 0,
        "poor": 0
    }
    
    # This would be calculated from actual health assessments
    # For now, just placeholder values
    for pond in user_ponds:
        # This would call the health calculator
        health_distribution["good"] += 1
    
    return {
        "total_ponds": total_ponds,
        "active_ponds": active_ponds,
        "total_alerts": active_alerts,
        "critical_alerts": critical_alerts,
        "warning_alerts": active_alerts - critical_alerts,
        "recent_readings_count": recent_readings,
        "health_distribution": health_distribution,
        "last_updated": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import time
    
    # Run the application
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )