#!/usr/bin/env python3
"""
Enhanced API Endpoints for Body Composition Gateway
Complete REST API for Actiwell Backend Integration
"""

from flask import Flask, request, jsonify, send_file
from flask_restful import Api, Resource
from flask_cors import CORS
from datetime import datetime, timedelta
import json
import logging
import os
from typing import Dict, List, Optional
import uuid
import hashlib
import jwt
from functools import wraps
import mysql.connector
from mysql.connector import Error
import requests
import threading
import time

# Import enhanced classes from main application
# from app import DatabaseManager, DeviceManager, ActiwellAPI, TanitaResult

# Enhanced API class
class BodyCompositionAPI:
    def __init__(self, app: Flask, db_manager, device_manager, actiwell_api):
        self.app = app
        self.api = Api(app)
        self.db_manager = db_manager
        self.device_manager = device_manager
        self.actiwell_api = actiwell_api
        
        # Configure CORS
        CORS(app, resources={
            r"/api/*": {
                "origins": "*",
                "methods": ["GET", "POST", "PUT", "DELETE"],
                "allow_headers": ["Content-Type", "Authorization"]
            }
        })
        
        self._register_routes()
        self._setup_error_handlers()
    
    def _register_routes(self):
        """Register all API endpoints"""
        
        # Authentication endpoints
        self.api.add_resource(AuthLoginAPI, '/api/auth/login')
        self.api.add_resource(AuthRefreshAPI, '/api/auth/refresh')
        
        # Device management endpoints
        self.api.add_resource(DeviceStatusAPI, '/api/devices/status')
        self.api.add_resource(DeviceScanAPI, '/api/devices/scan')
        self.api.add_resource(DeviceControlAPI, '/api/devices/<string:device_id>/control')
        self.api.add_resource(DeviceCalibrationAPI, '/api/devices/<string:device_id>/calibrate')
        self.api.add_resource(DeviceConfigAPI, '/api/devices/<string:device_id>/config')
        
        # Measurement endpoints
        self.api.add_resource(MeasurementsListAPI, '/api/measurements')
        self.api.add_resource(MeasurementDetailAPI, '/api/measurements/<int:measurement_id>')
        self.api.add_resource(MeasurementsByCustomerAPI, '/api/measurements/customer/<string:phone>')
        self.api.add_resource(MeasurementUploadAPI, '/api/measurements/upload')
        self.api.add_resource(MeasurementExportAPI, '/api/measurements/export')
        
        # Customer management endpoints
        self.api.add_resource(CustomersListAPI, '/api/customers')
        self.api.add_resource(CustomerDetailAPI, '/api/customers/<int:customer_id>')
        self.api.add_resource(CustomerSyncAPI, '/api/customers/sync')
        self.api.add_resource(CustomerSearchAPI, '/api/customers/search')
        
        # Actiwell sync endpoints
        self.api.add_resource(SyncStatusAPI, '/api/sync/status')
        self.api.add_resource(SyncTriggerAPI, '/api/sync/trigger')
        self.api.add_resource(SyncLogsAPI, '/api/sync/logs')
        self.api.add_resource(SyncConfigAPI, '/api/sync/config')
        
        # Analytics endpoints
        self.api.add_resource(AnalyticsSummaryAPI, '/api/analytics/summary')
        self.api.add_resource(AnalyticsTrendsAPI, '/api/analytics/trends')
        self.api.add_resource(AnalyticsCustomerAPI, '/api/analytics/customer/<int:customer_id>')
        self.api.add_resource(AnalyticsDeviceAPI, '/api/analytics/device/<string:device_id>')
        
        # System endpoints
        self.api.add_resource(SystemHealthAPI, '/api/system/health')
        self.api.add_resource(SystemSettingsAPI, '/api/system/settings')
        self.api.add_resource(SystemLogsAPI, '/api/system/logs')
        self.api.add_resource(SystemBackupAPI, '/api/system/backup')
        
        # Webhook endpoints for Actiwell
        self.api.add_resource(ActiwellWebhookAPI, '/api/webhooks/actiwell')
        
    def _setup_error_handlers(self):
        """Setup global error handlers"""
        
        @self.app.errorhandler(400)
        def bad_request(error):
            return jsonify({
                'error': 'Bad Request',
                'message': 'Invalid request data',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        @self.app.errorhandler(401)
        def unauthorized(error):
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Authentication required',
                'timestamp': datetime.now().isoformat()
            }), 401
        
        @self.app.errorhandler(404)
        def not_found(error):
            return jsonify({
                'error': 'Not Found',
                'message': 'Resource not found',
                'timestamp': datetime.now().isoformat()
            }), 404
        
        @self.app.errorhandler(500)
        def internal_error(error):
            return jsonify({
                'error': 'Internal Server Error',
                'message': 'An unexpected error occurred',
                'timestamp': datetime.now().isoformat()
            }), 500

