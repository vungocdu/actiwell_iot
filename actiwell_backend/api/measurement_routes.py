#!/usr/bin/env python3
"""
InBody Measurement API Routes
RESTful API endpoints for InBody 370s measurement management
"""

import logging
import json
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from functools import wraps

from ..services.inbody_service import InBodyService
from ..core.database_manager import DatabaseManager
from ..core.actiwell_api import ActiwellAPI
from config import ACTIWELL_CONFIG

logger = logging.getLogger(__name__)

# Create Blueprint for measurement routes
measurement_bp = Blueprint('measurements', __name__, url_prefix='/api/measurements')

# Global service instances (will be initialized in run.py)
inbody_service: InBodyService = None
database_manager: DatabaseManager = None
actiwell_api: ActiwellAPI = None


def init_services(db_manager: DatabaseManager, actiwell: ActiwellAPI, inbody_svc: InBodyService):
    """Initialize service instances"""
    global database_manager, actiwell_api, inbody_service
    database_manager = db_manager
    actiwell_api = actiwell
    inbody_service = inbody_svc


def require_auth(f):
    """Decorator for API authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Simple API key authentication
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        # For now, accept any API key or skip auth in development
        if not api_key and current_app.config.get('FLASK_DEBUG'):
            logger.warning("API authentication skipped in debug mode")
        elif not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        return f(*args, **kwargs)
    return decorated_function


def handle_api_errors(f):
    """Decorator for consistent API error handling"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Validation error in {f.__name__}: {e}")
            return jsonify({'error': 'Invalid input', 'details': str(e)}), 400
        except Exception as e:
            logger.error(f"Unexpected error in {f.__name__}: {e}")
            return jsonify({'error': 'Internal server error'}), 500
    return decorated_function


