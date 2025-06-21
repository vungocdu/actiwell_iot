#!/usr/bin/env python3
"""
Actiwell Body Measurement Backend - Flask Application Core
Web server chính và điều phối trung tâm cho hệ thống đo thành phần cơ thể
"""

import os
import sys
import logging
import threading
import time
import queue
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Any, Optional

# Flask và extensions
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
import jwt

# Import các modules của ứng dụng
from config import Config
from models import BodyMeasurement, DeviceStatus
from database_manager import DatabaseManager
from device_manager import DeviceManager
from actiwell_api import ActiwellAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/opt/actiwell/logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ====================================================================================
# FLASK APPLICATION INITIALIZATION
# ====================================================================================

def create_app(config_class=Config):
    """
    Factory function để tạo Flask application
    """
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config_class)
    
    # Ensure secret key is set
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = 'actiwell-default-secret-key-change-in-production'
    
    return app

# Tạo Flask app instance
app = create_app()

# ====================================================================================
# CORS CONFIGURATION
# ====================================================================================

def configure_cors(app):
    """
    Cấu hình Cross-Origin Resource Sharing (CORS)
    """
    CORS(app, resources={
        r"/api/*": {
            "origins": ["http://localhost:3000", "http://localhost:5000", "*"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
            "supports_credentials": True
        },
        r"/static/*": {
            "origins": "*",
            "methods": ["GET"]
        }
    })
    
    logger.info("CORS configured successfully")

configure_cors(app)

# ====================================================================================
# APPLICATION STATE MANAGEMENT
# ====================================================================================

class ApplicationState:
    """
    Quản lý trạng thái toàn cục của ứng dụng
    """
    def __init__(self):
        self.is_running = False
        self.startup_time = None
        self.managers_initialized = False
        self.background_services_started = False
        
        # Service instances
        self.db_manager: Optional[DatabaseManager] = None
        self.device_manager: Optional[DeviceManager] = None
        self.actiwell_api: Optional[ActiwellAPI] = None
        
        # Background queues và threads
        self.measurement_queue = queue.Queue()
        self.background_threads = []
        self.shutdown_event = threading.Event()

app_state = ApplicationState()

# ====================================================================================
# MIDDLEWARE CONFIGURATION
# ====================================================================================

@app.before_request
def before_request():
    """
    Middleware chạy trước mỗi request
    """
    # Log request info
    logger.debug(f"Request: {request.method} {request.path} from {request.remote_addr}")
    
    # Add request timestamp
    request.start_time = time.time()
    
    # Check if services are initialized
    if not app_state.managers_initialized and request.endpoint not in ['health_check', 'static']:
        return jsonify({
            'error': 'System is initializing',
            'message': 'Please wait for system initialization to complete'
        }), 503

@app.after_request
def after_request(response):
    """
    Middleware chạy sau mỗi request
    """
    # Calculate request duration
    if hasattr(request, 'start_time'):
        duration = time.time() - request.start_time
        logger.debug(f"Request completed in {duration:.3f}s")
    
    # Add security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    return response

@app.errorhandler(404)
def not_found(error):
    """Global error handler cho 404"""
    return jsonify({
        'error': 'Not Found',
        'message': 'The requested resource was not found',
        'timestamp': datetime.now().isoformat()
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Global error handler cho 500"""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'error': 'Internal Server Error',
        'message': 'An unexpected error occurred',
        'timestamp': datetime.now().isoformat()
    }), 500

@app.errorhandler(Exception)
def handle_exception(e):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {e}", exc_info=True)
    
    # Return JSON error instead of HTML for API requests
    if request.path.startswith('/api/'):
        return jsonify({
            'error': 'Unexpected Error',
            'message': 'An unexpected error occurred while processing your request',
            'timestamp': datetime.now().isoformat()
        }), 500
    
    # Return HTML error page for web requests
    return render_template('error.html', error=str(e)), 500

# ====================================================================================
# AUTHENTICATION & SECURITY
# ====================================================================================

def token_required(f):
    """
    Decorator để yêu cầu JWT authentication
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check for token in Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]  # Bearer <token>
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            # Decode JWT token
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = data.get('user')
            
            # Add user info to request context
            request.current_user = current_user
            
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token is invalid'}), 401
        
        return f(*args, **kwargs)
    
    return decorated

def admin_required(f):
    """
    Decorator để yêu cầu admin privileges
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(request, 'current_user'):
            return jsonify({'error': 'Authentication required'}), 401
        
        # Check admin privileges (có thể mở rộng logic này)
        if request.current_user != 'admin':
            return jsonify({'error': 'Admin privileges required'}), 403
        
        return f(*args, **kwargs)
    
    return decorated

# ====================================================================================
# CORE ROUTES & ENDPOINTS
# ====================================================================================

@app.route('/')
def index():
    """
    Trang chủ dashboard
    """
    if not app_state.managers_initialized:
        return render_template('initializing.html')
    
    return render_template('dashboard.html')

@app.route('/api/health')
def health_check():
    """
    Health check endpoint - không yêu cầu authentication
    """
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uptime_seconds': int(time.time() - app_state.startup_time.timestamp()) if app_state.startup_time else 0,
        'version': '1.0.0',
        'services': {
            'database': False,
            'device_manager': False,
            'actiwell_api': False
        }
    }
    
    # Check service status
    if app_state.managers_initialized:
        try:
            if app_state.db_manager:
                # Test database connection
                connection = app_state.db_manager.get_connection()
                connection.close()
                health_status['services']['database'] = True
        except Exception:
            pass
        
        health_status['services']['device_manager'] = app_state.device_manager is not None
        health_status['services']['actiwell_api'] = app_state.actiwell_api is not None
    
    # Determine overall status
    all_services_ok = all(health_status['services'].values())
    if not all_services_ok:
        health_status['status'] = 'degraded'
    
    status_code = 200 if health_status['status'] == 'healthy' else 503
    return jsonify(health_status), status_code

@app.route('/api/system/info')
@token_required
def system_info():
    """
    Thông tin chi tiết về hệ thống
    """
    import psutil
    
    system_info = {
        'system': {
            'platform': sys.platform,
            'python_version': sys.version,
            'cpu_count': psutil.cpu_count(),
            'memory_total_gb': round(psutil.virtual_memory().total / (1024**3), 2),
            'disk_usage': {
                'total_gb': round(psutil.disk_usage('/').total / (1024**3), 2),
                'used_gb': round(psutil.disk_usage('/').used / (1024**3), 2),
                'free_gb': round(psutil.disk_usage('/').free / (1024**3), 2)
            }
        },
        'application': {
            'name': 'Actiwell Body Measurement Backend',
            'version': '1.0.0',
            'startup_time': app_state.startup_time.isoformat() if app_state.startup_time else None,
            'managers_initialized': app_state.managers_initialized,
            'background_services': app_state.background_services_started,
            'active_threads': len(app_state.background_threads)
        },
        'services': {
            'connected_devices': len(app_state.device_manager.devices) if app_state.device_manager else 0,
            'measurement_queue_size': app_state.measurement_queue.qsize()
        }
    }
    
    return jsonify(system_info)

# ====================================================================================
# AUTHENTICATION ENDPOINTS
# ====================================================================================

@app.route('/api/auth/login', methods=['POST'])
def login():
    """
    Authentication endpoint
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Simple authentication (trong production cần hash password)
        if username == 'admin' and password == 'actiwell123':
            # Generate JWT token
            token = jwt.encode({
                'user': username,
                'role': 'admin',
                'exp': datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRE_HOURS),
                'iat': datetime.utcnow()
            }, app.config['SECRET_KEY'], algorithm='HS256')
            
            logger.info(f"Successful login for user: {username}")
            
            return jsonify({
                'success': True,
                'token': token,
                'user': {
                    'username': username,
                    'role': 'admin'
                },
                'expires_at': (datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRE_HOURS)).isoformat()
            })
        
        logger.warning(f"Failed login attempt for user: {username}")
        return jsonify({'error': 'Invalid credentials'}), 401
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'error': 'Authentication failed'}), 500

