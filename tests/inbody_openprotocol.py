#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
InBody 270 - Simulated Printer Listener on Raspberry Pi (PCL Mode)
====================================================================

Description:
- This script simulates a printer connected to InBody 270.
- It listens for PCL-formatted print data sent via USB-to-Serial.
- It saves raw PCL files and optionally decodes them to readable formats.

Author: Professional IoT Engineer
Version: 1.4.0 (PCL Capture Mode)
"""

import serial
import serial.tools.list_ports
import time
import logging
import os

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("InBodyPCLPrinter")

BAUDRATE = 9600
TIMEOUT = 0.5
PCL_OUTPUT_DIR = "/tmp/inbody_pcl"
os.makedirs(PCL_OUTPUT_DIR, exist_ok=True)

def find_inbody_port():
    logger.info("Scanning for available serial ports...")
    available_ports = serial.tools.list_ports.comports()
    if not available_ports:
        logger.warning("No serial ports found.")
        return None
    for port in available_ports:
        if "USB" in port.description or "ACM" in port.name or "ttyUSB" in port.device:
            try:
                ser = serial.Serial(port.device, BAUDRATE, timeout=1)
                ser.close()
                logger.info("Selected port: {}".format(port.device))
                return port.device
            except Exception as e:
                logger.warning("Failed to access port {}: {}".format(port.device, e))
    return None

def save_pcl_data(raw_bytes):
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = os.path.join(PCL_OUTPUT_DIR, "inbody_{}.pcl".format(timestamp))
    with open(filename, 'wb') as f:
        f.write(raw_bytes)
    logger.info("Saved raw PCL to: {} ({} bytes)".format(filename, len(raw_bytes)))
    return filename

def listen_for_measurement(port):
    while True:
        logger.info("Listening on {} at {} baud for PCL data...".format(port, BAUDRATE))
        try:
            with serial.Serial(port, BAUDRATE, timeout=TIMEOUT) as ser:
                buffer = bytearray()
                last_data_time = time.time()
                print("\n>>> Waiting for PCL print job from InBody <<<\n")

                while True:
                    incoming = ser.read(ser.in_waiting or 1)
                    if incoming:
                        buffer.extend(incoming)
                        logger.debug("Received: {} bytes".format(len(incoming)))
                        last_data_time = time.time()

                    if buffer and (time.time() - last_data_time > 1.5):
                        logger.info("End of PCL transmission. Saving...")
                        filename = save_pcl_data(buffer)

                        print("\n===== RAW PCL CAPTURED =====")
                        print("File: {}".format(filename))
                        print("Size: {} bytes".format(len(buffer)))
                        print("============================\n")

                        buffer = bytearray()
                        print("\n>>> Ready for next measurement <<<\n")

        except serial.SerialException as e:
            logger.error("Serial error: {}".format(e))
            time.sleep(10)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Exiting.")
            break
        except Exception as e:
            logger.error("Unexpected error: {}".format(e))
            time.sleep(10)

def main():
    port = find_inbody_port()
    if port:
        listen_for_measurement(port)
    else:
        logger.error("No valid serial port detected.")

if __name__ == '__main__':
    main()
