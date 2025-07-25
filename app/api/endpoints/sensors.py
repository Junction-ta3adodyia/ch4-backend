"""
Sensor data endpoints
Handle sensor data collection, validation, and storage
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import and_, desc, func

from app.api.deps import get_db, get_current_active_user, get_pond_from_api_key
from app.models.api_key import PondAPIKey
from app.models.pond import User, UserRole # Import UserRole
from app.models.pond import Pond
from app.models.sensor import SensorData
from app.schemas.sensor import (
    SensorDataCreate, 
    SensorDataResponse, 
    SensorDataBulkCreate,
    SensorDataQuery,
    SensorDataUpdate
)
from app.services.data_processor import (
    validate_sensor_data, 
    detect_anomalies,
    process_sensor_data_batch
)
from app.services.data_processor import process_sensor_alerts
import uuid
from app.services.alert_service import send_anomaly_alert_notification
from app.models.alert import Alert
from app.database import SessionLocal

router = APIRouter()


# Update the main sensor endpoint with better error tracking
@router.post("/data", response_model=SensorDataResponse, status_code=status.HTTP_201_CREATED)
async def add_sensor_data(
    sensor_data: SensorDataCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create new sensor data reading with anomaly detection and alerts"""
    
    try:
        print(f"🔍 Processing sensor data for pond {sensor_data.pond_id}")
        if current_user.role == UserRole.ADMIN:
            print(f"👤 User {current_user.username} is an admin, proceeding with data submission")
            # Verify pond access
            pond = db.query(Pond).filter(
                Pond.id == sensor_data.pond_id,
            ).first()
        else:
            # Verify pond access
            pond = db.query(Pond).filter(
                Pond.id == sensor_data.pond_id,
                Pond.assigned_users.any(id=current_user.id)
            ).first()
        
        if not pond:
            print(f"⚠️  Pond {sensor_data.pond_id} not found or no permission for user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pond not found or you don't have permission to add data to this pond"
            )
        
        print(f"✅ Pond access verified for user '{current_user.username}' on pond '{pond.name}'")
        
        # Validate sensor data quality
        quality_score = validate_sensor_data(sensor_data)
        print(f"📊 Data quality score: {quality_score}")
        
        # Detect anomalies with Page-Hinkley method
        is_anomaly = False
        anomaly_alert_id = None
        
        try:
            print("🔍 Running Page-Hinkley anomaly detection...")
            from app.services.page_hinkley import page_hinkley_service
            
            # Run anomaly detection with alert creation
            anomaly_results = await page_hinkley_service.detect_anomaly_with_alerts(
                sensor_data.pond_id, sensor_data, db
            )
            
            is_anomaly = anomaly_results['is_anomaly']
            anomaly_alert_id = anomaly_results.get('alert_id')
            
            if is_anomaly:
                print(f"🚨 ANOMALY DETECTED in Pond {sensor_data.pond_id}")
                print(f"   Anomaly Score: {anomaly_results['anomaly_score']:.3f}")
                print(f"   Change Points: {anomaly_results['change_points_detected']}")
                if anomaly_alert_id:
                    print(f"   Alert Created: ID {anomaly_alert_id}")
            else:
                print("✅ No anomaly detected")
            
        except Exception as anomaly_error:
            print(f"❌ Anomaly detection failed: {anomaly_error}")
            import traceback
            traceback.print_exc()
        
        # Create database record
        print("💾 Creating sensor data record...")
        db_sensor_data = SensorData(
            pond_id=sensor_data.pond_id,
            timestamp=sensor_data.timestamp,
            temperature=sensor_data.temperature,
            ph=sensor_data.ph,
            dissolved_oxygen=sensor_data.dissolved_oxygen,
            turbidity=sensor_data.turbidity,
            ammonia=sensor_data.ammonia,
            nitrate=sensor_data.nitrate,
            nitrite=sensor_data.nitrite,
            salinity=sensor_data.salinity,
            fish_count=sensor_data.fish_count,
            fish_length=sensor_data.fish_length,
            fish_weight=sensor_data.fish_weight,
            water_level=sensor_data.water_level,
            flow_rate=sensor_data.flow_rate,
            data_source=sensor_data.data_source,
            quality_score=quality_score,
            is_anomaly=is_anomaly,
            entry_id=str(uuid.uuid4()),
            notes=sensor_data.notes
        )
        
        db.add(db_sensor_data)
        db.commit()
        db.refresh(db_sensor_data)
        print(f"✅ Sensor data saved with ID: {db_sensor_data.id}")
        
        # If anomaly was detected and alert created, send email notification
        if is_anomaly and anomaly_alert_id:
            print(f"📧 Scheduling email notification for alert {anomaly_alert_id}")
            background_tasks.add_task(
                send_anomaly_email_notification,
                anomaly_alert_id,
                db_session_factory=SessionLocal
            )
        
        # Process regular sensor alerts in background
        print("🔔 Scheduling alert processing...")
        background_tasks.add_task(
            process_sensor_alerts, 
            sensor_data.pond_id, 
            db_sensor_data.id
        )
        
        print("✅ Request completed successfully")
        return db_sensor_data
        
    except Exception as e:
        print(f"❌ Unexpected error in add_sensor_data: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


async def send_anomaly_email_notification(alert_id: int, db_session_factory):
    """Background task to send anomaly email notification"""
    db = db_session_factory()
    try:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            print(f"📧 Sending email notification for alert {alert_id}")
            from app.services.alert_service import send_anomaly_alert_notification
            success = await send_anomaly_alert_notification(alert, db)
            if success:
                print(f"✅ Email notification sent successfully for alert {alert_id}")
            else:
                print(f"❌ Failed to send email notification for alert {alert_id}")
        else:
            print(f"⚠️  Alert {alert_id} not found for email notification")
    except Exception as e:
        print(f"❌ Error in background email task for alert {alert_id}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


@router.post("/data/batch", status_code=status.HTTP_201_CREATED)
async def add_sensor_data_batch(
    batch_data: SensorDataBulkCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create multiple sensor data readings in batch"""
    
    created_records = []
    errors = []
    
    try:
        # Process batch validation first
        batch_results = await process_sensor_data_batch(batch_data.readings, db)
        
        # Verify pond access for all ponds in batch
        pond_ids = list(set(reading.pond_id for reading in batch_data.readings))
        accessible_ponds = db.query(Pond.id).filter(
            Pond.id.in_(pond_ids),
            Pond.assigned_users.any(id=current_user.id)
        ).all()
        
        accessible_pond_ids = {pond.id for pond in accessible_ponds}
        
        for i, sensor_data in enumerate(batch_data.readings):
            try:
                # Check pond access
                if sensor_data.pond_id not in accessible_pond_ids:
                    errors.append(f"Reading {i}: Pond {sensor_data.pond_id} not found or no permission")
                    continue
                
                # Get quality score from batch processing
                quality_score = batch_results["quality_scores"][i] if i < len(batch_results["quality_scores"]) else 0.8
                
                # Create database record
                db_sensor_data = SensorData(
                    pond_id=sensor_data.pond_id,
                    timestamp=sensor_data.timestamp,
                    temperature=sensor_data.temperature,
                    ph=sensor_data.ph,
                    dissolved_oxygen=sensor_data.dissolved_oxygen,
                    turbidity=sensor_data.turbidity,
                    ammonia=sensor_data.ammonia,
                    nitrate=sensor_data.nitrate,
                    nitrite=sensor_data.nitrite,
                    salinity=sensor_data.salinity,
                    fish_count=sensor_data.fish_count,
                    fish_length=sensor_data.fish_length,
                    fish_weight=sensor_data.fish_weight,
                    water_level=sensor_data.water_level,
                    flow_rate=sensor_data.flow_rate,
                    data_source=sensor_data.data_source,
                    quality_score=quality_score,
                    is_anomaly=False,  # Set to False for batch, process later
                    entry_id=str(uuid.uuid4()),
                    notes=sensor_data.notes
                )
                
                db.add(db_sensor_data)
                created_records.append(db_sensor_data)
                
            except Exception as e:
                errors.append(f"Reading {i}: {str(e)}")
        
        # Commit all successful records
        if created_records:
            db.commit()
            
            # Refresh all created records
            for record in created_records:
                db.refresh(record)
            
            # Process alerts for all ponds in background
            for pond_id in accessible_pond_ids:
                background_tasks.add_task(
                    process_sensor_alerts, 
                    pond_id, 
                    None  # Process all recent data for the pond
                )
        
        return {
            "created": len(created_records),
            "errors": errors,
            "batch_analysis": batch_results,
            "success": len(created_records) > 0
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch processing error: {str(e)}"
        )

@router.get("/data", response_model=List[SensorDataResponse])
async def get_sensor_data(
    query: SensorDataQuery = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get sensor data with filtering and pagination"""
    
    try:
        # Base query for ponds the user is assigned to
        base_query = db.query(SensorData).join(Pond).filter(
            Pond.assigned_users.any(id=current_user.id)
        )
        
        # Apply filters
        if query.pond_id:
            base_query = base_query.filter(SensorData.pond_id == query.pond_id)
        
        if query.start_date:
            base_query = base_query.filter(SensorData.timestamp >= query.start_date)
        
        if query.end_date:
            base_query = base_query.filter(SensorData.timestamp <= query.end_date)
        
        if not query.include_anomalies:
            base_query = base_query.filter(SensorData.is_anomaly == False)
        
        # Apply ordering
        if query.order_direction == "desc":
            base_query = base_query.order_by(desc(getattr(SensorData, query.order_by)))
        else:
            base_query = base_query.order_by(getattr(SensorData, query.order_by))
        
        # Apply pagination
        sensor_data = base_query.offset(query.offset).limit(query.limit).all()
        
        return sensor_data
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving sensor data: {str(e)}"
        )


@router.get("/data/{sensor_id}", response_model=SensorDataResponse)
async def get_sensor_data_by_id(
    sensor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get specific sensor data by ID"""
    
    sensor_data = db.query(SensorData).join(Pond).filter(
        SensorData.id == sensor_id,
        Pond.assigned_users.any(id=current_user.id)
    ).first()
    
    if not sensor_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sensor data not found or no permission"
        )
    
    return sensor_data


@router.put("/data/{sensor_id}", response_model=SensorDataResponse)
async def update_sensor_data(
    sensor_id: int,
    sensor_update: SensorDataUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update sensor data"""
    
    try:
        # Get sensor data with access check
        sensor_data = db.query(SensorData).join(Pond).filter(
            SensorData.id == sensor_id,
            Pond.assigned_users.any(id=current_user.id)
        ).first()
        
        if not sensor_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sensor data not found or no permission"
            )
        
        # Update fields
        update_data = sensor_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(sensor_data, field, value)
        
        # Recalculate quality score if data parameters changed
        parameter_fields = {'temperature', 'ph', 'dissolved_oxygen', 'turbidity', 'ammonia', 'nitrate'}
        if any(field in update_data for field in parameter_fields):
            # Create a temporary schema object for validation
            from app.schemas.sensor import SensorDataCreate
            temp_data = SensorDataCreate(
                pond_id=sensor_data.pond_id,
                timestamp=sensor_data.timestamp,
                temperature=sensor_data.temperature,
                ph=sensor_data.ph,
                dissolved_oxygen=sensor_data.dissolved_oxygen,
                turbidity=sensor_data.turbidity,
                ammonia=sensor_data.ammonia,
                nitrate=sensor_data.nitrate,
                data_source=sensor_data.data_source
            )
            sensor_data.quality_score = validate_sensor_data(temp_data)
        
        db.commit()
        db.refresh(sensor_data)
        
        return sensor_data
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating sensor data: {str(e)}"
        )


@router.delete("/data/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sensor_data(
    sensor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete sensor data"""
    
    try:
        # Check access before deleting
        sensor_data = db.query(SensorData).join(Pond).filter(
            SensorData.id == sensor_id,
            Pond.assigned_users.any(id=current_user.id)
        ).first()
        
        if not sensor_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sensor data not found or no permission"
            )
        
        db.delete(sensor_data)
        db.commit()
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting sensor data: {str(e)}"
        )
    

# Add this to your sensors.py router
@router.get("/pond/{pond_id}/anomaly-detector-status")
async def get_anomaly_detector_status(
    pond_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get Page-Hinkley detector status for a pond"""
    
    if current_user.role != UserRole.ADMIN:
        # Verify pond access
        pond = db.query(Pond).filter(
            Pond.id == pond_id,
            Pond.assigned_users.any(id=current_user.id)
        ).first()
    else:
        # Admins can access all ponds
        pond = db.query(Pond).filter(Pond.id == pond_id).first()

    print(f"🔍 Checking anomaly detector status for pond {pond_id} by user {current_user.username}")
    
    if not pond:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pond not found or no permission"
        )
    
    from app.services.page_hinkley import get_page_hinkley_diagnostics
    diagnostics = get_page_hinkley_diagnostics(pond_id)
    
    return {
        "pond_id": pond_id,
        "pond_name": pond.name,
        "detector_status": diagnostics,
        "timestamp": datetime.now(timezone.utc)
    }

@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_sensor_data(
    background_tasks: BackgroundTasks,
    auth_data: Tuple[Pond, User, 'PondAPIKey', dict] = Depends(get_pond_from_api_key),
    db: Session = Depends(get_db)
):
    """
    Ingest sensor data from authenticated sensors using API Key + HMAC authentication.
    This endpoint is specifically designed for IoT devices and sensor networks.
    """
    pond, api_key_user, api_key_record, payload = auth_data
    
    try:
        print(f"🔒 Secure sensor data ingestion for pond: {pond.name} (ID: {pond.id})")
        print(f"👤 API key '{api_key_record.name}' belongs to user: {api_key_user.username} (ID: {api_key_user.id})")
        
        # Validate payload structure
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty payload"
            )
        
        # Ensure pond_id matches authenticated pond
        if 'pond_id' in payload and payload['pond_id'] != pond.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pond ID in payload does not match authenticated pond"
            )
        
        # Set pond_id if not provided
        payload['pond_id'] = pond.id
        
        # Create sensor data schema
        try:
            sensor_data = SensorDataCreate(**payload)
        except Exception as validation_error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid sensor data: {str(validation_error)}"
            )

        # Validate sensor data quality
        quality_score = validate_sensor_data(sensor_data)
        print(f"📊 Data quality score: {quality_score}")

        # Detect anomalies with Page-Hinkley method
        is_anomaly = False
        anomaly_alert_id = None
        
        try:
            print("🔍 Running Page-Hinkley anomaly detection...")
            from app.services.page_hinkley import page_hinkley_service
            
            anomaly_results = await page_hinkley_service.detect_anomaly_with_alerts(
                sensor_data.pond_id, sensor_data, db
            )
            
            is_anomaly = anomaly_results['is_anomaly']
            anomaly_alert_id = anomaly_results.get('alert_id')
            
            if is_anomaly:
                print(f"🚨 ANOMALY DETECTED in Pond {sensor_data.pond_id}")
                print(f"   Anomaly Score: {anomaly_results['anomaly_score']:.3f}")
                print(f"   Change Points: {anomaly_results['change_points_detected']}")
            else:
                print("✅ No anomaly detected")
                
        except Exception as anomaly_error:
            print(f"❌ Anomaly detection failed: {anomaly_error}")
            # Continue processing even if anomaly detection fails

        # Create database record
        print("💾 Creating sensor data record...")
        db_sensor_data = SensorData(
            pond_id=sensor_data.pond_id,
            timestamp=sensor_data.timestamp,
            temperature=sensor_data.temperature,
            ph=sensor_data.ph,
            dissolved_oxygen=sensor_data.dissolved_oxygen,
            turbidity=sensor_data.turbidity,
            ammonia=sensor_data.ammonia,
            nitrate=sensor_data.nitrate,
            nitrite=sensor_data.nitrite,
            salinity=sensor_data.salinity,
            fish_count=sensor_data.fish_count,
            fish_length=sensor_data.fish_length,
            fish_weight=sensor_data.fish_weight,
            water_level=sensor_data.water_level,
            flow_rate=sensor_data.flow_rate,
            data_source=sensor_data.data_source or "sensor",
            quality_score=quality_score,
            is_anomaly=is_anomaly,
            entry_id=str(uuid.uuid4()),
            notes=sensor_data.notes,
            api_key_id=api_key_record.id  # Track which API key was used
        )

        db.add(db_sensor_data)
        db.commit()
        db.refresh(db_sensor_data)
        print(f"✅ Sensor data saved with ID: {db_sensor_data.id}")

        # Send email notification if anomaly detected
        if is_anomaly and anomaly_alert_id:
            print(f"📧 Scheduling email notification for alert {anomaly_alert_id}")
            background_tasks.add_task(
                send_anomaly_email_notification,
                anomaly_alert_id,
                db_session_factory=SessionLocal
            )

        # Process regular sensor alerts in background
        print("🔔 Scheduling alert processing...")
        background_tasks.add_task(
            process_sensor_alerts,
            sensor_data.pond_id,
            db_sensor_data.id
        )

        return {
            "message": "Sensor data ingested successfully",
            "sensor_data_id": db_sensor_data.id,
            "pond_id": pond.id,
            "pond_name": pond.name,
            "submitted_by_user": api_key_user.username,
            "submitted_by_user_id": api_key_user.id,
            "api_key_name": api_key_record.name,
            "api_key_id": api_key_record.id,
            "is_anomaly": is_anomaly,
            "quality_score": quality_score,
            "timestamp": db_sensor_data.timestamp.isoformat(),
            "anomaly_details": {
                "alert_id": anomaly_alert_id,
                "detected": is_anomaly
            } if is_anomaly else None
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error in sensor ingestion: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sensor data ingestion failed: {str(e)}"
        )