"""
Pond management API endpoints
Handles CRUD operations for ponds and basic pond information
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.database import get_db
from app.models.pond import Pond, User
from app.schemas import pond as pond_schemas
from app.api.deps import get_current_active_user, check_pond_ownership, get_pagination_params
from app.core.health_calculator import calculate_pond_health
from app.services.data_processor import get_pond_latest_data, get_pond_statistics as pond_stats_service

router = APIRouter(prefix="/ponds", tags=["ponds"])


@router.get("/", response_model=List[pond_schemas.PondSummary])
async def get_ponds(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    active_only: bool = Query(True, description="Show only active ponds"),
    search: Optional[str] = Query(None, description="Search pond names")
):
    """Get list of user's ponds with summary information"""
    # Show ponds the user owns OR is assigned to
    query = db.query(Pond).filter(
        or_(
            Pond.owner_id == current_user.id,
            Pond.assigned_users.any(id=current_user.id)
        )
    )    
    # Apply filters
    if active_only:
        query = query.filter(Pond.is_active == True)
    
    if search:
        query = query.filter(Pond.name.ilike(f"%{search}%"))
    
    # Apply pagination - FIXED
    ponds = query.offset(skip).limit(limit).all()
    # Rest of the function remains the same...
    pond_summaries = []
    for pond in ponds:
        health_data = calculate_pond_health(pond.id, db)
        
        from app.models.alert import Alert, AlertStatus
        active_alerts = db.query(Alert).filter(
            and_(
                Alert.pond_id == pond.id,
                Alert.status == AlertStatus.ACTIVE
            )
        ).count()
        
        summary = pond_schemas.PondSummary(
            id=pond.id,
            name=pond.name,
            health_score=health_data.get("overall_score") if health_data else None,
            health_grade=health_data.get("grade") if health_data else None,
            status="Active" if pond.is_active else "Inactive",
            active_alerts_count=active_alerts,
            last_updated=pond.updated_at
        )
        pond_summaries.append(summary)
    
    return pond_summaries

