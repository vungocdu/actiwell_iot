#!/usr/bin/env python3
"""
Combined HL7 + Connection Test for InBody 270
This script tests the connection to an InBody 270 device via serial port,
reads HL7 messages, and parses the relevant data fields.
"""

import serial
import time
import glob
import logging
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("InBodyHL7")

# HL7 markers
START_BLOCK = b'\x0b'  # VT (vertical tab)
END_BLOCK = b'\x1c'    # FS (file separator)
CARRIAGE_RETURN = b'\x0d'  # CR

BAUDRATE = 9600


def scan_serial_ports():
    """Scan for available serial ports"""
    ports = []
    patterns = ['/dev/ttyUSB*', '/dev/ttyACM*', '/dev/ttyS*']
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


def parse_hl7_message(hl7_text):
    segments = hl7_text.strip().split('\r')
    data = {}

    for segment in segments:
        fields = segment.split('|')
        if fields[0] == 'PID':
            data['patient_id'] = fields[3] if len(fields) > 3 else ''
        elif fields[0] == 'OBX':
            if len(fields) > 5:
                code_field = fields[3]
                value = fields[5]
                if 'WT' in code_field:
                    data['weight_kg'] = float(value)
                elif 'HT' in code_field:
                    data['height_cm'] = float(value)
                elif 'BF' in code_field:
                    data['body_fat_percent'] = float(value)
                elif 'BMI' in code_field:
                    data['bmi'] = float(value)

    return data


def read_hl7(port):
    try:
        ser = serial.Serial(port, baudrate=BAUDRATE, timeout=1.0)
        logger.info("Connected to port: {}".format(port))
        buffer = b''

        print("Please perform a measurement on InBody device...")
        start_time = time.time()

        while time.time() - start_time < 60:
            byte = ser.read(1)
            if not byte:
                continue

            buffer += byte

            if START_BLOCK in buffer and END_BLOCK in buffer:
                start = buffer.index(START_BLOCK) + 1
                end = buffer.index(END_BLOCK)
                hl7_raw = buffer[start:end].decode('utf-8', errors='ignore')

                logger.info("Received HL7 message:")
                logger.info(hl7_raw.replace('\r', '\n'))

                parsed = parse_hl7_message(hl7_raw)
                logger.info("Parsed Data: {}".format(parsed))
                return True

            time.sleep(0.01)

        logger.warning("No HL7 message received within 60 seconds")
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
            read_hl7(port)
        else:
            print("Skipping port {} due to access failure".format(port))


if __name__ == '__main__':
    main()
# This script is designed to test the connection to an InBody 270 device via serial port,
# read HL7 messages, and parse the relevant data fields.