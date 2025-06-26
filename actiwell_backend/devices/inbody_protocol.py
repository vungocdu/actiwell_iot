#!/usr/bin/env python3
"""
InBody Protocol Implementation
Handles HL7 communication for InBody 270/370s devices
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

from .base_protocol import DeviceProtocol, DeviceState, MeasurementStatus, MeasurementData, DeviceCapabilities

logger = logging.getLogger(__name__)

@dataclass
class InBodyCapabilities(DeviceCapabilities):
    """InBody 270/370s specific capabilities"""
    model: str = "InBody-270"
    manufacturer: str = "InBody Co., Ltd."
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
    metabolic_age: bool = False  # Not all InBody models
    body_water: bool = True
    muscle_mass: bool = True
    bone_mass: bool = False  # InBody focuses on lean mass
    
    def __post_init__(self):
        if self.connectivity is None:
            self.connectivity = ['RS-232C', 'USB', 'LAN', 'Bluetooth', 'Wi-Fi']

class HL7MessageParser:
    """HL7 v2.5 message parser for InBody devices"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.segment_separator = self.config.get('segment_separator', '\r')
        self.field_separator = self.config.get('field_separator', '|')
        
    def parse_message(self, raw_message: str) -> Optional[MeasurementData]:
        """Parse HL7 message into standardized MeasurementData object"""
        try:
            logger.debug(f"Parsing HL7 message: {len(raw_message)} characters")
            
            # Split into segments
            segments = raw_message.split(self.segment_separator)
            segments = [seg.strip() for seg in segments if seg.strip()]
            
            if not segments:
                logger.warning("Empty HL7 message received")
                return None
            
            # Initialize measurement object
            measurement = MeasurementData()
            measurement.device_type = "inbody_270"
            measurement.device_id = "inbody_001"
            measurement.raw_data = raw_message
            measurement.measurement_timestamp = datetime.now()
            
            # Parse each segment
            for segment in segments:
                self._parse_segment(segment, measurement)
            
            # Validate parsed data
            if self._validate_measurement(measurement):
                logger.info(f"Successfully parsed HL7 measurement for: {measurement.customer_phone}")
                measurement.status = MeasurementStatus.COMPLETE
                return measurement
            else:
                logger.warning("HL7 measurement validation failed")
                measurement.status = MeasurementStatus.ERROR
                return measurement
                
        except Exception as e:
            logger.error(f"Error parsing HL7 message: {e}")
            return None
    
    def _parse_segment(self, segment: str, measurement: MeasurementData):
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
    
    def _parse_msh_segment(self, fields: List[str], measurement: MeasurementData):
        """Parse MSH (Message Header) segment"""
        if len(fields) >= 9:
            # Parse timestamp if available
            if len(fields) > 6 and fields[6]:
                timestamp_str = fields[6]
                if len(timestamp_str) >= 14:
                    measurement.measurement_timestamp = datetime.strptime(
                        timestamp_str[:14], '%Y%m%d%H%M%S'
                    )
            
            # Message ID
            if len(fields) > 9:
                measurement.measurement_uuid = fields[9]
    
    def _parse_pid_segment(self, fields: List[str], measurement: MeasurementData):
        """Parse PID (Patient Identification) segment"""
        # Patient ID (field 3) - extract phone number
        if len(fields) > 2 and fields[2]:
            patient_id = fields[2].strip('"')
            phone = self._extract_phone_number(patient_id)
            if phone:
                measurement.customer_phone = phone
                measurement.customer_id = phone
        
        # Date of birth (field 7) - calculate age
        if len(fields) > 7 and fields[7]:
            try:
                birth_date = datetime.strptime(fields[7], '%Y%m%d')
                measurement.age = (datetime.now() - birth_date).days // 365
            except ValueError:
                pass
        
        # Gender (field 8)
        if len(fields) > 8 and fields[8]:
            measurement.gender = fields[8].upper()
    
    def _parse_obr_segment(self, fields: List[str], measurement: MeasurementData):
        """Parse OBR (Observation Request) segment"""
        pass  # Additional metadata if needed
    
    def _parse_obx_segment(self, fields: List[str], measurement: MeasurementData):
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
        
        # InBody measurement mapping (standardized codes)
        measurement_map = {
            # Basic measurements
            'WT': lambda m, v: setattr(m, 'weight_kg', v),
            'HT': lambda m, v: setattr(m, 'height_cm', v),
            'BMI': lambda m, v: setattr(m, 'bmi', v),
            
            # Body composition
            'PBF': lambda m, v: setattr(m, 'body_fat_percent', v),
            'SMM': lambda m, v: setattr(m, 'muscle_mass_kg', v),
            'TBW': lambda m, v: setattr(m, 'total_body_water_kg', v),
            'TBWP': lambda m, v: setattr(m, 'total_body_water_percent', v),
            'BMR': lambda m, v: setattr(m, 'bmr_kcal', int(v)),
            'VFA': lambda m, v: setattr(m, 'visceral_fat_rating', int(v)),
            
            # Segmental analysis (InBody specialty)
            'RLA': lambda m, v: setattr(m, 'right_leg_muscle_kg', v),
            'LLA': lambda m, v: setattr(m, 'left_leg_muscle_kg', v),
            'RAA': lambda m, v: setattr(m, 'right_arm_muscle_kg', v),
            'LAA': lambda m, v: setattr(m, 'left_arm_muscle_kg', v),
            'TR': lambda m, v: setattr(m, 'trunk_muscle_kg', v),
            
            # Bioelectrical impedance
            'IMP50': lambda m, v: setattr(m, 'impedance_50khz', v),
            'IMP250': lambda m, v: setattr(m, 'impedance_250khz', v),
            
            # Phase angle
            'PA50': lambda m, v: setattr(m, 'phase_angle', v),
        }
        
        # Find matching measurement
        for code, setter in measurement_map.items():
            if code in observation_id.upper():
                setter(measurement, numeric_value)
                logger.debug(f"Mapped {observation_id} = {numeric_value} {units}")
                break
    
    def _parse_nte_segment(self, fields: List[str], measurement: MeasurementData):
        """Parse NTE (Notes) segment"""
        if len(fields) > 3:
            note = fields[3].strip()
            if measurement.processing_notes:
                measurement.processing_notes += f"; {note}"
            else:
                measurement.processing_notes = note
    
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
    
    def _validate_measurement(self, measurement: MeasurementData) -> bool:
        """Validate parsed measurement data"""
        # Check required fields
        if not measurement.customer_phone:
            logger.warning("Missing phone number in HL7 measurement")
            return False
        
        if not measurement.weight_kg or measurement.weight_kg <= 0:
            logger.warning("Missing or invalid weight in HL7 measurement")
            return False
        
        # Phone number format validation
        phone_pattern = r'^0[2-9][0-9]{8}$'
        if not re.match(phone_pattern, measurement.customer_phone):
            logger.warning(f"Invalid phone number format: {measurement.customer_phone}")
            return False
        
        return True

