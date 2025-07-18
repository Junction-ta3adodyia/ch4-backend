#!/usr/bin/env python3
"""
Aquaculture API Test Client - Enhanced Debug Version with Anomaly Injection
"""

import asyncio
import aiohttp
import json
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import random
import time
import ssl

# Configuration
API_BASE_URL = "http://localhost:8000"
POND_ID = 1
NUM_READINGS = 50  # Increased for better anomaly testing
INTERVAL_SECONDS = 2  # 2 seconds between readings

# Authentication credentials
USERNAME = "admin"
PASSWORD = "saidani2003"

# Normal ranges for aquaculture parameters
NORMAL_RANGES = {
    'temperature': {'mean': 24.0, 'std': 1.5, 'min': 20.0, 'max': 30.0},
    'ph': {'mean': 7.2, 'std': 0.2, 'min': 6.5, 'max': 8.0},
    'dissolved_oxygen': {'mean': 7.5, 'std': 0.8, 'min': 5.0, 'max': 10.0},
    'turbidity': {'mean': 3.0, 'std': 1.0, 'min': 0.0, 'max': 8.0},
    'ammonia': {'mean': 0.05, 'std': 0.02, 'min': 0.0, 'max': 0.2},
    'nitrate': {'mean': 8.0, 'std': 2.0, 'min': 0.0, 'max': 20.0}
}

# Anomaly patterns to inject (designed to trigger Page-Hinkley detection)
ANOMALY_PATTERNS = [
    {
        'name': 'Temperature Spike (Equipment Malfunction)',
        'start_reading': 10,
        'duration': 8,
        'parameter': 'temperature',
        'change_magnitude': +8.0,  # Sudden +8°C increase
        'pattern_type': 'sudden_spike',
        'description': 'Simulates heating equipment malfunction'
    },
    {
        'name': 'pH Gradual Drop (Acid Rain)',
        'start_reading': 20,
        'duration': 12,
        'parameter': 'ph',
        'change_magnitude': -1.2,  # Gradual -1.2 pH drop
        'pattern_type': 'gradual_drift',
        'description': 'Simulates environmental acidification'
    },
    {
        'name': 'Oxygen Depletion (Algae Bloom)',
        'start_reading': 35,
        'duration': 6,
        'parameter': 'dissolved_oxygen',
        'change_magnitude': -4.0,  # Sudden -4 mg/L drop
        'pattern_type': 'sudden_drop',
        'description': 'Simulates algae bloom oxygen consumption'
    },
    {
        'name': 'Ammonia Spike (Overfeeding)',
        'start_reading': 42,
        'duration': 8,
        'parameter': 'ammonia',
        'change_magnitude': +1.5,  # Exponential increase to +1.5 mg/L
        'pattern_type': 'exponential_growth',
        'description': 'Simulates overfeeding waste accumulation'
    }
]

