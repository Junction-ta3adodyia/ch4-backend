"""
Page-Hinkley Change Point Detection Service
Advanced anomaly detection for aquaculture sensor data
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.models.sensor import SensorData
from app.models.alert import Alert, AlertType, AlertSeverity, AlertStatus
from app.schemas.sensor import SensorDataCreate


@dataclass
class PageHinkleyState:
    """State for Page-Hinkley algorithm"""
    cumulative_sum: float = 0.0
    min_cumulative_sum: float = 0.0
    max_cumulative_sum: float = 0.0
    mean_estimate: float = 0.0
    sample_count: int = 0
    last_change_point: int = 0
    
    
class PageHinkleyDetector:
    """
    Page-Hinkley Change Point Detection Algorithm
    Detects abrupt changes in sensor data streams
    """
    
    def __init__(self, threshold: float = 5.0, alpha: float = 0.01, min_samples: int = 3):
        """
        Initialize Page-Hinkley detector
        
        Args:
            threshold: Detection threshold (lower = more sensitive)
            alpha: Learning rate for mean estimation
            min_samples: Minimum samples before detection starts
        """
        self.threshold = threshold
        self.alpha = alpha
        self.min_samples = min_samples
        self.state = PageHinkleyState()
    
    def update_and_detect(self, value: float) -> Tuple[bool, float]:
        """
        Update detector state and check for change point
        
        Args:
            value: New sensor value
            
        Returns:
            Tuple of (is_change_point, anomaly_score)
        """
        state = self.state
        
        # Update mean estimate using exponential moving average
        if state.sample_count == 0:
            state.mean_estimate = value
        else:
            state.mean_estimate = (1 - self.alpha) * state.mean_estimate + self.alpha * value
        
        state.sample_count += 1
        
        # Calculate deviation from mean
        deviation = value - state.mean_estimate
        
        # Update cumulative sum
        state.cumulative_sum += deviation
        
        # Update min and max cumulative sums
        state.min_cumulative_sum = min(state.min_cumulative_sum, state.cumulative_sum)
        state.max_cumulative_sum = max(state.max_cumulative_sum, state.cumulative_sum)
        
        # Calculate Page-Hinkley statistics
        ph_up = state.cumulative_sum - state.min_cumulative_sum
        ph_down = state.max_cumulative_sum - state.cumulative_sum
        
        # Calculate anomaly score (0-1, higher means more anomalous)
        anomaly_score = max(ph_up, ph_down) / max(self.threshold, 1.0)
        anomaly_score = min(1.0, anomaly_score)  # Cap at 1.0
        
        # Detect change point
        is_change_point = False
        if state.sample_count >= self.min_samples:
            if ph_up > self.threshold or ph_down > self.threshold:
                is_change_point = True
                print(f"🔍 Change detected: ph_up={ph_up:.2f}, ph_down={ph_down:.2f}, threshold={self.threshold}")
        
        return is_change_point, anomaly_score


class AquaculturePageHinkleyService:
    """
    Aquaculture-specific Page-Hinkley anomaly detection service.
    Uses sliding window approach per parameter for consistent detection.
    """
    
    def __init__(self):
        # Parameter-specific detector configurations - made more sensitive
        self.detector_configs = {
            'temperature': {'threshold': 1.5, 'alpha': 0.1, 'min_samples': 3},  # More sensitive
            'ph': {'threshold': 1.0, 'alpha': 0.05, 'min_samples': 3},
            'dissolved_oxygen': {'threshold': 1.2, 'alpha': 0.06, 'min_samples': 3},
            'ammonia': {'threshold': 0.8, 'alpha': 0.04, 'min_samples': 3},
            'nitrate': {'threshold': 1.0, 'alpha': 0.04, 'min_samples': 3},
            'nitrite': {'threshold': 0.9, 'alpha': 0.04, 'min_samples': 3},
            'turbidity': {'threshold': 1.5, 'alpha': 0.08, 'min_samples': 3},
            'salinity': {'threshold': 1.2, 'alpha': 0.05, 'min_samples': 3},
            'fish_count': {'threshold': 2.0, 'alpha': 0.1, 'min_samples': 4},
            'fish_length': {'threshold': 1.8, 'alpha': 0.08, 'min_samples': 4},
            'fish_weight': {'threshold': 1.8, 'alpha': 0.08, 'min_samples': 4},
            'water_level': {'threshold': 1.4, 'alpha': 0.06, 'min_samples': 3},
            'flow_rate': {'threshold': 1.6, 'alpha': 0.08, 'min_samples': 3}
        }

    def _get_historical_data_for_parameter(self, pond_id: int, parameter: str, db: Session, limit: int = 10) -> List[float]:
        """
        Get historical data for a specific parameter from the database.
        """
        try:
            historical_records = db.query(SensorData).filter(
                SensorData.pond_id == pond_id,
                # SensorData.is_anomaly == False,
                getattr(SensorData, parameter).isnot(None)
            ).order_by(desc(SensorData.timestamp)).limit(limit).all()
            
            # Reverse to get chronological order (oldest to newest)
            historical_records.reverse()
            
            # Extract parameter values
            values = [getattr(record, parameter) for record in historical_records]
            # print(f"📊 Historical {parameter} data: {values}")
            return values
        except Exception as e:
            print(f"Error fetching historical data for {parameter}: {e}")
            return []

    def _run_detection_on_parameter_window(self, parameter: str, window: List[float]) -> Tuple[bool, float, Dict]:
        """
        Runs Page-Hinkley detector on a window of data for a specific parameter.
        """
        if not window or len(window) < 2:
            return False, 0.0, {'error': 'insufficient_data', 'window_size': len(window)}
            
        config = self.detector_configs.get(parameter, 
                                         {'threshold': 1.5, 'alpha': 0.05, 'min_samples': 3})
        
        print(f"🔍 Running detection for {parameter} with config: {config}")
        print(f"   Window data: {window}")
        
        detector = PageHinkleyDetector(**config)
        
        final_is_change_point = False
        final_anomaly_score = 0.0
        detection_details = {
            'window_size': len(window),
            'parameter': parameter,
            'config': config,
            'final_mean': 0.0,
            'final_cumsum': 0.0,
            'step_by_step': []
        }

        # Process each value in the window
        for i, value in enumerate(window):
            is_change_point, anomaly_score = detector.update_and_detect(value)
            
            step_info = {
                'step': i,
                'value': value,
                'mean': detector.state.mean_estimate,
                'cumsum': detector.state.cumulative_sum,
                'is_change': is_change_point,
                'score': anomaly_score
            }
            detection_details['step_by_step'].append(step_info)
            
            print(f"   Step {i}: value={value:.2f}, mean={detector.state.mean_estimate:.2f}, "
                  f"cumsum={detector.state.cumulative_sum:.2f}, change={is_change_point}, score={anomaly_score:.3f}")
            
            # Store final results (last point)
            if i == len(window) - 1:
                final_is_change_point = is_change_point
                final_anomaly_score = anomaly_score
                detection_details['final_mean'] = detector.state.mean_estimate
                detection_details['final_cumsum'] = detector.state.cumulative_sum
                detection_details['is_last_point_anomaly'] = is_change_point
                detection_details['anomaly_score'] = anomaly_score
                detection_details['sample_count'] = detector.state.sample_count
        
        print(f"   🎯 Final result for {parameter}: anomaly={final_is_change_point}, score={final_anomaly_score:.3f}")
        return final_is_change_point, final_anomaly_score, detection_details

    async def detect_anomaly_with_alerts(self, pond_id: int, sensor_data: SensorDataCreate, db: Session) -> Dict[str, any]:
        """
        Detects anomalies by analyzing the new data point against historical data per parameter.
        Creates an alert if anomalies are found.
        """
        print(f"🔍 Starting anomaly detection for pond {pond_id}")
        
        results = {
            'is_anomaly': False,
            'anomaly_score': 0.0,
            'parameter_results': {},
            'change_points_detected': [],
            'alert_id': None
        }

        # All possible parameters to check
        parameters_to_check = [
            'temperature', 'ph', 'dissolved_oxygen', 'ammonia', 'nitrate', 'nitrite',
            'turbidity', 'salinity', 'fish_count', 'fish_length', 'fish_weight',
            'water_level', 'flow_rate'
        ]

        max_anomaly_score = 0.0
        total_anomalies = 0

        for param in parameters_to_check:
            new_value = getattr(sensor_data, param)
            
            # Skip if new value is None
            if new_value is None:
                print(f"   ⏭️  Skipping {param}: value is None")
                continue

            # print(f"📊 Processing {param}: new_value={new_value}")

            # Get historical data for this parameter
            historical_values = self._get_historical_data_for_parameter(pond_id, param, db, limit=10)
            
            # Create window: historical + new value
            window = historical_values + [new_value]
            
            # print(f"   Window size: {len(window)} (historical: {len(historical_values)} + new: 1)")
            
            # Run detection on this parameter's window
            is_anomaly, anomaly_score, detection_details = self._run_detection_on_parameter_window(param, window)
            
            # Store results for this parameter
            results['parameter_results'][param] = {
                'value': new_value,
                'is_anomaly': is_anomaly,
                'anomaly_score': anomaly_score,
                'historical_count': len(historical_values),
                'window_size': len(window),
                'detection_details': detection_details
            }
            
            # Track overall anomaly status
            if is_anomaly:
                print(f"🚨 ANOMALY DETECTED in {param}!")
                results['change_points_detected'].append(param)
                total_anomalies += 1
                max_anomaly_score = max(max_anomaly_score, anomaly_score)

        # Determine overall anomaly status
        results['is_anomaly'] = total_anomalies > 0
        results['anomaly_score'] = max_anomaly_score
        results['total_anomalous_parameters'] = total_anomalies

        print(f"🎯 Final detection results:")
        print(f"   Total anomalies: {total_anomalies}")
        print(f"   Max anomaly score: {max_anomaly_score:.3f}")
        print(f"   Anomalous parameters: {results['change_points_detected']}")

        # Create alert if anomaly detected
        if results['is_anomaly']:
            alert = await self.create_anomaly_alert(pond_id, sensor_data, results, db)
            results['alert_id'] = alert.id if alert else None
        
        return results

    async def create_anomaly_alert(self, pond_id: int, sensor_data: SensorDataCreate, 
                                detection_results: Dict, db: Session) -> Optional[Alert]:
        """Create an alert when anomaly is detected"""
        try:
            anomaly_score = detection_results['anomaly_score']
            change_points = detection_results['change_points_detected']
            total_anomalies = detection_results['total_anomalous_parameters']
            
            # Determine severity based on number of anomalous parameters and score
            if total_anomalies >= 3 or anomaly_score >= 0.8:
                severity = AlertSeverity.CRITICAL
            elif total_anomalies >= 2 or anomaly_score >= 0.6:
                severity = AlertSeverity.WARNING
            else:
                severity = AlertSeverity.INFO
            
            affected_params = ', '.join(change_points[:5])  # Limit to first 5 for readability
            if len(change_points) > 5:
                affected_params += f" and {len(change_points) - 5} more"
            
            message = f"Anomaly detected in {affected_params}. Score: {anomaly_score:.2f}"
            
            # Serialize sensor_data to ensure JSON compatibility
            def make_json_serializable(obj):
                """Convert datetime objects to ISO format strings for JSON serialization"""
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {key: make_json_serializable(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [make_json_serializable(item) for item in obj]
                else:
                    return obj
            
            # Create JSON-safe context data
            alert_context = {
                'detection_method': 'page_hinkley_windowed_per_parameter',
                'anomaly_score': anomaly_score,
                'total_anomalous_parameters': total_anomalies,
                'change_points_detected': change_points,
                'parameter_results': make_json_serializable(detection_results['parameter_results']),
                'sensor_values': make_json_serializable(sensor_data.dict())
            }
            
            alert = Alert(
                pond_id=pond_id,
                alert_type=AlertType.ANOMALY_DETECTED,
                severity=severity,
                status=AlertStatus.ACTIVE,
                parameter=change_points[0] if change_points else 'multiple',
                current_value=anomaly_score,
                threshold_value=0.5,
                title="Parameter Anomaly Detected",
                message=message,
                message_fr=f"Anomalie détectée - Paramètres: {affected_params}. Score: {anomaly_score:.2f}",
                message_ar=f"تم اكتشاف شذوذ - المعايير: {affected_params}. النتيجة: {anomaly_score:.2f}",
                triggered_at=datetime.now(timezone.utc),
                context_data=alert_context,
                notifications_sent={}
            )
            
            db.add(alert)
            db.commit()
            db.refresh(alert)
            
            print(f"✅ Parameter anomaly alert created successfully: ID {alert.id}")
            print(f"   Affected parameters: {affected_params}")
            print(f"   Total anomalous parameters: {total_anomalies}")
            return alert
            
        except Exception as e:
            print(f"❌ Error creating parameter anomaly alert: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            return None

    def get_pond_detector_status(self, pond_id: int) -> Dict[str, any]:
        """Get status of windowed detection for a pond"""
        return {
            'status': 'windowed_per_parameter_detection',
            'description': 'Uses sliding window of 10 previous points per parameter plus new point',
            'window_size': 10,
            'parameters_monitored': list(self.detector_configs.keys()),
            'detection_method': 'page_hinkley_change_point_per_parameter',
            'parameter_configs': self.detector_configs
        }


# Global service instance
page_hinkley_service = AquaculturePageHinkleyService()


async def detect_anomalies_page_hinkley(sensor_data: SensorDataCreate, db: Session) -> bool:
    """Main anomaly detection function using Page-Hinkley method"""
    try:
        pond_id = sensor_data.pond_id
        results = await page_hinkley_service.detect_anomaly_with_alerts(pond_id, sensor_data, db)
        return results['is_anomaly']
    except Exception as e:
        print(f"Error in Page-Hinkley anomaly detection: {e}")
        return False


def get_page_hinkley_diagnostics(pond_id: int) -> Dict[str, any]:
    """Get diagnostic information about Page-Hinkley detectors"""
    return page_hinkley_service.get_pond_detector_status(pond_id)