# Actiwell IoT Backend - Hệ thống Gateway cho Thiết bị Đo Thành phần Cơ thể

## 📋 Tổng quan

Hệ thống Actiwell IoT Backend là một gateway thông minh để tích hợp các thiết bị đo thành phần cơ thể (Tanita MC-780MA, InBody 270) với nền tảng SaaS Actiwell. Hệ thống được thiết kế theo kiến trúc package và sử dụng Application Factory pattern để đảm bảo tính ổn định và khả năng mở rộng.

## 🏗️ Kiến trúc Hệ thống

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Tanita/InBody │────│  Raspberry Pi   │────│  Actiwell SaaS  │
│     Devices     │USB │   IoT Gateway   │API │    Platform     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Cấu trúc Thư mục

```
actiwell_iot/
├── .env                          # Environment variables
├── .gitignore                    # Git ignore patterns
├── requirements.txt              # Python dependencies
├── run.py                       # Application entry point
├── config.py                    # Configuration settings
├── setup_database.sql           # Database schema
├── README.md                    # This documentation
├── Deployment Steps.md          # Migration guide
│
├── actiwell_backend/            # Main application package
│   ├── __init__.py             # Package initialization + App Factory
│   ├── models.py               # Data models
│   │
│   ├── core/                   # Core business logic
│   │   ├── __init__.py
│   │   ├── database_manager.py # Database operations
│   │   ├── device_manager.py   # Device management
│   │   ├── device_communication.py # Device protocols
│   │   └── actiwell_api.py     # Actiwell integration
│   │
│   ├── api/                    # REST API endpoints
│   │   ├── __init__.py
│   │   ├── auth_routes.py      # Authentication
│   │   ├── device_routes.py    # Device management
│   │   ├── measurement_routes.py # Measurements
│   │   ├── sync_routes.py      # Data synchronization
│   │   └── system_routes.py    # System monitoring
│   │
│   ├── services/               # Business services
│   │   ├── __init__.py
│   │   ├── measurement_service.py
│   │   ├── sync_service.py
│   │   └── health_service.py
│   │
│   ├── static/                 # Web assets
│   │   ├── css/
│   │   ├── js/
│   │   └── images/
│   │
│   └── templates/              # HTML templates
│       ├── base.html
│       ├── dashboard.html
│       ├── error.html
│       └── initializing.html
│
├── data/                       # Data storage
├── logs/                       # Log files
├── scripts/                    # Utility scripts
│   ├── installation.sh
│   ├── enhanced_tanita_test.sh
│   ├── system_test_script.sh
│   └── tanita_production_setup.sh
│
└── tests/                      # Unit tests
    ├── __init__.py
    ├── test_api.py
    ├── test_database.py
    └── test_device_manager.py
```

## 🚀 Hướng dẫn Cài đặt Nhanh

### Bước 1: Chuẩn bị môi trường

```bash
# Cập nhật hệ thống
sudo apt update && sudo apt full-upgrade -y

# Cài đặt các gói cần thiết
sudo apt install -y python3 python3-pip python3-venv mariadb-server usbutils git

# Tạo thư mục dự án
sudo mkdir -p /opt/actiwell_iot
cd /opt/actiwell_iot

# Tạo user riêng cho ứng dụng
sudo useradd -r -s /bin/false -d /opt/actiwell_iot actiwell
sudo chown -R actiwell:actiwell /opt/actiwell_iot
```

### Bước 2: Clone và cấu hình mã nguồn

```bash
# Clone repository (hoặc copy files)
git clone <your-repository-url> .

# Hoặc copy files theo cấu trúc đã mô tả

# Set quyền
sudo chown -R actiwell:actiwell /opt/actiwell_iot
```

### Bước 3: Thiết lập môi trường Python

```bash
cd /opt/actiwell_iot

# Tạo virtual environment
sudo -u actiwell python3 -m venv venv

# Kích hoạt và cài đặt dependencies
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

### Bước 4: Cấu hình Database

```bash
# Bảo mật MariaDB
sudo mysql_secure_installation

# Tạo database và user
sudo mysql -u root -p << 'EOF'
CREATE DATABASE actiwell_measurements CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'actiwell_user'@'localhost' IDENTIFIED BY 'your_secure_password_here';
GRANT ALL PRIVILEGES ON actiwell_measurements.* TO 'actiwell_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
EOF

