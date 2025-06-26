#!/bin/bash
# InBody 370s HL7 Integration Test Suite
# Professional testing framework for production environment

set -e

# Colors and formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$PROJECT_ROOT/test_results"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
TEST_REPORT="$TEST_DIR/inbody_test_report_$TIMESTAMP.txt"

# Test configuration
INBODY_IP="${INBODY_IP:-192.168.1.100}"
PI_IP="${PI_IP:-192.168.1.50}"
DATA_PORT="${DATA_PORT:-2575}"
LISTENING_PORT="${LISTENING_PORT:-2580}"
TEST_PHONE="${TEST_PHONE:-0965385123}"

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Utility functions
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_info() {
    log "${BLUE}[INFO]${NC} $1"
}

log_success() {
    log "${GREEN}[✓ PASS]${NC} $1"
    ((PASSED_TESTS++))
}

log_fail() {
    log "${RED}[✗ FAIL]${NC} $1"
    ((FAILED_TESTS++))
}

log_warning() {
    log "${YELLOW}[⚠ WARN]${NC} $1"
}

print_header() {
    clear
    echo -e "${PURPLE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║            InBody 370s HL7 Integration Test Suite           ║"
    echo "║                Professional Testing Framework                ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo "Test Configuration:"
    echo "  • InBody Device IP: $INBODY_IP"
    echo "  • Raspberry Pi IP: $PI_IP"
    echo "  • Data Port: $DATA_PORT"
    echo "  • Listening Port: $LISTENING_PORT"
    echo "  • Test Phone: $TEST_PHONE"
    echo "  • Test Report: $TEST_REPORT"
    echo ""
}

init_test_environment() {
    log_info "Initializing test environment..."
    
    # Create test directories
    mkdir -p "$TEST_DIR"
    mkdir -p "$PROJECT_ROOT/logs"
    
    # Initialize test report
    cat > "$TEST_REPORT" << EOF
InBody 370s HL7 Integration Test Report
======================================
Test Date: $(date)
Test Environment: $(hostname)
Project Root: $PROJECT_ROOT

Configuration:
- InBody Device IP: $INBODY_IP
- Raspberry Pi IP: $PI_IP
- Data Port: $DATA_PORT
- Listening Port: $LISTENING_PORT

Test Results:
=============
EOF
}

write_test_result() {
    local test_name="$1"
    local result="$2"
    local details="$3"
    
    echo "[$result] $test_name" >> "$TEST_REPORT"
    if [ -n "$details" ]; then
        echo "    Details: $details" >> "$TEST_REPORT"
    fi
    echo "" >> "$TEST_REPORT"
}

run_test() {
    local test_name="$1"
    local test_function="$2"
    
    ((TOTAL_TESTS++))
    log_info "Running test: $test_name"
    
    if $test_function; then
        log_success "$test_name"
        write_test_result "$test_name" "PASS" ""
        return 0
    else
        log_fail "$test_name"
        write_test_result "$test_name" "FAIL" "$?"
        return 1
    fi
}

# Test functions
test_system_prerequisites() {
    local errors=0
    
    # Check Python 3
    if command -v python3 &> /dev/null; then
        log_info "Python 3: $(python3 --version)"
    else
        log_fail "Python 3 not found"
        ((errors++))
    fi
    
    # Check required Python packages
    local packages=("socket" "threading" "json" "datetime" "logging" "configparser")
    for package in "${packages[@]}"; do
        if python3 -c "import $package" 2>/dev/null; then
            log_info "Python package $package: Available"
        else
            log_fail "Python package $package: Missing"
            ((errors++))
        fi
    done
    
    # Check project structure
    local required_dirs=("actiwell_backend" "actiwell_backend/devices" "actiwell_backend/services" "test_scripts")
    for dir in "${required_dirs[@]}"; do
        if [ -d "$PROJECT_ROOT/$dir" ]; then
            log_info "Directory $dir: Exists"
        else
            log_fail "Directory $dir: Missing"
            ((errors++))
        fi
    done
    
    # Check configuration file
    if [ -f "$PROJECT_ROOT/config.py" ]; then
        log_info "Configuration file: Found"
        # Test configuration loading
        if python3 -c "import sys; sys.path.append('$PROJECT_ROOT'); import config" 2>/dev/null; then
            log_info "Configuration loading: OK"
        else
            log_fail "Configuration loading: Failed"
            ((errors++))
        fi
    else
        log_fail "Configuration file: Missing"
        ((errors++))
    fi
    
    return $errors
}

