"""
Command-line sensor simulator tool
Usage: python sensor_simulator_cli.py --help
"""

import argparse
import asyncio
import sys
import json
from pathlib import Path

# Add the parent directory to the path to import app modules
sys.path.append(str(Path(__file__).parent.parent))

from app.services.sensor_simulator import AquacultureSensorSimulator, SimulationScenario


async def main():
    parser = argparse.ArgumentParser(description='Aquaculture Sensor Simulator CLI')
    
    # Basic configuration
    parser.add_argument('--url', default='http://127.0.0.1:8000', help='API base URL')
    parser.add_argument('--pond-id', type=int, required=True, help='Pond ID')
    parser.add_argument('--api-key', required=True, help='API key for authentication')
    parser.add_argument('--secret', required=True, help='Secret key for signing')
    
    # Simulation parameters
    parser.add_argument('--duration', type=int, default=300, help='Simulation duration (seconds)')
    parser.add_argument('--interval', type=int, default=10, help='Reading interval (seconds)')
    parser.add_argument('--scenario', choices=[s.value for s in SimulationScenario], 
                       default=SimulationScenario.NORMAL.value, help='Simulation scenario')
    
    # Scenario-specific options
    parser.add_argument('--anomaly-duration', type=int, default=120, 
                       help='Duration of anomaly injection (seconds)')
    parser.add_argument('--anomaly-intensity', type=float, default=1.5, 
                       help='Intensity of anomaly injection')
    parser.add_argument('--failure-type', choices=['aerator', 'heater', 'pump'], 
                       default='aerator', help='Type of equipment failure to simulate')
    
    # Output options
    parser.add_argument('--quiet', action='store_true', help='Suppress output except errors')
    parser.add_argument('--log-file', help='Log output to file')
    
    args = parser.parse_args()
    
    # Configure logging
    if args.log_file:
        import logging
        logging.basicConfig(
            level=logging.INFO if not args.quiet else logging.ERROR,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(args.log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
    
    # Create and configure simulator
    simulator = AquacultureSensorSimulator(
        base_url=args.url,
        api_key=args.api_key,
        secret_key=args.secret,
        pond_id=args.pond_id
    )
    
    # Set scenario
    scenario = SimulationScenario(args.scenario)
    scenario_settings = {}
    
    if scenario == SimulationScenario.ANOMALY_INJECTION:
        scenario_settings = {
            'anomaly_duration': args.anomaly_duration,
            'anomaly_intensity': args.anomaly_intensity
        }
    elif scenario == SimulationScenario.EQUIPMENT_FAILURE:
        scenario_settings = {
            'failure_type': args.failure_type
        }
    
    simulator.set_scenario(scenario, **scenario_settings)
    
    # Run simulation
    try:
        async with simulator:
            await simulator.run_simulation(args.duration, args.interval)
    except KeyboardInterrupt:
        print("\n🛑 Simulation interrupted by user")
    except Exception as e:
        print(f"💥 Simulation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())