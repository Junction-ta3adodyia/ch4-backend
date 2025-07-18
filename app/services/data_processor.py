"""
Data Processing Service
Handles data validation, anomaly detection, and aggregation
"""

import statistics
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from scipy import stats
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.models.sensor import SensorData, SensorDataAggregated
from app.models.pond import Pond
from app.schemas.sensor import SensorDataCreate
from app.config import settings

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from datetime import datetime, timedelta, timezone
import asyncio

from app.models.alert import Alert, AlertType, AlertSeverity, AlertStatus
from app.database import SessionLocal

from app.services.page_hinkley import detect_anomalies_page_hinkley, get_page_hinkley_diagnostics



def validate_sensor_data(sensor_data: SensorDataCreate) -> float:
    """
    Validate sensor data quality and return quality score (0-1)
    """
    quality_score = 1.0
    
    # Check for missing critical parameters
    critical_params = ['temperature', 'ph', 'dissolved_oxygen']
    missing_critical = sum(1 for param in critical_params if getattr(sensor_data, param) is None)
    quality_score -= (missing_critical / len(critical_params)) * 0.3
    
    # Check for unrealistic values
    unrealistic_penalty = 0
    
    # Temperature validation
    if sensor_data.temperature is not None:
        if sensor_data.temperature < -5 or sensor_data.temperature > 50:
            unrealistic_penalty += 0.2
    
    # pH validation
    if sensor_data.ph is not None:
        if sensor_data.ph < 0 or sensor_data.ph > 14:
            unrealistic_penalty += 0.2
    
    # Dissolved oxygen validation
    if sensor_data.dissolved_oxygen is not None:
        if sensor_data.dissolved_oxygen < 0 or sensor_data.dissolved_oxygen > 30:
            unrealistic_penalty += 0.2
    
    quality_score -= unrealistic_penalty
    
    # Check timestamp validity - FIXED: Use timezone-aware comparison
    if sensor_data.timestamp:
        current_time = datetime.now(timezone.utc)
        # Ensure both datetimes are timezone-aware
        sensor_timestamp = sensor_data.timestamp
        if sensor_timestamp.tzinfo is None:
            sensor_timestamp = sensor_timestamp.replace(tzinfo=timezone.utc)
        
        if sensor_timestamp > current_time:
            quality_score -= 0.1
    
    # Check for data source
    if sensor_data.data_source and sensor_data.data_source != 'sensor':
        quality_score -= 0.1  # Manual data might be less accurate
    
    return max(0.0, min(1.0, quality_score))


async def detect_anomalies(sensor_data: SensorDataCreate, db: Session) -> bool:
    """
    Detect anomalies using Page-Hinkley change point detection
    """
    return await detect_anomalies_page_hinkley(sensor_data, db)


async def get_pond_latest_data(pond_id: int, db: Session) -> Optional[Dict[str, Any]]:
    """
    Get the latest sensor data for a pond
    """
    latest_data = db.query(SensorData).filter(
        SensorData.pond_id == pond_id
    ).order_by(desc(SensorData.timestamp)).first()
    
    if not latest_data:
        return None
    
    return {
        'timestamp': latest_data.timestamp,
        'temperature': latest_data.temperature,
        'ph': latest_data.ph,
        'dissolved_oxygen': latest_data.dissolved_oxygen,
        'turbidity': latest_data.turbidity,
        'ammonia': latest_data.ammonia,
        'nitrate': latest_data.nitrate,
        'salinity': latest_data.salinity,
        'water_level': latest_data.water_level,
        'fish_count': latest_data.fish_count,
        'data_source': latest_data.data_source,
        'quality_score': getattr(latest_data, 'quality_score', None)
    }


