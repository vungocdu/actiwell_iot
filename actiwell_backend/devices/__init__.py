"""
Device protocols package initialization
========================================

This package contains device communication protocols for body composition analyzers.
Supports Tanita MC-780MA and InBody 270 devices with comprehensive data extraction.

Components:
- base_protocol: Abstract base class for all device protocols
- tanita_protocol: Tanita MC-780MA implementation with 152+ parameters
- inbody_protocol: InBody 270 implementation with segmental analysis
- Device discovery and management utilities

Author: Actiwell Development Team
Version: 2.0.0
"""

import logging

# Setup logger for devices package
logger = logging.getLogger(__name__)

# Import device protocols with comprehensive error handling
try:
    from .base_protocol import (
        DeviceProtocol, 
        DeviceState, 
        MeasurementStatus, 
        MeasurementData, 
        DeviceCapabilities
    )
    logger.debug("Base protocol components imported successfully")
except ImportError as e:
    logger.error(f"Failed to import base protocol: {e}")
    DeviceProtocol = None
    DeviceState = None
    MeasurementStatus = None
    MeasurementData = None
    DeviceCapabilities = None

try:
    from .tanita_protocol import TanitaProtocol, TanitaCapabilities
    logger.debug("Tanita MC-780MA protocol imported successfully")
except ImportError as e:
    logger.error(f"Failed to import Tanita protocol: {e}")
    TanitaProtocol = None
    TanitaCapabilities = None

try:
    from .inbody_protocol import InBodyProtocol, InBodyCapabilities, InBodyDataFormat
    logger.debug("InBody 270 protocol imported successfully")
except ImportError as e:
    logger.error(f"Failed to import InBody protocol: {e}")
    InBodyProtocol = None
    InBodyCapabilities = None
    InBodyDataFormat = None

# Define public API
__all__ = [
    # Base protocol components
    'DeviceProtocol',
    'DeviceState', 
    'MeasurementStatus',
    'MeasurementData',
    'DeviceCapabilities',
    
    # Tanita MC-780MA
    'TanitaProtocol',
    'TanitaCapabilities',
    
    # InBody 270
    'InBodyProtocol',
    'InBodyCapabilities',
    'InBodyDataFormat',
    
    # Utility functions
    'create_device_protocol',
    'get_supported_devices',
    'validate_device_capabilities'
]

def create_device_protocol(device_type: str, port: str, **kwargs) -> DeviceProtocol:
    """
    Factory function to create appropriate device protocol
    
    Args:
        device_type: Type of device ('tanita_mc780ma', 'inbody_270')
        port: Serial port path
        **kwargs: Additional configuration parameters
        
    Returns:
        DeviceProtocol: Initialized device protocol instance
        
    Raises:
        ValueError: If device type is not supported
        ImportError: If required protocol class is not available
    """
    device_type = device_type.lower()
    
    if device_type in ['tanita', 'tanita_mc780ma', 'mc780ma', 'mc-780ma']:
        if TanitaProtocol is None:
            raise ImportError("Tanita protocol not available")
        
        logger.info(f"Creating Tanita MC-780MA protocol for {port}")
        return TanitaProtocol(port, **kwargs)
    
    elif device_type in ['inbody', 'inbody_270', 'inbody270']:
        if InBodyProtocol is None:
            raise ImportError("InBody protocol not available")
        
        logger.info(f"Creating InBody 270 protocol for {port}")
        return InBodyProtocol(port, **kwargs)
    
    else:
        # Default to Tanita for unknown devices (most common)
        if TanitaProtocol is None:
            raise ImportError("No device protocols available")
        
        logger.warning(f"Unknown device type '{device_type}', defaulting to Tanita MC-780MA")
        return TanitaProtocol(port, **kwargs)

