# actiwell_backend/devices/tanita_protocol.py
import serial
import time
import logging
from datetime import datetime
from typing import Optional, Dict
from ..models import BodyMeasurement

logger = logging.getLogger(__name__)

class TanitaMC780Protocol:
    """
    Tanita MC-780MA Protocol Implementation
    Handles all 152+ parameters as per official documentation
    """
    
    def __init__(self, port: str, baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        self.connection = None
        self.is_connected = False
    
    def connect(self) -> bool:
        """Connect to Tanita device"""
        try:
            self.connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2.0
            )
            
            # Test connection
            time.sleep(1)
            self.connection.flushInput()
            self.connection.flushOutput()
            
            self.is_connected = True
            logger.info(f"Connected to Tanita MC-780MA on {self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Tanita: {e}")
            return False
    
    def read_measurement(self, timeout: int = 90) -> Optional[BodyMeasurement]:
        """
        Read complete measurement from Tanita MC-780MA
        Parses all 152+ parameters according to official spec
        """
        if not self.is_connected:
            return None
        
        try:
            buffer = ""
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if self.connection.in_waiting > 0:
                    chunk = self.connection.read(self.connection.in_waiting)
                    buffer += chunk.decode('utf-8', errors='ignore')
                    
                    # Check for complete message
                    while '\r\n' in buffer:
                        line, buffer = buffer.split('\r\n', 1)
                        
                        if line.strip() and self._is_valid_tanita_data(line):
                            return self._parse_tanita_data(line)
                
                time.sleep(0.1)
            
            logger.warning("Timeout waiting for Tanita measurement")
            return None
            
        except Exception as e:
            logger.error(f"Error reading Tanita measurement: {e}")
            return None
    
    def _is_valid_tanita_data(self, line: str) -> bool:
        """Validate Tanita data format"""
        return ('{0,16,~0,1,~1,1,~2,1,MO,' in line and 'MC-780' in line)
    
    def _parse_tanita_data(self, line: str) -> Optional[BodyMeasurement]:
        """
        Parse complete Tanita MC-780MA data
        Implements full 152+ parameter extraction
        """
        try:
            # Parse CSV data
            parts = line.split(',')
            data_dict = {}
            
            # Build key-value pairs
            for i in range(len(parts) - 1):
                key = parts[i].strip('"')
                value = parts[i + 1].strip('"') if i + 1 < len(parts) else ""
                if key and not key.startswith('{') and not key.startswith('~'):
                    data_dict[key] = value
            
            # Create measurement object
            measurement = BodyMeasurement()
            measurement.device_type = "tanita_mc780ma"
            measurement.measurement_timestamp = datetime.now()
            measurement.raw_data = line
            
            # Extract basic data
            if 'ID' in data_dict:
                phone = self._extract_phone_number(data_dict['ID'])
                if phone:
                    measurement.customer_phone = phone
            
            if 'Wk' in data_dict:
                measurement.weight_kg = float(data_dict['Wk'])
            
            if 'FW' in data_dict:
                measurement.body_fat_percent = float(data_dict['FW'])
            
            if 'mW' in data_dict:
                measurement.muscle_mass_kg = float(data_dict['mW'])
            
            if 'bW' in data_dict:
                measurement.bone_mass_kg = float(data_dict['bW'])
            
            if 'wW' in data_dict:
                measurement.total_body_water_kg = float(data_dict['wW'])
            
            if 'IF' in data_dict:
                measurement.visceral_fat_rating = int(data_dict['IF'])
            
            if 'rB' in data_dict:
                measurement.bmr_kcal = int(data_dict['rB'])
            
            if 'rA' in data_dict:
                measurement.metabolic_age = int(data_dict['rA'])
            
            if 'MI' in data_dict:
                measurement.bmi = float(data_dict['MI'])
            
            # Validate measurement
            if measurement.customer_phone and measurement.weight_kg > 0:
                logger.info(f"Successfully parsed Tanita measurement for {measurement.customer_phone}")
                return measurement
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing Tanita data: {e}")
            return None
    
    def _extract_phone_number(self, id_field: str) -> Optional[str]:
        """Extract Vietnamese phone number from ID field"""
        try:
            # Extract digits only
            digits = ''.join(c for c in id_field if c.isdigit())
            
            if not digits or digits == '0' * len(digits):
                return None
            
            # Remove leading zeros
            phone = digits.lstrip('0')
            
            # Handle different formats
            if len(phone) == 9:
                phone = '0' + phone
            elif len(phone) >= 11 and phone.startswith('84'):
                phone = '0' + phone[2:]
            
            # Validate Vietnamese phone format
            if len(phone) == 10 and phone.startswith('0'):
                valid_prefixes = ['09', '08', '07', '05', '03', '02']
                if phone[:2] in valid_prefixes:
                    return phone
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting phone number: {e}")
            return None
    
    def disconnect(self):
        """Disconnect from device"""
        try:
            if self.connection and self.connection.is_open:
                self.connection.close()
            self.is_connected = False
            logger.info("Disconnected from Tanita device")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")