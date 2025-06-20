# Hướng dẫn cài đặt Body Composition Gateway trên Raspberry Pi

## Bước 1: Chuẩn bị Raspberry Pi

### 1.1 Yêu cầu hệ thống
- Raspberry Pi 3B+ hoặc mới hơn
- MicroSD card 32GB (Class 10)
- Raspberry Pi OS (64-bit recommended)
- Kết nối internet

### 1.2 Cài đặt Raspberry Pi OS
```bash
# Cập nhật hệ thống
sudo apt update && sudo apt upgrade -y

# Cài đặt các gói cần thiết
sudo apt install -y git curl wget nano htop
```

## Bước 2: Cài đặt MySQL Server

### 2.1 Cài đặt MySQL
```bash
# Cài đặt MySQL Server
sudo apt install -y mysql-server

# Khởi động và enable MySQL
sudo systemctl start mysql
sudo systemctl enable mysql

# Kiểm tra trạng thái
sudo systemctl status mysql
```

### 2.2 Bảo mật MySQL
```bash
# Chạy script bảo mật MySQL
sudo mysql_secure_installation

# Trả lời các câu hỏi:
# - Set root password: Y (đặt mật khẩu mạnh)
# - Remove anonymous users: Y
# - Disallow root login remotely: Y
# - Remove test database: Y
# - Reload privilege tables: Y
```

### 2.3 Tạo database và user cho ứng dụng
```bash
# Đăng nhập MySQL với quyền root
sudo mysql -u root -p

# Tạo database
CREATE DATABASE body_composition_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# Tạo user cho ứng dụng
CREATE USER 'body_comp_user'@'localhost' IDENTIFIED BY 'your_secure_password';

# Cấp quyền
GRANT ALL PRIVILEGES ON body_composition_db.* TO 'body_comp_user'@'localhost';
FLUSH PRIVILEGES;

# Thoát MySQL
EXIT;
```

### 2.4 Tối ưu MySQL cho Raspberry Pi
```bash
# Chỉnh sửa cấu hình MySQL
sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf

# Thêm các dòng sau vào cuối file:
[mysqld]
# Tối ưu cho Raspberry Pi
innodb_buffer_pool_size = 128M
innodb_log_file_size = 32M
max_connections = 50
query_cache_type = 1
query_cache_size = 16M
tmp_table_size = 16M
max_heap_table_size = 16M

# Khởi động lại MySQL
sudo systemctl restart mysql
```

## Bước 3: Cài đặt Python Environment

### 3.1 Cài đặt Python và pip
```bash
# Cài đặt Python 3 và các gói liên quan
sudo apt install -y python3 python3-pip python3-venv python3-dev

# Cài đặt các thư viện hệ thống cần thiết
sudo apt install -y build-essential libssl-dev libffi-dev libjpeg-dev libpng-dev
```

### 3.2 Tạo thư mục ứng dụng
```bash
# Tạo thư mục cho ứng dụng
sudo mkdir -p /opt/body-composition-gateway
sudo chown pi:pi /opt/body-composition-gateway
cd /opt/body-composition-gateway

# Tạo virtual environment
python3 -m venv venv
source venv/bin/activate

# Cài đặt các package Python cần thiết
pip install --upgrade pip setuptools wheel
```

### 3.3 Cài đặt các thư viện Python
```bash
# Tạo file requirements.txt
cat > requirements.txt << 'EOF'
Flask==2.3.3
Flask-CORS==4.0.0
Flask-SocketIO==5.3.6
mysql-connector-python==8.1.0
pyserial==3.5
requests==2.31.0
PyYAML==6.0.1
python-socketio==5.8.0
eventlet==0.33.3
psutil==5.9.5
schedule==1.2.0
python-dotenv==1.0.0
EOF

# Cài đặt các package
pip install -r requirements.txt
```

## Bước 4: Tạo ứng dụng Web Server

### 4.1 Tạo file cấu hình
```bash
# Tạo file cấu hình
cat > config.yaml << 'EOF'
database:
  host: "localhost"
  port: 3306
  username: "body_comp_user"
  password: "your_secure_password"
  database: "body_composition_db"

web:
  host: "0.0.0.0"
  port: 5000
  debug: false

device:
  auto_detect: true
  scan_ports: ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0", "/dev/ttyACM1"]
  baudrate: 9600

actiwell:
  api_url: ""
  api_key: ""
  location_id: ""
EOF
```

