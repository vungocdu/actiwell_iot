# ====================================================================================
# ACTIWELL BODY MEASUREMENT BACKEND SERVER - COMPLETE SOURCE CODE
# ====================================================================================

# ====================================================================================
# 1. MAIN APPLICATION (app.py)
# ====================================================================================

#!/usr/bin/env python3
"""
Actiwell Body Measurement Backend Server
Complete system for Tanita & InBody device integration
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import mysql.connector
from mysql.connector import Error, pooling
import serial
import time
import threading
import queue
import logging
import json
import os
import glob
import jwt
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
import requests
import uuid
from functools import wraps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/actiwell_backend.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ====================================================================================
# 2. CONFIGURATION (config.py)
# ====================================================================================

class Config:
    """Application configuration"""
    
    # Database Configuration
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER', 'actiwell_user')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'actiwell_pass123')
    DB_NAME = os.getenv('DB_NAME', 'actiwell_measurements')
    DB_POOL_SIZE = 5
    
    # Actiwell API Configuration
    ACTIWELL_API_URL = os.getenv('ACTIWELL_API_URL', 'https://api.actiwell.com')
    ACTIWELL_API_KEY = os.getenv('ACTIWELL_API_KEY', '')
    ACTIWELL_LOCATION_ID = os.getenv('ACTIWELL_LOCATION_ID', '1')
    
    # Device Configuration
    TANITA_BAUDRATE = 9600
    INBODY_BAUDRATE = 9600
    DEVICE_TIMEOUT = 5
    AUTO_DETECT_DEVICES = True
    
    # Application Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'actiwell-secret-key-2024')
    JWT_EXPIRE_HOURS = 24
    WEB_PORT = 5000
    WEB_HOST = '0.0.0.0'
    
    # File Storage
    DATA_STORAGE_PATH = '/opt/actiwell/data'
    LOG_STORAGE_PATH = '/opt/actiwell/logs'

# ====================================================================================
# 3. DATA MODELS (models.py)
# ====================================================================================

@dataclass
class BodyMeasurement:
    """Body composition measurement data model"""
    
    # Device Info
    device_id: str = ""
    device_type: str = ""  # tanita, inbody
    measurement_uuid: str = ""
    
    # Customer Info
    customer_phone: str = ""
    customer_id: Optional[int] = None
    
    # Measurement Time
    measurement_timestamp: datetime = None
    
    # Basic Measurements
    weight_kg: float = 0.0
    height_cm: float = 0.0
    bmi: float = 0.0
    
    # Body Composition
    body_fat_percent: float = 0.0
    muscle_mass_kg: float = 0.0
    bone_mass_kg: float = 0.0
    total_body_water_percent: float = 0.0
    protein_percent: float = 0.0
    mineral_percent: float = 0.0
    
    # Advanced Metrics
    visceral_fat_rating: int = 0
    subcutaneous_fat_percent: float = 0.0
    skeletal_muscle_mass_kg: float = 0.0
    
    # Metabolic Data
    bmr_kcal: int = 0
    metabolic_age: int = 0
    
    # Segmental Analysis (for advanced devices)
    right_arm_muscle_kg: float = 0.0
    left_arm_muscle_kg: float = 0.0
    trunk_muscle_kg: float = 0.0
    right_leg_muscle_kg: float = 0.0
    left_leg_muscle_kg: float = 0.0
    
    # Quality Indicators
    measurement_quality: str = "good"  # excellent, good, fair, poor
    impedance_values: str = ""  # JSON string of impedance data
    
    # Sync Status
    synced_to_actiwell: bool = False
    sync_attempts: int = 0
    last_sync_attempt: Optional[datetime] = None
    sync_error_message: str = ""
    
    # Raw Data
    raw_data: str = ""
    processing_notes: str = ""
    
    def to_dict(self):
        """Convert to dictionary"""
        result = asdict(self)
        if self.measurement_timestamp:
            result['measurement_timestamp'] = self.measurement_timestamp.isoformat()
        if self.last_sync_attempt:
            result['last_sync_attempt'] = self.last_sync_attempt.isoformat()
        return result
    
    def validate(self) -> List[str]:
        """Validate measurement data"""
        errors = []
        
        if not self.customer_phone or len(self.customer_phone) < 10:
            errors.append("Valid customer phone required")
        
        if self.weight_kg <= 0 or self.weight_kg > 300:
            errors.append("Invalid weight value")
        
        if self.body_fat_percent < 0 or self.body_fat_percent > 60:
            errors.append("Invalid body fat percentage")
        
        return errors

@dataclass
class DeviceStatus:
    """Device status information"""
    device_id: str
    device_type: str  # tanita_mc780ma, inbody_270, etc.
    serial_port: str
    connection_status: str  # connected, disconnected, error
    firmware_version: str = ""
    last_heartbeat: Optional[datetime] = None
    last_measurement: Optional[datetime] = None
    total_measurements: int = 0
    error_count: int = 0
    configuration: Dict = None

# ====================================================================================
# 4. DATABASE MANAGER (database.py)
# ====================================================================================





# ====================================================================================
# 6. ACTIWELL API INTEGRATION (actiwell_api.py)
# ====================================================================================

class ActiwellAPI:
    """Actiwell API integration manager"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.api_url = Config.ACTIWELL_API_URL
        self.api_key = Config.ACTIWELL_API_KEY
        self.location_id = Config.ACTIWELL_LOCATION_ID
        
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'X-Location-ID': self.location_id
        }
    
    def find_customer_by_phone(self, phone: str) -> Optional[Dict]:
        """Find customer in Actiwell by phone number"""
        try:
            # Clean phone number
            clean_phone = phone.replace('+84', '0').replace('-', '').replace(' ', '')
            
            # Check local cache first
            connection = self.db_manager.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            query = """
                SELECT actiwell_customer_id, customer_name, customer_email
                FROM customer_mapping 
                WHERE phone_number = %s
                AND last_updated > DATE_SUB(NOW(), INTERVAL 1 DAY)
            """
            cursor.execute(query, (clean_phone,))
            cached_result = cursor.fetchone()
            
            cursor.close()
            connection.close()
            
            if cached_result:
                return {
                    'id': cached_result['actiwell_customer_id'],
                    'name': cached_result['customer_name'],
                    'email': cached_result['customer_email'],
                    'phone': phone
                }
            
            # Query Actiwell API
            url = f"{self.api_url}/api/customers/search"
            params = {'phone': clean_phone}
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get('success') and data.get('data'):
                customer = data['data'][0]
                
                # Cache the result
                self._cache_customer(clean_phone, customer)
                
                return customer
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding customer by phone {phone}: {e}")
            return None
    
    def _cache_customer(self, phone: str, customer: Dict):
        """Cache customer information"""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor()
            
            query = """
                INSERT INTO customer_mapping (
                    phone_number, actiwell_customer_id, customer_name, customer_email
                ) VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    actiwell_customer_id = VALUES(actiwell_customer_id),
                    customer_name = VALUES(customer_name),
                    customer_email = VALUES(customer_email),
                    last_updated = CURRENT_TIMESTAMP
            """
            
            cursor.execute(query, (
                phone, customer['id'], customer.get('name'), customer.get('email')
            ))
            
            connection.commit()
            cursor.close()
            connection.close()
            
        except Exception as e:
            logger.error(f"Error caching customer: {e}")
    
    def sync_measurement_to_actiwell(self, measurement: BodyMeasurement) -> bool:
        """Sync measurement to Actiwell system"""
        try:
            # Find customer
            customer = self.find_customer_by_phone(measurement.customer_phone)
            if not customer:
                logger.warning(f"Customer not found for phone: {measurement.customer_phone}")
                return False
            
            # Prepare payload
            payload = {
                'customer_id': customer['id'],
                'location_id': self.location_id,
                'measurement_date': measurement.measurement_timestamp.isoformat(),
                'device_type': measurement.device_type,
                'device_id': measurement.device_id,
                'measurement_uuid': measurement.measurement_uuid,
                'body_composition': {
                    'weight_kg': measurement.weight_kg,
                    'height_cm': measurement.height_cm,
                    'bmi': measurement.bmi,
                    'body_fat_percent': measurement.body_fat_percent,
                    'muscle_mass_kg': measurement.muscle_mass_kg,
                    'bone_mass_kg': measurement.bone_mass_kg,
                    'total_body_water_percent': measurement.total_body_water_percent,
                    'protein_percent': measurement.protein_percent,
                    'mineral_percent': measurement.mineral_percent,
                    'visceral_fat_rating': measurement.visceral_fat_rating,
                    'subcutaneous_fat_percent': measurement.subcutaneous_fat_percent,
                    'skeletal_muscle_mass_kg': measurement.skeletal_muscle_mass_kg,
                    'bmr_kcal': measurement.bmr_kcal,
                    'metabolic_age': measurement.metabolic_age,
                    'measurement_quality': measurement.measurement_quality
                },
                'segmental_analysis': {
                    'right_arm_muscle_kg': measurement.right_arm_muscle_kg,
                    'left_arm_muscle_kg': measurement.left_arm_muscle_kg,
                    'trunk_muscle_kg': measurement.trunk_muscle_kg,
                    'right_leg_muscle_kg': measurement.right_leg_muscle_kg,
                    'left_leg_muscle_kg': measurement.left_leg_muscle_kg
                } if measurement.right_arm_muscle_kg > 0 else None
            }
            
            # Send to Actiwell
            url = f"{self.api_url}/api/body-composition-measurements"
            response = requests.post(url, headers=self.headers, json=payload, timeout=15)
            response.raise_for_status()
            
            result = response.json()
            if result.get('success'):
                logger.info(f"Successfully synced measurement to Actiwell: {measurement.measurement_uuid}")
                return True
            else:
                logger.error(f"Actiwell sync failed: {result.get('message', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.error(f"Error syncing measurement to Actiwell: {e}")
            return False

# ====================================================================================
# 7. MAIN APPLICATION (main.py)
# ====================================================================================

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
CORS(app)

# Initialize managers
db_manager = DatabaseManager()
device_manager = DeviceManager(db_manager)
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
            jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token invalid'}), 401
        
        return f(*args, **kwargs)
    return decorated

# ====================================================================================
# 8. API ENDPOINTS
# ====================================================================================

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Authentication endpoint"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        # Simple authentication (enhance with proper user management)
        if username == 'admin' and password == 'actiwell123':
            token = jwt.encode({
                'user': username,
                'exp': datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRE_HOURS)
            }, app.config['SECRET_KEY'], algorithm='HS256')
            
            return jsonify({
                'success': True,
                'token': token,
                'user': username,
                'expires_at': (datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRE_HOURS)).isoformat()
            })
        
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """System health check"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'Actiwell Body Measurement Backend',
        'version': '1.0.0'
    })

@app.route('/api/devices/status', methods=['GET'])
@token_required
def get_device_status():
    """Get status of all devices"""
    try:
        device_status = {}
        for device_id, device in device_manager.devices.items():
            device_status[device_id] = {
                'device_id': device_id,
                'device_type': device.device_type,
                'port': device.port,
                'connected': device.is_connected,
                'status': 'connected' if device.is_connected else 'disconnected'
            }
        
        return jsonify({
            'success': True,
            'devices': device_status,
            'total_devices': len(device_status),
            'connected_devices': len([d for d in device_status.values() if d['connected']])
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/devices/scan', methods=['POST'])
@token_required
def scan_devices():
    """Scan and connect to devices"""
    try:
        device_manager.connect_devices()
        return jsonify({
            'success': True,
            'message': 'Device scan completed',
            'devices_found': len(device_manager.devices)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/measurements', methods=['GET'])
@token_required
def get_measurements():
    """Get measurements with pagination and filtering"""
    try:
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 50)), 100)
        customer_phone = request.args.get('customer_phone')
        device_type = request.args.get('device_type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Build query with filters
        connection = db_manager.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        where_conditions = []
        params = []
        
        if customer_phone:
            where_conditions.append("customer_phone LIKE %s")
            params.append(f"%{customer_phone}%")
        
        if device_type:
            where_conditions.append("device_type = %s")
            params.append(device_type)
        
        if start_date:
            where_conditions.append("measurement_timestamp >= %s")
            params.append(start_date)
        
        if end_date:
            where_conditions.append("measurement_timestamp <= %s")
            params.append(end_date)
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Get total count
        count_query = f"SELECT COUNT(*) as total FROM body_measurements {where_clause}"
        cursor.execute(count_query, tuple(params))
        total_count = cursor.fetchone()['total']
        
        # Get measurements with pagination
        offset = (page - 1) * per_page
        query = f"""
            SELECT * FROM body_measurements 
            {where_clause}
            ORDER BY measurement_timestamp DESC
            LIMIT %s OFFSET %s
        """
        params.extend([per_page, offset])
        
        cursor.execute(query, tuple(params))
        measurements = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        # Convert datetime objects to strings
        for measurement in measurements:
            for key, value in measurement.items():
                if isinstance(value, datetime):
                    measurement[key] = value.isoformat()
        
        total_pages = (total_count + per_page - 1) // per_page
        
        return jsonify({
            'success': True,
            'measurements': measurements,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_count': total_count,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/measurements/customer/<phone>', methods=['GET'])
@token_required
def get_customer_measurements(phone):
    """Get measurements for specific customer"""
    try:
        connection = db_manager.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        query = """
            SELECT * FROM body_measurements 
            WHERE customer_phone = %s 
            ORDER BY measurement_timestamp DESC
            LIMIT 50
        """
        
        cursor.execute(query, (phone,))
        measurements = cursor.fetchall()
        
        cursor.close()
        connection.close()
        
        # Convert datetime objects
        for measurement in measurements:
            for key, value in measurement.items():
                if isinstance(value, datetime):
                    measurement[key] = value.isoformat()
        
        return jsonify({
            'success': True,
            'customer_phone': phone,
            'measurements': measurements,
            'count': len(measurements)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sync/status', methods=['GET'])
@token_required
def get_sync_status():
    """Get sync status with Actiwell"""
    try:
        connection = db_manager.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Get sync statistics
        query = """
            SELECT 
                COUNT(*) as total_measurements,
                SUM(CASE WHEN synced_to_actiwell = TRUE THEN 1 ELSE 0 END) as synced_count,
                SUM(CASE WHEN synced_to_actiwell = FALSE THEN 1 ELSE 0 END) as pending_count,
                MAX(last_sync_attempt) as last_sync_time
            FROM body_measurements
            WHERE measurement_timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        """
        
        cursor.execute(query)
        stats = cursor.fetchone()
        
        cursor.close()
        connection.close()
        
        sync_percentage = 0
        if stats['total_measurements'] > 0:
            sync_percentage = (stats['synced_count'] / stats['total_measurements']) * 100
        
        return jsonify({
            'success': True,
            'sync_statistics': {
                'total_measurements': stats['total_measurements'],
                'synced_count': stats['synced_count'],
                'pending_count': stats['pending_count'],
                'sync_percentage': round(sync_percentage, 1),
                'last_sync_time': stats['last_sync_time'].isoformat() if stats['last_sync_time'] else None
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sync/trigger', methods=['POST'])
@token_required
def trigger_sync():
    """Manually trigger sync to Actiwell"""
    try:
        # Get unsynced measurements
        unsynced_measurements = db_manager.get_unsynced_measurements(50)
        
        sync_results = []
        
        for measurement_data in unsynced_measurements:
            # Convert dict to BodyMeasurement object
            measurement = BodyMeasurement(
                device_id=measurement_data['device_id'],
                device_type=measurement_data['device_type'],
                measurement_uuid=measurement_data['measurement_uuid'],
                customer_phone=measurement_data['customer_phone'],
                customer_id=measurement_data['customer_id'],
                measurement_timestamp=measurement_data['measurement_timestamp'],
                weight_kg=measurement_data['weight_kg'],
                height_cm=measurement_data['height_cm'],
                bmi=measurement_data['bmi'],
                body_fat_percent=measurement_data['body_fat_percent'],
                muscle_mass_kg=measurement_data['muscle_mass_kg'],
                bone_mass_kg=measurement_data['bone_mass_kg'],
                total_body_water_percent=measurement_data['total_body_water_percent'],
                protein_percent=measurement_data['protein_percent'],
                mineral_percent=measurement_data['mineral_percent'],
                visceral_fat_rating=measurement_data['visceral_fat_rating'],
                subcutaneous_fat_percent=measurement_data['subcutaneous_fat_percent'],
                skeletal_muscle_mass_kg=measurement_data['skeletal_muscle_mass_kg'],
                bmr_kcal=measurement_data['bmr_kcal'],
                metabolic_age=measurement_data['metabolic_age'],
                raw_data=measurement_data['raw_data']
            )
            
            # Attempt sync
            success = actiwell_api.sync_measurement_to_actiwell(measurement)
            
            # Update sync status
            db_manager.update_sync_status(
                measurement_data['id'], 
                success, 
                "" if success else "Sync failed",
                measurement_data['sync_attempts'] + 1
            )
            
            sync_results.append({
                'measurement_id': measurement_data['id'],
                'customer_phone': measurement_data['customer_phone'],
                'success': success
            })
        
        successful_syncs = len([r for r in sync_results if r['success']])
        
        return jsonify({
            'success': True,
            'message': f'Sync completed: {successful_syncs}/{len(sync_results)} successful',
            'results': sync_results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ====================================================================================
# 9. BACKGROUND SERVICES
# ====================================================================================

def measurement_processor():
    """Background service to process measurements"""
    logger.info("Measurement processor started")
    
    while True:
        try:
            # Get measurement from device queue
            measurement = device_manager.get_measurement(timeout=1.0)
            
            if measurement:
                # Save to database
                measurement_id = db_manager.save_measurement(measurement)
                logger.info(f"Saved measurement ID: {measurement_id} for customer: {measurement.customer_phone}")
                
                # Sync to Actiwell
                success = actiwell_api.sync_measurement_to_actiwell(measurement)
                
                # Update sync status
                db_manager.update_sync_status(
                    measurement_id, 
                    success, 
                    "" if success else "Initial sync failed"
                )
                
                if success:
                    logger.info(f"Successfully synced measurement {measurement_id} to Actiwell")
                else:
                    logger.warning(f"Failed to sync measurement {measurement_id} to Actiwell")
        
        except Exception as e:
            logger.error(f"Measurement processor error: {e}")
            time.sleep(5)

def retry_failed_syncs():
    """Background service to retry failed syncs"""
    logger.info("Retry sync service started")
    
    while True:
        try:
            # Wait 5 minutes between retry attempts
            time.sleep(300)
            
            # Get unsynced measurements
            unsynced = db_manager.get_unsynced_measurements(20)
            
            for measurement_data in unsynced:
                if measurement_data['sync_attempts'] < 5:  # Max 5 attempts
                    # Convert to BodyMeasurement object and retry sync
                    measurement = BodyMeasurement(**{k: v for k, v in measurement_data.items() 
                                                   if k in BodyMeasurement.__annotations__})
                    
                    success = actiwell_api.sync_measurement_to_actiwell(measurement)
                    
                    db_manager.update_sync_status(
                        measurement_data['id'],
                        success,
                        "" if success else "Retry sync failed",
                        measurement_data['sync_attempts'] + 1
                    )
                    
                    if success:
                        logger.info(f"Retry sync successful for measurement {measurement_data['id']}")
                    
                    time.sleep(1)  # Small delay between retries
        
        except Exception as e:
            logger.error(f"Retry sync service error: {e}")

# ====================================================================================
# 10. APPLICATION STARTUP
# ====================================================================================

if __name__ == '__main__':
    try:
        logger.info("Starting Actiwell Body Measurement Backend Server")
        
        # Connect to devices
        device_manager.connect_devices()
        
        # Start device monitoring
        device_manager.start_monitoring()
        
        # Start background services
        measurement_thread = threading.Thread(target=measurement_processor, daemon=True)
        measurement_thread.start()
        
        retry_thread = threading.Thread(target=retry_failed_syncs, daemon=True)
        retry_thread.start()
        
        logger.info(f"Server starting on {Config.WEB_HOST}:{Config.WEB_PORT}")
        logger.info(f"Connected devices: {len(device_manager.devices)}")
        
        # Start Flask application
        app.run(
            host=Config.WEB_HOST,
            port=Config.WEB_PORT,
            debug=False,
            threaded=True
        )
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        device_manager.stop_monitoring()
        device_manager.disconnect_all()
    except Exception as e:
        logger.error(f"Application startup error: {e}")
        raise