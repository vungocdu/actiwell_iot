#!/bin/bash
# Actiwell Tanita Integration - Production Setup Script

echo "🚀 ACTIWELL TANITA INTEGRATION SETUP"
echo "====================================="

# Create directory structure
sudo mkdir -p /opt/actiwell/tanita
cd /opt/actiwell/tanita

# Create Laravel API routes (add to routes/api.php)
cat > routes_to_add.php << 'EOF'
// Tanita Integration Routes
Route::prefix('tanita')->middleware(['auth:api'])->group(function () {
    Route::get('/customers/search', [TanitaIntegrationController::class, 'searchCustomerByPhone']);
    Route::post('/body-composition', [TanitaIntegrationController::class, 'saveBodyCompositionData']);
    Route::get('/customers/{customer}/body-composition/history', [TanitaIntegrationController::class, 'getBodyCompositionHistory']);
    Route::get('/customers/{customer}/body-composition/stats', [TanitaIntegrationController::class, 'getBodyCompositionStats']);
});
EOF

# Create Tanita configuration file
cat > tanita_config.ini << 'EOF'
[tanita]
port = /dev/ttyUSB0
baudrate = 9600

[actiwell]
api_base_url = https://your-actiwell-domain.com
api_token = your-api-token-here
location_id = 1
operator_id = 1

[logging]
level = INFO
log_file = /opt/actiwell/tanita/tanita_gateway.log
max_log_size = 10485760
backup_count = 5
EOF

# Create systemd service file
sudo cat > /etc/systemd/system/tanita-gateway.service << 'EOF'
[Unit]
Description=Actiwell Tanita MC-780MA Gateway Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=pi
Group=dialout
WorkingDirectory=/opt/actiwell/tanita
ExecStart=/usr/bin/python3 /opt/actiwell/tanita/actiwell_tanita_gateway.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/tanita-gateway.log
StandardError=append:/var/log/tanita-gateway-error.log

# Environment variables
Environment=PYTHONPATH=/opt/actiwell/tanita
Environment=PYTHONUNBUFFERED=1

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/actiwell/tanita /var/log

[Install]
WantedBy=multi-user.target
EOF

# Create log rotation configuration
sudo cat > /etc/logrotate.d/tanita-gateway << 'EOF'
/var/log/tanita-gateway*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 pi dialout
    postrotate
        /bin/systemctl reload tanita-gateway.service > /dev/null 2>&1 || true
    endscript
}

/opt/actiwell/tanita/tanita_gateway.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 pi dialout
}
EOF

# Create installation script
cat > install.sh << 'EOF'
#!/bin/bash
echo "📦 Installing Actiwell Tanita Integration..."

# Install Python dependencies
pip3 install pyserial requests configparser

