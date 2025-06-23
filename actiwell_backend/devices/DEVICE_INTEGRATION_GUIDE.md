# Actiwell Device Integration Guide

## Tổng quan

Hệ thống Actiwell IoT Backend đã được cập nhật để hỗ trợ đầy đủ các thiết bị phân tích thành phần cơ thể:

- **Tanita MC-780MA**: Thiết bị phân tích bioelectrical impedance đa tần số với 152+ thông số
- **InBody 270**: Thiết bị phân tích thành phần cơ thể chuyên nghiệp với màn hình cảm ứng

## Kiến trúc hệ thống

### 1. Device Protocols Package (`actiwell_backend/devices/`)

**Cấu trúc thư mục:**
```
devices/
├── __init__.py              # Package initialization
├── base_protocol.py         # Abstract base class cho tất cả devices
├── tanita_protocol.py       # Tanita MC-780MA implementation
└── inbody_protocol.py       # InBody 270 implementation
```

**Tính năng chính:**
- ✅ Abstract base class chuẩn hoá giao tiếp với devices
- ✅ Tanita MC-780MA: Hỗ trợ đầy đủ 152+ parameters theo spec chính thức
- ✅ InBody 270: Hỗ trợ segmental analysis và network communication
- ✅ Automatic error recovery và reconnection
- ✅ Thread-safe communication với background monitoring
- ✅ Comprehensive data validation và quality assessment

### 2. Device Manager (`actiwell_backend/core/device_manager.py`)

**Chức năng:**
- 🔍 **Auto-discovery**: Tự động phát hiện devices kết nối
- 🔗 **Connection management**: Quản lý kết nối nhiều devices
- ⚖️ **Load balancing**: Phân phối measurements giữa các devices
- 📊 **Health monitoring**: Giám sát trạng thái devices liên tục
- 💾 **Database integration**: Tự động lưu measurements vào database

### 3. Core Integration (`actiwell_backend/core/`)

**Components:**
- `__init__.py`: Core package initialization với dependency validation
- `device_communication.py`: Legacy compatibility layer
- Integration với DatabaseManager và ActiwellAPI

## Cách sử dụng

### 1. Kết nối với thiết bị đơn lẻ

#### Tanita MC-780MA
```python
from actiwell_backend.devices import TanitaProtocol

# Tạo kết nối
tanita = TanitaProtocol('/dev/ttyUSB0')

# Kết nối thiết bị
if tanita.connect():
    print("✅ Kết nối thành công với Tanita MC-780MA")
    
    # Đọc measurement (chờ customer thực hiện đo)
    measurement = tanita.read_measurement(timeout=90)
    
    if measurement:
        print(f"📱 Khách hàng: {measurement.customer_phone}")
        print(f"⚖️ Cân nặng: {measurement.weight_kg} kg")
        print(f"🏋️ Body Fat: {measurement.body_fat_percent}%")
        print(f"💪 Muscle Mass: {measurement.muscle_mass_kg} kg")
        print(f"🔥 BMR: {measurement.bmr_kcal} kcal")
        
        # Segmental analysis
        print(f"🦾 Right Arm: {measurement.right_arm_muscle_kg} kg")
        print(f"🦵 Right Leg: {measurement.right_leg_muscle_kg} kg")
        
    tanita.disconnect()
```

#### InBody 270
```python
from actiwell_backend.devices import InBodyProtocol

# Tạo kết nối
inbody = InBodyProtocol('/dev/ttyUSB1')

# Kết nối và bắt đầu measurement
if inbody.connect():
    print("✅ Kết nối thành công với InBody 270")
    
    # Bắt đầu measurement với customer ID
    inbody.start_measurement("0965385123")
    
    # Đọc kết quả
    measurement = inbody.read_measurement(timeout=30)
    
    if measurement:
        print(f"📱 Khách hàng: {measurement.customer_phone}")
        print(f"⚖️ Cân nặng: {measurement.weight_kg} kg")
        print(f"💪 Skeletal Muscle: {measurement.muscle_mass_kg} kg")
        print(f"💧 Total Body Water: {measurement.total_body_water_kg} kg")
        
    inbody.disconnect()
```

### 2. Sử dụng Device Manager (Khuyến nghị)

