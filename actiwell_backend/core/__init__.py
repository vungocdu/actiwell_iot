"""
Actiwell Backend Core Package
=============================

Core business logic và infrastructure components.
Chứa các managers chính cho database, devices, và external API integration.

Components:
- DatabaseManager: Quản lý kết nối database và queries
- DeviceManager: Giao tiếp với Tanita MC-780MA và InBody 270
- ActiwellAPI: Integration với Actiwell SaaS platform

Author: Actiwell Development Team
Version: 2.0.0
"""

import logging
import os
from typing import Dict, Any, Optional

# Setup logger cho core package
logger = logging.getLogger(__name__)

# Import core managers - with error handling để tránh circular imports
try:
    from .database_manager import DatabaseManager
    logger.debug("DatabaseManager imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import DatabaseManager: {e}")
    DatabaseManager = None

try:
    from .device_manager import DeviceManager
    logger.debug("DeviceManager imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import DeviceManager: {e}")
    DeviceManager = None

try:
    from .actiwell_api import ActiwellAPI
    logger.debug("ActiwellAPI imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import ActiwellAPI: {e}")
    ActiwellAPI = None

# Import device protocols from devices package
try:
    from ..devices import (
        DeviceProtocol, 
        TanitaProtocol, 
        InBodyProtocol,
        create_device_protocol,
        get_supported_devices
    )
    logger.debug("Device protocols imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import device protocols: {e}")
    DeviceProtocol = None
    TanitaProtocol = None
    InBodyProtocol = None
    create_device_protocol = None
    get_supported_devices = None

# Define public API - những gì có thể import từ bên ngoài
__all__ = [
    # Core managers
    'DatabaseManager',
    'DeviceManager', 
    'ActiwellAPI',
    
    # Device protocols (re-exported for convenience)
    'DeviceProtocol',
    'TanitaProtocol',
    'InBodyProtocol',
    
    # Utility functions
    'initialize_core_managers',
    'get_core_status',
    'create_device_protocol',
    'get_supported_devices',
    'validate_core_dependencies'
]

def initialize_core_managers(config=None) -> Dict[str, Any]:
    """
    Initialize tất cả core managers với configuration
    
    Args:
        config: Configuration object chứa DB credentials, API keys, etc.
        
    Returns:
        dict: Dictionary chứa initialized managers
        
    Raises:
        Exception: Nếu không thể initialize core managers
    """
    managers = {
        'database': None,
        'devices': None, 
        'actiwell_api': None,
        'initialization_errors': []
    }
    
    try:
        logger.info("🚀 Initializing Actiwell Core Managers...")
        
        # Initialize Database Manager
        if DatabaseManager:
            try:
                logger.info("Initializing Database Manager...")
                managers['database'] = DatabaseManager(config)
                
                # Test database connection
                if hasattr(managers['database'], 'test_connection'):
                    if managers['database'].test_connection():
                        logger.info("✅ Database Manager initialized and connected")
                    else:
                        logger.warning("⚠️ Database Manager initialized but connection failed")
                else:
                    logger.info("✅ Database Manager initialized")
                    
            except Exception as e:
                error_msg = f"Database Manager initialization failed: {e}"
                logger.error(error_msg)
                managers['initialization_errors'].append(error_msg)
        else:
            error_msg = "DatabaseManager class not available"
            logger.error(error_msg)
            managers['initialization_errors'].append(error_msg)
        
        # Initialize Device Manager
        if DeviceManager:
            try:
                logger.info("Initializing Device Manager...")
                managers['devices'] = DeviceManager(managers['database'])
                
                # Start device discovery if enabled
                if config and getattr(config, 'AUTO_DETECT_DEVICES', True):
                    managers['devices'].start_auto_discovery()
                    logger.info("📱 Device auto-discovery started")
                
                logger.info("✅ Device Manager initialized")
                
            except Exception as e:
                error_msg = f"Device Manager initialization failed: {e}"
                logger.error(error_msg)
                managers['initialization_errors'].append(error_msg)
        else:
            error_msg = "DeviceManager class not available"
            logger.error(error_msg)
            managers['initialization_errors'].append(error_msg)
        
        # Initialize Actiwell API
        if ActiwellAPI:
            try:
                logger.info("Initializing Actiwell API...")
                managers['actiwell_api'] = ActiwellAPI(config)
                
                # Test API connection if possible
                if hasattr(managers['actiwell_api'], 'test_connection'):
                    if managers['actiwell_api'].test_connection():
                        logger.info("✅ Actiwell API initialized and connected")
                    else:
                        logger.warning("⚠️ Actiwell API initialized but connection failed")
                else:
                    logger.info("✅ Actiwell API initialized")
                    
            except Exception as e:
                error_msg = f"Actiwell API initialization failed: {e}"
                logger.error(error_msg)
                managers['initialization_errors'].append(error_msg)
        else:
            error_msg = "ActiwellAPI class not available"
            logger.error(error_msg)
            managers['initialization_errors'].append(error_msg)
        
        # Summary
        successful_managers = sum(1 for manager in ['database', 'devices', 'actiwell_api'] 
                                if managers[manager] is not None)
        total_managers = 3
        
        if successful_managers == total_managers:
            logger.info("🎉 All core managers initialized successfully!")
        elif successful_managers > 0:
            logger.warning(f"⚠️ Partial initialization: {successful_managers}/{total_managers} managers initialized")
        else:
            logger.error("❌ No core managers could be initialized")
        
        # Log errors if any
        if managers['initialization_errors']:
            logger.error("Initialization errors encountered:")
            for error in managers['initialization_errors']:
                logger.error(f"  - {error}")
        
        return managers
        
    except Exception as e:
        logger.error(f"❌ Critical error during core managers initialization: {e}")
        managers['initialization_errors'].append(f"Critical initialization error: {e}")
        raise

