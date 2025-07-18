"""
Alert management API endpoints
Handles alert rules, active alerts, and alert acknowledgment
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func, or_
from datetime import datetime, timedelta

from app.database import get_db
from app.models.alert import Alert, AlertRule, AlertStatus, AlertSeverity
from app.models.pond import Pond, User
from app.schemas import alert as alert_schemas
from app.api.deps import get_current_active_user, check_pond_ownership, get_pagination_params
from app.services.notification import NotificationService

router = APIRouter(prefix="/alerts", tags=["alerts"])


# Alert Rules Management
@router.get("/rules", response_model=List[alert_schemas.AlertRuleResponse])
async def get_alert_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    pond_id: Optional[int] = Query(None),
    active_only: bool = Query(True)
):
    """
    Get alert rules for user's ponds
    """
    query = db.query(AlertRule).join(Pond).filter(Pond.owner_id == current_user.id)
    
    if pond_id:
        check_pond_ownership(pond_id, current_user, db)
        query = query.filter(AlertRule.pond_id == pond_id)
    
    if active_only:
        query = query.filter(AlertRule.is_active == True)
    
    rules = query.all()
    return rules


@router.post("/rules", response_model=alert_schemas.AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    rule_data: alert_schemas.AlertRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new alert rule
    """
    check_pond_ownership(rule_data.pond_id, current_user, db)
    
    # Create alert rule
    alert_rule = AlertRule(
        **rule_data.dict(),
        created_by=current_user.id
    )
    
    db.add(alert_rule)
    db.commit()
    db.refresh(alert_rule)
    
    return alert_rule


