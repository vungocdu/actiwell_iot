#!/usr/bin/env python3
"""
Actiwell IoT Backend - Main Application Entry Point
Body Composition Gateway for Tanita MC-780MA and InBody 270 Integration
Designed for Raspberry Pi deployment

Author: Actiwell Development Team
Version: 2.0.0
Compatible with: Raspberry Pi 3/4, Ubuntu Server, Debian
"""

import os
import sys
import signal
import threading
import time
import logging
import queue
from datetime import datetime
from typing import Optional
import atexit

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, jsonify
from flask_cors import CORS

# Import application components
try:
    from actiwell_backend.config import Config, DevelopmentConfig, ProductionConfig
    from actiwell_backend.core.database_manager import DatabaseManager
    from actiwell_backend.core.device_manager import DeviceManager
    from actiwell_backend.core.actiwell_api import ActiwellAPI
    from actiwell_backend.services.measurement_service import MeasurementService
    from actiwell_backend.services.sync_service import SyncService
    from actiwell_backend.services.health_service import HealthService
    from actiwell_backend.models import BodyMeasurement
    
    # Import API routes
    from actiwell_backend.api.auth_routes import auth_bp, token_required
    from actiwell_backend.api.device_routes import device_bp
    from actiwell_backend.api.measurement_routes import measurement_bp
    from actiwell_backend.api.sync_routes import sync_bp
    from actiwell_backend.api.system_routes import system_bp
    
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("📋 Please ensure all required modules are installed:")
    print("   pip install -r requirements.txt")
    print("📁 Also check that you're running from the correct directory")
    sys.exit(1)

# Global application state
class ApplicationState:
    """Global application state management"""
    
    def __init__(self):
        self.startup_time = datetime.now()
        self.shutdown_requested = False
        self.managers_initialized = False
        self.background_services_started = False
        
        # Core managers
        self.db_manager: Optional[DatabaseManager] = None
        self.device_manager: Optional[DeviceManager] = None
        self.actiwell_api: Optional[ActiwellAPI] = None
        
        # Services
        self.measurement_service: Optional[MeasurementService] = None
        self.sync_service: Optional[SyncService] = None
        self.health_service: Optional[HealthService] = None
        
        # Communication queues
        self.measurement_queue = queue.Queue()
        
        # Background threads
        self.background_threads = []
        
        # Flask app instance
        self.app: Optional[Flask] = None

# Global state instance
app_state = ApplicationState()

def setup_logging():
    """Configure comprehensive logging for production deployment"""
    log_dir = "/var/log/actiwell" if os.path.exists("/var/log") else "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'{log_dir}/actiwell_backend.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set specific log levels
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info("🔧 Logging system initialized")
    return logger

def detect_environment():
    """Detect deployment environment and return appropriate config"""
    if os.getenv('FLASK_ENV') == 'development':
        return DevelopmentConfig
    elif os.path.exists('/proc/device-tree/model'):  # Raspberry Pi detection
        return ProductionConfig
    elif os.getenv('FLASK_ENV') == 'production':
        return ProductionConfig
    else:
        return DevelopmentConfig

def initialize_database_manager(config):
    """Initialize database connection and ensure tables exist"""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("🗄️  Initializing database manager...")
        db_manager = DatabaseManager()
        
        # Test connection
        connection = db_manager.get_connection()
        if connection:
            connection.close()
            logger.info("✅ Database connection successful")
            return db_manager
        else:
            raise Exception("Failed to establish database connection")
            
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.error("💡 Please check:")
        logger.error("   - MySQL/MariaDB is running")
        logger.error("   - Database credentials in .env file")
        logger.error("   - Database and user exist")
        raise

def initialize_device_manager(db_manager):
    """Initialize device manager and start device monitoring"""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("📡 Initializing device manager...")
        device_manager = DeviceManager(db_manager)
        
        # Auto-detect and connect to devices
        if Config.AUTO_DETECT_DEVICES:
            logger.info("🔍 Auto-detecting connected devices...")
            device_manager.connect_devices()
            
            connected_count = len(device_manager.devices)
            logger.info(f"📱 Found and connected to {connected_count} devices")
            
            # Start device monitoring
            device_manager.start_monitoring()
            logger.info("👁️  Device monitoring started")
        
        return device_manager
        
    except Exception as e:
        logger.error(f"❌ Device manager initialization failed: {e}")
        logger.error("💡 Common issues:")
        logger.error("   - USB devices not connected")
        logger.error("   - User not in 'dialout' group")
        logger.error("   - FTDI drivers not installed")
        logger.warning("⚠️  Continuing without device manager...")
        return None

