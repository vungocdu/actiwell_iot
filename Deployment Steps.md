# 🔄 HƯỚNG DẪN MIGRATION VÀ SETUP HỆ THỐNG

## 1. 📁 CẬP NHẬT CẤU TRÚC FILE

### Bước 1: Tạo cấu trúc thư mục mới
```bash
cd /opt/actiwell_iot

# Tạo thư mục mới
mkdir -p actiwell_backend/{core,services,api,static/{css,js,images},templates}
mkdir -p logs data scripts tests

# Di chuyển và đổi tên files
mv requirement.txt requirements.txt
mv db.sql setup_database.sql
mv test_scripts/* scripts/
```

### Bước 2: Di chuyển và tổ chức lại code
```bash
# Di chuyển config vào package
mv config.py actiwell_backend/

# Gộp device communication vào device manager
cat device_communication.py >> actiwell_backend/core/device_manager.py

# Di chuyển files vào core
mv database_manager.py actiwell_backend/core/
mv device_manager.py actiwell_backend/core/
mv actiwell_backend/actiwell_api.py actiwell_backend/core/

# Files API đã ở đúng chỗ rồi (actiwell_backend/api/)

# Loại bỏ files không cần thiết
rm -f api_endpoints.py customer_health_profile.py claude_step.txt
```

### Bước 3: Cập nhật file __init__.py cho package
```python
# actiwell_backend/__init__.py
"""
Actiwell IoT Backend Package
Body Composition Gateway for Medical Devices
"""

__version__ = "2.0.0"
__author__ = "Actiwell Development Team"

from flask import Flask
from flask_cors import CORS

def create_app(config_object=None):
    """
    Application factory pattern
    Tạo và cấu hình Flask app instance
    """
    app = Flask(__name__)
    
    if config_object:
        app.config.from_object(config_object)
    
    # Initialize CORS
    CORS(app)
    
    return app
```

### Bước 4: Cập nhật requirements.txt
```txt
Flask==2.3.3
Flask-CORS==4.0.0
mysql-connector-python==8.1.0
pyserial==3.5
requests==2.31.0
PyJWT==2.8.0
python-dotenv==1.0.0
psutil==5.9.5
gunicorn==21.2.0
supervisor==4.2.5
```

## 2. 🔧 CẬP NHẬT CẤU HÌNH

### Cập nhật file .env
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

## 3. 🐍 CÀI ĐẶT VÀ CHẠY

### Bước 1: Cài đặt dependencies
```bash
cd /opt/actiwell_iot

# Kích hoạt virtual environment
source venv/bin/activate

# Cài đặt packages mới
pip install --upgrade pip
pip install -r requirements.txt

# Thoát virtual environment
deactivate
```

### Bước 2: Cập nhật database schema
```bash
# Import schema mới nếu cần
sudo mysql -u actiwell_user -p actiwell_measurements < setup_database.sql
```

### Bước 3: Test chạy thử
```bash
cd /opt/actiwell_iot

# Chạy với user actiwell
sudo -u actiwell /opt/actiwell_iot/venv/bin/python run.py
```

### Bước 4: Cập nhật systemd service
```bash
sudo nano /etc/systemd/system/actiwell-backend.service
```

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
ReadWritePaths=/opt/actiwell_iot /var/log/actiwell

[Install]
WantedBy=multi-user.target
```

### Bước 5: Khởi động service
```bash
# Reload systemd
sudo systemctl daemon-reload

# Start service
sudo systemctl start actiwell-backend.service

# Check status
sudo systemctl status actiwell-backend.service

# Enable auto-start
sudo systemctl enable actiwell-backend.service
```

## 4. 🧪 KIỂM TRA HỆ THỐNG

### Test endpoints:
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

### Monitor logs:
```bash
# System logs
sudo journalctl -u actiwell-backend.service -f

# Application logs
tail -f /var/log/actiwell/actiwell_backend.log

# Error logs only
sudo journalctl -u actiwell-backend.service -p err
```

## 5. 🔧 TROUBLESHOOTING

### Lỗi import modules:
```bash
# Kiểm tra PYTHONPATH
echo $PYTHONPATH

# Kiểm tra structure
ls -la actiwell_backend/
ls -la actiwell_backend/core/
ls -la actiwell_backend/api/
```

### Lỗi database connection:
```bash
# Test MySQL connection
mysql -u actiwell_user -p actiwell_measurements -e "SELECT 1;"

# Check MySQL service
sudo systemctl status mariadb
```

### Lỗi device connection:
```bash
# Check USB devices
lsusb | grep -i ftdi

# Check permissions
ls -l /dev/ttyUSB*
groups actiwell

# Test serial ports
sudo apt install minicom
minicom -D /dev/ttyUSB0 -b 9600
```

### Performance monitoring:
```bash
# Check CPU/Memory usage
htop

# Check disk space
df -h

# Check service resource usage
sudo systemctl status actiwell-backend.service
```

## 6. 📊 FEATURES MỚI TRONG VERSION 2.0

1. **Improved Architecture**: Package-based structure, separation of concerns
2. **Better Error Handling**: Comprehensive logging và error recovery
3. **Background Services**: Async processing for measurements và sync
4. **Health Monitoring**: System health checks và alerts
5. **Graceful Shutdown**: Clean shutdown of all services
6. **Production Ready**: Security settings, resource protection
7. **Enhanced API**: More robust REST endpoints
8. **Device Management**: Better device detection và connection handling

## 7. 🚀 NEXT STEPS

1. **Monitor**: Theo dõi logs và performance trong 24h đầu
2. **Configure**: Update Actiwell API credentials
3. **Test**: Thử nghiệm với thiết bị Tanita/InBody thực tế
4. **Backup**: Setup backup cho database và config files
5. **Security**: Review và cập nhật passwords, API keys
6. **Documentation**: Cập nhật documentation cho team