# Authentication decorator
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return {'error': 'Token missing'}, 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return {'error': 'Token expired'}, 401
        except jwt.InvalidTokenError:
            return {'error': 'Token invalid'}, 401
        
        return f(*args, **kwargs)
    return decorated_function

# Authentication APIs
class AuthLoginAPI(Resource):
    def post(self):
        """Authenticate user and return JWT token"""
        try:
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')
            
            # Simple authentication (enhance with proper user management)
            if username == 'admin' and password == 'admin123':
                token = jwt.encode({
                    'user': username,
                    'permissions': ['read', 'write', 'admin'],
                    'exp': datetime.utcnow() + timedelta(hours=24)
                }, app.config['SECRET_KEY'], algorithm='HS256')
                
                return {
                    'token': token,
                    'user': username,
                    'permissions': ['read', 'write', 'admin'],
                    'expires_at': (datetime.utcnow() + timedelta(hours=24)).isoformat()
                }
            
            return {'error': 'Invalid credentials'}, 401
            
        except Exception as e:
            return {'error': str(e)}, 500

class AuthRefreshAPI(Resource):
    @require_auth
    def post(self):
        """Refresh JWT token"""
        try:
            # Extract user from current token
            token = request.headers.get('Authorization')[7:]
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            
            # Generate new token
            new_token = jwt.encode({
                'user': payload['user'],
                'permissions': payload.get('permissions', ['read']),
                'exp': datetime.utcnow() + timedelta(hours=24)
            }, app.config['SECRET_KEY'], algorithm='HS256')
            
            return {
                'token': new_token,
                'expires_at': (datetime.utcnow() + timedelta(hours=24)).isoformat()
            }
            
        except Exception as e:
            return {'error': str(e)}, 500

# Device Management APIs
class DeviceStatusAPI(Resource):
    @require_auth
    def get(self):
        """Get status of all connected devices"""
        try:
            db_manager = app.config['DB_MANAGER']
            
            # Get device status from database
            query = """
            SELECT device_id, device_type, status, serial_port, 
                   firmware_version, last_heartbeat, configuration
            FROM device_status
            ORDER BY device_type, device_id
            """
            devices = db_manager.execute_query(query)
            
            # Get recent measurement counts
            measurement_query = """
            SELECT tm.device_id, COUNT(*) as measurement_count
            FROM tanita_measurements tm
            WHERE tm.measurement_timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY tm.device_id
            """
            measurements = db_manager.execute_query(measurement_query)
            measurement_counts = {m['device_id']: m['measurement_count'] for m in measurements}
            
            # Enhance device data
            for device in devices:
                device['measurement_count_24h'] = measurement_counts.get(device['device_id'], 0)
                device['last_heartbeat_relative'] = self._get_relative_time(device['last_heartbeat'])
                
                # Parse configuration if it's JSON string
                if device['configuration']:
                    try:
                        device['configuration'] = json.loads(device['configuration'])
                    except:
                        device['configuration'] = {}
            
            return {
                'devices': devices,
                'total_devices': len(devices),
                'connected_devices': len([d for d in devices if d['status'] == 'connected']),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'error': str(e)}, 500
    
    def _get_relative_time(self, timestamp):
        """Get relative time string"""
        if not timestamp:
            return 'Never'
        
        now = datetime.now()
        diff = now - timestamp
        
        if diff.seconds < 60:
            return f"{diff.seconds} seconds ago"
        elif diff.seconds < 3600:
            return f"{diff.seconds // 60} minutes ago"
        elif diff.days == 0:
            return f"{diff.seconds // 3600} hours ago"
        else:
            return f"{diff.days} days ago"

class DeviceScanAPI(Resource):
    @require_auth
    def post(self):
        """Trigger device scan and detection"""
        try:
            device_manager = app.config['DEVICE_MANAGER']
            
            # Trigger device scan in background
            threading.Thread(target=device_manager.auto_detect_devices).start()
            
            return {
                'message': 'Device scan initiated',
                'scan_id': str(uuid.uuid4()),
                'estimated_duration': '30 seconds'
            }
            
        except Exception as e:
            return {'error': str(e)}, 500

