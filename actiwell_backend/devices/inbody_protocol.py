#!/usr/bin/env python3
"""
InBody 370s HL7 Protocol Handler
Professional implementation for InBody 370s body composition analyzer
Dual port support: Listening 2580, Data 2575
"""

import socket
import threading
import time
import logging
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod

from .base_protocol import BaseDeviceProtocol, DeviceMessage, DeviceStatus
from ..core.database_manager import DatabaseManager
from config import INBODY_CONFIG, HL7_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class InBodyMeasurement:
    """InBody 370s measurement data structure"""
    
    # Device identification
    device_id: str
    device_model: str = "InBody-370s"
    measurement_id: str = ""
    
    # Patient information
    patient_id: str = ""
    phone_number: str = ""
    patient_name: str = ""
    gender: str = "M"
    age: Optional[int] = None
    date_of_birth: Optional[str] = None
    
    # Basic measurements
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    bmi: Optional[float] = None
    
    # Body composition
    body_fat_percent: Optional[float] = None
    body_fat_mass_kg: Optional[float] = None
    skeletal_muscle_mass_kg: Optional[float] = None
    fat_free_mass_kg: Optional[float] = None
    total_body_water_kg: Optional[float] = None
    total_body_water_percent: Optional[float] = None
    protein_mass_kg: Optional[float] = None
    mineral_mass_kg: Optional[float] = None
    
    # Advanced metrics
    visceral_fat_area_cm2: Optional[float] = None
    visceral_fat_level: Optional[int] = None
    basal_metabolic_rate_kcal: Optional[int] = None
    
    # Segmental analysis (InBody 370s specialty)
    right_leg_lean_mass_kg: Optional[float] = None
    left_leg_lean_mass_kg: Optional[float] = None
    right_arm_lean_mass_kg: Optional[float] = None
    left_arm_lean_mass_kg: Optional[float] = None
    trunk_lean_mass_kg: Optional[float] = None
    
    # Bioelectrical impedance
    impedance_1khz: Optional[float] = None
    impedance_5khz: Optional[float] = None
    impedance_50khz: Optional[float] = None
    impedance_250khz: Optional[float] = None
    impedance_500khz: Optional[float] = None
    impedance_1000khz: Optional[float] = None
    
    # Phase angle
    phase_angle_50khz: Optional[float] = None
    phase_angle_whole_body: Optional[float] = None
    
    # Quality indicators
    measurement_quality: str = "good"
    contact_quality: Dict[str, str] = None
    
    # Metadata
    measurement_timestamp: datetime = None
    raw_hl7_message: str = ""
    hl7_message_type: str = "ORU"
    
    def __post_init__(self):
        if self.measurement_timestamp is None:
            self.measurement_timestamp = datetime.now()
        if self.contact_quality is None:
            self.contact_quality = {}


