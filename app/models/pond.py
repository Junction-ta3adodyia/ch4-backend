"""
Pond model - Represents fish ponds/tanks
Contains pond metadata, location, and configuration
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Pond(Base):
    """
    Pond/Tank model
    Represents individual fish farming ponds with their characteristics
    """
    __tablename__ = "ponds"
    
    # Primary identification
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, index=True)
    
    # Basic information
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Physical characteristics
    capacity = Column(Float, nullable=True, comment="Capacity in liters")
    depth = Column(Float, nullable=True, comment="Depth in meters")
    surface_area = Column(Float, nullable=True, comment="Surface area in square meters")
    
    # Location (can store GPS coordinates)
    location_name = Column(String(200), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # Fish information
    fish_species = Column(String(100), nullable=True)
    fish_count = Column(Integer, nullable=True, default=0)
    stocking_date = Column(DateTime, nullable=True)
    
    # System configuration
    aeration_system = Column(Boolean, default=False)
    filtration_system = Column(Boolean, default=False)
    heating_system = Column(Boolean, default=False)
    
    # Alert configuration (JSON field for flexible alert rules)
    alert_config = Column(JSONB, nullable=True, default={})
    
    # Owner/Manager information
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    manager_contact = Column(String(100), nullable=True)
    
    # Status and metadata
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    sensor_data = relationship("SensorData", back_populates="pond", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="pond", cascade="all, delete-orphan")
    health_records = relationship("PondHealth", back_populates="pond", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Pond(id={self.id}, name='{self.name}', active={self.is_active})>"


class User(Base):
    """
    User model for pond owners/managers
    Basic user management for the system
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, index=True)
    
    # Authentication
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    # Personal information
    first_name = Column(String(50), nullable=True)
    last_name = Column(String(50), nullable=True)
    phone_number = Column(String(20), nullable=True)
    organization = Column(String(100), nullable=True)  # Add this missing field
    
    # Preferences
    language = Column(String(5), default="fr")  # Default to French for Algeria
    timezone = Column(String(50), default="Africa/Algiers")
    
    # Notification preferences
    email_notifications = Column(Boolean, default=True)
    sms_notifications = Column(Boolean, default=True)
    push_notifications = Column(Boolean, default=True)
    
    # Status and permissions
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)  # Add this for admin checking
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    ponds = relationship("Pond", backref="owner")
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"