"""
Sensor simulation management endpoints
"""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import get_db, get_current_active_user
from app.models.pond import User, UserRole, Pond
from app.models.api_key import PondAPIKey
from app.services.sensor_simulator import AquacultureSensorSimulator, SimulationScenario

router = APIRouter()

# Global simulation registry
active_simulations: Dict[str, Dict[str, Any]] = {}


class SimulationConfig(BaseModel):
    pond_id: int
    api_key_id: int
    duration_seconds: int = Field(default=300, ge=30, le=7200, description="Simulation duration (30s to 2h)")
    interval_seconds: int = Field(default=10, ge=1, le=60, description="Reading interval (1-60s)")
    scenario: SimulationScenario = Field(default=SimulationScenario.NORMAL, description="Simulation scenario")
    scenario_settings: Optional[Dict[str, Any]] = Field(default={}, description="Scenario-specific settings")


class SimulationStatus(BaseModel):
    simulation_id: str
    pond_id: int
    pond_name: str
    status: str
    scenario: str
    started_at: datetime
    duration_seconds: int
    readings_sent: int
    successful_readings: int
    last_reading_at: Optional[datetime]


@router.post("/start")
async def start_simulation(
    config: SimulationConfig,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Start a new sensor simulation"""
    
    # Verify API key and permissions
    api_key = db.query(PondAPIKey).filter(
        PondAPIKey.id == config.api_key_id,
        PondAPIKey.is_active == True
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or inactive"
        )
    
    if api_key.pond_id != config.pond_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key does not belong to the specified pond"
        )
    
    # Check permissions
    pond = api_key.pond
    can_simulate = (
        current_user.role == UserRole.ADMIN or
        pond.owner_id == current_user.id or
        pond in current_user.assigned_ponds or
        api_key.user_id == current_user.id
    )
    
    if not can_simulate:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to start simulation"
        )
    
    # Check if simulation already running for this pond
    simulation_id = f"pond_{config.pond_id}_{int(datetime.now().timestamp())}"
    existing_sim = next((sim for sim in active_simulations.values() 
                        if sim['pond_id'] == config.pond_id and sim['status'] == 'running'), None)
    
    if existing_sim:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Simulation already running for pond {config.pond_id}"
        )
    
    # Create simulation record
    simulation_record = {
        'simulation_id': simulation_id,
        'pond_id': config.pond_id,
        'pond_name': pond.name,
        'status': 'starting',
        'scenario': config.scenario.value,
        'started_at': datetime.now(timezone.utc),
        'duration_seconds': config.duration_seconds,
        'readings_sent': 0,
        'successful_readings': 0,
        'last_reading_at': None,
        'api_key': api_key,
        'config': config
    }
    
    active_simulations[simulation_id] = simulation_record
    
    # Start simulation in background
    background_tasks.add_task(
        run_simulation_task,
        simulation_id,
        config,
        api_key
    )
    
    return {
        "message": "Simulation started successfully",
        "simulation_id": simulation_id,
        "pond_id": config.pond_id,
        "pond_name": pond.name,
        "duration_seconds": config.duration_seconds,
        "scenario": config.scenario.value,
        "estimated_readings": config.duration_seconds // config.interval_seconds
    }


@router.get("/", response_model=List[SimulationStatus])
async def list_simulations(
    pond_id: Optional[int] = None,
    include_completed: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List active and recent simulations"""
    
    simulations = []
    
    for sim_data in active_simulations.values():
        # Check permissions
        if current_user.role != UserRole.ADMIN:
            pond = db.query(Pond).filter(Pond.id == sim_data['pond_id']).first()
            if not pond:
                continue
            
            can_view = (
                pond.owner_id == current_user.id or
                pond in current_user.assigned_ponds or
                sim_data['api_key'].user_id == current_user.id
            )
            
            if not can_view:
                continue
        
        # Apply filters
        if pond_id and sim_data['pond_id'] != pond_id:
            continue
        
        if not include_completed and sim_data['status'] in ['completed', 'failed']:
            continue
        
        simulations.append(SimulationStatus(
            simulation_id=sim_data['simulation_id'],
            pond_id=sim_data['pond_id'],
            pond_name=sim_data['pond_name'],
            status=sim_data['status'],
            scenario=sim_data['scenario'],
            started_at=sim_data['started_at'],
            duration_seconds=sim_data['duration_seconds'],
            readings_sent=sim_data['readings_sent'],
            successful_readings=sim_data['successful_readings'],
            last_reading_at=sim_data['last_reading_at']
        ))
    
    return sorted(simulations, key=lambda x: x.started_at, reverse=True)


@router.get("/{simulation_id}", response_model=SimulationStatus)
async def get_simulation(
    simulation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get details of a specific simulation"""
    
    if simulation_id not in active_simulations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Simulation not found"
        )
    
    sim_data = active_simulations[simulation_id]
    
    # Check permissions
    if current_user.role != UserRole.ADMIN:
        pond = db.query(Pond).filter(Pond.id == sim_data['pond_id']).first()
        can_view = (
            pond and (
                pond.owner_id == current_user.id or
                pond in current_user.assigned_ponds or
                sim_data['api_key'].user_id == current_user.id
            )
        )
        
        if not can_view:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to view this simulation"
            )
    
    return SimulationStatus(
        simulation_id=sim_data['simulation_id'],
        pond_id=sim_data['pond_id'],
        pond_name=sim_data['pond_name'],
        status=sim_data['status'],
        scenario=sim_data['scenario'],
        started_at=sim_data['started_at'],
        duration_seconds=sim_data['duration_seconds'],
        readings_sent=sim_data['readings_sent'],
        successful_readings=sim_data['successful_readings'],
        last_reading_at=sim_data['last_reading_at']
    )


@router.post("/{simulation_id}/stop")
async def stop_simulation(
    simulation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Stop a running simulation"""
    
    if simulation_id not in active_simulations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Simulation not found"
        )
    
    sim_data = active_simulations[simulation_id]
    
    # Check permissions
    if current_user.role != UserRole.ADMIN:
        pond = db.query(Pond).filter(Pond.id == sim_data['pond_id']).first()
        can_stop = (
            pond and (
                pond.owner_id == current_user.id or
                sim_data['api_key'].user_id == current_user.id
            )
        )
        
        if not can_stop:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to stop this simulation"
            )
    
    if sim_data['status'] != 'running':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot stop simulation with status: {sim_data['status']}"
        )
    
    # Mark for stopping
    sim_data['status'] = 'stopping'
    
    return {
        "message": "Simulation stop requested",
        "simulation_id": simulation_id,
        "status": "stopping"
    }


