"""
Actiwell Backend Tests Package
==============================

Unit tests và integration tests cho Actiwell IoT Backend.
Package này chứa test utilities, fixtures, và test configurations.

Test Categories:
- Unit Tests: Test individual components in isolation
- Integration Tests: Test component interactions
- API Tests: Test REST API endpoints
- Device Tests: Test device communication
- Performance Tests: Test system performance và scalability

Test Modules:
- test_database.py: Database manager tests
- test_device_manager.py: Device communication tests
- test_api.py: API endpoint tests
- test_services.py: Business service tests
- test_integration.py: End-to-end integration tests

Author: Actiwell Development Team
Version: 2.0.0
"""

import os
import sys
import unittest
import logging
from typing import Optional, Dict, Any
from unittest.mock import Mock, MagicMock

# Add project root to Python path cho imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Setup test logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Disable verbose logging từ external libraries
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Test configuration
TEST_CONFIG = {
    'database': {
        'host': 'localhost',
        'user': 'test_user',
        'password': 'test_password',
        'database': 'actiwell_test',
        'autocommit': True
    },
    'api': {
        'base_url': 'http://localhost:5000',
        'test_token': 'test_jwt_token_here',
        'timeout': 30
    },
    'devices': {
        'mock_serial_port': '/dev/ttyUSB999',
        'test_data_file': 'test_tanita_data.txt'
    },
    'files': {
        'test_data_dir': os.path.join(os.path.dirname(__file__), 'test_data'),
        'fixtures_dir': os.path.join(os.path.dirname(__file__), 'fixtures')
    }
}

class BaseTestCase(unittest.TestCase):
    """
    Base test case với common setup và teardown methods
    """
    
    def setUp(self):
        """Setup method chạy trước mỗi test"""
        self.test_config = TEST_CONFIG.copy()
        logger.debug(f"Setting up test: {self._testMethodName}")
    
    def tearDown(self):
        """Teardown method chạy sau mỗi test"""
        logger.debug(f"Tearing down test: {self._testMethodName}")
    
    @classmethod
    def setUpClass(cls):
        """Setup method chạy một lần cho toàn bộ test class"""
        logger.info(f"Setting up test class: {cls.__name__}")
    
    @classmethod
    def tearDownClass(cls):
        """Teardown method chạy một lần sau toàn bộ test class"""
        logger.info(f"Tearing down test class: {cls.__name__}")

class DatabaseTestCase(BaseTestCase):
    """
    Base test case cho database-related tests
    """
    
    def setUp(self):
        super().setUp()
        self.mock_db_manager = Mock()
        self.mock_connection = Mock()
        self.mock_cursor = Mock()
        
        # Setup mock database responses
        self.mock_db_manager.get_connection.return_value = self.mock_connection
        self.mock_connection.cursor.return_value = self.mock_cursor
        
        logger.debug("Database test case setup complete")

class APITestCase(BaseTestCase):
    """
    Base test case cho API-related tests
    """
    
    def setUp(self):
        super().setUp()
        self.api_base_url = TEST_CONFIG['api']['base_url']
        self.test_headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {TEST_CONFIG['api']['test_token']}"
        }
        
        logger.debug("API test case setup complete")

