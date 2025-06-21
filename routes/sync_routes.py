# ====================================================================================
# 5. ROUTES/SYNC_ROUTES.PY - SYNC API ENDPOINTS
# ====================================================================================

from flask import Blueprint, request, jsonify
from app import app_state, token_required
from models import BodyMeasurement
import logging

logger = logging.getLogger(__name__)

sync_bp = Blueprint('sync', __name__)

@sync_bp.route('/status')
@token_required
def get_sync_status():
    """Get sync status with Actiwell"""
    try:
        if not app_state.db_manager:
            return jsonify({'error': 'Database manager not initialized'}), 503
        
        connection = app_state.db_manager.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        try:
            # Get sync statistics for last 7 days
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
            
            # Calculate sync percentage
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
                },
                'health_status': 'healthy' if sync_percentage > 95 else 'warning' if sync_percentage > 80 else 'critical'
            })
            
        finally:
            cursor.close()
            connection.close()
        
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        return jsonify({'error': str(e)}), 500

@sync_bp.route('/trigger', methods=['POST'])
@token_required
def trigger_sync():
    """Manually trigger sync to Actiwell"""
    try:
        if not app_state.db_manager or not app_state.actiwell_api:
            return jsonify({'error': 'Required services not initialized'}), 503
        
        # Get unsynced measurements
        unsynced_measurements = app_state.db_manager.get_unsynced_measurements(50)
        
        sync_results = []
        successful_syncs = 0
        
        for measurement_data in unsynced_measurements:
            try:
                # Convert dict to BodyMeasurement object
                measurement = BodyMeasurement(
                    device_id=measurement_data['device_id'],
                    device_type=measurement_data['device_type'],
                    measurement_uuid=measurement_data['measurement_uuid'],
                    customer_phone=measurement_data['customer_phone'],
                    customer_id=measurement_data['customer_id'],
                    measurement_timestamp=measurement_data['measurement_timestamp'],
                    weight_kg=float(measurement_data['weight_kg']) if measurement_data['weight_kg'] else 0.0,
                    height_cm=float(measurement_data['height_cm']) if measurement_data['height_cm'] else 0.0,
                    bmi=float(measurement_data['bmi']) if measurement_data['bmi'] else 0.0,
                    body_fat_percent=float(measurement_data['body_fat_percent']) if measurement_data['body_fat_percent'] else 0.0,
                    muscle_mass_kg=float(measurement_data['muscle_mass_kg']) if measurement_data['muscle_mass_kg'] else 0.0,
                    bone_mass_kg=float(measurement_data['bone_mass_kg']) if measurement_data['bone_mass_kg'] else 0.0,
                    total_body_water_percent=float(measurement_data['total_body_water_percent']) if measurement_data['total_body_water_percent'] else 0.0,
                    visceral_fat_rating=int(measurement_data['visceral_fat_rating']) if measurement_data['visceral_fat_rating'] else 0,
                    bmr_kcal=int(measurement_data['bmr_kcal']) if measurement_data['bmr_kcal'] else 0,
                    metabolic_age=int(measurement_data['metabolic_age']) if measurement_data['metabolic_age'] else 0,
                    raw_data=measurement_data['raw_data'] or ""
                )
                
                # Attempt sync
                success = app_state.actiwell_api.sync_measurement_to_actiwell(measurement)
                
                # Update sync status
                app_state.db_manager.update_sync_status(
                    measurement_data['id'], 
                    success, 
                    "" if success else "Manual sync failed",
                    measurement_data['sync_attempts'] + 1
                )
                
                sync_results.append({
                    'measurement_id': measurement_data['id'],
                    'customer_phone': measurement_data['customer_phone'],
                    'success': success
                })
                
                if success:
                    successful_syncs += 1
                    
            except Exception as e:
                logger.error(f"Error syncing measurement {measurement_data['id']}: {e}")
                sync_results.append({
                    'measurement_id': measurement_data['id'],
                    'customer_phone': measurement_data['customer_phone'],
                    'success': False,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'message': f'Sync completed: {successful_syncs}/{len(sync_results)} successful',
            'results': sync_results,
            'summary': {
                'total_attempted': len(sync_results),
                'successful': successful_syncs,
                'failed': len(sync_results) - successful_syncs
            }
        })
        
    except Exception as e:
        logger.error(f"Error triggering sync: {e}")
        return jsonify({'error': str(e)}), 500
