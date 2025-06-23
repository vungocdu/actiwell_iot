#!/bin/bash
##############################################################################
# Body Composition Gateway - System Test Script
# Kiểm tra toàn bộ hệ thống sau khi cài đặt
##############################################################################

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/opt/body-composition-gateway"
SERVICE_NAME="body-composition-gateway"
WEB_PORT=5000

# Test results
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓ PASS]${NC} $1"
    ((PASSED_TESTS++))
}

log_fail() {
    echo -e "${RED}[✗ FAIL]${NC} $1"
    ((FAILED_TESTS++))
}

log_warning() {
    echo -e "${YELLOW}[⚠ WARN]${NC} $1"
}

# Test function wrapper
run_test() {
    local test_name="$1"
    local test_function="$2"
    
    ((TOTAL_TESTS++))
    echo -e "\n${BLUE}Testing: $test_name${NC}"
    
    if $test_function; then
        log_success "$test_name"
        return 0
    else
        log_fail "$test_name"
        return 1
    fi
}

# Test 1: System requirements
test_system_requirements() {
    local errors=0
    
    # Check if running on Raspberry Pi
    if [[ -f /proc/device-tree/model ]] && grep -q "Raspberry Pi" /proc/device-tree/model; then
        echo "  - Raspberry Pi detected: $(cat /proc/device-tree/model)"
    else
        echo "  - Warning: Not running on Raspberry Pi"
        ((errors++))
    fi
    
    # Check memory
    local total_mem=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local total_mem_gb=$((total_mem / 1024 / 1024))
    if [[ $total_mem_gb -ge 1 ]]; then
        echo "  - Memory: ${total_mem_gb}GB (sufficient)"
    else
        echo "  - Memory: ${total_mem_gb}GB (may be insufficient)"
        ((errors++))
    fi
    
    # Check disk space
    local available_space=$(df / | awk 'NR==2{printf "%.1f", $4/1024/1024}')
    if (( $(echo "$available_space > 1.0" | bc -l) )); then
        echo "  - Disk space: ${available_space}GB available"
    else
        echo "  - Disk space: ${available_space}GB (insufficient)"
        ((errors++))
    fi
    
    return $errors
}

# Test 2: MySQL installation and configuration
test_mysql() {
    local errors=0
    
    # Check if MySQL service is running
    if systemctl is-active --quiet mysql; then
        echo "  - MySQL service: Running"
    else
        echo "  - MySQL service: Not running"
        ((errors++))
    fi
    
    # Check if MySQL is enabled on boot
    if systemctl is-enabled --quiet mysql; then
        echo "  - MySQL auto-start: Enabled"
    else
        echo "  - MySQL auto-start: Not enabled"
        ((errors++))
    fi
    
    # Test database connection
    if mysql -u root -e "SELECT 1;" &>/dev/null; then
        echo "  - MySQL root access: OK"
    else
        echo "  - MySQL root access: Failed"
        ((errors++))
    fi
    
    # Check if application database exists
    if mysql -u root -e "USE body_composition_db; SELECT 1;" &>/dev/null; then
        echo "  - Application database: Exists"
    else
        echo "  - Application database: Not found"
        ((errors++))
    fi
    
    return $errors
}

# Test 3: Python environment
test_python_environment() {
    local errors=0
    
    # Check if application directory exists
    if [[ -d "$APP_DIR" ]]; then
        echo "  - Application directory: Exists"
    else
        echo "  - Application directory: Not found"
        ((errors++))
        return $errors
    fi
    
    # Check if virtual environment exists
    if [[ -d "$APP_DIR/venv" ]]; then
        echo "  - Python virtual environment: Exists"
    else
        echo "  - Python virtual environment: Not found"
        ((errors++))
    fi
    
    # Check if main application file exists
    if [[ -f "$APP_DIR/app.py" ]]; then
        echo "  - Main application file: Exists"
    else
        echo "  - Main application file: Not found"
        ((errors++))
    fi
    
    # Check if configuration file exists
    if [[ -f "$APP_DIR/config.yaml" ]]; then
        echo "  - Configuration file: Exists"
    else
        echo "  - Configuration file: Not found"
        ((errors++))
    fi
    
    # Test Python packages
    if [[ -f "$APP_DIR/venv/bin/python" ]]; then
        if $APP_DIR/venv/bin/python -c "import flask, mysql.connector, serial, yaml" &>/dev/null; then
            echo "  - Required Python packages: Installed"
        else
            echo "  - Required Python packages: Missing or broken"
            ((errors++))
        fi
    fi
    
    return $errors
}

