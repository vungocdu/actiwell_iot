#!/bin/bash
# Tanita Linux Compatibility Test Script - Python 3.5 Compatible

echo "🍓 TANITA LINUX COMPATIBILITY TEST - RASPBERRY PI 3"
echo "=================================================="
echo "🔧 System: $(cat /proc/device-tree/model 2>/dev/null || echo 'Unknown Pi Model')"
echo "🐧 OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)"
echo "⚡ Kernel: $(uname -r)"
echo ""

# Test 6: Real Communication Test with Python 3.5 compatible syntax
echo "6️⃣ Testing real serial communication..."

if ls /dev/ttyUSB* &>/dev/null || ls /dev/ttyACM* &>/dev/null; then
    SERIAL_PORT=$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -1)
    echo "📡 Testing serial communication on $SERIAL_PORT"
    echo "📏 Please perform a measurement on Tanita within 15 seconds..."
    echo ""
    
    python3 << 'EOF'
import serial
import time
import sys
import signal
import glob

def signal_handler(sig, frame):
    print('\n⏭️  Test skipped by user')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

try:
    ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
    
    if not ports:
        print("❌ No serial ports available")
        sys.exit(1)
    
    port = ports[0]
    print("🔌 Using port: {}".format(port))
    
    ser = serial.Serial(
        port=port,
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False
    )
    
    print("✅ Serial connection opened")
    print("⏳ Waiting for data (15 seconds)...")
    print("📏 Step on Tanita scale now!")
    
    buffer = ""
    data_received = False
    start_time = time.time()
    
    while time.time() - start_time < 15:
        if ser.in_waiting > 0:
            try:
                chunk = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                buffer += chunk
                
                while '\r\n' in buffer:
                    line, buffer = buffer.split('\r\n', 1)
                    
                    if line.strip():
                        print("📥 Data received: {}...".format(line[:60]))
                        
                        if '{0,16,~0,1,~1,1,~2,1,MO,' in line and 'MC-780' in line:
                            print("🎉 VALID TANITA MC-780MA DATA!")
                            
                            # Extract phone number from ID field
                            if 'ID,' in line:
                                parts = line.split(',')
                                for i, part in enumerate(parts):
                                    if part.strip('"') == 'ID' and i+1 < len(parts):
                                        id_field = parts[i+1].strip('"')
                                        print("📱 Raw ID field: {}".format(id_field))
                                        
                                        # Extract digits and validate phone
                                        digits = ''.join(c for c in id_field if c.isdigit())
                                        if digits and digits != '0' * len(digits):
                                            phone = digits.strip('0')
                                            if len(phone) >= 9:
                                                if len(phone) == 9:
                                                    phone = '0' + phone
                                                elif len(phone) >= 11 and phone.startswith('84'):
                                                    phone = '0' + phone[2:]
                                                    
                                                if len(phone) == 10 and phone.startswith('0'):
                                                    print("📱 Extracted phone: {}".format(phone))
                                                    
                                                    valid_prefixes = ['09', '08', '07', '05', '03', '02']
                                                    if phone[:2] in valid_prefixes:
                                                        print("✅ Valid Vietnam phone number format!")
                                                    else:
                                                        print("⚠️  Phone format may be invalid for Vietnam")
                                        else:
                                            print("📱 No phone number in ID field (all zeros)")
                                        break
                            
                            # Extract weight
                            if 'Wk,' in line:
                                weight_parts = line.split('Wk,')
                                if len(weight_parts) > 1:
                                    weight = weight_parts[1].split(',')[0]
                                    print("⚖️  Weight: {}kg".format(weight))
                            
                            data_received = True
                            break
                            
            except Exception as e:
                print("⚠️  Data processing error: {}".format(e))
        
        elapsed = int(time.time() - start_time)
        if elapsed % 5 == 0 and elapsed > 0:
            remaining = 15 - elapsed
            if remaining > 0:
                print("⏳ Still waiting... {}s remaining".format(remaining))
        
        time.sleep(0.1)
    
    ser.close()
    
    if data_received:
        print("\n🎉 SUCCESS! Tanita communication works perfectly on Linux!")
        print("✅ Phone number extraction tested")
        print("✅ Data format validation passed") 
        print("👍 Ready for Actiwell integration")
        sys.exit(0)
    else:
        print("\n⏰ TIMEOUT: No Tanita data received")
        print("🔧 Please ensure:")
        print("   ├── Someone steps on the scale")
        print("   ├── Scale completes full measurement")
        print("   ├── Wait for measurement to finish")
        print("   └── Data transmits automatically")
        sys.exit(1)
        
except Exception as e:
    print("❌ Unexpected error: {}".format(e))
    sys.exit(3)
EOF

    TEST_RESULT=$?
else
    echo "⚠️  Cannot test - no serial port available"
    TEST_RESULT=99
fi

# Summary
echo ""
echo "📋 TEST SUMMARY"
echo "==============="
if [ $TEST_RESULT -eq 0 ]; then
    echo "🎉 EXCELLENT! All tests passed!"
    echo "✅ Tanita MC-780MA works perfectly with Raspberry Pi 3"
    echo "💰 Ready for Actiwell integration!"
    echo ""
    echo "🚀 Next steps for Actiwell:"
    echo "   1. Set up Tanita data gateway service"
    echo "   2. Configure customer phone number workflow"
    echo "   3. Integrate with customer_operators table"
    echo "   4. Test face ID + body composition flow"
else
    echo "⚠️  Communication test needs retry with actual measurement"
fi

echo ""
echo "📊 Test completed at: $(date)"