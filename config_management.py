#!/usr/bin/env python3
"""
Enhanced Configuration Management System for Body Composition Gateway
Centralized configuration with validation, encryption, and environment support
"""

import os
import json
import yaml
import configparser
import logging
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
from dataclasses import dataclass, asdict, field
from datetime import datetime
import hashlib
import base64
from cryptography.fernet import Fernet
from enum import Enum
import threading
import time

# Configure logging
logger = logging.getLogger(__name__)

class ConfigSource(Enum):
    """Configuration sources in order of priority"""
    ENVIRONMENT = "environment"
    COMMAND_LINE = "command_line"
    CONFIG_FILE = "config_file"
    DATABASE = "database"
    DEFAULT = "default"

class ConfigType(Enum):
    """Configuration value types"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"
    PASSWORD = "password"
    PATH = "path"
    URL = "url"

@dataclass
class ConfigField:
    """Configuration field definition"""
    key: str
    description: str
    config_type: ConfigType
    default_value: Any = None
    required: bool = False
    sensitive: bool = False
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    allowed_values: Optional[List[Any]] = None
    validation_pattern: Optional[str] = None
    env_var: Optional[str] = None
    category: str = "general"

@dataclass
class DatabaseConfig:
    """Database configuration"""
    host: str = "localhost"
    port: int = 3306
    username: str = "body_comp_user"
    password: str = ""
    database: str = "body_composition_db"
    charset: str = "utf8mb4"
    pool_size: int = 10
    pool_timeout: int = 30
    ssl_enabled: bool = False
    ssl_cert_path: Optional[str] = None

@dataclass
class ActiwellConfig:
    """Actiwell API configuration"""
    api_url: str = ""
    api_key: str = ""
    location_id: str = ""
    timeout: int = 30
    retry_attempts: int = 3
    retry_delay: int = 5
    batch_size: int = 50
    sync_interval: int = 300  # seconds
    webhook_secret: str = ""
    enable_webhooks: bool = False

@dataclass
class DeviceConfig:
    """Device configuration"""
    auto_detect: bool = True
    scan_interval: int = 60  # seconds
    connection_timeout: int = 10
    max_retries: int = 3
    measurement_timeout: int = 120
    calibration_interval: int = 86400  # 24 hours in seconds
    default_baudrate: int = 9600
    supported_ports: List[str] = field(default_factory=lambda: ["/dev/ttyUSB*", "/dev/ttyACM*"])

@dataclass
class WebConfig:
    """Web interface configuration"""
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False
    secret_key: str = ""
    session_timeout: int = 3600  # seconds
    max_upload_size: int = 16777216  # 16MB
    enable_cors: bool = True
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    enable_websocket: bool = True

@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: str = "/var/log/body_composition_gateway.log"
    max_file_size: int = 10485760  # 10MB
    backup_count: int = 5
    enable_console: bool = True
    enable_file: bool = True
    enable_syslog: bool = False

@dataclass
class SecurityConfig:
    """Security configuration"""
    encryption_key: str = ""
    jwt_secret: str = ""
    jwt_expiry: int = 86400  # 24 hours
    api_rate_limit: int = 1000  # requests per hour
    enable_2fa: bool = False
    password_policy: Dict[str, Any] = field(default_factory=lambda: {
        "min_length": 8,
        "require_uppercase": True,
        "require_lowercase": True,
        "require_numbers": True,
        "require_symbols": False
    })

@dataclass
class BackupConfig:
    """Backup configuration"""
    enabled: bool = True
    interval: int = 86400  # 24 hours
    retention_days: int = 30
    backup_path: str = "/home/pi/backups"
    compress: bool = True
    encryption: bool = True
    remote_backup: bool = False
    remote_url: str = ""

@dataclass
class SystemConfig:
    """Complete system configuration"""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    actiwell: ActiwellConfig = field(default_factory=ActiwellConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    web: WebConfig = field(default_factory=WebConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    
    # Metadata
    version: str = "1.0.0"
    environment: str = "production"
    instance_id: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class ConfigValidator:
    """Configuration validation utilities"""
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL format"""
        import re
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return url_pattern.match(url) is not None
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        import re
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        return email_pattern.match(email) is not None
    
    @staticmethod
    def validate_path(path: str) -> bool:
        """Validate file/directory path"""
        try:
            Path(path).resolve()
            return True
        except (OSError, ValueError):
            return False
    
    @staticmethod
    def validate_port(port: int) -> bool:
        """Validate port number"""
        return 1 <= port <= 65535
    
    @staticmethod
    def validate_ip_address(ip: str) -> bool:
        """Validate IP address format"""
        import socket
        try:
            socket.inet_aton(ip)
            return True
        except socket.error:
            return False

