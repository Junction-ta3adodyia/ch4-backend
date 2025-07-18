"""
Application configuration
Manages environment variables and application settings using Pydantic
"""

from typing import List, Dict, Any, Optional
from pydantic import validator
from pydantic_settings import BaseSettings
import json
import os


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    """
    
    # Database Configuration
    DATABASE_URL: str
    DATABASE_NAME: str = "aquaculture"
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    
    # Security Settings
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    ALGORITHM: str = "HS256"
    
    # Application Settings
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_HOSTS: List[str] = ["*"]
    
    # Data Processing Settings
    ANOMALY_DETECTION_THRESHOLD: float = 0.1
    DATA_QUALITY_THRESHOLD: float = 0.7
    DATA_RETENTION_DAYS: int = 90
    
    # Alert System Configuration
    ALERT_CHECK_INTERVAL_MINUTES: int = 5
    MAX_ALERTS_PER_HOUR: int = 10
    
    # File Upload Settings
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_FILE_TYPES: List[str] = ["csv", "xlsx", "json"]
    
    # Email Configuration - Now reading from .env
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str  # Required from .env
    SMTP_PASSWORD: str  # Required from .env
    FROM_EMAIL: str = "noreply@aquaculture.dz"
    ENABLE_EMAIL_ALERTS: bool = True
    
    # SMS Configuration - Now reading from .env
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None
    
    # Push Notification Configuration (Optional)
    FIREBASE_SERVER_KEY: Optional[str] = None
    
    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Multilingual Support
    DEFAULT_LANGUAGE: str = "fr"
    SUPPORTED_LANGUAGES: List[str] = ["fr", "ar", "en"]
    
    # Alert Configuration
    ALERT_COOLDOWN_MINUTES: int = 30
    
    @validator('ALLOWED_HOSTS', pre=True)
    def parse_allowed_hosts(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [v]
        return v
    
    @validator('ALLOWED_FILE_TYPES', pre=True)
    def parse_allowed_file_types(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v.split(',')
        return v
    
    @validator('SUPPORTED_LANGUAGES', pre=True)
    def parse_supported_languages(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v.split(',')
        return v
    
    @validator('DEBUG', pre=True)
    def parse_debug(cls, v):
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return v
    
    @validator('ENABLE_EMAIL_ALERTS', pre=True)
    def parse_enable_email_alerts(cls, v):
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # This allows extra fields in .env without validation errors


# Alert thresholds configuration (as constants)
ALERT_THRESHOLDS = {
    "temperature": {
        "unit": "°C",
        "optimal_min": 20.0,
        "optimal_max": 28.0,
        "warning_min": 18.0,
        "warning_max": 30.0,
        "critical_min": 15.0,
        "critical_max": 35.0
    },
    "ph": {
        "unit": "pH",
        "optimal_min": 6.5,
        "optimal_max": 8.5,
        "warning_min": 6.0,
        "warning_max": 9.0,
        "critical_min": 5.5,
        "critical_max": 9.5
    },
    "dissolved_oxygen": {
        "unit": "mg/L",
        "optimal_min": 5.0,
        "optimal_max": 12.0,
        "warning_min": 3.0,
        "warning_max": 15.0,
        "critical_min": 2.0,
        "critical_max": 20.0
    },
    "turbidity": {
        "unit": "NTU",
        "optimal_min": 0.0,
        "optimal_max": 10.0,
        "warning_min": 0.0,
        "warning_max": 25.0,
        "critical_min": 0.0,
        "critical_max": 50.0
    },
    "ammonia": {
        "unit": "mg/L",
        "optimal_min": 0.0,
        "optimal_max": 0.25,
        "warning_min": 0.0,
        "warning_max": 0.5,
        "critical_min": 0.0,
        "critical_max": 1.0
    },
    "nitrate": {
        "unit": "mg/L",
        "optimal_min": 0.0,
        "optimal_max": 20.0,
        "warning_min": 0.0,
        "warning_max": 40.0,
        "critical_min": 0.0,
        "critical_max": 80.0
    }
}

# Health scoring weights
HEALTH_WEIGHTS = {
    "temperature": 0.25,
    "ph": 0.20,
    "dissolved_oxygen": 0.30,
    "turbidity": 0.10,
    "ammonia": 0.10,
    "nitrate": 0.05
}

# Multilingual alert messages
ALERT_MESSAGES = {
    "fr": {
        "critical_temp_high": "Température critique élevée: {value}{unit} dans {pond_name}",
        "critical_temp_low": "Température critique basse: {value}{unit} dans {pond_name}",
        "critical_oxygen_low": "Oxygène dissous critique: {value}{unit} dans {pond_name}",
        "critical_ph_high": "pH critique élevé: {value}{unit} dans {pond_name}",
        "critical_ph_low": "pH critique bas: {value}{unit} dans {pond_name}",
        "warning_temperature": "Alerte température: {value}{unit} dans {pond_name}",
        "warning_ph": "Alerte pH: {value}{unit} dans {pond_name}",
        "warning_dissolved_oxygen": "Alerte oxygène: {value}{unit} dans {pond_name}",
        "warning_turbidity": "Alerte turbidité: {value}{unit} dans {pond_name}",
        "warning_ammonia": "Alerte ammoniac: {value}{unit} dans {pond_name}",
        "warning_nitrate": "Alerte nitrate: {value}{unit} dans {pond_name}",
        "anomaly_detected": "Anomalie détectée - Paramètres: {parameters}. Score: {score}",
        "system_error": "Erreur système dans {pond_name}: {error_message}"
    },
    "ar": {
        "critical_temp_high": "درجة حرارة حرجة عالية: {value}{unit} في {pond_name}",
        "critical_temp_low": "درجة حرارة حرجة منخفضة: {value}{unit} في {pond_name}",
        "critical_oxygen_low": "أكسجين منحل حرج: {value}{unit} في {pond_name}",
        "critical_ph_high": "رقم هيدروجيني حرج عالي: {value}{unit} في {pond_name}",
        "critical_ph_low": "رقم هيدروجيني حرج منخفض: {value}{unit} في {pond_name}",
        "warning_temperature": "تحذير درجة الحرارة: {value}{unit} في {pond_name}",
        "warning_ph": "تحذير الرقم الهيدروجيني: {value}{unit} في {pond_name}",
        "warning_dissolved_oxygen": "تحذير الأكسجين: {value}{unit} في {pond_name}",
        "warning_turbidity": "تحذير العكارة: {value}{unit} في {pond_name}",
        "warning_ammonia": "تحذير الأمونيا: {value}{unit} في {pond_name}",
        "warning_nitrate": "تحذير النترات: {value}{unit} في {pond_name}",
        "anomaly_detected": "تم اكتشاف شذوذ - المعايير: {parameters}. النتيجة: {score}",
        "system_error": "خطأ في النظام في {pond_name}: {error_message}"
    },
    "en": {
        "critical_temp_high": "Critical high temperature: {value}{unit} in {pond_name}",
        "critical_temp_low": "Critical low temperature: {value}{unit} in {pond_name}",
        "critical_oxygen_low": "Critical low dissolved oxygen: {value}{unit} in {pond_name}",
        "critical_ph_high": "Critical high pH: {value}{unit} in {pond_name}",
        "critical_ph_low": "Critical low pH: {value}{unit} in {pond_name}",
        "warning_temperature": "Temperature warning: {value}{unit} in {pond_name}",
        "warning_ph": "pH warning: {value}{unit} in {pond_name}",
        "warning_dissolved_oxygen": "Oxygen warning: {value}{unit} in {pond_name}",
        "warning_turbidity": "Turbidity warning: {value}{unit} in {pond_name}",
        "warning_ammonia": "Ammonia warning: {value}{unit} in {pond_name}",
        "warning_nitrate": "Nitrate warning: {value}{unit} in {pond_name}",
        "anomaly_detected": "Anomaly detected - Parameters: {parameters}. Score: {score}",
        "system_error": "System error in {pond_name}: {error_message}"
    }
}

# Water quality grade mappings
HEALTH_GRADE_THRESHOLDS = {
    90: {"grade": "A+", "status": "Excellent", "color": "#00C851"},
    80: {"grade": "A", "status": "Very Good", "color": "#2E7D32"},
    70: {"grade": "B", "status": "Good", "color": "#4CAF50"},
    60: {"grade": "C", "status": "Fair", "color": "#FF9800"},
    50: {"grade": "D", "status": "Poor", "color": "#FF5722"},
    0: {"grade": "F", "status": "Critical", "color": "#F44336"}
}

# Create settings instance
settings = Settings()