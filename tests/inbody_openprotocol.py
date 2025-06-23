#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
InBody 270 - Open Protocol Serial Reader for Raspberry Pi
=========================================================

Description:
- This script is designed to run on a Raspberry Pi.
- It connects to an InBody 270 body composition analyzer via a USB-to-Serial adapter.
- It listens for, receives, and parses measurement data sent from the InBody device
  when configured in "Serial Open Protocol (One Way)" mode.

Author: Professional IoT Engineer
Version: 1.2.0
"""

import serial
import serial.tools.list_ports
import time
import logging
import re
from typing import Dict, Optional

# Configure logging to monitor the script's activity
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("InBodyReader")

# Serial port configuration (must match the settings on the InBody device)
BAUDRATE = 9600
TIMEOUT = 0.5  # Serial port read timeout in seconds

def find_inbody_port() -> Optional[str]:
    """
    Automatically scans for and identifies the serial port connected to the InBody device.
    This method is more reliable than using glob.
    """
    logger.info("Scanning for available serial ports...")
    available_ports = serial.tools.list_ports.comports()
    
    if not available_ports:
        logger.warning("No serial ports found on this system.")
        return None

    logger.info("Found {} port(s): {}".format(len(available_ports), [p.device for p in available_ports]))

    for port in available_ports:
        # USB-to-Serial adapters often have 'USB' or 'ACM' in their description or name
        if "USB" in port.description or "USB" in port.name or "ACM" in port.name:
            logger.info("Checking port {}...".format(port.device))
            try:
                # Attempt to open and close the port to verify access permissions
                ser = serial.Serial(port.device, BAUDRATE, timeout=1)
                ser.close()
                logger.info("Successfully accessed port {}. Selecting this port.".format(port.device))
                return port.device
            except serial.SerialException as e:
                logger.warning("Could not open port {}. Error: {}".format(port.device, e))
                continue
    
    logger.error("Could not find a valid or accessible InBody serial port.")
    return None

def parse_inbody_data(raw_data: str) -> Dict[str, any]:
    """
    Parses the raw text data from the InBody device into a structured dictionary.
    Example: 'Weight: 75.2kg' -> {'Weight_kg': 75.2}
    """
    data = {}
    data['raw_data'] = raw_data
    
    # Regular expression to find "Key: Value" pairs and extract the number
    # e.g., "Key Name: 123.4 unit"
    pattern = re.compile(r'([a-zA-Z\s]+):\s*([\d\.]+)')

    lines = raw_data.strip().split('\n')
    for line in lines:
        match = pattern.search(line)
        if match:
            # "Body Fat" -> "Body_Fat" for a valid dictionary key
            key = match.group(1).strip().replace(' ', '_') 
            try:
                value = float(match.group(2).strip())
                # Append unit to the key for clarity
                if 'kg' in line.lower():
                    data['{}_kg'.format(key)] = value
                elif '%' in line:
                    data['{}_percent'.format(key)] = value
                else:
                    data[key] = value
            except ValueError:
                logger.warning("Could not convert '{}' to a number.".format(match.group(2)))

    # Handle the ID field separately as it's typically alphanumeric
    id_match = re.search(r'ID\s*:\s*([^\n\r]+)', raw_data)
    if id_match:
        data['ID'] = id_match.group(1).strip()
        
    return data

def listen_for_measurement(port: str):
    """
    Opens the serial port and listens for measurement data from the InBody device.
    This function will run indefinitely until the user presses Ctrl+C.
    """
    while True: # Main loop to auto-reconnect on error
        logger.info("Attempting to connect to InBody on port {} at {} baud...".format(port, BAUDRATE))
        try:
            with serial.Serial(port, BAUDRATE, timeout=TIMEOUT) as ser:
                logger.info("Connection successful! Waiting for measurement data...")
                print("\n>>> Please perform a measurement on the InBody device <<<\n")

                message_buffer = ""
                last_data_time = time.time()

                while True:
                    # Read any available data from the serial port
                    data = ser.read(ser.in_waiting or 1).decode('utf-8', errors='ignore')

                    if data:
                        if not message_buffer: # This is the start of a new data packet
                            logger.info("Signal detected! Receiving data...")
                        message_buffer += data
                        last_data_time = time.time()

                    # Check if the message is complete.
                    # Condition: data exists in the buffer AND no new data has been received for 1.0 second.
                    if message_buffer and (time.time() - last_data_time > 1.0):
                        logger.info("Full measurement packet received.")
                        
                        # Parse the received data
                        parsed_data = parse_inbody_data(message_buffer)
                        
                        print("\n" + "="*50)
                        logger.info("MEASUREMENT RESULT")
                        print("="*50)
                        
                        # Print the parsed results in a clean format
                        for key, value in parsed_data.items():
                            if key != 'raw_data':
                                print("{:<25}: {}".format(key.replace('_', ' ').title(), value))
                        
                        # Here you can add code to save the data to a file or database
                        # e.g., save_to_database(parsed_data)
                        
                        print("="*50 + "\n")
                        
                        # Reset the buffer to wait for the next measurement
                        message_buffer = ""
                        logger.info("System is ready for the next measurement.")
                        print("\n>>> Please perform a measurement on the InBody device <<<\n")

        except serial.SerialException as e:
            logger.error("Serial port error: {}".format(e))
            logger.info("Will attempt to reconnect in 10 seconds...")
            time.sleep(10)
        except KeyboardInterrupt:
            logger.info("Shutdown signal received (Ctrl+C). Exiting program.")
            break
        except Exception as e:
            logger.error("An unexpected error occurred: {}".format(e))
            logger.info("Restarting listener in 10 seconds...")
            time.sleep(10)

def main():
    """Main function to run the application."""
    # Step 1: Find the InBody's serial port
    inbody_port = find_inbody_port()

    if inbody_port:
        # Step 2: Start listening for data
        listen_for_measurement(inbody_port)
    else:
        logger.error("Cannot start listener because no InBody port was found.")
        logger.error("Please check the USB cable connection and serial port permissions.")

if __name__ == '__main__':
    main()