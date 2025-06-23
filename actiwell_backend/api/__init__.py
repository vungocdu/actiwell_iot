"""
Actiwell Backend API Package
============================

REST API endpoints cho Actiwell IoT Backend.
Package này chứa tất cả API routes, authentication, và API utilities.

API Modules:
- auth_routes: Authentication và authorization endpoints
- device_routes: Device management API endpoints
- measurement_routes: Measurement data API endpoints  
- sync_routes: Data synchronization API endpoints
- system_routes: System monitoring và admin API endpoints

Author: Actiwell Development Team
Version: 2.0.0
"""

import logging
from flask import Flask, jsonify
from typing import Optional, Dict, Any

# Setup logger cho API package
logger = logging.getLogger(__name__)

# Import API blueprints với error handling
try:
    from .auth_routes import auth_bp, token_required
    logger.debug("Auth routes imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import auth_routes: {e}")
    auth_bp = None
    token_required = None

try:
    from .device_routes import device_bp
    logger.debug("Device routes imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import device_routes: {e}")
    device_bp = None

try:
    from .measurement_routes import measurement_bp
    logger.debug("Measurement routes imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import measurement_routes: {e}")
    measurement_bp = None

try:
    from .sync_routes import sync_bp
    logger.debug("Sync routes imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import sync_routes: {e}")
    sync_bp = None

try:
    from .system_routes import system_bp
    logger.debug("System routes imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import system_routes: {e}")
    system_bp = None

# Define public API
__all__ = [
    'auth_bp',
    'device_bp', 
    'measurement_bp',
    'sync_bp',
    'system_bp',
    'token_required',
    'APIManager',
    'register_all_blueprints',
    'setup_error_handlers',
    'get_api_status'
]