class ConfigEncryption:
    """Configuration encryption utilities"""
    
    def __init__(self, key: Optional[str] = None):
        if key:
            self.key = key.encode()
        else:
            self.key = Fernet.generate_key()
        
        self.cipher = Fernet(self.key)
    
    def encrypt_value(self, value: str) -> str:
        """Encrypt a configuration value"""
        try:
            encrypted = self.cipher.encrypt(value.encode())
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return value
    
    def decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt a configuration value"""
        try:
            encrypted_bytes = base64.b64decode(encrypted_value.encode())
            decrypted = self.cipher.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return encrypted_value
    
    def get_key_string(self) -> str:
        """Get encryption key as string"""
        return self.key.decode()

class ConfigurationManager:
    """
    Centralized configuration management system
    Supports multiple sources, validation, encryption, and real-time updates
    """
    
    def __init__(self, config_path: str = "/home/pi/body_composition_gateway/config"):
        self.config_path = Path(config_path)
        self.config_path.mkdir(parents=True, exist_ok=True)
        
        # Configuration storage
        self.config = SystemConfig()
        self.config_fields: Dict[str, ConfigField] = {}
        self.encryption: Optional[ConfigEncryption] = None
        
        # Change tracking
        self.change_callbacks: List[callable] = []
        self.last_modified: Dict[str, datetime] = {}
        
        # File watching
        self.watch_thread: Optional[threading.Thread] = None
        self.stop_watching = threading.Event()
        
        # Initialize
        self._register_config_fields()
        self._initialize_encryption()
        self.load_configuration()
    
    def _register_config_fields(self):
        """Register all configuration fields with validation rules"""
        fields = [
            # Database fields
            ConfigField("database.host", "Database host", ConfigType.STRING, "localhost", 
                       env_var="DB_HOST", category="database"),
            ConfigField("database.port", "Database port", ConfigType.INTEGER, 3306, 
                       min_value=1, max_value=65535, env_var="DB_PORT", category="database"),
            ConfigField("database.username", "Database username", ConfigType.STRING, "body_comp_user", 
                       required=True, env_var="DB_USERNAME", category="database"),
            ConfigField("database.password", "Database password", ConfigType.PASSWORD, "", 
                       required=True, sensitive=True, env_var="DB_PASSWORD", category="database"),
            ConfigField("database.database", "Database name", ConfigType.STRING, "body_composition_db", 
                       required=True, env_var="DB_NAME", category="database"),
            
            # Actiwell fields
            ConfigField("actiwell.api_url", "Actiwell API URL", ConfigType.URL, "", 
                       required=True, env_var="ACTIWELL_API_URL", category="actiwell"),
            ConfigField("actiwell.api_key", "Actiwell API key", ConfigType.PASSWORD, "", 
                       required=True, sensitive=True, env_var="ACTIWELL_API_KEY", category="actiwell"),
            ConfigField("actiwell.location_id", "Actiwell location ID", ConfigType.STRING, "", 
                       required=True, env_var="ACTIWELL_LOCATION_ID", category="actiwell"),
            ConfigField("actiwell.timeout", "API timeout (seconds)", ConfigType.INTEGER, 30, 
                       min_value=5, max_value=300, category="actiwell"),
            
            # Web fields
            ConfigField("web.host", "Web server host", ConfigType.STRING, "0.0.0.0", 
                       env_var="WEB_HOST", category="web"),
            ConfigField("web.port", "Web server port", ConfigType.INTEGER, 5000, 
                       min_value=1024, max_value=65535, env_var="WEB_PORT", category="web"),
            ConfigField("web.debug", "Enable debug mode", ConfigType.BOOLEAN, False, 
                       env_var="WEB_DEBUG", category="web"),
            ConfigField("web.secret_key", "Web secret key", ConfigType.PASSWORD, "", 
                       required=True, sensitive=True, env_var="WEB_SECRET_KEY", category="web"),
            
            # Device fields
            ConfigField("device.auto_detect", "Auto-detect devices", ConfigType.BOOLEAN, True, 
                       category="device"),
            ConfigField("device.scan_interval", "Device scan interval", ConfigType.INTEGER, 60, 
                       min_value=10, max_value=3600, category="device"),
            ConfigField("device.connection_timeout", "Connection timeout", ConfigType.INTEGER, 10, 
                       min_value=5, max_value=60, category="device"),
            
            # Logging fields
            ConfigField("logging.level", "Log level", ConfigType.STRING, "INFO", 
                       allowed_values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                       env_var="LOG_LEVEL", category="logging"),
            ConfigField("logging.file_path", "Log file path", ConfigType.PATH, 
                       "/var/log/body_composition_gateway.log", env_var="LOG_FILE", category="logging"),
            
            # Security fields
            ConfigField("security.jwt_secret", "JWT secret key", ConfigType.PASSWORD, "", 
                       required=True, sensitive=True, env_var="JWT_SECRET", category="security"),
            ConfigField("security.jwt_expiry", "JWT expiry (seconds)", ConfigType.INTEGER, 86400, 
                       min_value=3600, max_value=604800, category="security"),
        ]
        
        for field in fields:
            self.config_fields[field.key] = field
    
    def _initialize_encryption(self):
        """Initialize encryption for sensitive data"""
        encryption_key_file = self.config_path / "encryption.key"
        
        if encryption_key_file.exists():
            with open(encryption_key_file, 'r') as f:
                key = f.read().strip()
        else:
            # Generate new encryption key
            temp_encryption = ConfigEncryption()
            key = temp_encryption.get_key_string()
            
            # Save key securely
            with open(encryption_key_file, 'w') as f:
                f.write(key)
            os.chmod(encryption_key_file, 0o600)  # Read/write for owner only
        
        self.encryption = ConfigEncryption(key)
    
    def load_configuration(self):
        """Load configuration from all sources"""
        logger.info("Loading configuration from all sources")
        
        # Load from files (lowest priority)
        self._load_from_files()
        
        # Override with environment variables
        self._load_from_environment()
        
        # Override with database settings (if available)
        self._load_from_database()
        
        # Generate defaults for missing required fields
        self._generate_defaults()
        
        # Validate configuration
        self._validate_configuration()
        
        # Update timestamps
        self.config.updated_at = datetime.now()
        if not self.config.created_at:
            self.config.created_at = datetime.now()
        
        logger.info("Configuration loaded successfully")
    
    def _load_from_files(self):
        """Load configuration from files"""
        config_files = [
            self.config_path / "config.json",
            self.config_path / "config.yaml",
            self.config_path / "config.yml",
            self.config_path / "config.ini"
        ]
        
        for config_file in config_files:
            if config_file.exists():
                try:
                    self._load_config_file(config_file)
                    logger.info(f"Loaded configuration from {config_file}")
                    break
                except Exception as e:
                    logger.error(f"Error loading {config_file}: {e}")
    
    def _load_config_file(self, config_file: Path):
        """Load configuration from specific file"""
        if config_file.suffix == '.json':
            with open(config_file, 'r') as f:
                data = json.load(f)
        elif config_file.suffix in ['.yaml', '.yml']:
            with open(config_file, 'r') as f:
                data = yaml.safe_load(f)
        elif config_file.suffix == '.ini':
            parser = configparser.ConfigParser()
            parser.read(config_file)
            data = self._ini_to_dict(parser)
        else:
            raise ValueError(f"Unsupported config file format: {config_file.suffix}")
        
        # Apply configuration data
        self._apply_config_data(data)
    
    def _ini_to_dict(self, parser: configparser.ConfigParser) -> Dict:
        """Convert ConfigParser to nested dictionary"""
        result = {}
        for section_name in parser.sections():
            section = {}
            for key, value in parser.items(section_name):
                # Try to convert to appropriate type
                if value.lower() in ['true', 'false']:
                    section[key] = value.lower() == 'true'
                elif value.isdigit():
                    section[key] = int(value)
                elif '.' in value and value.replace('.', '').isdigit():
                    section[key] = float(value)
                else:
                    section[key] = value
            result[section_name] = section
        return result
    
    def _load_from_environment(self):
        """Load configuration from environment variables"""
        for field in self.config_fields.values():
            if field.env_var and field.env_var in os.environ:
                value = os.environ[field.env_var]
                
                # Convert to appropriate type
                converted_value = self._convert_value(value, field.config_type)
                
                # Set in configuration
                self._set_nested_value(self.config, field.key, converted_value)
                
                logger.debug(f"Loaded {field.key} from environment variable {field.env_var}")
    
    def _load_from_database(self):
        """Load configuration from database (if available)"""
        try:
            # This would connect to database and load settings
            # Implementation depends on database availability
            pass
        except Exception as e:
            logger.debug(f"Could not load from database: {e}")
    
    def _generate_defaults(self):
        """Generate default values for missing required fields"""
        for field in self.config_fields.values():
            current_value = self._get_nested_value(self.config, field.key)
            
            if current_value is None and field.required:
                if field.config_type == ConfigType.PASSWORD:
                    # Generate secure random password/key
                    import secrets
                    default_value = secrets.token_urlsafe(32)
                elif field.default_value is not None:
                    default_value = field.default_value
                else:
                    logger.warning(f"No default value for required field: {field.key}")
                    continue
                
                self._set_nested_value(self.config, field.key, default_value)
                logger.info(f"Generated default value for {field.key}")
    
    def _validate_configuration(self):
        """Validate all configuration values"""
        errors = []
        
        for field in self.config_fields.values():
            value = self._get_nested_value(self.config, field.key)
            
            # Check required fields
            if field.required and (value is None or value == ""):
                errors.append(f"Required field missing: {field.key}")
                continue
            
            if value is not None:
                # Type validation
                if not self._validate_type(value, field.config_type):
                    errors.append(f"Invalid type for {field.key}: expected {field.config_type.value}")
                
                # Range validation
                if field.min_value is not None and isinstance(value, (int, float)):
                    if value < field.min_value:
                        errors.append(f"{field.key} below minimum: {value} < {field.min_value}")
                
                if field.max_value is not None and isinstance(value, (int, float)):
                    if value > field.max_value:
                        errors.append(f"{field.key} above maximum: {value} > {field.max_value}")
                
                # Allowed values validation
                if field.allowed_values and value not in field.allowed_values:
                    errors.append(f"{field.key} not in allowed values: {field.allowed_values}")
                
                # Custom validation
                if field.config_type == ConfigType.URL and not ConfigValidator.validate_url(str(value)):
                    errors.append(f"Invalid URL format for {field.key}: {value}")
                
                if field.config_type == ConfigType.PATH and not ConfigValidator.validate_path(str(value)):
                    errors.append(f"Invalid path for {field.key}: {value}")
        
        if errors:
            error_msg = "Configuration validation errors:\n" + "\n".join(f"- {error}" for error in errors)
            raise ValueError(error_msg)
        
        logger.info("Configuration validation passed")
    
    def _apply_config_data(self, data: Dict):
        """Apply configuration data to config object"""
        for key, value in data.items():
            if isinstance(value, dict):
                # Handle nested configuration
                for subkey, subvalue in value.items():
                    full_key = f"{key}.{subkey}"
                    self._set_nested_value(self.config, full_key, subvalue)
            else:
                self._set_nested_value(self.config, key, value)
    
    def _get_nested_value(self, obj: Any, key: str) -> Any:
        """Get nested value using dot notation"""
        keys = key.split('.')
        current = obj
        
        for k in keys:
            if hasattr(current, k):
                current = getattr(current, k)
            else:
                return None
        
        return current
    
    def _set_nested_value(self, obj: Any, key: str, value: Any):
        """Set nested value using dot notation"""
        keys = key.split('.')
        current = obj
        
        for k in keys[:-1]:
            if not hasattr(current, k):
                return
            current = getattr(current, k)
        
        if hasattr(current, keys[-1]):
            setattr(current, keys[-1], value)
    
    def _convert_value(self, value: str, config_type: ConfigType) -> Any:
        """Convert string value to appropriate type"""
        if config_type == ConfigType.BOOLEAN:
            return value.lower() in ['true', '1', 'yes', 'on']
        elif config_type == ConfigType.INTEGER:
            return int(value)
        elif config_type == ConfigType.FLOAT:
            return float(value)
        elif config_type == ConfigType.LIST:
            return value.split(',') if value else []
        elif config_type == ConfigType.DICT:
            return json.loads(value) if value else {}
        else:
            return value
    
    def _validate_type(self, value: Any, config_type: ConfigType) -> bool:
        """Validate value type"""
        type_map = {
            ConfigType.STRING: str,
            ConfigType.INTEGER: int,
            ConfigType.FLOAT: (int, float),
            ConfigType.BOOLEAN: bool,
            ConfigType.LIST: list,
            ConfigType.DICT: dict,
            ConfigType.PASSWORD: str,
            ConfigType.PATH: str,
            ConfigType.URL: str
        }
        
        expected_type = type_map.get(config_type, str)
        return isinstance(value, expected_type)
    
    def save_configuration(self, format: str = "json"):
        """Save current configuration to file"""
        try:
            config_dict = self._config_to_dict()
            
            # Encrypt sensitive values
            encrypted_dict = self._encrypt_sensitive_values(config_dict)
            
            if format == "json":
                config_file = self.config_path / "config.json"
                with open(config_file, 'w') as f:
                    json.dump(encrypted_dict, f, indent=2, default=str)
            elif format in ["yaml", "yml"]:
                config_file = self.config_path / "config.yaml"
                with open(config_file, 'w') as f:
                    yaml.dump(encrypted_dict, f, indent=2, default_flow_style=False)
            else:
                raise ValueError(f"Unsupported format: {format}")
            
            logger.info(f"Configuration saved to {config_file}")
            
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            raise
    
    def _config_to_dict(self) -> Dict:
        """Convert config object to dictionary"""
        return asdict(self.config)
    
    def _encrypt_sensitive_values(self, config_dict: Dict) -> Dict:
        """Encrypt sensitive configuration values"""
        encrypted_dict = config_dict.copy()
        
        for field in self.config_fields.values():
            if field.sensitive:
                value = self._get_nested_dict_value(encrypted_dict, field.key)
                if value:
                    encrypted_value = self.encryption.encrypt_value(str(value))
                    self._set_nested_dict_value(encrypted_dict, field.key, encrypted_value)
        
        return encrypted_dict
    
    def _get_nested_dict_value(self, dict_obj: Dict, key: str) -> Any:
        """Get value from nested dictionary using dot notation"""
        keys = key.split('.')
        current = dict_obj
        
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        
        return current
    
    def _set_nested_dict_value(self, dict_obj: Dict, key: str, value: Any):
        """Set value in nested dictionary using dot notation"""
        keys = key.split('.')
        current = dict_obj
        
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
    
    def get_value(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key"""
        value = self._get_nested_value(self.config, key)
        return value if value is not None else default
    
    def set_value(self, key: str, value: Any):
        """Set configuration value by key"""
        # Validate field if registered
        if key in self.config_fields:
            field = self.config_fields[key]
            if not self._validate_type(value, field.config_type):
                raise ValueError(f"Invalid type for {key}: expected {field.config_type.value}")
        
        # Set value
        self._set_nested_value(self.config, key, value)
        
        # Update timestamp
        self.config.updated_at = datetime.now()
        
        # Notify callbacks
        self._notify_change_callbacks(key, value)
        
        logger.info(f"Configuration updated: {key}")
    
    def get_category_config(self, category: str) -> Dict:
        """Get all configuration values for a category"""
        result = {}
        
        for field in self.config_fields.values():
            if field.category == category:
                value = self._get_nested_value(self.config, field.key)
                if value is not None:
                    result[field.key] = value
        
        return result
    
    def register_change_callback(self, callback: callable):
        """Register callback for configuration changes"""
        self.change_callbacks.append(callback)
    
    def _notify_change_callbacks(self, key: str, value: Any):
        """Notify all change callbacks"""
        for callback in self.change_callbacks:
            try:
                callback(key, value)
            except Exception as e:
                logger.error(f"Error in change callback: {e}")
    
    def start_file_watching(self):
        """Start watching configuration files for changes"""
        if self.watch_thread and self.watch_thread.is_alive():
            return
        
        self.stop_watching.clear()
        self.watch_thread = threading.Thread(target=self._file_watch_loop, daemon=True)
        self.watch_thread.start()
        logger.info("Started configuration file watching")
    
    def stop_file_watching(self):
        """Stop watching configuration files"""
        self.stop_watching.set()
        if self.watch_thread and self.watch_thread.is_alive():
            self.watch_thread.join(timeout=5.0)
        logger.info("Stopped configuration file watching")
    
    def _file_watch_loop(self):
        """File watching loop"""
        while not self.stop_watching.is_set():
            try:
                config_files = list(self.config_path.glob("config.*"))
                
                for config_file in config_files:
                    if config_file.is_file():
                        current_mtime = datetime.fromtimestamp(config_file.stat().st_mtime)
                        last_mtime = self.last_modified.get(str(config_file))
                        
                        if last_mtime is None or current_mtime > last_mtime:
                            logger.info(f"Configuration file changed: {config_file}")
                            self.load_configuration()
                            self.last_modified[str(config_file)] = current_mtime
                            break
                
                time.sleep(1.0)  # Check every second
                
            except Exception as e:
                logger.error(f"File watching error: {e}")
                time.sleep(5.0)
    
    def export_config(self, include_sensitive: bool = False) -> Dict:
        """Export configuration for external use"""
        config_dict = self._config_to_dict()
        
        if not include_sensitive:
            # Remove sensitive values
            for field in self.config_fields.values():
                if field.sensitive:
                    self._set_nested_dict_value(config_dict, field.key, "[HIDDEN]")
        
        return config_dict
    
    def get_field_info(self, key: str) -> Optional[ConfigField]:
        """Get information about a configuration field"""
        return self.config_fields.get(key)
    
    def list_categories(self) -> List[str]:
        """List all configuration categories"""
        categories = set()
        for field in self.config_fields.values():
            categories.add(field.category)
        return sorted(list(categories))
    
    def validate_single_field(self, key: str, value: Any) -> List[str]:
        """Validate a single configuration field"""
        errors = []
        
        if key not in self.config_fields:
            errors.append(f"Unknown configuration field: {key}")
            return errors
        
        field = self.config_fields[key]
        
        # Type validation
        if not self._validate_type(value, field.config_type):
            errors.append(f"Invalid type: expected {field.config_type.value}")
        
        # Range validation
        if field.min_value is not None and isinstance(value, (int, float)):
            if value < field.min_value:
                errors.append(f"Value below minimum: {value} < {field.min_value}")
        
        if field.max_value is not None and isinstance(value, (int, float)):
            if value > field.max_value:
                errors.append(f"Value above maximum: {value} > {field.max_value}")
        
        # Allowed values validation
        if field.allowed_values and value not in field.allowed_values:
            errors.append(f"Value not in allowed values: {field.allowed_values}")
        
        return errors

# Global configuration instance
_config_manager: Optional[ConfigurationManager] = None

def get_config_manager(config_path: str = None) -> ConfigurationManager:
    """Get global configuration manager instance"""
    global _config_manager
    
    if _config_manager is None:
        _config_manager = ConfigurationManager(config_path)
    
    return _config_manager

def get_config(key: str, default: Any = None) -> Any:
    """Get configuration value (convenience function)"""
    return get_config_manager().get_value(key, default)

def set_config(key: str, value: Any):
    """Set configuration value (convenience function)"""
    get_config_manager().set_value(key, value)

# Example usage
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Initialize configuration manager
    config_manager = ConfigurationManager("/tmp/test_config")
    
    # Set some values
    config_manager.set_value("database.host", "localhost")
    config_manager.set_value("database.port", 3306)
    config_manager.set_value("actiwell.api_url", "https://api.actiwell.com")
    
    # Save configuration
    config_manager.save_configuration("json")
    
    # Export configuration
    exported = config_manager.export_config()
    print("Exported configuration:")
    print(json.dumps(exported, indent=2, default=str))
    
    # List categories
    print("\nConfiguration categories:")
    for category in config_manager.list_categories():
        print(f"- {category}")
    
    print("\nConfiguration management test completed")