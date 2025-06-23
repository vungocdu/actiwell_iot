#!/usr/bin/env python3
"""
Device Integration Test
======================
Usage:
    python test_device_integration.py
    python test_device_integration.py --port /dev/ttyUSB0 --device tanita
    python test_device_integration.py --discover
"""

import sys
import argparse
import logging
import time
from datetime import datetime
from typing import Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    # Import device protocols
    from devices import (
        TanitaProtocol,
        InBodyProtocol, 
        create_device_protocol,
        get_supported_devices
    )
    
    # Import device manager
    from core import DeviceManager, initialize_core_managers
    
    logger.info("✅ Successfully imported Actiwell device modules")
    
except ImportError as e:
    logger.error(f"❌ Failed to import required modules: {e}")
    logger.error("Make sure you're running from the actiwell_backend directory")
    sys.exit(1)

def test_device_discovery():
    """Test automatic device discovery"""
    logger.info("🔍 Testing device discovery...")
    
    try:
        device_manager = DeviceManager()
        discovered_devices = device_manager.discover_devices()
        
        if discovered_devices:
            logger.info(f"✅ Discovered {len(discovered_devices)} devices:")
            for port, device_info in discovered_devices.items():
                logger.info(f"  📱 {device_info.device_type} on {port} (status: {device_info.status})")
            return list(discovered_devices.keys())
        else:
            logger.warning("⚠️ No devices discovered")
            return []
            
    except Exception as e:
        logger.error(f"❌ Device discovery failed: {e}")
        return []

def test_single_device(port: str, device_type: str = 'tanita', timeout: float = 60.0):
    """Test single device connection and measurement"""
    logger.info(f"🧪 Testing {device_type} device on {port}")
    
    try:
        # Create device protocol
        if device_type.lower() in ['tanita', 'tanita_mc780ma']:
            device = TanitaProtocol(port)
        elif device_type.lower() in ['inbody', 'inbody_270']:
            device = InBodyProtocol(port)
        else:
            device = create_device_protocol(device_type, port)
        
        logger.info(f"📡 Created {device.device_type} protocol")
        
        # Test connection
        logger.info("🔌 Attempting to connect...")
        if device.connect():
            logger.info("✅ Device connected successfully")
            
            # Get device info
            device_info = device.get_device_info()
            logger.info(f"📋 Device Info:")
            logger.info(f"  Model: {device_info.get('model', 'Unknown')}")
            logger.info(f"  State: {device_info.get('state', 'Unknown')}")
            logger.info(f"  Port: {device_info.get('port', 'Unknown')}")
            
            # Test measurement reading
            logger.info(f"⏳ Waiting for measurement (timeout: {timeout}s)")
            logger.info("📏 Please perform a measurement on the device...")
            
            if device_type.lower() in ['tanita', 'tanita_mc780ma']:
                logger.info("💡 For Tanita MC-780MA:")
                logger.info("   1. Enter customer phone number as ID (e.g., 0965385123)")
                logger.info("   2. Step on scale barefoot")
                logger.info("   3. Stay still until measurement completes")
                logger.info("   4. Data will be transmitted automatically")
            else:
                logger.info("💡 For InBody 270:")
                logger.info("   1. Follow device instructions on screen")
                logger.info("   2. Enter customer information if prompted")
                logger.info("   3. Complete measurement process")
            
            measurement = device.read_measurement(timeout=timeout)
            
            if measurement:
                logger.info("🎉 Measurement received successfully!")
                print_measurement_summary(measurement)
                
                # Validate measurement
                errors = measurement.validate()
                if errors:
                    logger.warning(f"⚠️ Validation warnings: {', '.join(errors)}")
                else:
                    logger.info("✅ Measurement validation passed")
                
                return True
            else:
                logger.warning("⏰ No measurement received within timeout period")
                return False
                
        else:
            logger.error("❌ Failed to connect to device")
            return False
            
    except Exception as e:
        logger.error(f"❌ Device test failed: {e}")
        return False
        
    finally:
        try:
            device.disconnect()
            logger.info("🔌 Device disconnected")
        except:
            pass

