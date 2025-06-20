#!/usr/bin/env python3
"""
Enhanced Body Composition Gateway - Raspberry Pi Application
Advanced Tanita MC-780MA Integration with Modern Web Interface
Compatible with Actiwell Fitness Management System
"""

from flask import Flask, render_template, jsonify, request, send_file, flash, redirect, url_for
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import mysql.connector
from mysql.connector import Error
import serial
import time
import threading
import json
import queue
import logging
from datetime import datetime, timedelta
import os
import glob
import re
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
import schedule
import requests
import hashlib
import jwt
from functools import wraps
import asyncio
import websockets

# Configure enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/body_composition_gateway.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Enhanced Configuration
class Config:
    # Database Configuration
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER', 'body_comp_user')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'body_comp_pass')
    DB_NAME = os.getenv('DB_NAME', 'body_composition_db')
    DB_POOL_SIZE = 10
    
    # Serial Configuration
    TANITA_BAUDRATE = 9600
    INBODY_BAUDRATE = 9600
    SERIAL_TIMEOUT = 2
    AUTO_DETECT_DEVICES = True
    
    # Actiwell Integration
    ACTIWELL_API_URL = os.getenv('ACTIWELL_API_URL', 'https://api.actiwell.com')
    ACTIWELL_API_KEY = os.getenv('ACTIWELL_API_KEY', '')
    ACTIWELL_LOCATION_ID = os.getenv('ACTIWELL_LOCATION_ID', '')
    
    # Security
    SECRET_KEY = os.getenv('SECRET_KEY', 'tanita-gateway-secret-key')
    API_TOKEN_EXPIRE_HOURS = 24
    
    # File Storage
    DATA_STORAGE_PATH = '/home/pi/body_composition_data'
    MAX_STORAGE_DAYS = 30
    BACKUP_ENABLED = True
    
    # Web Interface
    WEB_PORT = 5000
    WEB_HOST = '0.0.0.0'
    ENABLE_REALTIME = True

# Initialize Flask App with enhanced features
app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*") if Config.ENABLE_REALTIME else None

# Enhanced data classes
@dataclass
class TanitaResult:
    """Enhanced Tanita measurement with validation"""
    # Device info
    device_id: str = ""
    customer_phone: str = ""
    measurement_timestamp: datetime = None
    
    # Personal info
    gender: str = ""
    age: int = 0
    height_cm: float = 0.0
    
    # Core measurements
    weight_kg: float = 0.0
    bmi: float = 0.0
    body_fat_percent: float = 0.0
    muscle_mass_kg: float = 0.0
    bone_mass_kg: float = 0.0
    total_body_water_percent: float = 0.0
    visceral_fat_rating: int = 0
    metabolic_age: int = 0
    bmr_kcal: int = 0
    
    # Advanced metrics
    protein_percent: float = 0.0
    mineral_percent: float = 0.0
    subcutaneous_fat_percent: float = 0.0
    
    # Quality indicators
    measurement_quality: str = "good"  # excellent, good, fair, poor
    impedance_stability: bool = True
    
    # Calculated scores
    health_score: int = 0
    fitness_level: str = ""
    
    def to_dict(self):
        result = asdict(self)
        if self.measurement_timestamp:
            result['measurement_timestamp'] = self.measurement_timestamp.isoformat()
        return result
    
    def validate(self) -> List[str]:
        """Validate measurement data and return error messages"""
        errors = []
        
        if not self.customer_phone or len(self.customer_phone) < 10:
            errors.append("Valid customer phone number required")
        
        if self.weight_kg <= 0 or self.weight_kg > 300:
            errors.append("Weight must be between 0-300 kg")
        
        if self.age <= 0 or self.age > 120:
            errors.append("Age must be between 0-120 years")
        
        if self.height_cm <= 0 or self.height_cm > 250:
            errors.append("Height must be between 0-250 cm")
        
        return errors

