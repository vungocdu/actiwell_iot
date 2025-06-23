#!/usr/bin/env python3
"""
InBody Open Protocol Reader (One Way Mode)
"""

import serial
import time
import glob
import logging
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("InBodyOpenProtocol")

BAUDRATE = 9600


def scan_serial_ports():
    """Scan for available serial ports"""
    ports = []
    patterns = ['/dev/ttyUSB*', '/dev/ttyACM*']
    for pattern in patterns:
        ports.extend(glob.glob(pattern))
    return ports


def test_port_access(port):
    try:
        ser = serial.Serial(port, baudrate=BAUDRATE, timeout=1.0)
        ser.close()
        logger.info("Port access OK: {}".format(port))
        return True
    except Exception as e:
        logger.error("Cannot open port {}: {}".format(port, e))
        return False


def read_openprotocol(port):
    try:
        ser = serial.Serial(port, baudrate=BAUDRATE, timeout=1.0)
        logger.info("Connected to port: {}".format(port))
        buffer = ""

        print("Please perform a measurement on InBody device...")
        start_time = time.time()

        while time.time() - start_time < 180:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                buffer += data
                logger.info("Raw Data: {}".format(data.strip()))

                if "Weight" in buffer or "ID" in buffer:
                    logger.info("Measurement data received.")
                    return True

            time.sleep(0.2)

        logger.warning("No measurement data received within 180 seconds")
        return False

    except Exception as e:
        logger.error("Read error: {}".format(e))
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', help='Serial port to test (e.g. /dev/ttyUSB0)')
    args = parser.parse_args()

    ports = [args.port] if args.port else scan_serial_ports()

    if not ports:
        logger.error("No serial ports found")
        return

    for port in ports:
        print("\n--- Testing port {} ---".format(port))
        if test_port_access(port):
            read_openprotocol(port)
        else:
            print("Skipping port {} due to access failure".format(port))


if __name__ == '__main__':
    main()