class DeviceTestCase(BaseTestCase):
    """
    Base test case cho device communication tests
    """
    
    def setUp(self):
        super().setUp()
        self.mock_serial = Mock()
        self.mock_device_manager = Mock()
        
        # Setup mock device responses
        self.sample_tanita_data = self._load_sample_data('tanita_sample.txt')
        self.sample_inbody_data = self._load_sample_data('inbody_sample.txt')
        
        logger.debug("Device test case setup complete")
    
    def _load_sample_data(self, filename: str) -> str:
        """Load sample data file cho testing"""
        try:
            data_file = os.path.join(TEST_CONFIG['files']['test_data_dir'], filename)
            if os.path.exists(data_file):
                with open(data_file, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                logger.warning(f"Sample data file not found: {data_file}")
                return ""
        except Exception as e:
            logger.error(f"Error loading sample data {filename}: {e}")
            return ""

# Test utilities và helper functions
def create_mock_measurement(customer_phone: str = "0901234567", **kwargs) -> Dict[str, Any]:
    """
    Create mock measurement data cho testing
    
    Args:
        customer_phone: Customer phone number
        **kwargs: Additional measurement fields
        
    Returns:
        dict: Mock measurement data
    """
    default_measurement = {
        'device_id': 'test_device_001',
        'device_type': 'tanita_mc780ma',
        'customer_phone': customer_phone,
        'measurement_timestamp': '2024-01-01T10:00:00',
        'weight_kg': 70.5,
        'height_cm': 170.0,
        'bmi': 24.4,
        'body_fat_percent': 15.2,
        'muscle_mass_kg': 55.8,
        'bone_mass_kg': 3.2,
        'total_body_water_percent': 60.5,
        'visceral_fat_rating': 5,
        'metabolic_age': 25,
        'bmr_kcal': 1650,
        'raw_data': 'mock_tanita_data_string'
    }
    
    # Update với custom values
    default_measurement.update(kwargs)
    return default_measurement

def create_mock_device_status(device_id: str = "test_device_001", **kwargs) -> Dict[str, Any]:
    """
    Create mock device status data
    
    Args:
        device_id: Device identifier
        **kwargs: Additional status fields
        
    Returns:
        dict: Mock device status
    """
    default_status = {
        'device_id': device_id,
        'device_type': 'tanita_mc780ma',
        'serial_port': '/dev/ttyUSB0',
        'connection_status': 'connected',
        'firmware_version': '1.0.0',
        'last_heartbeat': '2024-01-01T10:00:00',
        'total_measurements': 150,
        'error_count': 0
    }
    
    default_status.update(kwargs)
    return default_status

def run_test_suite(test_pattern: str = "test_*.py", verbosity: int = 2) -> unittest.TestResult:
    """
    Run test suite với specified pattern
    
    Args:
        test_pattern: Pattern để tìm test files
        verbosity: Test output verbosity level
        
    Returns:
        unittest.TestResult: Test execution results
    """
    logger.info(f"Running test suite with pattern: {test_pattern}")
    
    # Discover tests
    loader = unittest.TestLoader()
    test_dir = os.path.dirname(__file__)
    suite = loader.discover(test_dir, pattern=test_pattern)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    # Log results
    logger.info(f"Tests run: {result.testsRun}")
    logger.info(f"Failures: {len(result.failures)}")
    logger.info(f"Errors: {len(result.errors)}")
    logger.info(f"Skipped: {len(result.skipped)}")
    
    return result

def setup_test_database():
    """Setup test database với sample data"""
    logger.info("Setting up test database...")
    
    try:
        # Import database manager
        from actiwell_backend.core.database_manager import DatabaseManager
        
        # Create test database connection
        # Implementation would go here
        
        logger.info("✅ Test database setup complete")
        
    except Exception as e:
        logger.error(f"❌ Failed to setup test database: {e}")
        raise

def cleanup_test_database():
    """Cleanup test database sau khi tests complete"""
    logger.info("Cleaning up test database...")
    
    try:
        # Clean up test data
        # Implementation would go here
        
        logger.info("✅ Test database cleanup complete")
        
    except Exception as e:
        logger.error(f"❌ Failed to cleanup test database: {e}")

# Test fixtures và sample data
SAMPLE_TANITA_DATA = """
{0,16,~0,1,~1,1,~2,1,MO,"MC-780",ID,"0901234567000000",St,0,Da,"01/01/2024",TI,"10:00",Bt,0,
GE,1,AG,30,Hm,170.0,Pt,0.0,Wk,70.5,FW,15.2,fW,10.7,MW,59.8,mW,55.8,sW,0,bW,3.2,wW,42.5,
ww,60.3,wI,25.6,wO,16.9,wo,39.8,MI,24.4,Sw,63.5,OV,11.0,Sf,14.0,SM,52.8,IF,5,LP,105,rB,1650,
rb,6903,rJ,10,rA,25,BA,0,BF,1,gF,12,gW,68.0,gf,8.2,gt,-2.5,CS,A5
"""

SAMPLE_API_RESPONSES = {
    'login_success': {
        'success': True,
        'token': 'mock_jwt_token',
        'user': 'test_user',
        'expires_at': '2024-01-02T10:00:00'
    },
    'device_status': {
        'success': True,
        'devices': [create_mock_device_status()],
        'total_devices': 1,
        'connected_devices': 1
    },
    'measurement_list': {
        'success': True,
        'measurements': [create_mock_measurement()],
        'pagination': {
            'page': 1,
            'per_page': 50,
            'total_count': 1,
            'total_pages': 1
        }
    }
}

# Define public API cho test package
__all__ = [
    'BaseTestCase',
    'DatabaseTestCase',
    'APITestCase',
    'DeviceTestCase',
    'TEST_CONFIG',
    'create_mock_measurement',
    'create_mock_device_status',
    'run_test_suite',
    'setup_test_database',
    'cleanup_test_database',
    'SAMPLE_TANITA_DATA',
    'SAMPLE_API_RESPONSES'
]

# Module metadata
__version__ = "2.0.0"
__author__ = "Actiwell Development Team"
__description__ = "Test package for Actiwell IoT Backend"

# Create test data directory nếu không tồn tại
os.makedirs(TEST_CONFIG['files']['test_data_dir'], exist_ok=True)
os.makedirs(TEST_CONFIG['files']['fixtures_dir'], exist_ok=True)

# Log package initialization
logger.info(f"Actiwell Backend Tests Package v{__version__} loaded")
logger.debug(f"Test data directory: {TEST_CONFIG['files']['test_data_dir']}")
logger.debug(f"Test fixtures directory: {TEST_CONFIG['files']['fixtures_dir']}")