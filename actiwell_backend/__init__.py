#!/usr/bin/env python3
"""
Actiwell Backend Application Package
=====================================
Sử dụng Application Factory pattern để khởi tạo và cấu hình ứng dụng Flask.
Đây là điểm khởi đầu trung tâm cho ứng dụng.
"""

import os
import sys
import logging
import threading
import queue
import time
from datetime import datetime
from typing import Optional

# Flask và extensions
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

# Import các thành phần của ứng dụng từ package hiện tại
from .models import BodyMeasurement, DeviceStatus
from .database_manager import DatabaseManager
from .device_manager import DeviceManager
from .actiwell_api import ActiwellAPI
from .services.measurement_processor import measurement_processor_service
from .services.sync_retry import sync_retry_service

# Import cấu hình từ file config.py ở thư mục gốc
from config import Config

# ====================================================================================
# LOGGING CONFIGURATION
# ====================================================================================

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
# APPLICATION STATE MANAGEMENT
# ====================================================================================

class ApplicationState:
    """Quản lý trạng thái toàn cục của ứng dụng, được chia sẻ giữa các threads."""
    def __init__(self):
        self.is_running = False
        self.startup_time: Optional[datetime] = None
        self.managers_initialized = False
        self.background_services_started = False
        self.db_manager: Optional[DatabaseManager] = None
        self.device_manager: Optional[DeviceManager] = None
        self.actiwell_api: Optional[ActiwellAPI] = None
        self.measurement_queue = queue.Queue()
        self.background_threads = []
        self.shutdown_event = threading.Event()

app_state = ApplicationState()


# ====================================================================================
# APPLICATION FACTORY
# ====================================================================================

def create_app(config_class=Config):
    """
    Factory function để tạo và cấu hình Flask application.
    """
    logger.info("=" * 60)
    logger.info("CREATING ACTIWELL BACKEND FLASK APPLICATION")
    logger.info("=" * 60)
    
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.config.from_object(config_class)
    
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = 'actiwell-default-secret-key-change-in-production'

    # --- KHỞI TẠO CÁC MANAGER ---
    try:
        logger.info("Initializing application managers...")
        app_state.db_manager = DatabaseManager()
        app_state.device_manager = DeviceManager(app_state.db_manager)
        app_state.actiwell_api = ActiwellAPI(app_state.db_manager)
        app_state.managers_initialized = True
        logger.info("All managers initialized successfully.")
    except Exception as e:
        logger.error(f"FATAL: Failed to initialize managers: {e}", exc_info=True)
        sys.exit(1)

    # --- ĐĂNG KÝ CÁC THÀNH PHẦN BÊN TRONG APP CONTEXT ---
    with app.app_context():
        
        # 1. Cấu hình CORS
        CORS(app, resources={r"/api/*": {"origins": "*"}})
        logger.info("CORS configured.")

        # 2. Đăng ký Middleware
        @app.before_request
        def before_request_hook():
            logger.debug(f"Request: {request.method} {request.path}")
            request.start_time = time.time()
            if not app_state.managers_initialized and request.endpoint and 'static' not in request.endpoint and 'health_check' not in request.endpoint:
                return jsonify({'error': 'System is initializing'}), 503

        @app.after_request
        def after_request_hook(response):
            if hasattr(request, 'start_time'):
                duration = time.time() - request.start_time
                logger.debug(f"Request completed in {duration:.3f}s")
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            return response

        # 3. Đăng ký Error Handlers
        @app.errorhandler(404)
        def not_found(error): return jsonify({'error': 'Not Found'}), 404
        @app.errorhandler(500)
        def internal_error(error):
            logger.error(f"Internal server error: {error}", exc_info=True)
            return jsonify({'error': 'Internal Server Error'}), 500
        @app.errorhandler(Exception)
        def handle_exception(e):
            logger.error(f"Unhandled exception: {e}", exc_info=True)
            return jsonify({'error': 'Unexpected Error'}), 500

        # 4. Đăng ký API Blueprints
        logger.info("Registering API blueprints...")
        from .api.auth_routes import auth_bp
        from .api.device_routes import device_bp
        from .api.measurement_routes import measurement_bp
        from .api.sync_routes import sync_bp
        from .api.system_routes import system_bp # <-- Import blueprint mới
        
        app.register_blueprint(auth_bp, url_prefix='/api/auth')
        app.register_blueprint(device_bp, url_prefix='/api/devices')
        app.register_blueprint(measurement_bp, url_prefix='/api/measurements')
        app.register_blueprint(sync_bp, url_prefix='/api/sync')
        app.register_blueprint(system_bp, url_prefix='/api/system') # <-- Đăng ký blueprint mới
        logger.info("API blueprints registered successfully.")
        
        # 5. Đăng ký các routes chính (Core Routes)
        @app.route('/')
        def index():
            if not app_state.managers_initialized:
                return render_template('initializing.html')
            return render_template('dashboard.html')

        @app.route('/api/health')
        def health_check():
            """Kiểm tra sức khỏe hệ thống chi tiết."""
            health_status = {
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'uptime_seconds': int(time.time() - app_state.startup_time.timestamp()) if app_state.startup_time else 0,
                'version': '1.0.0',
                'services': {
                    'database': False,
                    'device_manager': app_state.device_manager is not None,
                    'actiwell_api': app_state.actiwell_api is not None
                }
            }
            if app_state.db_manager:
                try:
                    connection = app_state.db_manager.get_connection()
                    connection.close()
                    health_status['services']['database'] = True
                except Exception:
                    health_status['services']['database'] = False
            
            if not all(health_status['services'].values()):
                health_status['status'] = 'degraded'
            
            return jsonify(health_status), 200 if health_status['status'] == 'healthy' else 503

        # 6. Khởi động các Background Services
        _start_background_services()

        app_state.startup_time = datetime.now()
        app_state.is_running = True
        logger.info("Application startup sequence completed successfully.")
        logger.info(f"Connected devices: {len(app_state.device_manager.devices) if app_state.device_manager else 0}")

    return app


def _start_background_services():
    """Hàm helper để khởi động các tiến trình chạy nền."""
    if app_state.background_services_started: return
    logger.info("Starting background services...")
    try:
        if app_state.device_manager:
            app_state.device_manager.connect_devices()
            app_state.device_manager.start_monitoring()
        
        measurement_thread = threading.Thread(target=measurement_processor_service, args=(app_state,), name="MeasurementProcessor", daemon=True)
        measurement_thread.start()
        app_state.background_threads.append(measurement_thread)
        
        sync_thread = threading.Thread(target=sync_retry_service, args=(app_state,), name="SyncRetryService", daemon=True)
        sync_thread.start()
        app_state.background_threads.append(sync_thread)
        
        app_state.background_services_started = True
        logger.info(f"Started {len(app_state.background_threads)} background services.")
    except Exception as e:
        logger.error(f"Failed to start background services: {e}", exc_info=True)
        raise

def shutdown_application():
    """Hàm để thực hiện shutdown ứng dụng một cách an toàn."""
    logger.info("Shutting down Actiwell Backend...")
    app_state.shutdown_event.set()
    if app_state.device_manager:
        app_state.device_manager.stop_monitoring()
        app_state.device_manager.disconnect_all()
    logger.info("Waiting for background threads to finish...")
    for thread in app_state.background_threads:
        thread.join(timeout=5)
    app_state.is_running = False
    logger.info("Application shutdown completed.")