async def get_pond_statistics(pond_id: int, db: Session, days: int = 30) -> Dict[str, Any]:
    """Get comprehensive pond statistics"""
    
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Get sensor data for the period
    sensor_data = db.query(SensorData).filter(
        and_(
            SensorData.pond_id == pond_id,
            SensorData.timestamp >= start_date
        )
    ).order_by(SensorData.timestamp.asc()).all()
    
    if not sensor_data:
        return {
            "message": "No data available for the specified period",
            "period_days": days,
            "total_readings": 0,
            "date_range": {
                "start": start_date.isoformat(),
                "end": datetime.now(timezone.utc).isoformat()
            }
        }
    
    # Calculate statistics
    stats = {
        "period_days": days,
        "total_readings": len(sensor_data),
        "date_range": {
            "start": start_date.isoformat(),
            "end": datetime.now(timezone.utc).isoformat()
        },
        "parameters": {},
        "data_quality": {
            "completeness": 0,
            "missing_readings": 0
        }
    }
    
    # Calculate parameter statistics
    parameters = ['temperature', 'ph', 'dissolved_oxygen', 'turbidity', 'ammonia', 'nitrate']
    
    for param in parameters:
        values = [getattr(reading, param) for reading in sensor_data if getattr(reading, param) is not None]
        
        if values:
            param_stats = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "average": round(sum(values) / len(values), 2),
                "median": round(statistics.median(values), 2),
                "std_dev": round(statistics.stdev(values) if len(values) > 1 else 0, 2),
                "latest": values[-1] if values else None,
                "first": values[0] if values else None
            }
            
            # Calculate trend (simple linear trend)
            if len(values) > 1:
                x_values = list(range(len(values)))
                try:
                    # Simple linear regression slope
                    n = len(values)
                    sum_x = sum(x_values)
                    sum_y = sum(values)
                    sum_xy = sum(x * y for x, y in zip(x_values, values))
                    sum_x2 = sum(x * x for x in x_values)
                    
                    denominator = n * sum_x2 - sum_x * sum_x
                    if denominator != 0:
                        slope = (n * sum_xy - sum_x * sum_y) / denominator
                        param_stats["trend_slope"] = round(slope, 4)
                        
                        if slope > 0.01:
                            param_stats["trend"] = "increasing"
                        elif slope < -0.01:
                            param_stats["trend"] = "decreasing"
                        else:
                            param_stats["trend"] = "stable"
                    else:
                        param_stats["trend"] = "stable"
                        param_stats["trend_slope"] = 0
                except (ZeroDivisionError, ValueError):
                    param_stats["trend"] = "stable"
                    param_stats["trend_slope"] = 0
            else:
                param_stats["trend"] = "insufficient_data"
                param_stats["trend_slope"] = 0
            
            stats["parameters"][param] = param_stats
        else:
            # No data for this parameter
            stats["parameters"][param] = {
                "count": 0,
                "message": "No data available for this parameter"
            }
    
    # Calculate data quality metrics
    expected_readings = days * 24  # Assuming hourly readings
    if expected_readings > 0:
        stats["data_quality"]["completeness"] = round((len(sensor_data) / expected_readings) * 100, 1)
        stats["data_quality"]["missing_readings"] = expected_readings - len(sensor_data)
    else:
        stats["data_quality"]["completeness"] = 0
        stats["data_quality"]["missing_readings"] = 0
    
    return stats


def _calculate_trend(data: np.ndarray) -> str:
    """
    Calculate trend direction for a parameter
    """
    if len(data) < 3:
        return 'insufficient_data'
    
    try:
        # Use linear regression to determine trend
        x = np.arange(len(data))
        slope, _, r_value, p_value, _ = stats.linregress(x, data)
        
        # Consider trend significant if p-value < 0.05 and R² > 0.1
        if p_value < 0.05 and r_value**2 > 0.1:
            if slope > 0:
                return 'increasing'
            else:
                return 'decreasing'
        else:
            return 'stable'
    except Exception:
        return 'stable'



