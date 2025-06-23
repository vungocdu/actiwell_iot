#!/usr/bin/env python3
"""
InBody 270 Protocol Implementation
Enhanced serial communication with comprehensive data parsing
Compatible with InBody 270 body composition analyzer
"""

import serial
import time
import threading
import queue
import logging
import re
import json
import struct
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Callable
from dataclasses import dataclass
from enum import Enum

from .base_protocol import DeviceProtocol, DeviceState, MeasurementStatus, MeasurementData, DeviceCapabilities

logger = logging.getLogger(__name__)

@dataclass
@dataclass
class InBodyCapabilities(DeviceCapabilities):
    """InBody 270 device capabilities"""
    model: str = "InBody 270"
    manufacturer: str = "InBody"
    max_weight_kg: float = 250.0
    min_weight_kg: float = 10.0
    weight_resolution: float = 0.1
    measurement_time_seconds: int = 15
    supported_ages: tuple = (3, 99)
    supported_heights: tuple = (95, 220)  # cm
    connectivity: List[str] = None
    segmental_analysis: bool = True
    multi_frequency: bool = True
    visceral_fat: bool = True
    metabolic_age: bool = False  # InBody typically doesn't provide metabolic age
    body_water: bool = True
    muscle_mass: bool = True
    bone_mass: bool = False  # InBody focuses on lean body mass
    
    def __post_init__(self):
        if self.connectivity is None:
            self.connectivity = ['RS-232C', 'USB', 'LAN', 'Bluetooth', 'Wi-Fi']

class InBodyDataFormat(Enum):
    """InBody data output formats"""
    STANDARD = "standard"
    DETAILED = "detailed"
    RAW = "raw"

