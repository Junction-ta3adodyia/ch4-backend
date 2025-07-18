"""
Pydantic schemas for pond-related API endpoints
Handles request/response validation and serialization
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from app.schemas.alert import AlertSeverity
from app.models.pond import UserRole

class PondBase(BaseModel):
    """Base pond schema with common fields"""
    name: str = Field(..., min_length=1, max_length=100, description="Pond name")
    description: Optional[str] = Field(None, max_length=500, description="Pond description")
    capacity: Optional[float] = Field(None, gt=0, description="Capacity in liters")
    depth: Optional[float] = Field(None, gt=0, description="Depth in meters")
    surface_area: Optional[float] = Field(None, gt=0, description="Surface area in square meters")
    location_name: Optional[str] = Field(None, max_length=200)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    fish_species: Optional[str] = Field(None, max_length=100)
    fish_count: Optional[int] = Field(None, ge=0)
    stocking_date: Optional[datetime] = None
    aeration_system: bool = False
    filtration_system: bool = False
    heating_system: bool = False
    alert_config: Optional[Dict[str, Any]] = {}
    manager_contact: Optional[str] = Field(None, max_length=100)


class PondCreate(PondBase):
    """Schema for creating a new pond"""
    pass


class PondUpdate(BaseModel):
    """Schema for updating pond information"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    capacity: Optional[float] = Field(None, gt=0)
    depth: Optional[float] = Field(None, gt=0)
    surface_area: Optional[float] = Field(None, gt=0)
    location_name: Optional[str] = Field(None, max_length=200)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    fish_species: Optional[str] = Field(None, max_length=100)
    fish_count: Optional[int] = Field(None, ge=0)
    stocking_date: Optional[datetime] = None
    aeration_system: Optional[bool] = None
    filtration_system: Optional[bool] = None
    heating_system: Optional[bool] = None
    alert_config: Optional[Dict[str, Any]] = None
    manager_contact: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class PondInDB(PondBase):
    """Schema for pond data from database"""
    id: int
    uuid: UUID
    assigned_users: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PondResponse(PondInDB):
    """Schema for pond API responses"""
    pass


class PondSummary(BaseModel):
    """Simplified pond summary for lists"""
    id: int
    name: str
    health_score: Optional[float] = Field(None, ge=0, le=100)
    health_grade: Optional[str] = None
    status: str
    active_alerts_count: int = Field(default=0, ge=0)
    last_updated: datetime
    
    class Config:
        from_attributes = True


class PondWithStats(PondResponse):
    """Pond with additional statistics"""
    latest_reading: Optional[Dict[str, Any]] = None
    health_score: Optional[float] = Field(None, ge=0, le=100)
    health_grade: Optional[str] = None
    active_alerts_count: int = Field(default=0, ge=0)
    last_data_timestamp: Optional[datetime] = None
    push_notifications: bool = True

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    """Base user schema"""
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    first_name: Optional[str] = Field(None, max_length=50)
    last_name: Optional[str] = Field(None, max_length=50)
    phone_number: Optional[str] = Field(None, max_length=20)
    language: str = Field(default="fr", pattern=r'^(fr|ar|en)$')
    timezone: str = Field(default="Africa/Algiers")
    email_notifications: bool = True
    sms_notifications: bool = True
    push_notifications: bool = True


class UserCreate(UserBase):
    """Schema for user registration"""
    password: str = Field(..., min_length=8, max_length=100)
    role: UserRole = Field(default=UserRole.OBSERVER, description="Role of the user")



class UserUpdate(BaseModel):
    """Schema for updating user information"""
    first_name: Optional[str] = Field(None, max_length=50)
    last_name: Optional[str] = Field(None, max_length=50)
    phone_number: Optional[str] = Field(None, max_length=20)
    language: Optional[str] = Field(None, pattern=r'^(fr|ar|en)$')
    timezone: Optional[str] = None
    email_notifications: Optional[bool] = None
    sms_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    role: UserRole


class UserInDB(UserBase):
    """User schema from database"""
    id: int
    uuid: UUID
    is_active: bool
    is_verified: bool
    last_login: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserResponse(UserInDB):
    """User response schema (excludes sensitive data)"""
    assigned_ponds: List[PondSummary] = [] # Show assigned ponds

    pass

class HealthAssessment(BaseModel):
    """Pond health assessment schema (based on your analysis)"""
    pond_id: int
    overall_score: float = Field(..., ge=0, le=100)
    weighted_score: float = Field(..., ge=0, le=100)
    grade: str = Field(..., pattern=r'^(A\+|A|B\+|B|C\+|C|D|F|N/A)$')
    status: str = Field(..., max_length=20)
    
    # Individual parameter scores
    temperature_score: Optional[float] = Field(None, ge=0, le=100)
    ph_score: Optional[float] = Field(None, ge=0, le=100)
    dissolved_oxygen_score: Optional[float] = Field(None, ge=0, le=100)
    turbidity_score: Optional[float] = Field(None, ge=0, le=100)
    ammonia_score: Optional[float] = Field(None, ge=0, le=100)
    nitrate_score: Optional[float] = Field(None, ge=0, le=100)
    
    # Risk and recommendations
    risk_level: str = Field(..., pattern=r'^(Low|Medium|High)$')
    warning_count: int = Field(default=0, ge=0)
    critical_issues: List[str] = Field(default=[])
    recommendations: List[str] = Field(default=[])
    action_priority: Optional[str] = Field(None, pattern=r'^(Maintain|Monitor|Improve|Urgent)$')
    
    # Assessment metadata
    parameters_assessed: int = Field(..., ge=0)
    data_completeness: Optional[float] = Field(None, ge=0, le=100)
    assessment_confidence: Optional[float] = Field(None, ge=0, le=1)
    assessment_period_start: datetime
    assessment_period_end: datetime
    calculated_at: datetime


class HealthAssessmentCreate(BaseModel):
    """Schema for creating health assessments"""
    pond_id: int
    assessment_period_start: datetime
    assessment_period_end: datetime


class NotificationPreferences(BaseModel):
    """User notification preferences"""
    email_enabled: bool = True
    sms_enabled: bool = True
    push_enabled: bool = True
    
    # Severity preferences
    email_min_severity: AlertSeverity = AlertSeverity.WARNING
    sms_min_severity: AlertSeverity = AlertSeverity.CRITICAL
    push_min_severity: AlertSeverity = AlertSeverity.INFO
    
    # Timing preferences
    quiet_hours_start: Optional[int] = Field(None, ge=0, le=23, description="Quiet hours start (24h format)")
    quiet_hours_end: Optional[int] = Field(None, ge=0, le=23, description="Quiet hours end (24h format)")
    weekend_notifications: bool = True
    
    # Language preference
    language: str = Field(default="fr", pattern=r'^(fr|ar|en)$')


class DashboardSummary(BaseModel):
    """Dashboard summary data"""
    total_ponds: int
    active_ponds: int
    total_alerts: int
    critical_alerts: int
    warning_alerts: int
    
    # Health distribution
    excellent_ponds: int  # A+ and A grades
    good_ponds: int       # B+ and B grades
    fair_ponds: int       # C+ and C grades
    poor_ponds: int       # D and F grades
    
    # Recent activity
    recent_readings_count: int
    last_reading_timestamp: Optional[datetime]
    
    # System health
    data_quality_avg: Optional[float]
    connectivity_status: str = Field(default="online", pattern=r'^(online|offline|degraded)$')