class HL7MessageParser:
    """HL7 v2.5 message parser for InBody 370s"""
    
    def __init__(self, config: Dict = None):
        self.config = config or HL7_CONFIG
        self.segment_separator = self.config.get('segment_separator', '\r')
        self.field_separator = self.config.get('field_separator', '|')
        
    def parse_message(self, raw_message: str) -> Optional[InBodyMeasurement]:
        """Parse HL7 message into InBodyMeasurement object"""
        try:
            logger.debug(f"Parsing HL7 message: {len(raw_message)} characters")
            
            # Split into segments
            segments = raw_message.split(self.segment_separator)
            segments = [seg.strip() for seg in segments if seg.strip()]
            
            if not segments:
                logger.warning("Empty HL7 message received")
                return None
            
            # Initialize measurement object
            measurement = InBodyMeasurement(
                device_id="INBODY-370S-001",
                raw_hl7_message=raw_message,
                measurement_timestamp=datetime.now()
            )
            
            # Parse each segment
            for segment in segments:
                self._parse_segment(segment, measurement)
            
            # Validate parsed data
            if self._validate_measurement(measurement):
                logger.info(f"Successfully parsed measurement for patient: {measurement.phone_number}")
                return measurement
            else:
                logger.warning("Measurement validation failed")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing HL7 message: {e}")
            return None
    
    def _parse_segment(self, segment: str, measurement: InBodyMeasurement):
        """Parse individual HL7 segment"""
        if not segment:
            return
        
        fields = segment.split(self.field_separator)
        segment_type = fields[0][:3]
        
        try:
            if segment_type == 'MSH':
                self._parse_msh_segment(fields, measurement)
            elif segment_type == 'PID':
                self._parse_pid_segment(fields, measurement)
            elif segment_type == 'OBR':
                self._parse_obr_segment(fields, measurement)
            elif segment_type == 'OBX':
                self._parse_obx_segment(fields, measurement)
            elif segment_type == 'NTE':
                self._parse_nte_segment(fields, measurement)
        except Exception as e:
            logger.warning(f"Error parsing {segment_type} segment: {e}")
    
    def _parse_msh_segment(self, fields: List[str], measurement: InBodyMeasurement):
        """Parse MSH (Message Header) segment"""
        if len(fields) >= 9:
            measurement.hl7_message_type = fields[8] if len(fields) > 8 else 'ORU'
            
            # Parse timestamp if available
            if len(fields) > 6 and fields[6]:
                timestamp_str = fields[6]
                if len(timestamp_str) >= 14:
                    measurement.measurement_timestamp = datetime.strptime(
                        timestamp_str[:14], '%Y%m%d%H%M%S'
                    )
            
            # Message ID
            if len(fields) > 9:
                measurement.measurement_id = fields[9]
    
    def _parse_pid_segment(self, fields: List[str], measurement: InBodyMeasurement):
        """Parse PID (Patient Identification) segment"""
        # Patient ID (field 3)
        if len(fields) > 2 and fields[2]:
            measurement.patient_id = fields[2].strip('"')
            measurement.phone_number = self._extract_phone_number(measurement.patient_id)
        
        # Patient name (field 5)
        if len(fields) > 5 and fields[5]:
            measurement.patient_name = fields[5].strip('"')
        
        # Date of birth (field 7)
        if len(fields) > 7 and fields[7]:
            measurement.date_of_birth = fields[7]
            # Calculate age
            try:
                birth_date = datetime.strptime(fields[7], '%Y%m%d')
                measurement.age = (datetime.now() - birth_date).days // 365
            except ValueError:
                pass
        
        # Gender (field 8)
        if len(fields) > 8 and fields[8]:
            measurement.gender = fields[8].upper()
    
    def _parse_obr_segment(self, fields: List[str], measurement: InBodyMeasurement):
        """Parse OBR (Observation Request) segment"""
        # Observation request details
        if len(fields) > 4:
            # Universal Service ID
            measurement.measurement_id = measurement.measurement_id or fields[2]
    
    def _parse_obx_segment(self, fields: List[str], measurement: InBodyMeasurement):
        """Parse OBX (Observation/Result) segment"""
        if len(fields) < 6:
            return
        
        observation_id = fields[3].strip()
        observation_value = fields[5].strip()
        units = fields[6].strip() if len(fields) > 6 else ''
        
        # Map observations to measurement fields
        try:
            numeric_value = float(observation_value)
        except ValueError:
            logger.debug(f"Non-numeric observation value: {observation_id} = {observation_value}")
            return
        
        # InBody 370s measurement mapping
        measurement_map = {
            # Basic measurements
            'WT': lambda m, v: setattr(m, 'weight_kg', v),
            'HT': lambda m, v: setattr(m, 'height_cm', v),
            'BMI': lambda m, v: setattr(m, 'bmi', v),
            
            # Body composition
            'PBF': lambda m, v: setattr(m, 'body_fat_percent', v),
            'BFM': lambda m, v: setattr(m, 'body_fat_mass_kg', v),
            'SMM': lambda m, v: setattr(m, 'skeletal_muscle_mass_kg', v),
            'FFM': lambda m, v: setattr(m, 'fat_free_mass_kg', v),
            'TBW': lambda m, v: setattr(m, 'total_body_water_kg', v),
            'TBWP': lambda m, v: setattr(m, 'total_body_water_percent', v),
            'PMM': lambda m, v: setattr(m, 'protein_mass_kg', v),
            'MM': lambda m, v: setattr(m, 'mineral_mass_kg', v),
            
            # Advanced metrics
            'VFA': lambda m, v: setattr(m, 'visceral_fat_area_cm2', v),
            'VFL': lambda m, v: setattr(m, 'visceral_fat_level', int(v)),
            'BMR': lambda m, v: setattr(m, 'basal_metabolic_rate_kcal', int(v)),
            
            # Segmental analysis
            'RLA': lambda m, v: setattr(m, 'right_leg_lean_mass_kg', v),
            'LLA': lambda m, v: setattr(m, 'left_leg_lean_mass_kg', v),
            'RAA': lambda m, v: setattr(m, 'right_arm_lean_mass_kg', v),
            'LAA': lambda m, v: setattr(m, 'left_arm_lean_mass_kg', v),
            'TR': lambda m, v: setattr(m, 'trunk_lean_mass_kg', v),
            
            # Bioelectrical impedance
            'IMP1': lambda m, v: setattr(m, 'impedance_1khz', v),
            'IMP5': lambda m, v: setattr(m, 'impedance_5khz', v),
            'IMP50': lambda m, v: setattr(m, 'impedance_50khz', v),
            'IMP250': lambda m, v: setattr(m, 'impedance_250khz', v),
            'IMP500': lambda m, v: setattr(m, 'impedance_500khz', v),
            'IMP1000': lambda m, v: setattr(m, 'impedance_1000khz', v),
            
            # Phase angle
            'PA50': lambda m, v: setattr(m, 'phase_angle_50khz', v),
            'PAWB': lambda m, v: setattr(m, 'phase_angle_whole_body', v),
        }
        
        # Find matching measurement
        for code, setter in measurement_map.items():
            if code in observation_id.upper():
                setter(measurement, numeric_value)
                logger.debug(f"Mapped {observation_id} = {numeric_value} {units}")
                break
    
    def _parse_nte_segment(self, fields: List[str], measurement: InBodyMeasurement):
        """Parse NTE (Notes) segment"""
        if len(fields) > 3:
            note = fields[3].strip()
            logger.debug(f"Note: {note}")
    
    def _extract_phone_number(self, patient_id: str) -> str:
        """Extract Vietnamese phone number from patient ID"""
        if not patient_id:
            return ""
        
        # Remove non-digits
        digits = re.sub(r'[^\d]', '', patient_id)
        
        if not digits or digits == '0' * len(digits):
            return ""
        
        # Format Vietnamese phone number
        if len(digits) >= 9:
            if len(digits) == 9:
                phone = '0' + digits
            elif len(digits) >= 11 and digits.startswith('84'):
                phone = '0' + digits[2:]
            else:
                phone = digits[:10] if len(digits) >= 10 else digits
            
            # Validate Vietnamese phone format
            if len(phone) == 10 and phone.startswith('0'):
                valid_prefixes = ['09', '08', '07', '05', '03', '02']
                if phone[:2] in valid_prefixes:
                    return phone
        
        logger.warning(f"Invalid phone number format: {patient_id}")
        return digits
    
    def _validate_measurement(self, measurement: InBodyMeasurement) -> bool:
        """Validate parsed measurement data"""
        # Check required fields
        if not measurement.phone_number:
            logger.warning("Missing phone number in measurement")
            return False
        
        if not measurement.weight_kg or measurement.weight_kg <= 0:
            logger.warning("Missing or invalid weight in measurement")
            return False
        
        # Phone number format validation
        phone_pattern = r'^0[2-9][0-9]{8}$'
        if not re.match(phone_pattern, measurement.phone_number):
            logger.warning(f"Invalid phone number format: {measurement.phone_number}")
            return False
        
        return True


