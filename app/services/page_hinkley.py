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
    
    def __init__(self, threshold: float = 5.0, alpha: float = 0.01, min_samples: int = 10):
        """
        Initialize Page-Hinkley detector
        
        Args:
            threshold: Detection threshold (higher = less sensitive)
            alpha: Learning rate for mean estimation
            min_samples: Minimum samples before detection starts
        """
        self.threshold = threshold
        self.alpha = alpha
        self.min_samples = min_samples
        self.states: Dict[str, PageHinkleyState] = {}
    
    def update_and_detect(self, parameter: str, value: float) -> Tuple[bool, float]:
        """
        Update detector state and check for change point
        
        Args:
            parameter: Parameter name (e.g., 'temperature', 'ph')
            value: New sensor value
            
        Returns:
            Tuple of (is_change_point, anomaly_score)
        """
        if parameter not in self.states:
            self.states[parameter] = PageHinkleyState()
        
        state = self.states[parameter]
        
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
                # Reset cumulative sums after detection
                state.cumulative_sum = 0.0
                state.min_cumulative_sum = 0.0
                state.max_cumulative_sum = 0.0
                state.last_change_point = state.sample_count
        
        return is_change_point, anomaly_score
    
    def get_state_info(self, parameter: str) -> Optional[Dict]:
        """Get current state information for a parameter"""
        if parameter not in self.states:
            return None
        
        state = self.states[parameter]
        return {
            'sample_count': state.sample_count,
            'mean_estimate': state.mean_estimate,
            'cumulative_sum': state.cumulative_sum,
            'last_change_point': state.last_change_point,
            'samples_since_change': state.sample_count - state.last_change_point
        }


