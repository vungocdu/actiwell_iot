#!/bin/bash
##############################################################################
# Body Composition Gateway - Quick Install Script for Raspberry Pi
# Tự động cài đặt MySQL, Web Server và thiết lập môi trường
##############################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DB_NAME="body_composition_db"
DB_USER="body_comp_user"
DB_PASS=""
APP_DIR="/opt/body-composition-gateway"
SERVICE_NAME="body-composition-gateway"

# Logging
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_info() {
    log "${BLUE}[INFO]${NC} $1"
}

log_success() {
    log "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    log "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    log "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_error "This script should not be run as root. Please run as pi user with sudo when needed."
        exit 1
    fi
}

# Generate secure password
generate_password() {
    if [ -z "$DB_PASS" ]; then
        DB_PASS=$(openssl rand -base64 20 | tr -d "=+/" | cut -c1-16)
    fi
}

# Install dependencies
install_dependencies() {
    log_info "Installing system dependencies..."
    
    sudo apt update
    sudo apt install -y \
        python3 python3-pip python3-venv python3-dev \
        mysql-server \
        build-essential libssl-dev libffi-dev \
        git curl wget nano htop
    
    log_success "Dependencies installed"
}

# Setup MySQL
setup_mysql() {
    log_info "Setting up MySQL..."
    
    # Start and enable MySQL
    sudo systemctl start mysql
    sudo systemctl enable mysql
    
    # Create database and user
    log_info "Creating database and user..."
    sudo mysql << EOF
CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';
GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
EOF
    
    # Optimize MySQL for Raspberry Pi
    log_info "Optimizing MySQL for Raspberry Pi..."
    sudo tee -a /etc/mysql/mysql.conf.d/raspberrypi.cnf > /dev/null << 'EOF'
[mysqld]
# Raspberry Pi optimizations
innodb_buffer_pool_size = 128M
innodb_log_file_size = 32M
max_connections = 50
query_cache_type = 1
query_cache_size = 16M
tmp_table_size = 16M
max_heap_table_size = 16M
EOF
    
    sudo systemctl restart mysql
    log_success "MySQL setup completed"
}

# Setup application
setup_application() {
    log_info "Setting up application..."
    
    # Create application directory
    sudo mkdir -p $APP_DIR
    sudo chown pi:pi $APP_DIR
    cd $APP_DIR
    
    # Create virtual environment
    python3 -m venv venv
    source venv/bin/activate
    
    # Upgrade pip and install packages
    pip install --upgrade pip setuptools wheel
    
    # Create requirements.txt
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
    
    # Install Python packages
    pip install -r requirements.txt
    
    log_success "Application environment created"
}

# Create configuration
create_config() {
    log_info "Creating configuration..."
    
    cd $APP_DIR
    
    cat > config.yaml << EOF
database:
  host: "localhost"
  port: 3306
  username: "$DB_USER"
  password: "$DB_PASS"
  database: "$DB_NAME"

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

    chmod 600 config.yaml
    log_success "Configuration created"
}