# Enhanced Database Manager
class DatabaseManager:
    def __init__(self):
        self.connection_pool = []
        self.pool_size = Config.DB_POOL_SIZE
        self._create_pool()
    
    def _create_pool(self):
        """Create database connection pool"""
        for _ in range(self.pool_size):
            try:
                connection = mysql.connector.connect(
                    host=Config.DB_HOST,
                    user=Config.DB_USER,
                    password=Config.DB_PASSWORD,
                    database=Config.DB_NAME,
                    autocommit=True,
                    charset='utf8mb4',
                    use_unicode=True
                )
                self.connection_pool.append(connection)
            except Error as e:
                logger.error(f"Database connection error: {e}")
    
    def get_connection(self):
        """Get connection from pool"""
        if self.connection_pool:
            return self.connection_pool.pop()
        return self._create_new_connection()
    
    def return_connection(self, connection):
        """Return connection to pool"""
        if len(self.connection_pool) < self.pool_size:
            self.connection_pool.append(connection)
        else:
            connection.close()
    
    def _create_new_connection(self):
        """Create new database connection"""
        return mysql.connector.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            autocommit=True,
            charset='utf8mb4',
            use_unicode=True
        )
    
    def execute_query(self, query: str, params: tuple = None):
        """Execute query with connection pooling"""
        connection = self.get_connection()
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute(query, params)
            result = cursor.fetchall()
            cursor.close()
            return result
        except Error as e:
            logger.error(f"Database query error: {e}")
            raise
        finally:
            self.return_connection(connection)
    
    def execute_update(self, query: str, params: tuple = None):
        """Execute update/insert query"""
        connection = self.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(query, params)
            connection.commit()
            last_id = cursor.lastrowid
            cursor.close()
            return last_id
        except Error as e:
            logger.error(f"Database update error: {e}")
            connection.rollback()
            raise
        finally:
            self.return_connection(connection)

# Enhanced Device Manager
class DeviceManager:
    def __init__(self):
        self.devices = {}
        self.device_status = {}
        self.measurement_queue = queue.Queue()
        self.stop_monitoring = False
        
    def auto_detect_devices(self):
        """Auto-detect connected Tanita and InBody devices"""
        detected_devices = {}
        
        # Scan USB serial ports
        for port in glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*'):
            try:
                ser = serial.Serial(port, 9600, timeout=1)
                # Send device identification command
                ser.write(b'ID\r\n')
                time.sleep(0.5)
                response = ser.read(100).decode('utf-8', errors='ignore')
                ser.close()
                
                if 'tanita' in response.lower() or 'mc-780' in response.lower():
                    detected_devices[port] = 'tanita'
                    logger.info(f"Detected Tanita device on {port}")
                elif 'inbody' in response.lower():
                    detected_devices[port] = 'inbody'
                    logger.info(f"Detected InBody device on {port}")
                    
            except Exception as e:
                logger.debug(f"Could not detect device on {port}: {e}")
        
        return detected_devices
    
    def start_monitoring(self):
        """Start device monitoring in background thread"""
        if Config.AUTO_DETECT_DEVICES:
            self.devices = self.auto_detect_devices()
        
        monitor_thread = threading.Thread(target=self._monitor_devices)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        logger.info("Device monitoring started")
    
    def _monitor_devices(self):
        """Monitor devices for incoming measurements"""
        while not self.stop_monitoring:
            for port, device_type in self.devices.items():
                try:
                    if device_type == 'tanita':
                        self._check_tanita_device(port)
                    elif device_type == 'inbody':
                        self._check_inbody_device(port)
                except Exception as e:
                    logger.error(f"Error monitoring {device_type} on {port}: {e}")
                    self.device_status[port] = 'error'
            
            time.sleep(1)  # Check every second
    
    def _check_tanita_device(self, port):
        """Check Tanita device for new measurements"""
        try:
            ser = serial.Serial(port, Config.TANITA_BAUDRATE, timeout=Config.SERIAL_TIMEOUT)
            
            # Check if data is available
            if ser.in_waiting > 0:
                raw_data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                
                if raw_data.strip():
                    measurement = self._parse_tanita_data(raw_data)
                    if measurement:
                        self.measurement_queue.put(measurement)
                        
                        # Emit real-time update if enabled
                        if socketio:
                            socketio.emit('new_measurement', measurement.to_dict())
            
            ser.close()
            self.device_status[port] = 'connected'
            
        except Exception as e:
            logger.error(f"Tanita device error on {port}: {e}")
            self.device_status[port] = 'error'
    
    def _parse_tanita_data(self, raw_data: str) -> Optional[TanitaResult]:
        """Parse Tanita raw data into structured format"""
        try:
            lines = raw_data.strip().split('\n')
            measurement = TanitaResult()
            measurement.measurement_timestamp = datetime.now()
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Parse different data fields based on Tanita protocol
                if line.startswith('ID:'):
                    measurement.customer_phone = line.split(':')[1].strip()
                elif line.startswith('WT:'):
                    measurement.weight_kg = float(line.split(':')[1].strip())
                elif line.startswith('BF:'):
                    measurement.body_fat_percent = float(line.split(':')[1].strip())
                elif line.startswith('MM:'):
                    measurement.muscle_mass_kg = float(line.split(':')[1].strip())
                elif line.startswith('BW:'):
                    measurement.total_body_water_percent = float(line.split(':')[1].strip())
                elif line.startswith('VF:'):
                    measurement.visceral_fat_rating = int(line.split(':')[1].strip())
                elif line.startswith('MA:'):
                    measurement.metabolic_age = int(line.split(':')[1].strip())
                elif line.startswith('BMR:'):
                    measurement.bmr_kcal = int(line.split(':')[1].strip())
                elif line.startswith('BMI:'):
                    measurement.bmi = float(line.split(':')[1].strip())
            
            # Validate measurement
            errors = measurement.validate()
            if errors:
                logger.warning(f"Measurement validation errors: {errors}")
                return None
            
            return measurement
            
        except Exception as e:
            logger.error(f"Error parsing Tanita data: {e}")
            return None