class DeviceControlAPI(Resource):
    @require_auth
    def post(self, device_id):
        """Control device operations (start/stop/reset)"""
        try:
            data = request.get_json()
            command = data.get('command')  # start, stop, reset, test
            
            if command not in ['start', 'stop', 'reset', 'test']:
                return {'error': 'Invalid command'}, 400
            
            # Execute device command
            result = self._execute_device_command(device_id, command)
            
            return {
                'device_id': device_id,
                'command': command,
                'result': result,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'error': str(e)}, 500
    
    def _execute_device_command(self, device_id, command):
        """Execute command on specific device"""
        # Implementation would depend on device communication protocol
        return f"Command '{command}' executed on device {device_id}"

class DeviceCalibrationAPI(Resource):
    @require_auth
    def post(self, device_id):
        """Start device calibration process"""
        try:
            data = request.get_json()
            calibration_type = data.get('type', 'full')  # weight, impedance, full
            reference_weights = data.get('reference_weights', [])
            
            db_manager = app.config['DB_MANAGER']
            
            # Create calibration record
            calibration_id = db_manager.execute_update("""
                INSERT INTO device_calibrations 
                (device_id, calibration_type, calibration_status, technician_name, notes, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (device_id, calibration_type, 'in_progress', 'API User', f'API initiated calibration'))
            
            # Start calibration process (implement device-specific logic)
            calibration_result = self._perform_calibration(device_id, calibration_type, reference_weights)
            
            # Update calibration record with results
            db_manager.execute_update("""
                UPDATE device_calibrations 
                SET calibration_status = %s, calibration_value = %s, 
                    deviation_percent = %s, notes = %s
                WHERE id = %s
            """, (
                calibration_result['status'],
                calibration_result.get('value'),
                calibration_result.get('deviation'),
                calibration_result.get('notes'),
                calibration_id
            ))
            
            return {
                'calibration_id': calibration_id,
                'device_id': device_id,
                'type': calibration_type,
                'result': calibration_result
            }
            
        except Exception as e:
            return {'error': str(e)}, 500
    
    def _perform_calibration(self, device_id, calibration_type, reference_weights):
        """Perform actual device calibration"""
        # Simulate calibration process
        time.sleep(2)  # Simulate calibration time
        
        return {
            'status': 'passed',
            'value': 100.0,
            'deviation': 0.1,
            'notes': 'Calibration completed successfully'
        }

# Measurement APIs
class MeasurementsListAPI(Resource):
    @require_auth
    def get(self):
        """Get list of measurements with filtering and pagination"""
        try:
            # Parse query parameters
            page = int(request.args.get('page', 1))
            per_page = min(int(request.args.get('per_page', 50)), 100)
            device_id = request.args.get('device_id')
            customer_phone = request.args.get('customer_phone')
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            sync_status = request.args.get('sync_status')
            
            db_manager = app.config['DB_MANAGER']
            
            # Build query with filters
            where_conditions = []
            params = []
            
            if device_id:
                where_conditions.append("tm.device_id = %s")
                params.append(device_id)
            
            if customer_phone:
                where_conditions.append("tm.extracted_phone_number LIKE %s")
                params.append(f"%{customer_phone}%")
            
            if start_date:
                where_conditions.append("tm.measurement_timestamp >= %s")
                params.append(start_date)
            
            if end_date:
                where_conditions.append("tm.measurement_timestamp <= %s")
                params.append(end_date)
            
            if sync_status:
                if sync_status == 'synced':
                    where_conditions.append("tm.synced_to_actiwell = TRUE")
                elif sync_status == 'pending':
                    where_conditions.append("tm.synced_to_actiwell = FALSE")
            
            where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
            
            # Get total count
            count_query = f"""
            SELECT COUNT(*) as total
            FROM tanita_measurements tm
            {where_clause}
            """
            count_result = db_manager.execute_query(count_query, tuple(params))
            total_count = count_result[0]['total'] if count_result else 0
            
            # Get measurements with pagination
            offset = (page - 1) * per_page
            query = f"""
            SELECT tm.*, c.name as customer_name, ds.device_type
            FROM tanita_measurements tm
            LEFT JOIN customers c ON tm.customer_id = c.id
            LEFT JOIN device_status ds ON tm.device_id = ds.device_id
            {where_clause}
            ORDER BY tm.measurement_timestamp DESC
            LIMIT %s OFFSET %s
            """
            
            params.extend([per_page, offset])
            measurements = db_manager.execute_query(query, tuple(params))
            
            # Calculate pagination info
            total_pages = (total_count + per_page - 1) // per_page
            
            return {
                'measurements': measurements,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total_count': total_count,
                    'total_pages': total_pages,
                    'has_next': page < total_pages,
                    'has_prev': page > 1
                },
                'filters_applied': {
                    'device_id': device_id,
                    'customer_phone': customer_phone,
                    'start_date': start_date,
                    'end_date': end_date,
                    'sync_status': sync_status
                }
            }
            
        except Exception as e:
            return {'error': str(e)}, 500

    @require_auth
    def post(self):
        """Create new measurement (manual entry)"""
        try:
            data = request.get_json()
            
            # Validate required fields
            required_fields = ['device_id', 'extracted_phone_number', 'weight_kg']
            for field in required_fields:
                if field not in data:
                    return {'error': f'Missing required field: {field}'}, 400
            
            db_manager = app.config['DB_MANAGER']
            
            # Generate measurement UUID
            measurement_uuid = str(uuid.uuid4())
            
            # Insert measurement
            measurement_id = db_manager.execute_update("""
                INSERT INTO tanita_measurements (
                    device_id, extracted_phone_number, measurement_uuid,
                    measurement_timestamp, weight_kg, bmi, body_fat_percent,
                    muscle_mass_kg, visceral_fat_rating, metabolic_age,
                    bmr_kcal, raw_data, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                data['device_id'],
                data['extracted_phone_number'],
                measurement_uuid,
                data.get('measurement_timestamp', datetime.now()),
                data['weight_kg'],
                data.get('bmi'),
                data.get('body_fat_percent'),
                data.get('muscle_mass_kg'),
                data.get('visceral_fat_rating'),
                data.get('metabolic_age'),
                data.get('bmr_kcal'),
                json.dumps(data)
            ))
            
            return {
                'measurement_id': measurement_id,
                'measurement_uuid': measurement_uuid,
                'message': 'Measurement created successfully'
            }, 201
            
        except Exception as e:
            return {'error': str(e)}, 500

