#!/usr/bin/env python3
"""
Advanced Device Communication Protocol for Tanita MC-780MA
Enhanced serial communication with error handling and data validation
"""

import serial
import time
import threading
import queue
import logging
import re
import struct
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
import crc16
import json

# Configure logging
logger = logging.getLogger(__name__)

class DeviceState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    MEASURING = "measuring"
    ERROR = "error"
    CALIBRATING = "calibrating"

class MeasurementStatus(Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    ERROR = "error"
    INVALID = "invalid"

@dataclass
class DeviceCapabilities:
    """Device capabilities and features"""
    model: str
    max_weight_kg: float
    min_weight_kg: float
    weight_resolution: float
    supported_frequencies: List[int]
    segmental_analysis: bool
    visceral_fat: bool
    metabolic_age: bool
    body_type_detection: bool
    multi_frequency: bool

@dataclass
class CommunicationConfig:
    """Serial communication configuration"""
    port: str
    baudrate: int = 9600
    bytesize: int = serial.EIGHTBITS
    parity: str = serial.PARITY_NONE
    stopbits: int = serial.STOPBITS_ONE
    timeout: float = 2.0
    write_timeout: float = 1.0
    rtscts: bool = False
    dsrdtr: bool = False
    xonxoff: bool = False

class TanitaProtocolHandler:
    """
    Advanced protocol handler for Tanita MC-780MA body composition analyzer
    Implements full communication protocol with error recovery
    """
    
    # Protocol constants
    STX = 0x02  # Start of text
    ETX = 0x03  # End of text
    ACK = 0x06  # Acknowledge
    NAK = 0x15  # Negative acknowledge
    ENQ = 0x05  # Enquiry
    EOT = 0x04  # End of transmission
    
    # Command codes
    CMD_STATUS = "ST"
    CMD_VERSION = "VR"
    CMD_CALIBRATE = "CA"
    CMD_MEASURE = "MS"
    CMD_DATA_REQUEST = "DR"
    CMD_SET_TIME = "TM"
    CMD_SET_ID = "ID"
    CMD_RESET = "RS"
    
    def __init__(self, config: CommunicationConfig):
        self.config = config
        self.serial_connection: Optional[serial.Serial] = None
        self.state = DeviceState.DISCONNECTED
        self.capabilities: Optional[DeviceCapabilities] = None
        
        # Communication buffers and queues
        self.receive_buffer = bytearray()
        self.command_queue = queue.Queue()
        self.response_queue = queue.Queue()
        
        # Threading
        self.communication_thread: Optional[threading.Thread] = None
        self.stop_communication = threading.Event()
        
        # Callbacks
        self.measurement_callback: Optional[Callable] = None
        self.status_callback: Optional[Callable] = None
        self.error_callback: Optional[Callable] = None
        
        # Statistics
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'errors': 0,
            'successful_measurements': 0,
            'failed_measurements': 0,
            'last_communication': None
        }
        
        # Error recovery
        self.max_retries = 3
        self.retry_delay = 1.0
        self.connection_timeout = 10.0
    
    def connect(self) -> bool:
        """
        Establish connection with Tanita device
        """
        try:
            logger.info(f"Connecting to Tanita device on {self.config.port}")
            self.state = DeviceState.CONNECTING
            
            # Close existing connection if any
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
            
            # Create new serial connection
            self.serial_connection = serial.Serial(
                port=self.config.port,
                baudrate=self.config.baudrate,
                bytesize=self.config.bytesize,
                parity=self.config.parity,
                stopbits=self.config.stopbits,
                timeout=self.config.timeout,
                write_timeout=self.config.write_timeout,
                rtscts=self.config.rtscts,
                dsrdtr=self.config.dsrdtr,
                xonxoff=self.config.xonxoff
            )
            
            # Wait for device to stabilize
            time.sleep(0.5)
            
            # Clear buffers
            self.serial_connection.flushInput()
            self.serial_connection.flushOutput()
            
            # Test communication
            if self._test_communication():
                self.state = DeviceState.CONNECTED
                
                # Start communication thread
                self.stop_communication.clear()
                self.communication_thread = threading.Thread(
                    target=self._communication_loop,
                    daemon=True
                )
                self.communication_thread.start()
                
                # Get device capabilities
                self._initialize_device()
                
                logger.info("Successfully connected to Tanita device")
                return True
            else:
                logger.error("Failed to establish communication with device")
                self.state = DeviceState.ERROR
                return False
                
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.state = DeviceState.ERROR
            return False
    
    def disconnect(self):
        """Disconnect from device"""
        try:
            logger.info("Disconnecting from Tanita device")
            
            # Stop communication thread
            self.stop_communication.set()
            if self.communication_thread and self.communication_thread.is_alive():
                self.communication_thread.join(timeout=5.0)
            
            # Close serial connection
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
            
            self.state = DeviceState.DISCONNECTED
            logger.info("Disconnected from Tanita device")
            
        except Exception as e:
            logger.error(f"Disconnection error: {e}")
    
    def _test_communication(self) -> bool:
        """Test basic communication with device"""
        try:
            # Send enquiry command
            self._send_raw_command(self.ENQ)
            
            # Wait for response
            start_time = time.time()
            while time.time() - start_time < self.connection_timeout:
                if self.serial_connection.in_waiting > 0:
                    response = self.serial_connection.read(1)
                    if len(response) > 0 and response[0] == self.ACK:
                        return True
                time.sleep(0.1)
            
            return False
            
        except Exception as e:
            logger.error(f"Communication test error: {e}")
            return False
    
    def _initialize_device(self):
        """Initialize device and get capabilities"""
        try:
            # Get device version and model
            version_response = self._send_command_sync(self.CMD_VERSION)
            if version_response:
                self._parse_version_info(version_response)
            
            # Get device status
            status_response = self._send_command_sync(self.CMD_STATUS)
            if status_response:
                self._parse_status_info(status_response)
            
        except Exception as e:
            logger.error(f"Device initialization error: {e}")
    
    def _parse_version_info(self, response: str):
        """Parse device version information"""
        try:
            # Example response: "MC-780MA v1.23"
            if "MC-780MA" in response:
                self.capabilities = DeviceCapabilities(
                    model="MC-780MA",
                    max_weight_kg=200.0,
                    min_weight_kg=5.0,
                    weight_resolution=0.1,
                    supported_frequencies=[50, 250],
                    segmental_analysis=True,
                    visceral_fat=True,
                    metabolic_age=True,
                    body_type_detection=True,
                    multi_frequency=True
                )
            
            logger.info(f"Device version: {response}")
            
        except Exception as e:
            logger.error(f"Version parsing error: {e}")
    
    def _parse_status_info(self, response: str):
        """Parse device status information"""
        try:
            # Parse status response for device health
            if "OK" in response:
                logger.info("Device status: OK")
            else:
                logger.warning(f"Device status: {response}")
                
        except Exception as e:
            logger.error(f"Status parsing error: {e}")
    
    def _communication_loop(self):
        """Main communication loop running in background thread"""
        logger.info("Communication loop started")
        
        while not self.stop_communication.is_set():
            try:
                # Process outgoing commands
                self._process_command_queue()
                
                # Read incoming data
                self._read_incoming_data()
                
                # Process received messages
                self._process_received_messages()
                
                time.sleep(0.01)  # Small delay to prevent CPU overload
                
            except Exception as e:
                logger.error(f"Communication loop error: {e}")
                self.stats['errors'] += 1
                time.sleep(0.1)
        
        logger.info("Communication loop stopped")
    
    def _process_command_queue(self):
        """Process pending commands in queue"""
        try:
            while not self.command_queue.empty():
                command_data = self.command_queue.get_nowait()
                self._send_raw_data(command_data)
                self.stats['messages_sent'] += 1
                
        except queue.Empty:
            pass
        except Exception as e:
            logger.error(f"Command processing error: {e}")
    
    def _read_incoming_data(self):
        """Read and buffer incoming data"""
        try:
            if self.serial_connection and self.serial_connection.in_waiting > 0:
                data = self.serial_connection.read(self.serial_connection.in_waiting)
                self.receive_buffer.extend(data)
                self.stats['last_communication'] = datetime.now()
                
        except Exception as e:
            logger.error(f"Data reading error: {e}")
    
    def _process_received_messages(self):
        """Process complete messages from receive buffer"""
        try:
            while True:
                message = self._extract_message_from_buffer()
                if message is None:
                    break
                
                self.stats['messages_received'] += 1
                self._handle_received_message(message)
                
        except Exception as e:
            logger.error(f"Message processing error: {e}")
    
    def _extract_message_from_buffer(self) -> Optional[bytearray]:
        """Extract complete message from receive buffer"""
        try:
            # Look for STX...ETX pattern
            stx_index = -1
            etx_index = -1
            
            for i, byte in enumerate(self.receive_buffer):
                if byte == self.STX and stx_index == -1:
                    stx_index = i
                elif byte == self.ETX and stx_index != -1:
                    etx_index = i
                    break
            
            if stx_index != -1 and etx_index != -1:
                # Extract message including STX and ETX
                message = self.receive_buffer[stx_index:etx_index + 1]
                
                # Remove processed data from buffer
                self.receive_buffer = self.receive_buffer[etx_index + 1:]
                
                return message
            
            # Clean up buffer if it gets too large
            if len(self.receive_buffer) > 1024:
                logger.warning("Receive buffer overflow, clearing")
                self.receive_buffer.clear()
            
            return None
            
        except Exception as e:
            logger.error(f"Message extraction error: {e}")
            return None
    
    def _handle_received_message(self, message: bytearray):
        """Handle a complete received message"""
        try:
            # Validate message
            if not self._validate_message(message):
                logger.warning("Invalid message received")
                return
            
            # Remove STX and ETX
            payload = message[1:-1]
            message_str = payload.decode('ascii', errors='ignore')
            
            # Parse message type and content
            if message_str.startswith('MS:'):
                # Measurement data
                self._handle_measurement_data(message_str[3:])
            elif message_str.startswith('ST:'):
                # Status update
                self._handle_status_update(message_str[3:])
            elif message_str.startswith('ER:'):
                # Error message
                self._handle_error_message(message_str[3:])
            else:
                # Generic response
                self._handle_generic_response(message_str)
                
        except Exception as e:
            logger.error(f"Message handling error: {e}")
    
    def _validate_message(self, message: bytearray) -> bool:
        """Validate message integrity"""
        try:
            # Check minimum length
            if len(message) < 3:
                return False
            
            # Check STX and ETX
            if message[0] != self.STX or message[-1] != self.ETX:
                return False
            
            # Check if message contains valid ASCII
            payload = message[1:-1]
            try:
                payload.decode('ascii')
            except UnicodeDecodeError:
                return False
            
            return True
            
        except Exception:
            return False
    
    def _handle_measurement_data(self, data: str):
        """Handle incoming measurement data"""
        try:
            logger.info(f"Received measurement data: {data}")
            
            # Parse measurement data
            measurement = self._parse_measurement_data(data)
            
            if measurement:
                self.stats['successful_measurements'] += 1
                
                # Callback to application
                if self.measurement_callback:
                    self.measurement_callback(measurement)
            else:
                self.stats['failed_measurements'] += 1
                logger.error("Failed to parse measurement data")
                
        except Exception as e:
            logger.error(f"Measurement handling error: {e}")
            self.stats['failed_measurements'] += 1
    
    def _parse_measurement_data(self, data: str) -> Optional[Dict]:
        """Parse Tanita measurement data format"""
        try:
            measurement = {
                'timestamp': datetime.now(),
                'raw_data': data,
                'status': MeasurementStatus.INCOMPLETE
            }
            
            # Split data into fields (format depends on device configuration)
            fields = data.split(',')
            
            field_map = {
                0: 'customer_id',
                1: 'weight_kg',
                2: 'body_fat_percent',
                3: 'total_body_water_percent',
                4: 'muscle_mass_kg',
                5: 'bone_mass_kg',
                6: 'visceral_fat_rating',
                7: 'metabolic_age',
                8: 'bmr_kcal'
            }
            
            # Parse numeric fields
            for i, field in enumerate(fields):
                if i in field_map:
                    key = field_map[i]
                    try:
                        if key == 'customer_id':
                            measurement[key] = field.strip()
                        elif 'rating' in key or 'age' in key or 'kcal' in key:
                            measurement[key] = int(float(field)) if field.strip() else None
                        else:
                            measurement[key] = float(field) if field.strip() else None
                    except ValueError:
                        logger.warning(f"Invalid value for {key}: {field}")
                        measurement[key] = None
            
            # Validate measurement completeness
            required_fields = ['customer_id', 'weight_kg']
            if all(measurement.get(field) is not None for field in required_fields):
                measurement['status'] = MeasurementStatus.COMPLETE
                
                # Additional validations
                if self._validate_measurement_ranges(measurement):
                    return measurement
                else:
                    measurement['status'] = MeasurementStatus.INVALID
            
            return measurement
            
        except Exception as e:
            logger.error(f"Measurement parsing error: {e}")
            return None
    
    def _validate_measurement_ranges(self, measurement: Dict) -> bool:
        """Validate measurement values are within expected ranges"""
        try:
            # Weight validation
            if measurement.get('weight_kg'):
                weight = measurement['weight_kg']
                if not (5.0 <= weight <= 200.0):
                    logger.warning(f"Weight out of range: {weight} kg")
                    return False
            
            # Body fat validation
            if measurement.get('body_fat_percent'):
                bf = measurement['body_fat_percent']
                if not (1.0 <= bf <= 60.0):
                    logger.warning(f"Body fat out of range: {bf}%")
                    return False
            
            # Visceral fat validation
            if measurement.get('visceral_fat_rating'):
                vf = measurement['visceral_fat_rating']
                if not (1 <= vf <= 59):
                    logger.warning(f"Visceral fat out of range: {vf}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
    
    def _handle_status_update(self, status: str):
        """Handle device status updates"""
        try:
            logger.info(f"Device status: {status}")
            
            if self.status_callback:
                self.status_callback(status)
                
        except Exception as e:
            logger.error(f"Status handling error: {e}")
    
    def _handle_error_message(self, error: str):
        """Handle device error messages"""
        try:
            logger.error(f"Device error: {error}")
            
            self.stats['errors'] += 1
            
            if self.error_callback:
                self.error_callback(error)
                
        except Exception as e:
            logger.error(f"Error handling error: {e}")
    
    def _handle_generic_response(self, response: str):
        """Handle generic device responses"""
        try:
            logger.debug(f"Device response: {response}")
            
            # Put response in queue for sync commands
            self.response_queue.put(response)
            
        except Exception as e:
            logger.error(f"Response handling error: {e}")
    
    def _send_command_sync(self, command: str, timeout: float = 5.0) -> Optional[str]:
        """Send command and wait for response synchronously"""
        try:
            # Clear response queue
            while not self.response_queue.empty():
                self.response_queue.get_nowait()
            
            # Send command
            self._send_command(command)
            
            # Wait for response
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = self.response_queue.get(timeout=0.1)
                    return response
                except queue.Empty:
                    continue
            
            logger.warning(f"Timeout waiting for response to command: {command}")
            return None
            
        except Exception as e:
            logger.error(f"Sync command error: {e}")
            return None
    
    def _send_command(self, command: str, data: str = ""):
        """Send command to device asynchronously"""
        try:
            # Format command message
            message = f"{command}:{data}" if data else command
            
            # Create packet with STX/ETX
            packet = bytearray([self.STX])
            packet.extend(message.encode('ascii'))
            packet.extend([self.ETX])
            
            # Add to command queue
            self.command_queue.put(packet)
            
        except Exception as e:
            logger.error(f"Command sending error: {e}")
    
    def _send_raw_command(self, command_byte: int):
        """Send raw command byte"""
        try:
            self.command_queue.put(bytearray([command_byte]))
        except Exception as e:
            logger.error(f"Raw command error: {e}")
    
    def _send_raw_data(self, data: bytearray):
        """Send raw data to device"""
        try:
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.write(data)
                self.serial_connection.flush()
                
        except Exception as e:
            logger.error(f"Raw data sending error: {e}")
    
    # Public API methods
    def start_measurement(self, customer_id: str = "") -> bool:
        """Start a new measurement"""
        try:
            if self.state != DeviceState.CONNECTED:
                logger.error("Device not connected")
                return False
            
            self.state = DeviceState.MEASURING
            
            # Set customer ID if provided
            if customer_id:
                self._send_command(self.CMD_SET_ID, customer_id)
                time.sleep(0.5)
            
            # Start measurement
            self._send_command(self.CMD_MEASURE)
            
            logger.info(f"Measurement started for customer: {customer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Start measurement error: {e}")
            return False
    
    def calibrate_device(self, weight_kg: Optional[float] = None) -> bool:
        """Calibrate device with optional reference weight"""
        try:
            if self.state not in [DeviceState.CONNECTED, DeviceState.ERROR]:
                logger.error("Device not in correct state for calibration")
                return False
            
            self.state = DeviceState.CALIBRATING
            
            # Send calibration command
            cal_data = str(weight_kg) if weight_kg else ""
            response = self._send_command_sync(self.CMD_CALIBRATE, cal_data)
            
            if response and "OK" in response:
                logger.info("Device calibration successful")
                self.state = DeviceState.CONNECTED
                return True
            else:
                logger.error("Device calibration failed")
                self.state = DeviceState.ERROR
                return False
                
        except Exception as e:
            logger.error(f"Calibration error: {e}")
            self.state = DeviceState.ERROR
            return False
    
    def reset_device(self) -> bool:
        """Reset device to default state"""
        try:
            response = self._send_command_sync(self.CMD_RESET)
            
            if response and "OK" in response:
                logger.info("Device reset successful")
                return True
            else:
                logger.error("Device reset failed")
                return False
                
        except Exception as e:
            logger.error(f"Reset error: {e}")
            return False
    
    def set_callbacks(self, measurement_cb: Callable = None, 
                     status_cb: Callable = None, error_cb: Callable = None):
        """Set callback functions for events"""
        self.measurement_callback = measurement_cb
        self.status_callback = status_cb
        self.error_callback = error_cb
    
    def get_statistics(self) -> Dict:
        """Get communication statistics"""
        return self.stats.copy()
    
    def get_device_info(self) -> Dict:
        """Get device information and capabilities"""
        return {
            'state': self.state.value,
            'capabilities': self.capabilities.__dict__ if self.capabilities else None,
            'config': {
                'port': self.config.port,
                'baudrate': self.config.baudrate
            },
            'statistics': self.get_statistics()
        }
    
    def is_connected(self) -> bool:
        """Check if device is connected and ready"""
        return self.state in [DeviceState.CONNECTED, DeviceState.MEASURING]
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()

# Device manager for multiple devices
class TanitaDeviceManager:
    """
    Manager for multiple Tanita devices
    Handles device discovery, connection management, and load balancing
    """
    
    def __init__(self):
        self.devices: Dict[str, TanitaProtocolHandler] = {}
        self.device_configs: Dict[str, CommunicationConfig] = {}
        self.measurement_queue = queue.Queue()
        
        # Load balancing
        self.last_used_device = None
        
        # Monitoring
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_monitoring = threading.Event()
    
    def add_device(self, device_id: str, config: CommunicationConfig):
        """Add a new device to management"""
        try:
            device = TanitaProtocolHandler(config)
            
            # Set up callbacks
            device.set_callbacks(
                measurement_cb=lambda data, dev_id=device_id: self._handle_measurement(dev_id, data),
                status_cb=lambda status, dev_id=device_id: self._handle_status(dev_id, status),
                error_cb=lambda error, dev_id=device_id: self._handle_error(dev_id, error)
            )
            
            self.devices[device_id] = device
            self.device_configs[device_id] = config
            
            logger.info(f"Added device: {device_id}")
            
        except Exception as e:
            logger.error(f"Error adding device {device_id}: {e}")
    
    def connect_all_devices(self) -> Dict[str, bool]:
        """Connect to all managed devices"""
        results = {}
        
        for device_id, device in self.devices.items():
            try:
                success = device.connect()
                results[device_id] = success
                
                if success:
                    logger.info(f"Connected to device: {device_id}")
                else:
                    logger.error(f"Failed to connect to device: {device_id}")
                    
            except Exception as e:
                logger.error(f"Connection error for device {device_id}: {e}")
                results[device_id] = False
        
        return results
    
    def disconnect_all_devices(self):
        """Disconnect from all devices"""
        for device_id, device in self.devices.items():
            try:
                device.disconnect()
                logger.info(f"Disconnected from device: {device_id}")
            except Exception as e:
                logger.error(f"Disconnection error for device {device_id}: {e}")
    
    def get_available_device(self) -> Optional[str]:
        """Get an available device for measurement"""
        # Simple round-robin load balancing
        connected_devices = [
            dev_id for dev_id, device in self.devices.items()
            if device.is_connected() and device.state == DeviceState.CONNECTED
        ]
        
        if not connected_devices:
            return None
        
        if self.last_used_device in connected_devices:
            current_index = connected_devices.index(self.last_used_device)
            next_index = (current_index + 1) % len(connected_devices)
            self.last_used_device = connected_devices[next_index]
        else:
            self.last_used_device = connected_devices[0]
        
        return self.last_used_device
    
    def start_measurement(self, customer_id: str = "") -> bool:
        """Start measurement on an available device"""
        device_id = self.get_available_device()
        
        if not device_id:
            logger.error("No available devices for measurement")
            return False
        
        device = self.devices[device_id]
        return device.start_measurement(customer_id)
    
    def _handle_measurement(self, device_id: str, measurement_data: Dict):
        """Handle measurement from any device"""
        measurement_data['device_id'] = device_id
        self.measurement_queue.put(measurement_data)
        logger.info(f"Measurement received from device {device_id}")
    
    def _handle_status(self, device_id: str, status: str):
        """Handle status update from device"""
        logger.info(f"Device {device_id} status: {status}")
    
    def _handle_error(self, device_id: str, error: str):
        """Handle error from device"""
        logger.error(f"Device {device_id} error: {error}")
    
    def get_device_status(self) -> Dict:
        """Get status of all devices"""
        status = {}
        
        for device_id, device in self.devices.items():
            status[device_id] = device.get_device_info()
        
        return status
    
    def get_measurement(self, timeout: float = None) -> Optional[Dict]:
        """Get next measurement from queue"""
        try:
            return self.measurement_queue.get(timeout=timeout)
        except queue.Empty:
            return None

# Example usage
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Example device configuration
    config = CommunicationConfig(
        port="/dev/ttyUSB0",
        baudrate=9600,
        timeout=2.0
    )
    
    # Test single device
    with TanitaProtocolHandler(config) as device:
        if device.is_connected():
            print("Device connected successfully")
            
            # Start a test measurement
            device.start_measurement("0901234567")
            
            # Wait for measurement
            time.sleep(10)
        else:
            print("Failed to connect to device")
    
    print("Device communication test completed")