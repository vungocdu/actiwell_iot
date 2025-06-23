#!/usr/bin/env python3
"""
Advanced Device Communication Utilities
Legacy compatibility layer for device communication
This module provides backward compatibility and utility functions for device communication.

Note: This module is maintained for compatibility. New implementations should use
the dedicated protocol classes in the devices package.
"""

import serial
import time
import logging
import threading
import queue
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Callable, Any
from enum import Enum

# Import new device protocols
from ..devices import (
    DeviceProtocol,
    DeviceState, 
    MeasurementStatus,
    MeasurementData,
    TanitaProtocol,
    InBodyProtocol,
    create_device_protocol
)

logger = logging.getLogger(__name__)

# Legacy compatibility aliases
class DeviceConnectionState(Enum):
    """Legacy device state enum for backward compatibility"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting" 
    CONNECTED = "connected"
    MEASURING = "measuring"
    ERROR = "error"

class CommunicationConfig:
    """
    Legacy communication configuration class
    Maintained for backward compatibility
    """
    def __init__(self, port: str, baudrate: int = 9600, **kwargs):
        self.port = port
        self.baudrate = baudrate
        self.bytesize = kwargs.get('bytesize', serial.EIGHTBITS)
        self.parity = kwargs.get('parity', serial.PARITY_NONE)
        self.stopbits = kwargs.get('stopbits', serial.STOPBITS_ONE)
        self.timeout = kwargs.get('timeout', 2.0)
        self.write_timeout = kwargs.get('write_timeout', 1.0)
        self.rtscts = kwargs.get('rtscts', False)
        self.dsrdtr = kwargs.get('dsrdtr', False)
        self.xonxoff = kwargs.get('xonxoff', False)

class LegacyDeviceHandler:
    """
    Legacy device handler class
    Provides compatibility layer for existing code that uses the old communication pattern
    """
    
    def __init__(self, device_type: str, port: str, **kwargs):
        """
        Initialize legacy device handler
        
        Args:
            device_type: Type of device ('tanita' or 'inbody')
            port: Serial port path
            **kwargs: Additional configuration
        """
        self.device_type = device_type
        self.port = port
        self.config = CommunicationConfig(port, **kwargs)
        
        # Create modern device protocol
        try:
            self.device_protocol = create_device_protocol(device_type, port, **kwargs)
            logger.info(f"Created modern protocol for {device_type} on {port}")
        except Exception as e:
            logger.error(f"Failed to create modern protocol: {e}")
            self.device_protocol = None
        
        # Legacy state tracking
        self.state = DeviceConnectionState.DISCONNECTED
        self.is_connected = False
        
        # Legacy callbacks
        self.measurement_callback = None
        self.status_callback = None
        self.error_callback = None
        
        logger.warning("Using legacy device handler - consider migrating to modern device protocols")
    
    def connect(self) -> bool:
        """Legacy connect method"""
        if self.device_protocol:
            try:
                success = self.device_protocol.connect()
                if success:
                    self.state = DeviceConnectionState.CONNECTED
                    self.is_connected = True
                    
                    # Set up callbacks
                    self.device_protocol.set_callbacks(
                        measurement_cb=self._handle_measurement,
                        status_cb=self._handle_status,
                        error_cb=self._handle_error
                    )
                    
                    logger.info(f"Legacy handler connected to {self.device_type}")
                    return True
                else:
                    self.state = DeviceConnectionState.ERROR
                    return False
            except Exception as e:
                logger.error(f"Legacy connection error: {e}")
                return False
        
        return False
    
    def disconnect(self):
        """Legacy disconnect method"""
        if self.device_protocol:
            self.device_protocol.disconnect()
        
        self.state = DeviceConnectionState.DISCONNECTED
        self.is_connected = False
        logger.info(f"Legacy handler disconnected from {self.device_type}")
    
    def read_measurement(self, timeout: float = 30.0) -> Optional[Dict]:
        """
        Legacy read measurement method
        Returns measurement as dictionary for backward compatibility
        """
        if not self.device_protocol:
            return None
        
        try:
            measurement = self.device_protocol.read_measurement(timeout)
            if measurement:
                # Convert to legacy dictionary format
                return self._convert_to_legacy_format(measurement)
            return None
        except Exception as e:
            logger.error(f"Legacy measurement read error: {e}")
            return None
    
    def start_measurement(self, customer_id: str = "") -> bool:
        """Legacy start measurement method"""
        if self.device_protocol:
            return self.device_protocol.start_measurement(customer_id)
        return False
    
    def set_callbacks(self, measurement_cb=None, status_cb=None, error_cb=None):
        """Legacy callback setter"""
        self.measurement_callback = measurement_cb
        self.status_callback = status_cb  
        self.error_callback = error_cb
    
    def _handle_measurement(self, measurement: MeasurementData):
        """Handle measurement from modern protocol"""
        if self.measurement_callback:
            try:
                legacy_data = self._convert_to_legacy_format(measurement)
                self.measurement_callback(legacy_data)
            except Exception as e:
                logger.error(f"Legacy measurement callback error: {e}")
    
    def _handle_status(self, device_id: str, status: str):
        """Handle status from modern protocol"""
        if self.status_callback:
            try:
                self.status_callback(status)
            except Exception as e:
                logger.error(f"Legacy status callback error: {e}")
    
    def _handle_error(self, device_id: str, error: str):
        """Handle error from modern protocol"""
        if self.error_callback:
            try:
                self.error_callback(error)
            except Exception as e:
                logger.error(f"Legacy error callback error: {e}")
    
    def _convert_to_legacy_format(self, measurement: MeasurementData) -> Dict:
        """Convert modern MeasurementData to legacy dictionary format"""
        return {
            'device_id': measurement.device_id,
            'device_type': measurement.device_type,
            'timestamp': measurement.measurement_timestamp,
            'customer_id': measurement.customer_phone or measurement.customer_id,
            'customer_phone': measurement.customer_phone,
            
            # Basic measurements
            'weight_kg': measurement.weight_kg,
            'height_cm': measurement.height_cm,
            'bmi': measurement.bmi,
            'age': measurement.age,
            'gender': measurement.gender,
            
            # Body composition
            'body_fat_percent': measurement.body_fat_percent,
            'muscle_mass_kg': measurement.muscle_mass_kg,
            'bone_mass_kg': measurement.bone_mass_kg,
            'total_body_water_kg': measurement.total_body_water_kg,
            'total_body_water_percent': measurement.total_body_water_percent,
            'visceral_fat_rating': measurement.visceral_fat_rating,
            'metabolic_age': measurement.metabolic_age,
            'bmr_kcal': measurement.bmr_kcal,
            
            # Segmental data
            'right_arm_muscle_kg': measurement.right_arm_muscle_kg,
            'left_arm_muscle_kg': measurement.left_arm_muscle_kg,
            'trunk_muscle_kg': measurement.trunk_muscle_kg,
            'right_leg_muscle_kg': measurement.right_leg_muscle_kg,
            'left_leg_muscle_kg': measurement.left_leg_muscle_kg,
            
            'right_arm_fat_percent': measurement.right_arm_fat_percent,
            'left_arm_fat_percent': measurement.left_arm_fat_percent,
            'trunk_fat_percent': measurement.trunk_fat_percent,
            'right_leg_fat_percent': measurement.right_leg_fat_percent,
            'left_leg_fat_percent': measurement.left_leg_fat_percent,
            
            # Technical data
            'impedance_50khz': measurement.impedance_50khz,
            'phase_angle': measurement.phase_angle,
            
            # Quality and metadata
            'measurement_quality': measurement.measurement_quality,
            'data_completeness': measurement.data_completeness,
            'validation_errors': measurement.validation_errors,
            'status': measurement.status.value if measurement.status else 'unknown',
            'raw_data': measurement.raw_data,
            'processing_notes': measurement.processing_notes
        }
    
    def get_device_info(self) -> Dict:
        """Legacy device info method"""
        if self.device_protocol:
            return self.device_protocol.get_device_info()
        
        return {
            'device_type': self.device_type,
            'port': self.port,
            'state': self.state.value,
            'is_connected': self.is_connected,
            'legacy_handler': True
        }

# Legacy factory functions for backward compatibility
def create_tanita_handler(port: str, **kwargs) -> LegacyDeviceHandler:
    """
    Create legacy Tanita device handler
    
    Args:
        port: Serial port path
        **kwargs: Additional configuration
        
    Returns:
        LegacyDeviceHandler: Configured for Tanita device
    """
    logger.warning("create_tanita_handler is deprecated - use TanitaProtocol directly")
    return LegacyDeviceHandler('tanita_mc780ma', port, **kwargs)

def create_inbody_handler(port: str, **kwargs) -> LegacyDeviceHandler:
    """
    Create legacy InBody device handler
    
    Args:
        port: Serial port path
        **kwargs: Additional configuration
        
    Returns:
        LegacyDeviceHandler: Configured for InBody device
    """
    logger.warning("create_inbody_handler is deprecated - use InBodyProtocol directly")
    return LegacyDeviceHandler('inbody_270', port, **kwargs)

def scan_for_devices() -> List[Dict]:
    """
    Legacy device scanning function
    
    Returns:
        List[Dict]: List of discovered devices in legacy format
    """
    logger.warning("scan_for_devices is deprecated - use DeviceManager.discover_devices()")
    
    devices = []
    try:
        # Use modern device discovery through DeviceManager
        from .device_manager import DeviceManager
        
        manager = DeviceManager()
        discovered = manager.discover_devices()
        
        for port, device_info in discovered.items():
            devices.append({
                'port': port,
                'device_type': device_info.device_type,
                'device_id': device_info.device_id,
                'status': device_info.status,
                'last_seen': device_info.last_seen,
                'legacy_format': True
            })
    
    except Exception as e:
        logger.error(f"Legacy device scan error: {e}")
    
    return devices

def test_device_communication(port: str, device_type: str = 'tanita') -> bool:
    """
    Legacy communication test function
    
    Args:
        port: Serial port to test
        device_type: Type of device to test
        
    Returns:
        bool: True if communication successful
    """
    logger.warning("test_device_communication is deprecated - use modern protocol classes")
    
    try:
        handler = LegacyDeviceHandler(device_type, port)
        if handler.connect():
            handler.disconnect()
            return True
        return False
    except Exception as e:
        logger.error(f"Legacy communication test error: {e}")
        return False

# Migration utilities
def migrate_to_modern_protocol(legacy_handler: LegacyDeviceHandler) -> Optional[DeviceProtocol]:
    """
    Migrate from legacy handler to modern protocol
    
    Args:
        legacy_handler: Legacy device handler instance
        
    Returns:
        DeviceProtocol: Modern protocol instance or None
    """
    try:
        if legacy_handler.device_protocol:
            logger.info("Legacy handler already uses modern protocol internally")
            return legacy_handler.device_protocol
        
        # Create new modern protocol
        protocol = create_device_protocol(
            legacy_handler.device_type,
            legacy_handler.port
        )
        
        logger.info(f"Migrated legacy handler to modern protocol: {legacy_handler.device_type}")
        return protocol
        
    except Exception as e:
        logger.error(f"Migration error: {e}")
        return None

def get_migration_guide() -> Dict[str, Any]:
    """
    Get migration guide for updating from legacy to modern protocols
    
    Returns:
        Dict: Migration guide with examples
    """
    return {
        'overview': 'Migration from legacy device communication to modern protocols',
        'benefits': [
            'Better error handling and recovery',
            'Comprehensive data extraction (152+ parameters for Tanita)',
            'Standardized measurement data format',
            'Built-in device monitoring and health checks',
            'Thread-safe communication',
            'Automatic device discovery and management'
        ],
        'migration_steps': {
            '1_replace_imports': {
                'old': 'from device_communication import create_tanita_handler',
                'new': 'from actiwell_backend.devices import TanitaProtocol'
            },
            '2_replace_creation': {
                'old': 'handler = create_tanita_handler("/dev/ttyUSB0")',
                'new': 'protocol = TanitaProtocol("/dev/ttyUSB0")'
            },
            '3_replace_connection': {
                'old': 'if handler.connect():',
                'new': 'if protocol.connect():'
            },
            '4_replace_measurement': {
                'old': 'data = handler.read_measurement()',
                'new': 'measurement = protocol.read_measurement()'
            },
            '5_update_data_access': {
                'old': 'weight = data["weight_kg"]',
                'new': 'weight = measurement.weight_kg'
            }
        },
        'new_features': {
            'comprehensive_data': 'Access to all 152+ Tanita parameters',
            'data_validation': 'Built-in measurement validation',
            'device_monitoring': 'Automatic health monitoring',
            'error_recovery': 'Automatic reconnection on errors',
            'standardized_format': 'Consistent MeasurementData structure'
        }
    }

# Deprecation warnings
logger.warning(
    "device_communication.py is deprecated and maintained for compatibility only. "
    "New code should use the dedicated protocol classes in the devices package."
)

logger.info("Legacy device communication module loaded with modern protocol backend")