@router.post("/", response_model=pond_schemas.PondResponse, status_code=status.HTTP_201_CREATED)
async def create_pond(
    pond_data: pond_schemas.PondCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new pond
    """
    # Create pond object
    pond = Pond(
        **pond_data.dict(),
        owner_id=current_user.id
    )
    
    db.add(pond)
    db.commit()
    db.refresh(pond)
    
    # Create default alert rules in background
    background_tasks.add_task(create_default_alert_rules, pond.id, db)
    
    return pond


@router.get("/{pond_id}", response_model=pond_schemas.PondWithStats)
async def get_pond(
    pond_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get detailed pond information with statistics"""
    
    # No await needed - fixed
    pond = check_pond_ownership(pond_id, current_user, db)
    
    # Get additional statistics
    latest_reading = await get_pond_latest_data(pond_id, db)
    health_data =  calculate_pond_health(pond_id, db)
    
    # Get active alerts count
    from app.models.alert import Alert, AlertStatus
    active_alerts = db.query(Alert).filter(
        and_(
            Alert.pond_id == pond_id,
            Alert.status == AlertStatus.ACTIVE
        )
    ).count()
    
    # Create response with statistics
    pond_with_stats = pond_schemas.PondWithStats(
        **pond.__dict__,
        latest_reading=latest_reading,
        health_score=health_data.get("overall_score") if health_data else None,
        health_grade=health_data.get("grade") if health_data else None,
        active_alerts_count=active_alerts,
        last_data_timestamp=latest_reading.get("timestamp") if latest_reading else None
    )
    
    return pond_with_stats


@router.put("/{pond_id}", response_model=pond_schemas.PondResponse)
async def update_pond(
    pond_id: int,
    pond_update: pond_schemas.PondUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update pond information"""
    
    # No await needed - fixed
    pond = check_pond_ownership(pond_id, current_user, db)
    
    # Update fields
    update_data = pond_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pond, field, value)
    
    db.commit()
    db.refresh(pond)
    
    return pond


@router.delete("/{pond_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pond(
    pond_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    permanent: bool = Query(False, description="Permanently delete (vs soft delete)")
):
    """Delete pond (soft delete by default)"""
    
    # No await needed - fixed
    pond = check_pond_ownership(pond_id, current_user, db)
    
    if permanent:
        db.delete(pond)
    else:
        pond.is_active = False
    
    db.commit()


@router.get("/{pond_id}/health", response_model=pond_schemas.HealthAssessment)
async def get_pond_health(
    pond_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    days: int = Query(7, ge=1, le=90, description="Days to analyze")
):
    """
    Get comprehensive pond health assessment
    """
    # Check ownership
    check_pond_ownership(pond_id, current_user, db)
    
    # Calculate health assessment
    health_data = calculate_pond_health(pond_id, db, days=days)
    
    if not health_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insufficient data for health assessment"
        )
    
    return health_data


@router.get("/{pond_id}/statistics")
async def get_pond_statistics(
    pond_id: int,
    days: int = Query(30, ge=1, le=365, description="Number of days for statistics"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive statistics for a specific pond"""
    
    try:
        # Check pond ownership - no await needed now
        pond = check_pond_ownership(pond_id, current_user, db)
        
        # Get statistics
        stats = await pond_stats_service(pond_id, db, days)
        
        return {
            "pond_id": pond_id,
            "pond_name": pond.name,
            "owner_id": pond.owner_id,
            "statistics": stats,
            "success": True
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 404, 403)
        raise
    except Exception as e:
        # Handle any other errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving pond statistics: {str(e)}"
        )


def create_default_alert_rules(pond_id: int, db: Session):
    """
    Create default alert rules for a new pond
    Background task function
    """
    from app.models.alert import AlertRule, AlertSeverity
    from app.config import settings
    
    default_rules = []
    
    # Create rules based on your threshold analysis
    for parameter, thresholds in settings.ALERT_THRESHOLDS.items():
        # Critical low threshold
        if "critical_low" in thresholds:
            rule = AlertRule(
                pond_id=pond_id,
                parameter=parameter,
                rule_name=f"{parameter} Critical Low",
                description=f"Alert when {parameter} falls below critical threshold",
                min_threshold=thresholds["critical_low"],
                severity=AlertSeverity.CRITICAL,
                send_sms=True,
                cooldown_minutes=15
            )
            default_rules.append(rule)
        
        # Critical high threshold
        if "critical_high" in thresholds:
            rule = AlertRule(
                pond_id=pond_id,
                parameter=parameter,
                rule_name=f"{parameter} Critical High",
                description=f"Alert when {parameter} exceeds critical threshold",
                max_threshold=thresholds["critical_high"],
                severity=AlertSeverity.CRITICAL,
                send_sms=True,
                cooldown_minutes=15
            )
            default_rules.append(rule)
        
        # Warning thresholds
        if "warning_low" in thresholds:
            rule = AlertRule(
                pond_id=pond_id,
                parameter=parameter,
                rule_name=f"{parameter} Warning Low",
                description=f"Alert when {parameter} falls below warning threshold",
                min_threshold=thresholds["warning_low"],
                severity=AlertSeverity.WARNING,
                send_sms=False,
                cooldown_minutes=60
            )
            default_rules.append(rule)
        
        if "warning_high" in thresholds:
            rule = AlertRule(
                pond_id=pond_id,
                parameter=parameter,
                rule_name=f"{parameter} Warning High",
                description=f"Alert when {parameter} exceeds warning threshold",
                max_threshold=thresholds["warning_high"],
                severity=AlertSeverity.WARNING,
                send_sms=False,
                cooldown_minutes=60
            )
            default_rules.append(rule)
    
    # Add rules to database
    for rule in default_rules:
        db.add(rule)
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error creating default alert rules: {e}")