# Import schema
sudo mysql -u actiwell_user -p actiwell_measurements < setup_database.sql
```

### Bước 5: Cấu hình Environment

```bash
# Tạo file .env
sudo nano /opt/actiwell_iot/.env
```

Nội dung file `.env`:

```env
# Database Configuration
DB_HOST=localhost
DB_USER=actiwell_user
DB_PASSWORD=your_secure_password_here
DB_NAME=actiwell_measurements
DB_POOL_SIZE=5

# Actiwell API Configuration
ACTIWELL_API_URL=https://api.actiwell.com
ACTIWELL_API_KEY=your_api_key_here
ACTIWELL_LOCATION_ID=1

# Application Configuration
SECRET_KEY=your_very_long_and_random_secret_key_here
JWT_EXPIRE_HOURS=24
WEB_PORT=5000
WEB_HOST=0.0.0.0
FLASK_ENV=production
FLASK_DEBUG=False

# Device Configuration
AUTO_DETECT_DEVICES=True
DEVICE_TIMEOUT=5
TANITA_BAUDRATE=9600
INBODY_BAUDRATE=9600

# Storage Configuration
DATA_STORAGE_PATH=/opt/actiwell_iot/data
LOG_STORAGE_PATH=/opt/actiwell_iot/logs
```

```bash
# Set quyền cho file .env
sudo chown actiwell:actiwell /opt/actiwell_iot/.env
sudo chmod 600 /opt/actiwell_iot/.env
```

### Bước 6: Cấu hình USB Permissions

```bash
# Thêm user vào dialout group
sudo usermod -a -G dialout actiwell

# Tạo udev rules
sudo tee /etc/udev/rules.d/99-actiwell-devices.rules > /dev/null << 'EOF'
# Grant access to USB-to-Serial devices
SUBSYSTEM=="tty", KERNEL=="ttyUSB[0-9]*", MODE="0666", GROUP="dialout"
SUBSYSTEM=="tty", KERNEL=="ttyACM[0-9]*", MODE="0666", GROUP="dialout"
EOF

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Bước 7: Tạo systemd Service

```bash
sudo nano /etc/systemd/system/actiwell-backend.service
```

Nội dung service file:

```ini
[Unit]
Description=Actiwell Body Measurement Backend v2.0
After=network.target mariadb.service
Wants=mariadb.service

[Service]
Type=simple
User=actiwell
Group=actiwell
WorkingDirectory=/opt/actiwell_iot
ExecStart=/opt/actiwell_iot/venv/bin/python run.py
Restart=on-failure
RestartSec=10
Environment="PYTHONPATH=/opt/actiwell_iot"

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/actiwell_iot /var/log

[Install]
WantedBy=multi-user.target
```

### Bước 8: Khởi động hệ thống

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start
sudo systemctl enable actiwell-backend.service

# Start service
sudo systemctl start actiwell-backend.service

# Check status
sudo systemctl status actiwell-backend.service
```

## 🧪 Kiểm tra và Test

### Test Manual

```bash
cd /opt/actiwell_iot

# Test chạy thử
sudo -u actiwell /opt/actiwell_iot/venv/bin/python run.py
```

### Test Endpoints

```bash
# Health check
curl http://localhost:5000/health

# Login để lấy token
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"actiwell123"}'

# Check device status (cần token)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:5000/api/devices/status
```

### Test Thiết bị Tanita

```bash
# Chạy script test Tanita
cd /opt/actiwell_iot/scripts
chmod +x enhanced_tanita_test.sh
./enhanced_tanita_test.sh
```

## 📊 Tính năng Chính

### 🔌 Hỗ trợ Thiết bị
- **Tanita MC-780MA**: Phân tích thành phần cơ thể chuyên nghiệp với 152+ thông số
- **InBody 270**: Thiết bị đo thành phần cơ thể đa tần số
- **Auto-detection**: Tự động phát hiện và kết nối thiết bị qua USB

### 📡 API Integration
- **RESTful API**: Endpoints đầy đủ cho quản lý thiết bị và đo lường
- **Actiwell Sync**: Đồng bộ tự động với nền tảng SaaS Actiwell
- **Real-time**: WebSocket cho cập nhật trạng thái theo thời gian thực

### 🗄️ Quản lý Dữ liệu
- **Database**: MariaDB với schema tối ưu cho Raspberry Pi
- **Backup**: Tự động backup và rotation logs
- **Analytics**: Phân tích xu hướng và báo cáo sức khỏe

### 🔐 Bảo mật
- **JWT Authentication**: Xác thực token an toàn
- **User Isolation**: Chạy dưới user riêng biệt
- **Environment Security**: Bảo vệ thông tin nhạy cảm

## 🌐 Truy cập Hệ thống

- **Web Dashboard**: `http://<raspberry-pi-ip>:5000`
- **API Health Check**: `http://<raspberry-pi-ip>:5000/health`
- **Login mặc định**:
  - Username: `admin`
  - Password: `actiwell123`

