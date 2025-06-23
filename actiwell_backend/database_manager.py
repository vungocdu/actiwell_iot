class DatabaseManager:
    """Enhanced database manager with connection pooling"""
    
    def __init__(self):
        self.pool = None
        self._create_connection_pool()
        self._ensure_tables_exist()
    
    def _create_connection_pool(self):
        """Create MySQL connection pool"""
        try:
            pool_config = {
                'host': Config.DB_HOST,
                'database': Config.DB_NAME,
                'user': Config.DB_USER,
                'password': Config.DB_PASSWORD,
                'pool_size': Config.DB_POOL_SIZE,
                'pool_name': 'actiwell_pool',
                'charset': 'utf8mb4',
                'collation': 'utf8mb4_unicode_ci',
                'autocommit': True
            }
            
            self.pool = pooling.MySQLConnectionPool(**pool_config)
            logger.info("Database connection pool created successfully")
            
        except Error as e:
            logger.error(f"Database pool creation error: {e}")
            raise
    
    def get_connection(self):
        """Get connection from pool"""
        try:
            return self.pool.get_connection()
        except Exception as e:
            logger.error(f"Error getting database connection: {e}")
            raise
    
    def _ensure_tables_exist(self):
        """Create database tables if they don't exist"""
        connection = self.get_connection()
        cursor = connection.cursor()
        
        try:
            # Body measurements table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS body_measurements (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    measurement_uuid VARCHAR(36) UNIQUE NOT NULL,
                    device_id VARCHAR(50) NOT NULL,
                    device_type VARCHAR(20) NOT NULL,
                    customer_phone VARCHAR(20) NOT NULL,
                    customer_id INT NULL,
                    measurement_timestamp DATETIME NOT NULL,
                    
                    -- Basic measurements
                    weight_kg DECIMAL(5,2) NULL,
                    height_cm DECIMAL(5,2) NULL,
                    bmi DECIMAL(5,2) NULL,
                    
                    -- Body composition
                    body_fat_percent DECIMAL(5,2) NULL,
                    muscle_mass_kg DECIMAL(5,2) NULL,
                    bone_mass_kg DECIMAL(5,2) NULL,
                    total_body_water_percent DECIMAL(5,2) NULL,
                    protein_percent DECIMAL(5,2) NULL,
                    mineral_percent DECIMAL(5,2) NULL,
                    
                    -- Advanced metrics
                    visceral_fat_rating INT NULL,
                    subcutaneous_fat_percent DECIMAL(5,2) NULL,
                    skeletal_muscle_mass_kg DECIMAL(5,2) NULL,
                    
                    -- Metabolic data
                    bmr_kcal INT NULL,
                    metabolic_age INT NULL,
                    
                    -- Segmental analysis
                    right_arm_muscle_kg DECIMAL(5,2) NULL,
                    left_arm_muscle_kg DECIMAL(5,2) NULL,
                    trunk_muscle_kg DECIMAL(5,2) NULL,
                    right_leg_muscle_kg DECIMAL(5,2) NULL,
                    left_leg_muscle_kg DECIMAL(5,2) NULL,
                    
                    -- Quality and sync
                    measurement_quality VARCHAR(20) DEFAULT 'good',
                    impedance_values TEXT NULL,
                    synced_to_actiwell BOOLEAN DEFAULT FALSE,
                    sync_attempts INT DEFAULT 0,
                    last_sync_attempt DATETIME NULL,
                    sync_error_message TEXT NULL,
                    
                    -- Raw data
                    raw_data TEXT NULL,
                    processing_notes TEXT NULL,
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    
                    INDEX idx_customer_phone (customer_phone),
                    INDEX idx_device_id (device_id),
                    INDEX idx_measurement_time (measurement_timestamp),
                    INDEX idx_sync_status (synced_to_actiwell),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Device status table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_status (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    device_id VARCHAR(50) UNIQUE NOT NULL,
                    device_type VARCHAR(20) NOT NULL,
                    serial_port VARCHAR(50) NOT NULL,
                    connection_status VARCHAR(20) DEFAULT 'disconnected',
                    firmware_version VARCHAR(50) NULL,
                    last_heartbeat DATETIME NULL,
                    last_measurement DATETIME NULL,
                    total_measurements INT DEFAULT 0,
                    error_count INT DEFAULT 0,
                    configuration JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    
                    INDEX idx_device_type (device_type),
                    INDEX idx_connection_status (connection_status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Sync logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    measurement_id INT NOT NULL,
                    sync_direction VARCHAR(20) NOT NULL DEFAULT 'to_actiwell',
                    sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    sync_attempts INT DEFAULT 1,
                    started_at DATETIME NOT NULL,
                    completed_at DATETIME NULL,
                    duration_ms INT NULL,
                    error_message TEXT NULL,
                    actiwell_response TEXT NULL,
                    
                    FOREIGN KEY (measurement_id) REFERENCES body_measurements(id),
                    INDEX idx_sync_status (sync_status),
                    INDEX idx_started_at (started_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Customer mapping table (cache for Actiwell customers)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customer_mapping (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    phone_number VARCHAR(20) UNIQUE NOT NULL,
                    actiwell_customer_id INT NOT NULL,
                    customer_name VARCHAR(255) NULL,
                    customer_email VARCHAR(255) NULL,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    
                    INDEX idx_phone (phone_number),
                    INDEX idx_actiwell_id (actiwell_customer_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            connection.commit()
            logger.info("Database tables created/verified successfully")
            
        except Error as e:
            logger.error(f"Table creation error: {e}")
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()
    
    def save_measurement(self, measurement: BodyMeasurement) -> int:
        """Save body measurement to database"""
        connection = self.get_connection()
        cursor = connection.cursor()
        
        try:
            query = """
                INSERT INTO body_measurements (
                    measurement_uuid, device_id, device_type, customer_phone, customer_id,
                    measurement_timestamp, weight_kg, height_cm, bmi, body_fat_percent,
                    muscle_mass_kg, bone_mass_kg, total_body_water_percent, protein_percent,
                    mineral_percent, visceral_fat_rating, subcutaneous_fat_percent,
                    skeletal_muscle_mass_kg, bmr_kcal, metabolic_age, right_arm_muscle_kg,
                    left_arm_muscle_kg, trunk_muscle_kg, right_leg_muscle_kg, 
                    left_leg_muscle_kg, measurement_quality, impedance_values,
                    raw_data, processing_notes
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """
            
            values = (
                measurement.measurement_uuid, measurement.device_id, measurement.device_type,
                measurement.customer_phone, measurement.customer_id, measurement.measurement_timestamp,
                measurement.weight_kg, measurement.height_cm, measurement.bmi,
                measurement.body_fat_percent, measurement.muscle_mass_kg, measurement.bone_mass_kg,
                measurement.total_body_water_percent, measurement.protein_percent,
                measurement.mineral_percent, measurement.visceral_fat_rating,
                measurement.subcutaneous_fat_percent, measurement.skeletal_muscle_mass_kg,
                measurement.bmr_kcal, measurement.metabolic_age, measurement.right_arm_muscle_kg,
                measurement.left_arm_muscle_kg, measurement.trunk_muscle_kg,
                measurement.right_leg_muscle_kg, measurement.left_leg_muscle_kg,
                measurement.measurement_quality, measurement.impedance_values,
                measurement.raw_data, measurement.processing_notes
            )
            
            cursor.execute(query, values)
            measurement_id = cursor.lastrowid
            
            connection.commit()
            logger.info(f"Measurement saved with ID: {measurement_id}")
            return measurement_id
            
        except Error as e:
            logger.error(f"Error saving measurement: {e}")
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()
    
    def get_unsynced_measurements(self, limit: int = 100) -> List[Dict]:
        """Get measurements not yet synced to Actiwell"""
        connection = self.get_connection()
        cursor = connection.cursor(dictionary=True)
        
        try:
            query = """
                SELECT * FROM body_measurements 
                WHERE synced_to_actiwell = FALSE 
                AND sync_attempts < 5
                ORDER BY measurement_timestamp ASC
                LIMIT %s
            """
            
            cursor.execute(query, (limit,))
            results = cursor.fetchall()
            
            return results
            
        except Error as e:
            logger.error(f"Error getting unsynced measurements: {e}")
            return []
        finally:
            cursor.close()
            connection.close()
    
    def update_sync_status(self, measurement_id: int, synced: bool, 
                          error_message: str = "", attempts: int = None):
        """Update sync status for a measurement"""
        connection = self.get_connection()
        cursor = connection.cursor()
        
        try:
            if attempts is not None:
                query = """
                    UPDATE body_measurements 
                    SET synced_to_actiwell = %s, sync_error_message = %s,
                        sync_attempts = %s, last_sync_attempt = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (synced, error_message, attempts, measurement_id))
            else:
                query = """
                    UPDATE body_measurements 
                    SET synced_to_actiwell = %s, sync_error_message = %s,
                        sync_attempts = sync_attempts + 1, last_sync_attempt = NOW()
                    WHERE id = %s
                """
                cursor.execute(query, (synced, error_message, measurement_id))
            
            connection.commit()
            
        except Error as e:
            logger.error(f"Error updating sync status: {e}")
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()
    
    def update_device_status(self, device_status: DeviceStatus):
        """Update device status in database"""
        connection = self.get_connection()
        cursor = connection.cursor()
        
        try:
            query = """
                INSERT INTO device_status (
                    device_id, device_type, serial_port, connection_status,
                    firmware_version, last_heartbeat, configuration
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    connection_status = VALUES(connection_status),
                    last_heartbeat = VALUES(last_heartbeat),
                    configuration = VALUES(configuration),
                    error_count = CASE 
                        WHEN VALUES(connection_status) = 'error' THEN error_count + 1
                        ELSE error_count
                    END
            """
            
            config_json = json.dumps(device_status.configuration) if device_status.configuration else None
            
            cursor.execute(query, (
                device_status.device_id, device_status.device_type, device_status.serial_port,
                device_status.connection_status, device_status.firmware_version,
                device_status.last_heartbeat, config_json
            ))
            
            connection.commit()
            
        except Error as e:
            logger.error(f"Error updating device status: {e}")
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()