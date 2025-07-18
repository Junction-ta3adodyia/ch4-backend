"""
Alert Processing Engine
Processes sensor data and triggers alerts based on configured rules
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.database import SessionLocal
from app.models.alert import Alert, AlertRule, AlertSeverity, AlertStatus
from app.models.sensor import SensorData
from app.models.pond import Pond, User
from app.config import settings
from app.services.notification import NotificationService


async def process_sensor_data_for_alerts(
    sensor_reading_id: int,
    pond_id: int,
    sensor_data: Dict[str, Any]
) -> List[Alert]:
    """
    Process new sensor data and check for alert conditions
    This is called as a background task for each new sensor reading
    """
    db = SessionLocal()
    triggered_alerts = []
    
    try:
        # Get active alert rules for this pond
        alert_rules = db.query(AlertRule).filter(
            and_(
                AlertRule.pond_id == pond_id,
                AlertRule.is_active == True
            )
        ).all()
        
        for rule in alert_rules:
            # Check if this rule should trigger
            should_trigger = await _evaluate_alert_rule(rule, sensor_data, db)
            
            if should_trigger:
                # Check rate limiting
                if _is_rate_limited(rule, db):
                    continue
                
                # Create alert
                alert = await _create_alert(rule, sensor_reading_id, sensor_data, db)
                if alert:
                    triggered_alerts.append(alert)
                    
                    # Send notification asynchronously
                    asyncio.create_task(_send_alert_notification(alert, rule, db))
        
        return triggered_alerts
        
    except Exception as e:
        print(f"Error processing alerts: {e}")
        db.rollback()
        return []
    finally:
        db.close()


async def _evaluate_alert_rule(
    rule: AlertRule,
    sensor_data: Dict[str, Any],
    db: Session
) -> bool:
    """
    Evaluate if an alert rule should trigger based on sensor data
    """
    parameter_value = sensor_data.get(rule.parameter)
    
    if parameter_value is None:
        return False
    
    # Check threshold conditions
    threshold_violated = False
    
    if rule.min_threshold is not None and parameter_value < rule.min_threshold:
        threshold_violated = True
    
    if rule.max_threshold is not None and parameter_value > rule.max_threshold:
        threshold_violated = True
    
    # Check advanced conditions (if any)
    if rule.conditions and not _evaluate_advanced_conditions(rule.conditions, sensor_data, db):
        return False
    
    return threshold_violated


def _evaluate_advanced_conditions(
    conditions: Dict[str, Any],
    sensor_data: Dict[str, Any],
    db: Session
) -> bool:
    """
    Evaluate advanced alert conditions (JSON-based rules)
    Examples: consecutive readings, rate of change, multiple parameter conditions
    """
    # Example advanced conditions:
    # {"consecutive_violations": 3, "time_window_minutes": 30}
    # {"rate_of_change": {"threshold": 5, "time_minutes": 15}}
    # {"multiple_parameters": {"ph": {"min": 6.5}, "temperature": {"max": 30}}}
    
    consecutive_violations = conditions.get('consecutive_violations')
    if consecutive_violations:
        # Check if we've had consecutive violations
        # This would require querying recent sensor data
        pass
    
    rate_of_change = conditions.get('rate_of_change')
    if rate_of_change:
        # Check if parameter is changing too rapidly
        pass
    
    multiple_parameters = conditions.get('multiple_parameters')
    if multiple_parameters:
        # Check multiple parameter conditions
        for param, condition in multiple_parameters.items():
            param_value = sensor_data.get(param)
            if param_value is None:
                return False
            
            if 'min' in condition and param_value < condition['min']:
                return False
            if 'max' in condition and param_value > condition['max']:
                return False
    
    return True


def _is_rate_limited(rule: AlertRule, db: Session) -> bool:
    """
    Check if alert rule is rate limited (too many recent alerts)
    """
    now = datetime.utcnow()
    
    # Check cooldown period
    cooldown_start = now - timedelta(minutes=rule.cooldown_minutes)
    recent_alert = db.query(Alert).filter(
        and_(
            Alert.rule_id == rule.id,
            Alert.triggered_at >= cooldown_start
        )
    ).first()
    
    if recent_alert:
        return True
    
    # Check hourly limit
    hour_start = now - timedelta(hours=1)
    alerts_this_hour = db.query(Alert).filter(
        and_(
            Alert.rule_id == rule.id,
            Alert.triggered_at >= hour_start
        )
    ).count()
    
    if alerts_this_hour >= rule.max_alerts_per_hour:
        return True
    
    return False


async def _create_alert(
    rule: AlertRule,
    sensor_reading_id: int,
    sensor_data: Dict[str, Any],
    db: Session
) -> Optional[Alert]:
    """
    Create a new alert record
    """
    try:
        parameter_value = sensor_data.get(rule.parameter)
        threshold_value = rule.min_threshold if parameter_value < (rule.min_threshold or float('inf')) else rule.max_threshold
        
        # Generate multilingual messages
        messages = _generate_alert_messages(rule, parameter_value, threshold_value)
        
        alert = Alert(
            pond_id=rule.pond_id,
            rule_id=rule.id,
            parameter=rule.parameter,
            current_value=parameter_value,
            threshold_value=threshold_value,
            severity=rule.severity,
            title=messages['title'],
            message=messages['message'],
            message_fr=messages.get('message_fr'),
            message_ar=messages.get('message_ar'),
            sensor_reading_id=sensor_reading_id,
            context_data={
                'sensor_data': sensor_data,
                'rule_name': rule.rule_name,
                'rule_description': rule.description
            }
        )
        
        db.add(alert)
        db.commit()
        db.refresh(alert)
        
        return alert
        
    except Exception as e:
        print(f"Error creating alert: {e}")
        db.rollback()
        return None


def _generate_alert_messages(
    rule: AlertRule,
    current_value: float,
    threshold_value: Optional[float]
) -> Dict[str, str]:
    """
    Generate multilingual alert messages
    """
    pond = rule.pond
    parameter = rule.parameter
    severity = rule.severity
    unit = settings.ALERT_THRESHOLDS.get(parameter, {}).get('unit', '')
    
    # Determine alert type
    if rule.min_threshold and current_value < rule.min_threshold:
        alert_type = "low"
    else:
        alert_type = "high"
    
    # Generate message key
    if severity == AlertSeverity.CRITICAL:
        if parameter == "temperature":
            message_key = f"critical_temp_{alert_type}"
        elif parameter == "dissolved_oxygen":
            message_key = "critical_oxygen_low"
        elif parameter == "ph":
            message_key = f"critical_ph_{alert_type}"
        else:
            message_key = "critical_generic"
    else:
        message_key = f"warning_{parameter}"
    
    # Get messages from config
    messages_fr = settings.ALERT_MESSAGES.get('fr', {})
    messages_ar = settings.ALERT_MESSAGES.get('ar', {})
    
    # Format messages
    format_data = {
        'value': current_value,
        'unit': unit,
        'pond_name': pond.name if pond else f"Pond {rule.pond_id}",
        'threshold': threshold_value or 'N/A'
    }
    
    # Default English message
    title = f"{severity.value.title()} Alert: {parameter} {alert_type} in {pond.name if pond else 'pond'}"
    message = f"{parameter} is {current_value} {unit}, threshold: {threshold_value} {unit}"
    
    # French message
    message_fr = messages_fr.get(message_key, message).format(**format_data)
    
    # Arabic message
    message_ar = messages_ar.get(message_key, message).format(**format_data)
    
    return {
        'title': title,
        'message': message,
        'message_fr': message_fr,
        'message_ar': message_ar
    }


async def _send_alert_notification(alert: Alert, rule: AlertRule, db: Session):
    """
    Send alert notification via configured channels
    """
    try:
        # Get pond owner
        pond = db.query(Pond).filter(Pond.id == alert.pond_id).first()
        if not pond or not pond.owner:
            return
        
        user = pond.owner
        notification_service = NotificationService()
        
        # Determine which notifications to send based on rule configuration
        notifications_sent = {}
        
        # Email notification
        if rule.send_email and user.email_notifications:
            try:
                await notification_service.send_email_alert(alert, user)
                notifications_sent['email'] = {
                    'sent_at': datetime.utcnow().isoformat(),
                    'status': 'sent',
                    'recipient': user.email
                }
            except Exception as e:
                notifications_sent['email'] = {
                    'sent_at': datetime.utcnow().isoformat(),
                    'status': 'failed',
                    'error': str(e)
                }
        
        # SMS notification
        if rule.send_sms and user.sms_notifications and user.phone_number:
            try:
                await notification_service.send_sms_alert(alert, user)
                notifications_sent['sms'] = {
                    'sent_at': datetime.utcnow().isoformat(),
                    'status': 'sent',
                    'recipient': user.phone_number
                }
            except Exception as e:
                notifications_sent['sms'] = {
                    'sent_at': datetime.utcnow().isoformat(),
                    'status': 'failed',
                    'error': str(e)
                }
        
        # Push notification
        if rule.send_push and user.push_notifications:
            try:
                await notification_service.send_push_alert(alert, user)
                notifications_sent['push'] = {
                    'sent_at': datetime.utcnow().isoformat(),
                    'status': 'sent',
                    'recipient': 'push_token'
                }
            except Exception as e:
                notifications_sent['push'] = {
                    'sent_at': datetime.utcnow().isoformat(),
                    'status': 'failed',
                    'error': str(e)
                }
        
        # Update alert with notification status
        alert.notifications_sent = notifications_sent
        db.commit()
        
    except Exception as e:
        print(f"Error sending alert notification: {e}")


def check_for_stale_data():
    """
    Check for ponds with stale data and create alerts
    This should be run as a scheduled task
    """
    db = SessionLocal()
    
    try:
        # Find ponds that haven't received data in the last hour
        stale_threshold = datetime.utcnow() - timedelta(hours=1)
        
        ponds_with_stale_data = db.query(Pond).filter(
            and_(
                Pond.is_active == True,
                ~Pond.id.in_(
                    db.query(SensorData.pond_id).filter(
                        SensorData.timestamp >= stale_threshold
                    ).distinct()
                )
            )
        ).all()
        
        for pond in ponds_with_stale_data:
            # Check if we already have a recent stale data alert
            recent_stale_alert = db.query(Alert).filter(
                and_(
                    Alert.pond_id == pond.id,
                    Alert.parameter == 'data_connectivity',
                    Alert.triggered_at >= datetime.utcnow() - timedelta(hours=2),
                    Alert.status == AlertStatus.ACTIVE
                )
            ).first()
            
            if not recent_stale_alert:
                # Create stale data alert
                alert = Alert(
                    pond_id=pond.id,
                    parameter='data_connectivity',
                    current_value=0,
                    threshold_value=1,
                    severity=AlertSeverity.WARNING,
                    title=f"No data received from {pond.name}",
                    message=f"No sensor data received from {pond.name} for over 1 hour",
                    message_fr=f"Aucune donnée reçue de {pond.name} depuis plus d'1 heure",
                    message_ar=f"لم يتم استلام بيانات من {pond.name} لأكثر من ساعة",
                    context_data={'alert_type': 'stale_data'}
                )
                
                db.add(alert)
        
        db.commit()
        
    except Exception as e:
        print(f"Error checking for stale data: {e}")
        db.rollback()
    finally:
        db.close()