class APIManager:
    """
    Central manager cho tất cả API blueprints và configuration
    """
    
    def __init__(self, app: Optional[Flask] = None):
        """
        Initialize APIManager
        
        Args:
            app: Flask application instance (optional)
        """
        self.app = app
        self.blueprints_registered = False
        self.error_handlers_setup = False
        
        logger.info("APIManager initialized")
    
    def register_all_blueprints(self, app: Flask, url_prefix: str = '/api'):
        """
        Register tất cả API blueprints với Flask app
        
        Args:
            app: Flask application instance
            url_prefix: Base URL prefix cho tất cả API endpoints
        """
        try:
            logger.info("Registering API blueprints...")
            
            # Register authentication blueprint
            if auth_bp:
                app.register_blueprint(auth_bp, url_prefix=f'{url_prefix}/auth')
                logger.debug("Auth blueprint registered at /api/auth")
            
            # Register device management blueprint
            if device_bp:
                app.register_blueprint(device_bp, url_prefix=f'{url_prefix}/devices')
                logger.debug("Device blueprint registered at /api/devices")
            
            # Register measurement blueprint
            if measurement_bp:
                app.register_blueprint(measurement_bp, url_prefix=f'{url_prefix}/measurements')
                logger.debug("Measurement blueprint registered at /api/measurements")
            
            # Register sync blueprint
            if sync_bp:
                app.register_blueprint(sync_bp, url_prefix=f'{url_prefix}/sync')
                logger.debug("Sync blueprint registered at /api/sync")
            
            # Register system blueprint
            if system_bp:
                app.register_blueprint(system_bp, url_prefix=f'{url_prefix}/system')
                logger.debug("System blueprint registered at /api/system")
            
            self.blueprints_registered = True
            logger.info("✅ All API blueprints registered successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to register blueprints: {e}")
            raise
    
    def setup_error_handlers(self, app: Flask):
        """
        Setup global error handlers cho API
        
        Args:
            app: Flask application instance
        """
        try:
            logger.info("Setting up API error handlers...")
            
            @app.errorhandler(400)
            def bad_request(error):
                return jsonify({
                    'success': False,
                    'error': 'Bad Request',
                    'message': 'Invalid request data or parameters',
                    'code': 400
                }), 400
            
            @app.errorhandler(401)
            def unauthorized(error):
                return jsonify({
                    'success': False,
                    'error': 'Unauthorized', 
                    'message': 'Authentication required or invalid credentials',
                    'code': 401
                }), 401
            
            @app.errorhandler(403)
            def forbidden(error):
                return jsonify({
                    'success': False,
                    'error': 'Forbidden',
                    'message': 'Insufficient permissions for this operation',
                    'code': 403
                }), 403
            
            @app.errorhandler(404)
            def not_found(error):
                return jsonify({
                    'success': False,
                    'error': 'Not Found',
                    'message': 'The requested resource was not found',
                    'code': 404
                }), 404
            
            @app.errorhandler(422)
            def unprocessable_entity(error):
                return jsonify({
                    'success': False,
                    'error': 'Unprocessable Entity',
                    'message': 'Request was well-formed but contains semantic errors',
                    'code': 422
                }), 422
            
            @app.errorhandler(429)
            def rate_limit_exceeded(error):
                return jsonify({
                    'success': False,
                    'error': 'Rate Limit Exceeded',
                    'message': 'Too many requests. Please try again later',
                    'code': 429
                }), 429
            
            @app.errorhandler(500)
            def internal_server_error(error):
                return jsonify({
                    'success': False,
                    'error': 'Internal Server Error',
                    'message': 'An unexpected error occurred on the server',
                    'code': 500
                }), 500
            
            @app.errorhandler(503)
            def service_unavailable(error):
                return jsonify({
                    'success': False,
                    'error': 'Service Unavailable',
                    'message': 'Service is temporarily unavailable. Please try again later',
                    'code': 503
                }), 503
            
            self.error_handlers_setup = True
            logger.info("✅ API error handlers setup successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to setup error handlers: {e}")
            raise
    
    def setup_api_docs_endpoints(self, app: Flask):
        """
        Setup API documentation endpoints
        
        Args:
            app: Flask application instance
        """
        @app.route('/api', methods=['GET'])
        def api_info():
            """API information endpoint"""
            return jsonify({
                'name': 'Actiwell IoT Backend API',
                'version': __version__,
                'description': 'REST API for body composition measurement integration',
                'endpoints': {
                    'authentication': '/api/auth',
                    'devices': '/api/devices', 
                    'measurements': '/api/measurements',
                    'synchronization': '/api/sync',
                    'system': '/api/system'
                },
                'documentation': '/api/docs',
                'health_check': '/health'
            })
        
        @app.route('/api/docs', methods=['GET'])
        def api_docs():
            """API documentation endpoint"""
            return jsonify({
                'api_documentation': {
                    'auth': {
                        'POST /api/auth/login': 'Authenticate user and get JWT token',
                        'POST /api/auth/refresh': 'Refresh JWT token'
                    },
                    'devices': {
                        'GET /api/devices/status': 'Get status of all connected devices',
                        'POST /api/devices/scan': 'Scan for new devices',
                        'POST /api/devices/{id}/control': 'Control device operations'
                    },
                    'measurements': {
                        'GET /api/measurements': 'List measurements with pagination',
                        'POST /api/measurements': 'Create new measurement',
                        'GET /api/measurements/{id}': 'Get measurement details',
                        'GET /api/measurements/customer/{phone}': 'Get customer measurements'
                    },
                    'sync': {
                        'GET /api/sync/status': 'Get synchronization status',
                        'POST /api/sync/trigger': 'Trigger manual sync'
                    },
                    'system': {
                        'GET /api/system/info': 'Get system information',
                        'GET /api/system/health': 'Get system health status'
                    }
                }
            })
        
        logger.info("✅ API documentation endpoints setup")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get status của API manager
        
        Returns:
            dict: Status information
        """
        return {
            'blueprints_registered': self.blueprints_registered,
            'error_handlers_setup': self.error_handlers_setup,
            'available_blueprints': {
                'auth': auth_bp is not None,
                'devices': device_bp is not None,
                'measurements': measurement_bp is not None,
                'sync': sync_bp is not None,
                'system': system_bp is not None
            }
        }

def register_all_blueprints(app: Flask, url_prefix: str = '/api'):
    """
    Convenience function để register tất cả blueprints
    
    Args:
        app: Flask application instance
        url_prefix: Base URL prefix
    """
    api_manager = APIManager(app)
    api_manager.register_all_blueprints(app, url_prefix)
    api_manager.setup_error_handlers(app)
    api_manager.setup_api_docs_endpoints(app)
    return api_manager

def setup_error_handlers(app: Flask):
    """
    Convenience function để setup error handlers
    
    Args:
        app: Flask application instance
    """
    api_manager = APIManager(app)
    api_manager.setup_error_handlers(app)
    return api_manager

def get_api_status():
    """
    Get status của API package
    
    Returns:
        dict: Status information
    """
    status = {
        'auth_routes_available': auth_bp is not None,
        'device_routes_available': device_bp is not None,
        'measurement_routes_available': measurement_bp is not None,
        'sync_routes_available': sync_bp is not None,
        'system_routes_available': system_bp is not None,
        'token_required_available': token_required is not None,
        'package_version': __version__
    }
    
    return status

# API configuration constants
API_CONFIG = {
    'version': 'v1',
    'base_url': '/api',
    'pagination': {
        'default_page_size': 50,
        'max_page_size': 100
    },
    'rate_limiting': {
        'enabled': True,
        'default_rate': '100/hour',
        'auth_rate': '1000/hour'
    },
    'authentication': {
        'token_expiry_hours': 24,
        'refresh_token_expiry_days': 7
    }
}

# Module metadata
__version__ = "2.0.0"
__author__ = "Actiwell Development Team"
__description__ = "REST API package for Actiwell IoT Backend"

# Log package initialization
logger.info(f"Actiwell Backend API Package v{__version__} loaded")
logger.debug(f"Available blueprints: {[name for name in ['auth_bp', 'device_bp', 'measurement_bp', 'sync_bp', 'system_bp'] if globals().get(name) is not None]}")