def get_supported_devices() -> dict:
    """
    Get information about supported devices
    
    Returns:
        dict: Dictionary of supported device types and their availability
    """
    supported = {
        'tanita_mc780ma': {
            'name': 'Tanita MC-780MA',
            'manufacturer': 'TANITA Corporation',
            'available': TanitaProtocol is not None,
            'description': 'Multi-frequency bioelectrical impedance analyzer with 152+ parameters',
            'features': [
                'Body fat percentage',
                'Muscle mass',
                'Bone mass', 
                'Total body water',
                'Visceral fat rating',
                'Metabolic age',
                'BMR (Basal Metabolic Rate)',
                'Segmental analysis (5 body parts)',
                'Multi-frequency impedance (6 frequencies)',
                'Phase angle measurements'
            ],
            'communication': ['RS-232C', 'USB'],
            'measurement_time': '30-60 seconds'
        },
        'inbody_270': {
            'name': 'InBody 270',
            'manufacturer': 'InBody Co., Ltd.',
            'available': InBodyProtocol is not None,
            'description': 'Professional body composition analyzer with touchscreen interface',
            'features': [
                'Body fat mass',
                'Skeletal muscle mass',
                'Total body water',
                'Protein mass',
                'Mineral mass',
                'Visceral fat area',
                'Segmental lean analysis',
                'Body composition history'
            ],
            'communication': ['RS-232C', 'USB', 'LAN', 'Bluetooth', 'Wi-Fi'],
            'measurement_time': '15 seconds'
        }
    }
    
    return supported

def validate_device_capabilities(device_type: str, required_features: list) -> bool:
    """
    Validate if a device type supports required features
    
    Args:
        device_type: Type of device to check
        required_features: List of required features
        
    Returns:
        bool: True if device supports all required features
    """
    supported = get_supported_devices()
    device_type = device_type.lower()
    
    # Normalize device type
    if device_type in ['tanita', 'tanita_mc780ma', 'mc780ma']:
        device_info = supported.get('tanita_mc780ma')
    elif device_type in ['inbody', 'inbody_270']:
        device_info = supported.get('inbody_270')
    else:
        return False
    
    if not device_info or not device_info['available']:
        return False
    
    device_features = [feature.lower() for feature in device_info['features']]
    
    for required_feature in required_features:
        feature_found = False
        required_lower = required_feature.lower()
        
        for device_feature in device_features:
            if required_lower in device_feature or device_feature in required_lower:
                feature_found = True
                break
        
        if not feature_found:
            logger.warning(f"Device {device_type} does not support required feature: {required_feature}")
            return False
    
    return True

def get_device_status() -> dict:
    """
    Get status of device protocol availability
    
    Returns:
        dict: Status information for all device protocols
    """
    status = {
        'base_protocol_available': DeviceProtocol is not None,
        'tanita_protocol_available': TanitaProtocol is not None,
        'inbody_protocol_available': InBodyProtocol is not None,
        'supported_device_count': len([d for d in get_supported_devices().values() if d['available']]),
        'package_version': __version__,
        'total_supported_devices': len(get_supported_devices())
    }
    
    return status

# Package metadata
__version__ = "2.0.0"
__author__ = "Actiwell Development Team"
__description__ = "Device communication protocols for body composition analyzers"

# Log package initialization
logger.info(f"Actiwell Devices Package v{__version__} loaded")

# Log available devices
available_devices = [name for name, info in get_supported_devices().items() if info['available']]
if available_devices:
    logger.info(f"Available device protocols: {', '.join(available_devices)}")
else:
    logger.warning("No device protocols available - check imports")

# Validate critical components
if DeviceProtocol is None:
    logger.error("Base DeviceProtocol class not available - device functionality will be limited")

if TanitaProtocol is None and InBodyProtocol is None:
    logger.error("No device protocols available - cannot communicate with devices")
elif TanitaProtocol is None:
    logger.warning("Tanita protocol not available - Tanita devices not supported")
elif InBodyProtocol is None:
    logger.warning("InBody protocol not available - InBody devices not supported")
else:
    logger.info("All device protocols loaded successfully")