async def process_sensor_data_batch(
    sensor_data_list: List[SensorDataCreate], 
    db: Session
) -> Dict[str, Any]:
    """
    Process a batch of sensor data entries
    """
    results = {
        "processed": 0,
        "errors": [],
        "quality_scores": [],
        "anomalies": 0
    }
    
    for i, sensor_data in enumerate(sensor_data_list):
        try:
            # Validate data quality
            quality_score = validate_sensor_data(sensor_data)
            results["quality_scores"].append(quality_score)
            
            # Detect anomalies
            is_anomaly = await detect_anomalies(sensor_data, db)
            if is_anomaly:
                results["anomalies"] += 1
            
            results["processed"] += 1
            
        except Exception as e:
            results["errors"].append(f"Error processing entry {i}: {str(e)}")
    
    return results

async def process_sensor_alerts(pond_id: int, sensor_reading_id: Optional[int] = None):
    """
    Process alerts for sensor data
    This runs in the background after sensor data is saved
    """
    try:
        # Create a new database session for background processing
        db = SessionLocal()
        
        try:
            # Get the pond
            pond = db.query(Pond).filter(Pond.id == pond_id).first()
            if not pond:
                return
            
            # Get recent sensor data (last reading or specific one)
            if sensor_reading_id:
                sensor_data = db.query(SensorData).filter(
                    SensorData.id == sensor_reading_id
                ).first()
                if sensor_data:
                    await _check_sensor_alerts(sensor_data, db)
            else:
                # Process recent data for the pond
                recent_data = db.query(SensorData).filter(
                    SensorData.pond_id == pond_id
                ).order_by(desc(SensorData.timestamp)).limit(5).all()
                
                for data in recent_data:
                    await _check_sensor_alerts(data, db)
            
            db.commit()
            
        finally:
            db.close()
            
    except Exception as e:
        print(f"Error in alert processing: {e}")


async def _check_sensor_alerts(sensor_data: SensorData, db: Session):
    """
    Check individual sensor data for alert conditions
    """
    alerts_to_create = []
    
    # Temperature alerts
    if sensor_data.temperature is not None:
        if sensor_data.temperature > 35:
            alerts_to_create.append({
                'type': AlertType.HIGH_TEMPERATURE,
                'severity': AlertSeverity.CRITICAL if sensor_data.temperature > 40 else AlertSeverity.WARNING,
                'parameter': 'temperature',
                'title': 'High Temperature Alert',
                'message': f"High temperature detected: {sensor_data.temperature}°C",
                'value': sensor_data.temperature,
                'threshold': 35
            })
        elif sensor_data.temperature < 15:
            alerts_to_create.append({
                'type': AlertType.LOW_TEMPERATURE,
                'severity': AlertSeverity.CRITICAL if sensor_data.temperature < 10 else AlertSeverity.WARNING,
                'parameter': 'temperature',
                'title': 'Low Temperature Alert',
                'message': f"Low temperature detected: {sensor_data.temperature}°C",
                'value': sensor_data.temperature,
                'threshold': 15
            })
    
    # pH alerts
    if sensor_data.ph is not None:
        if sensor_data.ph > 8.5:
            alerts_to_create.append({
                'type': AlertType.HIGH_PH,
                'severity': AlertSeverity.CRITICAL if sensor_data.ph > 9.0 else AlertSeverity.WARNING,
                'parameter': 'ph',
                'title': 'High pH Alert',
                'message': f"High pH detected: {sensor_data.ph}",
                'value': sensor_data.ph,
                'threshold': 8.5
            })
        elif sensor_data.ph < 6.5:
            alerts_to_create.append({
                'type': AlertType.LOW_PH,
                'severity': AlertSeverity.CRITICAL if sensor_data.ph < 6.0 else AlertSeverity.WARNING,
                'parameter': 'ph',
                'title': 'Low pH Alert',
                'message': f"Low pH detected: {sensor_data.ph}",
                'value': sensor_data.ph,
                'threshold': 6.5
            })
    
    # Dissolved Oxygen alerts
    if sensor_data.dissolved_oxygen is not None:
        if sensor_data.dissolved_oxygen < 4.0:
            alerts_to_create.append({
                'type': AlertType.LOW_OXYGEN,
                'severity': AlertSeverity.CRITICAL if sensor_data.dissolved_oxygen < 2.0 else AlertSeverity.WARNING,
                'parameter': 'dissolved_oxygen',
                'title': 'Low Oxygen Alert',
                'message': f"Low dissolved oxygen: {sensor_data.dissolved_oxygen} mg/L",
                'value': sensor_data.dissolved_oxygen,
                'threshold': 4.0
            })
    
    # Ammonia alerts
    if sensor_data.ammonia is not None and sensor_data.ammonia > 0.5:
        alerts_to_create.append({
            'type': AlertType.HIGH_AMMONIA,
            'severity': AlertSeverity.CRITICAL if sensor_data.ammonia > 2.0 else AlertSeverity.WARNING,
            'parameter': 'ammonia',
            'title': 'High Ammonia Alert',
            'message': f"High ammonia detected: {sensor_data.ammonia} mg/L",
            'value': sensor_data.ammonia,
            'threshold': 0.5
        })
    
    # Create alerts in database
    for alert_data in alerts_to_create:
        # Check if similar alert already exists recently
        existing_alert = db.query(Alert).filter(
            and_(
                Alert.pond_id == sensor_data.pond_id,
                Alert.alert_type == alert_data['type'],
                Alert.parameter == alert_data['parameter'],
                Alert.status == AlertStatus.ACTIVE,
                Alert.triggered_at >= datetime.now(timezone.utc) - timedelta(hours=1)
            )
        ).first()
        
        if not existing_alert:
            # Create multilingual messages
            message_fr = alert_data['message']
            message_ar = _translate_to_arabic(alert_data['message'], alert_data['parameter'])
            
            alert = Alert(
                pond_id=sensor_data.pond_id,
                sensor_reading_id=sensor_data.id,
                alert_type=alert_data['type'],
                severity=alert_data['severity'],
                status=AlertStatus.ACTIVE,
                parameter=alert_data['parameter'],
                current_value=alert_data['value'],
                threshold_value=alert_data['threshold'],
                title=alert_data['title'],
                message=alert_data['message'],  # Default message
                message_fr=message_fr,
                message_ar=message_ar,
                triggered_at=datetime.now(timezone.utc),
                context_data={
                    'sensor_data_id': sensor_data.id,
                    'pond_id': sensor_data.pond_id,
                    'detection_time': datetime.now(timezone.utc).isoformat(),
                    'data_source': getattr(sensor_data, 'data_source', 'unknown')
                },
                notifications_sent={}
            )
            db.add(alert)