# Set up permissions
sudo usermod -a -G dialout $USER
sudo chown -R pi:dialout /opt/actiwell/tanita
sudo chmod +x /opt/actiwell/tanita/*.py

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable tanita-gateway.service

echo "✅ Installation complete!"
echo ""
echo "📝 Next steps:"
echo "1. Edit tanita_config.ini with your Actiwell API details"
echo "2. Add the routes to your Laravel routes/api.php"
echo "3. Deploy the TanitaIntegrationController"
echo "4. Start the service: sudo systemctl start tanita-gateway"
echo "5. Check logs: sudo journalctl -u tanita-gateway -f"
echo ""
echo "🔧 Configuration file: /opt/actiwell/tanita/tanita_config.ini"
echo "📊 Service status: sudo systemctl status tanita-gateway"
EOF

chmod +x install.sh

# Create monitoring script
cat > monitor_tanita.sh << 'EOF'
#!/bin/bash
# Tanita Gateway Monitoring Script

echo "🔍 TANITA GATEWAY MONITORING"
echo "============================="

echo "📊 Service Status:"
sudo systemctl status tanita-gateway --no-pager

echo ""
echo "📡 USB Devices:"
lsusb | grep -i "FTDI\|Future Technology"

echo ""
echo "🔌 Serial Ports:"
ls -la /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "No serial ports found"

echo ""
echo "📝 Recent Logs (last 20 lines):"
sudo journalctl -u tanita-gateway --no-pager -n 20

echo ""
echo "🔧 Configuration:"
if [ -f "/opt/actiwell/tanita/tanita_config.ini" ]; then
    echo "✅ Config file exists"
    grep -E "^\[|^api_base_url|^location_id|^port" /opt/actiwell/tanita/tanita_config.ini
else
    echo "❌ Config file not found"
fi

echo ""
echo "💾 Disk Usage:"
du -sh /opt/actiwell/tanita/
du -sh /var/log/tanita-gateway*.log 2>/dev/null || echo "No log files yet"

echo ""
echo "🌐 Network Test:"
if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
    echo "✅ Internet connectivity OK"
else
    echo "❌ No internet connectivity"
fi
EOF

chmod +x monitor_tanita.sh

# Create customer workflow guide
cat > CUSTOMER_WORKFLOW.md << 'EOF'
# Actiwell Tanita Integration - Customer Workflow

## Setup Process

### 1. Customer Registration
- Customer purchases package in Actiwell CMS
- Enter customer phone number in Tanita device as ID
- Format: Vietnamese phone number (0912345678)

### 2. Face ID + Body Composition Flow
```
Customer arrives → Face ID check-in (Hanet) → Body composition measurement (Tanita)
                                         ↓
    Actiwell Database ← API Integration ← Phone number identification
```

### 3. Data Flow
1. **Customer steps on Tanita scale**
2. **Device reads phone number from ID field**
3. **Gateway extracts measurement data**
4. **API finds customer in Actiwell database**
5. **Saves body composition to log_customer_activities**
6. **Triggers business workflows (package recommendations, etc.)**

## Staff Training

### Tanita Device Operation
1. Power on device: Press power button
2. Enter customer phone number as ID
3. Customer steps on scale barefoot
4. Wait for complete measurement (30-60 seconds)
5. Data transmits automatically to Actiwell

### Phone Number Format
- **Correct**: 0912345678 (Vietnamese format)
- **Incorrect**: 912345678, +84912345678
- **Fallback**: If no phone → manual customer selection in CMS

### Troubleshooting
- **No data received**: Check USB cable, restart gateway service
- **Customer not found**: Verify phone number, check customer database
- **Measurement error**: Clean scale contacts, ensure good foot contact

## Business Integration

### Automatic Workflows
- **High BMI detected** → Suggest weight loss packages
- **Low muscle mass** → Recommend PT sessions
- **Trend analysis** → Send progress reports to customers
- **Package expiry** → Renewal notifications based on health goals

### Manual Workflows
- **Unknown phone number** → Staff registers new customer
- **Measurement review** → Trainer discusses results with customer
- **Goal setting** → Update customer targets based on body composition

## API Endpoints

### Search Customer
```http
GET /api/tanita/customers/search?phone=0912345678&operator_id=1&location_id=1
```

### Save Measurement
```http
POST /api/tanita/body-composition
{
  "customer_id": 123,
  "activity_type": 5,
  "data": { "measurements": {...} },
  "location_id": 1,
  "operator_id": 1
}
```

### Get History
```http
GET /api/tanita/customers/123/body-composition/history?operator_id=1&days=30
```

### Get Statistics
```http
GET /api/tanita/customers/123/body-composition/stats?operator_id=1
```
EOF

echo ""
echo "✅ Setup files created successfully!"
echo ""
echo "📂 Files created:"
echo "├── tanita_config.ini (configuration)"
echo "├── routes_to_add.php (Laravel routes)"
echo "├── install.sh (installation script)"
echo "├── monitor_tanita.sh (monitoring tools)"
echo "├── CUSTOMER_WORKFLOW.md (documentation)"
echo "└── /etc/systemd/system/tanita-gateway.service (systemd service)"
echo ""
echo "🚀 Run './install.sh' to complete installation"