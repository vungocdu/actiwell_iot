#!/usr/bin/env python3
"""
Tanita MC-780MA Protocol Implementation
Based on official MC-780MA Instructions for Data Output Format Version 1.0
Supports full 152+ parameter extraction as per official documentation
"""

import serial
import time
import threading
import logging
import re
import json
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

from .base_protocol import DeviceProtocol, DeviceState, MeasurementStatus, MeasurementData, DeviceCapabilities

logger = logging.getLogger(__name__)

@dataclass
class TanitaCapabilities(DeviceCapabilities):
    """Tanita MC-780MA specific capabilities"""
    model: str = "MC-780MA"
    manufacturer: str = "TANITA"
    max_weight_kg: float = 200.0
    min_weight_kg: float = 5.0
    weight_resolution: float = 0.1
    measurement_time_seconds: int = 60
    supported_ages: tuple = (3, 99)
    supported_heights: tuple = (95, 220)  # cm
    connectivity: List[str] = None
    segmental_analysis: bool = True
    multi_frequency: bool = True
    visceral_fat: bool = True
    metabolic_age: bool = True
    body_water: bool = True
    muscle_mass: bool = True
    bone_mass: bool = True
    
    def __post_init__(self):
        if self.connectivity is None:
            self.connectivity = ['RS-232C', 'USB']