# Enhanced API Manager
class ActiwellAPI:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.api_url = Config.ACTIWELL_API_URL
        self.api_key = Config.ACTIWELL_API_KEY
        self.location_id = Config.ACTIWELL_LOCATION_ID
        
    def sync_measurement_to_actiwell(self, measurement: TanitaResult) -> bool:
        """Sync measurement data to Actiwell backend"""
        try:
            # Find customer in Actiwell database by phone number
            customer = self._find_customer_by_phone(measurement.customer_phone)
            if not customer:
                logger.warning(f"Customer not found for phone: {measurement.customer_phone}")
                return False
            
            # Prepare payload for Actiwell API
            payload = {
                'customer_id': customer['id'],
                'location_id': self.location_id,
                'measurement_date': measurement.measurement_timestamp.isoformat(),
                'device_type': 'tanita_mc780ma',
                'measurements': {
                    'weight_kg': measurement.weight_kg,
                    'bmi': measurement.bmi,
                    'body_fat_percent': measurement.body_fat_percent,
                    'muscle_mass_kg': measurement.muscle_mass_kg,
                    'bone_mass_kg': measurement.bone_mass_kg,
                    'total_body_water_percent': measurement.total_body_water_percent,
                    'visceral_fat_rating': measurement.visceral_fat_rating,
                    'metabolic_age': measurement.metabolic_age,
                    'bmr_kcal': measurement.bmr_kcal,
                    'health_score': measurement.health_score,
                    'fitness_level': measurement.fitness_level
                }
            }
            
            # Send to Actiwell API
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'X-Location-ID': self.location_id
            }
            
            response = requests.post(
                f'{self.api_url}/api/v1/body-composition-measurements',
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 201:
                logger.info(f"Measurement synced to Actiwell for customer {customer['id']}")
                return True
            else:
                logger.error(f"Actiwell API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error syncing to Actiwell: {e}")
            return False
    
    def _find_customer_by_phone(self, phone: str) -> Optional[Dict]:
        """Find customer in local database by phone number"""
        try:
            # Clean phone number
            clean_phone = re.sub(r'\D', '', phone)
            
            query = """
            SELECT id, phone, name, email 
            FROM customers 
            WHERE REPLACE(phone, ' ', '') LIKE %s 
               OR REPLACE(phone, '-', '') LIKE %s
               OR REPLACE(phone, '+84', '0') LIKE %s
            LIMIT 1
            """
            
            result = self.db_manager.execute_query(
                query, 
                (f'%{clean_phone}%', f'%{clean_phone}%', f'%{clean_phone}%')
            )
            
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Error finding customer: {e}")
            return None

# Initialize global managers
db_manager = DatabaseManager()
device_manager = DeviceManager()
actiwell_api = ActiwellAPI(db_manager)

# Authentication decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token invalid'}), 401
        
        return f(*args, **kwargs)
    return decorated

# Enhanced Web Routes
@app.route('/')
def dashboard():
    """Main dashboard with real-time monitoring"""
    return render_template('dashboard.html')

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """API authentication endpoint"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    # Simple authentication (enhance with proper user management)
    if username == 'admin' and password == 'admin123':
        token = jwt.encode({
            'user': username,
            'exp': datetime.utcnow() + timedelta(hours=Config.API_TOKEN_EXPIRE_HOURS)
        }, Config.SECRET_KEY, algorithm='HS256')
        
        return jsonify({'token': token})
    
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/devices/status')
@token_required
def api_device_status():
    """Get current device status"""
    return jsonify({
        'devices': device_manager.devices,
        'status': device_manager.device_status,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/measurements/latest')
@token_required
def api_latest_measurements():
    """Get latest measurements"""
    try:
        query = """
        SELECT * FROM tanita_measurements 
        ORDER BY created_at DESC 
        LIMIT 50
        """
        measurements = db_manager.execute_query(query)
        
        return jsonify({
            'measurements': measurements,
            'count': len(measurements)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/measurements/customer/<phone>')
@token_required
def api_customer_measurements(phone):
    """Get measurements for specific customer"""
    try:
        query = """
        SELECT * FROM tanita_measurements 
        WHERE extracted_phone_number = %s 
        ORDER BY created_at DESC
        """
        measurements = db_manager.execute_query(query, (phone,))
        
        return jsonify({
            'customer_phone': phone,
            'measurements': measurements,
            'count': len(measurements)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/measurements/sync', methods=['POST'])
@token_required
def api_sync_measurements():
    """Manually trigger sync to Actiwell"""
    try:
        data = request.get_json()
        measurement_id = data.get('measurement_id')
        
        if measurement_id:
            # Sync specific measurement
            query = "SELECT * FROM tanita_measurements WHERE id = %s"
            result = db_manager.execute_query(query, (measurement_id,))
            
            if result:
                # Convert to TanitaResult and sync
                measurement_data = result[0]
                # Create TanitaResult object from database data
                # ... implementation details
                
                success = actiwell_api.sync_measurement_to_actiwell(measurement)
                return jsonify({'success': success})
        
        return jsonify({'error': 'Measurement not found'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics/summary')
@token_required
def api_analytics_summary():
    """Get analytics summary"""
    try:
        # Get daily measurements count
        daily_query = """
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM tanita_measurements 
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        """
        daily_stats = db_manager.execute_query(daily_query)
        
        # Get average measurements
        avg_query = """
        SELECT 
            AVG(weight_kg) as avg_weight,
            AVG(body_fat_percent) as avg_body_fat,
            AVG(muscle_mass_kg) as avg_muscle_mass,
            COUNT(*) as total_measurements
        FROM tanita_measurements 
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        """
        avg_stats = db_manager.execute_query(avg_query)
        
        return jsonify({
            'daily_measurements': daily_stats,
            'averages': avg_stats[0] if avg_stats else {},
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Real-time WebSocket events
if socketio:
    @socketio.on('connect')
    def handle_connect():
        logger.info('Client connected to WebSocket')
        emit('status', {'message': 'Connected to Body Composition Gateway'})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info('Client disconnected from WebSocket')

# Background measurement processor
def process_measurements():
    """Process measurements from queue"""
    while True:
        try:
            if not device_manager.measurement_queue.empty():
                measurement = device_manager.measurement_queue.get()
                
                # Save to database
                save_measurement_to_db(measurement)
                
                # Sync to Actiwell
                actiwell_api.sync_measurement_to_actiwell(measurement)
                
                logger.info(f"Processed measurement for {measurement.customer_phone}")
        except Exception as e:
            logger.error(f"Error processing measurement: {e}")
        
        time.sleep(0.5)

def save_measurement_to_db(measurement: TanitaResult):
    """Save measurement to database"""
    try:
        query = """
        INSERT INTO tanita_measurements (
            customer_id, extracted_phone_number, measurement_timestamp,
            weight_kg, bmi, body_fat_percent, muscle_mass_kg, bone_mass_kg,
            total_body_water_percent, visceral_fat_rating, metabolic_age,
            bmr_kcal, health_score, fitness_level, raw_data, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """
        
        params = (
            measurement.customer_phone,
            measurement.customer_phone,
            measurement.measurement_timestamp,
            measurement.weight_kg,
            measurement.bmi,
            measurement.body_fat_percent,
            measurement.muscle_mass_kg,
            measurement.bone_mass_kg,
            measurement.total_body_water_percent,
            measurement.visceral_fat_rating,
            measurement.metabolic_age,
            measurement.bmr_kcal,
            measurement.health_score,
            measurement.fitness_level,
            json.dumps(measurement.to_dict())
        )
        
        db_manager.execute_update(query, params)
        logger.info(f"Measurement saved to database for {measurement.customer_phone}")
        
    except Exception as e:
        logger.error(f"Error saving measurement to database: {e}")

# Application startup
if __name__ == '__main__':
    # Start device monitoring
    device_manager.start_monitoring()
    
    # Start measurement processor
    processor_thread = threading.Thread(target=process_measurements)
    processor_thread.daemon = True
    processor_thread.start()
    
    logger.info("Body Composition Gateway started successfully")
    
    # Start Flask application
    if socketio:
        socketio.run(app, host=Config.WEB_HOST, port=Config.WEB_PORT, debug=False)
    else:
        app.run(host=Config.WEB_HOST, port=Config.WEB_PORT, debug=False)