### 4.2 Tạo ứng dụng chính
```bash
# Tạo file app.py
cat > app.py << 'EOF'
#!/usr/bin/env python3
"""
Body Composition Gateway - Main Application
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import mysql.connector
import yaml
import serial
import threading
import time
import json
import psutil
from datetime import datetime
import glob
import os

# Load configuration
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'body-composition-secret-key'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host=config['database']['host'],
        user=config['database']['username'],
        password=config['database']['password'],
        database=config['database']['database'],
        charset='utf8mb4'
    )

# Device management
class DeviceManager:
    def __init__(self):
        self.devices = {}
        self.connected_devices = []
        self.monitoring = False
        
    def scan_devices(self):
        """Scan for connected devices"""
        devices = []
        for port_pattern in config['device']['scan_ports']:
            for port in glob.glob(port_pattern):
                try:
                    ser = serial.Serial(port, config['device']['baudrate'], timeout=1)
                    devices.append({
                        'port': port,
                        'status': 'connected',
                        'type': 'tanita'
                    })
                    ser.close()
                except:
                    devices.append({
                        'port': port,
                        'status': 'error',
                        'type': 'unknown'
                    })
        return devices
    
    def start_monitoring(self):
        """Start device monitoring"""
        self.monitoring = True
        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()
    
    def _monitor_loop(self):
        """Device monitoring loop"""
        while self.monitoring:
            self.connected_devices = self.scan_devices()
            socketio.emit('device_status', {
                'devices': self.connected_devices,
                'timestamp': datetime.now().isoformat()
            })
            time.sleep(5)  # Scan every 5 seconds

# Initialize device manager
device_manager = DeviceManager()

# Web routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/system/status')
def system_status():
    """Get system status"""
    # Get system metrics
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Test database connection
    db_status = 'disconnected'
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        db_status = 'connected'
    except:
        pass
    
    return jsonify({
        'system': {
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_available_gb': round(memory.available / (1024**3), 2),
            'disk_percent': round((disk.used / disk.total) * 100, 1),
            'disk_free_gb': round(disk.free / (1024**3), 2)
        },
        'database': {
            'status': db_status
        },
        'devices': device_manager.connected_devices,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/devices/scan')
def scan_devices():
    """Scan for devices"""
    devices = device_manager.scan_devices()
    return jsonify({
        'devices': devices,
        'count': len(devices)
    })

@app.route('/api/measurements/latest')
def latest_measurements():
    """Get latest measurements"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT * FROM tanita_measurements 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        
        measurements = cursor.fetchall()
        
        # Convert datetime objects to strings
        for measurement in measurements:
            for key, value in measurement.items():
                if isinstance(value, datetime):
                    measurement[key] = value.isoformat()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'measurements': measurements,
            'count': len(measurements)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# WebSocket events
@socketio.on('connect')
def handle_connect():
    emit('status', {'message': 'Connected to Body Composition Gateway'})

@socketio.on('request_status')
def handle_status_request():
    # Send current system status
    emit('system_status', {
        'devices': device_manager.connected_devices,
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    # Create database tables if they don't exist
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create measurements table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tanita_measurements (
                id INT AUTO_INCREMENT PRIMARY KEY,
                customer_id VARCHAR(50),
                extracted_phone_number VARCHAR(15),
                device_id VARCHAR(50),
                weight_kg DECIMAL(5,1),
                bmi DECIMAL(4,1),
                body_fat_percent DECIMAL(4,1),
                muscle_mass_kg DECIMAL(5,1),
                bone_mass_kg DECIMAL(4,1),
                visceral_fat_rating SMALLINT,
                metabolic_age SMALLINT,
                bmr_kcal SMALLINT,
                raw_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_phone (extracted_phone_number),
                INDEX idx_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Database tables created successfully")
    except Exception as e:
        print(f"Database setup error: {e}")
    
    # Start device monitoring
    device_manager.start_monitoring()
    
    # Start web application
    print(f"Starting Body Composition Gateway on port {config['web']['port']}")
    socketio.run(app, 
                host=config['web']['host'], 
                port=config['web']['port'], 
                debug=config['web']['debug'])
EOF

chmod +x app.py
```