class MeasurementDetailAPI(Resource):
    @require_auth
    def get(self, measurement_id):
        """Get detailed measurement information"""
        try:
            db_manager = app.config['DB_MANAGER']
            
            query = """
            SELECT tm.*, c.name as customer_name, c.email as customer_email,
                   ds.device_type, ds.firmware_version
            FROM tanita_measurements tm
            LEFT JOIN customers c ON tm.customer_id = c.id
            LEFT JOIN device_status ds ON tm.device_id = ds.device_id
            WHERE tm.id = %s
            """
            
            result = db_manager.execute_query(query, (measurement_id,))
            
            if not result:
                return {'error': 'Measurement not found'}, 404
            
            measurement = result[0]
            
            # Parse raw data if available
            if measurement['raw_data']:
                try:
                    measurement['parsed_data'] = json.loads(measurement['raw_data'])
                except:
                    measurement['parsed_data'] = {}
            
            # Get sync history
            sync_query = """
            SELECT sync_status, started_at, completed_at, error_message
            FROM sync_logs
            WHERE entity_type = 'tanita_measurement' AND entity_id = %s
            ORDER BY started_at DESC
            LIMIT 10
            """
            sync_history = db_manager.execute_query(sync_query, (measurement_id,))
            measurement['sync_history'] = sync_history
            
            return measurement
            
        except Exception as e:
            return {'error': str(e)}, 500
    
    @require_auth
    def put(self, measurement_id):
        """Update measurement data"""
        try:
            data = request.get_json()
            db_manager = app.config['DB_MANAGER']
            
            # Build update query dynamically
            allowed_fields = [
                'weight_kg', 'bmi', 'body_fat_percent', 'muscle_mass_kg',
                'visceral_fat_rating', 'metabolic_age', 'bmr_kcal',
                'health_score', 'fitness_level'
            ]
            
            update_fields = []
            params = []
            
            for field in allowed_fields:
                if field in data:
                    update_fields.append(f"{field} = %s")
                    params.append(data[field])
            
            if not update_fields:
                return {'error': 'No valid fields to update'}, 400
            
            params.append(measurement_id)
            
            query = f"""
            UPDATE tanita_measurements 
            SET {', '.join(update_fields)}
            WHERE id = %s
            """
            
            db_manager.execute_update(query, tuple(params))
            
            return {'message': 'Measurement updated successfully'}
            
        except Exception as e:
            return {'error': str(e)}, 500
    
    @require_auth
    def delete(self, measurement_id):
        """Delete measurement (soft delete)"""
        try:
            db_manager = app.config['DB_MANAGER']
            
            # Check if measurement exists
            check_query = "SELECT id FROM tanita_measurements WHERE id = %s"
            result = db_manager.execute_query(check_query, (measurement_id,))
            
            if not result:
                return {'error': 'Measurement not found'}, 404
            
            # Soft delete by marking as deleted (you may want to add deleted_at column)
            # For now, we'll move to a deleted_measurements table or mark with a flag
            db_manager.execute_update("""
                UPDATE tanita_measurements 
                SET processing_notes = CONCAT(COALESCE(processing_notes, ''), ' [DELETED]')
                WHERE id = %s
            """, (measurement_id,))
            
            return {'message': 'Measurement deleted successfully'}
            
        except Exception as e:
            return {'error': str(e)}, 500

