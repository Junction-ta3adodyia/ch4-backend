"""
API Key schemas
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Human-readable name for the API key")
    pond_id: int = Field(..., description="ID of the pond this key will access")
    user_id: Optional[int] = Field(None, description="User ID to assign the key to (defaults to current user)")
    expires_at: Optional[datetime] = Field(None, description="Optional expiration date")
    max_requests_per_hour: Optional[int] = Field(None, ge=1, le=10000, description="Rate limit")


class APIKeyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None
    max_requests_per_hour: Optional[int] = Field(None, ge=1, le=10000)


class APIKeyResponse(BaseModel):
    id: int
    name: str
    pond_id: int
    user_id: int
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    usage_count: int
    expires_at: Optional[datetime]
    max_requests_per_hour: Optional[int]

    class Config:
        from_attributes = True


class APIKeyListResponse(BaseModel):
    id: int
    name: str
    pond_id: int
    pond_name: str
    user_id: int
    username: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime]
    usage_count: int
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True