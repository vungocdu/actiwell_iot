# Hướng dẫn kiểm tra kết nối với máy InBody

## 🎯 Mục tiêu
Hướng dẫn step-by-step để kiểm tra và thiết lập kết nối với máy InBody 270, từ hardware setup đến software integration.

## 📋 Checklist trước khi bắt đầu

### Hardware Requirements
- [ ] Máy InBody 270 đã được cắm điện và bật
- [ ] Cable kết nối (USB hoặc RS-232C)
- [ ] Máy tính/Raspberry Pi có port tương ứng
- [ ] InBody device đã hoàn thành self-test và sẵn sàng

### Software Requirements  
- [ ] Python 3.7+ đã cài đặt
- [ ] pyserial library (`pip install pyserial`)
- [ ] User account có quyền truy cập serial ports

## 🔧 Bước 1: Kiểm tra Hardware Connection

### 1.1 Kiểm tra InBody Device
```bash
# Kiểm tra device có power không
# - Màn hình LCD có sáng không
# - Device có hiển thị "Ready" hoặc home screen không
# - Test bằng cách step lên scale xem có phản ứng không
```

### 1.2 Kiểm tra Cable Connection
**USB Connection:**
- Cắm USB cable từ InBody vào máy tính
- InBody 270 có USB Type-B port ở phía sau device

**RS-232C Connection:**
- Sử dụng straight cable (không phải null modem)
- Connect vào RS-232C port ở phía sau device

### 1.3 Kiểm tra System Detection
```bash
# Linux: Check USB devices
lsusb
dmesg | tail -20

# Check serial ports
ls -la /dev/ttyUSB* /dev/ttyACM* 2>/dev/null

# Windows: Check Device Manager
# Tìm "Ports (COM & LPT)" section
```

## 🧪 Bước 2: Chạy Connection Test

### 2.1 Sử dụng Test Script
```bash
# Download và chạy test script
python test_inbody_connection.py

# Hoặc test port cụ thể
python test_inbody_connection.py --port /dev/ttyUSB0

# Chỉ scan ports
python test_inbody_connection.py --scan
```

### 2.2 Expected Output
```
🏥 INBODY CONNECTION TEST - COMPREHENSIVE CHECK
=======================================================

1️⃣ HARDWARE DETECTION
-------------------------
✅ Found 1 serial port(s):
   1. /dev/ttyUSB0

🎯 Testing port: /dev/ttyUSB0

2️⃣ PORT ACCESS TEST
--------------------
   📡 Port /dev/ttyUSB0 opened successfully
   ⚙️ Settings: 9600-8-N-1
✅ Port access successful

3️⃣ BASIC COMMUNICATION TEST
----------------------------
   📡 Connected to /dev/ttyUSB0
   🔄 Buffers cleared
   📭 No immediate data (normal)
✅ Basic communication successful
```

## 🔍 Bước 3: Manual Communication Test

### 3.1 Simple Serial Test
```python
import serial
import time

# Thay '/dev/ttyUSB0' bằng port thực tế của bạn
port = '/dev/ttyUSB0'

try:
    # Mở connection
    ser = serial.Serial(
        port=port,
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=2.0
    )
    
    print(f"✅ Connected to {port}")
    print("📏 Perform measurement on InBody...")
    print("⏰ Waiting for data (30 seconds)...")
    
    start_time = time.time()
    while time.time() - start_time < 30:
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting)
            print(f"📥 Data received: {data}")
            break
        time.sleep(0.5)
    else:
        print("⏰ No data received")
    
    ser.close()
    print("✅ Test completed")
    
except Exception as e:
    print(f"❌ Error: {e}")
```

### 3.2 InBody Protocol Test
```python
# Test với InBody protocol class
from actiwell_backend.devices import InBodyProtocol

inbody = InBodyProtocol('/dev/ttyUSB0')

if inbody.connect():
    print("✅ InBody connected")
    
    # Get device info
    info = inbody.get_device_info()
    print(f"📋 Device: {info['model']}")
    print(f"📋 State: {info['state']}")
    
    # Test measurement
    print("📏 Please perform measurement...")
    measurement = inbody.read_measurement(timeout=30)
    
    if measurement:
        print("🎉 Measurement successful!")
        print(f"Customer: {measurement.customer_phone}")
        print(f"Weight: {measurement.weight_kg} kg")
        print(f"Body Fat: {measurement.body_fat_percent}%")
    
    inbody.disconnect()
else:
    print("❌ Connection failed")
```

## 🔧 Bước 4: Troubleshooting

### 4.1 Port Access Issues
**Lỗi: Permission Denied**
```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER

# Logout và login lại, hoặc:
newgrp dialout

# Hoặc temporary fix:
sudo chmod 666 /dev/ttyUSB0
```

