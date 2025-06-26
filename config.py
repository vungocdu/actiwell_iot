#!/usr/bin/env python3
"""
Configuration Management for Actiwell InBody Integration
Professional configuration system with environment variable support
Fixed version with compatibility for test scripts
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any, Optional

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration class"""
    
    # Application
    SECRET_KEY = os.getenv('SECRET_KEY', 'inbody-dev-secret-key-change-in-production')
    JWT_EXPIRE_HOURS = int(os.getenv('JWT_EXPIRE_HOURS', '24'))
    WEB_PORT = int(os.getenv('WEB_PORT', '5000'))
    WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    # Database Configuration (Fixed env var names)
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER', 'actiwell_user')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'your_secure_password')
    DB_NAME = os.getenv('DB_NAME', 'actiwell_measurements')
    DB_PORT = int(os.getenv('DB_PORT', '3306'))
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '5'))
    
    # InBody Device Configuration (Fixed to match test scripts)
    INBODY_DEVICE_MODEL = os.getenv('INBODY_DEVICE_MODEL', 'InBody-370s')
    INBODY_IP = os.getenv('INBODY_IP', '192.168.1.100')  # Fixed env var name
    INBODY_DEVICE_IP = INBODY_IP  # Backward compatibility
    INBODY_LISTENING_PORT = int(os.getenv('INBODY_LISTENING_PORT', '2580'))
    INBODY_DATA_PORT = int(os.getenv('INBODY_DATA_PORT', '2575'))
    INBODY_TIMEOUT = int(os.getenv('INBODY_TIMEOUT', '30'))
    INBODY_MAX_CONNECTIONS = int(os.getenv('INBODY_MAX_CONNECTIONS', '10'))
    INBODY_ENABLED = os.getenv('INBODY_ENABLED', 'true').lower() == 'true'
    
    # HL7 Configuration
    HL7_VERSION = os.getenv('HL7_VERSION', '2.5')
    HL7_MESSAGE_TYPE = os.getenv('HL7_MESSAGE_TYPE', 'ORU_R01')
    HL7_ENCODING = os.getenv('HL7_ENCODING', 'UTF-8')
    HL7_SEGMENT_SEPARATOR = os.getenv('HL7_SEGMENT_SEPARATOR', '\r')
    HL7_FIELD_SEPARATOR = os.getenv('HL7_FIELD_SEPARATOR', '|')
    
    # Actiwell API Configuration
    ACTIWELL_API_URL = os.getenv('ACTIWELL_API_URL', 'https://api.actiwell.com')
    ACTIWELL_API_KEY = os.getenv('ACTIWELL_API_KEY', '')
    ACTIWELL_LOCATION_ID = int(os.getenv('ACTIWELL_LOCATION_ID', '1'))
    ACTIWELL_OPERATOR_ID = int(os.getenv('ACTIWELL_OPERATOR_ID', '1'))
    ACTIWELL_TIMEOUT = int(os.getenv('ACTIWELL_TIMEOUT', '10'))
    ACTIWELL_RETRY_ATTEMPTS = int(os.getenv('ACTIWELL_RETRY_ATTEMPTS', '3'))
    
    # File Paths
    BASE_DIR = Path(__file__).parent.absolute()
    DATA_DIR = BASE_DIR / 'data'
    LOGS_DIR = BASE_DIR / 'logs'
    TEMPLATES_DIR = BASE_DIR / 'actiwell_backend' / 'templates'
    STATIC_DIR = BASE_DIR / 'actiwell_backend' / 'static'
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = LOGS_DIR / 'inbody_integration.log'
    LOG_ERROR_FILE = LOGS_DIR / 'inbody_integration_error.log'
    LOG_MAX_SIZE = int(os.getenv('LOG_MAX_SIZE', '10485760'))  # 10MB
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    
    # Processing Configuration
    AUTO_CUSTOMER_LOOKUP = os.getenv('AUTO_CUSTOMER_LOOKUP', 'True').lower() == 'true'
    SEND_TO_ACTIWELL = os.getenv('SEND_TO_ACTIWELL', 'True').lower() == 'true'
    SAVE_TO_DATABASE = os.getenv('SAVE_TO_DATABASE', 'True').lower() == 'true'
    BACKUP_RAW_DATA = os.getenv('BACKUP_RAW_DATA', 'True').lower() == 'true'
    PHONE_VALIDATION_REGEX = os.getenv('PHONE_VALIDATION_REGEX', r'^0[2-9][0-9]{8}$')
    
    # Performance Configuration
    MESSAGE_TIMEOUT = int(os.getenv('MESSAGE_TIMEOUT', '60'))
    PROCESSING_TIMEOUT = int(os.getenv('PROCESSING_TIMEOUT', '30'))
    MAX_QUEUE_SIZE = int(os.getenv('MAX_QUEUE_SIZE', '100'))
    WORKER_THREADS = int(os.getenv('WORKER_THREADS', '3'))
    
    @classmethod
    def init_directories(cls):
        """Initialize required directories"""
        cls.DATA_DIR.mkdir(exist_ok=True)
        cls.LOGS_DIR.mkdir(exist_ok=True)
        (cls.DATA_DIR / 'backup').mkdir(exist_ok=True)
        (cls.DATA_DIR / 'exports').mkdir(exist_ok=True)
    
    @classmethod
    def get_database_url(cls) -> str:
        """Get database connection URL"""
        return f"mysql+pymysql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
    
    @classmethod
    def get_database_config(cls) -> Dict[str, Any]:
        """Get database configuration dictionary"""
        return {
            'host': cls.DB_HOST,
            'port': cls.DB_PORT,
            'user': cls.DB_USER,
            'password': cls.DB_PASSWORD,
            'database': cls.DB_NAME,
            'charset': 'utf8mb4',
            'autocommit': True,
            'pool_size': cls.DB_POOL_SIZE
        }
    
    @classmethod
    def get_inbody_config(cls) -> Dict[str, Any]:
        """Get InBody device configuration - Fixed for test compatibility"""
        return {
            'model': cls.INBODY_DEVICE_MODEL,
            'ip_address': cls.INBODY_IP,  # Fixed key name for test scripts
            'device_ip': cls.INBODY_IP,   # Backward compatibility
            'listening_port': cls.INBODY_LISTENING_PORT,
            'data_port': cls.INBODY_DATA_PORT,
            'timeout': cls.INBODY_TIMEOUT,
            'max_connections': cls.INBODY_MAX_CONNECTIONS,
            'enabled': cls.INBODY_ENABLED
        }
    
    @classmethod
    def get_hl7_config(cls) -> Dict[str, Any]:
        """Get HL7 protocol configuration"""
        return {
            'version': cls.HL7_VERSION,
            'message_type': cls.HL7_MESSAGE_TYPE,
            'encoding': cls.HL7_ENCODING,
            'segment_separator': cls.HL7_SEGMENT_SEPARATOR,
            'field_separator': cls.HL7_FIELD_SEPARATOR
        }
    
    @classmethod
    def get_actiwell_config(cls) -> Dict[str, Any]:
        """Get Actiwell API configuration"""
        return {
            'api_url': cls.ACTIWELL_API_URL,
            'api_key': cls.ACTIWELL_API_KEY,
            'location_id': cls.ACTIWELL_LOCATION_ID,
            'operator_id': cls.ACTIWELL_OPERATOR_ID,
            'timeout': cls.ACTIWELL_TIMEOUT,
            'retry_attempts': cls.ACTIWELL_RETRY_ATTEMPTS
        }
    
    @classmethod
    def validate_config(cls) -> Dict[str, bool]:
        """Validate configuration settings"""
        validation_results = {}
        
        # Check required API settings
        validation_results['actiwell_api_configured'] = bool(cls.ACTIWELL_API_URL and cls.ACTIWELL_API_KEY)
        
        # Check database settings
        validation_results['database_configured'] = bool(
            cls.DB_HOST and cls.DB_USER and cls.DB_PASSWORD and cls.DB_NAME
        )
        
        # Check InBody device settings
        validation_results['inbody_configured'] = bool(
            cls.INBODY_IP and cls.INBODY_LISTENING_PORT and cls.INBODY_DATA_PORT
        )
        
        # Check required directories
        validation_results['directories_exist'] = all([
            cls.DATA_DIR.exists(),
            cls.LOGS_DIR.exists(),
            cls.TEMPLATES_DIR.exists(),
            cls.STATIC_DIR.exists()
        ])
        
        return validation_results