class InBody370sHandler(BaseDeviceProtocol):
    """InBody 370s HL7 Protocol Handler with dual port support"""
    
    def __init__(self, config: Dict = None, database_manager: DatabaseManager = None):
        super().__init__(config or INBODY_CONFIG)
        self.database_manager = database_manager
        self.hl7_parser = HL7MessageParser()
        
        # Dual port configuration
        self.data_port = self.config.get('data_port', 2575)
        self.listening_port = self.config.get('listening_port', 2580)
        self.device_ip = self.config.get('device_ip', '192.168.1.100')
        
        # Server sockets
        self.data_server = None
        self.command_server = None
        self.running = False
        
        # Message callbacks
        self.message_callbacks: List[Callable] = []
        
        logger.info(f"InBody 370s Handler initialized: Data port {self.data_port}, Listening port {self.listening_port}")
    
    def add_message_callback(self, callback: Callable[[InBodyMeasurement], None]):
        """Add callback for processed measurements"""
        self.message_callbacks.append(callback)
    
    def start(self) -> bool:
        """Start InBody 370s HL7 server with dual port support"""
        try:
            # Start data reception server (port 2575)
            self.data_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.data_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.data_server.bind(('0.0.0.0', self.data_port))
            self.data_server.listen(self.config.get('max_connections', 10))
            
            # Start command interface server (port 2580) - optional
            try:
                self.command_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.command_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.command_server.bind(('0.0.0.0', self.listening_port))
                self.command_server.listen(5)
                logger.info(f"Command interface started on port {self.listening_port}")
            except Exception as e:
                logger.warning(f"Command interface failed to start: {e}")
                self.command_server = None
            
            self.running = True
            
            # Start server threads
            data_thread = threading.Thread(target=self._data_server_loop, daemon=True)
            data_thread.start()
            
            if self.command_server:
                command_thread = threading.Thread(target=self._command_server_loop, daemon=True)
                command_thread.start()
            
            logger.info(f"InBody 370s Handler started successfully on ports {self.data_port}/{self.listening_port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start InBody 370s Handler: {e}")
            self.stop()
            return False
    
    def stop(self):
        """Stop InBody 370s HL7 server"""
        self.running = False
        
        if self.data_server:
            self.data_server.close()
        if self.command_server:
            self.command_server.close()
        
        logger.info("InBody 370s Handler stopped")
    
    def _data_server_loop(self):
        """Main loop for data reception server"""
        logger.info(f"Data server listening on port {self.data_port}")
        
        while self.running:
            try:
                client_socket, client_address = self.data_server.accept()
                logger.info(f"Data connection from {client_address}")
                
                # Handle client in separate thread
                client_thread = threading.Thread(
                    target=self._handle_data_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()
                
            except socket.error as e:
                if self.running:
                    logger.error(f"Data server error: {e}")
                break
    
    def _command_server_loop(self):
        """Main loop for command interface server"""
        logger.info(f"Command server listening on port {self.listening_port}")
        
        while self.running:
            try:
                client_socket, client_address = self.command_server.accept()
                logger.info(f"Command connection from {client_address}")
                
                # Handle command client
                client_thread = threading.Thread(
                    target=self._handle_command_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()
                
            except socket.error as e:
                if self.running:
                    logger.error(f"Command server error: {e}")
                break
    
    def _handle_data_client(self, client_socket: socket.socket, client_address: Tuple[str, int]):
        """Handle data client connection (measurement data)"""
        try:
            buffer = b''
            
            while True:
                data = client_socket.recv(4096)
                if not data:
                    break
                
                buffer += data
                
                # Look for HL7 message terminators
                while b'\x1C\r' in buffer:
                    message_end = buffer.find(b'\x1C\r')
                    message_data = buffer[:message_end]
                    buffer = buffer[message_end + 2:]
                    
                    if message_data:
                        self._process_hl7_message(message_data, client_address)
                        
                        # Send ACK
                        ack = self._create_ack_message()
                        client_socket.send(ack.encode('utf-8'))
        
        except Exception as e:
            logger.error(f"Data client error: {e}")
        finally:
            client_socket.close()
            logger.debug(f"Data client {client_address} disconnected")
    
    def _handle_command_client(self, client_socket: socket.socket, client_address: Tuple[str, int]):
        """Handle command client connection (optional)"""
        try:
            # Simple command interface for device management
            logger.info(f"Command client connected: {client_address}")
            
            # Send welcome message
            welcome = "InBody 370s Command Interface\r\n"
            client_socket.send(welcome.encode('utf-8'))
            
            # Handle commands (basic implementation)
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break
                
                command = data.decode('utf-8', errors='ignore').strip()
                response = self._process_command(command)
                client_socket.send(response.encode('utf-8'))
        
        except Exception as e:
            logger.error(f"Command client error: {e}")
        finally:
            client_socket.close()
            logger.debug(f"Command client {client_address} disconnected")
    
    def _process_hl7_message(self, message_data: bytes, client_address: Tuple[str, int]):
        """Process received HL7 message"""
        try:
            message_str = message_data.decode('utf-8', errors='ignore')
            logger.info(f"Processing HL7 message from {client_address} ({len(message_str)} chars)")
            
            # Parse HL7 message
            measurement = self.hl7_parser.parse_message(message_str)
            
            if measurement:
                logger.info(f"Parsed measurement for phone: {measurement.phone_number}")
                
                # Call registered callbacks
                for callback in self.message_callbacks:
                    try:
                        callback(measurement)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
                
                # Save to database if configured
                if self.database_manager:
                    self._save_measurement(measurement)
                
            else:
                logger.warning("Failed to parse HL7 message")
                
        except Exception as e:
            logger.error(f"Error processing HL7 message: {e}")
    
    def _process_command(self, command: str) -> str:
        """Process command interface commands"""
        command = command.upper().strip()
        
        if command == 'STATUS':
            return f"InBody 370s Handler Status: {'Running' if self.running else 'Stopped'}\r\n"
        elif command == 'VERSION':
            return "InBody 370s Handler v1.0\r\n"
        elif command == 'HELP':
            return "Available commands: STATUS, VERSION, HELP, QUIT\r\n"
        elif command == 'QUIT':
            return "Goodbye\r\n"
        else:
            return f"Unknown command: {command}\r\n"
    
    def _create_ack_message(self) -> str:
        """Create HL7 ACK response message"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        message_id = f"ACK{int(time.time())}"
        
        ack = (
            f"MSH|^~\\&|ACTIWELL|RASPBERRY_PI|INBODY370S|DEVICE|{timestamp}||ACK^R01^ACK|{message_id}|P|2.5\r"
            f"MSA|AA|{message_id}|Message accepted\r"
        )
        return ack + '\x1C\r'
    
    def _save_measurement(self, measurement: InBodyMeasurement):
        """Save measurement to database"""
        try:
            if self.database_manager:
                # Convert measurement to database format
                measurement_data = {
                    'device_id': measurement.device_id,
                    'extracted_phone_number': measurement.phone_number,
                    'patient_id': measurement.patient_id,
                    'measurement_timestamp': measurement.measurement_timestamp,
                    'weight_kg': measurement.weight_kg,
                    'height_cm': measurement.height_cm,
                    'bmi': measurement.bmi,
                    'body_fat_percent': measurement.body_fat_percent,
                    'skeletal_muscle_mass_kg': measurement.skeletal_muscle_mass_kg,
                    'visceral_fat_area_cm2': measurement.visceral_fat_area_cm2,
                    'basal_metabolic_rate_kcal': measurement.basal_metabolic_rate_kcal,
                    'raw_hl7_message': measurement.raw_hl7_message,
                    'hl7_message_type': measurement.hl7_message_type
                }
                
                # Save to database
                result = self.database_manager.save_inbody_measurement(measurement_data)
                if result:
                    logger.info(f"Measurement saved to database for {measurement.phone_number}")
                else:
                    logger.error("Failed to save measurement to database")
                    
        except Exception as e:
            logger.error(f"Database save error: {e}")
    
    def get_status(self) -> DeviceStatus:
        """Get device handler status"""
        return DeviceStatus(
            device_id="INBODY-370S-001",
            device_type="InBody-370s",
            status="online" if self.running else "offline",
            connection_type="ethernet_hl7",
            last_heartbeat=datetime.now() if self.running else None
        )