@router.put("/rules/{rule_id}", response_model=alert_schemas.AlertRuleResponse)
async def update_alert_rule(
    rule_id: int,
    rule_update: alert_schemas.AlertRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Update an alert rule
    """
    # Get rule and check ownership
    rule = db.query(AlertRule).join(Pond).filter(
        and_(
            AlertRule.id == rule_id,
            Pond.owner_id == current_user.id
        )
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule not found"
        )
    
    # Update fields
    update_data = rule_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)
    
    db.commit()
    db.refresh(rule)
    
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Delete an alert rule
    """
    # Get rule and check ownership
    rule = db.query(AlertRule).join(Pond).filter(
        and_(
            AlertRule.id == rule_id,
            Pond.owner_id == current_user.id
        )
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule not found"
        )
    
    # Soft delete - just deactivate
    rule.is_active = False
    db.commit()


# Active Alerts Management
@router.get("/", response_model=List[alert_schemas.AlertResponse])
async def get_alerts(
    query_params: alert_schemas.AlertQuery = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get alerts with filtering options
    """
    # Base query - only user's ponds
    query = db.query(Alert).join(Pond).filter(Pond.owner_id == current_user.id)
    
    # Apply filters
    if query_params.pond_id:
        check_pond_ownership(query_params.pond_id, current_user, db)
        query = query.filter(Alert.pond_id == query_params.pond_id)
    
    if query_params.severity:
        query = query.filter(Alert.severity == query_params.severity)
    
    if query_params.status:
        query = query.filter(Alert.status == query_params.status)
    
    if query_params.parameter:
        query = query.filter(Alert.parameter == query_params.parameter)
    
    if query_params.start_date:
        query = query.filter(Alert.triggered_at >= query_params.start_date)
    
    if query_params.end_date:
        query = query.filter(Alert.triggered_at <= query_params.end_date)
    
    # Ordering
    if query_params.order_direction == "desc":
        query = query.order_by(desc(getattr(Alert, query_params.order_by)))
    else:
        query = query.order_by(getattr(Alert, query_params.order_by))
    
    # Pagination
    alerts = query.offset(query_params.offset).limit(query_params.limit).all()
    
    # Enhance with pond names
    alert_responses = []
    for alert in alerts:
        pond = db.query(Pond).filter(Pond.id == alert.pond_id).first()
        alert_response = alert_schemas.AlertResponse(
            **alert.__dict__,
            pond_name=pond.name if pond else "Unknown"
        )
        alert_responses.append(alert_response)
    
    return alert_responses


@router.get("/active", response_model=List[alert_schemas.AlertResponse])
async def get_active_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    severity: Optional[alert_schemas.AlertSeverity] = Query(None)
):
    """
    Get all active alerts for user's ponds
    """
    query = db.query(Alert).join(Pond).filter(
        and_(
            Pond.owner_id == current_user.id,
            Alert.status == AlertStatus.ACTIVE
        )
    )
    
    if severity:
        query = query.filter(Alert.severity == severity)
    
    alerts = query.order_by(desc(Alert.triggered_at)).all()
    
    # Enhance with pond names
    alert_responses = []
    for alert in alerts:
        pond = db.query(Pond).filter(Pond.id == alert.pond_id).first()
        alert_response = alert_schemas.AlertResponse(
            **alert.__dict__,
            pond_name=pond.name if pond else "Unknown"
        )
        alert_responses.append(alert_response)
    
    return alert_responses


@router.post("/acknowledge", status_code=status.HTTP_200_OK)
async def acknowledge_alerts(
    acknowledge_data: alert_schemas.AlertAcknowledge,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Acknowledge multiple alerts
    """
    # Get alerts and verify ownership
    alerts = db.query(Alert).join(Pond).filter(
        and_(
            Alert.id.in_(acknowledge_data.alert_ids),
            Pond.owner_id == current_user.id,
            Alert.status == AlertStatus.ACTIVE
        )
    ).all()
    
    if len(alerts) != len(acknowledge_data.alert_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Some alerts not found or not accessible"
        )
    
    # Acknowledge alerts
    acknowledged_count = 0
    for alert in alerts:
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = current_user.id
        acknowledged_count += 1
    
    db.commit()
    
    # Send notification about acknowledgment
    background_tasks.add_task(
        send_acknowledgment_notification,
        current_user.id,
        acknowledged_count,
        acknowledge_data.note
    )
    
    return {"message": f"Acknowledged {acknowledged_count} alerts"}


@router.post("/resolve", status_code=status.HTTP_200_OK)
async def resolve_alerts(
    resolve_data: alert_schemas.AlertResolve,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Resolve multiple alerts
    """
    # Get alerts and verify ownership
    alerts = db.query(Alert).join(Pond).filter(
        and_(
            Alert.id.in_(resolve_data.alert_ids),
            Pond.owner_id == current_user.id,
            Alert.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED])
        )
    ).all()
    
    if len(alerts) != len(resolve_data.alert_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Some alerts not found or not accessible"
        )
    
    # Resolve alerts
    resolved_count = 0
    for alert in alerts:
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by = current_user.id
        resolved_count += 1
    
    db.commit()
    
    return {"message": f"Resolved {resolved_count} alerts"}


@router.get("/statistics")
async def get_alert_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    days: int = Query(30, ge=1, le=365)
):
    """
    Get alert statistics for dashboard
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get user's pond IDs
    user_pond_ids = db.query(Pond.id).filter(Pond.owner_id == current_user.id).subquery()
    
    # Total alerts in period
    total_alerts = db.query(Alert).filter(
        and_(
            Alert.pond_id.in_(user_pond_ids),
            Alert.triggered_at >= start_date
        )
    ).count()
    
    # Active alerts
    active_alerts = db.query(Alert).filter(
        and_(
            Alert.pond_id.in_(user_pond_ids),
            Alert.status == AlertStatus.ACTIVE
        )
    ).count()
    
    # Critical alerts
    critical_alerts = db.query(Alert).filter(
        and_(
            Alert.pond_id.in_(user_pond_ids),
            Alert.severity == AlertSeverity.CRITICAL,
            Alert.triggered_at >= start_date
        )
    ).count()
    
    # Alerts by severity
    severity_counts = {}
    for severity in AlertSeverity:
        count = db.query(Alert).filter(
            and_(
                Alert.pond_id.in_(user_pond_ids),
                Alert.severity == severity,
                Alert.triggered_at >= start_date
            )
        ).count()
        severity_counts[severity.value] = count
    
    # Alerts by parameter
    parameter_counts = db.query(
        Alert.parameter,
        func.count(Alert.id).label('count')
    ).filter(
        and_(
            Alert.pond_id.in_(user_pond_ids),
            Alert.triggered_at >= start_date
        )
    ).group_by(Alert.parameter).all()
    
    # Recent alert trend (last 7 days)
    recent_trend = []
    for i in range(7):
        day_start = datetime.utcnow() - timedelta(days=i+1)
        day_end = datetime.utcnow() - timedelta(days=i)
        
        day_count = db.query(Alert).filter(
            and_(
                Alert.pond_id.in_(user_pond_ids),
                Alert.triggered_at >= day_start,
                Alert.triggered_at < day_end
            )
        ).count()
        
        recent_trend.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "count": day_count
        })
    
    return {
        "total_alerts": total_alerts,
        "active_alerts": active_alerts,
        "critical_alerts": critical_alerts,
        "severity_breakdown": severity_counts,
        "parameter_breakdown": dict(parameter_counts),
        "recent_trend": list(reversed(recent_trend))
    }


async def send_acknowledgment_notification(user_id: int, count: int, note: Optional[str]):
    """
    Send notification about alert acknowledgment
    Background task function
    """
    # Implementation would send email/push notification
    # This is a placeholder for the notification service
    pass