@app.route('/api/auth/refresh', methods=['POST'])
@token_required
def refresh_token():
    """
    Refresh JWT token
    """
    try:
        # Generate new token with extended expiry
        new_token = jwt.encode({
            'user': request.current_user,
            'role': 'admin',
            'exp': datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRE_HOURS),
            'iat': datetime.utcnow()
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'success': True,
            'token': new_token,
            'expires_at': (datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRE_HOURS)).isoformat()
        })
        
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return jsonify({'error': 'Token refresh failed'}), 500

@app.route('/api/auth/logout', methods=['POST'])
@token_required
def logout():
    """
    Logout endpoint (client-side token invalidation)
    """
    logger.info(f"User {request.current_user} logged out")
    return jsonify({
        'success': True,
        'message': 'Logged out successfully'
    })

# ====================================================================================
# API ROUTE BLUEPRINTS REGISTRATION
# ====================================================================================

def register_api_blueprints():
    """
    Đăng ký các blueprint cho API endpoints
    """
    try:
        # Import và register device routes
        from routes.device_routes import device_bp
        app.register_blueprint(device_bp, url_prefix='/api/devices')
        
        # Import và register measurement routes  
        from routes.measurement_routes import measurement_bp
        app.register_blueprint(measurement_bp, url_prefix='/api/measurements')
        
        # Import và register sync routes
        from routes.sync_routes import sync_bp
        app.register_blueprint(sync_bp, url_prefix='/api/sync')
        
        # Import và register analytics routes
        from routes.analytics_routes import analytics_bp
        app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
        
        logger.info("API blueprints registered successfully")
        
    except ImportError as e:
        logger.warning(f"Some API blueprints not available: {e}")
        # Fallback: register inline routes
        register_inline_routes()