class AquaculturePageHinkleyService:
    """
    Aquaculture-specific Page-Hinkley anomaly detection service
    """
    
    def __init__(self):
        # Parameter-specific detector configurations
        self.detector_configs = {
            'temperature': {'threshold': 3.0, 'alpha': 0.05, 'min_samples': 8},
            'ph': {'threshold': 2.0, 'alpha': 0.03, 'min_samples': 10},
            'dissolved_oxygen': {'threshold': 2.5, 'alpha': 0.04, 'min_samples': 8},
            'ammonia': {'threshold': 1.5, 'alpha': 0.02, 'min_samples': 12},
            'nitrate': {'threshold': 2.0, 'alpha': 0.02, 'min_samples': 12},
            'turbidity': {'threshold': 3.0, 'alpha': 0.05, 'min_samples': 8},
            'salinity': {'threshold': 2.5, 'alpha': 0.03, 'min_samples': 10}
        }
        
        # Store detectors per pond
        self.pond_detectors: Dict[int, Dict[str, PageHinkleyDetector]] = {}
    
    def _get_detector(self, pond_id: int, parameter: str) -> PageHinkleyDetector:
        """Get or create detector for specific pond and parameter"""
        if pond_id not in self.pond_detectors:
            self.pond_detectors[pond_id] = {}
        
        if parameter not in self.pond_detectors[pond_id]:
            config = self.detector_configs.get(parameter, 
                                             {'threshold': 2.5, 'alpha': 0.03, 'min_samples': 10})
            self.pond_detectors[pond_id][parameter] = PageHinkleyDetector(**config)
        
        return self.pond_detectors[pond_id][parameter]
    
    def initialize_detector_from_history(self, pond_id: int, parameter: str, 
                                       historical_values: List[float]) -> None:
        """Initialize detector with historical data"""
        detector = self._get_detector(pond_id, parameter)
        
        # Process historical data to warm up the detector
        for value in historical_values:
            detector.update_and_detect(parameter, value)
    
    def detect_anomaly(self, pond_id: int, sensor_data: SensorDataCreate) -> Dict[str, any]:
        """
        Detect anomalies in new sensor data using Page-Hinkley method
        
        Returns:
            Dictionary with anomaly detection results
        """
        results = {
            'is_anomaly': False,
            'anomaly_score': 0.0,
            'parameter_results': {},
            'change_points_detected': []
        }
        
        # Parameters to check
        parameters = ['temperature', 'ph', 'dissolved_oxygen', 'ammonia', 'nitrate', 'turbidity']
        
        max_anomaly_score = 0.0
        total_change_points = 0
        
        for param in parameters:
            value = getattr(sensor_data, param)
            if value is not None:
                detector = self._get_detector(pond_id, param)
                is_change_point, anomaly_score = detector.update_and_detect(param, value)
                
                results['parameter_results'][param] = {
                    'value': value,
                    'is_change_point': is_change_point,
                    'anomaly_score': anomaly_score,
                    'detector_state': detector.get_state_info(param)
                }
                
                if is_change_point:
                    results['change_points_detected'].append(param)
                    total_change_points += 1
                
                max_anomaly_score = max(max_anomaly_score, anomaly_score)
        
        # Determine overall anomaly status
        high_anomaly_params = sum(1 for p in results['parameter_results'].values() 
                                if p['anomaly_score'] > 0.7)
        moderate_anomaly_params = sum(1 for p in results['parameter_results'].values() 
                                    if 0.4 <= p['anomaly_score'] <= 0.7)
        
        results['is_anomaly'] = (
            high_anomaly_params >= 1 or 
            moderate_anomaly_params >= 2 or 
            total_change_points >= 2
        )
        
        results['anomaly_score'] = max_anomaly_score
        
        return results
    
    async def create_anomaly_alert(self, pond_id: int, sensor_data: SensorDataCreate, 
                                detection_results: Dict, db: Session) -> Optional[Alert]:
        """Create an alert when anomaly is detected"""
        try:
            anomaly_score = detection_results['anomaly_score']
            change_points = detection_results['change_points_detected']
            
            # Determine severity
            if anomaly_score >= 0.8 or len(change_points) >= 3:
                severity = AlertSeverity.CRITICAL
            elif anomaly_score >= 0.6 or len(change_points) >= 2:
                severity = AlertSeverity.WARNING
            else:
                severity = AlertSeverity.INFO
            
            # Create alert message
            affected_params = ', '.join(change_points) if change_points else 'paramètres multiples'
            
            alert_messages = {
                'fr': f"Anomalie détectée - Paramètres: {affected_params}. Score: {anomaly_score:.2f}",
                'ar': f"تم اكتشاف شذوذ - المعايير: {affected_params}. النتيجة: {anomaly_score:.2f}",
                'en': f"Anomaly detected - Parameters: {affected_params}. Score: {anomaly_score:.2f}"
            }
            
            # Create alert data for context_data field
            alert_context = {
                'detection_method': 'page_hinkley',
                'anomaly_score': anomaly_score,
                'change_points_detected': change_points,
                'parameter_details': detection_results['parameter_results'],
                'sensor_values': {
                    'temperature': sensor_data.temperature,
                    'ph': sensor_data.ph,
                    'dissolved_oxygen': sensor_data.dissolved_oxygen,
                    'ammonia': sensor_data.ammonia,
                    'nitrate': sensor_data.nitrate,
                    'turbidity': sensor_data.turbidity
                }
            }
            
            # Create alert with correct field names matching your model
            alert = Alert(
                pond_id=pond_id,
                alert_type=AlertType.ANOMALY_DETECTED,
                severity=severity,
                status=AlertStatus.ACTIVE,
                
                # Required fields for your model
                parameter=change_points[0] if change_points else 'multiple',  # Use first parameter or 'multiple'
                current_value=anomaly_score,
                threshold_value=0.5,  # Anomaly threshold
                
                # Messages - match your model fields
                title="Anomaly Detected",
                message=alert_messages['en'],  # Default English message
                message_fr=alert_messages['fr'],
                message_ar=alert_messages['ar'],
                
                # Timing - use triggered_at instead of created_at
                triggered_at=datetime.now(timezone.utc),
                
                # Additional context in JSONB field
                context_data=alert_context,
                
                # Empty notifications tracking
                notifications_sent={}
            )
            
            db.add(alert)
            db.commit()
            db.refresh(alert)
            
            print(f"✅ Anomaly alert created successfully: ID {alert.id}")
            return alert
            
        except Exception as e:
            print(f"❌ Error creating anomaly alert: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            return None
    
    async def detect_anomaly_with_alerts(self, pond_id: int, sensor_data: SensorDataCreate, db: Session) -> Dict[str, any]:
        """Detect anomalies and create alerts if needed"""
        # Initialize detectors if needed
        await self._initialize_detectors_if_needed(pond_id, db)
        
        # Run anomaly detection
        results = self.detect_anomaly(pond_id, sensor_data)
        
        # If anomaly detected, create alert
        if results['is_anomaly']:
            alert = await self.create_anomaly_alert(pond_id, sensor_data, results, db)
            results['alert_created'] = alert is not None
            results['alert_id'] = alert.id if alert else None
        else:
            results['alert_created'] = False
            results['alert_id'] = None
        
        return results
    
    async def _initialize_detectors_if_needed(self, pond_id: int, db: Session) -> None:
        """Initialize Page-Hinkley detectors with historical data if needed"""
        try:
            # Check if detectors are already initialized
            if pond_id in self.pond_detectors:
                return
            
            # Get historical data (last 100 readings)
            historical_data = db.query(SensorData).filter(
                and_(
                    SensorData.pond_id == pond_id,
                    SensorData.is_anomaly == False
                )
            ).order_by(desc(SensorData.timestamp)).limit(100).all()
            
            if len(historical_data) < 10:
                return
            
            # Reverse to get chronological order
            historical_data.reverse()
            
            # Initialize detectors for each parameter
            parameters = ['temperature', 'ph', 'dissolved_oxygen', 'ammonia', 'nitrate', 'turbidity']
            
            for param in parameters:
                values = [getattr(record, param) for record in historical_data 
                         if getattr(record, param) is not None]
                
                if len(values) >= 5:
                    self.initialize_detector_from_history(pond_id, param, values)
            
            print(f"Initialized Page-Hinkley detectors for pond {pond_id} with {len(historical_data)} records")
            
        except Exception as e:
            print(f"Error initializing detectors: {e}")
    
    def get_pond_detector_status(self, pond_id: int) -> Dict[str, any]:
        """Get status of all detectors for a pond"""
        if pond_id not in self.pond_detectors:
            return {'status': 'no_detectors', 'parameters': []}
        
        status = {
            'status': 'active',
            'parameters': {}
        }
        
        for param, detector in self.pond_detectors[pond_id].items():
            for param_name in detector.states:
                state_info = detector.get_state_info(param_name)
                if state_info:
                    status['parameters'][param_name] = state_info
        
        return status


# Global service instance
page_hinkley_service = AquaculturePageHinkleyService()


async def detect_anomalies_page_hinkley(sensor_data: SensorDataCreate, db: Session) -> bool:
    """Main anomaly detection function using Page-Hinkley method"""
    try:
        pond_id = sensor_data.pond_id
        results = page_hinkley_service.detect_anomaly(pond_id, sensor_data)
        return results['is_anomaly']
    except Exception as e:
        print(f"Error in Page-Hinkley anomaly detection: {e}")
        return False


def get_page_hinkley_diagnostics(pond_id: int) -> Dict[str, any]:
    """Get diagnostic information about Page-Hinkley detectors"""
    return page_hinkley_service.get_pond_detector_status(pond_id)