async def run_simulation_task(simulation_id: str, config: SimulationConfig, api_key: PondAPIKey):
    """Background task to run the simulation"""
    
    sim_data = active_simulations[simulation_id]
    
    try:
        sim_data['status'] = 'running'
        
        # Create simulator instance
        simulator = AquacultureSensorSimulator(
            base_url="http://127.0.0.1:8000",  # Adjust as needed
            api_key="_nTKh7X_JtMF3bXYUe1bLTbVKNjk6EBML5hCeMNROpg",  # This should be the raw key, not hash
            secret_key="0141924a12c7738589c6ed5384d899d5cec9958a5c3a266bd4fa418e9c7b0ff4",
            pond_id=config.pond_id
        )
        
        # Set scenario
        simulator.set_scenario(config.scenario, **config.scenario_settings)
        
        async with simulator:
            # Run simulation with periodic status updates
            end_time = datetime.now().timestamp() + config.duration_seconds
            
            while datetime.now().timestamp() < end_time and sim_data['status'] == 'running':
                reading = simulator._generate_sensor_reading()
                success = await simulator.send_reading(reading)
                
                # Update simulation status
                sim_data['readings_sent'] = simulator.readings_sent
                sim_data['successful_readings'] = simulator.successful_readings
                sim_data['last_reading_at'] = datetime.now(timezone.utc)
                
                # Check if stop was requested
                if sim_data['status'] == 'stopping':
                    break
                
                await asyncio.sleep(config.interval_seconds)
        
        # Mark as completed
        if sim_data['status'] != 'stopping':
            sim_data['status'] = 'completed'
        else:
            sim_data['status'] = 'stopped'
            
    except Exception as e:
        sim_data['status'] = 'failed'
        sim_data['error'] = str(e)
        print(f"❌ Simulation {simulation_id} failed: {e}")


@router.get("/scenarios/list")
async def list_scenarios():
    """List available simulation scenarios"""
    
    scenarios = []
    for scenario in SimulationScenario:
        description = {
            SimulationScenario.NORMAL: "Normal operating conditions with natural variations",
            SimulationScenario.STRESS_TEST: "High-frequency readings to test system capacity",
            SimulationScenario.ANOMALY_INJECTION: "Intentionally inject anomalies for testing detection",
            SimulationScenario.DAILY_CYCLE: "24-hour cycle with realistic daily variations",
            SimulationScenario.EQUIPMENT_FAILURE: "Simulate equipment failures (aerator, heater, etc.)",
            SimulationScenario.FEEDING_TIME: "Simulate feeding time effects on water quality",
            SimulationScenario.WEATHER_STORM: "Simulate storm impact on pond conditions"
        }.get(scenario, "No description available")
        
        scenarios.append({
            "name": scenario.value,
            "display_name": scenario.value.replace('_', ' ').title(),
            "description": description
        })
    
    return scenarios