test_network_connectivity() {
    local errors=0
    
    # Test ping to InBody device
    if ping -c 3 -W 5 "$INBODY_IP" >/dev/null 2>&1; then
        log_info "Ping to InBody ($INBODY_IP): Success"
    else
        log_fail "Ping to InBody ($INBODY_IP): Failed"
        ((errors++))
    fi
    
    # Test local network interface
    local local_ip=$(hostname -I | awk '{print $1}')
    if [ -n "$local_ip" ]; then
        log_info "Local IP address: $local_ip"
    else
        log_fail "No network interface found"
        ((errors++))
    fi
    
    # Test internet connectivity
    if ping -c 1 -W 5 8.8.8.8 >/dev/null 2>&1; then
        log_info "Internet connectivity: Available"
    else
        log_warning "Internet connectivity: Not available"
    fi
    
    return $errors
}

test_port_availability() {
    local errors=0
    
    # Test InBody listening port
    if timeout 5 bash -c "</dev/tcp/$INBODY_IP/$LISTENING_PORT" 2>/dev/null; then
        log_info "InBody listening port ($LISTENING_PORT): Accessible"
    else
        log_fail "InBody listening port ($LISTENING_PORT): Not accessible"
        ((errors++))
    fi
    
    # Test data port availability
    if netstat -tlnp 2>/dev/null | grep -q ":$DATA_PORT "; then
        log_warning "Data port ($DATA_PORT): Already in use"
    else
        log_info "Data port ($DATA_PORT): Available"
        # Test if we can bind to the port
        if python3 -c "
import socket
s = socket.socket()
try:
    s.bind(('0.0.0.0', $DATA_PORT))
    s.close()
    print('Bind test: Success')
except Exception as e:
    print(f'Bind test: Failed - {e}')
    exit(1)
" 2>/dev/null; then
            log_info "Port binding test: Success"
        else
            log_fail "Port binding test: Failed"
            ((errors++))
        fi
    fi
    
    return $errors
}

test_hl7_message_parsing() {
    local errors=0
    
    log_info "Testing HL7 message parsing..."
    
    # Create test HL7 message
    local test_message="MSH|^~\\&|INBODY370S|DEVICE|ACTIWELL|RASPBERRY_PI|20250125120000||ORU^R01^ORU_R01|MSG1234|P|2.5\rPID|1||$TEST_PHONE^^^PHONE||NGUYEN^VAN^A||19850315|M\rOBR|1|MSG1234|MSG1234|BODYCOMP^Body Composition Analysis^LOCAL|||20250125120000\rOBX|1|NM|WT^Weight^LOCAL||68.5|kg|||||F\rOBX|2|NM|HT^Height^LOCAL||170.0|cm|||||F\rOBX|3|NM|BMI^Body Mass Index^LOCAL||23.7|kg/m2|||||F\rNTE|1||Test measurement completed"
    
    # Test parsing with Python
    if python3 << EOF
import sys
sys.path.append('$PROJECT_ROOT')
try:
    from actiwell_backend.devices.inbody_370s_handler import HL7MessageParser
    
    parser = HL7MessageParser()
    measurement = parser.parse_message('$test_message')
    
    if measurement and measurement.phone_number == '$TEST_PHONE':
        print('HL7 parsing: Success')
        print(f'Parsed phone: {measurement.phone_number}')
        print(f'Parsed weight: {measurement.weight_kg}')
        exit(0)
    else:
        print('HL7 parsing: Failed - Invalid parsed data')
        exit(1)
except Exception as e:
    print(f'HL7 parsing: Failed - {e}')
    exit(1)
EOF
    then
        log_info "HL7 message parsing: Success"
    else
        log_fail "HL7 message parsing: Failed"
        ((errors++))
    fi
    
    return $errors
}

