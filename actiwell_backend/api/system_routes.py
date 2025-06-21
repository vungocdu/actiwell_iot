# /opt/actiwell/actiwell_backend/api/system_routes.py

import sys
import psutil
from flask import Blueprint, jsonify

from actiwell_backend import app_state
from .auth_routes import token_required

system_bp = Blueprint('system_bp', __name__)

@system_bp.route('/info', methods=['GET'])
@token_required
def system_info():
    """Cung cấp thông tin chi tiết về hệ thống và ứng dụng."""
    try:
        system_details = {
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
                'measurement_queue_size': app_state.measurement_queue.qsize() if app_state.measurement_queue else 0
            }
        }
        return jsonify(system_details)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500