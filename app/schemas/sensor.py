"""
Pydantic schemas for sensor data endpoints
Handles validation for water quality measurements based on your pond analysis
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum


class SensorDataBase(BaseModel):
    """Base sensor data schema with all water quality parameters"""
    pond_id: int = Field(..., gt=0, description="Pond ID")
    
    # Core water quality parameters (from your analysis)
    temperature: Optional[float] = Field(None, ge=-10, le=50, description="Temperature in Celsius")
    ph: Optional[float] = Field(None, ge=0, le=14, description="pH level")
    dissolved_oxygen: Optional[float] = Field(None, ge=0, le=25, description="Dissolved oxygen in mg/L")
    turbidity: Optional[float] = Field(None, ge=0, description="Turbidity in NTU")
    ammonia: Optional[float] = Field(None, ge=0, description="Ammonia in mg/L")
    nitrate: Optional[float] = Field(None, ge=0, description="Nitrate in mg/L")
    nitrite: Optional[float] = Field(None, ge=0, description="Nitrite in mg/L")
    salinity: Optional[float] = Field(None, ge=0, description="Salinity in ppt")
    
    # Fish measurements
    fish_count: Optional[int] = Field(None, ge=0, description="Number of fish")
    fish_length: Optional[float] = Field(None, ge=0, description="Average fish length in cm")
    fish_weight: Optional[float] = Field(None, ge=0, description="Average fish weight in grams")
    
    # Additional measurements
    water_level: Optional[float] = Field(None, ge=0, description="Water level in cm")
    flow_rate: Optional[float] = Field(None, ge=0, description="Flow rate in L/min")
    
    # Metadata
    data_source: Optional[str] = Field(default="sensor", max_length=50)
    notes: Optional[str] = Field(None, max_length=500)
    timestamp: Optional[datetime] = Field(None, description="Measurement timestamp")


class SensorDataCreate(SensorDataBase):
    """Schema for creating new sensor data"""
    
    @validator('timestamp', pre=True, always=True)
    def validate_timestamp(cls, v):
        """Validate and set default timestamp with proper timezone handling"""
        if v is None:
            # Use UTC timezone-aware datetime as default
            return datetime.now(timezone.utc)
        
        # Handle string timestamps
        if isinstance(v, str):
            try:
                # Try parsing ISO format first
                v = datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError:
                # Try other common formats
                try:
                    v = datetime.strptime(v, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    raise ValueError('Invalid timestamp format. Use ISO format or YYYY-MM-DD HH:MM:SS')
        
        # Handle datetime objects
        if isinstance(v, datetime):
            # If no timezone info, assume UTC
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            
            # Compare with timezone-aware datetime
            now_utc = datetime.now(timezone.utc)
            if v > now_utc:
                raise ValueError('Timestamp cannot be in the future')
        
        return v
    
    @validator('temperature')
    def validate_temperature(cls, v):
        """Validate temperature range for aquaculture"""
        if v is not None:
            if v < -10 or v > 45:
                raise ValueError('Temperature should be between -10°C and 45°C for aquaculture, probable sensor failure.')
            # Warning for extreme values
            if v < 10 or v > 35:
                # Log warning but don't raise error
                pass
        return v
    
    @validator('ph')
    def validate_ph(cls, v):
        """Validate pH range for aquaculture"""
        if v is not None:
            if v < 4.0 or v > 10.0:
                raise ValueError('pH should be between 4.0 and 10.0 for aquaculture systems')
            # Optimal range warning
            if v < 6.5 or v > 8.5:
                # Log warning for suboptimal pH
                pass
        return v
    
    @validator('dissolved_oxygen')
    def validate_dissolved_oxygen(cls, v):
        """Validate dissolved oxygen levels"""
        if v is not None:
            if v < 0:
                raise ValueError('Dissolved oxygen cannot be negative')
            if v > 20:  # Very high DO might indicate measurement error
                raise ValueError('Dissolved oxygen level seems unusually high (>20 mg/L)')
        return v
    
    @validator('ammonia')
    def validate_ammonia(cls, v):
        """Validate ammonia levels"""
        if v is not None:
            if v < 0:
                raise ValueError('Ammonia level cannot be negative')
            if v > 10:  # High ammonia is dangerous
                # This is a critical level but might be valid in some conditions
                pass
        return v
    
    @validator('turbidity')
    def validate_turbidity(cls, v):
        """Validate turbidity levels"""
        if v is not None:
            if v < 0:
                raise ValueError('Turbidity cannot be negative')
        return v
    
    @validator('fish_count')
    def validate_fish_count(cls, v):
        """Validate fish count"""
        if v is not None:
            if v < 0:
                raise ValueError('Fish count cannot be negative')
            if v > 100000:  # Sanity check
                raise ValueError('Fish count seems unusually high')
        return v


class SensorDataBulkCreate(BaseModel):
    """Schema for bulk sensor data creation"""
    readings: List[SensorDataCreate] = Field(..., min_items=1, max_items=1000)
    
    @validator('readings')
    def validate_batch_consistency(cls, v):
        """Validate batch readings consistency"""
        if len(v) > 1000:
            raise ValueError('Batch size cannot exceed 1000 readings')
        
        # Check for duplicate timestamps per pond
        pond_timestamps = {}
        for reading in v:
            pond_id = reading.pond_id
            timestamp = reading.timestamp
            
            if pond_id not in pond_timestamps:
                pond_timestamps[pond_id] = set()
            
            if timestamp in pond_timestamps[pond_id]:
                raise ValueError(f'Duplicate timestamp {timestamp} for pond {pond_id}')
            
            pond_timestamps[pond_id].add(timestamp)
        
        return v


class SensorDataUpdate(BaseModel):
    """Schema for updating sensor data (limited fields)"""
    temperature: Optional[float] = Field(None, ge=-10, le=50)
    ph: Optional[float] = Field(None, ge=0, le=14)
    dissolved_oxygen: Optional[float] = Field(None, ge=0, le=25)
    turbidity: Optional[float] = Field(None, ge=0)
    ammonia: Optional[float] = Field(None, ge=0)
    nitrate: Optional[float] = Field(None, ge=0)
    nitrite: Optional[float] = Field(None, ge=0)
    salinity: Optional[float] = Field(None, ge=0)
    fish_count: Optional[int] = Field(None, ge=0)
    fish_length: Optional[float] = Field(None, ge=0)
    fish_weight: Optional[float] = Field(None, ge=0)
    water_level: Optional[float] = Field(None, ge=0)
    flow_rate: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=500)
    data_source: Optional[str] = Field(None, max_length=50)


class SensorDataInDB(SensorDataBase):
    """Sensor data from database"""
    id: int
    timestamp: datetime  # Override to make it required from DB
    quality_score: Optional[float] = Field(None, ge=0, le=100)
    is_anomaly: Optional[bool] = Field(None, description="Whether this reading is anomalous")
    entry_id: Optional[str] = Field(None, description="Unique entry identifier")
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class SensorDataResponse(SensorDataInDB):
    """Sensor data API response"""
    
    # Add computed fields
    health_indicators: Optional[Dict[str, Any]] = Field(None, description="Health assessment indicators")
    alerts_triggered: Optional[List[str]] = Field(None, description="List of alerts this reading triggered")
    
    class Config:
        from_attributes = True


class SensorDataQuery(BaseModel):
    """Schema for querying sensor data"""
    pond_id: Optional[int] = Field(None, gt=0)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    parameters: Optional[List[str]] = Field(
        None, 
        description="Specific parameters to retrieve",
        example=["temperature", "ph", "dissolved_oxygen"]
    )
    limit: Optional[int] = Field(default=100, ge=1, le=10000)
    offset: Optional[int] = Field(default=0, ge=0)
    include_anomalies: Optional[bool] = Field(default=True)
    order_by: Optional[str] = Field(
        default="timestamp", 
        pattern=r'^(timestamp|pond_id|temperature|ph|dissolved_oxygen)$'
    )
    order_direction: Optional[str] = Field(default="desc", pattern=r'^(asc|desc)$')
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        """Validate that end_date is after start_date"""
        if v and 'start_date' in values and values['start_date']:
            if v <= values['start_date']:
                raise ValueError('end_date must be after start_date')
        return v
    
    @validator('parameters')
    def validate_parameters(cls, v):
        """Validate parameter names"""
        if v:
            valid_params = {
                'temperature', 'ph', 'dissolved_oxygen', 'turbidity', 
                'ammonia', 'nitrate', 'nitrite', 'salinity', 'fish_count',
                'fish_length', 'fish_weight', 'water_level', 'flow_rate'
            }
            invalid_params = set(v) - valid_params
            if invalid_params:
                raise ValueError(f'Invalid parameters: {", ".join(invalid_params)}')
        return v


class AggregationType(str, Enum):
    """Data aggregation types"""
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class SensorDataAggregated(BaseModel):
    """Aggregated sensor data response"""
    pond_id: int
    period_start: datetime
    period_end: datetime
    aggregation_type: AggregationType
    
    # Temperature statistics
    temp_avg: Optional[float] = Field(None, description="Average temperature")
    temp_min: Optional[float] = Field(None, description="Minimum temperature")
    temp_max: Optional[float] = Field(None, description="Maximum temperature")
    temp_std: Optional[float] = Field(None, description="Temperature standard deviation")
    
    # pH statistics
    ph_avg: Optional[float] = Field(None, description="Average pH")
    ph_min: Optional[float] = Field(None, description="Minimum pH")
    ph_max: Optional[float] = Field(None, description="Maximum pH")
    ph_std: Optional[float] = Field(None, description="pH standard deviation")
    
    # Dissolved oxygen statistics
    do_avg: Optional[float] = Field(None, description="Average dissolved oxygen")
    do_min: Optional[float] = Field(None, description="Minimum dissolved oxygen")
    do_max: Optional[float] = Field(None, description="Maximum dissolved oxygen")
    do_std: Optional[float] = Field(None, description="Dissolved oxygen standard deviation")
    
    # Other parameters
    turbidity_avg: Optional[float] = Field(None, description="Average turbidity")
    ammonia_avg: Optional[float] = Field(None, description="Average ammonia")
    nitrate_avg: Optional[float] = Field(None, description="Average nitrate")
    
    # Data quality metrics
    data_points_count: int = Field(..., ge=0, description="Number of data points in aggregation")
    quality_score_avg: Optional[float] = Field(None, ge=0, le=100, description="Average quality score")
    anomaly_count: Optional[int] = Field(None, ge=0, description="Number of anomalous readings")
    completeness_score: Optional[float] = Field(None, ge=0, le=100, description="Data completeness percentage")
    
    class Config:
        from_attributes = True


class ParameterStatistics(BaseModel):
    """Statistics for a single parameter"""
    parameter: str = Field(..., description="Parameter name")
    count: int = Field(..., ge=0, description="Number of readings")
    mean: Optional[float] = Field(None, description="Mean value")
    median: Optional[float] = Field(None, description="Median value")
    std: Optional[float] = Field(None, ge=0, description="Standard deviation")
    min: Optional[float] = Field(None, description="Minimum value")
    max: Optional[float] = Field(None, description="Maximum value")
    q25: Optional[float] = Field(None, description="25th percentile")
    q75: Optional[float] = Field(None, description="75th percentile")
    latest_value: Optional[float] = Field(None, description="Latest recorded value")
    latest_timestamp: Optional[datetime] = Field(None, description="Timestamp of latest reading")
    trend: Optional[str] = Field(None, description="Trend direction: increasing, decreasing, stable")
    
    class Config:
        from_attributes = True


class PondDataSummary(BaseModel):
    """Summary of pond sensor data"""
    pond_id: int = Field(..., gt=0)
    pond_name: str = Field(..., description="Name of the pond")
    total_readings: int = Field(..., ge=0, description="Total number of readings")
    date_range_start: Optional[datetime] = Field(None, description="First reading timestamp")
    date_range_end: Optional[datetime] = Field(None, description="Last reading timestamp")
    parameters: List[ParameterStatistics] = Field(..., description="Statistics for each parameter")
    last_reading_timestamp: Optional[datetime] = Field(None, description="Most recent reading timestamp")
    data_quality_score: Optional[float] = Field(None, ge=0, le=100, description="Overall data quality score")
    health_score: Optional[float] = Field(None, ge=0, le=100, description="Current pond health score")
    active_alerts: Optional[int] = Field(None, ge=0, description="Number of active alerts")
    
    class Config:
        from_attributes = True


class SensorCalibration(BaseModel):
    """Schema for sensor calibration data"""
    sensor_id: str = Field(..., description="Sensor identifier")
    parameter: str = Field(..., description="Parameter being calibrated")
    calibration_date: datetime = Field(..., description="Calibration timestamp")
    calibration_factor: float = Field(..., description="Calibration multiplier")
    offset: float = Field(default=0.0, description="Calibration offset")
    reference_value: Optional[float] = Field(None, description="Reference standard value")
    measured_value: Optional[float] = Field(None, description="Measured value before calibration")
    notes: Optional[str] = Field(None, max_length=500)
    
    class Config:
        from_attributes = True


class DataQualityReport(BaseModel):
    """Data quality assessment report"""
    pond_id: int
    assessment_period: Dict[str, datetime] = Field(..., description="Start and end dates")
    overall_score: float = Field(..., ge=0, le=100, description="Overall quality score")
    
    # Quality metrics
    completeness_score: float = Field(..., ge=0, le=100)
    accuracy_score: Optional[float] = Field(None, ge=0, le=100)
    consistency_score: float = Field(..., ge=0, le=100)
    timeliness_score: float = Field(..., ge=0, le=100)
    
    # Issues found
    missing_data_periods: List[Dict[str, datetime]] = Field(default_factory=list)
    anomalous_readings: int = Field(default=0, ge=0)
    calibration_issues: List[str] = Field(default_factory=list)
    
    # Recommendations
    recommendations: List[str] = Field(default_factory=list)
    
    class Config:
        from_attributes = True