**Lỗi: Port not found**
```bash
# Check USB connection
lsusb | grep -i inbody

# Check dmesg for USB events
dmesg | tail -20 | grep -i usb

# Try different USB port
# Check cable integrity
```

### 4.2 Communication Issues
**Không nhận được data:**

1. **Check InBody Settings:**
   - Vào Settings menu trên InBody
   - Kiểm tra Output/Communication settings
   - Enable data output nếu cần

2. **Check Connection Parameters:**
   ```python
   # Try different baudrates
   baudrates = [9600, 19200, 38400, 57600, 115200]
   for baud in baudrates:
       try:
           ser = serial.Serial('/dev/ttyUSB0', baud, timeout=1)
           print(f"Testing {baud}...")
           # Test communication
       except:
           continue
   ```

3. **Check Data Format:**
   - InBody có thể output data ở nhiều format khác nhau
   - Kiểm tra manual để config đúng format

### 4.3 InBody Device Settings

**Truy cập InBody Settings:**
1. Trên màn hình InBody, touch Settings icon
2. Tìm "Communication" hoặc "Data Output" section
3. Enable các options:
   - Auto Send Data: ON
   - Output Format: Detailed hoặc Standard
   - Connection Type: RS-232C hoặc USB

**Reset Communication:**
1. Power off InBody device
2. Disconnect cable
3. Wait 10 seconds
4. Reconnect cable
5. Power on device
6. Wait for full initialization

## 📊 Bước 5: Verify Data Reception

### 5.1 Measurement Test
1. **Prepare InBody:**
   - Device hiển thị home screen
   - "Ready" indicator visible

2. **Start Measurement:**
   - Enter customer ID (phone number)
   - Step on scale barefoot
   - Hold handholds properly
   - Stay still during measurement

3. **Monitor Data:**
   ```bash
   # Chạy monitoring script
   python test_inbody_connection.py --port /dev/ttyUSB0
   
   # Trong quá trình đo, sẽ thấy:
   # 📥 Data received: 128 bytes
   # 📄 Content preview: ID:0965385123,Weight:65.2kg,BMI:22.1...
   ```

### 5.2 Data Format Examples

**InBody Standard Output:**
```
ID:0965385123
Weight:65.2kg
Height:165.0cm
BMI:22.1
BodyFat:18.5%
MuscleMass:28.4kg
TBW:38.2L
VFA:45cm²
```

**InBody Detailed Output:**
```
ID:0965385123,Weight:65.2,Height:165.0,BMI:22.1,BodyFat:18.5,SKM:28.4,BFM:12.1,TBW:38.2,Protein:10.2,Mineral:3.1,VFA:45,RAL:2.8,LAL:2.9,TRL:15.2,RLL:8.1,LLL:8.0
```

## ✅ Bước 6: Integration Test

### 6.1 Full Integration Test
```python
from actiwell_backend.core import DeviceManager

# Initialize device manager
manager = DeviceManager()

# Discover devices
discovered = manager.discover_devices()
print(f"Found {len(discovered)} devices")

# Connect to InBody
for port, device_info in discovered.items():
    if device_info.device_type == 'inbody_270':
        success = manager.connect_device(port, 'inbody_270')
        print(f"InBody connection: {'✅' if success else '❌'}")

# Test measurement
device_id = manager.start_measurement("0965385123")
if device_id:
    measurement = manager.get_measurement(timeout=30)
    if measurement:
        print("🎉 Full integration successful!")
```

### 6.2 Production Readiness Check
```bash
# Test multiple measurements
for i in {1..5}; do
    echo "Test $i:"
    python test_inbody_connection.py --port /dev/ttyUSB0 --protocol
    sleep 10
done

# Check error rate và stability
# Monitor memory usage
# Verify data consistency
```

## 📝 Common InBody 270 Specifications

**Communication Settings:**
- Baudrate: 9600 bps (default)
- Data bits: 8
- Parity: None  
- Stop bits: 1
- Flow control: None

**Measurement Time:** 15 seconds

**Data Output:** Automatic after measurement completion

**Connection Types:**
- RS-232C (9-pin D-sub)
- USB (Type-B)
- LAN (Ethernet)
- Bluetooth (optional)
- Wi-Fi (optional)

## 🎯 Expected Results

### Successful Connection:
```
📋 TEST SUMMARY
===============
Total Tests: 5
Passed: 5
Failed: 0
Success Rate: 100.0%

✅ PASS Hardware Check
✅ PASS Port Access  
✅ PASS Basic Communication
✅ PASS Command Response
✅ PASS Data Reception

🎉 CONNECTION SUCCESSFUL!
✅ InBody device is properly connected and communicating
```

### Next Steps after Success:
1. ✅ Device connection verified
2. ✅ Data reception working
3. ✅ Integration với Actiwell system
4. ✅ Ready for production use

Nếu gặp vấn đề ở bất kỳ bước nào, tham khảo troubleshooting section và kiểm tra lại hardware setup.