### 4.3 Tạo templates HTML
```bash
# Tạo thư mục templates
mkdir -p templates

# Tạo file index.html
cat > templates/index.html << 'EOF'
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Body Composition Gateway</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37);
        }
        
        .header h1 {
            color: #2c3e50;
            text-align: center;
            margin-bottom: 10px;
        }
        
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .status-card {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37);
        }
        
        .status-card h3 {
            color: #2c3e50;
            margin-bottom: 15px;
            border-bottom: 2px solid #3498db;
            padding-bottom: 5px;
        }
        
        .metric {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            padding: 8px;
            background: rgba(52, 152, 219, 0.1);
            border-radius: 5px;
        }
        
        .metric-label {
            font-weight: 500;
        }
        
        .metric-value {
            font-weight: bold;
            color: #2c3e50;
        }
        
        .status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 500;
        }
        
        .status-connected {
            background: rgba(46, 204, 113, 0.2);
            color: #27ae60;
        }
        
        .status-disconnected {
            background: rgba(231, 76, 60, 0.2);
            color: #e74c3c;
        }
        
        .status-error {
            background: rgba(230, 126, 34, 0.2);
            color: #e67e22;
        }
        
        .device-list {
            max-height: 200px;
            overflow-y: auto;
        }
        
        .device-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            margin-bottom: 8px;
            background: rgba(52, 152, 219, 0.1);
            border-radius: 8px;
        }
        
        .btn {
            background: #3498db;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.3s;
        }
        
        .btn:hover {
            background: #2980b9;
        }
        
        .btn:disabled {
            background: #bdc3c7;
            cursor: not-allowed;
        }
        
        .measurements-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        .measurements-table th,
        .measurements-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ecf0f1;
        }
        
        .measurements-table th {
            background: #3498db;
            color: white;
            font-weight: 600;
        }
        
        .measurements-table tr:hover {
            background: rgba(52, 152, 219, 0.1);
        }
        
        .real-time-indicator {
            position: relative;
        }
        
        .real-time-indicator::before {
            content: '';
            position: absolute;
            top: -2px;
            right: -2px;
            width: 8px;
            height: 8px;
            background: #2ecc71;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.2); opacity: 0.7; }
            100% { transform: scale(1); opacity: 1; }
        }
        
        .loading {
            text-align: center;
            padding: 20px;
            color: #7f8c8d;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏥 Body Composition Gateway</h1>
            <p style="text-align: center; color: #7f8c8d; margin-top: 5px;">
                Real-time monitoring system for Tanita MC-780MA devices
            </p>
        </div>
        
        <div class="status-grid">
            <!-- System Status -->
            <div class="status-card">
                <h3>🖥️ System Status</h3>
                <div class="metric">
                    <span class="metric-label">CPU Usage:</span>
                    <span class="metric-value" id="cpu-usage">Loading...</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Memory Usage:</span>
                    <span class="metric-value" id="memory-usage">Loading...</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Disk Usage:</span>
                    <span class="metric-value" id="disk-usage">Loading...</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Last Update:</span>
                    <span class="metric-value" id="last-update">Loading...</span>
                </div>
            </div>
            
            <!-- Database Status -->
            <div class="status-card">
                <h3>🗄️ Database Status</h3>
                <div class="metric">
                    <span class="metric-label">Connection:</span>
                    <span class="status-indicator" id="db-status">
                        <span class="status-dot"></span>
                        Loading...
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">Server:</span>
                    <span class="metric-value">MySQL</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Database:</span>
                    <span class="metric-value">body_composition_db</span>
                </div>
            </div>
            
            <!-- Device Status -->
            <div class="status-card">
                <h3 class="real-time-indicator">📱 Connected Devices</h3>
                <div id="device-list" class="device-list">
                    <div class="loading">Scanning devices...</div>
                </div>
                <button class="btn" onclick="scanDevices()" id="scan-btn">
                    🔍 Scan Devices
                </button>
            </div>
            
            <!-- Connection Status -->
            <div class="status-card">
                <h3>🌐 Connection Status</h3>
                <div class="metric">
                    <span class="metric-label">WebSocket:</span>
                    <span class="status-indicator" id="websocket-status">
                        <span class="status-dot"></span>
                        Connecting...
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">API Status:</span>
                    <span class="status-indicator" id="api-status">
                        <span class="status-dot"></span>
                        Checking...
                    </span>
                </div>
                <div class="metric">
                    <span class="metric-label">Actiwell Sync:</span>
                    <span class="status-indicator" id="actiwell-status">
                        <span class="status-dot"></span>
                        Not configured
                    </span>
                </div>
            </div>
        </div>
        
        <!-- Latest Measurements -->
        <div class="status-card">
            <h3>📊 Latest Measurements</h3>
            <div id="measurements-container">
                <div class="loading">Loading measurements...</div>
            </div>
            <button class="btn" onclick="loadMeasurements()" style="margin-top: 15px;">
                🔄 Refresh Measurements
            </button>
        </div>
    </div>

    <!-- Socket.IO -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    
    <script>
        // Initialize Socket.IO
        const socket = io();
        let systemData = {};
        
        // Socket event handlers
        socket.on('connect', function() {
            console.log('Connected to server');
            updateWebSocketStatus('connected');
            socket.emit('request_status');
        });
        
        socket.on('disconnect', function() {
            console.log('Disconnected from server');
            updateWebSocketStatus('disconnected');
        });
        
        socket.on('system_status', function(data) {
            console.log('Received system status:', data);
            updateSystemStatus(data);
        });
        
        socket.on('device_status', function(data) {
            console.log('Received device status:', data);
            updateDeviceStatus(data.devices);
        });
        
        // Update functions
        function updateWebSocketStatus(status) {
            const element = document.getElementById('websocket-status');
            if (status === 'connected') {
                element.className = 'status-indicator status-connected';
                element.innerHTML = '<span class="status-dot"></span>Connected';
            } else {
                element.className = 'status-indicator status-disconnected';
                element.innerHTML = '<span class="status-dot"></span>Disconnected';
            }
        }
        
        function updateSystemStatus(data) {
            systemData = data;
            
            // Update system metrics
            if (data.system) {
                document.getElementById('cpu-usage').textContent = data.system.cpu_percent + '%';
                document.getElementById('memory-usage').textContent = data.system.memory_percent + '%';
                document.getElementById('disk-usage').textContent = data.system.disk_percent + '%';
            }
            
            // Update database status
            if (data.database) {
                const dbElement = document.getElementById('db-status');
                if (data.database.status === 'connected') {
                    dbElement.className = 'status-indicator status-connected';
                    dbElement.innerHTML = '<span class="status-dot"></span>Connected';
                } else {
                    dbElement.className = 'status-indicator status-disconnected';
                    dbElement.innerHTML = '<span class="status-dot"></span>Disconnected';
                }
            }
            
            // Update devices
            if (data.devices) {
                updateDeviceStatus(data.devices);
            }
            
            // Update timestamp
            document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
        }
        
        function updateDeviceStatus(devices) {
            const container = document.getElementById('device-list');
            
            if (!devices || devices.length === 0) {
                container.innerHTML = '<div class="loading">No devices found</div>';
                return;
            }
            
            let html = '';
            devices.forEach(device => {
                const statusClass = device.status === 'connected' ? 'status-connected' : 
                                  device.status === 'error' ? 'status-error' : 'status-disconnected';
                
                html += `
                    <div class="device-item">
                        <div>
                            <strong>${device.port}</strong><br>
                            <small>Type: ${device.type}</small>
                        </div>
                        <span class="status-indicator ${statusClass}">
                            <span class="status-dot"></span>
                            ${device.status}
                        </span>
                    </div>
                `;
            });
            
            container.innerHTML = html;
        }
        
        // API functions
        async function loadSystemStatus() {
            try {
                const response = await fetch('/api/system/status');
                const data = await response.json();
                updateSystemStatus(data);
                
                // Update API status
                const apiElement = document.getElementById('api-status');
                apiElement.className = 'status-indicator status-connected';
                apiElement.innerHTML = '<span class="status-dot"></span>Online';
            } catch (error) {
                console.error('Error loading system status:', error);
                const apiElement = document.getElementById('api-status');
                apiElement.className = 'status-indicator status-error';
                apiElement.innerHTML = '<span class="status-dot"></span>Error';
            }
        }
        
        async function scanDevices() {
            const btn = document.getElementById('scan-btn');
            btn.disabled = true;
            btn.textContent = '🔍 Scanning...';
            
            try {
                const response = await fetch('/api/devices/scan');
                const data = await response.json();
                updateDeviceStatus(data.devices);
            } catch (error) {
                console.error('Error scanning devices:', error);
            } finally {
                btn.disabled = false;
                btn.textContent = '🔍 Scan Devices';
            }
        }
        
        async function loadMeasurements() {
            const container = document.getElementById('measurements-container');
            container.innerHTML = '<div class="loading">Loading measurements...</div>';
            
            try {
                const response = await fetch('/api/measurements/latest');
                const data = await response.json();
                
                if (data.measurements && data.measurements.length > 0) {
                    let html = `
                        <table class="measurements-table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Phone</th>
                                    <th>Weight (kg)</th>
                                    <th>BMI</th>
                                    <th>Body Fat (%)</th>
                                    <th>Muscle Mass (kg)</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;
                    
                    data.measurements.forEach(m => {
                        const time = new Date(m.created_at).toLocaleString();
                        html += `
                            <tr>
                                <td>${time}</td>
                                <td>${m.extracted_phone_number || 'N/A'}</td>
                                <td>${m.weight_kg || 'N/A'}</td>
                                <td>${m.bmi || 'N/A'}</td>
                                <td>${m.body_fat_percent || 'N/A'}</td>
                                <td>${m.muscle_mass_kg || 'N/A'}</td>
                            </tr>
                        `;
                    });
                    
                    html += '</tbody></table>';
                    container.innerHTML = html;
                } else {
                    container.innerHTML = '<div class="loading">No measurements found</div>';
                }
            } catch (error) {
                console.error('Error loading measurements:', error);
                container.innerHTML = '<div class="loading">Error loading measurements</div>';
            }
        }
        
        // Initialize page
        document.addEventListener('DOMContentLoaded', function() {
            loadSystemStatus();
            loadMeasurements();
            
            // Auto-refresh every 30 seconds
            setInterval(loadSystemStatus, 30000);
            setInterval(loadMeasurements, 60000);
        });
    </script>