test_database_connection() {
    local errors=0
    
    log_info "Testing database connection..."
    
    # Test database connectivity
    if python3 << EOF
import sys
sys.path.append('$PROJECT_ROOT')
try:
    from config import DATABASE_CONFIG
    import mysql.connector
    
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if result:
        print('Database connection: Success')
        exit(0)
    else:
        print('Database connection: Failed - No result')
        exit(1)
except Exception as e:
    print(f'Database connection: Failed - {e}')
    exit(1)
EOF
    then
        log_info "Database connection: Success"
    else
        log_fail "Database connection: Failed"
        ((errors++))
    fi
    
    return $errors
}

test_inbody_handler_initialization() {
    local errors=0
    
    log_info "Testing InBody handler initialization..."
    
    if python3 << EOF
import sys
sys.path.append('$PROJECT_ROOT')
try:
    from actiwell_backend.devices.inbody_370s_handler import InBody370sHandler
    from actiwell_backend.core.database_manager import DatabaseManager
    from config import INBODY_CONFIG, DATABASE_CONFIG
    
    # Initialize database manager
    db_manager = DatabaseManager(DATABASE_CONFIG)
    
    # Initialize InBody handler
    handler = InBody370sHandler(INBODY_CONFIG, db_manager)
    
    # Check configuration
    if handler.data_port == $DATA_PORT and handler.listening_port == $LISTENING_PORT:
        print('InBody handler initialization: Success')
        print(f'Data port: {handler.data_port}')
        print(f'Listening port: {handler.listening_port}')
        exit(0)
    else:
        print('InBody handler initialization: Failed - Invalid configuration')
        exit(1)
except Exception as e:
    print(f'InBody handler initialization: Failed - {e}')
    exit(1)
EOF
    then
        log_info "InBody handler initialization: Success"
    else
        log_fail "InBody handler initialization: Failed"
        ((errors++))
    fi
    
    return $errors
}

test_hl7_server_startup() {
    local errors=0
    
    log_info "Testing HL7 server startup..."
    
    # Start HL7 server in background for testing
    local server_pid=""
    
    if python3 << EOF &
import sys
sys.path.append('$PROJECT_ROOT')
import time
import signal
import os

def signal_handler(sig, frame):
    print('HL7 server test: Stopped by signal')
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)

try:
    from actiwell_backend.devices.inbody_370s_handler import InBody370sHandler
    from config import INBODY_CONFIG
    
    handler = InBody370sHandler(INBODY_CONFIG)
    
    if handler.start():
        print('HL7 server startup: Success')
        time.sleep(5)  # Run for 5 seconds
        handler.stop()
        exit(0)
    else:
        print('HL7 server startup: Failed')
        exit(1)
except Exception as e:
    print(f'HL7 server startup: Failed - {e}')
    exit(1)
EOF
    then
        server_pid=$!
        sleep 2
        
        # Check if server is listening
        if netstat -tlnp 2>/dev/null | grep -q ":$DATA_PORT "; then
            log_info "HL7 server listening on port $DATA_PORT: Success"
        else
            log_fail "HL7 server not listening on port $DATA_PORT"
            ((errors++))
        fi
        
        # Stop the test server
        if [ -n "$server_pid" ]; then
            kill -TERM "$server_pid" 2>/dev/null || true
            wait "$server_pid" 2>/dev/null || true
        fi
    else
        log_fail "HL7 server startup: Failed"
        ((errors++))
    fi
    
    return $errors
}

