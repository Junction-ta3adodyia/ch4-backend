from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List

from app.database import get_db
from app.models.pond import User, Pond, UserRole
from app.schemas import pond as pond_schemas
from app.api.deps import get_current_active_user
from app.core.health_calculator import calculate_pond_health

router = APIRouter(prefix="/users", tags=["User Management"])

def get_current_active_admin(current_user: User = Depends(get_current_active_user)):
    """Dependency to check if the current user is an admin."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user

def convert_user_to_response(user: User, db: Session) -> pond_schemas.UserResponse:
    """
    Helper function to correctly convert a User model to a UserResponse schema,
    handling the nested PondSummary conversion.
    """
    assigned_ponds_summary = []
    for p in user.assigned_ponds:
        # Calculate health score and grade using the helper
        health_data = calculate_pond_health(pond_id=p.id, db=db)
        
        health_score = health_data["overall_score"] if health_data else 'N/A'
        health_grade = health_data["grade"] if health_data else "N/A"

        # This assumes your Alert model has an 'is_active' boolean field.
        active_alerts_count = sum(1 for alert in p.alerts if alert.status == "active")
        
        summary = pond_schemas.PondSummary(
            id=p.id,
            name=p.name,
            health_score=health_score,
            health_grade=health_grade,
            status="Active" if p.is_active else "Inactive",
            active_alerts_count=active_alerts_count,
            last_updated=p.updated_at
        )
        assigned_ponds_summary.append(summary)
    
    user_data = pond_schemas.UserInDB.from_orm(user).dict()
    
    user_response = pond_schemas.UserResponse(
        **user_data,
        assigned_ponds=assigned_ponds_summary
    )
    return user_response


@router.get("/", response_model=List[pond_schemas.UserResponse], dependencies=[Depends(get_current_active_admin)])
def get_all_users(db: Session = Depends(get_db), skip: int = 0, limit: int = 100):
    """
    Retrieve all users. (Admin only)
    """
    # Eager load all necessary relationships to prevent N+1 query issues
    users = db.query(User).options(
        joinedload(User.assigned_ponds).subqueryload(Pond.alerts),
        joinedload(User.assigned_ponds).subqueryload(Pond.sensor_data)
    ).offset(skip).limit(limit).all()
    
    return [convert_user_to_response(user, db) for user in users]


@router.post("/{user_id}/assign-pond/{pond_id}", response_model=pond_schemas.UserResponse, dependencies=[Depends(get_current_active_admin)])
def assign_pond_to_user(user_id: int, pond_id: int, db: Session = Depends(get_db)):
    """
    Assign a pond to a user. (Admin only)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    pond = db.query(Pond).filter(Pond.id == pond_id).first()
    if not pond:
        raise HTTPException(status_code=404, detail="Pond not found")

    if pond not in user.assigned_ponds:
        user.assigned_ponds.append(pond)
        db.commit()
    
    # Re-query the user with all relationships loaded for the response
    user_for_response = db.query(User).options(
        joinedload(User.assigned_ponds).subqueryload(Pond.alerts),
        joinedload(User.assigned_ponds).subqueryload(Pond.sensor_data)
    ).filter(User.id == user_id).first()
    
    return convert_user_to_response(user_for_response, db)

@router.delete("/{user_id}/unassign-pond/{pond_id}", response_model=pond_schemas.UserResponse, dependencies=[Depends(get_current_active_admin)])
def unassign_pond_from_user(user_id: int, pond_id: int, db: Session = Depends(get_db)):
    """
    Unassign a pond from a user. (Admin only)
    """
    user = db.query(User).options(joinedload(User.assigned_ponds)).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    pond = db.query(Pond).filter(Pond.id == pond_id).first()
    if not pond:
        raise HTTPException(status_code=404, detail="Pond not found")

    if pond in user.assigned_ponds:
        user.assigned_ponds.remove(pond)
        db.commit()

    # Re-query the user with all relationships loaded for the response
    user_for_response = db.query(User).options(
        joinedload(User.assigned_ponds).subqueryload(Pond.alerts),
        joinedload(User.assigned_ponds).subqueryload(Pond.sensor_data)
    ).filter(User.id == user_id).first()

    return convert_user_to_response(user_for_response, db)