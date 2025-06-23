#!/usr/bin/env python3
"""
HL7 Reader for InBody 270
"""

import serial
import time
import re
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("InBodyHL7")

# Serial Port Config
SERIAL_PORT = '/dev/ttyUSB0'
BAUDRATE = 9600

# HL7 message start and end
START_BLOCK = b'\x0b'  # VT (vertical tab)
END_BLOCK = b'\x1c'    # FS (file separator)
CARRIAGE_RETURN = b'\x0d'  # CR


def parse_hl7_message(hl7_text):
    """Parses a raw HL7 message string and extracts meaningful fields."""
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


def read_hl7_from_serial():
    """Continuously reads HL7 messages from serial port and parses them."""
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0
        )
        logger.info("Opened serial port {}".format(SERIAL_PORT))

        buffer = b''

        while True:
            byte = ser.read(1)
            if not byte:
                continue

            buffer += byte

            # Check for complete HL7 message
            if START_BLOCK in buffer and END_BLOCK in buffer:
                start = buffer.index(START_BLOCK) + 1
                end = buffer.index(END_BLOCK)
                hl7_raw = buffer[start:end].decode('utf-8', errors='ignore')

                logger.info("Received HL7 message:")
                logger.info(hl7_raw.replace('\r', '\n'))

                parsed = parse_hl7_message(hl7_raw)
                logger.info("Parsed Data: {}".format(parsed))

                # Reset buffer
                buffer = buffer[end+1:]

            time.sleep(0.01)

    except Exception as e:
        logger.error("Serial Error: {}".format(e))


if __name__ == '__main__':
    read_hl7_from_serial()