test_hl7_message_simulation() {
    local errors=0
    
    log_info "Testing HL7 message simulation..."
    
    # Start a simple HL7 listener for testing
    python3 << 'EOF' &
import socket
import threading
import time
import sys

def hl7_listener():
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', 12575))  # Use test port
        server.listen(1)
        
        print('Test HL7 listener started on port 12575')
        
        # Wait for connection with timeout
        server.settimeout(10)
        client, addr = server.accept()
        
        # Receive data
        data = client.recv(4096)
        if data and b'INBODY370S' in data:
            print('HL7 message simulation: Success')
            # Send ACK
            ack = b"MSH|^~\\&|TEST|SYSTEM|INBODY370S|DEVICE|20250125120000||ACK^R01^ACK|ACK123|P|2.5\rMSA|AA|ACK123|Message accepted\r\x1C\r"
            client.send(ack)
        else:
            print('HL7 message simulation: Failed - Invalid data')
        
        client.close()
        server.close()
        
    except Exception as e:
        print(f'HL7 message simulation: Failed - {e}')

# Start listener in background
threading.Thread(target=hl7_listener, daemon=True).start()
time.sleep(15)  # Keep running for 15 seconds
EOF
    
    local listener_pid=$!
    sleep 2
    
    # Send test HL7 message
    if python3 << EOF
import socket
import time

try:
    # Create test message
    message = '''MSH|^~\\&|INBODY370S|DEVICE|TEST|SYSTEM|20250125120000||ORU^R01^ORU_R01|MSG1234|P|2.5\rPID|1||$TEST_PHONE^^^PHONE||TEST^USER||19850315|M\rOBR|1|MSG1234|MSG1234|BODYCOMP^Body Composition Test^LOCAL|||20250125120000\rOBX|1|NM|WT^Weight^LOCAL||70.5|kg|||||F\rOBX|2|NM|BMI^Body Mass Index^LOCAL||24.2|kg/m2|||||F\rNTE|1||Test message from simulation'''
    
    # Connect and send
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect(('localhost', 12575))
    
    # Send message with HL7 terminators
    full_message = message + '\r\x1C\r'
    sock.send(full_message.encode('utf-8'))
    
    # Wait for ACK
    response = sock.recv(1024)
    sock.close()
    
    if response and b'MSA|AA' in response:
        print('HL7 message sending: Success')
        exit(0)
    else:
        print('HL7 message sending: Failed - No ACK received')
        exit(1)
        
except Exception as e:
    print(f'HL7 message sending: Failed - {e}')
    exit(1)
EOF
    then
        log_info "HL7 message simulation: Success"
    else
        log_fail "HL7 message simulation: Failed"
        ((errors++))
    fi
    
    # Cleanup
    kill -TERM "$listener_pid" 2>/dev/null || true
    wait "$listener_pid" 2>/dev/null || true
    
    return $errors
}

test_configuration_validation() {
    local errors=0
    
    log_info "Testing configuration validation..."
    
    if python3 << EOF
import sys
sys.path.append('$PROJECT_ROOT')
try:
    from config import config
    
    # Validate configuration
    validation_results = config.validate_config()
    
    failed_validations = []
    for key, result in validation_results.items():
        if not result:
            failed_validations.append(key)
    
    if failed_validations:
        print(f'Configuration validation: Failed - {", ".join(failed_validations)}')
        exit(1)
    else:
        print('Configuration validation: Success')
        print(f'All {len(validation_results)} validation checks passed')
        exit(0)
        
except Exception as e:
    print(f'Configuration validation: Failed - {e}')
    exit(1)
EOF
    then
        log_info "Configuration validation: Success"
    else
        log_fail "Configuration validation: Failed"
        ((errors++))
    fi
    
    return $errors
}