class DevelopmentConfig(Config):
    """Development configuration"""
    FLASK_DEBUG = True
    LOG_LEVEL = 'DEBUG'
    SEND_TO_ACTIWELL = False  # Don't send to production API in dev
    DB_NAME = 'actiwell_measurements_dev'


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    FLASK_DEBUG = True
    LOG_LEVEL = 'DEBUG'
    
    # Use test database
    DB_NAME = 'actiwell_measurements_test'
    
    # Use test ports to avoid conflicts
    INBODY_LISTENING_PORT = 12580
    INBODY_DATA_PORT = 12575
    WEB_PORT = 15000
    
    # Disable external services in tests
    SEND_TO_ACTIWELL = False
    SAVE_TO_DATABASE = False


class ProductionConfig(Config):
    """Production configuration"""
    FLASK_DEBUG = False
    LOG_LEVEL = 'INFO'
    
    # Production security
    SECRET_KEY = os.getenv('SECRET_KEY')  # Must be set in production
    
    # Production database with connection pooling
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '10'))
    
    # Production performance settings
    WORKER_THREADS = int(os.getenv('WORKER_THREADS', '5'))
    MAX_QUEUE_SIZE = int(os.getenv('MAX_QUEUE_SIZE', '200'))


class ConfigManager:
    """Configuration manager for different environments"""
    
    configs = {
        'development': DevelopmentConfig,
        'testing': TestingConfig,
        'production': ProductionConfig,
        'default': DevelopmentConfig
    }
    
    @classmethod
    def get_config(cls, config_name: Optional[str] = None) -> Config:
        """Get configuration class based on environment"""
        if config_name is None:
            config_name = os.getenv('FLASK_ENV', 'default')
        
        return cls.configs.get(config_name, cls.configs['default'])
    
    @classmethod
    def setup_logging(cls, config: Config):
        """Setup logging configuration"""
        # Ensure logs directory exists
        config.LOGS_DIR.mkdir(exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, config.LOG_LEVEL),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(config.LOG_FILE),
                logging.StreamHandler()
            ]
        )
        
        # Create error log handler
        error_handler = logging.FileHandler(config.LOG_ERROR_FILE)
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
        )
        error_handler.setFormatter(error_formatter)
        
        # Add error handler to root logger
        logging.getLogger().addHandler(error_handler)


# Global configuration instance
config = ConfigManager.get_config()

# Initialize directories and logging
config.init_directories()
ConfigManager.setup_logging(config)

# Export commonly used configurations (Fixed for test script compatibility)
DATABASE_CONFIG = config.get_database_config()
INBODY_CONFIG = config.get_inbody_config()  # Fixed: Now available at module level
HL7_CONFIG = config.get_hl7_config()
ACTIWELL_CONFIG = config.get_actiwell_config()

# Additional exports for backward compatibility and test scripts
PI_IP = os.getenv('PI_IP', '192.168.1.50')
DATA_PORT = INBODY_CONFIG['data_port']
LISTENING_PORT = INBODY_CONFIG['listening_port']