"""
API Key management endpoints
"""

from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.api.deps import get_db, get_current_active_user
from app.models.pond import User, UserRole, Pond
from app.models.api_key import PondAPIKey
from app.schemas.api_key import (
    APIKeyCreate, APIKeyResponse, APIKeyUpdate, APIKeyListResponse
)

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    api_key_data: APIKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Create a new API key for a specific user and pond.
    Only pond owners, assigned users, or admins can create keys.
    """
    # Get the pond
    pond = db.query(Pond).filter(Pond.id == api_key_data.pond_id).first()
    if not pond:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pond not found"
        )
    
    # Determine target user
    target_user_id = api_key_data.user_id if api_key_data.user_id else current_user.id
    target_user = db.query(User).filter(User.id == target_user_id, User.is_active == True).first()
    
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user not found or inactive"
        )
    
    # Check permissions
    can_create = (
        current_user.role == UserRole.ADMIN or
        pond.owner_id == current_user.id or
        (pond in current_user.assigned_ponds and target_user_id == current_user.id)
    )
    
    if not can_create:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to create API key"
        )
    
    # Check if target user has access to pond
    target_has_access = (
        target_user.role == UserRole.ADMIN or
        pond.owner_id == target_user.id or
        pond in target_user.assigned_ponds
    )
    
    if not target_has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User '{target_user.username}' does not have access to pond '{pond.name}'"
        )
    
    # Check for existing active API key for same user-pond combination
    existing_key = db.query(PondAPIKey).filter(
        PondAPIKey.user_id == target_user_id,
        PondAPIKey.pond_id == api_key_data.pond_id,
        PondAPIKey.name == api_key_data.name,
        PondAPIKey.is_active == True
    ).first()
    
    if existing_key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active API key with name '{api_key_data.name}' already exists for this user-pond combination"
        )
    
    # Create new API key
    api_key_record, raw_api_key = PondAPIKey.create_new_key(
        user_id=target_user_id,
        pond_id=api_key_data.pond_id,
        name=api_key_data.name
    )
    
    # Set optional fields
    if api_key_data.expires_at:
        api_key_record.expires_at = api_key_data.expires_at
    if api_key_data.max_requests_per_hour:
        api_key_record.max_requests_per_hour = api_key_data.max_requests_per_hour
    
    db.add(api_key_record)
    db.commit()
    db.refresh(api_key_record)
    
    return {
        "message": "API key created successfully",
        "api_key_id": api_key_record.id,
        "api_key": raw_api_key,
        "secret_key": api_key_record.secret_key,
        "name": api_key_record.name,
        "pond_id": pond.id,
        "pond_name": pond.name,
        "user_id": target_user.id,
        "username": target_user.username,
        "expires_at": api_key_record.expires_at.isoformat() if api_key_record.expires_at else None,
        "created_at": api_key_record.created_at.isoformat(),
        "warning": "Store these credentials securely. They will not be shown again."
    }


@router.get("/", response_model=List[APIKeyListResponse])
async def list_api_keys(
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    pond_id: Optional[int] = Query(None, description="Filter by pond ID"),
    include_inactive: bool = Query(False, description="Include inactive keys"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    List API keys. Users can see their own keys, pond owners can see all keys for their ponds,
    admins can see all keys.
    """
    base_query = db.query(PondAPIKey).join(Pond).join(User)
    
    # Apply role-based filtering
    if current_user.role != UserRole.ADMIN:
        # Non-admins can only see keys for ponds they own or are assigned to
        accessible_pond_ids = [p.id for p in current_user.owned_ponds + current_user.assigned_ponds]
        base_query = base_query.filter(PondAPIKey.pond_id.in_(accessible_pond_ids))
        
        # And only their own keys unless they own the pond
        if user_id and user_id != current_user.id:
            owned_pond_ids = [p.id for p in current_user.owned_ponds]
            base_query = base_query.filter(
                and_(
                    PondAPIKey.user_id == user_id,
                    PondAPIKey.pond_id.in_(owned_pond_ids)
                )
            )
    
    # Apply filters
    if user_id:
        base_query = base_query.filter(PondAPIKey.user_id == user_id)
    if pond_id:
        base_query = base_query.filter(PondAPIKey.pond_id == pond_id)
    if not include_inactive:
        base_query = base_query.filter(PondAPIKey.is_active == True)
    
    api_keys = base_query.order_by(desc(PondAPIKey.created_at)).all()
    
    return [
        APIKeyListResponse(
            id=key.id,
            name=key.name,
            pond_id=key.pond_id,
            pond_name=key.pond.name,
            user_id=key.user_id,
            username=key.user.username,
            is_active=key.is_active,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            usage_count=key.usage_count,
            expires_at=key.expires_at
        )
        for key in api_keys
    ]


@router.get("/{api_key_id}", response_model=APIKeyResponse)
async def get_api_key(
    api_key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get details of a specific API key"""
    api_key = db.query(PondAPIKey).filter(PondAPIKey.id == api_key_id).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Check permissions
    can_view = (
        current_user.role == UserRole.ADMIN or
        api_key.user_id == current_user.id or
        api_key.pond.owner_id == current_user.id or
        api_key.pond in current_user.assigned_ponds
    )
    
    if not can_view:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view this API key"
        )
    
    return api_key


@router.put("/{api_key_id}")
async def update_api_key(
    api_key_id: int,
    update_data: APIKeyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update an API key"""
    api_key = db.query(PondAPIKey).filter(PondAPIKey.id == api_key_id).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Check permissions
    can_update = (
        current_user.role == UserRole.ADMIN or
        api_key.pond.owner_id == current_user.id
    )
    
    if not can_update:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update this API key"
        )
    
    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(api_key, field, value)
    
    db.commit()
    db.refresh(api_key)
    
    return {
        "message": "API key updated successfully",
        "api_key_id": api_key.id,
        "updated_fields": list(update_dict.keys())
    }


@router.delete("/{api_key_id}")
async def delete_api_key(
    api_key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete (deactivate) an API key"""
    api_key = db.query(PondAPIKey).filter(PondAPIKey.id == api_key_id).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Check permissions
    can_delete = (
        current_user.role == UserRole.ADMIN or
        api_key.user_id == current_user.id or
        api_key.pond.owner_id == current_user.id
    )
    
    if not can_delete:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to delete this API key"
        )
    
    # Soft delete (deactivate)
    api_key.is_active = False
    db.commit()
    
    return {
        "message": "API key deactivated successfully",
        "api_key_id": api_key.id
    }


@router.post("/{api_key_id}/regenerate")
async def regenerate_api_key(
    api_key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Regenerate credentials for an existing API key"""
    api_key = db.query(PondAPIKey).filter(PondAPIKey.id == api_key_id).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Check permissions
    can_regenerate = (
        current_user.role == UserRole.ADMIN or
        api_key.pond.owner_id == current_user.id
    )
    
    if not can_regenerate:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to regenerate this API key"
        )
    
    # Generate new credentials
    import secrets
    new_raw_key = secrets.token_urlsafe(32)
    api_key.set_api_key(new_raw_key)
    api_key.generate_secret_key()
    api_key.usage_count = 0  # Reset usage count
    api_key.last_used_at = None
    
    db.commit()
    
    return {
        "message": "API key regenerated successfully",
        "api_key_id": api_key.id,
        "api_key": new_raw_key,
        "secret_key": api_key.secret_key,
        "warning": "Update your sensors with the new credentials. Old credentials are now invalid."
    }