generate_final_report() {
    local test_duration=$1
    
    # Append summary to test report
    cat >> "$TEST_REPORT" << EOF

Test Summary:
=============
Total Tests: $TOTAL_TESTS
Passed: $PASSED_TESTS
Failed: $FAILED_TESTS
Success Rate: $(( (PASSED_TESTS * 100) / TOTAL_TESTS ))%
Test Duration: ${test_duration}s

System Information:
==================
Hostname: $(hostname)
OS: $(uname -a)
Python Version: $(python3 --version 2>&1)
Current User: $(whoami)
Test Timestamp: $TIMESTAMP

Network Configuration:
=====================
Local IP: $(hostname -I | awk '{print $1}')
InBody Device IP: $INBODY_IP
Data Port: $DATA_PORT
Listening Port: $LISTENING_PORT

$(if [ $FAILED_TESTS -eq 0 ]; then
    echo "✅ All tests passed! InBody 370s integration is ready for production."
else
    echo "❌ Some tests failed. Please review the failures above and fix the issues."
fi)

Recommendations:
===============
$(if [ $FAILED_TESTS -eq 0 ]; then
    echo "1. Proceed with production deployment"
    echo "2. Configure InBody 370s device with network settings"
    echo "3. Test with real measurements"
    echo "4. Monitor logs for any issues"
else
    echo "1. Fix failed test cases"
    echo "2. Re-run test suite"
    echo "3. Check network connectivity"
    echo "4. Verify configuration settings"
fi)

For support and troubleshooting, refer to:
- Project documentation: $PROJECT_ROOT/docs/
- Log files: $PROJECT_ROOT/logs/
- Configuration: $PROJECT_ROOT/config.py
EOF
}

print_summary() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                        TEST SUMMARY                         ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo -e "${BLUE}Test Results:${NC}"
    echo "  Total Tests: $TOTAL_TESTS"
    echo -e "  Passed: ${GREEN}$PASSED_TESTS${NC}"
    echo -e "  Failed: ${RED}$FAILED_TESTS${NC}"
    echo -e "  Success Rate: $(( (PASSED_TESTS * 100) / TOTAL_TESTS ))%"
    echo ""
    echo -e "${BLUE}Test Report:${NC} $TEST_REPORT"
    echo ""
    
    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "${GREEN}🎉 All tests passed! InBody 370s integration is ready.${NC}"
        echo ""
        echo -e "${BLUE}Next Steps:${NC}"
        echo "  1. Configure InBody 370s device network settings"
        echo "  2. Start the integration service"
        echo "  3. Perform test measurements"
        echo "  4. Monitor system logs"
    else
        echo -e "${RED}❌ Some tests failed. Please fix the issues.${NC}"
        echo ""
        echo -e "${YELLOW}Troubleshooting:${NC}"
        echo "  1. Check network connectivity"
        echo "  2. Verify configuration settings"
        echo "  3. Review test report for details"
        echo "  4. Check system prerequisites"
    fi
    
    echo ""
}

# Main test execution
main() {
    local start_time=$(date +%s)
    
    print_header
    init_test_environment
    
    log_info "Starting InBody 370s HL7 Integration Test Suite..."
    echo ""
    
    # Run all tests
    run_test "System Prerequisites" test_system_prerequisites
    run_test "Network Connectivity" test_network_connectivity
    run_test "Port Availability" test_port_availability
    run_test "HL7 Message Parsing" test_hl7_message_parsing
    run_test "Database Connection" test_database_connection
    run_test "InBody Handler Initialization" test_inbody_handler_initialization
    run_test "HL7 Server Startup" test_hl7_server_startup
    run_test "HL7 Message Simulation" test_hl7_message_simulation
    run_test "Configuration Validation" test_configuration_validation
    
    local end_time=$(date +%s)
    local test_duration=$((end_time - start_time))
    
    generate_final_report $test_duration
    print_summary
    
    # Exit with appropriate code
    if [ $FAILED_TESTS -eq 0 ]; then
        exit 0
    else
        exit 1
    fi
}

# Handle script interruption
trap 'echo ""; log_warning "Test interrupted by user"; exit 130' INT

# Run main function
main "$@"