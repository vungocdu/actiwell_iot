#!/usr/bin/env python3
"""
Base Protocol Interface for Body Composition Devices
Defines common interface for all device protocols (Tanita, InBody, etc.)
"""

import serial
import time
import logging
import threading
import queue
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, List, Callable, Any
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class DeviceState(Enum):
    """Device connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    MEASURING = "measuring"
    ERROR = "error"
    CALIBRATING = "calibrating"
    READY = "ready"

class MeasurementStatus(Enum):
    """Measurement completion status"""
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    ERROR = "error"
    INVALID = "invalid"
    PROCESSING = "processing"

@dataclass
class DeviceCapabilities:
    """Device capabilities and specifications"""
    model: str
    manufacturer: str
    max_weight_kg: float
    min_weight_kg: float
    weight_resolution: float
    measurement_time_seconds: int
    supported_ages: tuple
    supported_heights: tuple
    connectivity: List[str]
    segmental_analysis: bool = False
    multi_frequency: bool = False
    visceral_fat: bool = False
    metabolic_age: bool = False
    body_water: bool = False
    muscle_mass: bool = False
    bone_mass: bool = False

@dataclass
class MeasurementData:
    """Standard measurement data structure"""
    # Device info
    device_id: str = ""
    device_type: str = ""
    measurement_timestamp: datetime = None
    measurement_uuid: str = ""
    
    # Customer identification
    customer_phone: str = ""
    customer_id: str = ""
    
    # Basic measurements
    weight_kg: float = 0.0
    height_cm: float = 0.0
    bmi: float = 0.0
    age: int = 0
    gender: str = ""  # M/F
    
    # Body composition
    body_fat_percent: float = 0.0
    muscle_mass_kg: float = 0.0
    bone_mass_kg: float = 0.0
    total_body_water_kg: float = 0.0
    total_body_water_percent: float = 0.0
    visceral_fat_rating: int = 0
    metabolic_age: int = 0
    bmr_kcal: int = 0
    
    # Segmental analysis
    right_arm_muscle_kg: float = 0.0
    left_arm_muscle_kg: float = 0.0
    trunk_muscle_kg: float = 0.0
    right_leg_muscle_kg: float = 0.0
    left_leg_muscle_kg: float = 0.0
    
    right_arm_fat_percent: float = 0.0
    left_arm_fat_percent: float = 0.0
    trunk_fat_percent: float = 0.0
    right_leg_fat_percent: float = 0.0
    left_leg_fat_percent: float = 0.0
    
    # Bioelectrical impedance (for devices that support it)
    impedance_50khz: float = 0.0
    impedance_250khz: float = 0.0
    phase_angle: float = 0.0
    
    # Data quality and validation
    measurement_quality: str = "good"  # excellent, good, fair, poor
    data_completeness: float = 0.0  # 0-1 scale
    validation_errors: List[str] = None
    
    # Raw data and metadata
    raw_data: str = ""
    processing_notes: str = ""
    status: MeasurementStatus = MeasurementStatus.INCOMPLETE
    
    def __post_init__(self):
        if self.measurement_timestamp is None:
            self.measurement_timestamp = datetime.now()
        if self.validation_errors is None:
            self.validation_errors = []
    
    def validate(self) -> List[str]:
        """Validate measurement data and return list of errors"""
        errors = []
        
        # Basic validations
        if not self.customer_phone and not self.customer_id:
            errors.append("No customer identification provided")
        
        if self.weight_kg <= 0 or self.weight_kg > 300:
            errors.append(f"Invalid weight: {self.weight_kg}kg")
        
        if self.height_cm > 0 and (self.height_cm < 50 or self.height_cm > 250):
            errors.append(f"Invalid height: {self.height_cm}cm")
        
        if self.body_fat_percent < 0 or self.body_fat_percent > 80:
            errors.append(f"Invalid body fat: {self.body_fat_percent}%")
        
        if self.age > 0 and (self.age < 3 or self.age > 120):
            errors.append(f"Invalid age: {self.age}")
        
        # Calculate BMI if missing but have height/weight
        if self.bmi == 0.0 and self.weight_kg > 0 and self.height_cm > 0:
            self.bmi = self.weight_kg / ((self.height_cm / 100) ** 2)
        
        # Data completeness score
        total_fields = 0
        filled_fields = 0
        
        for field, value in self.__dict__.items():
            if field not in ['validation_errors', 'raw_data', 'processing_notes', 
                           'measurement_timestamp', 'measurement_uuid']:
                total_fields += 1
                if value and value != 0 and value != 0.0 and value != "":
                    filled_fields += 1
        
        self.data_completeness = filled_fields / total_fields if total_fields > 0 else 0.0
        
        # Set quality based on completeness and errors
        if not errors and self.data_completeness > 0.8:
            self.measurement_quality = "excellent"
        elif not errors and self.data_completeness > 0.6:
            self.measurement_quality = "good"
        elif len(errors) <= 2 and self.data_completeness > 0.4:
            self.measurement_quality = "fair"
        else:
            self.measurement_quality = "poor"
        
        self.validation_errors = errors
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = {}
        for key, value in self.__dict__.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, Enum):
                data[key] = value.value
            else:
                data[key] = value
        return data

class DeviceProtocol(ABC):
    """
    Abstract base class for body composition device protocols
    All device protocols must inherit from this class
    """
    
    def __init__(self, port: str, baudrate: int = 9600):
        """
        Initialize device protocol
        
        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0')
            baudrate: Communication speed (default: 9600)
        """
        self.port = port
        self.baudrate = baudrate
        self.device_type = "unknown"
        self.device_id = f"{self.device_type}_{port.replace('/', '_')}"
        self.serial_connection: Optional[serial.Serial] = None
        self.state = DeviceState.DISCONNECTED
        self.is_connected = False
        
        # Communication configuration
        self.timeout = 5.0
        self.write_timeout = 2.0
        self.max_retries = 3
        self.retry_delay = 1.0
        
        # Device capabilities
        self.capabilities: Optional[DeviceCapabilities] = None
        
        # Communication monitoring
        self.connection_time: Optional[datetime] = None
        self.last_activity: Optional[datetime] = None
        self.error_count = 0
        self.stats = {
            'measurements_received': 0,
            'successful_measurements': 0,
            'failed_measurements': 0,
            'connection_attempts': 0,
            'errors': 0,
            'uptime_seconds': 0
        }
        
        # Threading for background operations
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_monitoring = threading.Event()
        
        # Event callbacks
        self.measurement_callback: Optional[Callable] = None
        self.status_callback: Optional[Callable] = None
        self.error_callback: Optional[Callable] = None
        
        logger.debug(f"Device protocol initialized: {self.__class__.__name__} on {port}")
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection with the device
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self):
        """Disconnect from the device"""
        pass
    
    @abstractmethod
    def read_measurement(self, timeout: float = 30.0) -> Optional[MeasurementData]:
        """
        Read measurement data from device
        
        Args:
            timeout: Maximum time to wait for measurement
            
        Returns:
            MeasurementData: Parsed measurement data or None if no data
        """
        pass
    
    def start_measurement(self, customer_id: str = "") -> bool:
        """
        Start measurement process (optional for some devices)
        
        Args:
            customer_id: Customer identifier for the measurement
            
        Returns:
            bool: True if measurement started successfully
        """
        logger.warning(f"start_measurement not implemented for {self.device_type}")
        return False
    
    def calibrate_device(self, reference_weight: Optional[float] = None) -> bool:
        """
        Calibrate device (optional for some devices)
        
        Args:
            reference_weight: Known reference weight for calibration
            
        Returns:
            bool: True if calibration successful
        """
        logger.warning(f"calibrate_device not implemented for {self.device_type}")
        return False
    
    def get_device_info(self) -> Dict[str, Any]:
        """
        Get device information and status
        
        Returns:
            dict: Device information including state, capabilities, statistics
        """
        uptime = 0
        if self.connection_time:
            uptime = (datetime.now() - self.connection_time).total_seconds()
            self.stats['uptime_seconds'] = uptime
        
        return {
            'device_id': self.device_id,
            'device_type': self.device_type,
            'port': self.port,
            'baudrate': self.baudrate,
            'state': self.state.value,
            'is_connected': self.is_connected,
            'connection_time': self.connection_time.isoformat() if self.connection_time else None,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None,
            'error_count': self.error_count,
            'uptime_seconds': uptime,
            'capabilities': self.capabilities.__dict__ if self.capabilities else None,
            'statistics': self.stats.copy()
        }
    
    def set_callbacks(self, measurement_cb: Callable = None, 
                     status_cb: Callable = None, error_cb: Callable = None):
        """
        Set callback functions for events
        
        Args:
            measurement_cb: Called when measurement received
            status_cb: Called when status changes
            error_cb: Called when error occurs
        """
        self.measurement_callback = measurement_cb
        self.status_callback = status_cb
        self.error_callback = error_cb
    
    def validate_connection(self) -> bool:
        """
        Validate current connection status
        
        Returns:
            bool: True if connection is valid and active
        """
        try:
            if not self.serial_connection or not self.serial_connection.is_open:
                return False
            
            # Update last activity
            self.last_activity = datetime.now()
            return True
            
        except Exception as e:
            logger.error(f"Connection validation error: {e}")
            return False
    
    def reset_connection(self) -> bool:
        """
        Reset connection to device
        
        Returns:
            bool: True if reset successful
        """
        try:
            logger.info(f"Resetting connection to {self.device_type} on {self.port}")
            
            self.disconnect()
            time.sleep(2.0)  # Wait before reconnecting
            
            return self.connect()
            
        except Exception as e:
            logger.error(f"Connection reset error: {e}")
            return False
    
    def start_monitoring(self):
        """Start background monitoring thread"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        
        self.stop_monitoring.clear()
        self.monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name=f"{self.device_type}_monitor"
        )
        self.monitor_thread.start()
        logger.debug(f"Monitoring started for {self.device_type}")
    
    def stop_monitoring_thread(self):
        """Stop background monitoring thread"""
        self.stop_monitoring.set()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5.0)
        logger.debug(f"Monitoring stopped for {self.device_type}")
    
    def _monitoring_loop(self):
        """Background monitoring loop"""
        logger.debug(f"Monitoring loop started for {self.device_type}")
        
        while not self.stop_monitoring.is_set():
            try:
                # Check connection health
                if self.is_connected and not self.validate_connection():
                    logger.warning(f"Connection lost for {self.device_type}, attempting reconnect")
                    self.reset_connection()
                
                # Try to read measurements
                if self.is_connected and self.state == DeviceState.CONNECTED:
                    measurement = self.read_measurement(timeout=1.0)
                    if measurement:
                        self.stats['measurements_received'] += 1
                        
                        # Validate measurement
                        errors = measurement.validate()
                        if not errors:
                            self.stats['successful_measurements'] += 1
                            measurement.status = MeasurementStatus.COMPLETE
                        else:
                            self.stats['failed_measurements'] += 1
                            measurement.status = MeasurementStatus.ERROR
                            logger.warning(f"Measurement validation errors: {errors}")
                        
                        # Trigger callback
                        if self.measurement_callback:
                            self.measurement_callback(measurement)
                
                time.sleep(1.0)  # Check every second
                
            except Exception as e:
                logger.error(f"Monitoring loop error for {self.device_type}: {e}")
                self.error_count += 1
                self.stats['errors'] += 1
                time.sleep(5.0)
        
        logger.debug(f"Monitoring loop stopped for {self.device_type}")
    
    def _update_error_count(self, increment: bool = True):
        """Update error count and handle error states"""
        if increment:
            self.error_count += 1
            self.stats['errors'] += 1
            if self.error_count > 10:  # Too many errors
                self.state = DeviceState.ERROR
                logger.warning(f"Device {self.device_type} marked as ERROR due to high error count")
        else:
            self.error_count = 0  # Reset on success
    
    def _trigger_status_callback(self, status: str):
        """Trigger status callback if set"""
        try:
            if self.status_callback:
                self.status_callback(self.device_id, status)
        except Exception as e:
            logger.error(f"Status callback error: {e}")
    
    def _trigger_error_callback(self, error: str):
        """Trigger error callback if set"""
        try:
            if self.error_callback:
                self.error_callback(self.device_id, error)
            self._update_error_count(True)
        except Exception as e:
            logger.error(f"Error callback error: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop_monitoring_thread()
        self.disconnect()
    
    def __str__(self):
        return f"{self.device_type} on {self.port} (state: {self.state.value})"
    
    def __repr__(self):
        return f"{self.__class__.__name__}(port='{self.port}', baudrate={self.baudrate})"