# Test 4: Web service
test_web_service() {
    local errors=0
    
    # Check if service is running
    if systemctl is-active --quiet $SERVICE_NAME; then
        echo "  - Service status: Running"
    else
        echo "  - Service status: Not running"
        ((errors++))
    fi
    
    # Check if service is enabled
    if systemctl is-enabled --quiet $SERVICE_NAME; then
        echo "  - Service auto-start: Enabled"
    else
        echo "  - Service auto-start: Not enabled"
        ((errors++))
    fi
    
    # Check if port is listening
    if netstat -tlnp 2>/dev/null | grep -q ":$WEB_PORT "; then
        echo "  - Web port $WEB_PORT: Listening"
    else
        echo "  - Web port $WEB_PORT: Not listening"
        ((errors++))
    fi
    
    # Test HTTP response
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:$WEB_PORT/ | grep -q "200"; then
        echo "  - HTTP response: OK"
    else
        echo "  - HTTP response: Failed"
        ((errors++))
    fi
    
    # Test API endpoint
    if curl -s http://localhost:$WEB_PORT/api/system/status | grep -q "system"; then
        echo "  - API endpoint: Responding"
    else
        echo "  - API endpoint: Not responding"
        ((errors++))
    fi
    
    return $errors
}

# Test 5: USB permissions and device detection
test_usb_permissions() {
    local errors=0
    
    # Check if user is in dialout group
    if groups pi | grep -q dialout; then
        echo "  - User dialout group: Member"
    else
        echo "  - User dialout group: Not member"
        ((errors++))
    fi
    
    # Check udev rules
    if [[ -f /etc/udev/rules.d/99-tanita-devices.rules ]]; then
        echo "  - Udev rules: Installed"
    else
        echo "  - Udev rules: Not found"
        ((errors++))
    fi
    
    # Check for USB serial devices
    local usb_devices=$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | wc -l)
    if [[ $usb_devices -gt 0 ]]; then
        echo "  - USB serial devices: $usb_devices found"
        ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | while read device; do
            echo "    - $device"
        done
    else
        echo "  - USB serial devices: None found (this is OK if no device connected)"
    fi
    
    # Test serial port access
    if [[ $usb_devices -gt 0 ]]; then
        local test_port=$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -1)
        if timeout 2 python3 -c "import serial; s=serial.Serial('$test_port', 9600, timeout=1); s.close()" 2>/dev/null; then
            echo "  - Serial port access: OK"
        else
            echo "  - Serial port access: Failed (check permissions)"
            ((errors++))
        fi
    fi
    
    return $errors
}

# Test 6: Database tables and structure
test_database_structure() {
    local errors=0
    
    # Load database credentials from config
    if [[ -f "$APP_DIR/config.yaml" ]]; then
        local db_user=$(grep -A5 "database:" "$APP_DIR/config.yaml" | grep "username:" | cut -d'"' -f2)
        local db_pass=$(grep -A5 "database:" "$APP_DIR/config.yaml" | grep "password:" | cut -d'"' -f2)
        local db_name=$(grep -A5 "database:" "$APP_DIR/config.yaml" | grep "database:" | tail -1 | cut -d'"' -f2)
        
        # Test database connection with app credentials
        if mysql -u "$db_user" -p"$db_pass" "$db_name" -e "SELECT 1;" &>/dev/null; then
            echo "  - Application database access: OK"
        else
            echo "  - Application database access: Failed"
            ((errors++))
        fi
        
        # Check if main table exists
        if mysql -u "$db_user" -p"$db_pass" "$db_name" -e "DESCRIBE tanita_measurements;" &>/dev/null; then
            echo "  - Measurements table: Exists"
        else
            echo "  - Measurements table: Not found"
            ((errors++))
        fi
        
        # Test table structure
        local table_count=$(mysql -u "$db_user" -p"$db_pass" "$db_name" -e "SHOW TABLES;" 2>/dev/null | wc -l)
        echo "  - Database tables: $((table_count-1)) found"
        
    else
        echo "  - Configuration file: Not found"
        ((errors++))
    fi
    
    return $errors
}

