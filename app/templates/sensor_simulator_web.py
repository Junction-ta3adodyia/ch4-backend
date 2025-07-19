"""
Simulation Manager - Web interface for managing sensor simulations
"""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_db, get_current_active_user
from app.models.pond import User, Pond
from app.models.api_key import PondAPIKey

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def simulation_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Simulation management dashboard"""
    
    # Get accessible ponds and their API keys
    if current_user.role.value == 'admin':
        ponds = db.query(Pond).filter(Pond.is_active == True).all()
    else:
        ponds = current_user.owned_ponds + current_user.assigned_ponds
    
    pond_data = []
    for pond in ponds:
        api_keys = db.query(PondAPIKey).filter(
            PondAPIKey.pond_id == pond.id,
            PondAPIKey.is_active == True
        ).all()
        
        pond_data.append({
            'pond': pond,
            'api_keys': api_keys
        })
    
    return templates.TemplateResponse("simulation_dashboard.html", {
        "request": request,
        "current_user": current_user,
        "pond_data": pond_data
    })