def initialize_actiwell_api():
    """Initialize Actiwell API integration"""
    logger = logging.getLogger(__name__)
    
    try:
        if not Config.ACTIWELL_API_URL or not Config.ACTIWELL_API_KEY:
            logger.warning("⚠️  Actiwell API credentials not configured")
            logger.warning("📝 Please update .env file with:")
            logger.warning("   ACTIWELL_API_URL=your_api_url")
            logger.warning("   ACTIWELL_API_KEY=your_api_key")
            return None
        
        logger.info("🌐 Initializing Actiwell API...")
        actiwell_api = ActiwellAPI()
        
        # Test API connection
        if actiwell_api.test_connection():
            logger.info("✅ Actiwell API connection successful")
            return actiwell_api
        else:
            logger.warning("⚠️  Actiwell API connection failed - continuing offline")
            return None
            
    except Exception as e:
        logger.error(f"❌ Actiwell API initialization failed: {e}")
        logger.warning("⚠️  Continuing without Actiwell integration...")
        return None

def initialize_services():
    """Initialize business services"""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("⚙️  Initializing business services...")
        
        # Measurement service
        app_state.measurement_service = MeasurementService(
            app_state.db_manager,
            app_state.device_manager,
            app_state.actiwell_api
        )
        
        # Sync service  
        app_state.sync_service = SyncService(
            app_state.db_manager,
            app_state.actiwell_api
        )
        
        # Health monitoring service
        app_state.health_service = HealthService(
            app_state.db_manager,
            app_state.device_manager
        )
        
        logger.info("✅ Business services initialized")
        
    except Exception as e:
        logger.error(f"❌ Services initialization failed: {e}")
        raise

def create_flask_app(config_class):
    """Create and configure Flask application"""
    logger = logging.getLogger(__name__)
    
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
    
    # Store managers in app config for access by routes
    app.config['DB_MANAGER'] = app_state.db_manager
    app.config['DEVICE_MANAGER'] = app_state.device_manager
    app.config['ACTIWELL_API'] = app_state.actiwell_api
    app.config['MEASUREMENT_SERVICE'] = app_state.measurement_service
    app.config['SYNC_SERVICE'] = app_state.sync_service
    app.config['HEALTH_SERVICE'] = app_state.health_service
    app.config['APP_STATE'] = app_state
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(device_bp, url_prefix='/api/devices')
    app.register_blueprint(measurement_bp, url_prefix='/api/measurements')
    app.register_blueprint(sync_bp, url_prefix='/api/sync')
    app.register_blueprint(system_bp, url_prefix='/api/system')
    
    # Basic routes
    @app.route('/')
    def dashboard():
        """Main dashboard"""
        if not app_state.managers_initialized:
            return render_template('initializing.html'), 503
        
        return render_template('dashboard.html', 
                             startup_time=app_state.startup_time,
                             device_count=len(app_state.device_manager.devices) if app_state.device_manager else 0)
    
    @app.route('/health')
    def health_check():
        """Health check endpoint"""
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': (datetime.now() - app_state.startup_time).total_seconds(),
            'managers_initialized': app_state.managers_initialized,
            'services': {
                'database': app_state.db_manager is not None,
                'devices': app_state.device_manager is not None,
                'actiwell_api': app_state.actiwell_api is not None
            }
        }
        
        if app_state.device_manager:
            health_status['devices'] = {
                'total': len(app_state.device_manager.devices),
                'connected': len([d for d in app_state.device_manager.devices.values() if d.is_connected])
            }
        
        return jsonify(health_status)
    
    @app.route('/api/status')
    @token_required
    def api_status():
        """Detailed API status"""
        return jsonify({
            'application': 'Actiwell Body Measurement Backend',
            'version': '2.0.0',
            'startup_time': app_state.startup_time.isoformat(),
            'managers_initialized': app_state.managers_initialized,
            'background_services': app_state.background_services_started,
            'measurement_queue_size': app_state.measurement_queue.qsize()
        })
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return render_template('error.html', error="Page not found"), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return render_template('error.html', error="Internal server error"), 500
    
    logger.info("🌐 Flask application created and configured")
    return app

def start_background_services():
    """Start background services and monitoring threads"""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("🔄 Starting background services...")
        
        # Measurement processing thread
        if app_state.device_manager:
            measurement_thread = threading.Thread(
                target=measurement_processing_loop,
                name="MeasurementProcessor",
                daemon=True
            )
            measurement_thread.start()
            app_state.background_threads.append(measurement_thread)
        
        # Sync service thread
        if app_state.actiwell_api:
            sync_thread = threading.Thread(
                target=sync_processing_loop,
                name="SyncProcessor", 
                daemon=True
            )
            sync_thread.start()
            app_state.background_threads.append(sync_thread)
        
        # Health monitoring thread
        health_thread = threading.Thread(
            target=health_monitoring_loop,
            name="HealthMonitor",
            daemon=True
        )
        health_thread.start()
        app_state.background_threads.append(health_thread)
        
        app_state.background_services_started = True
        logger.info(f"✅ Started {len(app_state.background_threads)} background services")
        
    except Exception as e:
        logger.error(f"❌ Failed to start background services: {e}")