class AquacultureAPIClient:
    def __init__(self):
        self.base_url = API_BASE_URL
        self.access_token = None
        self.session = None
        self.base_values = {}  # Track values for continuity
        
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(ssl=False)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
        )
        print(f"🔗 Created HTTP session targeting: {self.base_url}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            print("🔗 HTTP session closed")
    
    async def test_connection(self) -> bool:
        """Test basic connectivity"""
        print(f"🔍 Testing connection to {self.base_url}")
        try:
            async with self.session.get(f"{self.base_url}/") as response:
                print(f"📡 Root endpoint response: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    print(f"📄 Response data: {data}")
                    return True
                else:
                    print(f"❌ Root endpoint failed: {response.status}")
                    return False
        except aiohttp.ClientConnectorError as e:
            print(f"❌ Connection error: {e}")
            print("💡 Is your backend server running on port 8000?")
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return False
    
    async def authenticate(self, username: str, password: str) -> bool:
        """Authenticate and get access token"""
        print(f"🔐 Attempting authentication for user: {username}")
        try:
            login_data = aiohttp.FormData()
            login_data.add_field('username', username)
            login_data.add_field('password', password)
            
            async with self.session.post(
                f"{self.base_url}/api/v1/auth/login",
                data=login_data
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    self.access_token = result.get('access_token')
                    if self.access_token:
                        print(f"✅ Authentication successful")
                        return True
                    else:
                        print(f"❌ No access token in response")
                        return False
                else:
                    response_text = await response.text()
                    print(f"❌ Authentication failed: {response.status} - {response_text}")
                    return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False
    
    async def check_health(self) -> bool:
        """Check API health"""
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    print(f"🏥 API Status: {health_data['status']}")
                    return True
                return False
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return False
    
    def generate_normal_value(self, parameter: str, reading_index: int) -> float:
        """Generate a normal value with temporal correlation"""
        config = NORMAL_RANGES[parameter]
        
        # Use previous value for continuity, or generate initial value
        if parameter in self.base_values:
            # Small random walk from previous value
            base_value = self.base_values[parameter] + np.random.normal(0, config['std'] * 0.2)
        else:
            # Generate initial value
            base_value = np.random.normal(config['mean'], config['std'])
        
        # Add daily cycles for temperature
        if parameter == 'temperature':
            hour_of_day = (reading_index * INTERVAL_SECONDS / 3600) % 24
            daily_variation = 1.5 * np.sin(2 * np.pi * hour_of_day / 24)
            base_value += daily_variation
        
        # Ensure within bounds
        return np.clip(base_value, config['min'], config['max'])
    
    def apply_anomaly(self, base_value: float, parameter: str, reading_index: int) -> float:
        """Apply anomaly pattern if applicable"""
        for anomaly in ANOMALY_PATTERNS:
            if (anomaly['parameter'] == parameter and 
                anomaly['start_reading'] <= reading_index < anomaly['start_reading'] + anomaly['duration']):
                
                progress = (reading_index - anomaly['start_reading']) / anomaly['duration']
                
                if anomaly['pattern_type'] == 'sudden_spike':
                    # Immediate spike, then gradual return
                    if progress < 0.3:  # First 30% - maintain spike
                        return base_value + anomaly['change_magnitude']
                    else:  # Gradual return to normal
                        return base_value + anomaly['change_magnitude'] * (1 - (progress - 0.3) / 0.7)
                
                elif anomaly['pattern_type'] == 'sudden_drop':
                    # Immediate drop, then gradual recovery
                    if progress < 0.4:  # First 40% - maintain drop
                        return base_value + anomaly['change_magnitude']
                    else:  # Gradual recovery
                        return base_value + anomaly['change_magnitude'] * (1 - (progress - 0.4) / 0.6)
                
                elif anomaly['pattern_type'] == 'gradual_drift':
                    # Smooth drift over time
                    return base_value + anomaly['change_magnitude'] * progress
                
                elif anomaly['pattern_type'] == 'exponential_growth':
                    # Exponential growth pattern
                    return base_value + anomaly['change_magnitude'] * (np.exp(progress * 2.5) - 1) / (np.exp(2.5) - 1)
        
        return base_value
    
    def generate_sensor_reading(self, reading_index: int, timestamp: datetime) -> Dict[str, Any]:
        """Generate a complete sensor reading with potential anomalies"""
        reading = {
            'pond_id': POND_ID,
            'timestamp': timestamp.isoformat(),
            'data_source': 'anomaly_test'
        }
        
        # Generate values for each parameter
        for parameter in NORMAL_RANGES.keys():
            normal_value = self.generate_normal_value(parameter, reading_index)
            final_value = self.apply_anomaly(normal_value, parameter, reading_index)
            reading[parameter] = round(final_value, 3)
            self.base_values[parameter] = final_value
        
        # Add optional parameters occasionally
        if random.random() < 0.7:
            reading['nitrite'] = round(random.uniform(0.0, 0.1), 3)
        
        if random.random() < 0.6:
            reading['salinity'] = round(random.uniform(0.0, 1.5), 2)
        
        if random.random() < 0.5:
            reading['water_level'] = round(random.uniform(1.8, 2.2), 2)
            reading['flow_rate'] = round(random.uniform(25.0, 35.0), 1)
        
        return reading
    
    async def send_sensor_reading(self, reading_data: Dict, reading_index: int) -> bool:
        """Send a sensor reading to the API"""
        if not self.access_token:
            return False
        
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            async with self.session.post(
                f"{self.base_url}/api/v1/data",
                headers=headers,
                json=reading_data
            ) as response:
                if response.status == 201:
                    result = await response.json()
                    
                    # Check if anomaly was detected
                    anomaly_status = "🚨 ANOMALY" if result.get('is_anomaly') else "✅ Normal"
                    
                    # Check if we expected an anomaly
                    expected_anomaly = self.is_anomaly_expected(reading_index)
                    expected_indicator = " (Expected)" if expected_anomaly else ""
                    
                    print(f"📊 Reading {reading_index:2d}: {anomaly_status}{expected_indicator} - "
                          f"T:{reading_data['temperature']:5.1f}°C "
                          f"pH:{reading_data['ph']:4.2f} "
                          f"O2:{reading_data['dissolved_oxygen']:4.1f} "
                          f"NH3:{reading_data['ammonia']:5.3f}")
                    
                    return True
                else:
                    print(f"❌ Error {response.status}: {await response.text()}")
                    return False
                    
        except Exception as e:
            print(f"❌ Request failed: {e}")
            return False
    
    def is_anomaly_expected(self, reading_index: int) -> bool:
        """Check if an anomaly is expected at this reading index"""
        for anomaly in ANOMALY_PATTERNS:
            if (anomaly['start_reading'] <= reading_index < 
                anomaly['start_reading'] + anomaly['duration']):
                return True
        return False
    
    def get_active_anomaly(self, reading_index: int) -> Optional[str]:
        """Get the name of active anomaly at this reading index"""
        for anomaly in ANOMALY_PATTERNS:
            if (anomaly['start_reading'] <= reading_index < 
                anomaly['start_reading'] + anomaly['duration']):
                return anomaly['name']
        return None
    
    async def run_full_simulation(self):
        """Run the complete sensor data simulation with anomalies"""
        print("🔬 Starting Aquaculture Sensor Simulation with Anomalies")
        print(f"🎯 Target: {self.base_url}")
        print(f"📊 Readings: {NUM_READINGS}")
        print(f"⏱️  Interval: {INTERVAL_SECONDS}s")
        print("=" * 70)
        
        # Authentication
        if not await self.authenticate(USERNAME, PASSWORD):
            print("❌ Authentication failed")
            return
        
        # Print anomaly schedule
        print("\n🧪 Scheduled Anomalies:")
        for i, anomaly in enumerate(ANOMALY_PATTERNS, 1):
            start_time = anomaly['start_reading'] * INTERVAL_SECONDS
            duration_time = anomaly['duration'] * INTERVAL_SECONDS
            print(f"   {i}. {anomaly['name']}")
            print(f"      Parameter: {anomaly['parameter']}")
            print(f"      Readings: {anomaly['start_reading']}-{anomaly['start_reading'] + anomaly['duration']}")
            print(f"      Duration: {duration_time}s")
            print(f"      Magnitude: {anomaly['change_magnitude']:+.1f}")
            print(f"      Type: {anomaly['pattern_type']}")
        
        print("\n" + "=" * 70)
        print("📡 Starting data transmission...")
        
        success_count = 0
        detected_anomalies = 0
        expected_anomalies = sum(a['duration'] for a in ANOMALY_PATTERNS)
        
        start_time = datetime.now(timezone.utc)
        
        for reading_index in range(NUM_READINGS):
            # Calculate timestamp
            timestamp = start_time + timedelta(seconds=reading_index * INTERVAL_SECONDS)
            
            # Check for anomaly transitions
            active_anomaly = self.get_active_anomaly(reading_index)
            if active_anomaly and (reading_index == 0 or not self.get_active_anomaly(reading_index - 1)):
                print(f"\n🚨 STARTING ANOMALY: {active_anomaly}")
            elif not active_anomaly and reading_index > 0 and self.get_active_anomaly(reading_index - 1):
                print(f"✅ Anomaly ended\n")
            
            # Generate and send reading
            reading = self.generate_sensor_reading(reading_index, timestamp)
            
            if await self.send_sensor_reading(reading, reading_index):
                success_count += 1
            
            # Progress updates
            if (reading_index + 1) % 10 == 0:
                progress = (reading_index + 1) / NUM_READINGS * 100
                print(f"\n📈 Progress: {progress:5.1f}% ({reading_index + 1}/{NUM_READINGS})\n")
            
            # Wait before next reading
            await asyncio.sleep(INTERVAL_SECONDS)
        
        print("\n" + "=" * 70)
        print(f"✅ Simulation completed!")
        print(f"📊 Success rate: {success_count}/{NUM_READINGS}")
        print(f"🚨 Expected anomaly readings: {expected_anomalies}")
        print(f"⏱️  Total duration: {NUM_READINGS * INTERVAL_SECONDS}s")
        
        print(f"\n🔍 Check your backend logs and dashboard for:")
        print(f"   • Page-Hinkley anomaly detections")
        print(f"   • Alert notifications")
        print(f"   • Email notifications (if configured)")
    
    async def run_debug_test(self):
        """Run a quick debug test"""
        print("🐛 Starting Debug Test")
        print("=" * 50)
        
        # Step 1: Test basic connection
        print("\n1️⃣ Testing basic connection...")
        if not await self.test_connection():
            print("❌ Basic connection failed")
            return False
        
        # Step 2: Test health endpoint
        print("\n2️⃣ Testing health endpoint...")
        if not await self.check_health():
            print("❌ Health check failed")
            return False
        
        # Step 3: Test authentication
        print("\n3️⃣ Testing authentication...")
        if not await self.authenticate(USERNAME, PASSWORD):
            print("❌ Authentication failed")
            return False
        
        # Step 4: Test sensor data endpoint
        print("\n4️⃣ Testing sensor data endpoint...")
        test_data = {
            'pond_id': POND_ID,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'temperature': 25.0,
            'ph': 7.2,
            'dissolved_oxygen': 7.5,
            'data_source': 'debug_test'
        }
        
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            async with self.session.post(
                f"{self.base_url}/api/v1/data",
                headers=headers,
                json=test_data
            ) as response:
                if response.status == 201:
                    print("✅ All tests passed!")
                    return True
                else:
                    print(f"❌ Sensor data test failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def main():
    """Main function"""
    print("🐛 Aquaculture API Test Client")
    print("Choose mode:")
    print("1. Quick debug test")
    print("2. Full simulation with anomalies")
    
    try:
        choice = input("Enter choice (1 or 2): ").strip()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        return
    
    async with AquacultureAPIClient() as client:
        if choice == "1":
            await client.run_debug_test()
        elif choice == "2":
            await client.run_full_simulation()
        else:
            print("❌ Invalid choice")


if __name__ == "__main__":
    asyncio.run(main())