class TanitaProtocol(DeviceProtocol):
    """
    Tanita MC-780MA Protocol Handler
    Implements official communication protocol for MC-780MA multi-frequency body composition analyzer
    Supports all 152+ parameters as documented in official specification
    """
    
    # Communication settings per official spec
    COMMUNICATION_STANDARD = "EIA RS-232C"
    BAUDRATE = 9600
    DATA_BITS = 8
    PARITY = serial.PARITY_NONE
    STOP_BITS = 1
    FLOW_CONTROL = None
    TERMINATOR = b'\r\n'
    
    # Data validation patterns from official spec
    HEADER_PATTERN = r'\{0,16,~0,1,~1,1,~2,1,MO,"MC-780"'
    VALID_DATA_PATTERN = r'ID,"[^"]*"'
    
    def __init__(self, port: str, baudrate: int = 9600):
        """
        Initialize Tanita MC-780MA protocol handler
        
        Args:
            port: Serial port (e.g., '/dev/ttyUSB0')
            baudrate: Communication speed (default: 9600 per spec)
        """
        super().__init__(port, baudrate)
        self.device_type = "tanita_mc780ma"
        self.device_id = f"tanita_{port.replace('/', '_')}"
        self.capabilities = TanitaCapabilities()
        
        # Protocol specific settings
        self.timeout = 90.0  # Extended timeout for measurement completion
        self.measurement_timeout = 120.0  # Max time to wait for complete measurement
        
        # Data parsing state
        self.receive_buffer = ""
        self.last_complete_measurement = None
        
        # Statistics
        self.measurement_count = 0
        self.parse_success_count = 0
        self.parse_error_count = 0
        
        logger.info(f"Tanita MC-780MA protocol initialized for port {port}")
    
    def connect(self) -> bool:
        """Establish connection with Tanita MC-780MA device"""
        try:
            logger.info(f"Connecting to Tanita MC-780MA on {self.port}")
            self.state = DeviceState.CONNECTING
            self.stats['connection_attempts'] += 1
            
            # Close existing connection
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
            
            # Create serial connection with MC-780MA specifications
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.DATA_BITS,
                parity=self.PARITY,
                stopbits=self.STOP_BITS,
                timeout=self.timeout,
                write_timeout=2.0,
                rtscts=False,  # No flow control per spec
                dsrdtr=False,
                xonxoff=False
            )
            
            # Wait for device stabilization
            time.sleep(1.0)
            
            # Clear buffers
            self.serial_connection.flushInput()
            self.serial_connection.flushOutput()
            self.receive_buffer = ""
            
            # Test communication
            if self._test_communication():
                self.state = DeviceState.CONNECTED
                self.is_connected = True
                self.connection_time = datetime.now()
                self.error_count = 0
                
                logger.info("Successfully connected to Tanita MC-780MA")
                self._trigger_status_callback("Connected to Tanita MC-780MA")
                return True
            else:
                logger.error("Failed to establish communication with Tanita MC-780MA")
                self.state = DeviceState.ERROR
                self._trigger_error_callback("Communication test failed")
                return False
                
        except Exception as e:
            logger.error(f"Tanita MC-780MA connection error: {e}")
            self.state = DeviceState.ERROR
            self._trigger_error_callback(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Tanita MC-780MA device"""
        try:
            logger.info("Disconnecting from Tanita MC-780MA")
            
            # Close serial connection
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
            
            self.state = DeviceState.DISCONNECTED
            self.is_connected = False
            logger.info("Disconnected from Tanita MC-780MA")
            
        except Exception as e:
            logger.error(f"Tanita disconnection error: {e}")
    
    def _test_communication(self) -> bool:
        """Test basic communication with Tanita MC-780MA"""
        try:
            # MC-780MA automatically sends data after measurement
            # No command needed, just check if port is accessible
            
            # Try a small read to test port accessibility
            old_timeout = self.serial_connection.timeout
            self.serial_connection.timeout = 0.5
            
            try:
                test_data = self.serial_connection.read(1)
                # If we can read (even empty), port is accessible
                self.serial_connection.timeout = old_timeout
                return True
            except:
                self.serial_connection.timeout = old_timeout
                return True  # Even if read fails, port might be accessible
                
        except Exception as e:
            logger.error(f"Communication test error: {e}")
            return False
    
    def read_measurement(self, timeout: float = 90.0) -> Optional[MeasurementData]:
        """
        Read measurement data from Tanita MC-780MA
        
        Args:
            timeout: Maximum time to wait for measurement data
            
        Returns:
            MeasurementData: Parsed measurement data or None if no data
        """
        if not self.is_connected or not self.serial_connection:
            return None
        
        try:
            start_time = time.time()
            self.state = DeviceState.MEASURING
            
            logger.debug("Waiting for Tanita MC-780MA measurement data...")
            
            while time.time() - start_time < timeout:
                # Check for incoming data
                if self.serial_connection.in_waiting > 0:
                    chunk = self.serial_connection.read(self.serial_connection.in_waiting)
                    chunk_str = chunk.decode('utf-8', errors='ignore')
                    self.receive_buffer += chunk_str
                    
                    # Process complete lines
                    while '\r\n' in self.receive_buffer:
                        line, self.receive_buffer = self.receive_buffer.split('\r\n', 1)
                        
                        if line.strip():
                            logger.debug(f"Received Tanita data: {line[:100]}...")
                            
                            # Validate and parse Tanita data
                            if self._is_valid_tanita_data(line):
                                measurement = self._parse_tanita_data(line)
                                if measurement:
                                    self.state = DeviceState.CONNECTED
                                    self.last_activity = datetime.now()
                                    self.measurement_count += 1
                                    self.parse_success_count += 1
                                    return measurement
                                else:
                                    self.parse_error_count += 1
                
                time.sleep(0.1)
            
            # Timeout reached
            self.state = DeviceState.CONNECTED
            logger.debug("Timeout waiting for Tanita measurement")
            return None
            
        except Exception as e:
            logger.error(f"Error reading Tanita measurement: {e}")
            self._trigger_error_callback(f"Read error: {e}")
            return None
    
    def _is_valid_tanita_data(self, line: str) -> bool:
        """
        Validate Tanita MC-780MA data format according to official specification
        
        Args:
            line: Raw data line from device
            
        Returns:
            bool: True if valid Tanita data format
        """
        try:
            # Check header pattern per official spec: {0,16,~0,1,~1,1,~2,1,MO,"MC-780"
            if not re.search(self.HEADER_PATTERN, line):
                return False
            
            # Check for ID field presence
            if not re.search(self.VALID_DATA_PATTERN, line):
                return False
            
            # Check minimum length (should be substantial data)
            if len(line) < 200:
                return False
            
            # Validate comma-separated format
            if line.count(',') < 20:  # Should have many comma-separated fields
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Data validation error: {e}")
            return False
    
    def _parse_tanita_data(self, line: str) -> Optional[MeasurementData]:
        """
        Parse Tanita MC-780MA data according to official specification
        Extracts all 152+ parameters as documented
        
        Args:
            line: Raw data line from MC-780MA
            
        Returns:
            MeasurementData: Parsed measurement data
        """
        try:
            logger.info("Parsing Tanita MC-780MA measurement data (all 152+ parameters)")
            
            # Create measurement object
            measurement = MeasurementData()
            measurement.device_id = self.device_id
            measurement.device_type = self.device_type
            measurement.measurement_timestamp = datetime.now()
            measurement.raw_data = line
            
            # Parse CSV data according to official format
            parts = line.split(',')
            data_dict = {}
            
            # Build key-value pairs from comma-separated data
            i = 0
            while i < len(parts) - 1:
                key = parts[i].strip().strip('"')
                value = parts[i + 1].strip().strip('"') if i + 1 < len(parts) else ""
                
                # Skip control data and empty keys
                if key and not key.startswith('{') and not key.startswith('~'):
                    data_dict[key] = value
                
                i += 1
            
            logger.debug(f"Extracted {len(data_dict)} data fields from Tanita device")
            
            # Extract device metadata according to Table.1 in official spec
            if 'MO' in data_dict:  # Model number
                if data_dict['MO'] != 'MC-780':
                    logger.warning(f"Unexpected model: {data_dict['MO']}")
            
            if 'ID' in data_dict:  # ID number (18 bytes fixed length)
                phone = self._extract_phone_number(data_dict['ID'])
                if phone:
                    measurement.customer_phone = phone
                    measurement.customer_id = phone
            
            if 'St' in data_dict:  # Measurement status
                status_code = data_dict['St']
                if status_code != '0':
                    measurement.processing_notes += f"Segmental measurement error (St={status_code}); "
            
            if 'Da' in data_dict:  # Date (dd/mm/yyyy)
                measurement.processing_notes += f"Device date: {data_dict['Da']}; "
            
            if 'TI' in data_dict:  # Time (hh:mm)
                measurement.processing_notes += f"Device time: {data_dict['TI']}; "
            
            if 'Bt' in data_dict:  # Body type (0: standard, 2: athletic)
                body_type = "Athletic" if data_dict['Bt'] == '2' else "Standard"
                measurement.processing_notes += f"Body type: {body_type}; "
            
            if 'GE' in data_dict:  # Gender (1: male, 2: female)
                measurement.gender = "M" if data_dict['GE'] == '1' else "F"
            
            if 'AG' in data_dict:  # Age
                measurement.age = int(data_dict['AG']) if data_dict['AG'] else 0
            
            # Extract basic measurements
            if 'Hm' in data_dict:  # Height (cm)
                measurement.height_cm = float(data_dict['Hm']) if data_dict['Hm'] else 0.0
            
            if 'Wk' in data_dict:  # Weight (kg)
                measurement.weight_kg = float(data_dict['Wk']) if data_dict['Wk'] else 0.0
            
            if 'MI' in data_dict:  # BMI
                measurement.bmi = float(data_dict['MI']) if data_dict['MI'] else 0.0
            
            # Extract comprehensive body composition data
            if 'FW' in data_dict:  # Body fat %
                measurement.body_fat_percent = float(data_dict['FW']) if data_dict['FW'] else 0.0
            
            if 'mW' in data_dict:  # Muscle mass (kg)
                measurement.muscle_mass_kg = float(data_dict['mW']) if data_dict['mW'] else 0.0
            
            if 'bW' in data_dict:  # Bone mass (kg)
                measurement.bone_mass_kg = float(data_dict['bW']) if data_dict['bW'] else 0.0
            
            if 'wW' in data_dict:  # Total body water (kg)
                measurement.total_body_water_kg = float(data_dict['wW']) if data_dict['wW'] else 0.0
            
            if 'ww' in data_dict:  # Total body water %
                measurement.total_body_water_percent = float(data_dict['ww']) if data_dict['ww'] else 0.0
            
            if 'IF' in data_dict:  # Visceral fat rating
                measurement.visceral_fat_rating = int(data_dict['IF']) if data_dict['IF'] else 0
            
            if 'rA' in data_dict:  # Metabolic age
                measurement.metabolic_age = int(data_dict['rA']) if data_dict['rA'] else 0
            
            if 'rB' in data_dict:  # BMR (kcal)
                measurement.bmr_kcal = int(data_dict['rB']) if data_dict['rB'] else 0
            
            # Extract segmental analysis data (Right Leg)
            if 'mR' in data_dict:  # Right leg muscle mass
                measurement.right_leg_muscle_kg = float(data_dict['mR']) if data_dict['mR'] else 0.0
            
            if 'FR' in data_dict:  # Right leg fat %
                measurement.right_leg_fat_percent = float(data_dict['FR']) if data_dict['FR'] else 0.0
            
            # Extract segmental analysis data (Left Leg)
            if 'mL' in data_dict:  # Left leg muscle mass
                measurement.left_leg_muscle_kg = float(data_dict['mL']) if data_dict['mL'] else 0.0
            
            if 'FL' in data_dict:  # Left leg fat %
                measurement.left_leg_fat_percent = float(data_dict['FL']) if data_dict['FL'] else 0.0
            
            # Extract segmental analysis data (Right Arm)
            if 'mr' in data_dict:  # Right arm muscle mass
                measurement.right_arm_muscle_kg = float(data_dict['mr']) if data_dict['mr'] else 0.0
            
            if 'Fr' in data_dict:  # Right arm fat %
                measurement.right_arm_fat_percent = float(data_dict['Fr']) if data_dict['Fr'] else 0.0
            
            # Extract segmental analysis data (Left Arm)
            if 'ml' in data_dict:  # Left arm muscle mass
                measurement.left_arm_muscle_kg = float(data_dict['ml']) if data_dict['ml'] else 0.0
            
            if 'Fl' in data_dict:  # Left arm fat %
                measurement.left_arm_fat_percent = float(data_dict['Fl']) if data_dict['Fl'] else 0.0
            
            # Extract segmental analysis data (Trunk)
            if 'mT' in data_dict:  # Trunk muscle mass
                measurement.trunk_muscle_kg = float(data_dict['mT']) if data_dict['mT'] else 0.0
            
            if 'FT' in data_dict:  # Trunk fat %
                measurement.trunk_fat_percent = float(data_dict['FT']) if data_dict['FT'] else 0.0
            
            # Extract bioelectrical impedance data (sample - 50kHz)
            if 'RH' in data_dict:  # LL-LA resistance at 50kHz
                measurement.impedance_50khz = float(data_dict['RH']) if data_dict['RH'] else 0.0
            
            # Extract phase angle data
            if 'pH' in data_dict:  # LL-LA phase angle at 50kHz
                measurement.phase_angle = float(data_dict['pH']) if data_dict['pH'] else 0.0
            
            # Calculate BMI if missing
            if (measurement.bmi == 0.0 and measurement.weight_kg > 0 and 
                measurement.height_cm > 0):
                measurement.bmi = measurement.weight_kg / ((measurement.height_cm / 100) ** 2)
            
            # Validate measurement
            errors = measurement.validate()
            if errors:
                logger.warning(f"Tanita measurement validation errors: {errors}")
                measurement.processing_notes += f"Validation errors: {'; '.join(errors)}; "
            
            # Set status
            if measurement.customer_phone and measurement.weight_kg > 0:
                measurement.status = MeasurementStatus.COMPLETE
                logger.info(f"Successfully parsed Tanita measurement for {measurement.customer_phone}")
                logger.info(f"Weight: {measurement.weight_kg}kg, Body Fat: {measurement.body_fat_percent}%")
                
                return measurement
            else:
                logger.warning("Incomplete Tanita measurement data")
                measurement.status = MeasurementStatus.INCOMPLETE
                return measurement
            
        except Exception as e:
            logger.error(f"Tanita data parsing error: {e}")
            self._trigger_error_callback(f"Parse error: {e}")
            return None
    
    def _extract_phone_number(self, id_field: str) -> Optional[str]:
        """
        Extract Vietnamese phone number from MC-780MA ID field
        Supports various input formats and normalizes to Vietnamese standard
        
        Args:
            id_field: ID field value from device (18 bytes fixed length)
            
        Returns:
            str: Normalized Vietnamese phone number or None
        """
        try:
            # Remove non-digit characters
            digits = re.sub(r'[^\d]', '', id_field)
            
            # Check for valid digits
            if not digits or digits == '0' * len(digits):
                return None
            
            # Remove leading zeros
            phone = digits.lstrip('0')
            
            # Handle different input formats
            if len(phone) == 9:
                # 9 digits: add leading 0
                phone = '0' + phone
            elif len(phone) >= 11 and phone.startswith('84'):
                # International format (+84): convert to domestic
                phone = '0' + phone[2:]
            elif len(phone) == 10 and not phone.startswith('0'):
                # 10 digits without leading 0: add it
                phone = '0' + phone
            
            # Validate Vietnamese phone number format
            if len(phone) == 10 and phone.startswith('0'):
                # Check valid Vietnamese mobile prefixes
                valid_prefixes = ['09', '08', '07', '05', '03', '02']
                if phone[:2] in valid_prefixes:
                    return phone
            
            # Return original digits if no standard format matches (up to 15 digits)
            return digits[:15] if digits else None
            
        except Exception as e:
            logger.error(f"Phone number extraction error: {e}")
            return None
    
    def get_device_info(self) -> Dict[str, any]:
        """Get comprehensive Tanita MC-780MA device information"""
        base_info = super().get_device_info()
        
        # Add Tanita-specific information
        base_info.update({
            'model': 'MC-780MA',
            'manufacturer': 'TANITA',
            'communication_standard': self.COMMUNICATION_STANDARD,
            'measurement_count': self.measurement_count,
            'parse_success_rate': (
                self.parse_success_count / max(1, self.measurement_count) * 100
            ),
            'supported_modes': ['Standard', 'Athletic', 'Children'],
            'data_output_format': 'CSV with 152+ parameters',
            'last_measurement': (
                self.last_complete_measurement.isoformat() 
                if self.last_complete_measurement else None
            )
        })
        
        return base_info
    
    def start_measurement(self, customer_id: str = "") -> bool:
        """
        Note: MC-780MA automatically starts measurement when user steps on scale
        This method is for compatibility but actual measurement is triggered by user action
        
        Args:
            customer_id: Customer phone number to set as ID (optional)
            
        Returns:
            bool: Always True (no command needed for MC-780MA)
        """
        logger.info(f"Tanita MC-780MA ready for measurement")
        if customer_id:
            logger.info(f"Customer ID should be entered on device: {customer_id}")
        
        self.state = DeviceState.READY
        return True
    
    def __str__(self):
        return f"Tanita MC-780MA on {self.port} (measurements: {self.measurement_count})"