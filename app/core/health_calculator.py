"""
Pond Health Calculator
Implements the comprehensive health assessment algorithm based on your analysis
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.models.sensor import SensorData
from app.models.alert import Alert, AlertStatus, AlertSeverity
from app.models.pond import Pond
from app.config import settings


async def calculate_pond_health(
    pond_id: int, 
    db: Session, 
    days: int = 7
) -> Optional[Dict[str, Any]]:
    """
    Calculate comprehensive pond health score based on your analysis algorithm
    
    Args:
        pond_id: Pond ID to analyze
        db: Database session
        days: Number of days to analyze (default 7)
    
    Returns:
        Dictionary with health assessment data or None if insufficient data
    """
    
    # Get sensor data for the specified period
    start_date = datetime.utcnow() - timedelta(days=days)
    
    sensor_data = db.query(SensorData).filter(
        and_(
            SensorData.pond_id == pond_id,
            SensorData.timestamp >= start_date
        )
    ).order_by(SensorData.timestamp).all()
    
    if len(sensor_data) < 10:  # Need minimum data points
        return None
    
    # Convert to DataFrame for easier analysis
    data_dict = {
        'temperature': [d.temperature for d in sensor_data if d.temperature is not None],
        'ph': [d.ph for d in sensor_data if d.ph is not None],
        'dissolved_oxygen': [d.dissolved_oxygen for d in sensor_data if d.dissolved_oxygen is not None],
        'turbidity': [d.turbidity for d in sensor_data if d.turbidity is not None],
        'ammonia': [d.ammonia for d in sensor_data if d.ammonia is not None],
        'nitrate': [d.nitrate for d in sensor_data if d.nitrate is not None]
    }
    
    # Calculate individual parameter scores
    parameter_scores = {}
    weighted_scores = []
    total_weight = 0
    warnings = []
    recommendations = []
    critical_issues = []
    
    parameters_assessed = 0
    
    for parameter, data in data_dict.items():
        if not data or len(data) < 3:  # Skip if insufficient data
            continue
            
        parameters_assessed += 1
        criteria = settings.ALERT_THRESHOLDS.get(parameter, {})
        weight = settings.HEALTH_WEIGHTS.get(parameter, 1.0)
        
        if not criteria:
            continue
            
        # Calculate parameter score using your algorithm
        score = calculate_parameter_score(data, criteria)
        parameter_scores[f"{parameter}_score"] = score
        
        # Add to weighted calculation
        weighted_scores.append(score * weight)
        total_weight += weight
        
        # Generate warnings and recommendations
        mean_val = np.mean(data)
        _analyze_parameter_health(parameter, mean_val, criteria, warnings, recommendations, critical_issues)
    
    if not weighted_scores:
        return None
    
    # Calculate overall scores
    overall_weighted_score = sum(weighted_scores) / total_weight
    overall_simple_score = np.mean(list(parameter_scores.values()))
    
    # Assign grade and status
    grade, status = _assign_grade_and_status(overall_weighted_score)
    
    # Risk assessment
    risk_level = _assess_risk_level(overall_weighted_score, len(warnings), len(critical_issues))
    
    # Action priority
    action_priority = _determine_action_priority(overall_weighted_score, len(critical_issues))
    
    # Data completeness
    total_possible_params = len(settings.ALERT_THRESHOLDS)
    data_completeness = (parameters_assessed / total_possible_params) * 100
    
    # Assessment confidence
    confidence = _calculate_confidence(len(sensor_data), parameters_assessed, data_completeness)
    
    # Get recent alert count
    recent_alerts = db.query(Alert).filter(
        and_(
            Alert.pond_id == pond_id,
            Alert.triggered_at >= start_date
        )
    ).count()
    
    # Prepare assessment result
    assessment = {
        "pond_id": pond_id,
        "overall_score": round(overall_weighted_score, 1),
        "weighted_score": round(overall_weighted_score, 1),
        "grade": grade,
        "status": status,
        "risk_level": risk_level,
        "warning_count": len(warnings),
        "critical_issues": critical_issues,
        "recommendations": recommendations,
        "action_priority": action_priority,
        "parameters_assessed": parameters_assessed,
        "data_completeness": round(data_completeness, 1),
        "assessment_confidence": round(confidence, 2),
        "assessment_period_start": start_date,
        "assessment_period_end": datetime.utcnow(),
        "calculated_at": datetime.utcnow(),
        **parameter_scores  # Individual parameter scores
    }
    
    return assessment


def calculate_parameter_score(data: List[float], criteria: Dict[str, float]) -> float:
    """
    Calculate score for a single parameter based on your scoring algorithm
    """
    if not data:
        return 0.0
    
    mean_value = np.mean(data)
    std_value = np.std(data)
    
    # Get thresholds
    optimal_min = criteria.get('optimal_min')
    optimal_max = criteria.get('optimal_max')
    warning_low = criteria.get('warning_low')
    warning_high = criteria.get('warning_high')
    critical_low = criteria.get('critical_low')
    critical_high = criteria.get('critical_high')
    
    # Determine if lower is better (for toxicity parameters)
    lower_is_better = 'optimal_min' not in criteria
    
    scores = []
    
    for value in data:
        if lower_is_better:
            # For parameters where lower is better (turbidity, ammonia, nitrate)
            if optimal_max and value <= optimal_max:
                score = 100  # Excellent
            elif warning_high and value <= warning_high:
                # Linear interpolation between optimal and warning
                score = 80 + (optimal_max - value) / (optimal_max - 0) * 20
                score = max(60, min(100, score))
            elif critical_high and value <= critical_high:
                # Linear interpolation between warning and critical
                score = 40 + (warning_high - value) / (warning_high - (optimal_max or 0)) * 40
                score = max(0, min(60, score))
            else:
                score = 0  # Critical/dangerous
        else:
            # For parameters with optimal ranges (temperature, pH, DO)
            if optimal_min and optimal_max and optimal_min <= value <= optimal_max:
                score = 100  # Excellent
            elif warning_low and warning_high and warning_low <= value <= warning_high:
                if value < optimal_min:
                    # Below optimal range
                    score = 80 + (value - warning_low) / (optimal_min - warning_low) * 20
                else:
                    # Above optimal range
                    score = 80 + (warning_high - value) / (warning_high - optimal_max) * 20
                score = max(60, min(100, score))
            elif critical_low and critical_high and critical_low <= value <= critical_high:
                if value < warning_low:
                    # Below warning range
                    score = 40 + (value - critical_low) / (warning_low - critical_low) * 20
                else:
                    # Above warning range
                    score = 40 + (critical_high - value) / (critical_high - warning_high) * 20
                score = max(0, min(60, score))
            else:
                score = 0  # Critical/dangerous
        
        scores.append(max(0, min(100, score)))
    
    # Account for variability (stability is good)
    base_score = np.mean(scores)
    stability_penalty = min(std_value / mean_value * 10, 10) if mean_value > 0 else 0
    
    final_score = max(0, base_score - stability_penalty)
    
    return round(final_score, 1)


def _analyze_parameter_health(
    parameter: str,
    mean_val: float,
    criteria: Dict[str, float],
    warnings: List[str],
    recommendations: List[str],
    critical_issues: List[str]
) -> None:
    """
    Analyze parameter health and add warnings/recommendations
    """
    optimal_min = criteria.get('optimal_min')
    optimal_max = criteria.get('optimal_max')
    warning_low = criteria.get('warning_low')
    warning_high = criteria.get('warning_high')
    critical_low = criteria.get('critical_low')
    critical_high = criteria.get('critical_high')
    unit = criteria.get('unit', '')
    
    # Check for critical issues
    if critical_low and mean_val < critical_low:
        critical_issues.append(f"Critical {parameter}: {mean_val:.2f} {unit} (< {critical_low})")
        recommendations.append(f"URGENT: Immediately address low {parameter}")
    elif critical_high and mean_val > critical_high:
        critical_issues.append(f"Critical {parameter}: {mean_val:.2f} {unit} (> {critical_high})")
        recommendations.append(f"URGENT: Immediately address high {parameter}")
    
    # Check for warnings
    elif warning_low and mean_val < warning_low:
        warnings.append(f"Low {parameter}: {mean_val:.2f} {unit}")
        recommendations.append(f"Monitor and consider increasing {parameter}")
    elif warning_high and mean_val > warning_high:
        warnings.append(f"High {parameter}: {mean_val:.2f} {unit}")
        recommendations.append(f"Monitor and consider reducing {parameter}")
    
    # Add specific recommendations based on parameter
    _add_parameter_specific_recommendations(parameter, mean_val, criteria, recommendations)


def _add_parameter_specific_recommendations(
    parameter: str,
    value: float,
    criteria: Dict[str, float],
    recommendations: List[str]
) -> None:
    """
    Add parameter-specific recommendations
    """
    if parameter == "temperature":
        if value < 20:
            recommendations.append("Consider adding heating system or insulation")
        elif value > 28:
            recommendations.append("Improve aeration and consider cooling methods")
    
    elif parameter == "ph":
        if value < 6.5:
            recommendations.append("Add lime or baking soda to increase pH")
        elif value > 8.5:
            recommendations.append("Add organic matter or use pH reducing agents")
    
    elif parameter == "dissolved_oxygen":
        if value < 5:
            recommendations.append("Increase aeration immediately")
            recommendations.append("Check for overstocking or overfeeding")
    
    elif parameter == "ammonia":
        if value > 0.5:
            recommendations.append("Reduce feeding and increase water changes")
            recommendations.append("Check biofilter efficiency")
    
    elif parameter == "turbidity":
        if value > 50:
            recommendations.append("Improve filtration system")
            recommendations.append("Reduce organic load in pond")


def _assign_grade_and_status(score: float) -> tuple:
    """
    Assign letter grade and status based on score
    """
    if score >= 90:
        return 'A+', 'Excellent'
    elif score >= 85:
        return 'A', 'Very Good'
    elif score >= 80:
        return 'B+', 'Good'
    elif score >= 75:
        return 'B', 'Satisfactory'
    elif score >= 70:
        return 'C+', 'Fair'
    elif score >= 60:
        return 'C', 'Poor'
    elif score >= 50:
        return 'D', 'Very Poor'
    else:
        return 'F', 'Critical'


def _assess_risk_level(score: float, warning_count: int, critical_count: int) -> str:
    """
    Assess risk level based on score and issues
    """
    if critical_count > 0 or score < 50:
        return "High"
    elif warning_count > 2 or score < 70:
        return "Medium"
    else:
        return "Low"


def _determine_action_priority(score: float, critical_count: int) -> str:
    """
    Determine action priority
    """
    if critical_count > 0 or score < 50:
        return "Urgent"
    elif score < 70:
        return "Improve"
    elif score < 85:
        return "Monitor"
    else:
        return "Maintain"


def _calculate_confidence(data_points: int, parameters_assessed: int, completeness: float) -> float:
    """
    Calculate confidence in the assessment
    """
    # Data volume factor (0-1)
    volume_factor = min(data_points / 100, 1.0)
    
    # Parameter completeness factor (0-1)
    completeness_factor = completeness / 100
    
    # Time factor (more data points over time = higher confidence)
    time_factor = min(data_points / 50, 1.0)
    
    # Combined confidence
    confidence = (volume_factor * 0.4 + completeness_factor * 0.4 + time_factor * 0.2)
    
    return confidence