class MeasurementsByCustomerAPI(Resource):
    @require_auth
    def get(self, phone):
        """Get all measurements for a specific customer"""
        try:
            db_manager = app.config['DB_MANAGER']
            
            # Get customer measurements
            query = """
            SELECT tm.*, ds.device_type
            FROM tanita_measurements tm
            LEFT JOIN device_status ds ON tm.device_id = ds.device_id
            WHERE tm.extracted_phone_number = %s
            ORDER BY tm.measurement_timestamp DESC
            """
            
            measurements = db_manager.execute_query(query, (phone,))
            
            if not measurements:
                return {
                    'customer_phone': phone,
                    'measurements': [],
                    'count': 0,
                    'trends': {}
                }
            
            # Calculate trends
            trends = self._calculate_customer_trends(measurements)
            
            return {
                'customer_phone': phone,
                'measurements': measurements,
                'count': len(measurements),
                'trends': trends
            }
            
        except Exception as e:
            return {'error': str(e)}, 500
    
    def _calculate_customer_trends(self, measurements):
        """Calculate measurement trends for customer"""
        if len(measurements) < 2:
            return {}
        
        # Sort by date (oldest first for trend calculation)
        sorted_measurements = sorted(measurements, key=lambda x: x['measurement_timestamp'])
        
        first = sorted_measurements[0]
        latest = sorted_measurements[-1]
        
        trends = {}
        
        # Weight trend
        if first['weight_kg'] and latest['weight_kg']:
            weight_change = latest['weight_kg'] - first['weight_kg']
            trends['weight'] = {
                'change_kg': round(weight_change, 1),
                'change_percent': round((weight_change / first['weight_kg']) * 100, 1),
                'direction': 'up' if weight_change > 0 else 'down' if weight_change < 0 else 'stable'
            }
        
        # Body fat trend
        if first['body_fat_percent'] and latest['body_fat_percent']:
            bf_change = latest['body_fat_percent'] - first['body_fat_percent']
            trends['body_fat'] = {
                'change_percent': round(bf_change, 1),
                'direction': 'up' if bf_change > 0 else 'down' if bf_change < 0 else 'stable'
            }
        
        # Muscle mass trend
        if first['muscle_mass_kg'] and latest['muscle_mass_kg']:
            muscle_change = latest['muscle_mass_kg'] - first['muscle_mass_kg']
            trends['muscle_mass'] = {
                'change_kg': round(muscle_change, 1),
                'direction': 'up' if muscle_change > 0 else 'down' if muscle_change < 0 else 'stable'
            }
        
        return trends

