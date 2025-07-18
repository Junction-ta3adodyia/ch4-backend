"""
Sensor data model - Stores all water quality measurements
This is the core data model containing all sensor readings from your datasets
"""

from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, Index, Text, String, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class SensorData(Base):
    """
    Sensor Data model
    Stores time-series water quality measurements from IoT sensors
    Based on the parameters found in your pond datasets
    """
    __tablename__ = "sensor_data"
    
    # Primary key and relationships
    id = Column(Integer, primary_key=True, index=True)
    pond_id = Column(Integer, ForeignKey("ponds.id"), nullable=False, index=True)
    
    # Timestamp (critical for time-series analysis)
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Water quality parameters (based on your dataset analysis)
    temperature = Column(Float, nullable=True, comment="Temperature in Celsius")
    ph = Column(Float, nullable=True, comment="pH level (0-14)")
    dissolved_oxygen = Column(Float, nullable=True, comment="Dissolved oxygen in mg/L")
    turbidity = Column(Float, nullable=True, comment="Turbidity in NTU")
    ammonia = Column(Float, nullable=True, comment="Ammonia concentration in mg/L")
    nitrate = Column(Float, nullable=True, comment="Nitrate concentration in mg/L")
    nitrite = Column(Float, nullable=True, comment="Nitrite concentration in mg/L")
    salinity = Column(Float, nullable=True, comment="Salinity in ppt")
    
    # Fish-related measurements (from your datasets)
    fish_count = Column(Integer, nullable=True, comment="Number of fish observed")
    fish_length = Column(Float, nullable=True, comment="Average fish length in cm")
    fish_weight = Column(Float, nullable=True, comment="Average fish weight in grams")
    
    # Additional water parameters
    water_level = Column(Float, nullable=True, comment="Water level in cm")
    flow_rate = Column(Float, nullable=True, comment="Water flow rate in L/min")
    
    # Data quality and source tracking
    data_source = Column(String(50), nullable=True, default="sensor")  # sensor, manual, calculated
    quality_score = Column(Float, nullable=True, comment="Data quality score 0-1")
    is_anomaly = Column(Boolean, default=False, nullable=False, comment="Anomaly detection flag")
    
    # Metadata
    entry_id = Column(String(100), nullable=True, index=True)  # Original entry ID from your datasets
    notes = Column(Text, nullable=True, comment="Additional notes or observations")
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    pond = relationship("Pond", back_populates="sensor_data")
    
    # Database indexes for performance (critical for time-series queries)
    __table_args__ = (
        Index('idx_pond_timestamp', 'pond_id', 'timestamp'),
        Index('idx_timestamp_desc', 'timestamp', postgresql_using='btree'),
        Index('idx_pond_temp', 'pond_id', 'temperature'),
        Index('idx_pond_ph', 'pond_id', 'ph'),
        Index('idx_pond_do', 'pond_id', 'dissolved_oxygen'),
    )
    
    def __repr__(self):
        return f"<SensorData(pond_id={self.pond_id}, timestamp={self.timestamp}, temp={self.temperature})>"


class SensorDataAggregated(Base):
    """
    Aggregated sensor data for performance
    Stores hourly/daily aggregations to speed up historical queries
    """
    __tablename__ = "sensor_data_aggregated"
    
    id = Column(Integer, primary_key=True, index=True)
    pond_id = Column(Integer, ForeignKey("ponds.id"), nullable=False, index=True)
    
    # Time period
    period_start = Column(DateTime, nullable=False, index=True)
    period_end = Column(DateTime, nullable=False)
    aggregation_type = Column(String(10), nullable=False)  # 'hour', 'day', 'week'
    
    # Aggregated statistics for each parameter
    # Temperature
    temp_avg = Column(Float, nullable=True)
    temp_min = Column(Float, nullable=True)
    temp_max = Column(Float, nullable=True)
    temp_std = Column(Float, nullable=True)
    
    # pH
    ph_avg = Column(Float, nullable=True)
    ph_min = Column(Float, nullable=True)
    ph_max = Column(Float, nullable=True)
    ph_std = Column(Float, nullable=True)
    
    # Dissolved Oxygen
    do_avg = Column(Float, nullable=True)
    do_min = Column(Float, nullable=True)
    do_max = Column(Float, nullable=True)
    do_std = Column(Float, nullable=True)
    
    # Other parameters (similar pattern)
    turbidity_avg = Column(Float, nullable=True)
    ammonia_avg = Column(Float, nullable=True)
    nitrate_avg = Column(Float, nullable=True)
    
    # Data quality metrics
    data_points_count = Column(Integer, nullable=False, default=0)
    quality_score_avg = Column(Float, nullable=True)
    anomaly_count = Column(Integer, nullable=True, default=0)
    
    created_at = Column(DateTime, server_default=func.now())
    
    __table_args__ = (
        Index('idx_pond_period', 'pond_id', 'period_start', 'aggregation_type'),
    )
    
    def __repr__(self):
        return f"<SensorDataAggregated(pond_id={self.pond_id}, period={self.aggregation_type}, start={self.period_start})>"