def print_measurement_summary(measurement):
    """Print formatted measurement summary"""
    print("\n" + "="*60)
    print("📊 MEASUREMENT SUMMARY")
    print("="*60)
    
    print(f"🆔 Customer: {measurement.customer_phone or 'Unknown'}")
    print(f"📅 Timestamp: {measurement.measurement_timestamp}")
    print(f"🔧 Device: {measurement.device_type} ({measurement.device_id})")
    
    print(f"\n📏 BASIC MEASUREMENTS:")
    print(f"  Weight: {measurement.weight_kg} kg")
    print(f"  Height: {measurement.height_cm} cm")
    print(f"  BMI: {measurement.bmi}")
    print(f"  Age: {measurement.age}")
    print(f"  Gender: {measurement.gender}")
    
    print(f"\n🏋️ BODY COMPOSITION:")
    print(f"  Body Fat: {measurement.body_fat_percent}%")
    print(f"  Muscle Mass: {measurement.muscle_mass_kg} kg")
    print(f"  Bone Mass: {measurement.bone_mass_kg} kg")
    print(f"  Total Body Water: {measurement.total_body_water_kg} kg ({measurement.total_body_water_percent}%)")
    print(f"  Visceral Fat Rating: {measurement.visceral_fat_rating}")
    print(f"  Metabolic Age: {measurement.metabolic_age}")
    print(f"  BMR: {measurement.bmr_kcal} kcal")
    
    # Segmental analysis if available
    if any([measurement.right_arm_muscle_kg, measurement.left_arm_muscle_kg, 
            measurement.trunk_muscle_kg, measurement.right_leg_muscle_kg, 
            measurement.left_leg_muscle_kg]):
        print(f"\n🗂️ SEGMENTAL ANALYSIS:")
        print(f"  Right Arm: {measurement.right_arm_muscle_kg} kg ({measurement.right_arm_fat_percent}% fat)")
        print(f"  Left Arm: {measurement.left_arm_muscle_kg} kg ({measurement.left_arm_fat_percent}% fat)")
        print(f"  Trunk: {measurement.trunk_muscle_kg} kg ({measurement.trunk_fat_percent}% fat)")
        print(f"  Right Leg: {measurement.right_leg_muscle_kg} kg ({measurement.right_leg_fat_percent}% fat)")
        print(f"  Left Leg: {measurement.left_leg_muscle_kg} kg ({measurement.left_leg_fat_percent}% fat)")
    
    print(f"\n📈 DATA QUALITY:")
    print(f"  Quality: {measurement.measurement_quality}")
    print(f"  Completeness: {measurement.data_completeness:.1%}")
    print(f"  Status: {measurement.status.value if measurement.status else 'Unknown'}")
    
    if measurement.processing_notes:
        print(f"  Notes: {measurement.processing_notes}")
    
    print("="*60)

def test_device_manager():
    """Test device manager functionality"""
    logger.info("🎛️ Testing Device Manager...")
    
    try:
        # Initialize device manager
        device_manager = DeviceManager()
        
        # Test device discovery
        discovered = device_manager.discover_devices()
        logger.info(f"📱 Discovered {len(discovered)} devices")
        
        # Test connecting to all discovered devices
        if discovered:
            results = device_manager.connect_all_discovered_devices()
            connected_count = sum(results.values())
            logger.info(f"🔌 Connected to {connected_count}/{len(results)} devices")
            
            # Get device status
            status = device_manager.get_device_status()
            logger.info(f"📊 Manager Statistics:")
            logger.info(f"  Total devices: {status['manager_stats']['total_devices']}")
            logger.info(f"  Connected devices: {status['manager_stats']['connected_devices']}")
            
            return True
        else:
            logger.warning("⚠️ No devices to test with Device Manager")
            return False
            
    except Exception as e:
        logger.error(f"❌ Device Manager test failed: {e}")
        return False

def main():
    """Main test function"""
    parser = argparse.ArgumentParser(description='Test Actiwell device integration')
    parser.add_argument('--port', help='Serial port to test (e.g., /dev/ttyUSB0)')
    parser.add_argument('--device', choices=['tanita', 'inbody'], default='tanita',
                       help='Device type to test')
    parser.add_argument('--timeout', type=float, default=90.0,
                       help='Measurement timeout in seconds')
    parser.add_argument('--discover', action='store_true',
                       help='Run device discovery only')
    parser.add_argument('--manager', action='store_true',
                       help='Test device manager functionality')
    
    args = parser.parse_args()
    
    logger.info("🚀 Starting Actiwell Device Integration Test")
    logger.info("="*50)
    
    # Show supported devices
    supported = get_supported_devices()
    logger.info("📋 Supported Devices:")
    for device_type, info in supported.items():
        status = "✅ Available" if info['available'] else "❌ Not Available"
        logger.info(f"  {info['name']}: {status}")
    
    success_count = 0
    total_tests = 0
    
    # Test device discovery
    if args.discover or not args.port:
        total_tests += 1
        discovered_ports = test_device_discovery()
        if discovered_ports:
            success_count += 1
            
            # If no specific port given, use first discovered
            if not args.port and discovered_ports:
                args.port = discovered_ports[0]
                logger.info(f"🎯 Using discovered port: {args.port}")
    
    # Test device manager
    if args.manager:
        total_tests += 1
        if test_device_manager():
            success_count += 1
    
    # Test specific device
    if args.port:
        total_tests += 1
        if test_single_device(args.port, args.device, args.timeout):
            success_count += 1
    
    # Summary
    logger.info("\n" + "="*50)
    logger.info("📋 TEST SUMMARY")
    logger.info("="*50)
    logger.info(f"Tests run: {total_tests}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {total_tests - success_count}")
    logger.info(f"Success rate: {success_count/max(1,total_tests)*100:.1f}%")
    
    if success_count == total_tests:
        logger.info("🎉 All tests passed! Device integration is working correctly.")
        return 0
    elif success_count > 0:
        logger.warning("⚠️ Some tests failed. Check device connections and configuration.")
        return 1
    else:
        logger.error("❌ All tests failed. Check device setup and connections.")
        return 2

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)