"""
Data Aggregation Tasks
Scheduled tasks for aggregating sensor data and maintaining system health
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
import pandas as pd

from app.database import SessionLocal
from app.models.sensor import SensorData, SensorDataAggregated
from app.models.pond import Pond, User
from app.core.alert_engine import check_for_stale_data
from app.services.notification import NotificationService


async def aggregate_hourly_data():
    """
    Aggregate sensor data into hourly summaries
    Should be run every hour
    """
    db = SessionLocal()
    
    try:
        # Get the last hour's data
        end_time = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(hours=1)
        
        # Get all ponds with data in the last hour
        ponds_with_data = db.query(SensorData.pond_id).filter(
            and_(
                SensorData.timestamp >= start_time,
                SensorData.timestamp < end_time
            )
        ).distinct().all()
        
        for (pond_id,) in ponds_with_data:
            await _create_hourly_aggregation(db, pond_id, start_time, end_time)
        
        db.commit()
        print(f"Completed hourly aggregation for {len(ponds_with_data)} ponds")
        
    except Exception as e:
        print(f"Error in hourly aggregation: {e}")
        db.rollback()
    finally:
        db.close()


async def aggregate_daily_data():
    """
    Aggregate sensor data into daily summaries
    Should be run daily at midnight
    """
    db = SessionLocal()
    
    try:
        # Get yesterday's data
        end_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(days=1)
        
        # Get all ponds with data yesterday
        ponds_with_data = db.query(SensorData.pond_id).filter(
            and_(
                SensorData.timestamp >= start_time,
                SensorData.timestamp < end_time
            )
        ).distinct().all()
        
        for (pond_id,) in ponds_with_data:
            await _create_daily_aggregation(db, pond_id, start_time, end_time)
        
        db.commit()
        print(f"Completed daily aggregation for {len(ponds_with_data)} ponds")
        
        # Send daily summaries to users
        await _send_daily_summaries(db, start_time, end_time)
        
    except Exception as e:
        print(f"Error in daily aggregation: {e}")
        db.rollback()
    finally:
        db.close()


async def _create_hourly_aggregation(
    db: Session, 
    pond_id: int, 
    start_time: datetime, 
    end_time: datetime
):
    """
    Create hourly aggregation for a specific pond
    """
    # Check if aggregation already exists
    existing = db.query(SensorDataAggregated).filter(
        and_(
            SensorDataAggregated.pond_id == pond_id,
            SensorDataAggregated.aggregation_type == 'hour',
            SensorDataAggregated.period_start == start_time
        )
    ).first()
    
    if existing:
        return  # Already aggregated
    
    # Get raw data for the hour
    raw_data = db.query(SensorData).filter(
        and_(
            SensorData.pond_id == pond_id,
            SensorData.timestamp >= start_time,
            SensorData.timestamp < end_time
        )
    ).all()
    
    if not raw_data:
        return
    
    # Calculate aggregations
    aggregation = _calculate_aggregations(raw_data)
    
    # Create aggregated record
    agg_record = SensorDataAggregated(
        pond_id=pond_id,
        period_start=start_time,
        period_end=end_time,
        aggregation_type='hour',
        data_points_count=len(raw_data),
        **aggregation
    )
    
    db.add(agg_record)


async def _create_daily_aggregation(
    db: Session, 
    pond_id: int, 
    start_time: datetime, 
    end_time: datetime
):
    """
    Create daily aggregation for a specific pond
    """
    # Check if aggregation already exists
    existing = db.query(SensorDataAggregated).filter(
        and_(
            SensorDataAggregated.pond_id == pond_id,
            SensorDataAggregated.aggregation_type == 'day',
            SensorDataAggregated.period_start == start_time
        )
    ).first()
    
    if existing:
        return
    
    # Get raw data for the day
    raw_data = db.query(SensorData).filter(
        and_(
            SensorData.pond_id == pond_id,
            SensorData.timestamp >= start_time,
            SensorData.timestamp < end_time
        )
    ).all()
    
    if not raw_data:
        return
    
    # Calculate aggregations
    aggregation = _calculate_aggregations(raw_data)
    
    # Create aggregated record
    agg_record = SensorDataAggregated(
        pond_id=pond_id,
        period_start=start_time,
        period_end=end_time,
        aggregation_type='day',
        data_points_count=len(raw_data),
        **aggregation
    )
    
    db.add(agg_record)


def _calculate_aggregations(raw_data) -> Dict[str, Any]:
    """
    Calculate statistical aggregations from raw sensor data
    """
    # Convert to DataFrame for easier calculations
    df_data = []
    for record in raw_data:
        df_data.append({
            'temperature': record.temperature,
            'ph': record.ph,
            'dissolved_oxygen': record.dissolved_oxygen,
            'turbidity': record.turbidity,
            'ammonia': record.ammonia,
            'nitrate': record.nitrate,
            'quality_score': record.quality_score,
            'is_anomaly': record.is_anomaly
        })
    
    df = pd.DataFrame(df_data)
    
    aggregation = {}
    
    # Temperature aggregations
    if 'temperature' in df.columns and df['temperature'].notna().any():
        temp_data = df['temperature'].dropna()
        aggregation.update({
            'temp_avg': float(temp_data.mean()),
            'temp_min': float(temp_data.min()),
            'temp_max': float(temp_data.max()),
            'temp_std': float(temp_data.std()) if len(temp_data) > 1 else 0
        })
    
    # pH aggregations
    if 'ph' in df.columns and df['ph'].notna().any():
        ph_data = df['ph'].dropna()
        aggregation.update({
            'ph_avg': float(ph_data.mean()),
            'ph_min': float(ph_data.min()),
            'ph_max': float(ph_data.max()),
            'ph_std': float(ph_data.std()) if len(ph_data) > 1 else 0
        })
    
    # Dissolved oxygen aggregations
    if 'dissolved_oxygen' in df.columns and df['dissolved_oxygen'].notna().any():
        do_data = df['dissolved_oxygen'].dropna()
        aggregation.update({
            'do_avg': float(do_data.mean()),
            'do_min': float(do_data.min()),
            'do_max': float(do_data.max()),
            'do_std': float(do_data.std()) if len(do_data) > 1 else 0
        })
    
    # Other parameters
    if 'turbidity' in df.columns and df['turbidity'].notna().any():
        aggregation['turbidity_avg'] = float(df['turbidity'].dropna().mean())
    
    if 'ammonia' in df.columns and df['ammonia'].notna().any():
        aggregation['ammonia_avg'] = float(df['ammonia'].dropna().mean())
    
    if 'nitrate' in df.columns and df['nitrate'].notna().any():
        aggregation['nitrate_avg'] = float(df['nitrate'].dropna().mean())
    
    # Quality and anomaly metrics
    if 'quality_score' in df.columns and df['quality_score'].notna().any():
        aggregation['quality_score_avg'] = float(df['quality_score'].dropna().mean())
    
    if 'is_anomaly' in df.columns:
        aggregation['anomaly_count'] = int(df['is_anomaly'].sum())
    
    return aggregation


async def _send_daily_summaries(db: Session, start_time: datetime, end_time: datetime):
    """
    Send daily summary emails to users who have opted in
    """
    notification_service = NotificationService()
    
    # Get users who want daily summaries
    users_for_summaries = db.query(Pond.owner_id).filter(
        Pond.daily_summary_enabled == True
    ).distinct().all()
    
    for (user_id,) in users_for_summaries:
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.email:
                continue
            
            # Get user's pond data for yesterday
            user_ponds = db.query(Pond).filter(Pond.owner_id == user_id).all()
            
            summary_data = {
                'user': user,
                'date': start_time.strftime('%Y-%m-%d'),
                'ponds': []
            }
            
            for pond in user_ponds:
                # Get daily aggregation for this pond
                daily_agg = db.query(SensorDataAggregated).filter(
                    and_(
                        SensorDataAggregated.pond_id == pond.id,
                        SensorDataAggregated.aggregation_type == 'day',
                        SensorDataAggregated.period_start == start_time
                    )
                ).first()
                
                if daily_agg:
                    pond_summary = {
                        'name': pond.name,
                        'data_points': daily_agg.data_points_count,
                        'avg_temperature': daily_agg.temp_avg,
                        'avg_ph': daily_agg.ph_avg,
                        'avg_do': daily_agg.do_avg,
                        'quality_score': daily_agg.quality_score_avg,
                        'anomalies': daily_agg.anomaly_count
                    }
                    summary_data['ponds'].append(pond_summary)
            
            # Send summary if there's data
            if summary_data['ponds']:
                await notification_service.send_daily_summary(user, summary_data)
                
        except Exception as e:
            print(f"Error sending daily summary to user {user_id}: {e}")


async def cleanup_old_data():
    """
    Clean up old raw sensor data (keep aggregated data)
    Should be run weekly
    """
    db = SessionLocal()
    
    try:
        # Keep raw data for 90 days, remove older
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        # Delete old raw sensor data
        deleted_count = db.query(SensorData).filter(
            SensorData.timestamp < cutoff_date
        ).delete()
        
        # Keep aggregated data for 2 years
        agg_cutoff_date = datetime.utcnow() - timedelta(days=730)
        
        deleted_agg_count = db.query(SensorDataAggregated).filter(
            SensorDataAggregated.period_start < agg_cutoff_date
        ).delete()
        
        db.commit()
        
        print(f"Cleaned up {deleted_count} old sensor records and {deleted_agg_count} old aggregated records")
        
    except Exception as e:
        print(f"Error in data cleanup: {e}")
        db.rollback()
    finally:
        db.close()


async def system_health_check():
    """
    Perform system health checks
    Should be run every 15 minutes
    """
    # Check for stale data
    check_for_stale_data()
    
    # Add other health checks here
    # - Database connectivity
    # - Disk space
    # - Memory usage
    # - API response times
    
    print("System health check completed")