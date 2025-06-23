# ====================================================================================
# 1. CONFIG.PY - APPLICATION CONFIGURATION
# ====================================================================================

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Application configuration class"""
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'actiwell-default-secret-key-change-this')
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    TESTING = False
    
    # Web Server Configuration
    WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')
    WEB_PORT = int(os.getenv('WEB_PORT', 5000))
    
    # Database Configuration
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER', 'actiwell_user')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'actiwell_pass123')
    DB_NAME = os.getenv('DB_NAME', 'actiwell_measurements')
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', 5))
    
    # Authentication Configuration
    JWT_EXPIRE_HOURS = int(os.getenv('JWT_EXPIRE_HOURS', 24))
    
    # Actiwell API Configuration
    ACTIWELL_API_URL = os.getenv('ACTIWELL_API_URL', 'https://api.actiwell.com')
    ACTIWELL_API_KEY = os.getenv('ACTIWELL_API_KEY', '')
    ACTIWELL_LOCATION_ID = os.getenv('ACTIWELL_LOCATION_ID', '1')
    
    # Device Configuration
    TANITA_BAUDRATE = int(os.getenv('TANITA_BAUDRATE', 9600))
    INBODY_BAUDRATE = int(os.getenv('INBODY_BAUDRATE', 9600))
    DEVICE_TIMEOUT = int(os.getenv('DEVICE_TIMEOUT', 5))
    AUTO_DETECT_DEVICES = os.getenv('AUTO_DETECT_DEVICES', 'True').lower() == 'true'
    
    # File Storage Configuration
    DATA_STORAGE_PATH = os.getenv('DATA_STORAGE_PATH', '/opt/actiwell/data')
    LOG_STORAGE_PATH = os.getenv('LOG_STORAGE_PATH', '/opt/actiwell/logs')
    
    # Ensure directories exist
    @staticmethod
    def init_directories():
        """Create necessary directories"""
        import os
        directories = [
            Config.DATA_STORAGE_PATH,
            Config.LOG_STORAGE_PATH,
            '/opt/actiwell/static',
            '/opt/actiwell/templates'
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    WEB_HOST = 'localhost'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DB_NAME = 'actiwell_test'