"""
Alert models - Manages alert rules, active alerts, and notifications
Implements the intelligent alerting system based on your threshold analysis
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum 

from app.database import Base


# In app/models/alert.py - update the AlertType enum
class AlertType(str, Enum):
    # Temperature alerts
    HIGH_TEMPERATURE = "high_temperature"
    LOW_TEMPERATURE = "low_temperature"
    TEMPERATURE_FLUCTUATION = "temperature_fluctuation"
    
    # pH alerts
    HIGH_PH = "high_ph"
    LOW_PH = "low_ph"
    PH_FLUCTUATION = "ph_fluctuation"
    
    # Oxygen alerts
    LOW_OXYGEN = "low_oxygen"
    HIGH_OXYGEN = "high_oxygen"
    OXYGEN_FLUCTUATION = "oxygen_fluctuation"
    
    # Chemical alerts
    HIGH_AMMONIA = "high_ammonia"
    HIGH_NITRATE = "high_nitrate"
    HIGH_NITRITE = "high_nitrite"
    HIGH_TURBIDITY = "high_turbidity"
    
    # Water level alerts
    LOW_WATER_LEVEL = "low_water_level"
    HIGH_WATER_LEVEL = "high_water_level"
    
    # Equipment alerts
    PUMP_FAILURE = "pump_failure"
    FILTER_MAINTENANCE = "filter_maintenance"
    SENSOR_MALFUNCTION = "sensor_malfunction"
    
    # Fish health alerts
    FISH_MORTALITY = "fish_mortality"
    FISH_BEHAVIOR_CHANGE = "fish_behavior_change"
    
    # Data quality alerts
    DATA_QUALITY_LOW = "data_quality_low"
    SENSOR_OFFLINE = "sensor_offline"
    
    # System alerts
    SYSTEM_ERROR = "system_error"
    MAINTENANCE_REQUIRED = "maintenance_required"
    
    # Anomaly detection alerts - ADD THIS
    ANOMALY_DETECTED = "anomaly_detected"
    PATTERN_CHANGE = "pattern_change"
    UNUSUAL_TREND = "unusual_trend"

class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status"""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class AlertRule(Base):
    """
    Alert Rules model
    Defines conditions that trigger alerts for each pond
    """
    __tablename__ = "alert_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    pond_id = Column(Integer, ForeignKey("ponds.id"), nullable=False, index=True)
    
    # Rule definition
    parameter = Column(String(50), nullable=False, index=True)  # temperature, ph, etc.
    rule_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # Threshold values (based on your analysis)
    min_threshold = Column(Float, nullable=True, comment="Minimum acceptable value")
    max_threshold = Column(Float, nullable=True, comment="Maximum acceptable value")
    
    # Alert configuration
    severity = Column(SQLEnum(AlertSeverity), nullable=False, default=AlertSeverity.WARNING)
    is_active = Column(Boolean, default=True, index=True)
    
    # Advanced rule conditions (JSON for flexibility)
    conditions = Column(JSONB, nullable=True, default={})
    
    # Notification settings
    send_email = Column(Boolean, default=True)
    send_sms = Column(Boolean, default=False)
    send_push = Column(Boolean, default=True)
    
    # Rate limiting to prevent spam
    cooldown_minutes = Column(Integer, default=30, comment="Minutes between similar alerts")
    max_alerts_per_hour = Column(Integer, default=4)
    
    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    pond = relationship("Pond")
    alerts = relationship("Alert", back_populates="rule")
    
    def __repr__(self):
        return f"<AlertRule(pond_id={self.pond_id}, parameter='{self.parameter}', severity='{self.severity.value}')>"