class InBodyProtocol(DeviceProtocol):
    """
    InBody 270/370s Protocol Handler
    Supports HL7 communication over TCP/IP for professional InBody devices
    """
    
    def __init__(self, ip_address: str = "192.168.1.100", data_port: int = 2575, listening_port: int = 2580):
        """
        Initialize InBody protocol handler
        
        Args:
            ip_address: IP address of InBody device
            data_port: Port for receiving measurement data (default: 2575)
            listening_port: Port for command interface (default: 2580)
        """
        super().__init__(f"tcp://{ip_address}:{data_port}")
        self.device_type = "inbody_270"
        self.device_id = f"inbody_{ip_address.replace('.', '_')}"
        self.capabilities = InBodyCapabilities()
        
        # Network configuration
        self.ip_address = ip_address
        self.data_port = data_port
        self.listening_port = listening_port
        
        # HL7 parser
        self.hl7_parser = HL7MessageParser()
        
        # Server sockets
        self.data_server = None
        self.command_server = None
        self.server_running = False
        
        # Client connections
        self.active_connections = []
        
        logger.info(f"InBody protocol initialized: {ip_address}:{data_port}")
    
    def connect(self) -> bool:
        """Start HL7 TCP server for InBody device connections"""
        try:
            logger.info(f"Starting InBody HL7 server on {self.ip_address}:{self.data_port}")
            self.state = DeviceState.CONNECTING
            self.stats['connection_attempts'] += 1
            
            # Start data reception server
            self.data_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.data_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.data_server.bind(('0.0.0.0', self.data_port))
            self.data_server.listen(10)
            
            # Start command interface server (optional)
            try:
                self.command_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.command_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.command_server.bind(('0.0.0.0', self.listening_port))
                self.command_server.listen(5)
                logger.info(f"Command interface started on port {self.listening_port}")
            except Exception as e:
                logger.warning(f"Command interface failed to start: {e}")
                self.command_server = None
            
            self.server_running = True
            
            # Start server threads
            data_thread = threading.Thread(target=self._data_server_loop, daemon=True)
            data_thread.start()
            
            if self.command_server:
                command_thread = threading.Thread(target=self._command_server_loop, daemon=True)
                command_thread.start()
            
            self.state = DeviceState.CONNECTED
            self.is_connected = True
            self.connection_time = datetime.now()
            self.error_count = 0
            
            logger.info(f"InBody HL7 server started successfully")
            self._trigger_status_callback("HL7 server started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start InBody HL7 server: {e}")
            self.state = DeviceState.ERROR
            self._trigger_error_callback(f"Server start error: {e}")
            return False
    
    def disconnect(self):
        """Stop InBody HL7 server"""
        try:
            logger.info("Stopping InBody HL7 server")
            
            self.server_running = False
            
            # Close active connections
            for conn in self.active_connections:
                try:
                    conn.close()
                except:
                    pass
            self.active_connections.clear()
            
            # Close server sockets
            if self.data_server:
                self.data_server.close()
            if self.command_server:
                self.command_server.close()
            
            self.state = DeviceState.DISCONNECTED
            self.is_connected = False
            logger.info("InBody HL7 server stopped")
            
        except Exception as e:
            logger.error(f"InBody disconnection error: {e}")
    
    def read_measurement(self, timeout: float = 30.0) -> Optional[MeasurementData]:
        """
        Note: InBody measurements come through HL7 TCP connections
        This method is for compatibility but actual measurements are processed in callbacks
        """
        logger.debug("InBody measurements are processed via HL7 TCP callbacks")
        return None
    
    def _data_server_loop(self):
        """Main loop for HL7 data reception server"""
        logger.info(f"HL7 data server listening on port {self.data_port}")
        
        while self.server_running:
            try:
                client_socket, client_address = self.data_server.accept()
                logger.info(f"HL7 connection from {client_address}")
                
                self.active_connections.append(client_socket)
                
                # Handle client in separate thread
                client_thread = threading.Thread(
                    target=self._handle_hl7_client,
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()
                
            except socket.error as e:
                if self.server_running:
                    logger.error(f"HL7 server error: {e}")
                break
    
    def _command_server_loop(self):
        """Main loop for command interface server"""
        logger.info(f"Command server listening on port {self.listening_port}")
        
        while self.server_running:
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
                if self.server_running:
                    logger.error(f"Command server error: {e}")
                break
    
    def _handle_hl7_client(self, client_socket: socket.socket, client_address: Tuple[str, int]):
        """Handle HL7 data client connection"""
        try:
            buffer = b''
            
            while self.server_running:
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
            logger.error(f"HL7 client error: {e}")
        finally:
            if client_socket in self.active_connections:
                self.active_connections.remove(client_socket)
            client_socket.close()
            logger.debug(f"HL7 client {client_address} disconnected")
    
    def _handle_command_client(self, client_socket: socket.socket, client_address: Tuple[str, int]):
        """Handle command client connection"""
        try:
            logger.info(f"Command client connected: {client_address}")
            
            # Send welcome message
            welcome = "InBody Command Interface\r\n"
            client_socket.send(welcome.encode('utf-8'))
            
            # Handle commands
            while self.server_running:
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
                logger.info(f"Parsed HL7 measurement for phone: {measurement.customer_phone}")
                
                # Update statistics
                self.stats['measurements_received'] += 1
                self.last_activity = datetime.now()
                
                # Validate measurement
                errors = measurement.validate()
                if not errors:
                    self.stats['successful_measurements'] += 1
                    measurement.status = MeasurementStatus.COMPLETE
                else:
                    self.stats['failed_measurements'] += 1
                    measurement.status = MeasurementStatus.ERROR
                    logger.warning(f"HL7 measurement validation errors: {errors}")
                
                # Trigger callback
                if self.measurement_callback:
                    self.measurement_callback(measurement)
                
            else:
                logger.warning("Failed to parse HL7 message")
                self.stats['failed_measurements'] += 1
                
        except Exception as e:
            logger.error(f"Error processing HL7 message: {e}")
            self._trigger_error_callback(f"HL7 processing error: {e}")
    
    def _process_command(self, command: str) -> str:
        """Process command interface commands"""
        command = command.upper().strip()
        
        if command == 'STATUS':
            return f"InBody HL7 Handler Status: {'Running' if self.server_running else 'Stopped'}\r\n"
        elif command == 'VERSION':
            return "InBody HL7 Handler v2.0\r\n"
        elif command == 'STATS':
            return f"Measurements: {self.stats['measurements_received']}, Errors: {self.stats['errors']}\r\n"
        elif command == 'HELP':
            return "Available commands: STATUS, VERSION, STATS, HELP, QUIT\r\n"
        elif command == 'QUIT':
            return "Goodbye\r\n"
        else:
            return f"Unknown command: {command}\r\n"
    
    def _create_ack_message(self) -> str:
        """Create HL7 ACK response message"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        message_id = f"ACK{int(time.time())}"
        
        ack = (
            f"MSH|^~\\&|ACTIWELL|RASPBERRY_PI|INBODY|DEVICE|{timestamp}||ACK^R01^ACK|{message_id}|P|2.5\r"
            f"MSA|AA|{message_id}|Message accepted\r"
        )
        return ack + '\x1C\r'
    
    def start_measurement(self, customer_id: str = "") -> bool:
        """
        Note: InBody devices don't support remote measurement start
        Measurements are initiated on the device itself
        """
        logger.info("InBody measurement ready - start measurement on device")
        if customer_id:
            logger.info(f"Customer ID for measurement: {customer_id}")
        
        self.state = DeviceState.READY
        return True
    
    def get_device_info(self) -> Dict[str, any]:
        """Get comprehensive InBody device information"""
        base_info = super().get_device_info()
        
        # Add InBody-specific information
        base_info.update({
            'model': 'InBody-270/370s',
            'manufacturer': 'InBody Co., Ltd.',
            'protocol': 'HL7 v2.5',
            'data_port': self.data_port,
            'listening_port': self.listening_port,
            'ip_address': self.ip_address,
            'active_connections': len(self.active_connections),
            'server_running': self.server_running,
            'supported_features': [
                'Segmental lean analysis',
                'Bioelectrical impedance',
                'Phase angle',
                'Body composition history',
                'HL7 integration'
            ]
        })
        
        return base_info
    
    def __str__(self):
        return f"InBody HL7 on {self.ip_address}:{self.data_port} (connections: {len(self.active_connections)})"