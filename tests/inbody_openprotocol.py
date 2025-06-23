#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
InBody 270 - Simulated Printer Listener on Raspberry Pi
=========================================================

Description:
- This script simulates a thermal printer connected to InBody 270.
- It listens for printed data via USB-to-Serial (text stream) and parses it.
- Suitable when InBody is configured to auto-print results after each measurement.

Author: Professional IoT Engineer
Version: 1.3.0 (Printer Emulation Mode)
"""

import serial
import serial.tools.list_ports
import time
import logging
import re

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Enable debug logging for full raw output
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("InBodyPrinterEmu")

BAUDRATE = 9600
TIMEOUT = 0.5


def find_inbody_port():
    logger.info("Scanning for available serial ports...")
    available_ports = serial.tools.list_ports.comports()

    if not available_ports:
        logger.warning("No serial ports found on this system.")
        return None

    logger.info("Found ports: {}".format([p.device for p in available_ports]))

    for port in available_ports:
        if "USB" in port.description or "USB" in port.name or "ACM" in port.name:
            logger.info("Trying port: {}".format(port.device))
            try:
                ser = serial.Serial(port.device, BAUDRATE, timeout=1)
                ser.close()
                logger.info("Successfully accessed port: {}".format(port.device))
                return port.device
            except serial.SerialException as e:
                logger.warning("Could not open port {}: {}".format(port.device, e))
                continue

    logger.error("No valid or accessible InBody port found.")
    return None


def parse_inbody_data(raw_data):
    # type: (str) -> dict
    data = {}
    data['raw_data'] = raw_data

    lines = raw_data.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Attempt to capture key: value pairs
        match = re.match(r'^([A-Za-z\s]+):\s*([\d\.]+)\s*(kg|cm|%|)$', line)
        if match:
            key = match.group(1).strip().replace(' ', '_')
            value = match.group(2).strip()
            unit = match.group(3).strip()

            try:
                num_value = float(value)
                if unit == 'kg':
                    data[key + '_kg'] = num_value
                elif unit == 'cm':
                    data[key + '_cm'] = num_value
                elif unit == '%':
                    data[key + '_percent'] = num_value
                else:
                    data[key] = num_value
            except Exception as e:
                logger.warning("Failed to parse value '{}': {}".format(value, e))

        # Special handling for ID line
        if line.startswith("ID"):
            id_match = re.match(r'ID\s*[:=]\s*(\S+)', line)
            if id_match:
                data['ID'] = id_match.group(1)

    return data


def listen_for_measurement(port):
    while True:
        logger.info("Opening serial port {} at {} baud...".format(port, BAUDRATE))
        try:
            with serial.Serial(port, BAUDRATE, timeout=TIMEOUT) as ser:
                logger.info("Connected. Waiting for print job from InBody...")
                print("\n>>> Please perform a measurement on the InBody device <<<\n")

                buffer = ""
                last_data_time = time.time()

                while True:
                    incoming = ser.read(ser.in_waiting or 1).decode('utf-8', errors='ignore')
                    if incoming:
                        logger.debug("Raw: {}".format(repr(incoming)))
                        buffer += incoming
                        last_data_time = time.time()

                    if buffer and (time.time() - last_data_time > 1.5):
                        logger.info("Complete data received from InBody printer stream.")

                        print("\n===== RAW PRINTER OUTPUT =====")
                        print(buffer.strip())
                        print("==============================\n")

                        parsed = parse_inbody_data(buffer)

                        print("===== PARSED MEASUREMENT =====")
                        for k, v in parsed.items():
                            if k != 'raw_data':
                                print("{:<25}: {}".format(k.replace('_', ' ').title(), v))
                        print("==============================\n")

                        buffer = ""
                        logger.info("Ready for next measurement.")
                        print("\n>>> Please perform a measurement on the InBody device <<<\n")

        except serial.SerialException as e:
            logger.error("Serial port error: {}".format(e))
            time.sleep(10)
        except KeyboardInterrupt:
            logger.info("Shutdown requested. Exiting.")
            break
        except Exception as e:
            logger.error("Unexpected error: {}".format(e))
            time.sleep(10)


def main():
    port = find_inbody_port()
    if port:
        listen_for_measurement(port)
    else:
        logger.error("Cannot listen for data. No InBody device detected.")


if __name__ == '__main__':
    main()
