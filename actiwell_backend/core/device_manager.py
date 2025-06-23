#!/usr/bin/env python3
"""
Device Manager for Body Composition Devices
Manages multiple Tanita MC-780MA and InBody 270 devices
Provides device discovery, connection management, and measurement coordination
"""

import serial
import time
import threading
import queue
import logging
import glob
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Callable, Any
from dataclasses import dataclass
from enum import Enum

from ..devices.base_protocol import DeviceProtocol, DeviceState, MeasurementStatus, MeasurementData
from ..devices.tanita_protocol import TanitaProtocol
from ..devices.inbody_protocol import InBodyProtocol

logger = logging.getLogger(__name__)

@dataclass
class DeviceInfo:
    """Device information structure"""
    port: str
    device_type: str
    device_id: str
    status: str
    last_seen: datetime
    capabilities: Dict[str, Any] = None
    statistics: Dict[str, Any] = None

class DeviceManager:
    """
    Manager for multiple body composition devices
    Handles device discovery, connection management, and measurement coordination
    """
    
    def __init__(self, database_manager=None):
        """
        Initialize Device Manager
        
        Args:
            database_manager: Database manager instance for storing measurements
        """
        self.database_manager = database_manager
        
        # Device management
        self.devices: Dict[str, DeviceProtocol] = {}
        self.device_configs: Dict[str, Dict] = {}
        
        # Measurement handling
        self.measurement_queue = queue.Queue()
        self.measurement_handlers: List[Callable] = []
        
        # Device discovery and monitoring
        self.auto_discovery_enabled = True
        self.discovery_thread: Optional[threading.Thread] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_monitoring = threading.Event()
        
        # Load balancing for multiple devices
        self.last_used_device = None
        self.device_usage_count: Dict[str, int] = {}
        
        # Statistics
        self.stats = {
            'total_devices': 0,
            'connected_devices': 0,
            'total_measurements': 0,
            'successful_measurements': 0,
            'failed_measurements': 0,
            'uptime_start': datetime.now()
        }
        
        logger.info("Device Manager initialized")
    
    def start_auto_discovery(self, interval: float = 30.0):
        """
        Start automatic device discovery
        
        Args:
            interval: Discovery interval in seconds
        """
        if self.discovery_thread and self.discovery_thread.is_alive():
            return
        
        self.auto_discovery_enabled = True
        self.discovery_thread = threading.Thread(
            target=self._discovery_loop,
            args=(interval,),
            daemon=True,
            name="DeviceDiscovery"
        )
        self.discovery_thread.start()
        logger.info("Device auto-discovery started")
    
    def stop_auto_discovery(self):
        """Stop automatic device discovery"""
        self.auto_discovery_enabled = False
        if self.discovery_thread:
            self.discovery_thread.join(timeout=5.0)
        logger.info("Device auto-discovery stopped")
    
    def discover_devices(self) -> Dict[str, DeviceInfo]:
        """
        Discover connected body composition devices
        
        Returns:
            Dict[str, DeviceInfo]: Dictionary of discovered devices
        """
        discovered_devices = {}
        
        try:
            # Scan USB and serial ports
            ports = self._scan_serial_ports()
            
            for port in ports:
                device_info = self._identify_device(port)
                if device_info:
                    discovered_devices[port] = device_info
                    logger.info(f"Discovered {device_info.device_type} on {port}")
            
            logger.info(f"Discovery completed: {len(discovered_devices)} devices found")
            
        except Exception as e:
            logger.error(f"Device discovery error: {e}")
        
        return discovered_devices
    
    def _scan_serial_ports(self) -> List[str]:
        """Scan for available serial ports"""
        ports = []
        
        # Common serial port patterns
        port_patterns = [
            '/dev/ttyUSB*',
            '/dev/ttyACM*', 
            '/dev/ttyS*',
            '/dev/cu.usbserial*',  # macOS
            'COM*'  # Windows (if running on Windows)
        ]
        
        for pattern in port_patterns:
            ports.extend(glob.glob(pattern))
        
        # Filter accessible ports
        accessible_ports = []
        for port in ports:
            try:
                # Quick test to see if port is accessible
                test_serial = serial.Serial(port, 9600, timeout=0.5)
                test_serial.close()
                accessible_ports.append(port)
            except Exception:
                pass  # Port not accessible
        
        logger.debug(f"Found {len(accessible_ports)} accessible serial ports")
        return accessible_ports
    
    def _identify_device(self, port: str) -> Optional[DeviceInfo]:
        """
        Identify device type on a specific port
        
        Args:
            port: Serial port to test
            
        Returns:
            DeviceInfo: Device information if identified, None otherwise
        """
        try:
            # Test for Tanita MC-780MA
            tanita_info = self._test_tanita_device(port)
            if tanita_info:
                return tanita_info
            
            # Test for InBody 270
            inbody_info = self._test_inbody_device(port)
            if inbody_info:
                return inbody_info
            
            # Generic device detection
            return self._test_generic_device(port)
            
        except Exception as e:
            logger.debug(f"Device identification error on {port}: {e}")
            return None
    
    def _test_tanita_device(self, port: str) -> Optional[DeviceInfo]:
        """Test if device on port is Tanita MC-780MA"""
        try:
            # Create temporary connection
            test_serial = serial.Serial(port, 9600, timeout=2.0)
            time.sleep(0.5)
            
            # Check for any pending data (Tanita sends data after measurement)
            if test_serial.in_waiting > 0:
                test_data = test_serial.read(test_serial.in_waiting).decode('utf-8', errors='ignore')
                test_serial.close()
                
                # Check for Tanita data pattern
                if '{0,16,~0,1,~1,1,~2,1,MO,"MC-780"' in test_data:
                    return DeviceInfo(
                        port=port,
                        device_type="tanita_mc780ma",
                        device_id=f"tanita_{port.replace('/', '_')}",
                        status="detected",
                        last_seen=datetime.now()
                    )
            
            test_serial.close()
            
            # For Tanita, we might not have immediate data
            # Return as potential Tanita device for further testing
            return DeviceInfo(
                port=port,
                device_type="tanita_mc780ma",
                device_id=f"tanita_{port.replace('/', '_')}",
                status="potential",
                last_seen=datetime.now()
            )
            
        except Exception as e:
            logger.debug(f"Tanita test failed on {port}: {e}")
            return None
    
    def _test_inbody_device(self, port: str) -> Optional[DeviceInfo]:
        """Test if device on port is InBody 270"""
        try:
            # Create temporary connection
            test_serial = serial.Serial(port, 9600, timeout=2.0)
            time.sleep(0.5)
            
            # Send status inquiry
            test_serial.write(b'STATUS\r\n')
            time.sleep(1.0)
            
            if test_serial.in_waiting > 0:
                response = test_serial.read(test_serial.in_waiting).decode('utf-8', errors='ignore')
                test_serial.close()
                
                # Check for InBody response patterns
                if any(keyword in response.upper() for keyword in ['INBODY', 'READY', 'STATUS']):
                    return DeviceInfo(
                        port=port,
                        device_type="inbody_270",
                        device_id=f"inbody_{port.replace('/', '_')}",
                        status="detected",
                        last_seen=datetime.now()
                    )
            
            test_serial.close()
            return None
            
        except Exception as e:
            logger.debug(f"InBody test failed on {port}: {e}")
            return None
    
    def _test_generic_device(self, port: str) -> Optional[DeviceInfo]:
        """Test for generic body composition device"""
        try:
            # If port is accessible but not specifically identified,
            # assume it might be a Tanita (more common)
            return DeviceInfo(
                port=port,
                device_type="generic",
                device_id=f"generic_{port.replace('/', '_')}",
                status="unknown",
                last_seen=datetime.now()
            )
            
        except Exception as e:
            logger.debug(f"Generic test failed on {port}: {e}")
            return None
    
    def connect_device(self, port: str, device_type: str = None) -> bool:
        """
        Connect to a specific device
        
        Args:
            port: Serial port of the device
            device_type: Type of device ('tanita_mc780ma', 'inbody_270', or None for auto-detect)
            
        Returns:
            bool: True if connection successful
        """
        try:
            # Auto-detect device type if not provided
            if not device_type:
                device_info = self._identify_device(port)
                if device_info:
                    device_type = device_info.device_type
                else:
                    device_type = "tanita_mc780ma"  # Default to Tanita
            
            # Create appropriate device protocol
            if device_type == "tanita_mc780ma":
                device = TanitaProtocol(port)
            elif device_type == "inbody_270":
                device = InBodyProtocol(port)
            else:
                # Default to Tanita for unknown devices
                device = TanitaProtocol(port)
            
            # Set up callbacks
            device.set_callbacks(
                measurement_cb=self._handle_measurement,
                status_cb=self._handle_device_status,
                error_cb=self._handle_device_error
            )
            
            # Attempt connection
            if device.connect():
                device_id = device.device_id
                self.devices[device_id] = device
                self.device_usage_count[device_id] = 0
                
                # Start monitoring for this device
                device.start_monitoring()
                
                # Update statistics
                self.stats['total_devices'] += 1
                self.stats['connected_devices'] += 1
                
                logger.info(f"Successfully connected to {device_type} on {port}")
                return True
            else:
                logger.error(f"Failed to connect to {device_type} on {port}")
                return False
                
        except Exception as e:
            logger.error(f"Device connection error: {e}")
            return False
    
    def connect_all_discovered_devices(self) -> Dict[str, bool]:
        """
        Connect to all discovered devices
        
        Returns:
            Dict[str, bool]: Connection results for each device
        """
        discovered = self.discover_devices()
        results = {}
        
        for port, device_info in discovered.items():
            try:
                success = self.connect_device(port, device_info.device_type)
                results[port] = success
            except Exception as e:
                logger.error(f"Failed to connect to device on {port}: {e}")
                results[port] = False
        
        logger.info(f"Connected to {sum(results.values())}/{len(results)} discovered devices")
        return results
    
    def disconnect_device(self, device_id: str):
        """Disconnect a specific device"""
        try:
            if device_id in self.devices:
                device = self.devices[device_id]
                device.stop_monitoring_thread()
                device.disconnect()
                
                del self.devices[device_id]
                if device_id in self.device_usage_count:
                    del self.device_usage_count[device_id]
                
                self.stats['connected_devices'] -= 1
                logger.info(f"Disconnected device: {device_id}")
            
        except Exception as e:
            logger.error(f"Device disconnection error: {e}")
    
    def disconnect_all_devices(self):
        """Disconnect all devices"""
        device_ids = list(self.devices.keys())
        for device_id in device_ids:
            self.disconnect_device(device_id)
        
        logger.info("All devices disconnected")
    
    def get_available_device(self, device_type: str = None) -> Optional[str]:
        """
        Get an available device for measurement using load balancing
        
        Args:
            device_type: Preferred device type (optional)
            
        Returns:
            str: Device ID of available device or None
        """
        available_devices = []
        
        for device_id, device in self.devices.items():
            if (device.state == DeviceState.CONNECTED and 
                (not device_type or device.device_type == device_type)):
                available_devices.append(device_id)
        
        if not available_devices:
            return None
        
        # Simple round-robin load balancing
        if self.last_used_device in available_devices:
            current_index = available_devices.index(self.last_used_device)
            next_index = (current_index + 1) % len(available_devices)
            self.last_used_device = available_devices[next_index]
        else:
            self.last_used_device = available_devices[0]
        
        return self.last_used_device
    
    def start_measurement(self, customer_id: str = "", device_type: str = None) -> Optional[str]:
        """
        Start measurement on an available device
        
        Args:
            customer_id: Customer identifier
            device_type: Preferred device type
            
        Returns:
            str: Device ID that started measurement or None
        """
        device_id = self.get_available_device(device_type)
        
        if not device_id:
            logger.error("No available devices for measurement")
            return None
        
        device = self.devices[device_id]
        if device.start_measurement(customer_id):
            self.device_usage_count[device_id] += 1
            logger.info(f"Measurement started on {device_id} for customer {customer_id}")
            return device_id
        else:
            logger.error(f"Failed to start measurement on {device_id}")
            return None
    
    def _handle_measurement(self, measurement: MeasurementData):
        """Handle measurement from any device"""
        try:
            # Add to measurement queue
            self.measurement_queue.put(measurement)
            
            # Update statistics
            self.stats['total_measurements'] += 1
            if measurement.status == MeasurementStatus.COMPLETE:
                self.stats['successful_measurements'] += 1
            else:
                self.stats['failed_measurements'] += 1
            
            # Store in database if available
            if self.database_manager:
                try:
                    self.database_manager.save_measurement(measurement)
                    logger.info(f"Measurement saved to database: {measurement.customer_phone}")
                except Exception as e:
                    logger.error(f"Failed to save measurement to database: {e}")
            
            # Trigger registered handlers
            for handler in self.measurement_handlers:
                try:
                    handler(measurement)
                except Exception as e:
                    logger.error(f"Measurement handler error: {e}")
            
            logger.info(f"Measurement processed: {measurement.device_id} -> {measurement.customer_phone}")
            
        except Exception as e:
            logger.error(f"Measurement handling error: {e}")
    
    def _handle_device_status(self, device_id: str, status: str):
        """Handle device status updates"""
        logger.info(f"Device status update: {device_id} -> {status}")
    
    def _handle_device_error(self, device_id: str, error: str):
        """Handle device errors"""
        logger.error(f"Device error: {device_id} -> {error}")
        
        # Attempt to recover from error
        if device_id in self.devices:
            device = self.devices[device_id]
            if device.error_count > 5:  # Too many errors
                logger.warning(f"Device {device_id} has too many errors, attempting reconnection")
                self.disconnect_device(device_id)
                
                # Try to reconnect after a delay
                threading.Timer(10.0, self._reconnect_device, args=(device_id,)).start()
    
    def _reconnect_device(self, device_id: str):
        """Attempt to reconnect a device"""
        try:
            # Extract port from device_id
            if 'tanita_' in device_id:
                port = device_id.replace('tanita_', '').replace('_', '/')
                device_type = 'tanita_mc780ma'
            elif 'inbody_' in device_id:
                port = device_id.replace('inbody_', '').replace('_', '/')
                device_type = 'inbody_270'
            else:
                return
            
            logger.info(f"Attempting to reconnect device: {device_id}")
            if self.connect_device(port, device_type):
                logger.info(f"Successfully reconnected device: {device_id}")
            else:
                logger.error(f"Failed to reconnect device: {device_id}")
                
        except Exception as e:
            logger.error(f"Reconnection error: {e}")
    
    def add_measurement_handler(self, handler: Callable[[MeasurementData], None]):
        """Add a measurement handler function"""
        self.measurement_handlers.append(handler)
    
    def get_measurement(self, timeout: float = None) -> Optional[MeasurementData]:
        """
        Get next measurement from queue
        
        Args:
            timeout: Maximum time to wait for measurement
            
        Returns:
            MeasurementData: Next measurement or None
        """
        try:
            return self.measurement_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_device_status(self) -> Dict[str, Any]:
        """Get status of all managed devices"""
        status = {
            'manager_stats': self.stats.copy(),
            'devices': {}
        }
        
        # Add uptime
        uptime = (datetime.now() - self.stats['uptime_start']).total_seconds()
        status['manager_stats']['uptime_seconds'] = uptime
        
        # Add device information
        for device_id, device in self.devices.items():
            status['devices'][device_id] = {
                'info': device.get_device_info(),
                'usage_count': self.device_usage_count.get(device_id, 0)
            }
        
        return status
    
    def _discovery_loop(self, interval: float):
        """Background device discovery loop"""
        logger.debug("Device discovery loop started")
        
        while self.auto_discovery_enabled:
            try:
                # Discover new devices
                discovered = self.discover_devices()
                
                # Connect to new devices
                for port, device_info in discovered.items():
                    # Check if we already have a device on this port
                    existing_device = None
                    for device_id, device in self.devices.items():
                        if device.port == port:
                            existing_device = device_id
                            break
                    
                    if not existing_device:
                        logger.info(f"New device discovered: {device_info.device_type} on {port}")
                        self.connect_device(port, device_info.device_type)
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Discovery loop error: {e}")
                time.sleep(10.0)
        
        logger.debug("Device discovery loop stopped")
    
    def start_monitoring(self):
        """Start device monitoring"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        
        self.stop_monitoring.clear()
        self.monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="DeviceMonitor"
        )
        self.monitor_thread.start()
        logger.info("Device monitoring started")
    
    def stop_monitoring(self):
        """Stop device monitoring"""
        self.stop_monitoring.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
        logger.info("Device monitoring stopped")
    
    def _monitoring_loop(self):
        """Background device monitoring loop"""
        logger.debug("Device monitoring loop started")
        
        while not self.stop_monitoring.is_set():
            try:
                # Check device health
                for device_id, device in list(self.devices.items()):
                    if not device.validate_connection():
                        logger.warning(f"Device connection lost: {device_id}")
                        # Will be handled by device error callback
                
                time.sleep(30.0)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(10.0)
        
        logger.debug("Device monitoring loop stopped")
    
    def shutdown(self):
        """Shutdown device manager"""
        logger.info("Shutting down Device Manager")
        
        # Stop discovery and monitoring
        self.stop_auto_discovery()
        self.stop_monitoring()
        
        # Disconnect all devices
        self.disconnect_all_devices()
        
        logger.info("Device Manager shutdown complete")