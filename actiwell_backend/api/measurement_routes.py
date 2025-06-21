# ====================================================================================
# 4. ROUTES/MEASUREMENT_ROUTES.PY - MEASUREMENT API ENDPOINTS
# ====================================================================================

from flask import Blueprint, request, jsonify
from run import app_state, token_required
import logging

logger = logging.getLogger(__name__)

measurement_bp = Blueprint('measurements', __name__)

@measurement_bp.route('')
@token_required
def get_measurements():
    """Get measurements with pagination and filtering"""
    try:
        if not app_state.db_manager:
            return jsonify({'error': 'Database manager not initialized'}), 503
        
        # Parse query parameters
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 50)), 100)
        customer_phone = request.args.get('customer_phone')
        device_type = request.args.get('device_type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        sync_status = request.args.get('sync_status')
        
        # Build query conditions
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
        
        if sync_status:
            if sync_status == 'synced':
                where_conditions.append("synced_to_actiwell = TRUE")
            elif sync_status == 'pending':
                where_conditions.append("synced_to_actiwell = FALSE")
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Get connection
        connection = app_state.db_manager.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        try:
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
            
            # Convert datetime objects to strings
            for measurement in measurements:
                for key, value in measurement.items():
                    if isinstance(value, datetime):
                        measurement[key] = value.isoformat()
            
            # Calculate pagination info
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
                },
                'filters': {
                    'customer_phone': customer_phone,
                    'device_type': device_type,
                    'start_date': start_date,
                    'end_date': end_date,
                    'sync_status': sync_status
                }
            })
            
        finally:
            cursor.close()
            connection.close()
        
    except Exception as e:
        logger.error(f"Error getting measurements: {e}")
        return jsonify({'error': str(e)}), 500

@measurement_bp.route('/customer/<phone>')
@token_required
def get_customer_measurements(phone):
    """Get measurements for specific customer"""
    try:
        if not app_state.db_manager:
            return jsonify({'error': 'Database manager not initialized'}), 503
        
        connection = app_state.db_manager.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        try:
            query = """
                SELECT * FROM body_measurements 
                WHERE customer_phone = %s 
                ORDER BY measurement_timestamp DESC
                LIMIT 50
            """
            
            cursor.execute(query, (phone,))
            measurements = cursor.fetchall()
            
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
            
        finally:
            cursor.close()
            connection.close()
        
    except Exception as e:
        logger.error(f"Error getting customer measurements: {e}")
        return jsonify({'error': str(e)}), 500