## 🔧 Monitoring và Maintenance

### Logs

```bash
# System logs
sudo journalctl -u actiwell-backend.service -f

# Application logs
tail -f /opt/actiwell_iot/logs/actiwell_backend.log

# Error logs only
sudo journalctl -u actiwell-backend.service -p err
```

### Service Management

```bash
# Start service
sudo systemctl start actiwell-backend.service

# Stop service
sudo systemctl stop actiwell-backend.service

# Restart service
sudo systemctl restart actiwell-backend.service

# Check status
sudo systemctl status actiwell-backend.service
```

### System Health

```bash
# Run system test
cd /opt/actiwell_iot/scripts
./system_test_script.sh

# Check USB devices
lsusb | grep -i ftdi

# Check serial ports
ls -la /dev/ttyUSB* /dev/ttyACM*
```

## 🚨 Troubleshooting

### Lỗi thường gặp

1. **ImportError: No module named 'config'**
   ```bash
   # Kiểm tra PYTHONPATH trong service file
   sudo nano /etc/systemd/system/actiwell-backend.service
   # Đảm bảo có: Environment="PYTHONPATH=/opt/actiwell_iot"
   ```

2. **Device connection failed**
   ```bash
   # Kiểm tra permissions
   groups actiwell  # Phải có 'dialout'
   ls -l /dev/ttyUSB*  # Kiểm tra quyền truy cập
   ```

3. **Database connection error**
   ```bash
   # Test MySQL connection
   mysql -u actiwell_user -p actiwell_measurements -e "SELECT 1;"
   ```

4. **Service won't start**
   ```bash
   # Check detailed logs
   sudo journalctl -u actiwell-backend.service --no-pager -n 50
   ```

### Performance Issues

```bash
# Check resource usage
htop

# Check disk space
df -h

# Check memory usage
free -h
```

## 📱 Tích hợp Tanita MC-780MA

### Data Flow

```
Customer → Phone Number ID → Tanita Measurement → Gateway Processing → Actiwell API
```

### Quy trình Đo lường

1. **Nhập số điện thoại** khách hàng làm ID trên thiết bị Tanita
2. **Thực hiện đo lường** hoàn chỉnh (30-60 giây)
3. **Dữ liệu tự động truyền** qua USB đến Gateway
4. **Xử lý và đồng bộ** với database Actiwell

### Dữ liệu Trích xuất

- ✅ **152+ thông số** từ Tanita MC-780MA
- ✅ **Phân tích từng vùng cơ thể** (5 phần: 2 tay, 2 chân, thân)
- ✅ **Dữ liệu bioelectrical impedance** (6 tần số × 6 vùng)
- ✅ **Phase angle measurements** cho 6 vùng cơ thể
- ✅ **Chỉ số chuyển hóa** và tuổi chuyển hóa
- ✅ **Điểm số đánh giá** cơ bắp và BMR

## 🔄 Migration từ Version 1.x

Nếu bạn đang sử dụng phiên bản cũ, tham khảo file `Deployment Steps.md` để có hướng dẫn chi tiết về migration.

## 📚 Documentation

- `Deployment Steps.md`: Hướng dẫn migration chi tiết
- `scripts/`: Các script tiện ích và testing
- `tests/`: Unit tests và integration tests
- API Documentation: Truy cập `/api/docs` khi service đang chạy

## 🤝 Support

- **GitHub Issues**: Báo cáo bugs và feature requests
- **Documentation**: Wiki và README files
- **Logs**: Luôn kiểm tra logs khi gặp vấn đề

## 📋 Requirements

- **Hardware**: Raspberry Pi 3+ hoặc tương đương
- **OS**: Raspbian/Ubuntu 20.04+
- **Memory**: Tối thiểu 1GB RAM
- **Storage**: Tối thiểu 8GB SD card
- **Network**: Kết nối internet để sync với Actiwell

## 🎯 Roadmap

- [ ] Hỗ trợ thêm thiết bị (Omron, Seca)
- [ ] Mobile app companion
- [ ] Advanced analytics và AI insights
- [ ] Cloud deployment options
- [ ] Multi-tenant support

---

**Actiwell IoT Backend v2.0** - Professional body composition gateway for healthcare and fitness industry.