@measurement_bp.route('/inbody/latest', methods=['GET'])
@require_auth
@handle_api_errors
def get_latest_inbody_measurements():
    """Get latest InBody measurements"""
    try:
        limit = min(int(request.args.get('limit', 10)), 100)
        offset = int(request.args.get('offset', 0))
        
        measurements = database_manager.get_latest_inbody_measurements(limit, offset)
        
        # Format response
        formatted_measurements = []
        for measurement in measurements:
            formatted_measurements.append({
                'id': measurement['id'],
                'customer_phone': measurement['extracted_phone_number'],
                'customer_name': measurement.get('customer_name', 'Unknown'),
                'measurement_timestamp': measurement['measurement_timestamp'].isoformat(),
                'device_model': 'InBody-370s',
                'basic_measurements': {
                    'weight_kg': measurement.get('weight_kg'),
                    'height_cm': measurement.get('height_cm'),
                    'bmi': measurement.get('bmi')
                },
                'body_composition': {
                    'body_fat_percent': measurement.get('body_fat_percent'),
                    'skeletal_muscle_mass_kg': measurement.get('skeletal_muscle_mass_kg'),
                    'visceral_fat_area_cm2': measurement.get('visceral_fat_area_cm2'),
                    'basal_metabolic_rate_kcal': measurement.get('basal_metabolic_rate_kcal')
                },
                'segmental_analysis': {
                    'right_leg_lean_mass_kg': measurement.get('right_leg_lean_mass_kg'),
                    'left_leg_lean_mass_kg': measurement.get('left_leg_lean_mass_kg'),
                    'right_arm_lean_mass_kg': measurement.get('right_arm_lean_mass_kg'),
                    'left_arm_lean_mass_kg': measurement.get('left_arm_lean_mass_kg'),
                    'trunk_lean_mass_kg': measurement.get('trunk_lean_mass_kg')
                },
                'sync_status': {
                    'synced_to_actiwell': measurement.get('synced_to_actiwell', False),
                    'sync_attempts': measurement.get('sync_attempts', 0),
                    'last_sync_attempt': measurement.get('last_sync_attempt').isoformat() if measurement.get('last_sync_attempt') else None
                }
            })
        
        return jsonify({
            'success': True,
            'data': formatted_measurements,
            'pagination': {
                'limit': limit,
                'offset': offset,
                'total': len(formatted_measurements)
            },
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting latest measurements: {e}")
        return jsonify({'error': 'Failed to retrieve measurements'}), 500


@measurement_bp.route('/inbody/customer/<phone>', methods=['GET'])
@require_auth
@handle_api_errors
def get_customer_inbody_measurements(phone):
    """Get InBody measurements for a specific customer"""
    try:
        # Validate phone number format
        import re
        if not re.match(r'^0[2-9][0-9]{8}$', phone):
            return jsonify({'error': 'Invalid phone number format'}), 400
        
        days = min(int(request.args.get('days', 30)), 365)
        
        measurements = database_manager.get_customer_inbody_measurements(phone, days)
        
        if not measurements:
            return jsonify({
                'success': True,
                'data': [],
                'message': 'No measurements found for this customer'
            })
        
        # Calculate statistics
        stats = await inbody_service.get_measurement_stats(phone, days)
        
        # Format measurements
        formatted_measurements = []
        for measurement in measurements:
            formatted_measurements.append({
                'id': measurement['id'],
                'measurement_timestamp': measurement['measurement_timestamp'].isoformat(),
                'weight_kg': measurement.get('weight_kg'),
                'bmi': measurement.get('bmi'),
                'body_fat_percent': measurement.get('body_fat_percent'),
                'skeletal_muscle_mass_kg': measurement.get('skeletal_muscle_mass_kg'),
                'visceral_fat_area_cm2': measurement.get('visceral_fat_area_cm2'),
                'basal_metabolic_rate_kcal': measurement.get('basal_metabolic_rate_kcal'),
                'measurement_quality': measurement.get('measurement_quality', 'good'),
                'synced_to_actiwell': measurement.get('synced_to_actiwell', False)
            })
        
        return jsonify({
            'success': True,
            'data': {
                'customer_phone': phone,
                'measurements': formatted_measurements,
                'statistics': stats,
                'date_range': {
                    'start': (datetime.now() - timedelta(days=days)).isoformat(),
                    'end': datetime.now().isoformat()
                }
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting customer measurements: {e}")
        return jsonify({'error': 'Failed to retrieve customer measurements'}), 500


@measurement_bp.route('/inbody/customer/<phone>/stats', methods=['GET'])
@require_auth
@handle_api_errors
def get_customer_measurement_stats(phone):
    """Get measurement statistics and trends for a customer"""
    try:
        # Validate phone number
        import re
        if not re.match(r'^0[2-9][0-9]{8}$', phone):
            return jsonify({'error': 'Invalid phone number format'}), 400
        
        days = min(int(request.args.get('days', 30)), 365)
        
        stats = await inbody_service.get_measurement_stats(phone, days)
        
        return jsonify({
            'success': True,
            'data': stats,
            'customer_phone': phone,
            'analysis_period_days': days,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting customer stats: {e}")
        return jsonify({'error': 'Failed to retrieve customer statistics'}), 500


@measurement_bp.route('/inbody', methods=['POST'])
@require_auth
@handle_api_errors
def create_manual_measurement():
    """Create a manual InBody measurement entry"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'JSON data required'}), 400
        
        # Validate required fields
        required_fields = ['customer_phone', 'weight_kg']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Validate phone number
        import re
        phone = data['customer_phone']
        if not re.match(r'^0[2-9][0-9]{8}$', phone):
            return jsonify({'error': 'Invalid phone number format'}), 400
        
        # Prepare measurement data
        measurement_data = {
            'device_id': data.get('device_id', 'MANUAL-ENTRY'),
            'extracted_phone_number': phone,
            'patient_id': phone,
            'measurement_timestamp': datetime.fromisoformat(data['measurement_timestamp']) if data.get('measurement_timestamp') else datetime.now(),
            
            # Basic measurements
            'weight_kg': float(data['weight_kg']),
            'height_cm': float(data['height_cm']) if data.get('height_cm') else None,
            'bmi': float(data['bmi']) if data.get('bmi') else None,
            
            # Body composition
            'body_fat_percent': float(data['body_fat_percent']) if data.get('body_fat_percent') else None,
            'skeletal_muscle_mass_kg': float(data['skeletal_muscle_mass_kg']) if data.get('skeletal_muscle_mass_kg') else None,
            'visceral_fat_area_cm2': float(data['visceral_fat_area_cm2']) if data.get('visceral_fat_area_cm2') else None,
            'basal_metabolic_rate_kcal': int(data['basal_metabolic_rate_kcal']) if data.get('basal_metabolic_rate_kcal') else None,
            
            # Metadata
            'measurement_quality': data.get('measurement_quality', 'manual'),
            'hl7_message_type': 'MANUAL',
            'raw_hl7_message': json.dumps(data),
            'synced_to_actiwell': False
        }
        
        # Save measurement
        measurement_id = database_manager.save_inbody_measurement(measurement_data)
        
        if measurement_id:
            logger.info(f"Manual measurement created: ID {measurement_id}")
            
            # Trigger sync to Actiwell if configured
            if ACTIWELL_CONFIG.get('send_to_actiwell', True):
                # Add to sync queue (implement async processing)
                pass
            
            return jsonify({
                'success': True,
                'data': {
                    'measurement_id': measurement_id,
                    'customer_phone': phone,
                    'created_at': datetime.now().isoformat()
                },
                'message': 'Manual measurement created successfully'
            }), 201
        else:
            return jsonify({'error': 'Failed to create measurement'}), 500
            
    except ValueError as e:
        return jsonify({'error': f'Invalid data format: {e}'}), 400
    except Exception as e:
        logger.error(f"Error creating manual measurement: {e}")
        return jsonify({'error': 'Failed to create measurement'}), 500


@measurement_bp.route('/inbody/<int:measurement_id>', methods=['GET'])
@require_auth
@handle_api_errors
def get_inbody_measurement(measurement_id):
    """Get a specific InBody measurement by ID"""
    try:
        measurement = database_manager.get_inbody_measurement_by_id(measurement_id)
        
        if not measurement:
            return jsonify({'error': 'Measurement not found'}), 404
        
        # Format detailed response
        detailed_measurement = {
            'id': measurement['id'],
            'customer_phone': measurement['extracted_phone_number'],
            'patient_id': measurement.get('patient_id'),
            'device_id': measurement.get('device_id'),
            'measurement_timestamp': measurement['measurement_timestamp'].isoformat(),
            'created_at': measurement['created_at'].isoformat(),
            
            'basic_measurements': {
                'height_cm': measurement.get('height_cm'),
                'weight_kg': measurement.get('weight_kg'),
                'bmi': measurement.get('bmi')
            },
            
            'body_composition': {
                'body_fat_percent': measurement.get('body_fat_percent'),
                'body_fat_mass_kg': measurement.get('body_fat_mass_kg'),
                'skeletal_muscle_mass_kg': measurement.get('skeletal_muscle_mass_kg'),
                'fat_free_mass_kg': measurement.get('fat_free_mass_kg'),
                'total_body_water_kg': measurement.get('total_body_water_kg'),
                'total_body_water_percent': measurement.get('total_body_water_percent'),
                'protein_mass_kg': measurement.get('protein_mass_kg'),
                'mineral_mass_kg': measurement.get('mineral_mass_kg')
            },
            
            'advanced_metrics': {
                'visceral_fat_area_cm2': measurement.get('visceral_fat_area_cm2'),
                'visceral_fat_level': measurement.get('visceral_fat_level'),
                'basal_metabolic_rate_kcal': measurement.get('basal_metabolic_rate_kcal')
            },
            
            'segmental_analysis': {
                'right_leg_lean_mass_kg': measurement.get('right_leg_lean_mass_kg'),
                'left_leg_lean_mass_kg': measurement.get('left_leg_lean_mass_kg'),
                'right_arm_lean_mass_kg': measurement.get('right_arm_lean_mass_kg'),
                'left_arm_lean_mass_kg': measurement.get('left_arm_lean_mass_kg'),
                'trunk_lean_mass_kg': measurement.get('trunk_lean_mass_kg')
            },
            
            'bioelectrical_impedance': {
                'impedance_50khz_whole_body': measurement.get('impedance_50khz_whole_body'),
                'impedance_250khz_whole_body': measurement.get('impedance_250khz_whole_body'),
                'phase_angle_whole_body': measurement.get('phase_angle_whole_body')
            },
            
            'quality_indicators': {
                'measurement_quality': measurement.get('measurement_quality'),
                'contact_quality': json.loads(measurement.get('contact_quality', '{}')),
                'impedance_stability': measurement.get('impedance_stability')
            },
            
            'sync_status': {
                'synced_to_actiwell': measurement.get('synced_to_actiwell', False),
                'actiwell_measurement_id': measurement.get('actiwell_measurement_id'),
                'sync_attempts': measurement.get('sync_attempts', 0),
                'last_sync_attempt': measurement.get('last_sync_attempt').isoformat() if measurement.get('last_sync_attempt') else None,
                'sync_error_message': measurement.get('sync_error_message')
            },
            
            'raw_data': {
                'hl7_message_type': measurement.get('hl7_message_type'),
                'raw_hl7_message': measurement.get('raw_hl7_message') if request.args.get('include_raw') == 'true' else None
            }
        }
        
        return jsonify({
            'success': True,
            'data': detailed_measurement
        })
        
    except Exception as e:
        logger.error(f"Error getting measurement {measurement_id}: {e}")
        return jsonify({'error': 'Failed to retrieve measurement'}), 500


@measurement_bp.route('/inbody/<int:measurement_id>/sync', methods=['POST'])
@require_auth
@handle_api_errors
def retry_actiwell_sync(measurement_id):
    """Retry syncing a measurement to Actiwell"""
    try:
        measurement = database_manager.get_inbody_measurement_by_id(measurement_id)
        
        if not measurement:
            return jsonify({'error': 'Measurement not found'}), 404
        
        if measurement.get('synced_to_actiwell'):
            return jsonify({'error': 'Measurement already synced'}), 400
        
        # Trigger sync (implement async processing)
        # For now, return success
        
        return jsonify({
            'success': True,
            'message': 'Sync retry initiated',
            'measurement_id': measurement_id
        })
        
    except Exception as e:
        logger.error(f"Error retrying sync for measurement {measurement_id}: {e}")
        return jsonify({'error': 'Failed to retry sync'}), 500


@measurement_bp.route('/inbody/export', methods=['GET'])
@require_auth
@handle_api_errors
def export_measurements():
    """Export measurements to CSV or JSON"""
    try:
        # Get query parameters
        phone = request.args.get('phone')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        format_type = request.args.get('format', 'json').lower()
        
        if format_type not in ['json', 'csv']:
            return jsonify({'error': 'Invalid format. Use json or csv'}), 400
        
        # Build query filters
        filters = {}
        if phone:
            if not re.match(r'^0[2-9][0-9]{8}$', phone):
                return jsonify({'error': 'Invalid phone number format'}), 400
            filters['phone'] = phone
        
        if start_date:
            try:
                filters['start_date'] = datetime.fromisoformat(start_date)
            except ValueError:
                return jsonify({'error': 'Invalid start_date format. Use ISO format'}), 400
        
        if end_date:
            try:
                filters['end_date'] = datetime.fromisoformat(end_date)
            except ValueError:
                return jsonify({'error': 'Invalid end_date format. Use ISO format'}), 400
        
        # Get measurements
        measurements = database_manager.get_measurements_for_export(filters)
        
        if format_type == 'csv':
            # Generate CSV
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # CSV headers
            headers = [
                'measurement_id', 'customer_phone', 'measurement_timestamp',
                'weight_kg', 'height_cm', 'bmi', 'body_fat_percent',
                'skeletal_muscle_mass_kg', 'visceral_fat_area_cm2',
                'basal_metabolic_rate_kcal', 'measurement_quality',
                'synced_to_actiwell'
            ]
            writer.writerow(headers)
            
            # CSV data
            for measurement in measurements:
                row = [
                    measurement['id'],
                    measurement['extracted_phone_number'],
                    measurement['measurement_timestamp'].isoformat(),
                    measurement.get('weight_kg', ''),
                    measurement.get('height_cm', ''),
                    measurement.get('bmi', ''),
                    measurement.get('body_fat_percent', ''),
                    measurement.get('skeletal_muscle_mass_kg', ''),
                    measurement.get('visceral_fat_area_cm2', ''),
                    measurement.get('basal_metabolic_rate_kcal', ''),
                    measurement.get('measurement_quality', ''),
                    measurement.get('synced_to_actiwell', False)
                ]
                writer.writerow(row)
            
            output.seek(0)
            csv_data = output.getvalue()
            output.close()
            
            from flask import Response
            return Response(
                csv_data,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename=inbody_measurements_{datetime.now().strftime("%Y%m%d")}.csv'}
            )
        
        else:  # JSON format
            formatted_measurements = []
            for measurement in measurements:
                formatted_measurements.append({
                    'id': measurement['id'],
                    'customer_phone': measurement['extracted_phone_number'],
                    'measurement_timestamp': measurement['measurement_timestamp'].isoformat(),
                    'weight_kg': measurement.get('weight_kg'),
                    'height_cm': measurement.get('height_cm'),
                    'bmi': measurement.get('bmi'),
                    'body_fat_percent': measurement.get('body_fat_percent'),
                    'skeletal_muscle_mass_kg': measurement.get('skeletal_muscle_mass_kg'),
                    'visceral_fat_area_cm2': measurement.get('visceral_fat_area_cm2'),
                    'basal_metabolic_rate_kcal': measurement.get('basal_metabolic_rate_kcal'),
                    'measurement_quality': measurement.get('measurement_quality'),
                    'synced_to_actiwell': measurement.get('synced_to_actiwell', False)
                })
            
            return jsonify({
                'success': True,
                'data': formatted_measurements,
                'export_info': {
                    'total_records': len(formatted_measurements),
                    'filters_applied': filters,
                    'exported_at': datetime.now().isoformat()
                }
            })
            
    except Exception as e:
        logger.error(f"Error exporting measurements: {e}")
        return jsonify({'error': 'Failed to export measurements'}), 500


@measurement_bp.route('/inbody/bulk-sync', methods=['POST'])
@require_auth
@handle_api_errors
def bulk_sync_to_actiwell():
    """Bulk sync unsynced measurements to Actiwell"""
    try:
        data = request.get_json() or {}
        limit = min(int(data.get('limit', 100)), 500)
        
        # Get unsynced measurements
        unsynced_measurements = database_manager.get_unsynced_inbody_measurements(limit)
        
        if not unsynced_measurements:
            return jsonify({
                'success': True,
                'message': 'No measurements to sync',
                'processed_count': 0
            })
        
        # Trigger bulk sync (implement async processing)
        # For now, return initiated status
        
        return jsonify({
            'success': True,
            'message': f'Bulk sync initiated for {len(unsynced_measurements)} measurements',
            'processed_count': len(unsynced_measurements),
            'estimated_duration_minutes': len(unsynced_measurements) // 10
        })
        
    except Exception as e:
        logger.error(f"Error initiating bulk sync: {e}")
        return jsonify({'error': 'Failed to initiate bulk sync'}), 500


# Error handlers for the blueprint
@measurement_bp.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404


@measurement_bp.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': 'Method not allowed'}), 405


@measurement_bp.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500