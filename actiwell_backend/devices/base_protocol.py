#!/usr/bin/env python3
"""
Base Protocol Interface for Body Composition Devices
Defines common interface for all device protocols (Tanita, InBody, etc.)
"""

import serial
import time
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, List, Callable
from datetime import datetime

from ..models import BodyMeasurement

logger = logging.getLogger(__name__)

class DeviceState(Enum):
    """Device connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    MEASURING = "measuring"
    ERROR = "error"
    CALIBRATING = "calibrating"

class MeasurementStatus(Enum):
    """Measurement completion status"""
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    ERROR = "error"
    INVALID = "invalid"

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
        self.serial_connection: Optional[serial.Serial] = None
        self.state = DeviceState.DISCONNECTED
        self.is_connected = False
        
        # Connection configuration
        self.timeout = 5.0
        self.max_retries = 3
        self.retry_delay = 1.0
        
        # Statistics
        self.connection_time: Optional[datetime] = None
        self.last_activity: Optional[datetime] = None
        self.error_count = 0
        
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
    def read_measurement(self) -> Optional[BodyMeasurement]:
        """
        Read measurement data from device
        
        Returns:
            BodyMeasurement: Parsed measurement data or None if no data
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
    
    def get_device_info(self) -> Dict:
        """
        Get device information and status
        
        Returns:
            dict: Device information including state, capabilities, statistics
        """
        return {
            'device_type': self.device_type,
            'port': self.port,
            'baudrate': self.baudrate,
            'state': self.state.value,
            'is_connected': self.is_connected,
            'connection_time': self.connection_time.isoformat() if self.connection_time else None,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None,
            'error_count': self.error_count
        }
    
    def set_callbacks(self, measurement_cb: Callable = None, 
                     status_cb: Callable = None, error_cb: Callable = None):
        """
        Set callback functions for events (optional)
        
        Args:
            measurement_cb: Called when measurement received
            status_cb: Called when status changes
            error_cb: Called when error occurs
        """
        pass
    
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
    
    def _update_error_count(self, increment: bool = True):
        """Update error count and handle error states"""
        if increment:
            self.error_count += 1
            if self.error_count > 10:  # Too many errors
                self.state = DeviceState.ERROR
                logger.warning(f"Device {self.device_type} marked as ERROR due to high error count")
        else:
            self.error_count = 0  # Reset on success
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
    
    def __str__(self):
        return f"{self.device_type} on {self.port} (state: {self.state.value})"
    
    def __repr__(self):
        return f"{self.__class__.__name__}(port='{self.port}', baudrate={self.baudrate})"