# Sync APIs
class SyncStatusAPI(Resource):
    @require_auth
    def get(self):
        """Get overall sync status with Actiwell"""
        try:
            db_manager = app.config['DB_MANAGER']
            
            # Get sync statistics
            sync_stats_query = """
            SELECT 
                COUNT(*) as total_measurements,
                SUM(CASE WHEN synced_to_actiwell = TRUE THEN 1 ELSE 0 END) as synced_count,
                SUM(CASE WHEN synced_to_actiwell = FALSE THEN 1 ELSE 0 END) as pending_count,
                MAX(last_sync_attempt) as last_sync_time
            FROM tanita_measurements
            WHERE measurement_timestamp >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            """
            
            stats = db_manager.execute_query(sync_stats_query)[0]
            
            # Get recent sync logs
            recent_logs_query = """
            SELECT sync_type, entity_type, sync_status, started_at, 
                   completed_at, error_message
            FROM sync_logs
            ORDER BY started_at DESC
            LIMIT 20
            """
            
            recent_logs = db_manager.execute_query(recent_logs_query)
            
            # Calculate sync percentage
            sync_percentage = 0
            if stats['total_measurements'] > 0:
                sync_percentage = (stats['synced_count'] / stats['total_measurements']) * 100
            
            # Get failed sync count from logs
            failed_sync_query = """
            SELECT COUNT(*) as failed_count
            FROM sync_logs
            WHERE sync_status = 'failed' 
            AND started_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            """
            
            failed_count = db_manager.execute_query(failed_sync_query)[0]['failed_count']
            
            return {
                'sync_statistics': {
                    'total_measurements': stats['total_measurements'],
                    'synced_count': stats['synced_count'],
                    'pending_count': stats['pending_count'],
                    'failed_count': failed_count,
                    'sync_percentage': round(sync_percentage, 1),
                    'last_sync_time': stats['last_sync_time'].isoformat() if stats['last_sync_time'] else None
                },
                'recent_logs': recent_logs,
                'health_status': 'healthy' if sync_percentage > 95 and failed_count < 10 else 'warning'
            }
            
        except Exception as e:
            return {'error': str(e)}, 500

class SyncTriggerAPI(Resource):
    @require_auth
    def post(self):
        """Trigger manual sync to Actiwell"""
        try:
            data = request.get_json() or {}
            sync_type = data.get('type', 'measurements')  # measurements, customers, all
            force = data.get('force', False)  # Force resync of already synced items
            
            db_manager = app.config['DB_MANAGER']
            
            # Create sync batch ID
            batch_id = str(uuid.uuid4())
            
            if sync_type in ['measurements', 'all']:
                # Get measurements to sync
                where_clause = "WHERE synced_to_actiwell = FALSE" if not force else ""
                measurements_query = f"""
                SELECT id, extracted_phone_number, weight_kg, body_fat_percent,
                       muscle_mass_kg, measurement_timestamp
                FROM tanita_measurements
                {where_clause}
                ORDER BY measurement_timestamp DESC
                LIMIT 100
                """
                
                measurements_to_sync = db_manager.execute_query(measurements_query)
                
                # Start sync process in background
                threading.Thread(
                    target=self._sync_measurements_background,
                    args=(measurements_to_sync, batch_id)
                ).start()
            
            return {
                'sync_initiated': True,
                'batch_id': batch_id,
                'sync_type': sync_type,
                'estimated_items': len(measurements_to_sync) if 'measurements_to_sync' in locals() else 0
            }
            
        except Exception as e:
            return {'error': str(e)}, 500
    
    def _sync_measurements_background(self, measurements, batch_id):
        """Background sync process"""
        db_manager = app.config['DB_MANAGER']
        actiwell_api = app.config['ACTIWELL_API']
        
        for measurement in measurements:
            try:
                # Create sync log entry
                sync_log_id = db_manager.execute_update("""
                    INSERT INTO sync_logs 
                    (sync_type, entity_type, entity_id, sync_direction, 
                     sync_status, sync_batch_id, started_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """, ('measurement', 'tanita_measurement', measurement['id'], 
                      'to_actiwell', 'pending', batch_id))
                
                # Attempt sync
                # sync_result = actiwell_api.sync_measurement_to_actiwell(measurement)
                sync_result = True  # Simulate successful sync
                
                # Update sync log
                db_manager.execute_update("""
                    UPDATE sync_logs 
                    SET sync_status = %s, completed_at = NOW(),
                        duration_ms = TIMESTAMPDIFF(MICROSECOND, started_at, NOW()) / 1000
                    WHERE id = %s
                """, ('success' if sync_result else 'failed', sync_log_id))
                
                # Update measurement sync status
                if sync_result:
                    db_manager.execute_update("""
                        UPDATE tanita_measurements 
                        SET synced_to_actiwell = TRUE, last_sync_attempt = NOW()
                        WHERE id = %s
                    """, (measurement['id'],))
                
                time.sleep(0.1)  # Small delay to avoid overwhelming the API
                
            except Exception as e:
                logging.error(f"Error syncing measurement {measurement['id']}: {e}")