class Alert(Base):
    """
    Active Alerts model
    Stores triggered alerts and their status
    """
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    pond_id = Column(Integer, ForeignKey("ponds.id"), nullable=False, index=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=True, index=True)
    
    # Alert details
    parameter = Column(String(50), nullable=False, index=True)
    current_value = Column(Float, nullable=False)
    threshold_value = Column(Float, nullable=True)
    
    # Severity and status
    severity = Column(SQLEnum(AlertSeverity), nullable=False, index=True)
    status = Column(SQLEnum(AlertStatus), nullable=False, default=AlertStatus.ACTIVE, index=True)
    
    # Messages (multilingual support)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    message_ar = Column(Text, nullable=True, comment="Arabic translation")
    message_fr = Column(Text, nullable=True, comment="French translation")
    
    # Timing
    triggered_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    # User actions
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Additional context
    sensor_reading_id = Column(Integer, ForeignKey("sensor_data.id"), nullable=True)
    context_data = Column(JSONB, nullable=True, default={})
    
    # Notification tracking
    notifications_sent = Column(JSONB, nullable=True, default={})

    # Alert type
    alert_type = Column(SQLEnum(AlertType), nullable=False, default=AlertType.ANOMALY_DETECTED, index=True)
    
    # Relationships
    pond = relationship("Pond", back_populates="alerts")
    rule = relationship("AlertRule", back_populates="alerts")
    
    def __repr__(self):
        return f"<Alert(pond_id={self.pond_id}, parameter='{self.parameter}', severity='{self.severity.value}')>"


class PondHealth(Base):
    """
    Pond Health Records
    Stores calculated health scores and assessments based on your analysis
    """
    __tablename__ = "pond_health"
    
    id = Column(Integer, primary_key=True, index=True)
    pond_id = Column(Integer, ForeignKey("ponds.id"), nullable=False, index=True)
    
    # Health scores (based on your comprehensive assessment)
    overall_score = Column(Float, nullable=False, comment="Overall health score 0-100")
    weighted_score = Column(Float, nullable=False, comment="Weighted health score 0-100")
    grade = Column(String(5), nullable=False, comment="Letter grade A+ to F")
    status = Column(String(20), nullable=False, comment="Health status description")
    
    # Individual parameter scores
    temperature_score = Column(Float, nullable=True)
    ph_score = Column(Float, nullable=True)
    dissolved_oxygen_score = Column(Float, nullable=True)
    turbidity_score = Column(Float, nullable=True)
    ammonia_score = Column(Float, nullable=True)
    nitrate_score = Column(Float, nullable=True)
    
    # Risk assessment
    risk_level = Column(String(10), nullable=False, comment="Low, Medium, High")
    warning_count = Column(Integer, default=0)
    critical_issues = Column(JSONB, nullable=True, default=[])
    
    # Recommendations
    recommendations = Column(JSONB, nullable=True, default=[])
    action_priority = Column(String(20), nullable=True, comment="Maintain, Monitor, Improve, Urgent")
    
    # Data quality metrics
    parameters_assessed = Column(Integer, default=0)
    data_completeness = Column(Float, nullable=True, comment="Percentage of available parameters")
    assessment_confidence = Column(Float, nullable=True, comment="Confidence in assessment 0-1")
    
    # Time period for assessment
    assessment_period_start = Column(DateTime, nullable=False)
    assessment_period_end = Column(DateTime, nullable=False)
    calculated_at = Column(DateTime, server_default=func.now(), index=True)
    
    # Relationships
    pond = relationship("Pond", back_populates="health_records")
    
    def __repr__(self):
        return f"<PondHealth(pond_id={self.pond_id}, score={self.overall_score}, grade='{self.grade}')>"


class NotificationLog(Base):
    """
    Notification Log
    Tracks all sent notifications for debugging and analytics
    """
    __tablename__ = "notification_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Notification details
    notification_type = Column(String(20), nullable=False)  # email, sms, push
    recipient = Column(String(200), nullable=False)  # email address, phone number, device token
    subject = Column(String(200), nullable=True)
    message = Column(Text, nullable=False)
    
    # Status tracking
    status = Column(String(20), nullable=False, default="pending")  # pending, sent, failed, delivered
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    
    # Error handling
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Provider information
    provider = Column(String(50), nullable=True)  # twilio, firebase, smtp
    provider_response = Column(JSONB, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now(), index=True)
    
    def __repr__(self):
        return f"<NotificationLog(type='{self.notification_type}', status='{self.status}')>"
    

