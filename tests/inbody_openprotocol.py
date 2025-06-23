#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
InBody 270 - Simulated Printer Listener on Raspberry Pi (PCL Mode)
====================================================================

Description:
- This script simulates a printer connected to an InBody 270.
- It listens for PCL-formatted print data sent via a USB-to-Serial connection.
- It saves the raw PCL data to files for later processing.
- This version is compatible with older Python versions that do not support
  os.makedirs(exist_ok=True).

Author: Professional IoT Engineer
Version: 1.4.1 (Backward-compatible)
"""

import serial
import serial.tools.list_ports
import time
import logging
import os
import errno # Import errno for checking file existence errors

# --- Configuration ---
# Logging setup for monitoring and debugging
logging.basicConfig(
    level=logging.INFO, # Change to logging.DEBUG for more detailed output
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("InBodyPCLPrinter")

# Serial port settings (must match InBody configuration)
BAUDRATE = 9600
TIMEOUT = 0.5  # Read timeout in seconds

# Directory to save the captured PCL files
PCL_OUTPUT_DIR = "/tmp/inbody_pcl"
# --- End of Configuration ---


# --- Compatibility-safe directory creation ---
# This block replaces os.makedirs(..., exist_ok=True) for older Python versions
try:
    os.makedirs(PCL_OUTPUT_DIR)
    logger.info("Created PCL output directory: {}".format(PCL_OUTPUT_DIR))
except OSError as e:
    if e.errno != errno.EEXIST:
        # If the error is something other than "directory already exists", raise it.
        raise
    # If the directory already exists, do nothing (which is the goal of exist_ok=True)
    pass


def find_inbody_port():
    """Scans and selects a valid serial port, likely connected to the InBody device."""
    logger.info("Scanning for available serial ports...")
    available_ports = serial.tools.list_ports.comports()
    if not available_ports:
        logger.warning("No serial ports found.")
        return None
    
    logger.info("Found ports: {}".format([p.device for p in available_ports]))
    for port in available_ports:
        # Filter for common USB-to-Serial adapter names
        if "USB" in port.description or "ACM" in port.name or "ttyUSB" in port.device:
            try:
                # Test port accessibility
                ser = serial.Serial(port.device, BAUDRATE, timeout=1)
                ser.close()
                logger.info("Selected port: {}".format(port.device))
                return port.device
            except serial.SerialException as e:
                logger.warning("Failed to access port {}: {}".format(port.device, e))
                
    logger.error("No suitable serial port found.")
    return None

def save_pcl_data(raw_bytes):
    """Saves the captured raw PCL byte stream to a file with a timestamp."""
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = os.path.join(PCL_OUTPUT_DIR, "inbody_{}.pcl".format(timestamp))
    try:
        with open(filename, 'wb') as f:
            f.write(raw_bytes)
        logger.info("Saved raw PCL to: {} ({} bytes)".format(filename, len(raw_bytes)))
        return filename
    except IOError as e:
        logger.error("Failed to save PCL file {}: {}".format(filename, e))
        return None

def listen_for_print_job(port):
    """
    Main loop to listen for a PCL print job on the specified serial port.
    It runs continuously, reconnecting if necessary.
    """
    while True:
        logger.info("Listening on {} at {} baud for PCL data...".format(port, BAUDRATE))
        try:
            with serial.Serial(port, BAUDRATE, timeout=TIMEOUT) as ser:
                buffer = bytearray()
                last_data_time = time.time()
                is_receiving = False
                
                print("\n>>> Waiting for PCL print job from InBody device <<<")
                print("    (To test, use the 'Print' function on the InBody 270)")
                print("    Press Ctrl+C to exit.\n")

                while True:
                    # Read available bytes from the serial buffer
                    incoming_bytes = ser.read(ser.in_waiting or 1)
                    
                    if incoming_bytes:
                        if not is_receiving:
                            logger.info("Receiving PCL data stream...")
                            is_receiving = True
                        
                        buffer.extend(incoming_bytes)
                        # Uncomment for very detailed debugging:
                        # logger.debug("Received: {} bytes, Buffer size: {}".format(len(incoming_bytes), len(buffer)))
                        last_data_time = time.time()

                    # A timeout of 1.5 seconds with no new data indicates the end of the print job
                    if is_receiving and (time.time() - last_data_time > 1.5):
                        logger.info("End of PCL transmission detected. Processing...")
                        
                        # Save the captured data to a file
                        filename = save_pcl_data(buffer)

                        if filename:
                            print("\n" + "="*50)
                            print("      RAW PCL DATA CAPTURED SUCCESSFULLY")
                            print("      File: {}".format(filename))
                            print("      Size: {} bytes".format(len(buffer)))
                            print("="*50 + "\n")
                            # --- NEXT STEP ---
                            # Here you would call a function to process the PCL file, e.g.:
                            # process_pcl_file(filename)

                        # Reset for the next job
                        buffer = bytearray()
                        is_receiving = False
                        print("\n>>> System is ready for the next print job <<<\n")

        except serial.SerialException as e:
            logger.error("Serial port error: {}. Will retry in 10 seconds.".format(e))
            time.sleep(10)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Shutting down.")
            break
        except Exception as e:
            logger.error("An unexpected error occurred: {}. Restarting listener in 10 seconds.".format(e))
            time.sleep(10)

def main():
    """The main entry point for the script."""
    port = find_inbody_port()
    if port:
        listen_for_print_job(port)
    else:
        logger.error("Execution failed: No valid serial port was detected.")

if __name__ == '__main__':
    main()