```python
from actiwell_backend.core import DeviceManager, initialize_core_managers

# Khởi tạo core managers
managers = initialize_core_managers()
device_manager = managers['devices']

# Tự động phát hiện và kết nối devices
device_manager.start_auto_discovery()
device_manager.connect_all_discovered_devices()

# Bắt đầu measurement trên device available
device_id = device_manager.start_measurement("0965385123")

if device_id:
    print(f"✅ Measurement started on {device_id}")
    
    # Lấy kết quả measurement
    measurement = device_manager.get_measurement(timeout=60)
    
    if measurement:
        print("🎉 Measurement completed successfully!")
        # Measurement đã được tự động lưu vào database
else:
    print("❌ No available devices for measurement")

# Xem trạng thái tất cả devices
status = device_manager.get_device_status()
print(f"📊 Connected devices: {status['manager_stats']['connected_devices']}")
```

### 3. Advanced Usage với Callbacks

```python
from actiwell_backend.devices import TanitaProtocol

def on_measurement_received(measurement):
    print(f"🎊 New measurement: {measurement.customer_phone}")
    # Xử lý measurement data
    
def on_device_error(device_id, error):
    print(f"❌ Device error: {device_id} - {error}")
    
def on_status_change(device_id, status):
    print(f"📱 Device status: {device_id} - {status}")

# Setup device với callbacks
tanita = TanitaProtocol('/dev/ttyUSB0')
tanita.set_callbacks(
    measurement_cb=on_measurement_received,
    status_cb=on_status_change,
    error_cb=on_device_error
)

# Kết nối và start monitoring
if tanita.connect():
    tanita.start_monitoring()  # Background thread để monitor
    
    # Device sẽ tự động process measurements khi có
    time.sleep(300)  # Wait for measurements
    
    tanita.stop_monitoring_thread()
    tanita.disconnect()
```

## Tanita MC-780MA Integration

### 1. Đặc điểm kỹ thuật

- **Communication**: RS-232C, USB (FTDI FT232RL)
- **Baudrate**: 9600 bps
- **Data format**: CSV với 152+ parameters
- **Measurement time**: 30-60 giây
- **Output**: Tự động sau khi đo xong

### 2. Data Format

Theo official specification, Tanita MC-780MA xuất dữ liệu dạng CSV:
```
{0,16,~0,1,~1,1,~2,1,MO,"MC-780",ID,"0965385123",St,0,Da,"27/01/2015",TI,"06:36",Bt,0,GE,1,AG,37,Hm,174.0,Pt,1.0,Wk,76.6,FW,18.2,fW,13.9,MW,62.7,mW,59.6,sW,0,bW,3.1,wW,45.0,ww,58.7,wI,26.9,wO,18.1,wo,40.2,MI,25.3...
```

### 3. Parameters được hỗ trợ

**Basic Measurements:**
- Weight (Wk), Height (Hm), BMI (MI)
- Body type (Bt), Gender (GE), Age (AG)

**Body Composition:**
- Body Fat % (FW), Fat Mass (fW)
- Muscle Mass (mW), Bone Mass (bW)
- Total Body Water (wW, ww)
- Visceral Fat Rating (IF)
- Metabolic Age (rA), BMR (rB)

**Segmental Analysis (5 body parts):**
- Right/Left Leg: mR, mL (muscle), FR, FL (fat)
- Right/Left Arm: mr, ml (muscle), Fr, Fl (fat)  
- Trunk: mT (muscle), FT (fat)

**Bioelectrical Impedance (6 frequencies):**
- 1kHz, 5kHz, 50kHz, 250kHz, 500kHz, 1000kHz
- Cho 6 body segments: LL-LA, Right Leg, Left Leg, Right Arm, Left Arm, RL-LL

**Phase Angle (50kHz):**
- Cho tất cả 6 body segments

### 4. Phone Number Extraction

Hệ thống tự động extract số điện thoại từ ID field:
- **Input formats**: 0965385123, 965385123, +84965385123, 84965385123
- **Output format**: 0965385123 (Vietnamese standard)
- **Validation**: Kiểm tra prefix hợp lệ (09, 08, 07, 05, 03, 02)

## InBody 270 Integration

### 1. Đặc điểm kỹ thuật

- **Communication**: RS-232C, USB, LAN, Bluetooth, Wi-Fi
- **Measurement time**: 15 giây
- **Display**: 7-inch TFT LCD touchscreen
- **Data format**: Key-value pairs

### 2. Supported Features

**Body Composition:**
- Skeletal Muscle Mass (SKM)
- Body Fat Mass (BFM)
- Total Body Water (TBW)
- Protein Mass, Mineral Mass
- Visceral Fat Area (VFA)

**Segmental Analysis:**
- Lean Body Mass cho 5 segments
- Detailed muscle distribution

## Testing và Troubleshooting

### 1. Chạy Integration Test