# Analytics APIs
class AnalyticsSummaryAPI(Resource):
    @require_auth
    def get(self):
        """Get analytics summary for dashboard"""
        try:
            db_manager = app.config['DB_MANAGER']
            days = int(request.args.get('days', 30))
            
            # Daily measurements trend
            daily_query = """
            SELECT DATE(measurement_timestamp) as date, 
                   COUNT(*) as count,
                   AVG(weight_kg) as avg_weight,
                   AVG(body_fat_percent) as avg_body_fat
            FROM tanita_measurements 
            WHERE measurement_timestamp >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY DATE(measurement_timestamp)
            ORDER BY date DESC
            """
            daily_stats = db_manager.execute_query(daily_query, (days,))
            
            # Device usage statistics
            device_query = """
            SELECT ds.device_type, ds.device_id,
                   COUNT(tm.id) as measurement_count
            FROM device_status ds
            LEFT JOIN tanita_measurements tm ON ds.device_id = tm.device_id
                AND tm.measurement_timestamp >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY ds.device_type, ds.device_id
            """
            device_stats = db_manager.execute_query(device_query, (days,))
            
            # Customer engagement
            customer_query = """
            SELECT COUNT(DISTINCT extracted_phone_number) as unique_customers,
                   COUNT(*) as total_measurements,
                   AVG(CASE WHEN synced_to_actiwell THEN 1.0 ELSE 0.0 END) * 100 as sync_rate
            FROM tanita_measurements
            WHERE measurement_timestamp >= DATE_SUB(NOW(), INTERVAL %s DAY)
            """
            customer_stats = db_manager.execute_query(customer_query, (days,))
            
            return {
                'period_days': days,
                'daily_trends': daily_stats,
                'device_usage': device_stats,
                'customer_engagement': customer_stats[0] if customer_stats else {},
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'error': str(e)}, 500

# System APIs
class SystemHealthAPI(Resource):
    @require_auth
    def get(self):
        """Get system health status"""
        try:
            db_manager = app.config['DB_MANAGER']
            
            # Database health
            db_health = self._check_database_health(db_manager)
            
            # Device health
            device_health = self._check_device_health(db_manager)
            
            # Storage health
            storage_health = self._check_storage_health()
            
            # Overall health score
            health_score = (db_health['score'] + device_health['score'] + storage_health['score']) / 3
            
            return {
                'overall_health': {
                    'score': round(health_score, 1),
                    'status': 'healthy' if health_score > 80 else 'warning' if health_score > 60 else 'critical'
                },
                'database': db_health,
                'devices': device_health,
                'storage': storage_health,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'error': str(e)}, 500
    
    def _check_database_health(self, db_manager):
        """Check database connectivity and performance"""
        try:
            # Test connection
            result = db_manager.execute_query("SELECT 1 as test")
            if not result:
                return {'score': 0, 'status': 'critical', 'message': 'Database connection failed'}
            
            # Check table sizes
            size_query = """
            SELECT table_name, 
                   ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
            FROM information_schema.tables 
            WHERE table_schema = DATABASE()
            ORDER BY size_mb DESC
            """
            table_sizes = db_manager.execute_query(size_query)
            
            return {
                'score': 100,
                'status': 'healthy',
                'connection': 'active',
                'table_sizes': table_sizes[:5]  # Top 5 largest tables
            }
            
        except Exception as e:
            return {'score': 0, 'status': 'critical', 'message': str(e)}
    
    def _check_device_health(self, db_manager):
        """Check device connectivity status"""
        try:
            query = """
            SELECT status, COUNT(*) as count
            FROM device_status
            GROUP BY status
            """
            device_status = db_manager.execute_query(query)
            
            status_counts = {item['status']: item['count'] for item in device_status}
            total_devices = sum(status_counts.values())
            connected_devices = status_counts.get('connected', 0)
            
            if total_devices == 0:
                score = 0
            else:
                score = (connected_devices / total_devices) * 100
            
            return {
                'score': score,
                'status': 'healthy' if score > 80 else 'warning' if score > 50 else 'critical',
                'total_devices': total_devices,
                'connected_devices': connected_devices,
                'device_status': status_counts
            }
            
        except Exception as e:
            return {'score': 0, 'status': 'critical', 'message': str(e)}
    
    def _check_storage_health(self):
        """Check storage space and usage"""
        try:
            import shutil
            
            data_path = '/home/pi/body_composition_data'
            total, used, free = shutil.disk_usage(data_path)
            
            # Convert to GB
            total_gb = total // (1024**3)
            used_gb = used // (1024**3)
            free_gb = free // (1024**3)
            
            usage_percent = (used / total) * 100
            
            # Score based on free space
            if usage_percent < 70:
                score = 100
                status = 'healthy'
            elif usage_percent < 85:
                score = 70
                status = 'warning'
            else:
                score = 30
                status = 'critical'
            
            return {
                'score': score,
                'status': status,
                'total_gb': total_gb,
                'used_gb': used_gb,
                'free_gb': free_gb,
                'usage_percent': round(usage_percent, 1)
            }
            
        except Exception as e:
            return {'score': 50, 'status': 'warning', 'message': str(e)}