</body>
</html>
EOF
```

## Bước 5: Tạo Service để chạy tự động

### 5.1 Tạo systemd service
```bash
# Tạo service file
sudo cat > /etc/systemd/system/body-composition-gateway.service << 'EOF'
[Unit]
Description=Body Composition Gateway Service
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/opt/body-composition-gateway
Environment=PATH=/opt/body-composition-gateway/venv/bin
ExecStart=/opt/body-composition-gateway/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd và enable service
sudo systemctl daemon-reload
sudo systemctl enable body-composition-gateway
```

### 5.2 Khởi động service
```bash
# Khởi động service
sudo systemctl start body-composition-gateway

# Kiểm tra trạng thái
sudo systemctl status body-composition-gateway

# Xem logs
sudo journalctl -u body-composition-gateway -f
```

## Bước 6: Cấu hình USB permissions cho Tanita

### 6.1 Thêm user vào group dialout
```bash
# Thêm user pi vào group dialout
sudo usermod -a -G dialout pi

# Kiểm tra group membership
groups pi
```

### 6.2 Tạo udev rules cho Tanita device
```bash
# Tạo udev rules
sudo cat > /etc/udev/rules.d/99-tanita-devices.rules << 'EOF'
# Tanita MC-780MA (FTDI USB-to-Serial)
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", MODE="0666", GROUP="dialout", SYMLINK+="tanita%n"
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6014", MODE="0666", GROUP="dialout", SYMLINK+="tanita%n"