```bash
# Test device discovery
python test_device_integration.py --discover

# Test specific device
python test_device_integration.py --port /dev/ttyUSB0 --device tanita

# Test với timeout tùy chỉnh
python test_device_integration.py --port /dev/ttyUSB0 --timeout 120

# Test device manager
python test_device_integration.py --manager
```

### 2. Common Issues

**Device not detected:**
- Kiểm tra USB cable connection
- Verify device power
- Check user permissions: `sudo usermod -a -G dialout $USER`
- Install FTDI drivers nếu cần

**Communication timeout:**
- **Tanita**: Đảm bảo customer thực hiện đo đầy đủ
- **InBody**: Kiểm tra device settings và network config
- Tăng timeout parameter

**Data validation errors:**
- Kiểm tra phone number format
- Verify measurement completeness
- Check device calibration

### 3. Device Health Monitoring

```python
# Get device status
device_info = device.get_device_info()
print(f"State: {device_info['state']}")
print(f"Error count: {device_info['error_count']}")
print(f"Uptime: {device_info['uptime_seconds']} seconds")

# Check capabilities
capabilities = device_info['capabilities']
if capabilities:
    print(f"Segmental analysis: {capabilities['segmental_analysis']}")
    print(f"Multi-frequency: {capabilities['multi_frequency']}")
```

## Database Integration

### 1. Automatic Storage

Measurements được tự động lưu vào database với đầy đủ thông tin:

```sql
-- Tanita measurements với tất cả parameters
INSERT INTO tanita_measurements (
    device_id, customer_phone, weight_kg, body_fat_percent,
    muscle_mass_kg, bone_mass_kg, total_body_water_kg,
    visceral_fat_rating, metabolic_age, bmr_kcal,
    right_arm_muscle_kg, left_arm_muscle_kg, trunk_muscle_kg,
    right_leg_muscle_kg, left_leg_muscle_kg,
    raw_data, measurement_timestamp
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
```

### 2. Data Validation

Mỗi measurement được validate trước khi lưu:
- Phone number format validation
- Weight/height range checks  
- Body composition reasonableness
- Data completeness assessment

## Production Deployment

### 1. Systemd Service

```bash
# Copy service file
sudo cp scripts/actiwell-device-service.service /etc/systemd/system/

# Enable và start service
sudo systemctl enable actiwell-device-service
sudo systemctl start actiwell-device-service

# Monitor logs
sudo journalctl -u actiwell-device-service -f
```

### 2. Configuration

```env
# Device settings
AUTO_DETECT_DEVICES=True
DEVICE_TIMEOUT=90
TANITA_BAUDRATE=9600
INBODY_BAUDRATE=9600

# Database connection
DB_HOST=localhost
DB_USER=actiwell_user
DB_PASSWORD=secure_password
DB_NAME=actiwell_measurements

# Actiwell API integration
ACTIWELL_API_URL=https://api.actiwell.co
ACTIWELL_API_KEY=your_api_key
ACTIWELL_LOCATION_ID=1
```

### 3. Monitoring và Maintenance

**Health Checks:**
- Device connection status
- Measurement success rate
- Error frequency
- Database connectivity

**Maintenance Tasks:**
- Regular device calibration
- Database cleanup
- Log rotation
- Firmware updates

## Migration từ Legacy System

Nếu đang sử dụng hệ thống cũ, có thể migrate theo steps:

1. **Update imports:**
   ```python
   # Old
   from device_communication import create_tanita_handler
   
   # New  
   from actiwell_backend.devices import TanitaProtocol
   ```

2. **Update device creation:**
   ```python
   # Old
   handler = create_tanita_handler("/dev/ttyUSB0")
   
   # New
   protocol = TanitaProtocol("/dev/ttyUSB0")
   ```

3. **Update measurement handling:**
   ```python
   # Old - dictionary format
   data = handler.read_measurement()
   weight = data["weight_kg"]
   
   # New - object format
   measurement = protocol.read_measurement()
   weight = measurement.weight_kg
   ```

## Kết luận

Hệ thống device integration mới cung cấp:

✅ **Comprehensive data extraction**: Tất cả 152+ parameters từ Tanita MC-780MA
✅ **Professional device support**: InBody 270 với đầy đủ tính năng
✅ **Robust communication**: Error recovery, reconnection, monitoring
✅ **Standardized data format**: Consistent MeasurementData structure
✅ **Production ready**: Systemd service, health monitoring, logging
✅ **Database integration**: Automatic storage với validation
✅ **Actiwell API sync**: Seamless integration với SaaS platform

Hệ thống sẵn sàng cho production deployment và có thể handle multiple devices đồng thời với high reliability.