def measurement_processing_loop():
    """Background thread to process measurements from devices"""
    logger = logging.getLogger(__name__)
    logger.info("📊 Measurement processing loop started")
    
    while not app_state.shutdown_requested:
        try:
            if app_state.device_manager:
                # Get measurement from device manager
                measurement = app_state.device_manager.get_measurement(timeout=1.0)
                
                if measurement:
                    logger.info(f"📏 Processing measurement for customer: {measurement.customer_phone}")
                    
                    # Save to database
                    measurement_id = app_state.db_manager.save_measurement(measurement)
                    
                    # Add to sync queue
                    if app_state.actiwell_api:
                        app_state.measurement_queue.put(measurement)
                    
                    logger.info(f"✅ Measurement {measurement_id} processed successfully")
            
            time.sleep(0.1)  # Small delay to prevent CPU overload
            
        except Exception as e:
            logger.error(f"❌ Error in measurement processing: {e}")
            time.sleep(5)  # Wait before retrying

def sync_processing_loop():
    """Background thread to sync measurements to Actiwell"""
    logger = logging.getLogger(__name__)
    logger.info("🔄 Sync processing loop started")
    
    while not app_state.shutdown_requested:
        try:
            # Process queued measurements
            if not app_state.measurement_queue.empty():
                measurement = app_state.measurement_queue.get(timeout=1.0)
                
                success = app_state.sync_service.sync_measurement_to_actiwell(measurement)
                if success:
                    logger.info(f"✅ Synced measurement for {measurement.customer_phone}")
                else:
                    logger.warning(f"⚠️  Failed to sync measurement for {measurement.customer_phone}")
            
            # Also sync any unsynced measurements from database
            unsynced = app_state.db_manager.get_unsynced_measurements(10)
            for measurement_data in unsynced:
                measurement = BodyMeasurement(**measurement_data)
                success = app_state.sync_service.sync_measurement_to_actiwell(measurement)
                
                app_state.db_manager.update_sync_status(
                    measurement_data['id'],
                    success,
                    "" if success else "Sync failed"
                )
            
            time.sleep(30)  # Sync every 30 seconds
            
        except queue.Empty:
            time.sleep(1)
        except Exception as e:
            logger.error(f"❌ Error in sync processing: {e}")
            time.sleep(10)

def health_monitoring_loop():
    """Background thread for system health monitoring"""
    logger = logging.getLogger(__name__)
    logger.info("💓 Health monitoring loop started")
    
    while not app_state.shutdown_requested:
        try:
            if app_state.health_service:
                health_status = app_state.health_service.check_system_health()
                
                if health_status.get('critical_issues'):
                    logger.warning("⚠️  Critical health issues detected:")
                    for issue in health_status['critical_issues']:
                        logger.warning(f"   - {issue}")
            
            time.sleep(60)  # Check every minute
            
        except Exception as e:
            logger.error(f"❌ Error in health monitoring: {e}")
            time.sleep(30)

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger = logging.getLogger(__name__)
    logger.info(f"🛑 Received signal {signum}, initiating graceful shutdown...")
    app_state.shutdown_requested = True

def shutdown_application():
    """Clean shutdown of all services"""
    logger = logging.getLogger(__name__)
    logger.info("🔄 Shutting down application...")
    
    try:
        # Stop device monitoring
        if app_state.device_manager:
            app_state.device_manager.stop_monitoring()
            app_state.device_manager.disconnect_all()
            logger.info("📱 Device manager shutdown complete")
        
        # Wait for background threads to finish
        logger.info("⏳ Waiting for background threads to finish...")
        for thread in app_state.background_threads:
            if thread.is_alive():
                thread.join(timeout=5)
        
        logger.info("✅ Application shutdown complete")
        
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")

def main():
    """Main application entry point"""
    # Setup logging first
    logger = setup_logging()
    
    try:
        logger.info("🚀 Starting Actiwell IoT Backend...")
        logger.info(f"📍 Working directory: {os.getcwd()}")
        logger.info(f"🐍 Python version: {sys.version}")
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        atexit.register(shutdown_application)
        
        # Detect environment and load config
        config_class = detect_environment()
        logger.info(f"🔧 Using configuration: {config_class.__name__}")
        
        # Initialize directories
        config_class.init_directories()
        
        # Initialize core managers
        logger.info("📋 Initializing core managers...")
        
        app_state.db_manager = initialize_database_manager(config_class)
        app_state.device_manager = initialize_device_manager(app_state.db_manager)
        app_state.actiwell_api = initialize_actiwell_api()
        
        # Initialize services
        initialize_services()
        
        app_state.managers_initialized = True
        logger.info("✅ All managers initialized successfully")
        
        # Create Flask app
        app_state.app = create_flask_app(config_class)
        
        # Start background services
        start_background_services()
        
        # Start Flask application
        logger.info("🌐 Starting web server...")
        logger.info(f"📡 Server will be available at: http://0.0.0.0:{config_class.WEB_PORT}")
        logger.info("📋 Use Ctrl+C to stop the server")
        
        app_state.app.run(
            host=config_class.WEB_HOST,
            port=config_class.WEB_PORT,
            debug=config_class.DEBUG,
            use_reloader=False,  # Disable reloader for production
            threaded=True
        )
        
    except KeyboardInterrupt:
        logger.info("👋 Shutdown requested by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
    finally:
        shutdown_application()

if __name__ == '__main__':
    main()