# Test 7: System performance
test_system_performance() {
    local errors=0
    
    # CPU usage
    local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    echo "  - CPU usage: ${cpu_usage}%"
    
    # Memory usage
    local mem_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    echo "  - Memory usage: ${mem_usage}%"
    
    # Disk usage
    local disk_usage=$(df / | awk 'NR==2{printf "%.1f", $3/$2*100}')
    echo "  - Disk usage: ${disk_usage}%"
    
    # Load average
    local load_avg=$(uptime | awk -F'load average:' '{print $2}' | cut -d',' -f1 | xargs)
    echo "  - Load average (1m): ${load_avg}"
    
    # Check for high resource usage
    if (( $(echo "$cpu_usage > 80" | bc -l) )); then
        echo "  - Warning: High CPU usage"
        ((errors++))
    fi
    
    if (( $(echo "$mem_usage > 90" | bc -l) )); then
        echo "  - Warning: High memory usage"
        ((errors++))
    fi
    
    return $errors
}

# Test 8: Network connectivity
test_network_connectivity() {
    local errors=0
    
    # Check network interface
    local ip_address=$(hostname -I | awk '{print $1}')
    if [[ -n "$ip_address" ]]; then
        echo "  - IP address: $ip_address"
    else
        echo "  - IP address: Not assigned"
        ((errors++))
    fi
    
    # Test internet connectivity
    if ping -c 1 8.8.8.8 &>/dev/null; then
        echo "  - Internet connectivity: OK"
    else
        echo "  - Internet connectivity: Failed"
        ((errors++))
    fi
    
    # Test DNS resolution
    if nslookup google.com &>/dev/null; then
        echo "  - DNS resolution: OK"
    else
        echo "  - DNS resolution: Failed"
        ((errors++))
    fi
    
    return $errors
}

# Test 9: Log files and monitoring
test_logging() {
    local errors=0
    
    # Check service logs
    if journalctl -u $SERVICE_NAME --no-pager -n 1 &>/dev/null; then
        echo "  - Service logs: Available"
        local log_errors=$(journalctl -u $SERVICE_NAME --no-pager -n 50 | grep -i error | wc -l)
        echo "  - Recent errors in logs: $log_errors"
        if [[ $log_errors -gt 5 ]]; then
            echo "  - Warning: Many errors in recent logs"
            ((errors++))
        fi
    else
        echo "  - Service logs: Not available"
        ((errors++))
    fi
    
    # Check MySQL logs
    if [[ -f /var/log/mysql/error.log ]]; then
        echo "  - MySQL error log: Exists"
        local mysql_errors=$(tail -50 /var/log/mysql/error.log | grep -i error | wc -l)
        echo "  - Recent MySQL errors: $mysql_errors"
    else
        echo "  - MySQL error log: Not found"
    fi
    
    return $errors
}

# Test 10: Web interface functionality
test_web_interface() {
    local errors=0
    
    # Test main page
    if curl -s http://localhost:$WEB_PORT/ | grep -q "Body Composition Gateway"; then
        echo "  - Main page: Loading correctly"
    else
        echo "  - Main page: Not loading correctly"
        ((errors++))
    fi
    
    # Test API endpoints
    local api_endpoints=(
        "/api/system/status"
        "/api/devices/scan"
        "/api/measurements/latest"
    )
    
    for endpoint in "${api_endpoints[@]}"; do
        if curl -s "http://localhost:$WEB_PORT$endpoint" | grep -q "{"; then
            echo "  - API endpoint $endpoint: OK"
        else
            echo "  - API endpoint $endpoint: Failed"
            ((errors++))
        fi
    done
    
    # Test WebSocket (basic check)
    if netstat -tlnp 2>/dev/null | grep ":$WEB_PORT " | grep -q python; then
        echo "  - WebSocket service: Running"
    else
        echo "  - WebSocket service: Not detected"
        ((errors++))
    fi
    
    return $errors
}

