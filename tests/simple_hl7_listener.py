#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
InBody 370s - Passive HL7 Listener and Parser
===============================================

Description:
- This script operates in a purely passive (one-way) listening mode.
- It waits indefinitely for an InBody device to connect and send HL7 data.
- It includes a dedicated HL7 parser to extract key measurement values.
- Ideal for production environments where the Pi acts as a data receiver.

Version: 3.0.0 (Passive Listener with Integrated Parser)
"""

import socket
import logging
import time
import re
from dataclasses import dataclass, field

# --- Configuration ---
PI_IP = '192.168.1.50'  # The IP of this Raspberry Pi
DATA_PORT_ON_PI = 2575 # The port this script will listen on

# HL7 Terminators
VT = b'\x0b'
FS = b'\x1c'

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("InBodyListener")


@dataclass
class InBodyMeasurement:
    """A structured dataclass to hold parsed InBody measurement data."""
    phone_number: str = "N/A"
    weight_kg: float = 0.0
    height_cm: float = 0.0
    bmi: float = 0.0
    percent_body_fat: float = 0.0
    raw_message: str = ""
    errors: list[str] = field(default_factory=list)


class HL7Parser:
    """A dedicated parser for InBody HL7 messages."""
    
    # Mapping of InBody's local codes to standard names
    # This might need adjustment based on your device's exact output.
    CODE_MAP = {
        'WT': 'weight_kg',
        'HT': 'height_cm',
        'BMI': 'bmi',
        'PBF': 'percent_body_fat', # Percent Body Fat
        'FAT': 'percent_body_fat'  # Some devices use FAT for PBF
    }

    def parse(self, raw_hl7_bytes: bytes) -> InBodyMeasurement:
        """Parses a raw HL7 byte string into an InBodyMeasurement object."""
        measurement = InBodyMeasurement()
        
        try:
            # Decode the message, handling control characters
            message_str = raw_hl7_bytes.decode('utf-8', 'ignore')
            measurement.raw_message = message_str
            
            # HL7 segments are separated by a carriage return ('\r')
            segments = message_str.strip().replace(chr(0x0b), '').replace(chr(0x1c), '').split('\r')
            
            for segment in segments:
                segment = segment.strip()
                if not segment:
                    continue
                
                fields = segment.split('|')
                segment_type = fields[0]

                if segment_type == 'PID' and len(fields) > 3:
                    self._parse_pid_segment(fields, measurement)
                elif segment_type == 'OBX' and len(fields) > 5:
                    self._parse_obx_segment(fields, measurement)

        except Exception as e:
            error_msg = f"Critical parsing error: {e}"
            logger.error(error_msg)
            measurement.errors.append(error_msg)

        return measurement

    def _parse_pid_segment(self, fields: list, measurement: InBodyMeasurement):
        """Parses the Patient Identification (PID) segment."""
        try:
            # PID|1||123456789^^^...
            patient_id_field = fields[3]
            # Extract the ID part before any '^' characters
            phone_number = patient_id_field.split('^')[0]
            if phone_number:
                measurement.phone_number = phone_number
        except IndexError:
            measurement.errors.append("Could not parse phone number from PID segment.")

    def _parse_obx_segment(self, fields: list, measurement: InBodyMeasurement):
        """Parses an Observation/Result (OBX) segment for a specific value."""
        try:
            # OBX|1|NM|WT^Weight^LOCAL|...|68.5|kg|...
            observation_code = fields[3].split('^')[0]
            value_str = fields[5]
            
            if observation_code in self.CODE_MAP:
                attribute_name = self.CODE_MAP[observation_code]
                try:
                    value = float(value_str)
                    setattr(measurement, attribute_name, value)
                except (ValueError, TypeError):
                    measurement.errors.append(f"Could not convert value '{value_str}' for code '{observation_code}' to float.")
        except IndexError:
            measurement.errors.append("Could not parse key values from OBX segment.")


class InBodyPassiveListener:
    """A robust, passive listener for InBody devices."""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.parser = HL7Parser()
        self.server_socket = None

    def start(self):
        """Starts the server and enters the main listening loop."""
        logger.info(f"Initializing passive listener on {self.host}:{self.port}")
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
        except socket.error as e:
            logger.error(f"FATAL: Could not bind to port {self.port}. Error: {e}")
            logger.error("Is another application using this port? Or is the IP address correct?")
            return

        self.run_forever()

    def run_forever(self):
        """The main loop that waits for and handles connections."""
        while True:
            try:
                print("\n" + "="*60)
                logger.info("SERVER IS READY. Waiting for a measurement from the InBody device...")
                print("[ACTION] Please perform a measurement now.")
                print("="*60)

                # Wait indefinitely for a connection
                client_socket, addr = self.server_socket.accept()
                logger.info(f"Connection accepted from {addr}")

                with client_socket:
                    # Receive data from the connection
                    raw_data = self._receive_all_data(client_socket)
                    if raw_data:
                        logger.info(f"Received {len(raw_data)} bytes of data. Processing...")
                        # Parse the data using the dedicated parser
                        measurement_result = self.parser.parse(raw_data)
                        self.display_results(measurement_result)
                    else:
                        logger.warning("Connection closed without any data being sent.")
                
            except KeyboardInterrupt:
                logger.info("Shutdown signal received. Exiting.")
                break
            except Exception as e:
                logger.error(f"An unexpected error occurred in the main loop: {e}")
                logger.info("Restarting listener cycle in 10 seconds...")
                time.sleep(10)
        
        self.server_socket.close()
        logger.info("Server shut down.")

    def _receive_all_data(self, sock: socket.socket) -> bytes:
        """Receives all data from a socket until the HL7 end block is found or timeout."""
        sock.settimeout(30.0) # Set a 30-second timeout for the entire reception
        buffer = bytearray()
        try:
            while True:
                chunk = sock.recv(1024)
                if not chunk:
                    # Connection closed by the other side
                    break
                buffer.extend(chunk)
                # Check for the end of the message
                if FS in buffer:
                    break
        except socket.timeout:
            logger.warning("Socket timed out while receiving data.")
        
        return bytes(buffer)

    @staticmethod
    def display_results(measurement: InBodyMeasurement):
        """Prints the parsed measurement results in a structured format."""
        print("\n" + "*"*25 + " PARSED MEASUREMENT " + "*"*25)
        print(f"{'Phone Number':<20}: {measurement.phone_number}")
        print(f"{'Weight (kg)':<20}: {measurement.weight_kg}")
        print(f"{'Height (cm)':<20}: {measurement.height_cm}")
        print(f"{'BMI':<20}: {measurement.bmi}")
        print(f"{'Body Fat (%)':<20}: {measurement.percent_body_fat}")
        
        if measurement.errors:
            print("-" * 64)
            logger.warning("Parsing finished with errors:")
            for error in measurement.errors:
                print(f"  - {error}")
                
        print("*"*64 + "\n")


if __name__ == "__main__":
    listener = InBodyPassiveListener(host=PI_IP, port=DATA_PORT_ON_PI)
    listener.start()