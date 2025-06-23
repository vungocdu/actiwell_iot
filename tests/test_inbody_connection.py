#!/usr/bin/env python3
"""
InBody Connection Test Script
===========================

Usage:
    python test_inbody_connection.py
    python test_inbody_connection.py --port /dev/ttyUSB0
    python test_inbody_connection.py --scan
"""

import serial
import time
import sys
import glob
import argparse
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class InBodyConnectionTester:
    """InBody connection testing utility"""
    
    def __init__(self):
        self.test_results = {
            'hardware_check': False,
            'port_access': False,
            'basic_communication': False,
            'command_response': False,
            'data_reception': False
        }
    
    def run_comprehensive_test(self, port=None):
        """Run comprehensive InBody connection test"""
        print("INBODY CONNECTION TEST - COMPREHENSIVE CHECK")
        print("=" * 55)
        print("Test Time: {}".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        print()
        
        # Step 1: Hardware Detection
        print("1. HARDWARE DETECTION")
        print("-" * 25)
        available_ports = self.scan_serial_ports()
        
        if not available_ports:
            print("[FAIL] No serial ports found")
            print("Check:")
            print("   - USB cable connected properly")
            print("   - InBody device powered on") 
            print("   - USB drivers installed")
            return False
        
        print("[PASS] Found {} serial port(s):".format(len(available_ports)))
        for i, port in enumerate(available_ports, 1):
            print("   {}. {}".format(i, port))
        
        self.test_results['hardware_check'] = True
        print()
        
        # Step 2: Port Selection
        test_port = port or self.select_port(available_ports)
        if not test_port:
            print("[FAIL] No port selected for testing")
            return False
        
        print("Testing port: {}".format(test_port))
        print()
        
        # Step 3: Port Access Test
        print("2. PORT ACCESS TEST")
        print("-" * 20)
        if self.test_port_access(test_port):
            print("[PASS] Port access successful")
            self.test_results['port_access'] = True
        else:
            print("[FAIL] Port access failed")
            print("Try:")
            print("   - sudo usermod -a -G dialout $USER")
            print("   - sudo chmod 666 /dev/ttyUSB*")
            print("   - Logout and login again")
            return False
        print()
        
        # Step 4: Basic Communication
        print("3. BASIC COMMUNICATION TEST")
        print("-" * 28)
        if self.test_basic_communication(test_port):
            print("[PASS] Basic communication successful")
            self.test_results['basic_communication'] = True
        else:
            print("[FAIL] Basic communication failed")
            return False
        print()
        
        # Step 5: Command Response Test
        print("4. COMMAND RESPONSE TEST")
        print("-" * 24)
        if self.test_command_response(test_port):
            print("[PASS] Command response successful")
            self.test_results['command_response'] = True
        else:
            print("[WARN] No command response (this might be normal)")
        print()
        
        # Step 6: Data Reception Test
        print("5. DATA RECEPTION TEST")
        print("-" * 22)
        print("Please perform a measurement on InBody device...")
        print("Waiting for measurement data (30 seconds)...")
        
        if self.test_data_reception(test_port):
            print("[PASS] Data reception successful")
            self.test_results['data_reception'] = True
        else:
            print("[INFO] No data received (perform measurement to test)")
        print()
        
        # Summary
        self.print_test_summary()
        return self.test_results['basic_communication']
    
    def scan_serial_ports(self):
        """Scan for available serial ports"""
        ports = []
        
        # Common port patterns
        patterns = [
            '/dev/ttyUSB*',
            '/dev/ttyACM*',
            '/dev/ttyS*',
            'COM*'  # Windows
        ]
        
        for pattern in patterns:
            ports.extend(glob.glob(pattern))
        
        # Test accessibility
        accessible_ports = []
        for port in ports:
            try:
                ser = serial.Serial(port, 9600, timeout=0.5)
                ser.close()
                accessible_ports.append(port)
            except:
                pass
        
        return accessible_ports
    
    def select_port(self, available_ports):
        """Interactive port selection"""
        if len(available_ports) == 1:
            return available_ports[0]
        
        print("Multiple ports available. Please select:")
        for i, port in enumerate(available_ports, 1):
            print("   {}. {}".format(i, port))
        
        try:
            choice = input("Enter number (1-{}): ".format(len(available_ports)))
            index = int(choice) - 1
            if 0 <= index < len(available_ports):
                return available_ports[index]
        except:
            pass
        
        return available_ports[0]  # Default to first
    
    def test_port_access(self, port):
        """Test if port can be opened"""
        try:
            ser = serial.Serial(
                port=port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2.0
            )
            
            print("   Port {} opened successfully".format(port))
            print("   Settings: 9600-8-N-1")
            
            # Test basic read/write
            ser.flushInput()
            ser.flushOutput()
            
            ser.close()
            return True
            
        except Exception as e:
            print("   [FAIL] Failed to open {}: {}".format(port, e))
            return False
    
    def test_basic_communication(self, port):
        """Test basic serial communication"""
        try:
            ser = serial.Serial(port, 9600, timeout=2.0)
            time.sleep(1)
            
            print("   Connected to {}".format(port))
            
            # Clear buffers
            ser.flushInput()
            ser.flushOutput()
            
            print("   Buffers cleared")
            
            # Test if any data is immediately available
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                print("   Immediate data available: {} bytes".format(len(data)))
            else:
                print("   No immediate data (normal)")
            
            ser.close()
            return True
            
        except Exception as e:
            print("   [FAIL] Communication error: {}".format(e))
            return False
    
    def test_command_response(self, port):
        """Test command sending and response"""
        try:
            ser = serial.Serial(port, 9600, timeout=3.0)
            time.sleep(1)
            
            # Common InBody commands to try
            commands = [
                b'STATUS\r\n',
                b'VER\r\n', 
                b'HELLO\r\n',
                b'\x05',  # ENQ (Enquiry)
                b'ID\r\n'
            ]
            
            for cmd in commands:
                print("   Sending: {}".format(cmd))
                ser.write(cmd)
                ser.flush()
                time.sleep(1)
                
                if ser.in_waiting > 0:
                    response = ser.read(ser.in_waiting)
                    print("   Response: {}".format(response))
                    ser.close()
                    return True
            
            print("   No response to commands (device might be passive)")
            ser.close()
            return False
            
        except Exception as e:
            print("   [FAIL] Command test error: {}".format(e))
            return False
    
    def test_data_reception(self, port, timeout=30):
        """Test data reception during measurement"""
        try:
            ser = serial.Serial(port, 9600, timeout=1.0)
            
            print("   Monitoring for measurement data...")
            print("   Start measurement on InBody device now!")
            
            start_time = time.time()
            buffer = ""
            
            while time.time() - start_time < timeout:
                if ser.in_waiting > 0:
                    chunk = ser.read(ser.in_waiting)
                    chunk_str = chunk.decode('utf-8', errors='ignore')
                    buffer += chunk_str
                    
                    print("   Data received: {} bytes".format(len(chunk)))
                    print("   Content preview: {}...".format(chunk_str[:100]))
                    
                    # Check for InBody-like data patterns
                    if any(keyword in buffer.upper() for keyword in 
                          ['WEIGHT', 'BMI', 'ID', 'INBODY', 'KG', 'MUSCLE']):
                        print("   [SUCCESS] InBody measurement data detected!")
                        ser.close()
                        return True
                
                # Show progress
                elapsed = int(time.time() - start_time)
                if elapsed % 5 == 0 and elapsed > 0:
                    remaining = timeout - elapsed
                    print("   Still waiting... {}s remaining".format(remaining))
                
                time.sleep(0.5)
            
            print("   Timeout reached - no measurement data")
            ser.close()
            return False
            
        except Exception as e:
            print("   [FAIL] Data reception error: {}".format(e))
            return False
    
    def test_with_inbody_protocol(self, port):
        """Test using the InBody protocol class"""
        print("6. INBODY PROTOCOL TEST")
        print("-" * 23)
        
        try:
            # Try to import our InBody protocol
            from actiwell_backend.devices import InBodyProtocol
            
            print("   InBody protocol imported successfully")
            
            # Create and test connection
            inbody = InBodyProtocol(port)
            
            if inbody.connect():
                print("   [PASS] InBody protocol connection successful")
                
                # Get device info
                info = inbody.get_device_info()
                print("   Device State: {}".format(info['state']))
                print("   Device Type: {}".format(info['device_type']))
                
                # Test measurement
                print("   Testing measurement read (15 seconds)...")
                measurement = inbody.read_measurement(timeout=15)
                
                if measurement:
                    print("   [SUCCESS] Measurement successful!")
                    print("   Customer: {}".format(measurement.customer_phone))
                    print("   Weight: {} kg".format(measurement.weight_kg))
                else:
                    print("   No measurement data (perform measurement to test)")
                
                inbody.disconnect()
                return True
            else:
                print("   [FAIL] InBody protocol connection failed")
                return False
                
        except ImportError:
            print("   [WARN] InBody protocol not available")
            print("   Make sure you're in the correct directory")
            return False
        except Exception as e:
            print("   [FAIL] Protocol test error: {}".format(e))
            return False
    
    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("TEST SUMMARY")
        print("=" * 15)
        
        total_tests = len(self.test_results)
        passed_tests = sum(self.test_results.values())
        
        print("Total Tests: {}".format(total_tests))
        print("Passed: {}".format(passed_tests))
        print("Failed: {}".format(total_tests - passed_tests))
        print("Success Rate: {:.1f}%".format(passed_tests/total_tests*100))
        print()
        
        print("Detailed Results:")
        for test, result in self.test_results.items():
            status = "[PASS]" if result else "[FAIL]"
            test_name = test.replace('_', ' ').title()
            print("  {} {}".format(status, test_name))
        
        print()
        
        if passed_tests >= 3:
            print("[SUCCESS] CONNECTION SUCCESSFUL!")
            print("InBody device is properly connected and communicating")
            print()
            print("Next Steps:")
            print("1. Use the device with your application")
            print("2. Perform test measurements")
            print("3. Verify data integration")
        elif passed_tests >= 1:
            print("[WARN] PARTIAL CONNECTION")
            print("Device detected but communication issues")
            print()
            print("Recommendations:")
            print("1. Check InBody device settings")
            print("2. Verify communication parameters")
            print("3. Try different connection methods")
        else:
            print("[FAIL] CONNECTION FAILED")
            print("No working connection established")
            print()
            print("Troubleshooting:")
            print("1. Check hardware connections")
            print("2. Verify device power and settings")
            print("3. Install proper drivers")
            print("4. Check user permissions")

def main():
    """Main test function"""
    parser = argparse.ArgumentParser(description='Test InBody device connection')
    parser.add_argument('--port', help='Specific port to test (e.g., /dev/ttyUSB0)')
    parser.add_argument('--scan', action='store_true', help='Only scan for ports')
    parser.add_argument('--protocol', action='store_true', help='Test with InBody protocol class')
    
    args = parser.parse_args()
    
    tester = InBodyConnectionTester()
    
    if args.scan:
        print("SCANNING FOR SERIAL PORTS")
        print("=" * 30)
        ports = tester.scan_serial_ports()
        if ports:
            print("Found {} accessible port(s):".format(len(ports)))
            for port in ports:
                print("  {}".format(port))
        else:
            print("[FAIL] No accessible ports found")
        return
    
    success = tester.run_comprehensive_test(args.port)
    
    if args.protocol and success:
        port = args.port or tester.scan_serial_ports()[0]
        tester.test_with_inbody_protocol(port)
    
    print("\nTest completed!")

if __name__ == "__main__":
    main()