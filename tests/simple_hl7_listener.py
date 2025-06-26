#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
InBody 370s Interactive HL7 Debugger
=====================================

Description:
- Simulates a two-way HL7 communication flow with an InBody 370s.
- Thread 1: Listens for incoming measurement data on the DATA_PORT.
- Thread 2: Sends a simple command to the InBody's LISTENING_PORT.
- Designed to debug scenarios where a command is required before data is sent.
- Version 1.1: Fixed NameError for 'logger' within threads.
"""

import socket
import logging
import threading
import time

# --- Configuration ---
INBODY_IP = '192.168.1.100'
PI_IP = '192.168.1.50'

# Port on the Pi that will LISTEN for InBody's data
DATA_PORT_ON_PI = 2575

# Port on the InBody that LISTENS for our commands
COMMAND_PORT_ON_INBODY = 2580

# A test phone number to include in the command
TEST_PHONE = "0965385123"

# HL7 Terminators
VT = b'\x0b'
FS = b'\x1c'
CR = b'\x0d'

# --- Global Logging Setup ---
# This configures the root logger.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'
)

# --- Thread 1: The Data Listener ---
def data_listener():
    """Listens on DATA_PORT_ON_PI for HL7 messages from the InBody."""
    # --- FIX: Get logger instance for this thread ---
    logger = logging.getLogger(__name__)
    
    thread_name = threading.current_thread().name
    logger.info("Starting... Will listen on {}:{}".format(PI_IP, DATA_PORT_ON_PI))
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((PI_IP, DATA_PORT_ON_PI))
        server_socket.listen(1)
        logger.info("Socket bound. Waiting for InBody to send data...")

        # Wait for a connection from InBody with a timeout
        server_socket.settimeout(60.0) # Wait for 60 seconds
        client_socket, addr = server_socket.accept()
        logger.info("Accepted connection from InBody at {}".format(addr))

        with client_socket:
            full_data = client_socket.recv(4096) # Read a large chunk of data
            if full_data:
                logger.info("SUCCESS! Received {} bytes of data.".format(len(full_data)))
                print("\n" + "="*20 + " RAW HL7 DATA RECEIVED " + "="*20)
                # Print readable data by replacing control characters
                readable_data = full_data.decode('utf-8', 'ignore').replace(chr(0x0d), '\n')
                readable_data = readable_data.replace(chr(0x0b), '<VT>\n')
                readable_data = readable_data.replace(chr(0x1c), '\n<FS>')
                print(readable_data.strip())
                print("="*60 + "\n")
            else:
                logger.warning("Connection from InBody, but no data received.")

    except socket.timeout:
        logger.warning("Listener timed out. No data received from InBody in 60 seconds.")
    except Exception as e:
        logger.error("An error occurred: {}".format(e))
    finally:
        server_socket.close()
        logger.info("Listener thread finished.")

# --- Thread 2: The Command Sender ---
def send_command():
    """Connects to COMMAND_PORT_ON_INBODY and sends a simple request."""
    # --- FIX: Get logger instance for this thread ---
    logger = logging.getLogger(__name__)
    
    thread_name = threading.current_thread().name
    logger.info("Starting... Will send a command to {}:{}".format(INBODY_IP, COMMAND_PORT_ON_INBODY))
    
    # Wait a moment for the listener to be ready
    time.sleep(2) 

    # This is a hypothetical HL7 "Query" or "Request" message.
    # The exact format might be different and needs to be checked in InBody's documentation.
    timestamp = time.strftime("%Y%m%d%H%M%S")
    message_id = "MSG" + str(int(time.time()))
    
    # MLLP Framing: <VT>HL7_MESSAGE<FS><CR>
    hl7_query_message = (
        f"MSH|^~\\&|RASPBERRY_PI|ACTIWELL|INBODY_370S|DEVICE|{timestamp}||QBP^Q22^QBP_Q21|{message_id}|P|2.5{chr(0x0d)}"
        f"QPD|IHE_PCD_Q22^Query for Previous Patient Data^IHE_PCD|{message_id}|{TEST_PHONE}^^^PHONE{chr(0x0d)}"
        f"RCP|I"
    ).encode('utf-8')
    
    full_packet = VT + hl7_query_message + FS + CR

    try:
        logger.info("Connecting to InBody's command port...")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10.0)
            s.connect((INBODY_IP, COMMAND_PORT_ON_INBODY))
            logger.info("Connected! Sending command packet ({} bytes)...".format(len(full_packet)))
            
            s.sendall(full_packet)
            logger.info("Command sent successfully.")
            
            # Wait for a potential ACK (Acknowledgement)
            logger.info("Waiting for ACK from InBody...")
            response = s.recv(1024)
            if response:
                logger.info("Received response/ACK from InBody: {}".format(response.decode('utf-8', 'ignore').replace('\r', '\n')))
            else:
                logger.warning("No ACK received, but command was sent.")

    except socket.timeout:
        logger.error("Connection to command port timed out. Is InBody listening on port {}?".format(COMMAND_PORT_ON_INBODY))
    except Exception as e:
        logger.error("Failed to send command: {}".format(e))
    finally:
        logger.info("Command sender thread finished.")

# --- Main Execution ---
if __name__ == "__main__":
    main_logger = logging.getLogger(__name__)
    main_logger.info("="*60)
    main_logger.info("      InBody 370s Interactive HL7 Debugger      ")
    main_logger.info("="*60)
    
    # Create the listener thread
    listener_thread = threading.Thread(target=data_listener, name="HL7-Listener")
    
    # Create the command sender thread
    command_thread = threading.Thread(target=send_command, name="HL7-CommandSender")
    
    # Start the threads
    listener_thread.start()
    command_thread.start()
    
    main_logger.info("Both threads have been started.")
    print("\n[ACTION] Please perform a measurement on the InBody device now.")
    main_logger.info("The script will wait for results for up to 60 seconds.\n")
    
    # Wait for both threads to complete
    listener_thread.join()
    command_thread.join()
    
    main_logger.info("Debugging session finished.")