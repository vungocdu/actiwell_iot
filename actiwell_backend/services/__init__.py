"""
Actiwell Backend Services Package
=================================

Business logic services cho xử lý measurements, synchronization, và health monitoring.
Package này chứa các services layer giữa API endpoints và core managers.

Services:
- MeasurementService: Xử lý và validate measurement data từ devices
- SyncService: Đồng bộ dữ liệu với Actiwell SaaS platform  
- HealthService: Monitor system health và send alerts

Author: Actiwell Development Team
Version: 2.0.0
"""

import logging
from typing import Optional, Dict, Any

# Setup logger cho services package
logger = logging.getLogger(__name__)

# Import services với error handling
try:
    from .measurement_service import MeasurementService
    logger.debug("MeasurementService imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import MeasurementService: {e}")
    MeasurementService = None

try:
    from .sync_service import SyncService
    logger.debug("SyncService imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import SyncService: {e}")
    SyncService = None

try:
    from .health_service import HealthService
    logger.debug("HealthService imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import HealthService: {e}")
    HealthService = None

# Define public API
__all__ = [
    'MeasurementService',
    'SyncService', 
    'HealthService',
    'ServiceManager',
    'initialize_services',
    'get_services_status'
]

class ServiceManager:
    """
    Central manager cho tất cả business services
    Quản lý lifecycle và dependencies giữa các services
    """
    
    def __init__(self, db_manager=None, device_manager=None, actiwell_api=None):
        """
        Initialize ServiceManager với core dependencies
        
        Args:
            db_manager: DatabaseManager instance
            device_manager: DeviceManager instance  
            actiwell_api: ActiwellAPI instance
        """
        self.db_manager = db_manager
        self.device_manager = device_manager
        self.actiwell_api = actiwell_api
        
        # Initialize services
        self.measurement_service: Optional[MeasurementService] = None
        self.sync_service: Optional[SyncService] = None
        self.health_service: Optional[HealthService] = None
        
        logger.info("ServiceManager initialized")
    
    def initialize_all_services(self) -> Dict[str, Any]:
        """
        Initialize tất cả services với dependencies
        
        Returns:
            dict: Dictionary chứa initialized services
            
        Raises:
            Exception: Nếu không thể initialize critical services
        """
        services = {}
        
        try:
            # Initialize MeasurementService
            if MeasurementService:
                logger.info("Initializing Measurement Service...")
                self.measurement_service = MeasurementService(
                    self.db_manager,
                    self.device_manager, 
                    self.actiwell_api
                )
                services['measurement'] = self.measurement_service
                logger.info("✅ Measurement Service initialized")
            
            # Initialize SyncService
            if SyncService:
                logger.info("Initializing Sync Service...")
                self.sync_service = SyncService(
                    self.db_manager,
                    self.actiwell_api
                )
                services['sync'] = self.sync_service
                logger.info("✅ Sync Service initialized")
            
            # Initialize HealthService
            if HealthService:
                logger.info("Initializing Health Service...")
                self.health_service = HealthService(
                    self.db_manager,
                    self.device_manager
                )
                services['health'] = self.health_service
                logger.info("✅ Health Service initialized")
            
            logger.info("🎉 All services initialized successfully")
            return services
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize services: {e}")
            raise
    
    def get_service_status(self) -> Dict[str, bool]:
        """
        Get status của tất cả services
        
        Returns:
            dict: Status information cho each service
        """
        return {
            'measurement_service': self.measurement_service is not None,
            'sync_service': self.sync_service is not None,
            'health_service': self.health_service is not None
        }
    
    def start_background_services(self):
        """Start các background services nếu cần"""
        logger.info("Starting background services...")
        
        # Example: Start periodic health checks
        if self.health_service:
            # Implement periodic health monitoring
            pass
        
        # Example: Start automatic sync
        if self.sync_service:
            # Implement periodic sync operations
            pass
        
        logger.info("Background services started")
    
    def stop_background_services(self):
        """Stop các background services gracefully"""
        logger.info("Stopping background services...")
        
        # Implement graceful shutdown logic here
        
        logger.info("Background services stopped")

def initialize_services(db_manager=None, device_manager=None, actiwell_api=None):
    """
    Convenience function để initialize tất cả services
    
    Args:
        db_manager: DatabaseManager instance
        device_manager: DeviceManager instance
        actiwell_api: ActiwellAPI instance
        
    Returns:
        ServiceManager: Initialized service manager
    """
    service_manager = ServiceManager(db_manager, device_manager, actiwell_api)
    service_manager.initialize_all_services()
    return service_manager

def get_services_status():
    """
    Get status của services package
    
    Returns:
        dict: Status information
    """
    status = {
        'measurement_service_available': MeasurementService is not None,
        'sync_service_available': SyncService is not None,
        'health_service_available': HealthService is not None,
        'package_version': __version__
    }
    
    return status

# Service configuration constants
SERVICE_CONFIG = {
    'measurement': {
        'batch_size': 100,
        'timeout_seconds': 30,
        'retry_attempts': 3
    },
    'sync': {
        'batch_size': 50,
        'sync_interval_seconds': 30,
        'max_retry_attempts': 5
    },
    'health': {
        'check_interval_seconds': 60,
        'alert_threshold_cpu': 80,
        'alert_threshold_memory': 85,
        'alert_threshold_disk': 90
    }
}

# Module metadata
__version__ = "2.0.0"
__author__ = "Actiwell Development Team"
__description__ = "Business logic services for Actiwell IoT Backend"

# Log package initialization
logger.info(f"Actiwell Backend Services Package v{__version__} loaded")
logger.debug(f"Available services: {[name for name in __all__ if globals().get(name) is not None]}")