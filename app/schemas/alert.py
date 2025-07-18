"""
Pydantic schemas for alert system
Handles alert rules, active alerts, and notifications
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert status"""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class AlertRuleBase(BaseModel):
    """Base alert rule schema"""
    pond_id: int = Field(..., gt=0, description="Pond ID")
    parameter: str = Field(..., max_length=50, description="Parameter to monitor")
    rule_name: str = Field(..., max_length=100, description="Rule name")
    description: Optional[str] = Field(None, max_length=500)
    
    # Thresholds
    min_threshold: Optional[float] = Field(None, description="Minimum acceptable value")
    max_threshold: Optional[float] = Field(None, description="Maximum acceptable value")
    
    # Configuration
    severity: AlertSeverity = Field(default=AlertSeverity.WARNING)
    is_active: bool = Field(default=True)
    
    # Notification settings
    send_email: bool = Field(default=True)
    send_sms: bool = Field(default=False)
    send_push: bool = Field(default=True)
    
    # Rate limiting
    cooldown_minutes: int = Field(default=30, ge=1, le=1440)
    max_alerts_per_hour: int = Field(default=4, ge=1, le=100)
    
    # Advanced conditions
    conditions: Optional[Dict[str, Any]] = Field(default={})

    @validator('min_threshold', 'max_threshold')
    def validate_thresholds(cls, v, values):
        """Ensure at least one threshold is set"""
        if v is None and values.get('min_threshold') is None and values.get('max_threshold') is None:
            raise ValueError('At least one threshold (min or max) must be set')
        return v

    @validator('max_threshold')
    def validate_max_greater_than_min(cls, v, values):
        """Ensure max threshold is greater than min threshold"""
        min_val = values.get('min_threshold')
        if v is not None and min_val is not None and v <= min_val:
            raise ValueError('Max threshold must be greater than min threshold')
        return v


class AlertRuleCreate(AlertRuleBase):
    """Schema for creating alert rules"""
    pass


class AlertRuleUpdate(BaseModel):
    """Schema for updating alert rules"""
    rule_name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    min_threshold: Optional[float] = None
    max_threshold: Optional[float] = None
    severity: Optional[AlertSeverity] = None
    is_active: Optional[bool] = None
    send_email: Optional[bool] = None
    send_sms: Optional[bool] = None
    send_push: Optional[bool] = None
    cooldown_minutes: Optional[int] = Field(None, ge=1, le=1440)
    max_alerts_per_hour: Optional[int] = Field(None, ge=1, le=100)
    conditions: Optional[Dict[str, Any]] = None


class AlertRuleInDB(AlertRuleBase):
    """Alert rule from database"""
    id: int
    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class AlertRuleResponse(AlertRuleInDB):
    """Alert rule API response"""
    pass


class AlertBase(BaseModel):
    """Base alert schema"""
    pond_id: int = Field(..., gt=0)
    parameter: str = Field(..., max_length=50)
    current_value: float
    threshold_value: Optional[float] = None
    severity: AlertSeverity
    title: str = Field(..., max_length=200)
    message: str = Field(..., max_length=1000)
    message_ar: Optional[str] = Field(None, max_length=1000, description="Arabic message")
    message_fr: Optional[str] = Field(None, max_length=1000, description="French message")
    context_data: Optional[Dict[str, Any]] = Field(default={})
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AlertCreate(AlertBase):
    """Schema for creating alerts"""
    rule_id: Optional[int] = None
    sensor_reading_id: Optional[int] = None


class AlertUpdate(BaseModel):
    """Schema for updating alerts"""
    status: Optional[AlertStatus] = None
    context_data: Optional[Dict[str, Any]] = None


class AlertInDB(AlertBase):
    """Alert from database"""
    id: int
    rule_id: Optional[int]
    status: AlertStatus
    triggered_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    acknowledged_by: Optional[int]
    resolved_by: Optional[int]
    sensor_reading_id: Optional[int]
    notifications_sent: Optional[Dict[str, Any]]
    
    class Config:
        from_attributes = True


class AlertResponse(AlertInDB):
    """Alert API response"""
    pond_name: Optional[str] = None


class AlertQuery(BaseModel):
    """Schema for querying alerts"""
    pond_id: Optional[int] = None
    severity: Optional[AlertSeverity] = None
    status: Optional[AlertStatus] = None
    parameter: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: Optional[int] = Field(default=50, ge=1, le=1000)
    offset: Optional[int] = Field(default=0, ge=0)
    order_by: Optional[str] = Field(default="triggered_at", pattern=r'^(triggered_at|severity|pond_id)$')
    order_direction: Optional[str] = Field(default="desc", pattern=r'^(asc|desc)$')


class AlertAcknowledge(BaseModel):
    """Schema for acknowledging alerts"""
    alert_ids: List[int] = Field(..., min_items=1, max_items=100)
    note: Optional[str] = Field(None, max_length=500)


class AlertResolve(BaseModel):
    """Schema for resolving alerts"""
    alert_ids: List[int] = Field(..., min_items=1, max_items=100)
    resolution_note: Optional[str] = Field(None, max_length=500)