#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
InBody 270 Debug Tool - Advanced Troubleshooting
================================================

This script will help diagnose why InBody is not sending data
"""

import serial
import time
import sys
from datetime import datetime

class InBodyDebugger:
    """Debug tool for InBody connection issues"""
    
    def __init__(self):
        self.port = '/dev/ttyUSB0'  # Adjust if needed
        
    def test_all_baudrates(self):
        """Test different baudrates to find the correct one"""
        print("="*60)
        print("TESTING DIFFERENT BAUDRATES")
        print("="*60)
        
        baudrates = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
        
        for baudrate in baudrates:
            print("\nTesting baudrate: {}".format(baudrate))
            try:
                ser = serial.Serial(self.port, baudrate, timeout=2)
                
                # Send some test commands
                test_commands = [
                    b'STATUS\r\n',
                    b'VER\r\n',
                    b'ID\r\n',
                    b'START\r\n',
                    b'MEASURE\r\n',
                    b'\x05',  # ENQ
                    b'?'
                ]
                
                for cmd in test_commands:
                    ser.write(cmd)
                    ser.flush()
                    time.sleep(0.5)
                    
                    if ser.in_waiting > 0:
                        response = ser.read(ser.in_waiting)
                        print("  Command {}: Got response: {}".format(cmd, response))
                        ser.close()
                        return baudrate
                
                ser.close()
                print("  No response at {}".format(baudrate))
                
            except Exception as e:
                print("  Error at {}: {}".format(baudrate, e))
        
        print("\nNo responses found at any baudrate")
        return None
    
    def test_activation_commands(self):
        """Try various commands to activate data transmission"""
        print("="*60)
        print("TESTING ACTIVATION COMMANDS")
        print("="*60)
        
        commands = [
            # Standard commands
            (b'START\r\n', 'Start measurement'),
            (b'ACTIVATE\r\n', 'Activate protocol'),
            (b'ENABLE\r\n', 'Enable transmission'),
            (b'OUTPUT ON\r\n', 'Turn on output'),
            (b'PROTOCOL ON\r\n', 'Enable protocol'),
            
            # ASCII control characters
            (b'\x05', 'ENQ (Enquiry)'),
            (b'\x06', 'ACK (Acknowledge)'),
            (b'\x15', 'NAK (Negative Acknowledge)'),
            (b'\x04', 'EOT (End of Transmission)'),
            
            # InBody specific (guessed)
            (b'INBODY\r\n', 'InBody command'),
            (b'DATA\r\n', 'Request data'),
            (b'TRANSMIT\r\n', 'Transmit command'),
            (b'?', 'Query'),
            
            # Try hex commands
            (b'\x01\x02\x03', 'Hex sequence 1'),
            (b'\xFF\xFE\xFD', 'Hex sequence 2'),
        ]
        
        try:
            ser = serial.Serial(self.port, 9600, timeout=1)
            print("Connected to {}".format(self.port))
            
            for cmd, description in commands:
                print("\nTrying: {} ({})".format(description, cmd))
                
                # Clear buffers
                ser.flushInput()
                ser.flushOutput()
                
                # Send command
                ser.write(cmd)
                ser.flush()
                
                # Wait for response
                time.sleep(1)
                
                if ser.in_waiting > 0:
                    response = ser.read(ser.in_waiting)
                    print("  SUCCESS! Response: {}".format(response))
                    print("  Raw bytes: {}".format([hex(b) for b in response]))
                    
                    # Continue monitoring for more data
                    print("  Monitoring for 10 seconds...")
                    start_time = time.time()
                    while time.time() - start_time < 10:
                        if ser.in_waiting > 0:
                            more_data = ser.read(ser.in_waiting)
                            print("  Additional data: {}".format(more_data))
                        time.sleep(0.1)
                    
                    ser.close()
                    return True
                else:
                    print("  No response")
            
            ser.close()
            
        except Exception as e:
            print("Error testing commands: {}".format(e))
        
        return False
    
    def passive_monitor_extended(self):
        """Extended passive monitoring with detailed logging"""
        print("="*60)
        print("EXTENDED PASSIVE MONITORING")
        print("="*60)
        print("This will monitor for 5 minutes with detailed logging")
        print("Perform measurements during this time")
        print("Press Ctrl+C to stop early")
        print()
        
        try:
            ser = serial.Serial(self.port, 9600, timeout=0.1)
            
            start_time = time.time()
            last_activity = start_time
            total_bytes = 0
            data_chunks = []
            
            print("Monitoring started at: {}".format(datetime.now().strftime('%H:%M:%S')))
            print("Waiting for data...")
            
            while time.time() - start_time < 300:  # 5 minutes
                if ser.in_waiting > 0:
                    chunk = ser.read(ser.in_waiting)
                    chunk_time = datetime.now()
                    total_bytes += len(chunk)
                    
                    print("\n[{}] DATA RECEIVED: {} bytes".format(
                        chunk_time.strftime('%H:%M:%S.%f')[:-3], len(chunk)))
                    print("Raw bytes: {}".format([hex(b) for b in chunk]))
                    
                    # Try to decode as text
                    try:
                        text = chunk.decode('utf-8', errors='ignore')
                        print("As text: {}".format(repr(text)))
                        if text.strip():
                            print("Clean text: {}".format(text.strip()))
                    except:
                        print("Cannot decode as UTF-8")
                    
                    # Try other encodings
                    for encoding in ['ascii', 'latin-1', 'cp1252']:
                        try:
                            alt_text = chunk.decode(encoding, errors='ignore')
                            if alt_text != text and alt_text.strip():
                                print("As {}: {}".format(encoding, repr(alt_text)))
                        except:
                            pass
                    
                    data_chunks.append((chunk_time, chunk))
                    last_activity = time.time()
                    
                    print("-" * 50)
                
                # Show periodic status
                elapsed = int(time.time() - start_time)
                if elapsed % 30 == 0 and elapsed > 0:
                    print("\n[STATUS] {} seconds elapsed, {} bytes received total".format(
                        elapsed, total_bytes))
                
                time.sleep(0.1)
            
            ser.close()
            
            print("\n" + "="*60)
            print("MONITORING SUMMARY")
            print("="*60)
            print("Total monitoring time: 5 minutes")
            print("Total data received: {} bytes".format(total_bytes))
            print("Number of data chunks: {}".format(len(data_chunks)))
            
            if data_chunks:
                print("First data at: {}".format(data_chunks[0][0].strftime('%H:%M:%S')))
                print("Last data at: {}".format(data_chunks[-1][0].strftime('%H:%M:%S')))
                
                # Save all data to file
                filename = "inbody_debug_{}.txt".format(
                    datetime.now().strftime('%Y%m%d_%H%M%S'))
                with open(filename, 'wb') as f:
                    for chunk_time, chunk in data_chunks:
                        f.write("=== {} ===\n".format(chunk_time).encode())
                        f.write(chunk)
                        f.write(b"\n")
                print("All data saved to: {}".format(filename))
            else:
                print("NO DATA RECEIVED during monitoring period")
            
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
        except Exception as e:
            print("Error during monitoring: {}".format(e))
    
    def check_device_settings_help(self):
        """Display help for checking InBody device settings"""
        print("="*60)
        print("INBODY DEVICE CONFIGURATION CHECKLIST")
        print("="*60)
        print()
        print("Please check these settings on your InBody 270 device:")
        print()
        print("1. COMMUNICATION SETTINGS:")
        print("   - Look for 'Communication' or 'Comm' in device menu")
        print("   - Enable 'Serial Communication' or 'RS232'")
        print("   - Set Baud Rate to 9600")
        print("   - Set Data Bits: 8, Parity: None, Stop Bits: 1")
        print()
        print("2. DATA OUTPUT SETTINGS:")
        print("   - Look for 'Data Output' or 'Output' menu")
        print("   - Enable 'Auto Send' or 'Auto Transmit'")
        print("   - Enable 'Open Protocol' mode")
        print("   - Set Output Format to 'CSV' or 'Standard'")
        print()
        print("3. MEASUREMENT MODE:")
        print("   - Ensure device is in 'Professional' mode")
        print("   - Check that 'ID input' is enabled")
        print("   - Make sure 'Data transmission' is ON")
        print()
        print("4. CONNECTION CHECK:")
        print("   - USB cable properly connected")
        print("   - Device powered on and ready")
        print("   - No other software using the serial port")
        print()
        print("5. MEASUREMENT PROCEDURE:")
        print("   - Enter customer ID (phone number)")
        print("   - Wait for device to show 0.0")
        print("   - Step on device and complete full measurement")
        print("   - Stay on device until measurement finishes")
        print("   - Data should transmit automatically after measurement")
        print()
    
    def test_different_settings(self):
        """Test with different serial port settings"""
        print("="*60)
        print("TESTING DIFFERENT SERIAL SETTINGS")
        print("="*60)
        
        settings = [
            # (baudrate, bytesize, parity, stopbits)
            (9600, 8, 'N', 1),    # Standard
            (9600, 7, 'N', 1),    # 7-bit
            (9600, 8, 'E', 1),    # Even parity
            (9600, 8, 'O', 1),    # Odd parity
            (9600, 8, 'N', 2),    # 2 stop bits
            (19200, 8, 'N', 1),   # Higher speed
            (4800, 8, 'N', 1),    # Lower speed
        ]
        
        for baud, bits, parity, stop in settings:
            print("\nTesting: {}-{}-{}-{}".format(baud, bits, parity, stop))
            
            try:
                # Convert parity
                parity_map = {'N': serial.PARITY_NONE, 'E': serial.PARITY_EVEN, 'O': serial.PARITY_ODD}
                
                ser = serial.Serial(
                    port=self.port,
                    baudrate=baud,
                    bytesize=bits,
                    parity=parity_map[parity],
                    stopbits=stop,
                    timeout=2
                )
                
                print("  Connected successfully")
                
                # Try to read any existing data
                time.sleep(1)
                if ser.in_waiting > 0:
                    data = ser.read(ser.in_waiting)
                    print("  Found data: {}".format(data))
                
                # Send test command
                ser.write(b'STATUS\r\n')
                ser.flush()
                time.sleep(1)
                
                if ser.in_waiting > 0:
                    response = ser.read(ser.in_waiting)
                    print("  Response: {}".format(response))
                
                ser.close()
                
            except Exception as e:
                print("  Error: {}".format(e))
    
    def run_full_debug(self):
        """Run complete debug sequence"""
        print("INBODY 270 COMPLETE DEBUG TOOL")
        print("=" * 60)
        print("Starting comprehensive troubleshooting...")
        print()
        
        # Test 1: Device settings help
        self.check_device_settings_help()
        input("\nPress Enter after checking device settings...")
        
        # Test 2: Different baudrates
        print("\n")
        result_baud = self.test_all_baudrates()
        if result_baud:
            print("Found working baudrate: {}".format(result_baud))
        
        # Test 3: Different settings
        print("\n")
        self.test_different_settings()
        
        # Test 4: Activation commands
        print("\n")
        if self.test_activation_commands():
            print("Found working activation command!")
            return
        
        # Test 5: Extended monitoring
        print("\n")
        print("No activation commands worked. Starting extended monitoring...")
        input("Press Enter to start 5-minute monitoring (perform measurements during this time)...")
        self.passive_monitor_extended()

def main():
    """Main function"""
    debugger = InBodyDebugger()
    
    try:
        debugger.run_full_debug()
    except KeyboardInterrupt:
        print("\nDebug session stopped by user")
    except Exception as e:
        print("Error during debug: {}".format(e))
    
    print("\nDebug session completed!")
    print("If still no data, please:")
    print("1. Check InBody device manual for 'Open Protocol' setup")
    print("2. Contact InBody support for communication settings")
    print("3. Try with InBody's official software first")

if __name__ == '__main__':
    main()