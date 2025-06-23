#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
InBody 270 - Clean Data Reader for Raspberry Pi
===============================================

Description:
- Connects to InBody 270 via USB-to-Serial adapter
- Reads and parses measurement data from the device
- Saves data to files for further processing
- No external API dependencies
- Compatible with Python 3.5+

Author: Professional IoT Engineer
Version: 2.1.1 (Final Clean)
"""

import serial
import serial.tools.list_ports
import time
import logging
import re
import json
from datetime import datetime
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('inbody_reader.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("InBodyReader")

def safe_makedirs(path):
    """Create directory safely, compatible with older Python versions"""
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise

# Configuration
class Config:
    """Configuration settings"""
    def __init__(self):
        self.BAUDRATE = 9600
        self.TIMEOUT = 0.5
        self.MESSAGE_TIMEOUT = 2.0
        self.RECONNECT_DELAY = 10
        
        # Data storage
        self.SAVE_RAW_DATA = True
        self.SAVE_PARSED_DATA = True
        self.DATA_DIR = "inbody_data"
        
        # Output format
        self.DISPLAY_VERBOSE = True

class InBodyDataParser:
    """Enhanced parser for different InBody data formats"""
    
    def __init__(self):
        self.patterns = {
            # Common InBody patterns
            'key_value': re.compile(r'([a-zA-Z\s]+):\s*([\d\.]+)'),
            'csv_like': re.compile(r'([^,]+),([^,]+),([^,]+)'),
            'id_field': re.compile(r'ID\s*[:\s]*([^\n\r,]+)'),
            'phone_number': re.compile(r'(\d{10,11})'),
            
            # Specific measurements
            'weight': re.compile(r'(?:weight|wt|w)\s*[:\s]*([\d\.]+)', re.IGNORECASE),
            'bmi': re.compile(r'bmi\s*[:\s]*([\d\.]+)', re.IGNORECASE),
            'body_fat': re.compile(r'(?:body\s*fat|bf|fat)\s*[:\s]*([\d\.]+)', re.IGNORECASE),
            'muscle': re.compile(r'(?:muscle|mm)\s*[:\s]*([\d\.]+)', re.IGNORECASE),
            'water': re.compile(r'(?:water|tbw)\s*[:\s]*([\d\.]+)', re.IGNORECASE),
            'bone': re.compile(r'(?:bone|bm)\s*[:\s]*([\d\.]+)', re.IGNORECASE),
        }
    
    def parse_data(self, raw_data):
        """
        Parse raw InBody data into structured format
        """
        data = {
            'raw_data': raw_data,
            'timestamp': datetime.now().isoformat(),
            'device_type': 'InBody_270',
            'parsing_method': 'unknown',
            'data_length': len(raw_data)
        }
        
        # Clean the data
        cleaned_data = raw_data.strip().replace('\r', '').replace('\x00', '')
        
        # Try different parsing methods
        if self._try_csv_format(cleaned_data, data):
            data['parsing_method'] = 'csv'
        elif self._try_key_value_format(cleaned_data, data):
            data['parsing_method'] = 'key_value'
        elif self._try_structured_format(cleaned_data, data):
            data['parsing_method'] = 'structured'
        else:
            # Fallback: extract individual measurements
            self._extract_measurements(cleaned_data, data)
            data['parsing_method'] = 'fallback'
        
        # Extract customer identification
        self._extract_customer_id(cleaned_data, data)
        
        # Validate parsed data
        self._validate_measurements(data)
        
        return data
    
    def _try_csv_format(self, data, result):
        """Try parsing as CSV-like format"""
        lines = data.split('\n')
        for line in lines:
            if ',' in line and len(line.split(',')) >= 3:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 6:
                    try:
                        # Common InBody CSV format (approximate)
                        result.update({
                            'customer_id': parts[0] if parts[0] else 'unknown',
                            'weight_kg': float(parts[1]) if self._is_number(parts[1]) else None,
                            'bmi': float(parts[2]) if self._is_number(parts[2]) else None,
                            'body_fat_percent': float(parts[3]) if self._is_number(parts[3]) else None,
                            'muscle_mass_kg': float(parts[4]) if self._is_number(parts[4]) else None,
                            'bone_mass_kg': float(parts[5]) if self._is_number(parts[5]) else None,
                        })
                        return True
                    except (ValueError, IndexError):
                        continue
        return False
    
    def _try_key_value_format(self, data, result):
        """Try parsing as Key: Value format"""
        found_measurements = 0
        lines = data.split('\n')
        
        for line in lines:
            match = self.patterns['key_value'].search(line)
            if match:
                key = match.group(1).strip().replace(' ', '_').lower()
                try:
                    value = float(match.group(2).strip())
                    
                    # Append unit to key
                    if 'kg' in line.lower():
                        result['{}_kg'.format(key)] = value
                    elif '%' in line.lower():
                        result['{}_percent'.format(key)] = value
                    else:
                        result[key] = value
                    
                    found_measurements += 1
                except ValueError:
                    continue
        
        return found_measurements >= 3
    
    def _try_structured_format(self, data, result):
        """Try parsing structured/proprietary format"""
        if 'InBody' in data and len(data) > 50:
            return self._extract_measurements(data, result)
        return False
    
    def _extract_measurements(self, data, result):
        """Extract individual measurements using regex patterns"""
        extracted = 0
        
        measurements = {
            'weight_kg': self.patterns['weight'],
            'bmi': self.patterns['bmi'],
            'body_fat_percent': self.patterns['body_fat'],
            'muscle_mass_kg': self.patterns['muscle'],
            'total_body_water_kg': self.patterns['water'],
            'bone_mass_kg': self.patterns['bone']
        }
        
        for field, pattern in measurements.items():
            match = pattern.search(data)
            if match:
                try:
                    result[field] = float(match.group(1))
                    extracted += 1
                except ValueError:
                    continue
        
        return extracted >= 2
    
    def _extract_customer_id(self, data, result):
        """Extract customer ID/phone number"""
        id_match = self.patterns['id_field'].search(data)
        if id_match:
            customer_id = id_match.group(1).strip()
            result['customer_id_raw'] = customer_id
            
            # Try to extract phone number from ID
            phone_match = self.patterns['phone_number'].search(customer_id)
            if phone_match:
                phone = phone_match.group(1)
                # Format Vietnamese phone number
                if len(phone) == 10 and phone.startswith('0'):
                    result['customer_phone'] = phone
                elif len(phone) == 11 and phone.startswith('84'):
                    result['customer_phone'] = '0' + phone[2:]
                elif len(phone) == 9:
                    result['customer_phone'] = '0' + phone
                else:
                    result['customer_phone'] = phone
    
    def _validate_measurements(self, data):
        """Validate measurement values are within reasonable ranges"""
        validations = {
            'weight_kg': (20, 300),
            'bmi': (10, 50),
            'body_fat_percent': (3, 60),
            'muscle_mass_kg': (10, 150),
            'bone_mass_kg': (1, 10),
            'total_body_water_kg': (10, 100)
        }
        
        for field, limits in validations.items():
            min_val, max_val = limits
            if field in data and data[field] is not None:
                value = data[field]
                if not (min_val <= value <= max_val):
                    logger.warning("Suspicious value for {}: {} (expected {}-{})".format(
                        field, value, min_val, max_val))
                    data['{}_validation'.format(field)] = 'out_of_range'
                else:
                    data['{}_validation'.format(field)] = 'valid'
    
    def _is_number(self, value):
        """Check if string can be converted to float"""
        try:
            float(value)
            return True
        except ValueError:
            return False

class InBodyReader:
    """Main InBody reader class"""
    
    def __init__(self, config):
        self.config = config
        self.parser = InBodyDataParser()
        self.measurement_count = 0
        
        # Create data directory
        if config.SAVE_RAW_DATA or config.SAVE_PARSED_DATA:
            safe_makedirs(config.DATA_DIR)
    
    def find_inbody_port(self):
        """Find InBody serial port"""
        logger.info("Scanning for available serial ports...")
        available_ports = serial.tools.list_ports.comports()
        
        if not available_ports:
            logger.warning("No serial ports found on this system.")
            return None

        logger.info("Found {} port(s): {}".format(
            len(available_ports), [p.device for p in available_ports]))

        for port in available_ports:
            if "USB" in port.description or "USB" in port.name or "ACM" in port.name:
                logger.info("Checking port {}...".format(port.device))
                try:
                    ser = serial.Serial(port.device, self.config.BAUDRATE, timeout=1)
                    ser.close()
                    logger.info("Successfully accessed port {}".format(port.device))
                    return port.device
                except serial.SerialException as e:
                    logger.warning("Could not open port {}: {}".format(port.device, e))
                    continue
        
        # If no USB port found, try the first available port
        if available_ports:
            first_port = available_ports[0].device
            logger.info("Trying first available port: {}".format(first_port))
            try:
                ser = serial.Serial(first_port, self.config.BAUDRATE, timeout=1)
                ser.close()
                return first_port
            except serial.SerialException:
                pass
        
        logger.error("Could not find a valid InBody serial port.")
        return None
    
    def save_raw_data(self, data):
        """Save raw data to file"""
        if self.config.SAVE_RAW_DATA:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(self.config.DATA_DIR, 
                                   'inbody_raw_{}.txt'.format(timestamp))
            try:
                with open(filename, 'w') as f:
                    f.write("InBody Raw Data\n")
                    f.write("Timestamp: {}\n".format(datetime.now()))
                    f.write("Data Length: {} bytes\n".format(len(data)))
                    f.write("-" * 50 + "\n")
                    f.write(data)
                logger.info("Raw data saved to: {}".format(filename))
            except Exception as e:
                logger.error("Failed to save raw data: {}".format(e))
    
    def save_parsed_data(self, data):
        """Save parsed data to JSON file"""
        if self.config.SAVE_PARSED_DATA:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(self.config.DATA_DIR, 
                                   'inbody_parsed_{}.json'.format(timestamp))
            try:
                # Remove raw_data for cleaner JSON
                clean_data = {k: v for k, v in data.items() if k != 'raw_data'}
                
                with open(filename, 'w') as f:
                    json.dump(clean_data, f, indent=2, ensure_ascii=False)
                logger.info("Parsed data saved to: {}".format(filename))
            except Exception as e:
                logger.error("Failed to save parsed data: {}".format(e))
    
    def display_measurement(self, data):
        """Display measurement results"""
        self.measurement_count += 1
        
        print("\n" + "="*60)
        print("INBODY MEASUREMENT #{} RESULT".format(self.measurement_count))
        print("="*60)
        print("Timestamp: {}".format(data.get('timestamp')))
        print("Data Length: {} bytes".format(data.get('data_length')))
        print("Parsing Method: {}".format(data.get('parsing_method')))
        
        # Customer information
        customer_phone = data.get('customer_phone')
        customer_id = data.get('customer_id_raw')
        
        if customer_phone:
            print("Customer Phone: {}".format(customer_phone))
        elif customer_id:
            print("Customer ID: {}".format(customer_id))
        else:
            print("Customer ID: Not detected")
        
        print("-" * 30)
        print("MEASUREMENTS:")
        
        # Show measurements
        measurements = [
            ('weight_kg', 'Weight'),
            ('bmi', 'BMI'),
            ('body_fat_percent', 'Body Fat %'),
            ('muscle_mass_kg', 'Muscle Mass'),
            ('bone_mass_kg', 'Bone Mass'),
            ('total_body_water_kg', 'Total Body Water')
        ]
        
        found_measurements = 0
        for field, label in measurements:
            if field in data and data[field] is not None:
                value = data[field]
                unit = 'kg' if 'kg' in field else '%' if 'percent' in field else ''
                validation = data.get('{}_validation'.format(field), '')
                
                status = ""
                if validation == 'out_of_range':
                    status = " [WARNING: Out of range]"
                elif validation == 'valid':
                    status = " [OK]"
                
                print("{:<20}: {}{} {}".format(label, value, unit, status))
                found_measurements += 1
        
        if found_measurements == 0:
            print("No measurements extracted successfully")
            if self.config.DISPLAY_VERBOSE:
                print("\nRAW DATA PREVIEW:")
                raw_preview = data.get('raw_data', '')[:200]
                print(repr(raw_preview))
        
        print("="*60 + "\n")
    
    def listen_for_measurements(self, port):
        """Main listening loop"""
        while True:
            logger.info("Connecting to InBody on port {} at {} baud...".format(
                port, self.config.BAUDRATE))
            try:
                with serial.Serial(port, self.config.BAUDRATE, 
                                 timeout=self.config.TIMEOUT) as ser:
                    logger.info("Connection successful! Waiting for measurements...")
                    print("\n[READY] Perform measurement on InBody device\n")

                    message_buffer = ""
                    last_data_time = time.time()

                    while True:
                        data = ser.read(ser.in_waiting or 1).decode('utf-8', errors='ignore')

                        if data:
                            if not message_buffer:
                                logger.info("Data signal detected! Receiving...")
                            message_buffer += data
                            last_data_time = time.time()

                        # Check for complete message
                        if message_buffer and (time.time() - last_data_time > self.config.MESSAGE_TIMEOUT):
                            logger.info("Complete message received ({} bytes)".format(
                                len(message_buffer)))
                            
                            # Save raw data
                            self.save_raw_data(message_buffer)
                            
                            # Parse the data
                            parsed_data = self.parser.parse_data(message_buffer)
                            
                            # Save parsed data
                            self.save_parsed_data(parsed_data)
                            
                            # Display results
                            self.display_measurement(parsed_data)
                            
                            # Reset for next measurement
                            message_buffer = ""
                            print("\n[READY] Ready for next measurement\n")

            except serial.SerialException as e:
                logger.error("Serial port error: {}".format(e))
                logger.info("Reconnecting in {} seconds...".format(self.config.RECONNECT_DELAY))
                time.sleep(self.config.RECONNECT_DELAY)
            except KeyboardInterrupt:
                logger.info("Shutdown requested (Ctrl+C). Exiting...")
                break
            except Exception as e:
                logger.error("Unexpected error: {}".format(e))
                logger.info("Restarting in {} seconds...".format(self.config.RECONNECT_DELAY))
                time.sleep(self.config.RECONNECT_DELAY)

def main():
    """Main function"""
    print("InBody 270 Data Reader")
    print("=====================")
    print("Starting InBody measurement reader...")
    print()
    
    config = Config()
    reader = InBodyReader(config)
    
    # Find the InBody port
    port = reader.find_inbody_port()
    
    if port:
        logger.info("Starting InBody reader on port: {}".format(port))
        print("Data will be saved to: {}".format(config.DATA_DIR))
        print("Press Ctrl+C to stop\n")
        reader.listen_for_measurements(port)
    else:
        logger.error("Cannot start - no InBody port found")
        logger.error("Check USB connection and permissions")
        print("\nTroubleshooting:")
        print("1. Check USB cable connection")
        print("2. Verify InBody device is powered on")
        print("3. Check permissions: sudo usermod -a -G dialout $USER")
        print("4. Try: sudo chmod 666 /dev/ttyUSB*")

if __name__ == '__main__':
    main()