# Webhook API for Actiwell integration
class ActiwellWebhookAPI(Resource):
    def post(self):
        """Handle webhooks from Actiwell system"""
        try:
            data = request.get_json()
            webhook_type = data.get('type')
            
            if webhook_type == 'customer_updated':
                self._handle_customer_update(data)
            elif webhook_type == 'booking_created':
                self._handle_booking_created(data)
            elif webhook_type == 'measurement_requested':
                self._handle_measurement_request(data)
            
            return {'status': 'received', 'type': webhook_type}
            
        except Exception as e:
            logging.error(f"Webhook error: {e}")
            return {'error': str(e)}, 500
    
    def _handle_customer_update(self, data):
        """Handle customer data updates from Actiwell"""
        # Implement customer sync logic
        pass
    
    def _handle_booking_created(self, data):
        """Handle new booking notifications"""
        # Implement booking handling logic
        pass
    
    def _handle_measurement_request(self, data):
        """Handle measurement requests from Actiwell"""
        # Implement measurement request logic
        pass

# Additional placeholder classes for remaining endpoints
class DeviceConfigAPI(Resource):
    @require_auth
    def get(self, device_id):
        return {'device_id': device_id, 'config': {}}
    
    @require_auth
    def put(self, device_id):
        return {'message': 'Configuration updated'}

class MeasurementUploadAPI(Resource):
    @require_auth
    def post(self):
        return {'message': 'File uploaded successfully'}

class MeasurementExportAPI(Resource):
    @require_auth
    def get(self):
        return {'download_url': '/tmp/measurements_export.csv'}

class CustomersListAPI(Resource):
    @require_auth
    def get(self):
        return {'customers': []}

class CustomerDetailAPI(Resource):
    @require_auth
    def get(self, customer_id):
        return {'customer_id': customer_id}

class CustomerSyncAPI(Resource):
    @require_auth
    def post(self):
        return {'message': 'Customer sync initiated'}

class CustomerSearchAPI(Resource):
    @require_auth
    def get(self):
        return {'results': []}

class SyncLogsAPI(Resource):
    @require_auth
    def get(self):
        return {'logs': []}

class SyncConfigAPI(Resource):
    @require_auth
    def get(self):
        return {'config': {}}

class AnalyticsTrendsAPI(Resource):
    @require_auth
    def get(self):
        return {'trends': {}}

class AnalyticsCustomerAPI(Resource):
    @require_auth
    def get(self, customer_id):
        return {'customer_analytics': {}}

class AnalyticsDeviceAPI(Resource):
    @require_auth
    def get(self, device_id):
        return {'device_analytics': {}}

class SystemSettingsAPI(Resource):
    @require_auth
    def get(self):
        return {'settings': {}}

class SystemLogsAPI(Resource):
    @require_auth
    def get(self):
        return {'logs': []}

class SystemBackupAPI(Resource):
    @require_auth
    def post(self):
        return {'backup_id': str(uuid.uuid4())}

# Initialize API when imported
def create_api(app, db_manager, device_manager, actiwell_api):
    """Factory function to create and configure the API"""
    
    # Store managers in app config for access by resources
    app.config['DB_MANAGER'] = db_manager
    app.config['DEVICE_MANAGER'] = device_manager
    app.config['ACTIWELL_API'] = actiwell_api
    
    # Create API instance
    api_manager = BodyCompositionAPI(app, db_manager, device_manager, actiwell_api)
    
    return api_manager

if __name__ == '__main__':
    # This would be called from the main application
    print("Enhanced API Endpoints for Body Composition Gateway")
    print("Use create_api() function to initialize with Flask app")