# Create main application
create_app() {
    log_info "Creating main application..."
    
    cd $APP_DIR
    
    # Download the main app.py from the previous artifact content
    # For this script, we'll create a simplified version
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
            time.sleep(5)

# Initialize device manager
device_manager = DeviceManager()

# Web routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/system/status')
def system_status():
    """Get system status"""
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
    emit('system_status', {
        'devices': device_manager.connected_devices,
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    # Create database tables if they don't exist
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
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
    log_success "Main application created"
}

# Create templates
create_templates() {
    log_info "Creating web templates..."
    
    cd $APP_DIR
    mkdir -p templates
    
    # Create the HTML template (simplified version)
    cat > templates/index.html << 'EOF'
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Body Composition Gateway</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333; min-height: 100vh;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { 
            background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(10px);
            border-radius: 15px; padding: 20px; margin-bottom: 20px;
            box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37);
        }
        .header h1 { color: #2c3e50; text-align: center; margin-bottom: 10px; }
        .status-grid { 
            display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px; margin-bottom: 20px;
        }
        .status-card { 
            background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(10px);
            border-radius: 15px; padding: 20px; box-shadow: 0 8px 32px rgba(31, 38, 135, 0.37);
        }
        .status-card h3 { 
            color: #2c3e50; margin-bottom: 15px; border-bottom: 2px solid #3498db; padding-bottom: 5px;
        }
        .metric { 
            display: flex; justify-content: space-between; margin-bottom: 10px;
            padding: 8px; background: rgba(52, 152, 219, 0.1); border-radius: 5px;
        }
        .metric-label { font-weight: 500; }
        .metric-value { font-weight: bold; color: #2c3e50; }
        .status-indicator { 
            display: inline-flex; align-items: center; gap: 8px;
            padding: 5px 15px; border-radius: 20px; font-size: 14px; font-weight: 500;
        }
        .status-connected { background: rgba(46, 204, 113, 0.2); color: #27ae60; }
        .status-disconnected { background: rgba(231, 76, 60, 0.2); color: #e74c3c; }
        .status-error { background: rgba(230, 126, 34, 0.2); color: #e67e22; }
        .btn { 
            background: #3498db; color: white; border: none; padding: 10px 20px;
            border-radius: 8px; cursor: pointer; font-size: 14px; transition: background 0.3s;
        }
        .btn:hover { background: #2980b9; }
        .loading { text-align: center; padding: 20px; color: #7f8c8d; }
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
            </div>
            
            <!-- Database Status -->
            <div class="status-card">
                <h3>🗄️ Database Status</h3>
                <div class="metric">
                    <span class="metric-label">Connection:</span>
                    <span class="status-indicator" id="db-status">Loading...</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Database:</span>
                    <span class="metric-value">body_composition_db</span>
                </div>
            </div>
            
            <!-- Device Status -->
            <div class="status-card">
                <h3>📱 Connected Devices</h3>
                <div id="device-list" class="loading">Scanning devices...</div>
                <button class="btn" onclick="scanDevices()" id="scan-btn">🔍 Scan Devices</button>
            </div>
            
            <!-- Connection Status -->
            <div class="status-card">
                <h3>🌐 Connection Status</h3>
                <div class="metric">
                    <span class="metric-label">WebSocket:</span>
                    <span class="status-indicator" id="websocket-status">Connecting...</span>
                </div>
                <div class="metric">
                    <span class="metric-label">API Status:</span>
                    <span class="status-indicator" id="api-status">Checking...</span>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <script>
        const socket = io();
        
        socket.on('connect', function() {
            document.getElementById('websocket-status').className = 'status-indicator status-connected';
            document.getElementById('websocket-status').textContent = 'Connected';
            socket.emit('request_status');
        });
        
        socket.on('disconnect', function() {
            document.getElementById('websocket-status').className = 'status-indicator status-disconnected';
            document.getElementById('websocket-status').textContent = 'Disconnected';
        });
        
        socket.on('system_status', function(data) {
            if (data.system) {
                document.getElementById('cpu-usage').textContent = data.system.cpu_percent + '%';
                document.getElementById('memory-usage').textContent = data.system.memory_percent + '%';
                document.getElementById('disk-usage').textContent = data.system.disk_percent + '%';
            }
            if (data.database) {
                const dbElement = document.getElementById('db-status');
                if (data.database.status === 'connected') {
                    dbElement.className = 'status-indicator status-connected';
                    dbElement.textContent = 'Connected';
                } else {
                    dbElement.className = 'status-indicator status-disconnected';
                    dbElement.textContent = 'Disconnected';
                }
            }
            if (data.devices) updateDeviceStatus(data.devices);
        });
        
        function updateDeviceStatus(devices) {
            const container = document.getElementById('device-list');
            if (!devices || devices.length === 0) {
                container.innerHTML = '<div class="loading">No devices found</div>';
                return;
            }
            let html = '';
            devices.forEach(device => {
                const statusClass = device.status === 'connected' ? 'status-connected' : 'status-error';
                html += `<div style="margin-bottom: 10px; padding: 10px; background: rgba(52, 152, 219, 0.1); border-radius: 5px;">
                    <strong>${device.port}</strong> - <span class="status-indicator ${statusClass}">${device.status}</span>
                </div>`;
            });
            container.innerHTML = html;
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
        
        async function loadSystemStatus() {
            try {
                const response = await fetch('/api/system/status');
                const data = await response.json();
                socket.emit('system_status', data);
                
                document.getElementById('api-status').className = 'status-indicator status-connected';
                document.getElementById('api-status').textContent = 'Online';
            } catch (error) {
                document.getElementById('api-status').className = 'status-indicator status-error';
                document.getElementById('api-status').textContent = 'Error';
            }
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            loadSystemStatus();
            setInterval(loadSystemStatus, 30000);
        });
    </script>
</body>
</html>
EOF

    log_success "Web templates created"
}

# Setup USB permissions
setup_usb_permissions() {
    log_info "Setting up USB permissions..."
    
    # Add user to dialout group
    sudo usermod -a -G dialout pi
    
    # Create udev rules
    sudo tee /etc/udev/rules.d/99-tanita-devices.rules > /dev/null << 'EOF'
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
    
    log_success "USB permissions configured"
}

# Create systemd service
create_service() {
    log_info "Creating systemd service..."
    
    sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << EOF
[Unit]
Description=Body Composition Gateway Service
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd and enable service
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME
    
    log_success "Systemd service created"
}

# Start services
start_services() {
    log_info "Starting services..."
    
    # Start MySQL if not running
    sudo systemctl start mysql
    
    # Start our service
    sudo systemctl start $SERVICE_NAME
    
    # Check status
    sleep 3
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        log_success "Body Composition Gateway service started successfully"
    else
        log_error "Failed to start service. Check logs with: sudo journalctl -u $SERVICE_NAME"
    fi
}

# Save installation info
save_install_info() {
    log_info "Saving installation information..."
    
    cat > $APP_DIR/install_info.txt << EOF
Body Composition Gateway Installation Info
==========================================

Installation Date: $(date)
Raspberry Pi Model: $(cat /proc/device-tree/model 2>/dev/null || echo "Unknown")

Database Configuration:
- Database Name: $DB_NAME
- Username: $DB_USER
- Password: $DB_PASS

Web Interface:
- URL: http://$(hostname -I | awk '{print $1}'):5000
- Port: 5000

Service Management:
- Service Name: $SERVICE_NAME
- Start: sudo systemctl start $SERVICE_NAME
- Stop: sudo systemctl stop $SERVICE_NAME
- Status: sudo systemctl status $SERVICE_NAME
- Logs: sudo journalctl -u $SERVICE_NAME -f

Files and Directories:
- Application: $APP_DIR
- Configuration: $APP_DIR/config.yaml
- Main App: $APP_DIR/app.py

Useful Commands:
- Scan USB devices: lsusb
- List serial ports: ls -la /dev/ttyUSB* /dev/ttyACM*
- Test database: mysql -u $DB_USER -p$DB_PASS $DB_NAME
EOF

    chmod 600 $APP_DIR/install_info.txt
    log_success "Installation info saved to $APP_DIR/install_info.txt"
}

# Show installation summary
show_summary() {
    clear
    echo
    log_success "=================================================================="
    log_success "    Body Composition Gateway Installation Complete!"
    log_success "=================================================================="
    echo
    echo -e "${BLUE}📊 Installation Summary:${NC}"
    echo "   • MySQL Server: Installed and configured"
    echo "   • Web Application: Running on port 5000"
    echo "   • Database: $DB_NAME (user: $DB_USER)"
    echo "   • Service: $SERVICE_NAME (auto-start enabled)"
    echo
    echo -e "${BLUE}🌐 Web Access:${NC}"
    echo "   • URL: http://$(hostname -I | awk '{print $1}'):5000"
    echo "   • Local: http://localhost:5000"
    echo
    echo -e "${BLUE}🔧 Service Management:${NC}"
    echo "   • Start: sudo systemctl start $SERVICE_NAME"
    echo "   • Stop: sudo systemctl stop $SERVICE_NAME"
    echo "   • Status: sudo systemctl status $SERVICE_NAME"
    echo "   • Logs: sudo journalctl -u $SERVICE_NAME -f"
    echo
    echo -e "${BLUE}📱 Device Setup:${NC}"
    echo "   • Connect Tanita MC-780MA via USB"
    echo "   • Check devices: ls /dev/ttyUSB* /dev/ttyACM*"
    echo "   • Scan from web interface"
    echo
    echo -e "${BLUE}🔐 Database Access:${NC}"
    echo "   • Username: $DB_USER"
    echo "   • Password: $DB_PASS"
    echo "   • Database: $DB_NAME"
    echo
    echo -e "${YELLOW}⚠️  Next Steps:${NC}"
    echo "   1. Connect your Tanita device via USB"
    echo "   2. Access web interface to verify status"
    echo "   3. Configure Actiwell API in config.yaml if needed"
    echo "   4. Test device communication"
    echo
    log_success "Installation completed successfully! 🎉"
    echo
}

# Main installation function
main() {
    clear
    echo
    log_info "=================================================================="
    log_info "    Body Composition Gateway - Quick Install Script"
    log_info "    Installing MySQL, Web Server, and Device Interface"
    log_info "=================================================================="
    echo
    
    # Check prerequisites
    check_root
    
    # Generate secure password
    generate_password
    
    log_info "Starting installation with database password: $DB_PASS"
    echo
    
    # Installation steps
    install_dependencies
    setup_mysql
    setup_application
    create_config
    create_app
    create_templates
    setup_usb_permissions
    create_service
    start_services
    save_install_info
    
    # Show summary
    show_summary
}

# Run main function
main "$@"