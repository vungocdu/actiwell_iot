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
Version: 1.2.1 (Syntax Corrected)
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

def find_inbody_port():
    logger.info("Scanning for available serial ports...")
    available_ports = serial.tools.list_ports.comports()
    
    if not available_ports:
        logger.warning("No serial ports found on this system.")
        return None

    logger.info("Found {} port(s): {}".format(len(available_ports), [p.device for p in available_ports]))

    for port in available_ports:
        if "USB" in port.description or "USB" in port.name or "ACM" in port.name:
            logger.info("Checking port {}...".format(port.device))
            try:
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
    data = {}
    data['raw_data'] = raw_data
    
    pattern = re.compile(r'([a-zA-Z\s]+):\s*([\d\.]+)')

    lines = raw_data.strip().split('\n')
    for line in lines:
        match = pattern.search(line)
        if match:
            key = match.group(1).strip().replace(' ', '_') 
            try:
                value = float(match.group(2).strip())
                if 'kg' in line.lower():
                    data['{}_kg'.format(key)] = value
                elif '%' in line:
                    data['{}_percent'.format(key)] = value
                else:
                    data[key] = value
            except ValueError:
                logger.warning("Could not convert '{}' to a number.".format(match.group(2)))

    id_match = re.search(r'ID\s*:\s*([^\n\r]+)', raw_data)
    if id_match:
        data['ID'] = id_match.group(1).strip()
        
    return data

def listen_for_measurement(port: str):
    while True:
        logger.info("Attempting to connect to InBody on port {} at {} baud...".format(port, BAUDRATE))
        try:
            with serial.Serial(port, BAUDRATE, timeout=TIMEOUT) as ser:
                logger.info("Connection successful! Waiting for measurement data...")
                print("\n>>> Please perform a measurement on the InBody device <<<\n")

                message_buffer = ""
                last_data_time = time.time()

                while True:
                    data = ser.read(ser.in_waiting or 1).decode('utf-8', errors='ignore')

                    if data:
                        if not message_buffer:
                            logger.info("Signal detected! Receiving data...")
                        message_buffer += data
                        last_data_time = time.time()

                    if message_buffer and (time.time() - last_data_time > 1.0):
                        logger.info("Full measurement packet received.")
                        
                        parsed_data = parse_inbody_data(message_buffer)
                        
                        print("\n" + "="*50)
                        logger.info("MEASUREMENT RESULT")
                        print("="*50)
                        
                        for key, value in parsed_data.items():
                            if key != 'raw_data':
                                print("{:<25}: {}".format(key.replace('_', ' ').title(), value))
                        
                        print("="*50 + "\n")
                        
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
    inbody_port = find_inbody_port()

    if inbody_port:
        listen_for_measurement(inbody_port)
    else:
        logger.error("Cannot start listener because no InBody port was found.")
        logger.error("Please check the USB cable connection and serial port permissions.")

if __name__ == '__main__':
    main()
