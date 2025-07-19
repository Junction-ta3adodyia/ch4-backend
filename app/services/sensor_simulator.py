"""
Advanced Aquaculture Sensor Simulator Service
Simulates realistic IoT sensor behavior with various scenarios
"""

import asyncio
import aiohttp
import hmac
import hashlib
import json
import random
import time
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Any
import logging
from dataclasses import dataclass, asdict
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SimulationScenario(Enum):
    """Different simulation scenarios"""
    NORMAL = "normal"
    STRESS_TEST = "stress_test"
    ANOMALY_INJECTION = "anomaly_injection"
    DAILY_CYCLE = "daily_cycle"
    EQUIPMENT_FAILURE = "equipment_failure"
    FEEDING_TIME = "feeding_time"
    WEATHER_STORM = "weather_storm"


@dataclass
class SensorConfig:
    """Configuration for individual sensor parameters"""
    name: str
    min_value: float
    max_value: float
    optimal_min: float
    optimal_max: float
    daily_variation: float = 0.1  # How much it varies throughout the day
    noise_level: float = 0.02  # Random noise factor
    drift_rate: float = 0.001  # Long-term drift
    correlation_factors: Dict[str, float] = None  # Correlation with other parameters


class AquacultureSensorSimulator:
    """
    Advanced sensor simulator with realistic aquaculture patterns
    """

    def __init__(self, base_url: str, api_key: str, secret_key: str, pond_id: int):
        self.base_url = base_url
        self.api_key = api_key
        self.secret_key = secret_key
        self.pond_id = pond_id
        self.session = None
        self.simulation_start_time = None
        self.readings_sent = 0
        self.successful_readings = 0
        self.current_scenario = SimulationScenario.NORMAL
        
        # Sensor configurations
        self.sensors = {
            'temperature': SensorConfig(
                name='temperature',
                min_value=18.0, max_value=32.0,
                optimal_min=24.0, optimal_max=26.0,
                daily_variation=0.15,
                noise_level=0.02,
                correlation_factors={'dissolved_oxygen': -0.3}
            ),
            'ph': SensorConfig(
                name='ph',
                min_value=6.0, max_value=8.5,
                optimal_min=7.0, optimal_max=7.5,
                daily_variation=0.05,
                noise_level=0.01
            ),
            'dissolved_oxygen': SensorConfig(
                name='dissolved_oxygen',
                min_value=3.0, max_value=12.0,
                optimal_min=6.0, optimal_max=8.0,
                daily_variation=0.2,
                noise_level=0.03,
                correlation_factors={'temperature': -0.3, 'turbidity': -0.2}
            ),
            'turbidity': SensorConfig(
                name='turbidity',
                min_value=5.0, max_value=100.0,
                optimal_min=10.0, optimal_max=30.0,
                daily_variation=0.1,
                noise_level=0.05
            ),
            'ammonia': SensorConfig(
                name='ammonia',
                min_value=0.01, max_value=2.0,
                optimal_min=0.01, optimal_max=0.1,
                daily_variation=0.05,
                noise_level=0.02
            ),
            'nitrate': SensorConfig(
                name='nitrate',
                min_value=0.5, max_value=20.0,
                optimal_min=2.0, optimal_max=5.0,
                daily_variation=0.03,
                noise_level=0.02
            ),
            'salinity': SensorConfig(
                name='salinity',
                min_value=0.0, max_value=5.0,
                optimal_min=0.5, optimal_max=2.0,
                daily_variation=0.02,
                noise_level=0.01
            ),
            'water_level': SensorConfig(
                name='water_level',
                min_value=1.0, max_value=3.0,
                optimal_min=1.8, optimal_max=2.2,
                daily_variation=0.05,
                noise_level=0.01
            ),
            'flow_rate': SensorConfig(
                name='flow_rate',
                min_value=15.0, max_value=50.0,
                optimal_min=25.0, optimal_max=35.0,
                daily_variation=0.1,
                noise_level=0.03
            )
        }
        
        # Initialize current values to optimal ranges
        self.current_values = {}
        self.base_values = {}
        for param, config in self.sensors.items():
            optimal_mid = (config.optimal_min + config.optimal_max) / 2
            self.current_values[param] = optimal_mid
            self.base_values[param] = optimal_mid
        
        # Scenario-specific settings
        self.scenario_settings = {}
        self.scenario_start_time = None

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        self.simulation_start_time = time.time()
        logger.info(f"🔗 Initialized sensor simulator for pond {self.pond_id}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        elapsed = time.time() - self.simulation_start_time if self.simulation_start_time else 0
        logger.info(f"🔗 Simulation completed. Duration: {elapsed:.1f}s, Success rate: {self.successful_readings}/{self.readings_sent}")

    def _generate_signature(self, timestamp: str, payload: bytes) -> str:
        """Generate HMAC-SHA256 signature for the payload."""
        message = timestamp.encode('utf-8') + b'.' + payload
        return hmac.new(
            self.secret_key.encode('utf-8'),
            msg=message,
            digestmod=hashlib.sha256
        ).hexdigest()

    def set_scenario(self, scenario: SimulationScenario, **kwargs):
        """Set the current simulation scenario"""
        self.current_scenario = scenario
        self.scenario_settings = kwargs
        self.scenario_start_time = time.time()
        logger.info(f"🎭 Scenario changed to: {scenario.value}")

    def _apply_daily_cycle(self, elapsed_hours: float, base_value: float, config: SensorConfig) -> float:
        """Apply daily cycle variations (e.g., temperature changes, DO fluctuations)"""
        # 24-hour sine wave for daily patterns
        daily_phase = (elapsed_hours % 24) / 24 * 2 * math.pi
        daily_factor = math.sin(daily_phase - math.pi/2)  # Peak at noon, low at midnight
        
        variation = daily_factor * config.daily_variation * (config.optimal_max - config.optimal_min)
        return base_value + variation

    def _apply_correlations(self, param: str, base_value: float) -> float:
        """Apply correlations between parameters"""
        config = self.sensors[param]
        if not config.correlation_factors:
            return base_value
        
        correlation_adjustment = 0
        for correlated_param, factor in config.correlation_factors.items():
            if correlated_param in self.current_values:
                correlated_config = self.sensors[correlated_param]
                correlated_optimal_mid = (correlated_config.optimal_min + correlated_config.optimal_max) / 2
                correlated_deviation = (self.current_values[correlated_param] - correlated_optimal_mid) / correlated_optimal_mid
                correlation_adjustment += factor * correlated_deviation * (config.optimal_max - config.optimal_min)
        
        return base_value + correlation_adjustment

    def _apply_scenario_effects(self, param: str, base_value: float, elapsed_time: float) -> float:
        """Apply scenario-specific effects"""
        config = self.sensors[param]
        
        if self.current_scenario == SimulationScenario.ANOMALY_INJECTION:
            # Inject specific anomalies
            anomaly_duration = self.scenario_settings.get('anomaly_duration', 120)  # 2 minutes
            anomaly_intensity = self.scenario_settings.get('anomaly_intensity', 2.0)
            
            if elapsed_time < anomaly_duration:
                progress = elapsed_time / anomaly_duration
                intensity = math.sin(progress * math.pi) * anomaly_intensity  # Bell curve
                
                if param == 'temperature':
                    return base_value + intensity * 8.0  # +8°C spike
                elif param == 'ph':
                    return base_value - intensity * 1.5  # pH drop
                elif param == 'dissolved_oxygen':
                    return base_value - intensity * 4.0  # Oxygen depletion
                elif param == 'ammonia':
                    return base_value + intensity * 0.8  # Ammonia spike
        
        elif self.current_scenario == SimulationScenario.EQUIPMENT_FAILURE:
            failure_type = self.scenario_settings.get('failure_type', 'aerator')
            
            if failure_type == 'aerator' and param == 'dissolved_oxygen':
                # Gradual oxygen depletion
                depletion_rate = elapsed_time / 300  # 5 minutes to critical
                return base_value * (1 - min(0.6, depletion_rate))
            elif failure_type == 'heater' and param == 'temperature':
                # Temperature drop
                cooling_rate = elapsed_time / 600  # 10 minutes to drop
                return base_value - min(8.0, cooling_rate * 8.0)
        
        elif self.current_scenario == SimulationScenario.FEEDING_TIME:
            # Feeding effects
            feeding_duration = self.scenario_settings.get('feeding_duration', 60)
            
            if elapsed_time < feeding_duration:
                if param == 'turbidity':
                    return base_value * 2.5  # Increased turbidity
                elif param == 'dissolved_oxygen':
                    return base_value * 0.85  # Slight DO decrease
                elif param == 'ammonia':
                    return base_value * 1.5  # Slight ammonia increase
        
        elif self.current_scenario == SimulationScenario.WEATHER_STORM:
            # Storm effects
            storm_intensity = math.sin(elapsed_time / 120 * math.pi)  # 4-minute storm cycle
            
            if param == 'temperature':
                return base_value - storm_intensity * 3.0  # Temperature drop
            elif param == 'turbidity':
                return base_value + storm_intensity * 40.0  # Increased turbidity
            elif param == 'water_level':
                return base_value + storm_intensity * 0.3  # Water level rise
        
        return base_value

    def _generate_parameter_value(self, param: str, elapsed_time: float) -> float:
        """Generate a realistic parameter value"""
        config = self.sensors[param]
        
        # Get base value
        base_value = self.base_values[param]
        
        # Apply daily cycle
        elapsed_hours = elapsed_time / 3600
        value = self._apply_daily_cycle(elapsed_hours, base_value, config)
        
        # Apply correlations
        value = self._apply_correlations(param, value)
        
        # Apply scenario effects
        scenario_elapsed = elapsed_time - (self.scenario_start_time - self.simulation_start_time) if self.scenario_start_time else elapsed_time
        value = self._apply_scenario_effects(param, value, scenario_elapsed)
        
        # Add noise and drift
        noise = random.gauss(0, config.noise_level * (config.max_value - config.min_value))
        drift = config.drift_rate * elapsed_time * random.uniform(-1, 1)
        value += noise + drift
        
        # Apply bounds
        value = max(config.min_value, min(config.max_value, value))
        
        # Update current value for correlations
        self.current_values[param] = value
        
        return round(value, 3)

    def _generate_sensor_reading(self) -> Dict[str, Any]:
        """Generate a complete sensor reading"""
        current_time = time.time()
        elapsed_time = current_time - self.simulation_start_time
        
        reading = {
            'pond_id': self.pond_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'data_source': 'simulator'
        }
        
        # Generate core parameters
        for param in self.sensors.keys():
            reading[param] = self._generate_parameter_value(param, elapsed_time)
        
        # Add optional parameters occasionally
        if random.random() < 0.6:
            reading['nitrite'] = round(random.uniform(0.01, 0.15), 3)
        
        if random.random() < 0.3:
            reading['fish_count'] = random.randint(80, 120)
            reading['fish_length'] = round(random.uniform(12.0, 18.0), 1)
            reading['fish_weight'] = round(random.uniform(0.8, 1.5), 2)

        return reading

    async def send_reading(self, reading: Dict[str, Any]) -> bool:
        """Send a sensor reading to the API"""
        payload_bytes = json.dumps(reading).encode('utf-8')
        timestamp = str(time.time())
        signature = self._generate_signature(timestamp, payload_bytes)

        headers = {
            'Content-Type': 'application/json',
            'X-API-Key': self.api_key,
            'X-Signature': signature,
            'X-Timestamp': timestamp
        }

        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/ingest",  # Fixed URL path
                data=payload_bytes,
                headers=headers
            ) as response:
                self.readings_sent += 1
                
                if response.status == 201:
                    result = await response.json()
                    self.successful_readings += 1
                    
                    # Check for anomaly detection
                    anomaly_status = "🚨 ANOMALY" if result.get('is_anomaly') else "✅ Normal"
                    quality_score = result.get('quality_score', 0)
                    
                    logger.info(
                        f"📊 Reading {self.readings_sent}: {anomaly_status} "
                        f"(Quality: {quality_score:.2f}) - "
                        f"T:{reading['temperature']:5.1f}°C "
                        f"pH:{reading['ph']:4.2f} "
                        f"O2:{reading['dissolved_oxygen']:4.1f}mg/L "
                        f"[{self.current_scenario.value}]"
                    )
                    
                    if result.get('is_anomaly'):
                        anomaly_details = result.get('anomaly_details', {})
                        logger.warning(f"🚨 Alert created: ID {anomaly_details.get('alert_id')}")
                    
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ HTTP {response.status}: {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Error sending reading: {e}")
            return False

    async def run_simulation(self, duration_seconds: int, interval_seconds: int):
        """Run the sensor simulation with automatic scenario changes"""
        logger.info("🔬 Starting Advanced Sensor Simulation")
        logger.info(f"🎯 Target: {self.base_url}")
        logger.info(f"🏊 Pond ID: {self.pond_id}")
        logger.info(f"⏱️  Duration: {duration_seconds}s, Interval: {interval_seconds}s")
        logger.info("=" * 60)
        
        end_time = time.time() + duration_seconds
        reading_count = 0
        last_scenario_change = time.time()
        
        while time.time() < end_time:
            reading_count += 1
            
            # Change scenarios periodically for testing
            if time.time() - last_scenario_change > 180:  # Change every 3 minutes
                scenarios = list(SimulationScenario)
                new_scenario = random.choice(scenarios)
                
                if new_scenario == SimulationScenario.ANOMALY_INJECTION:
                    self.set_scenario(new_scenario, anomaly_duration=90, anomaly_intensity=1.5)
                elif new_scenario == SimulationScenario.EQUIPMENT_FAILURE:
                    failure_types = ['aerator', 'heater', 'pump']
                    self.set_scenario(new_scenario, failure_type=random.choice(failure_types))
                elif new_scenario == SimulationScenario.FEEDING_TIME:
                    self.set_scenario(new_scenario, feeding_duration=45)
                else:
                    self.set_scenario(new_scenario)
                
                last_scenario_change = time.time()
            
            # Generate and send reading
            reading = self._generate_sensor_reading()
            success = await self.send_reading(reading)
            
            # Progress updates
            if reading_count % 20 == 0:
                elapsed = time.time() - self.simulation_start_time
                progress = (elapsed / duration_seconds) * 100
                logger.info(f"📈 Progress: {progress:5.1f}% ({reading_count} readings, {self.current_scenario.value})")
            
            await asyncio.sleep(interval_seconds)
        
        # Final summary
        logger.info("=" * 60)
        logger.info(f"✅ Simulation completed!")
        logger.info(f"📊 Total readings: {self.readings_sent}")
        logger.info(f"✅ Successful: {self.successful_readings}")
        logger.info(f"❌ Failed: {self.readings_sent - self.successful_readings}")
        if self.readings_sent > 0:
            logger.info(f"📈 Success rate: {(self.successful_readings/self.readings_sent)*100:.1f}%")