class InBodyProtocol(DeviceProtocol):
    """
    InBody 270 Protocol Handler
    Implements communication protocol for InBody 270 body composition analyzer
    """
    
    # Protocol constants
    STX = 0x02  # Start of text
    ETX = 0x03  # End of text
    ACK = 0x06  # Acknowledge
    NAK = 0x15  # Negative acknowledge
    ENQ = 0x05  # Enquiry
    EOT = 0x04  # End of transmission
    
    # Command codes for InBody 270
    CMD_STATUS = "STATUS"
    CMD_VERSION = "VER"
    CMD_MEASURE = "MEASURE"
    CMD_RESULT = "RESULT"
    CMD_CONFIG = "CONFIG"
    CMD_RESET = "RESET"
    CMD_CALIBRATE = "CAL"
    
    # InBody 270 specific communication settings
    BAUDRATE = 9600
    DATA_BITS = 8
    PARITY = serial.PARITY_NONE
    STOP_BITS = 1
    
    def __init__(self, port: str, baudrate: int = 9600):
        """
        Initialize InBody protocol handler
        
        Args:
            port: Serial port (e.g., '/dev/ttyUSB0')
            baudrate: Communication speed (default: 9600)
        """
        super().__init__(port, baudrate)
        self.device_type = "inbody_270"
        self.device_id = f"inbody_{port.replace('/', '_')}"
        self.capabilities = InBodyCapabilities()
        self.data_format = InBodyDataFormat.DETAILED
        
        # Communication buffers
        self.receive_buffer = bytearray()
        self.command_queue = queue.Queue()
        self.response_queue = queue.Queue()
        
        # Threading for background communication
        self.communication_thread: Optional[threading.Thread] = None
        self.stop_communication = threading.Event()
        
        # Statistics
        self.stats.update({
            'commands_sent': 0,
            'responses_received': 0,
            'communication_errors': 0
        })
        
        # Configuration
        self.timeout = 30.0  # Measurement timeout
        self.max_retries = 3
        
        logger.info(f"InBody 270 protocol initialized for port {port}")
    
    def connect(self) -> bool:
        """Establish connection with InBody 270 device"""
        try:
            logger.info(f"Connecting to InBody 270 on {self.port}")
            self.state = DeviceState.CONNECTING
            self.stats['connection_attempts'] += 1
            
            # Close existing connection
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
            
            # Create serial connection with InBody 270 settings
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.DATA_BITS,
                parity=self.PARITY,
                stopbits=self.STOP_BITS,
                timeout=2.0,
                write_timeout=1.0,
                rtscts=False,
                dsrdtr=False,
                xonxoff=False
            )
            
            # Wait for device stabilization
            time.sleep(1.0)
            
            # Clear buffers
            self.serial_connection.flushInput()
            self.serial_connection.flushOutput()
            self.receive_buffer.clear()
            
            # Test communication
            if self._test_communication():
                self.state = DeviceState.CONNECTED
                self.is_connected = True
                self.connection_time = datetime.now()
                
                # Start background communication thread
                self._start_communication_thread()
                
                # Get device information
                self._initialize_device()
                
                logger.info("Successfully connected to InBody 270")
                self._trigger_status_callback("Connected to InBody 270")
                return True
            else:
                logger.error("Failed to establish communication with InBody 270")
                self.state = DeviceState.ERROR
                self._trigger_error_callback("Communication test failed")
                return False
                
        except Exception as e:
            logger.error(f"InBody 270 connection error: {e}")
            self.state = DeviceState.ERROR
            self._trigger_error_callback(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from InBody 270 device"""
        try:
            logger.info("Disconnecting from InBody 270")
            
            # Stop communication thread
            self.stop_communication.set()
            if self.communication_thread and self.communication_thread.is_alive():
                self.communication_thread.join(timeout=5.0)
            
            # Close serial connection
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
            
            self.state = DeviceState.DISCONNECTED
            self.is_connected = False
            logger.info("Disconnected from InBody 270")
            
        except Exception as e:
            logger.error(f"InBody disconnection error: {e}")
    
    def _test_communication(self) -> bool:
        """Test basic communication with InBody 270"""
        try:
            # Send status inquiry
            self._send_command(self.CMD_STATUS)
            
            # Wait for response
            start_time = time.time()
            while time.time() - start_time < 10.0:
                if self.serial_connection.in_waiting > 0:
                    response = self.serial_connection.read(self.serial_connection.in_waiting)
                    response_str = response.decode('utf-8', errors='ignore')
                    
                    if 'INBODY' in response_str.upper() or 'READY' in response_str.upper():
                        logger.debug(f"InBody 270 response: {response_str}")
                        return True
                
                time.sleep(0.1)
            
            # Try alternative communication test
            return self._test_alternative_communication()
            
        except Exception as e:
            logger.error(f"Communication test error: {e}")
            return False
    
    def _test_alternative_communication(self) -> bool:
        """Alternative communication test for InBody 270"""
        try:
            # Send enquiry
            self.serial_connection.write(bytes([self.ENQ]))
            time.sleep(0.5)
            
            if self.serial_connection.in_waiting > 0:
                response = self.serial_connection.read(self.serial_connection.in_waiting)
                return len(response) > 0
            
            return True  # Assume OK if port is accessible
            
        except Exception as e:
            logger.debug(f"Alternative communication test failed: {e}")
            return True  # Be permissive for InBody
    
    def _initialize_device(self):
        """Initialize device and get information"""
        try:
            # Get device version
            version_response = self._send_command_sync(self.CMD_VERSION)
            if version_response:
                logger.info(f"InBody device version: {version_response}")
            
            # Configure device for optimal data output
            self._configure_device()
            
        except Exception as e:
            logger.error(f"Device initialization error: {e}")
    
    def _configure_device(self):
        """Configure InBody 270 for optimal data output"""
        try:
            # Set detailed output format
            config_command = f"{self.CMD_CONFIG},OUTPUT,DETAILED"
            self._send_command(config_command)
            
            # Set automatic transmission
            auto_command = f"{self.CMD_CONFIG},AUTO,ON"
            self._send_command(auto_command)
            
        except Exception as e:
            logger.error(f"Device configuration error: {e}")
    
    def _start_communication_thread(self):
        """Start background communication thread"""
        self.stop_communication.clear()
        self.communication_thread = threading.Thread(
            target=self._communication_loop,
            daemon=True,
            name="InBodyCommThread"
        )
        self.communication_thread.start()
        logger.debug("InBody communication thread started")
    
    def _communication_loop(self):
        """Main communication loop"""
        logger.debug("InBody communication loop started")
        
        while not self.stop_communication.is_set():
            try:
                # Process command queue
                self._process_command_queue()
                
                # Read incoming data
                self._read_incoming_data()
                
                # Process received messages
                self._process_received_messages()
                
                time.sleep(0.01)  # Small delay
                
            except Exception as e:
                logger.error(f"Communication loop error: {e}")
                self.stats['communication_errors'] += 1
                time.sleep(0.1)
        
        logger.debug("InBody communication loop stopped")
    
    def _process_command_queue(self):
        """Process pending commands"""
        try:
            while not self.command_queue.empty():
                command = self.command_queue.get_nowait()
                self._send_raw_command(command)
                self.stats['commands_sent'] += 1
                
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
                self.last_activity = datetime.now()
                
        except Exception as e:
            logger.error(f"Data reading error: {e}")
    
    def _process_received_messages(self):
        """Process complete messages from buffer"""
        try:
            while True:
                message = self._extract_message_from_buffer()
                if message is None:
                    break
                
                self._handle_received_message(message)
                self.stats['responses_received'] += 1
                
        except Exception as e:
            logger.error(f"Message processing error: {e}")
    
    def _extract_message_from_buffer(self) -> Optional[str]:
        """Extract complete message from receive buffer"""
        try:
            buffer_str = self.receive_buffer.decode('utf-8', errors='ignore')
            
            # Look for complete lines (CR+LF terminated)
            if '\r\n' in buffer_str:
                line, remaining = buffer_str.split('\r\n', 1)
                self.receive_buffer = remaining.encode('utf-8')
                return line.strip()
            
            # Alternative: Look for newline terminated
            if '\n' in buffer_str:
                line, remaining = buffer_str.split('\n', 1)
                self.receive_buffer = remaining.encode('utf-8')
                return line.strip()
            
            # Prevent buffer overflow
            if len(buffer_str) > 2000:
                self.receive_buffer.clear()
                logger.warning("InBody receive buffer cleared due to overflow")
            
            return None
            
        except Exception as e:
            logger.error(f"Message extraction error: {e}")
            return None
    
    def _handle_received_message(self, message: str):
        """Handle a received message"""
        try:
            logger.debug(f"InBody message received: {message}")
            
            # Check message type and handle accordingly
            if self._is_measurement_data(message):
                self._handle_measurement_data(message)
            elif message.startswith('STATUS'):
                self._handle_status_message(message)
            elif message.startswith('ERROR'):
                self._handle_error_message(message)
            else:
                self._handle_generic_response(message)
                
        except Exception as e:
            logger.error(f"Message handling error: {e}")
    
    def _is_measurement_data(self, message: str) -> bool:
        """Check if message contains measurement data"""
        # InBody measurement data typically contains key measurements
        measurement_indicators = [
            'Weight:', 'BodyFat:', 'MuscleMass:', 'TBW:', 'BMI:', 'ID:',
            'SKM:', 'BFM:', 'LBM:', 'TBW:', 'Protein:', 'Mineral:', 'VFA:'
        ]
        return any(indicator in message for indicator in measurement_indicators)
    
    def _handle_measurement_data(self, data: str):
        """Handle incoming measurement data"""
        try:
            logger.info(f"Processing InBody measurement data")
            
            measurement = self._parse_inbody_data(data)
            
            if measurement:
                self.stats['successful_measurements'] += 1
                
                if self.measurement_callback:
                    self.measurement_callback(measurement)
            else:
                logger.error("Failed to parse InBody measurement data")
                self.stats['failed_measurements'] += 1
                
        except Exception as e:
            logger.error(f"Measurement handling error: {e}")
    
    def read_measurement(self, timeout: float = 30.0) -> Optional[MeasurementData]:
        """
        Read measurement from InBody 270
        
        Args:
            timeout: Maximum time to wait for measurement
            
        Returns:
            MeasurementData: Parsed measurement data or None
        """
        if not self.is_connected or not self.serial_connection:
            return None
        
        try:
            start_time = time.time()
            
            logger.debug("Waiting for InBody 270 measurement data...")
            
            while time.time() - start_time < timeout:
                # Check for incoming data
                if self.serial_connection.in_waiting > 0:
                    raw_data = ""
                    data_start_time = time.time()
                    
                    # Read data with timeout
                    while time.time() - data_start_time < 15.0:  # InBody measurement time
                        if self.serial_connection.in_waiting > 0:
                            chunk = self.serial_connection.read(self.serial_connection.in_waiting)
                            raw_data += chunk.decode('utf-8', errors='ignore')
                            
                            # Check for complete measurement
                            if self._is_complete_measurement(raw_data):
                                break
                        
                        time.sleep(0.1)
                    
                    if raw_data.strip():
                        return self._parse_inbody_data(raw_data)
                
                time.sleep(0.1)
            
            return None
            
        except Exception as e:
            logger.error(f"Read measurement error: {e}")
            return None
    
    def _parse_inbody_data(self, raw_data: str) -> Optional[MeasurementData]:
        """Parse InBody 270 data format"""
        try:
            measurement = MeasurementData()
            measurement.device_id = self.device_id
            measurement.device_type = self.device_type
            measurement.measurement_timestamp = datetime.now()
            measurement.raw_data = raw_data
            
            # Parse InBody format (key:value pairs separated by commas or newlines)
            data_dict = self._extract_data_fields(raw_data)
            
            # Extract customer identification
            if 'ID' in data_dict:
                measurement.customer_phone = self._extract_phone_number(data_dict['ID'])
                measurement.customer_id = measurement.customer_phone
            
            # Extract basic measurements
            if 'Weight' in data_dict:
                weight_str = data_dict['Weight'].replace('kg', '').replace('Kg', '').strip()
                measurement.weight_kg = float(weight_str) if weight_str else 0.0
            
            if 'Height' in data_dict:
                height_str = data_dict['Height'].replace('cm', '').replace('CM', '').strip()
                measurement.height_cm = float(height_str) if height_str else 0.0
            
            if 'BMI' in data_dict:
                measurement.bmi = float(data_dict['BMI']) if data_dict['BMI'] else 0.0
            
            # Extract body composition
            if 'BodyFat' in data_dict or 'BFM' in data_dict:
                bf_key = 'BodyFat' if 'BodyFat' in data_dict else 'BFM'
                bf_str = data_dict[bf_key].replace('%', '').replace('kg', '').strip()
                if '%' in data_dict[bf_key] or 'BodyFat' in bf_key:
                    measurement.body_fat_percent = float(bf_str) if bf_str else 0.0
                else:
                    # Convert body fat mass to percentage if weight is available
                    if measurement.weight_kg > 0:
                        fat_mass = float(bf_str) if bf_str else 0.0
                        measurement.body_fat_percent = (fat_mass / measurement.weight_kg) * 100
            
            if 'MuscleMass' in data_dict or 'SKM' in data_dict:
                mm_key = 'MuscleMass' if 'MuscleMass' in data_dict else 'SKM'
                mm_str = data_dict[mm_key].replace('kg', '').replace('Kg', '').strip()
                measurement.muscle_mass_kg = float(mm_str) if mm_str else 0.0
            
            if 'TBW' in data_dict:
                tbw_str = data_dict['TBW'].replace('L', '').replace('kg', '').replace('%', '').strip()
                if 'L' in data_dict['TBW'] or 'kg' in data_dict['TBW']:
                    measurement.total_body_water_kg = float(tbw_str) if tbw_str else 0.0
                    # Convert to percentage if weight is available
                    if measurement.weight_kg > 0:
                        measurement.total_body_water_percent = (measurement.total_body_water_kg / measurement.weight_kg) * 100
                else:
                    measurement.total_body_water_percent = float(tbw_str) if tbw_str else 0.0
            
            if 'VFA' in data_dict or 'VisceralFat' in data_dict:
                vf_key = 'VFA' if 'VFA' in data_dict else 'VisceralFat'
                vf_str = data_dict[vf_key].replace('cm²', '').replace('level', '').strip()
                # InBody VFA is in cm², convert to rating scale (approximate)
                vfa_value = float(vf_str) if vf_str else 0.0
                if vfa_value > 0:
                    # Approximate conversion: 100cm² ≈ rating 10
                    measurement.visceral_fat_rating = int(vfa_value / 10) if vfa_value < 600 else 59
            
            # Extract InBody specific segmental data
            self._extract_segmental_data(data_dict, measurement)
            
            # Calculate BMI if missing
            if not measurement.bmi and measurement.weight_kg > 0 and measurement.height_cm > 0:
                measurement.bmi = measurement.weight_kg / ((measurement.height_cm / 100) ** 2)
            
            # Validate measurement
            errors = measurement.validate()
            if errors:
                logger.warning(f"InBody measurement validation errors: {errors}")
                measurement.processing_notes = "; ".join(errors)
            
            if measurement.customer_phone and measurement.weight_kg > 0:
                measurement.status = MeasurementStatus.COMPLETE
                logger.info(f"Successfully parsed InBody measurement for {measurement.customer_phone}")
                return measurement
            
            return None
            
        except Exception as e:
            logger.error(f"InBody data parsing error: {e}")
            return None
    
    def _extract_data_fields(self, raw_data: str) -> Dict[str, str]:
        """Extract data fields from InBody format"""
        data_dict = {}
        
        # Try different parsing methods
        lines = raw_data.replace('\r', '\n').split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Method 1: Key:Value format
            if ':' in line:
                key, value = line.split(':', 1)
                data_dict[key.strip()] = value.strip()
            
            # Method 2: Comma-separated format
            elif ',' in line:
                parts = line.split(',')
                for i in range(0, len(parts) - 1, 2):
                    if i + 1 < len(parts):
                        key = parts[i].strip()
                        value = parts[i + 1].strip()
                        if key and value:
                            data_dict[key] = value
            
            # Method 3: Equal sign format
            elif '=' in line:
                key, value = line.split('=', 1)
                data_dict[key.strip()] = value.strip()
        
        return data_dict
    
    def _extract_phone_number(self, id_field: str) -> str:
        """Extract phone number from ID field"""
        # Remove non-digit characters
        digits = re.sub(r'[^\d]', '', id_field)
        
        if not digits or digits == '0' * len(digits):
            return ""
        
        # Format for Vietnam phone numbers
        if len(digits) >= 9:
            if len(digits) == 9:
                return '0' + digits
            elif len(digits) >= 11 and digits.startswith('84'):
                return '0' + digits[2:]
            elif len(digits) == 10 and digits.startswith('0'):
                return digits
        
        return digits[:15]  # Return first 15 digits if no standard format matches
    
    def _extract_segmental_data(self, data_dict: Dict[str, str], measurement: MeasurementData):
        """Extract InBody segmental analysis data"""
        try:
            # InBody provides detailed segmental data
            segmental_mapping = {
                'RightArmLean': 'right_arm_muscle_kg',
                'LeftArmLean': 'left_arm_muscle_kg',
                'TrunkLean': 'trunk_muscle_kg',
                'RightLegLean': 'right_leg_muscle_kg',
                'LeftLegLean': 'left_leg_muscle_kg',
                'RAL': 'right_arm_muscle_kg',  # Alternative naming
                'LAL': 'left_arm_muscle_kg',
                'TRL': 'trunk_muscle_kg',
                'RLL': 'right_leg_muscle_kg',
                'LLL': 'left_leg_muscle_kg'
            }
            
            for inbody_key, measurement_attr in segmental_mapping.items():
                if inbody_key in data_dict:
                    value_str = data_dict[inbody_key].replace('kg', '').replace('Kg', '').strip()
                    if value_str:
                        setattr(measurement, measurement_attr, float(value_str))
            
        except Exception as e:
            logger.error(f"Segmental data extraction error: {e}")
    
    def _handle_status_message(self, message: str):
        """Handle device status messages"""
        logger.info(f"InBody status: {message}")
        if self.status_callback:
            self.status_callback(message)
    
    def _handle_error_message(self, message: str):
        """Handle device error messages"""
        logger.error(f"InBody error: {message}")
        self.stats['errors'] += 1
        if self.error_callback:
            self.error_callback(message)
    
    def _handle_generic_response(self, message: str):
        """Handle generic device responses"""
        logger.debug(f"InBody response: {message}")
        self.response_queue.put(message)
    
    def _send_command(self, command: str):
        """Send command to device asynchronously"""
        try:
            command_bytes = (command + '\r\n').encode('utf-8')
            self.command_queue.put(command_bytes)
            
        except Exception as e:
            logger.error(f"Command sending error: {e}")
    
    def _send_command_sync(self, command: str, timeout: float = 5.0) -> Optional[str]:
        """Send command and wait for response"""
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
            
            logger.warning(f"Timeout waiting for response to: {command}")
            return None
            
        except Exception as e:
            logger.error(f"Sync command error: {e}")
            return None
    
    def _send_raw_command(self, command_bytes: bytes):
        """Send raw command bytes to device"""
        try:
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.write(command_bytes)
                self.serial_connection.flush()
                
        except Exception as e:
            logger.error(f"Raw command sending error: {e}")
    
    def start_measurement(self, customer_id: str = "") -> bool:
        """Start measurement on InBody 270"""
        try:
            if self.state != DeviceState.CONNECTED:
                logger.error("InBody device not connected")
                return False
            
            self.state = DeviceState.MEASURING
            
            # Send measurement command
            if customer_id:
                measure_command = f"{self.CMD_MEASURE},ID,{customer_id}"
            else:
                measure_command = self.CMD_MEASURE
            
            self._send_command(measure_command)
            
            logger.info(f"InBody measurement started for ID: {customer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Start measurement error: {e}")
            return False
    
    def _is_complete_measurement(self, data: str) -> bool:
        """Check if received data contains a complete measurement"""
        # InBody measurement should contain these key elements
        required_elements = ['Weight:', 'ID:']
        return all(element in data for element in required_elements) and len(data) > 100
    
    def get_device_info(self) -> Dict[str, any]:
        """Get comprehensive InBody 270 device information"""
        base_info = super().get_device_info()
        
        # Add InBody-specific information
        base_info.update({
            'model': 'InBody 270',
            'manufacturer': 'InBody',
            'measurement_time': '15 seconds',
            'display': '7-inch TFT LCD touchscreen',
            'supported_connectivity': self.capabilities.connectivity,
            'data_output_format': 'Key-value pairs',
        })
        
        return base_info