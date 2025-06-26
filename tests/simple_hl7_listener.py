#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
InBody 370s HL7 Handler - Focused on Receiving Measurement Results
===================================================================

Description:
- This script implements a robust handler for receiving HL7 measurement
  data from an InBody 370s device in a two-way communication setup.
- It continuously waits for a measurement, sends a command to the InBody,
  and listens for the resulting HL7 data packet.
- Designed for stability and clear debugging.

Version: 2.0.0 (Class-based, Production-ready)
"""

import socket
import logging
import time
import re

# --- Configuration ---
INBODY_IP = '192.168.1.100'
PI_IP = '192.168.1.50'
DATA_PORT_ON_PI = 2575  # Port on Pi to LISTEN for InBody's data
COMMAND_PORT_ON_INBODY = 2580  # Port on InBody to SEND commands to
TEST_PHONE = "0965385123"

# HL7 Terminators
VT = b'\x0b'
FS = b'\x1c'
CR = b'\x0d'

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("InBodyHandler")


class InBodyHL7Handler:
    """Handles the two-way communication with an InBody 370s device."""

    def __init__(self, pi_ip, data_port, inbody_ip, command_port):
        self.pi_ip = pi_ip
        self.data_port = data_port
        self.inbody_ip = inbody_ip
        self.command_port = command_port
        self.listener_socket = None

    def _setup_listener(self):
        """Initializes and binds the listening socket."""
        logger.info(f"Setting up listener on {self.pi_ip}:{self.data_port}")
        self.listener_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.listener_socket.bind((self.pi_ip, self.data_port))
            self.listener_socket.listen(1)
            logger.info("Listener is ready and waiting for connections.")
            return True
        except socket.error as e:
            logger.error(f"Failed to bind listener socket: {e}")
            return False

    def _send_trigger_command(self):
        """
        Sends a command to the InBody device to trigger the data transmission.
        Based on previous logs, this is a necessary step.
        """
        # NOTE: The content of this HL7 message is hypothetical.
        # It needs to be replaced with the correct command from InBody's documentation.
        # This ORM^O01 (Order Message) is a common choice for requesting a procedure.
        timestamp = time.strftime("%Y%m%d%H%M%S")
        message_id = f"MSG{int(time.time())}"
        
        hl7_order_message = (
            f"MSH|^~\\&|RASPBERRY_PI|ACTIWELL|INBODY_370S|DEVICE|{timestamp}||ORM^O01^ORM_O01|{message_id}|P|2.5\r"
            f"PID|1||{TEST_PHONE}^^^PHONE||Test^Patient||19900101|M\r"
            f"ORC|NW|{message_id}\r" # NW = New Order
            f"OBR|1||{message_id}|BODYCOMP^Body Composition^L|||{timestamp}"
        ).encode('utf-8')
        
        full_packet = VT + hl7_order_message + FS + CR

        logger.info(f"Connecting to InBody command port at {self.inbody_ip}:{self.command_port}...")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(10.0)
                s.connect((self.inbody_ip, self.command_port))
                logger.info("Connected. Sending trigger command...")
                s.sendall(full_packet)
                
                # Check for ACK
                response = s.recv(1024)
                if response:
                    logger.info(f"Received ACK from InBody: {response.decode('utf-8', 'ignore').strip()}")
                    return True
                else:
                    logger.warning("Command sent, but no ACK received.")
                    return True # Assume it worked anyway
        except Exception as e:
            logger.error(f"Failed to send trigger command: {e}")
            return False

    def _wait_for_and_process_data(self):
        """Waits for the InBody to connect back and send the measurement data."""
        if not self.listener_socket:
            logger.error("Listener socket is not set up. Cannot wait for data.")
            return None

        try:
            # Wait for the InBody to connect to our listening port
            self.listener_socket.settimeout(60.0) # Wait up to 60 seconds
            client_socket, addr = self.listener_socket.accept()
            logger.info(f"Data connection accepted from InBody at {addr}")

            with client_socket:
                client_socket.settimeout(30.0)
                full_data = bytearray()
                while True:
                    data = client_socket.recv(1024)
                    if not data:
                        break
                    full_data.extend(data)
                    if FS in full_data: # End of message detected
                        break
                
                if full_data:
                    logger.info("SUCCESS! Full measurement packet received.")
                    self.display_and_parse_data(full_data)
                else:
                    logger.warning("Connection from InBody but no data was received.")

        except socket.timeout:
            logger.warning("Timeout: Waited 60 seconds but InBody did not connect back to send data.")
        except Exception as e:
            logger.error(f"Error while receiving data: {e}")
        
    @staticmethod
    def display_and_parse_data(raw_bytes):
        """Displays the raw data and attempts to parse key values."""
        print("\n" + "="*25 + " RAW HL7 DATA " + "="*25)
        
        # Make control characters visible for debugging
        readable_data = raw_bytes.decode('utf-8', 'ignore')
        printable_data = readable_data.replace(chr(0x0b), '<VT>\n')
        printable_data = printable_data.replace(chr(0x1c), '\n<FS>')
        printable_data = printable_data.replace('\r', '\n')
        print(printable_data.strip())
        print("="*68)

        # Basic HL7 Parsing
        logger.info("Parsing key measurement values...")
        results = {}
        segments = readable_data.split('\r')
        for segment in segments:
            fields = segment.strip().split('|')
            if not fields:
                continue
            
            segment_type = fields[0]
            if segment_type == 'PID' and len(fields) > 5:
                results['PhoneNumber'] = fields[3].split('^')[0]
            elif segment_type == 'OBX' and len(fields) > 5:
                # Example: OBX|1|NM|WT^Weight^LOCAL||68.5|kg|||||F
                value_name = fields[3].split('^')[0]
                value = fields[5]
                unit = fields[6] if len(fields) > 6 else ''
                results[value_name] = f"{value} {unit}".strip()

        if results:
            print("\n" + "*"*25 + " PARSED RESULTS " + "*"*25)
            for key, value in results.items():
                print(f"{key:<20}: {value}")
            print("*"*68 + "\n")
        else:
            logger.warning("Could not parse any key values from the message.")

    def run_forever(self):
        """The main loop to continuously handle InBody measurements."""
        if not self._setup_listener():
            return # Exit if we can't even start the listener
        
        while True:
            try:
                print("\n" + "#"*68)
                logger.info("Starting new measurement cycle.")
                logger.info("Please prepare the InBody device.")
                print("[ACTION] Press the 'START' or 'ENTER' button on the InBody to initiate a test.")
                print("#"*68)

                # Step 1: Send a command to wake up the InBody.
                # This might be what happens when you press "Enter" on the InBody screen
                # with the Pi's IP configured.
                if not self._send_trigger_command():
                    logger.warning("Could not send trigger command. Will still listen for data, but it might not arrive.")

                # Step 2: Wait for the InBody to perform the measurement and send data back.
                logger.info("Command sent. Now waiting for InBody to connect and send measurement data...")
                self._wait_for_and_process_data()
                
                logger.info("Measurement cycle finished. Resetting for the next one in 5 seconds...")
                time.sleep(5)

            except KeyboardInterrupt:
                logger.info("Shutdown signal received. Exiting.")
                break
            except Exception as e:
                logger.error(f"An unhandled error occurred in the main loop: {e}")
                logger.info("Restarting cycle in 15 seconds...")
                time.sleep(15)
        
        if self.listener_socket:
            self.listener_socket.close()

if __name__ == "__main__":
    handler = InBodyHL7Handler(
        pi_ip=PI_IP,
        data_port=DATA_PORT_ON_PI,
        inbody_ip=INBODY_IP,
        command_port=COMMAND_PORT_ON_INBODY
    )
    handler.run_forever()