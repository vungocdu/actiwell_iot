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
    from .device_manager import DeviceManager, TanitaProtocol, InBodyProtocol
    logger.debug("DeviceManager imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import DeviceManager: {e}")
    DeviceManager = None
    TanitaProtocol = None
    InBodyProtocol = None

try:
    from .actiwell_api import ActiwellAPI
    logger.debug("ActiwellAPI imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import ActiwellAPI: {e}")
    ActiwellAPI = None

# Define public API - những gì có thể import từ bên ngoài
__all__ = [
    'DatabaseManager',
    'DeviceManager', 
    'TanitaProtocol',
    'InBodyProtocol',
    'ActiwellAPI',
    'initialize_core_managers',
    'get_core_status'
]

def initialize_core_managers(config):
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
        'actiwell_api': None
    }
    
    try:
        # Initialize Database Manager
        if DatabaseManager:
            logger.info("Initializing Database Manager...")
            managers['database'] = DatabaseManager()
            logger.info("✅ Database Manager initialized")
        
        # Initialize Device Manager
        if DeviceManager and managers['database']:
            logger.info("Initializing Device Manager...")
            managers['devices'] = DeviceManager(managers['database'])
            logger.info("✅ Device Manager initialized")
        
        # Initialize Actiwell API
        if ActiwellAPI:
            logger.info("Initializing Actiwell API...")
            managers['actiwell_api'] = ActiwellAPI()
            logger.info("✅ Actiwell API initialized")
        
        logger.info("🎉 All core managers initialized successfully")
        return managers
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize core managers: {e}")
        raise

def get_core_status():
    """
    Lấy status của tất cả core components
    
    Returns:
        dict: Status information của core managers
    """
    status = {
        'database_manager': DatabaseManager is not None,
        'device_manager': DeviceManager is not None,
        'actiwell_api': ActiwellAPI is not None,
        'tanita_protocol': TanitaProtocol is not None,
        'inbody_protocol': InBodyProtocol is not None
    }
    
    return status

# Module metadata
__version__ = "2.0.0"
__author__ = "Actiwell Development Team"
__description__ = "Core infrastructure components for Actiwell IoT Backend"

# Log package initialization
logger.info(f"Actiwell Backend Core Package v{__version__} loaded")
logger.debug(f"Available components: {[name for name in __all__ if globals().get(name) is not None]}")