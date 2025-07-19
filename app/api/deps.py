"""
Dependency injection utilities
Common dependencies for API endpoints
"""

import hashlib
import hmac
import json
import time
from typing import Optional, Tuple
from fastapi import Depends, HTTPException, status, Query, Request, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError

from app.database import get_db
from app.models.pond import User, Pond, UserRole
from app.core.security import verify_token  # Now this import should work
from app.config import settings
from app.models.api_key import PondAPIKey


# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current user from JWT token
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Verify token
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception
    
    # Extract user ID
    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    try:
        user_id = int(user_id)
    except ValueError:
        raise credentials_exception
    
    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user (must be active and verified)
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Get current admin user (must be active, verified, and admin)
    """
    if not current_user.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    return current_user


def check_pond_ownership(
    pond_id: int,
    current_user: User,
    db: Session
) -> Pond:
    """
    Check if current user owns the specified pond
    """
    pond = db.query(Pond).filter(Pond.id == pond_id).first()
    
    if not pond:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pond not found"
        )
    
    if current_user.id not in pond.assigned_users and not current_user.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to access this pond"
        )
    
    return pond


# Fix the get_pagination_params function to return individual values

def get_pagination_params(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return")
) -> tuple[int, int]:  # This returns a tuple, causing the issue
    """Get pagination parameters with validation"""
    return skip, limit



def get_date_range_params(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
) -> Tuple[Optional[str], Optional[str]]:
    """
    Get date range parameters for filtering
    """
    return start_date, end_date


def get_sensor_type_filter(
    sensor_type: Optional[str] = Query(None, description="Filter by sensor type")
) -> Optional[str]:
    """
    Get sensor type filter parameter
    """
    if sensor_type:
        valid_types = ["temperature", "ph", "dissolved_oxygen", "turbidity", "ammonia", "nitrate"]
        if sensor_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sensor type. Must be one of: {', '.join(valid_types)}"
            )
    
    return sensor_type

async def get_pond_from_api_key(
    request: Request,
    x_api_key: str = Header(..., description="API key for pond access"),
    x_signature: str = Header(..., description="HMAC signature"),
    x_timestamp: str = Header(..., description="Request timestamp"),
    db: Session = Depends(get_db)
) -> Tuple[Pond, User, PondAPIKey, dict]:
    """
    Dependency to authenticate requests from sensors using an API key and HMAC signature.
    Returns the authenticated pond, the user who owns the API key, the API key record, and request payload.
    """
    # Check timestamp to prevent replay attacks (5 minute window)
    try:
        request_time = float(x_timestamp)
        current_time = time.time()
        if abs(current_time - request_time) > 300:  # 5 minutes
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Request timestamp is too old or from the future."
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid timestamp format."
        )

    # Get request body for signature verification
    body = await request.body()
    
    # Find ALL active API keys first, then check which one matches
    api_keys = db.query(PondAPIKey).join(
        Pond, PondAPIKey.pond_id == Pond.id
    ).join(
        User, PondAPIKey.user_id == User.id
    ).filter(
        PondAPIKey.is_active == True,
        Pond.is_active == True,
        User.is_active == True
    ).all()
    
    # Try to find the matching API key
    authenticated_api_key = None
    pond = None
    user = None
    print()
    for api_key_record in api_keys:
        if api_key_record.verify_api_key(x_api_key) and api_key_record.is_valid():
            authenticated_api_key = api_key_record
            pond = api_key_record.pond
            user = api_key_record.user
            break
    
    if not authenticated_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid API Key, expired, or associated resources are inactive"
        )

    # Verify HMAC signature
    message = x_timestamp.encode('utf-8') + b'.' + body
    expected_signature = hmac.new(
        authenticated_api_key.secret_key.encode('utf-8'),
        msg=message,
        digestmod=hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, x_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid signature"
        )

    # Update usage statistics
    authenticated_api_key.update_usage()
    db.commit()

    # Parse and return payload
    try:
        payload = json.loads(body.decode('utf-8')) if body else {}
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )

    return pond, user, authenticated_api_key, payload