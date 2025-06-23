# ====================================================================================
# 3. ROUTES/DEVICE_ROUTES.PY - DEVICE API ENDPOINTS
# ====================================================================================

from flask import Blueprint, request, jsonify
from run import app_state, token_required, admin_required
import logging

logger = logging.getLogger(__name__)

device_bp = Blueprint('devices', __name__)

@device_bp.route('/status')
@token_required
def get_device_status():
    """Get status of all connected devices"""
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
                'last_measurement': None,  # TODO: implement from database
                'error_count': 0  # TODO: implement
            }
        
        connected_count = sum(1 for d in devices_status.values() if d['connected'])
        
        return jsonify({
            'success': True,
            'devices': devices_status,
            'total_devices': len(devices_status),
            'connected_devices': connected_count,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting device status: {e}")
        return jsonify({'error': str(e)}), 500

@device_bp.route('/scan', methods=['POST'])
@token_required
def scan_devices():
    """Trigger device scan and connection"""
    try:
        if not app_state.device_manager:
            return jsonify({'error': 'Device manager not initialized'}), 503
        
        # Disconnect existing devices
        app_state.device_manager.disconnect_all()
        
        # Scan and connect to new devices
        app_state.device_manager.connect_devices()
        
        device_count = len(app_state.device_manager.devices)
        
        return jsonify({
            'success': True,
            'message': f'Device scan completed. Found {device_count} devices.',
            'devices_found': device_count
        })
        
    except Exception as e:
        logger.error(f"Error scanning devices: {e}")
        return jsonify({'error': str(e)}), 500

@device_bp.route('/<device_id>/control', methods=['POST'])
@token_required
@admin_required
def control_device(device_id):
    """Control device operations"""
    try:
        data = request.get_json()
        command = data.get('command') if data else None
        
        if not command:
            return jsonify({'error': 'Command is required'}), 400
        
        if command not in ['start', 'stop', 'reset', 'calibrate']:
            return jsonify({'error': 'Invalid command'}), 400
        
        # TODO: Implement device control
        return jsonify({
            'success': True,
            'message': f'Command {command} sent to device {device_id}'
        })
        
    except Exception as e:
        logger.error(f"Error controlling device {device_id}: {e}")
        return jsonify({'error': str(e)}), 500