# Generate test report
generate_report() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local report_file="$APP_DIR/system_test_report_$(date +%Y%m%d_%H%M%S).txt"
    
    cat > "$report_file" << EOF
Body Composition Gateway - System Test Report
=============================================

Test Date: $timestamp
System: $(cat /proc/device-tree/model 2>/dev/null || echo "Unknown")
OS: $(lsb_release -d 2>/dev/null | cut -f2 || echo "Unknown")

Test Results Summary:
- Total Tests: $TOTAL_TESTS
- Passed: $PASSED_TESTS
- Failed: $FAILED_TESTS
- Success Rate: $(( (PASSED_TESTS * 100) / TOTAL_TESTS ))%

System Status:
- MySQL Service: $(systemctl is-active mysql)
- Web Service: $(systemctl is-active $SERVICE_NAME)
- Web URL: http://$(hostname -I | awk '{print $1}'):$WEB_PORT
- Application Directory: $APP_DIR

$(if [[ $FAILED_TESTS -eq 0 ]]; then
    echo "✅ All tests passed! System is ready for use."
else
    echo "❌ Some tests failed. Please review the issues above."
    echo ""
    echo "Common Solutions:"
    echo "- Restart services: sudo systemctl restart $SERVICE_NAME mysql"
    echo "- Check logs: sudo journalctl -u $SERVICE_NAME -f"
    echo "- Verify USB device connection"
    echo "- Check network connectivity"
fi)

For support, check the logs and configuration files in $APP_DIR
EOF

    echo
    log_info "Test report saved to: $report_file"
}

# Main test function
main() {
    clear
    echo
    log_info "=================================================================="
    log_info "    Body Composition Gateway - System Test"
    log_info "    Verifying installation and configuration"
    log_info "=================================================================="
    echo
    
    # Run all tests
    run_test "System Requirements" test_system_requirements
    run_test "MySQL Installation" test_mysql
    run_test "Python Environment" test_python_environment
    run_test "Web Service" test_web_service
    run_test "USB Permissions" test_usb_permissions
    run_test "Database Structure" test_database_structure
    run_test "System Performance" test_system_performance
    run_test "Network Connectivity" test_network_connectivity
    run_test "Logging" test_logging
    run_test "Web Interface" test_web_interface
    
    # Show summary
    echo
    echo "=================================================================="
    echo -e "${BLUE}Test Summary:${NC}"
    echo "  Total Tests: $TOTAL_TESTS"
    echo -e "  Passed: ${GREEN}$PASSED_TESTS${NC}"
    echo -e "  Failed: ${RED}$FAILED_TESTS${NC}"
    echo -e "  Success Rate: $(( (PASSED_TESTS * 100) / TOTAL_TESTS ))%"
    echo "=================================================================="
    
    if [[ $FAILED_TESTS -eq 0 ]]; then
        echo
        log_success "🎉 All tests passed! System is ready for use."
        echo
        echo -e "${GREEN}✅ You can now:${NC}"
        echo "  1. Access web interface: http://$(hostname -I | awk '{print $1}'):5000"
        echo "  2. Connect your Tanita MC-780MA device via USB"
        echo "  3. Start measuring and monitoring"
        echo
    else
        echo
        log_fail "❌ Some tests failed. Please review and fix the issues."
        echo
        echo -e "${YELLOW}💡 Quick fixes:${NC}"
        echo "  • Restart services: sudo systemctl restart $SERVICE_NAME mysql"
        echo "  • Check logs: sudo journalctl -u $SERVICE_NAME -f"
        echo "  • Verify device connections"
        echo "  • Check network settings"
        echo
    fi
    
    # Generate detailed report
    generate_report
    
    echo -e "${BLUE}📋 For detailed information, check:${NC}"
    echo "  • Service status: sudo systemctl status $SERVICE_NAME"
    echo "  • Service logs: sudo journalctl -u $SERVICE_NAME -f"
    echo "  • Application directory: $APP_DIR"
    echo "  • Configuration: $APP_DIR/config.yaml"
    echo
}

# Check if script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi