#!/usr/bin/env python3
"""
Database Manager for InBody Integration
Professional database operations and connection management
"""

import logging
import mysql.connector
from mysql.connector import pooling, Error
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
import asyncio
from threading import Lock

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Professional database manager with connection pooling and error handling"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.connection_pool = None
        self.pool_lock = Lock()
        self._initialize_connection_pool()
        self._ensure_tables_exist()
    
    def _initialize_connection_pool(self):
        """Initialize MySQL connection pool"""
        try:
            pool_config = {
                'pool_name': 'inbody_pool',
                'pool_size': self.config.get('pool_size', 5),
                'pool_reset_session': True,
                'host': self.config['host'],
                'port': self.config.get('port', 3306),
                'user': self.config['user'],
                'password': self.config['password'],
                'database': self.config['database'],
                'charset': 'utf8mb4',
                'collation': 'utf8mb4_unicode_ci',
                'autocommit': True,
                'raise_on_warnings': True,
                'sql_mode': 'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO',
                'time_zone': '+00:00'
            }
            
            self.connection_pool = pooling.MySQLConnectionPool(**pool_config)
            logger.info(f"Database connection pool initialized with {pool_config['pool_size']} connections")
            
        except Error as e:
            logger.error(f"Failed to initialize database connection pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        connection = None
        try:
            with self.pool_lock:
                connection = self.connection_pool.get_connection()
            
            # Test connection
            if not connection.is_connected():
                connection.reconnect(attempts=3, delay=1)
            
            yield connection
            
        except Error as e:
            logger.error(f"Database connection error: {e}")
            if connection and connection.is_connected():
                connection.rollback()
            raise
        finally:
            if connection and connection.is_connected():
                connection.close()
    
    def _ensure_tables_exist(self):
        """Ensure all required tables exist"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                
                # Check if key tables exist
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM information_schema.tables 
                    WHERE table_schema = %s 
                    AND table_name IN ('inbody_measurements', 'customers', 'inbody_devices')
                """, (self.config['database'],))
                
                table_count = cursor.fetchone()[0]
                
                if table_count < 3:
                    logger.warning("Some required tables missing. Please run setup_database.sql")
                else:
                    logger.info("All required database tables exist")
                
                cursor.close()
                
        except Error as e:
            logger.error(f"Error checking database tables: {e}")
    
    # InBody Measurements Operations
    
    def save_inbody_measurement(self, measurement_data: Dict[str, Any]) -> Optional[int]:
        """Save InBody measurement to database"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                
                # Prepare INSERT statement
                columns = list(measurement_data.keys())
                placeholders = ', '.join(['%s'] * len(columns))
                column_names = ', '.join(columns)
                
                query = f"""
                    INSERT INTO inbody_measurements ({column_names})
                    VALUES ({placeholders})
                """
                
                values = list(measurement_data.values())
                
                cursor.execute(query, values)
                measurement_id = cursor.lastrowid
                
                cursor.close()
                
                logger.info(f"Saved InBody measurement with ID: {measurement_id}")
                return measurement_id
                
        except Error as e:
            logger.error(f"Error saving InBody measurement: {e}")
            return None
    
    def get_inbody_measurement_by_id(self, measurement_id: int) -> Optional[Dict[str, Any]]:
        """Get InBody measurement by ID"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                
                query = """
                    SELECT im.*, c.name as customer_name, c.email as customer_email
                    FROM inbody_measurements im
                    LEFT JOIN customers c ON im.customer_id = c.id
                    WHERE im.id = %s
                """
                
                cursor.execute(query, (measurement_id,))
                result = cursor.fetchone()
                cursor.close()
                
                return result
                
        except Error as e:
            logger.error(f"Error getting measurement by ID {measurement_id}: {e}")
            return None
    
    def get_latest_inbody_measurements(self, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Get latest InBody measurements"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                
                query = """
                    SELECT im.*, c.name as customer_name, c.email as customer_email,
                           id_dev.device_model, id_dev.status as device_status
                    FROM inbody_measurements im
                    LEFT JOIN customers c ON im.customer_id = c.id
                    LEFT JOIN inbody_devices id_dev ON im.device_id = id_dev.device_id
                    ORDER BY im.measurement_timestamp DESC
                    LIMIT %s OFFSET %s
                """
                
                cursor.execute(query, (limit, offset))
                results = cursor.fetchall()
                cursor.close()
                
                return results
                
        except Error as e:
            logger.error(f"Error getting latest measurements: {e}")
            return []
    
    def get_customer_inbody_measurements(self, phone: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get InBody measurements for a specific customer"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                
                query = """
                    SELECT im.*, c.name as customer_name
                    FROM inbody_measurements im
                    LEFT JOIN customers c ON im.customer_id = c.id
                    WHERE im.extracted_phone_number = %s
                    AND im.measurement_timestamp >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    ORDER BY im.measurement_timestamp DESC
                """
                
                cursor.execute(query, (phone, days))
                results = cursor.fetchall()
                cursor.close()
                
                return results
                
        except Error as e:
            logger.error(f"Error getting customer measurements for {phone}: {e}")
            return []
    
    def get_unsynced_inbody_measurements(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get InBody measurements that haven't been synced to Actiwell"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                
                query = """
                    SELECT im.*, c.actiwell_customer_id
                    FROM inbody_measurements im
                    LEFT JOIN customers c ON im.customer_id = c.id
                    WHERE im.synced_to_actiwell = FALSE
                    AND im.sync_attempts < 3
                    AND (im.last_sync_attempt IS NULL OR im.last_sync_attempt < DATE_SUB(NOW(), INTERVAL 1 HOUR))
                    ORDER BY im.measurement_timestamp ASC
                    LIMIT %s
                """
                
                cursor.execute(query, (limit,))
                results = cursor.fetchall()
                cursor.close()
                
                return results
                
        except Error as e:
            logger.error(f"Error getting unsynced measurements: {e}")
            return []
    
    def update_measurement_sync_status(self, measurement_id: int, actiwell_measurement_id: int = None, 
                                     success: bool = False, error_message: str = None) -> bool:
        """Update measurement sync status"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                
                if success:
                    query = """
                        UPDATE inbody_measurements 
                        SET synced_to_actiwell = TRUE,
                            actiwell_measurement_id = %s,
                            sync_attempts = sync_attempts + 1,
                            last_sync_attempt = NOW(),
                            sync_error_message = NULL
                        WHERE id = %s
                    """
                    cursor.execute(query, (actiwell_measurement_id, measurement_id))
                else:
                    query = """
                        UPDATE inbody_measurements 
                        SET synced_to_actiwell = FALSE,
                            sync_attempts = sync_attempts + 1,
                            last_sync_attempt = NOW(),
                            sync_error_message = %s
                        WHERE id = %s
                    """
                    cursor.execute(query, (error_message, measurement_id))
                
                cursor.close()
                return True
                
        except Error as e:
            logger.error(f"Error updating sync status for measurement {measurement_id}: {e}")
            return False
    
    def get_measurements_for_export(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get measurements for export with filters"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                
                # Build query with filters
                where_conditions = []
                params = []
                
                if filters.get('phone'):
                    where_conditions.append("im.extracted_phone_number = %s")
                    params.append(filters['phone'])
                
                if filters.get('start_date'):
                    where_conditions.append("im.measurement_timestamp >= %s")
                    params.append(filters['start_date'])
                
                if filters.get('end_date'):
                    where_conditions.append("im.measurement_timestamp <= %s")
                    params.append(filters['end_date'])
                
                where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
                
                query = f"""
                    SELECT im.*, c.name as customer_name
                    FROM inbody_measurements im
                    LEFT JOIN customers c ON im.customer_id = c.id
                    {where_clause}
                    ORDER BY im.measurement_timestamp DESC
                    LIMIT 5000
                """
                
                cursor.execute(query, params)
                results = cursor.fetchall()
                cursor.close()
                
                return results
                
        except Error as e:
            logger.error(f"Error getting measurements for export: {e}")
            return []
    
    # Customer Operations
    
    def get_customer_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Get customer by phone number"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                
                query = """
                    SELECT * FROM customers 
                    WHERE phone = %s
                """
                
                cursor.execute(query, (phone,))
                result = cursor.fetchone()
                cursor.close()
                
                return result
                
        except Error as e:
            logger.error(f"Error getting customer by phone {phone}: {e}")
            return None
    
    def create_customer(self, customer_data: Dict[str, Any]) -> Optional[int]:
        """Create new customer"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                
                columns = list(customer_data.keys())
                placeholders = ', '.join(['%s'] * len(columns))
                column_names = ', '.join(columns)
                
                query = f"""
                    INSERT INTO customers ({column_names})
                    VALUES ({placeholders})
                """
                
                values = list(customer_data.values())
                cursor.execute(query, values)
                customer_id = cursor.lastrowid
                
                cursor.close()
                
                logger.info(f"Created customer with ID: {customer_id}")
                return customer_id
                
        except Error as e:
            logger.error(f"Error creating customer: {e}")
            return None
    
    def update_customer(self, phone: str, customer_data: Dict[str, Any]) -> bool:
        """Update customer information"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                
                # Remove phone from update data to avoid conflicts
                update_data = {k: v for k, v in customer_data.items() if k != 'phone'}
                
                if not update_data:
                    return True
                
                set_clauses = [f"{key} = %s" for key in update_data.keys()]
                values = list(update_data.values()) + [phone]
                
                query = f"""
                    UPDATE customers 
                    SET {', '.join(set_clauses)}, updated_at = NOW()
                    WHERE phone = %s
                """
                
                cursor.execute(query, values)
                cursor.close()
                
                return True
                
        except Error as e:
            logger.error(f"Error updating customer {phone}: {e}")
            return False
    
    # Device Operations
    
    def update_device_status(self, device_id: str, status: str, last_heartbeat: datetime = None) -> bool:
        """Update device status"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                
                if last_heartbeat is None:
                    last_heartbeat = datetime.now()
                
                query = """
                    UPDATE inbody_devices 
                    SET status = %s, last_heartbeat = %s, updated_at = NOW()
                    WHERE device_id = %s
                """
                
                cursor.execute(query, (status, last_heartbeat, device_id))
                
                # Insert if device doesn't exist
                if cursor.rowcount == 0:
                    insert_query = """
                        INSERT INTO inbody_devices (device_id, device_model, status, last_heartbeat)
                        VALUES (%s, 'InBody-370s', %s, %s)
                        ON DUPLICATE KEY UPDATE
                        status = VALUES(status),
                        last_heartbeat = VALUES(last_heartbeat),
                        updated_at = NOW()
                    """
                    cursor.execute(insert_query, (device_id, status, last_heartbeat))
                
                cursor.close()
                return True
                
        except Error as e:
            logger.error(f"Error updating device status for {device_id}: {e}")
            return False
    
    def get_device_status(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Get device status"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                
                query = """
                    SELECT * FROM inbody_devices 
                    WHERE device_id = %s
                """
                
                cursor.execute(query, (device_id,))
                result = cursor.fetchone()
                cursor.close()
                
                return result
                
        except Error as e:
            logger.error(f"Error getting device status for {device_id}: {e}")
            return None
    
    # Analytics and Reporting
    
    def save_measurement_report(self, measurement_id: int, report_data: Dict[str, Any]) -> bool:
        """Save measurement report"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                
                query = """
                    INSERT INTO measurement_reports (measurement_id, report_data, created_at)
                    VALUES (%s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                    report_data = VALUES(report_data),
                    updated_at = NOW()
                """
                
                cursor.execute(query, (measurement_id, json.dumps(report_data)))
                cursor.close()
                
                return True
                
        except Error as e:
            logger.error(f"Error saving measurement report: {e}")
            return False
    
    def update_customer_analytics(self, analytics_data: Dict[str, Any]) -> bool:
        """Update customer analytics"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                
                query = """
                    INSERT INTO inbody_measurement_analytics 
                    (customer_id, analysis_date, measurement_count, avg_weight_kg, 
                     avg_body_fat_percent, avg_muscle_mass_kg, avg_bmr_kcal)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    measurement_count = measurement_count + VALUES(measurement_count),
                    avg_weight_kg = (avg_weight_kg + VALUES(avg_weight_kg)) / 2,
                    avg_body_fat_percent = (avg_body_fat_percent + VALUES(avg_body_fat_percent)) / 2,
                    avg_muscle_mass_kg = (avg_muscle_mass_kg + VALUES(avg_muscle_mass_kg)) / 2,
                    avg_bmr_kcal = (avg_bmr_kcal + VALUES(avg_bmr_kcal)) / 2
                """
                
                cursor.execute(query, (
                    analytics_data['customer_id'],
                    analytics_data['analysis_date'],
                    analytics_data['measurement_count'],
                    analytics_data.get('avg_weight_kg'),
                    analytics_data.get('avg_body_fat_percent'),
                    analytics_data.get('avg_muscle_mass_kg'),
                    analytics_data.get('avg_metabolic_rate_kcal')
                ))
                
                cursor.close()
                return True
                
        except Error as e:
            logger.error(f"Error updating customer analytics: {e}")
            return False
    
    def save_health_alerts(self, customer_id: int, alerts: List[str], timestamp: datetime) -> bool:
        """Save health alerts for customer"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                
                for alert in alerts:
                    query = """
                        INSERT INTO health_alerts (customer_id, alert_message, alert_timestamp, alert_type, status)
                        VALUES (%s, %s, %s, 'measurement_alert', 'active')
                    """
                    cursor.execute(query, (customer_id, alert, timestamp))
                
                cursor.close()
                return True
                
        except Error as e:
            logger.error(f"Error saving health alerts: {e}")
            return False
    
    # System Operations
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                
                # Get measurement counts
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_measurements,
                        COUNT(CASE WHEN DATE(measurement_timestamp) = CURDATE() THEN 1 END) as today_measurements,
                        COUNT(CASE WHEN DATE(measurement_timestamp) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) THEN 1 END) as week_measurements,
                        COUNT(CASE WHEN synced_to_actiwell = TRUE THEN 1 END) as synced_measurements
                    FROM inbody_measurements
                """)
                
                measurement_stats = cursor.fetchone()
                
                # Get customer counts
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_customers,
                        COUNT(CASE WHEN actiwell_customer_id IS NOT NULL THEN 1 END) as synced_customers
                    FROM customers
                """)
                
                customer_stats = cursor.fetchone()
                
                # Get device status
                cursor.execute("""
                    SELECT device_id, status, last_heartbeat
                    FROM inbody_devices
                """)
                
                devices = cursor.fetchall()
                
                cursor.close()
                
                return {
                    'measurements': measurement_stats,
                    'customers': customer_stats,
                    'devices': devices,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Error as e:
            logger.error(f"Error getting system stats: {e}")
            return {}
    
    def cleanup_old_data(self, retention_days: int = 365) -> bool:
        """Cleanup old data based on retention policy"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                
                # Clean old HL7 messages
                cursor.execute("""
                    DELETE FROM inbody_hl7_messages 
                    WHERE received_timestamp < DATE_SUB(NOW(), INTERVAL %s DAY)
                """, (retention_days,))
                
                hl7_deleted = cursor.rowcount
                
                # Clean old sync logs
                cursor.execute("""
                    DELETE FROM inbody_sync_logs 
                    WHERE started_at < DATE_SUB(NOW(), INTERVAL %s DAY)
                """, (retention_days // 2,))
                
                sync_deleted = cursor.rowcount
                
                # Update offline devices
                cursor.execute("""
                    UPDATE inbody_devices 
                    SET status = 'offline' 
                    WHERE last_heartbeat < DATE_SUB(NOW(), INTERVAL 1 HOUR)
                    AND status != 'maintenance'
                """)
                
                cursor.close()
                
                logger.info(f"Cleanup completed: {hl7_deleted} HL7 messages, {sync_deleted} sync logs deleted")
                return True
                
        except Error as e:
            logger.error(f"Error during cleanup: {e}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """Database health check"""
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                
                # Test basic connectivity
                start_time = datetime.now()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                end_time = datetime.now()
                
                response_time = (end_time - start_time).total_seconds() * 1000
                
                # Check pool status
                pool_size = self.connection_pool.pool_size
                
                cursor.close()
                
                return {
                    'status': 'healthy' if result and response_time < 1000 else 'slow',
                    'response_time_ms': response_time,
                    'pool_size': pool_size,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Error as e:
            logger.error(f"Database health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def close_pool(self):
        """Close database connection pool"""
        try:
            if self.connection_pool:
                # Close all connections in pool
                for _ in range(self.connection_pool.pool_size):
                    try:
                        conn = self.connection_pool.get_connection()
                        conn.close()
                    except:
                        pass
                
                logger.info("Database connection pool closed")
                
        except Exception as e:
            logger.error(f"Error closing connection pool: {e}")