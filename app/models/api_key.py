"""
API Key model for sensor authentication
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.core.security import get_password_hash, verify_password
import secrets


class PondAPIKey(Base):
    """
    API Key model for pond sensor data ingestion.
    Allows multiple API keys per user and per pond.
    """
    __tablename__ = "pond_api_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # Human-readable name for the key
    api_key_hash = Column(String, nullable=False)  # Hashed API key
    secret_key = Column(String, nullable=False)  # HMAC secret key
    
    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    pond_id = Column(Integer, ForeignKey("ponds.id"), nullable=False)
    
    # Status and metadata
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    last_used_at = Column(DateTime, nullable=True)
    usage_count = Column(Integer, default=0, nullable=False)
    
    # Optional restrictions
    expires_at = Column(DateTime, nullable=True)
    allowed_ip_ranges = Column(String, nullable=True)  # JSON string of IP ranges
    max_requests_per_hour = Column(Integer, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="api_keys")
    pond = relationship("Pond", back_populates="api_keys")

    def set_api_key(self, api_key: str):
        """Hash and set the API key."""
        self.api_key_hash = get_password_hash(api_key)

    def verify_api_key(self, api_key: str) -> bool:
        """Verify a given API key against the stored hash."""
        return verify_password(api_key, self.api_key_hash)

    def generate_secret_key(self) -> str:
        """Generate a new HMAC secret key."""
        self.secret_key = secrets.token_hex(32)
        return self.secret_key

    @classmethod
    def create_new_key(cls, user_id: int, pond_id: int, name: str) -> tuple:
        """
        Create a new API key instance with generated credentials.
        Returns (api_key_instance, raw_api_key)
        """
        # Generate raw API key
        raw_api_key = secrets.token_urlsafe(32)
        
        # Create instance
        api_key = cls(
            name=name,
            user_id=user_id,
            pond_id=pond_id
        )
        
        # Set credentials
        api_key.set_api_key(raw_api_key)
        api_key.generate_secret_key()
        
        return api_key, raw_api_key

    def update_usage(self):
        """Update usage statistics."""
        from datetime import datetime, timezone
        self.last_used_at = datetime.now(timezone.utc)
        self.usage_count += 1

    def is_valid(self) -> bool:
        """Check if the API key is valid (active, not expired, etc.)."""
        if not self.is_active:
            return False
        
        if self.expires_at:
            from datetime import datetime, timezone
            # Fix: Handle both timezone-aware and timezone-naive datetimes
            current_time = datetime.now(timezone.utc)
            expires_at = self.expires_at
            
            # If expires_at is timezone-naive, make it timezone-aware (assume UTC)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            if current_time > expires_at:
                return False
        
        return True

    def __repr__(self):
        return f"<PondAPIKey(id={self.id}, name='{self.name}', user_id={self.user_id}, pond_id={self.pond_id})>"