def register_inline_routes():
    """
    Fallback inline routes nếu blueprints không available
    """
    @app.route('/api/devices/status')
    @token_required
    def get_device_status():
        try:
            if not app_state.device_manager:
                return jsonify({'error': 'Device manager not initialized'}), 503
            
            devices_status = {}
            for device_id, device in app_state.device_manager.devices.items():
                devices_status[device_id] = {
                    'device_id': device_id,
                    'device_type': getattr(device, 'device_type', 'unknown'),
                    'port': getattr(device, 'port', 'unknown'),
                    'connected': getattr(device, 'is_connected', False),
                    'last_measurement': None  # TODO: implement
                }
            
            return jsonify({
                'success': True,
                'devices': devices_status,
                'total_devices': len(devices_status),
                'connected_devices': sum(1 for d in devices_status.values() if d['connected'])
            })
            
        except Exception as e:
            logger.error(f"Error getting device status: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/measurements')
    @token_required 
    def get_measurements():
        try:
            if not app_state.db_manager:
                return jsonify({'error': 'Database manager not initialized'}), 503
            
            # TODO: Implement pagination and filtering
            return jsonify({
                'success': True,
                'measurements': [],
                'pagination': {
                    'page': 1,
                    'per_page': 50,
                    'total_count': 0,
                    'total_pages': 0
                }
            })
            
        except Exception as e:
            logger.error(f"Error getting measurements: {e}")
            return jsonify({'error': str(e)}), 500

# ====================================================================================
# SERVICE INITIALIZATION
# ====================================================================================

def initialize_managers():
    """
    Khởi tạo các manager services
    """
    logger.info("Initializing application managers...")
    
    try:
        # Initialize Database Manager
        logger.info("Initializing Database Manager...")
        app_state.db_manager = DatabaseManager()
        logger.info("Database Manager initialized successfully")
        
        # Initialize Device Manager
        logger.info("Initializing Device Manager...")
        app_state.device_manager = DeviceManager(app_state.db_manager)
        logger.info("Device Manager initialized successfully")
        
        # Initialize Actiwell API
        logger.info("Initializing Actiwell API...")
        app_state.actiwell_api = ActiwellAPI(app_state.db_manager)
        logger.info("Actiwell API initialized successfully")
        
        app_state.managers_initialized = True
        logger.info("All managers initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize managers: {e}")
        app_state.managers_initialized = False
        raise

def start_background_services():
    """
    Khởi động các background services
    """
    logger.info("Starting background services...")
    
    try:
        # Start device monitoring
        if app_state.device_manager:
            app_state.device_manager.connect_devices()
            app_state.device_manager.start_monitoring()
        
        # Start measurement processor
        measurement_thread = threading.Thread(
            target=measurement_processor_service,
            name="MeasurementProcessor",
            daemon=True
        )
        measurement_thread.start()
        app_state.background_threads.append(measurement_thread)
        
        # Start sync retry service  
        sync_thread = threading.Thread(
            target=sync_retry_service,
            name="SyncRetryService", 
            daemon=True
        )
        sync_thread.start()
        app_state.background_threads.append(sync_thread)
        
        app_state.background_services_started = True
        logger.info(f"Started {len(app_state.background_threads)} background services")
        
    except Exception as e:
        logger.error(f"Failed to start background services: {e}")
        raise

# ====================================================================================
# BACKGROUND SERVICES
# ====================================================================================

def measurement_processor_service():
    """
    Background service để xử lý measurements từ devices
    """
    logger.info("Measurement processor service started")
    
    while not app_state.shutdown_event.is_set():
        try:
            # Get measurement from device manager
            if app_state.device_manager:
                measurement = app_state.device_manager.get_measurement(timeout=1.0)
                
                if measurement:
                    # Save to database
                    measurement_id = app_state.db_manager.save_measurement(measurement)
                    logger.info(f"Saved measurement ID: {measurement_id} for customer: {measurement.customer_phone}")
                    
                    # Try to sync with Actiwell
                    if app_state.actiwell_api:
                        success = app_state.actiwell_api.sync_measurement_to_actiwell(measurement)
                        app_state.db_manager.update_sync_status(
                            measurement_id, 
                            success, 
                            "" if success else "Initial sync failed"
                        )
                        
                        if success:
                            logger.info(f"Successfully synced measurement {measurement_id}")
                        else:
                            logger.warning(f"Failed to sync measurement {measurement_id}")
        
        except Exception as e:
            logger.error(f"Measurement processor error: {e}")
            time.sleep(5)

def sync_retry_service():
    """
    Background service để retry failed syncs
    """
    logger.info("Sync retry service started")
    
    while not app_state.shutdown_event.is_set():
        try:
            # Wait 5 minutes between retry cycles
            if app_state.shutdown_event.wait(300):  # 300 seconds = 5 minutes
                break
            
            # Get unsynced measurements
            if app_state.db_manager and app_state.actiwell_api:
                unsynced = app_state.db_manager.get_unsynced_measurements(20)
                
                for measurement_data in unsynced:
                    if measurement_data['sync_attempts'] < 5:  # Max 5 attempts
                        # Create measurement object from database data
                        measurement = BodyMeasurement(
                            device_id=measurement_data['device_id'],
                            device_type=measurement_data['device_type'],
                            measurement_uuid=measurement_data['measurement_uuid'],
                            customer_phone=measurement_data['customer_phone'],
                            measurement_timestamp=measurement_data['measurement_timestamp'],
                            weight_kg=measurement_data['weight_kg'],
                            # Add other fields as needed
                            raw_data=measurement_data['raw_data']
                        )
                        
                        # Retry sync
                        success = app_state.actiwell_api.sync_measurement_to_actiwell(measurement)
                        app_state.db_manager.update_sync_status(
                            measurement_data['id'],
                            success,
                            "" if success else "Retry sync failed",
                            measurement_data['sync_attempts'] + 1
                        )
                        
                        if success:
                            logger.info(f"Retry sync successful for measurement {measurement_data['id']}")
                        
                        time.sleep(1)  # Small delay between retries
        
        except Exception as e:
            logger.error(f"Sync retry service error: {e}")

# ====================================================================================
# APPLICATION STARTUP & SHUTDOWN
# ====================================================================================

def startup_application():
    """
    Khởi động ứng dụng
    """
    logger.info("=" * 60)
    logger.info("ACTIWELL BODY MEASUREMENT BACKEND STARTING")
    logger.info("=" * 60)
    
    app_state.startup_time = datetime.now()
    app_state.is_running = True
    
    try:
        # Initialize managers
        initialize_managers()
        
        # Register API routes
        register_api_blueprints()
        
        # Start background services
        start_background_services()
        
        logger.info("Application startup completed successfully")
        logger.info(f"Connected devices: {len(app_state.device_manager.devices) if app_state.device_manager else 0}")
        logger.info(f"Server ready on {Config.WEB_HOST}:{Config.WEB_PORT}")
        
    except Exception as e:
        logger.error(f"Application startup failed: {e}")
        sys.exit(1)

def shutdown_application():
    """
    Graceful shutdown của ứng dụng
    """
    logger.info("Shutting down Actiwell Backend...")
    
    # Signal background services to stop
    app_state.shutdown_event.set()
    
    # Stop device monitoring
    if app_state.device_manager:
        app_state.device_manager.stop_monitoring()
        app_state.device_manager.disconnect_all()
    
    # Wait for background threads to finish
    for thread in app_state.background_threads:
        thread.join(timeout=5)
    
    app_state.is_running = False
    logger.info("Application shutdown completed")

# ====================================================================================
# STATIC FILES SERVING
# ====================================================================================

@app.route('/static/<path:filename>')
def static_files(filename):
    """
    Serve static files
    """
    return send_from_directory('static', filename)

# ====================================================================================
# MAIN APPLICATION ENTRY POINT
# ====================================================================================

if __name__ == '__main__':
    try:
        # Startup application
        startup_application()
        
        # Run Flask application
        app.run(
            host=Config.WEB_HOST,
            port=Config.WEB_PORT,
            debug=Config.DEBUG,
            threaded=True,
            use_reloader=False  # Disable reloader to avoid issues with background threads
        )
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Application error: {e}")
    finally:
        shutdown_application()