def _translate_to_arabic(message: str, parameter: str) -> str:
    """Translate alert messages to Arabic"""
    translations = {
        'temperature': {
            'High temperature detected': 'تم اكتشاف درجة حرارة عالية',
            'Low temperature detected': 'تم اكتشاف درجة حرارة منخفضة'
        },
        'ph': {
            'High pH detected': 'تم اكتشاف رقم هيدروجيني عالي',
            'Low pH detected': 'تم اكتشاف رقم هيدروجيني منخفض'
        },
        'dissolved_oxygen': {
            'Low dissolved oxygen': 'أكسجين منحل منخفض'
        },
        'ammonia': {
            'High ammonia detected': 'تم اكتشاف أمونيا عالية'
        }
    }
    
    # Simple translation lookup
    for key, translation in translations.get(parameter, {}).items():
        if key in message:
            return message.replace(key, translation)
    
    return message  # Return original if no translation found



def get_active_alerts(pond_id: int, db: Session) -> List[Alert]:
    """
    Get active alerts for a pond
    """
    return db.query(Alert).filter(
        and_(
            Alert.pond_id == pond_id,
            Alert.status == AlertStatus.ACTIVE
        )
    ).order_by(desc(Alert.triggered_at)).all()


def acknowledge_alert(alert_id: int, db: Session, user_id: int) -> bool:
    """
    Acknowledge an alert
    """
    try:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_by = user_id
            alert.acknowledged_at = datetime.now(timezone.utc)
            db.commit()
            return True
    except Exception as e:
        print(f"Error acknowledging alert: {e}")
    return False