def get_core_status() -> Dict[str, Any]:
    """
    Lấy status của tất cả core components
    
    Returns:
        dict: Status information của core managers và dependencies
    """
    status = {
        'core_managers': {
            'database_manager': DatabaseManager is not None,
            'device_manager': DeviceManager is not None,
            'actiwell_api': ActiwellAPI is not None
        },
        'device_protocols': {
            'base_protocol': DeviceProtocol is not None,
            'tanita_protocol': TanitaProtocol is not None,
            'inbody_protocol': InBodyProtocol is not None
        },
        'utility_functions': {
            'create_device_protocol': create_device_protocol is not None,
            'get_supported_devices': get_supported_devices is not None
        },
        'package_info': {
            'version': __version__,
            'python_version': f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}"
        }
    }
    
    # Calculate availability percentages
    core_available = sum(status['core_managers'].values())
    core_total = len(status['core_managers'])
    
    device_available = sum(status['device_protocols'].values())
    device_total = len(status['device_protocols'])
    
    status['summary'] = {
        'core_managers_availability': f"{core_available}/{core_total} ({core_available/core_total*100:.1f}%)",
        'device_protocols_availability': f"{device_available}/{device_total} ({device_available/device_total*100:.1f}%)",
        'overall_health': 'Good' if core_available >= 2 and device_available >= 2 else 'Limited' if core_available >= 1 else 'Critical'
    }
    
    return status

def validate_core_dependencies() -> Dict[str, Any]:
    """
    Validate tất cả core dependencies và requirements
    
    Returns:
        dict: Validation results với recommendations
    """
    validation = {
        'critical_dependencies': {},
        'optional_dependencies': {},
        'recommendations': [],
        'status': 'unknown'
    }
    
    # Critical dependencies
    validation['critical_dependencies'] = {
        'database_manager': DatabaseManager is not None,
        'device_manager': DeviceManager is not None,
        'base_device_protocol': DeviceProtocol is not None
    }
    
    # Optional dependencies  
    validation['optional_dependencies'] = {
        'actiwell_api': ActiwellAPI is not None,
        'tanita_protocol': TanitaProtocol is not None,
        'inbody_protocol': InBodyProtocol is not None,
        'device_utilities': create_device_protocol is not None
    }
    
    # Generate recommendations
    if not validation['critical_dependencies']['database_manager']:
        validation['recommendations'].append("Install database dependencies and ensure database_manager.py is available")
    
    if not validation['critical_dependencies']['device_manager']:
        validation['recommendations'].append("Ensure device_manager.py is available for device communication")
    
    if not validation['critical_dependencies']['base_device_protocol']:
        validation['recommendations'].append("Install device protocol dependencies")
    
    if not validation['optional_dependencies']['tanita_protocol']:
        validation['recommendations'].append("Tanita MC-780MA support not available - check tanita_protocol.py")
    
    if not validation['optional_dependencies']['inbody_protocol']:
        validation['recommendations'].append("InBody 270 support not available - check inbody_protocol.py")
    
    if not validation['optional_dependencies']['actiwell_api']:
        validation['recommendations'].append("Actiwell API integration not available - limited sync functionality")
    
    # Determine overall status
    critical_count = sum(validation['critical_dependencies'].values())
    critical_total = len(validation['critical_dependencies'])
    
    if critical_count == critical_total:
        validation['status'] = 'ready'
    elif critical_count >= critical_total * 0.7:  # 70% of critical deps
        validation['status'] = 'limited'
    else:
        validation['status'] = 'not_ready'
    
    return validation

def get_system_requirements() -> Dict[str, Any]:
    """
    Get system requirements và recommendations
    
    Returns:
        dict: System requirements information
    """
    return {
        'minimum_requirements': {
            'python_version': '3.7+',
            'ram_mb': 512,
            'storage_mb': 100,
            'serial_ports': 'USB/RS-232C support',
            'os_support': ['Linux', 'Windows', 'macOS']
        },
        'recommended_requirements': {
            'python_version': '3.8+',
            'ram_mb': 1024,
            'storage_mb': 500,
            'serial_ports': 'Multiple USB ports for multiple devices',
            'os_support': ['Linux (Raspberry Pi)', 'Ubuntu Server']
        },
        'dependencies': {
            'required': [
                'pyserial>=3.5',
                'mysql-connector-python>=8.0',
                'requests>=2.25'
            ],
            'optional': [
                'flask>=2.0 (for web interface)',
                'psutil>=5.8 (for system monitoring)'
            ]
        },
        'supported_devices': [
            'Tanita MC-780MA (via USB/RS-232C)',
            'InBody 270 (via USB/RS-232C/Network)'
        ]
    }

# Module metadata
__version__ = "2.0.0"
__author__ = "Actiwell Development Team"
__description__ = "Core infrastructure components for Actiwell IoT Backend"

# Log package initialization
logger.info(f"Actiwell Backend Core Package v{__version__} loaded")

# Validate and log component availability
status = get_core_status()
logger.info(f"Core managers availability: {status['summary']['core_managers_availability']}")
logger.info(f"Device protocols availability: {status['summary']['device_protocols_availability']}")
logger.info(f"Overall health: {status['summary']['overall_health']}")

# Log warnings for missing critical components
validation = validate_core_dependencies()
if validation['status'] != 'ready':
    logger.warning(f"Core system status: {validation['status']}")
    if validation['recommendations']:
        logger.warning("Recommendations to improve system:")
        for rec in validation['recommendations']:
            logger.warning(f"  - {rec}")

logger.debug(f"Available components: {[name for name in __all__ if globals().get(name) is not None]}")