# Generic USB-to-Serial adapters
SUBSYSTEM=="tty", ATTRS{idVendor}=="067b", ATTRS{idProduct}=="2303", MODE="0666", GROUP="dialout"
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", MODE="0666", GROUP="dialout"
EOF

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Bước 7: Kiểm tra và test hệ thống

### 7.1 Kiểm tra MySQL
```bash
# Test kết nối MySQL
mysql -u body_comp_user -p body_composition_db -e "SELECT 1;"
```

### 7.2 Kiểm tra web server
```bash
# Kiểm tra port có được mở không
sudo netstat -tlnp | grep :5000

# Test API
curl http://localhost:5000/api/system/status
```

### 7.3 Kiểm tra USB devices
```bash
# Liệt kê USB devices
lsusb

# Kiểm tra serial ports
ls -la /dev/ttyUSB* /dev/ttyACM*

# Test quyền truy cập
python3 -c "import serial; print('Serial access OK')"
```

## Bước 8: Truy cập Web Interface

### 8.1 Mở web browser
Truy cập: `http://[IP_của_Raspberry_Pi]:5000`

Để tìm IP của Raspberry Pi:
```bash
hostname -I
```

### 8.2 Kiểm tra các chức năng
- ✅ System Status hiển thị CPU, Memory, Disk usage
- ✅ Database Status hiển thị "Connected"
- ✅ Device Status hiển thị các USB devices
- ✅ WebSocket Status hiển thị "Connected"
- ✅ Latest Measurements (sẽ empty ban đầu)

## Bước 9: Troubleshooting

### 9.1 Nếu service không start
```bash
# Xem logs chi tiết
sudo journalctl -u body-composition-gateway -n 50

# Kiểm tra Python environment
cd /opt/body-composition-gateway
source venv/bin/activate
python app.py
```

### 9.2 Nếu không kết nối được database
```bash
# Kiểm tra MySQL service
sudo systemctl status mysql

# Test kết nối thủ công
mysql -u body_comp_user -p
```

### 9.3 Nếu không detect được USB device
```bash
# Kiểm tra USB device có được nhận diện không
dmesg | grep ttyUSB

# Kiểm tra quyền
ls -la /dev/ttyUSB*
```

## Bước 10: Cấu hình auto-start khi boot

```bash
# Đảm bảo service auto-start
sudo systemctl enable body-composition-gateway
sudo systemctl enable mysql

# Test reboot
sudo reboot
```

Sau khi reboot, hệ thống sẽ tự động khởi động và có thể truy cập qua web interface.