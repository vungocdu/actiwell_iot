-- Enhanced Body Composition Gateway Database Schema
-- Compatible with Actiwell Fitness Management System
-- Optimized for Raspberry Pi with MySQL

-- Drop existing tables if they exist (for fresh installation)
DROP TABLE IF EXISTS sync_logs;
DROP TABLE IF EXISTS measurement_analytics;
DROP TABLE IF EXISTS device_calibrations;
DROP TABLE IF EXISTS tanita_measurements;
DROP TABLE IF EXISTS inbody_measurements;
DROP TABLE IF EXISTS device_status;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS api_tokens;
DROP TABLE IF EXISTS system_settings;

-- System settings table
CREATE TABLE system_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(50) NOT NULL UNIQUE,
    setting_value TEXT,
    description VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default system settings
INSERT INTO system_settings (setting_key, setting_value, description) VALUES
('actiwell_api_url', '', 'Actiwell API base URL'),
('actiwell_api_key', '', 'Actiwell API authentication key'),
('actiwell_location_id', '', 'Actiwell location identifier'),
('auto_sync_enabled', 'true', 'Enable automatic sync to Actiwell'),
('measurement_timeout', '300', 'Measurement timeout in seconds'),
('device_auto_detect', 'true', 'Enable automatic device detection'),
('max_daily_measurements', '1000', 'Maximum measurements per day'),
('backup_retention_days', '30', 'Number of days to retain backups');

-- API tokens table for authentication
CREATE TABLE api_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    user_id VARCHAR(50) NOT NULL,
    permissions JSON,
    expires_at TIMESTAMP,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_token_hash (token_hash),
    INDEX idx_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Enhanced customers table (local cache of Actiwell customers)
CREATE TABLE customers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    actiwell_customer_id BIGINT,
    phone VARCHAR(15) NOT NULL,
    name VARCHAR(100),
    email VARCHAR(100),
    gender ENUM('M', 'F', 'Other') DEFAULT 'M',
    date_of_birth DATE,
    height_cm DECIMAL(5,1),
    target_weight_kg DECIMAL(5,1),
    activity_level ENUM('sedentary', 'light', 'moderate', 'active', 'very_active') DEFAULT 'moderate',
    medical_conditions TEXT,
    last_sync_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_phone (phone),
    INDEX idx_actiwell_id (actiwell_customer_id),
    INDEX idx_last_sync (last_sync_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Device status and configuration
CREATE TABLE device_status (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL UNIQUE,
    device_type ENUM('tanita_mc780ma', 'inbody_270', 'tanita_bc545n', 'other') NOT NULL,
    serial_port VARCHAR(20),
    status ENUM('connected', 'disconnected', 'error', 'calibrating') DEFAULT 'disconnected',
    firmware_version VARCHAR(20),
    last_calibration_date DATE,
    configuration JSON,
    error_message TEXT,
    connection_attempts INT DEFAULT 0,
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_device_type (device_type),
    INDEX idx_status (status),
    INDEX idx_last_heartbeat (last_heartbeat)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Device calibration records
CREATE TABLE device_calibrations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL,
    calibration_type ENUM('weight', 'impedance', 'full') NOT NULL,
    calibration_value DECIMAL(10,3),
    reference_value DECIMAL(10,3),
    deviation_percent DECIMAL(5,2),
    calibration_status ENUM('passed', 'failed', 'warning') NOT NULL,
    technician_name VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_device_id (device_id),
    INDEX idx_calibration_date (created_at),
    FOREIGN KEY (device_id) REFERENCES device_status(device_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Enhanced Tanita measurements table
CREATE TABLE tanita_measurements (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    
    -- Identification
    device_id VARCHAR(50) NOT NULL,
    customer_id BIGINT,
    extracted_phone_number VARCHAR(15) NOT NULL,
    measurement_uuid VARCHAR(36) UNIQUE,
    
    -- Timing
    measurement_timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Personal info
    gender ENUM('M', 'F') DEFAULT 'M',
    age SMALLINT UNSIGNED,
    height_cm DECIMAL(5,1),
    
    -- Basic measurements
    weight_kg DECIMAL(5,1) NOT NULL,
    bmi DECIMAL(4,1),
    standard_body_weight_kg DECIMAL(5,1),
    degree_of_obesity_percent DECIMAL(5,1),
    
    -- Body composition
    body_fat_percent DECIMAL(4,1),
    fat_mass_kg DECIMAL(5,1),
    fat_free_mass_kg DECIMAL(5,1),
    muscle_mass_kg DECIMAL(5,1),
    bone_mass_kg DECIMAL(4,1),
    total_body_water_kg DECIMAL(5,1),
    total_body_water_percent DECIMAL(4,1),
    intracellular_water_kg DECIMAL(5,1),
    extracellular_water_kg DECIMAL(5,1),
    extracellular_water_percent DECIMAL(4,1),
    protein_mass_kg DECIMAL(5,1),
    mineral_mass_kg DECIMAL(4,1),
    
    -- Advanced metrics
    visceral_fat_rating SMALLINT UNSIGNED,
    subcutaneous_fat_percent DECIMAL(4,1),
    metabolic_age SMALLINT UNSIGNED,
    bmr_kcal SMALLINT UNSIGNED,
    bmr_kj SMALLINT UNSIGNED,
    
    -- Body balance and segmental analysis
    right_arm_muscle_kg DECIMAL(4,1),
    left_arm_muscle_kg DECIMAL(4,1),
    trunk_muscle_kg DECIMAL(4,1),
    right_leg_muscle_kg DECIMAL(4,1),
    left_leg_muscle_kg DECIMAL(4,1),
    
    right_arm_fat_percent DECIMAL(4,1),
    left_arm_fat_percent DECIMAL(4,1),
    trunk_fat_percent DECIMAL(4,1),
    right_leg_fat_percent DECIMAL(4,1),
    left_leg_fat_percent DECIMAL(4,1),
    
    -- Quality indicators
    measurement_quality ENUM('excellent', 'good', 'fair', 'poor') DEFAULT 'good',
    impedance_50khz DECIMAL(6,1),
    impedance_250khz DECIMAL(6,1),
    impedance_stability BOOLEAN DEFAULT TRUE,
    
    -- Calculated scores and recommendations
    health_score SMALLINT UNSIGNED,
    fitness_level ENUM('athlete', 'excellent', 'good', 'fair', 'poor') DEFAULT 'fair',
    body_type ENUM('thin', 'healthy', 'hidden_obesity', 'obese') DEFAULT 'healthy',
    physique_rating SMALLINT UNSIGNED,
    
    -- Sync status
    synced_to_actiwell BOOLEAN DEFAULT FALSE,
    actiwell_measurement_id BIGINT,
    sync_attempts SMALLINT DEFAULT 0,
    last_sync_attempt TIMESTAMP,
    sync_error_message TEXT,
    
    -- Raw data and metadata
    raw_data LONGTEXT,
    data_checksum VARCHAR(32),
    processing_notes TEXT,
    
    -- Indexes for performance
    INDEX idx_customer_phone (extracted_phone_number),
    INDEX idx_customer_id (customer_id),
    INDEX idx_measurement_time (measurement_timestamp),
    INDEX idx_sync_status (synced_to_actiwell),
    INDEX idx_device_measurement (device_id, measurement_timestamp),
    INDEX idx_uuid (measurement_uuid),
    
    -- Foreign key constraints
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    FOREIGN KEY (device_id) REFERENCES device_status(device_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- InBody measurements table (for future expansion)
CREATE TABLE inbody_measurements (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL,
    customer_id BIGINT,
    extracted_phone_number VARCHAR(15) NOT NULL,
    measurement_uuid VARCHAR(36) UNIQUE,
    measurement_timestamp TIMESTAMP NOT NULL,
    
    -- InBody specific measurements
    weight_kg DECIMAL(5,1) NOT NULL,
    muscle_mass_kg DECIMAL(5,1),
    body_fat_mass_kg DECIMAL(5,1),
    body_fat_percent DECIMAL(4,1),
    total_body_water_l DECIMAL(5,1),
    protein_mass_kg DECIMAL(5,1),
    mineral_mass_kg DECIMAL(4,1),
    visceral_fat_area_cm2 DECIMAL(6,1),
    
    -- Segmental analysis (InBody specialty)
    skeletal_muscle_mass_kg DECIMAL(5,1),
    right_arm_lean_mass_kg DECIMAL(4,1),
    left_arm_lean_mass_kg DECIMAL(4,1),
    trunk_lean_mass_kg DECIMAL(5,1),
    right_leg_lean_mass_kg DECIMAL(4,1),
    left_leg_lean_mass_kg DECIMAL(4,1),
    
    -- Sync status
    synced_to_actiwell BOOLEAN DEFAULT FALSE,
    actiwell_measurement_id BIGINT,
    raw_data LONGTEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_customer_phone (extracted_phone_number),
    INDEX idx_measurement_time (measurement_timestamp),
    INDEX idx_sync_status (synced_to_actiwell),
    
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    FOREIGN KEY (device_id) REFERENCES device_status(device_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Measurement analytics and trends
CREATE TABLE measurement_analytics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    analysis_date DATE NOT NULL,
    measurement_count SMALLINT DEFAULT 0,
    
    -- Weight trends
    avg_weight_kg DECIMAL(5,1),
    weight_change_kg DECIMAL(5,1),
    weight_trend ENUM('increasing', 'stable', 'decreasing'),
    
    -- Body composition trends
    avg_body_fat_percent DECIMAL(4,1),
    body_fat_change_percent DECIMAL(4,1),
    avg_muscle_mass_kg DECIMAL(5,1),
    muscle_mass_change_kg DECIMAL(5,1),
    
    -- Health indicators
    avg_visceral_fat_rating DECIMAL(3,1),
    avg_metabolic_age DECIMAL(4,1),
    health_score_trend ENUM('improving', 'stable', 'declining'),
    
    -- Goals and recommendations
    weight_goal_progress_percent DECIMAL(5,1),
    body_fat_goal_progress_percent DECIMAL(5,1),
    recommendations JSON,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE KEY unique_customer_date (customer_id, analysis_date),
    INDEX idx_analysis_date (analysis_date),
    
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sync logs for tracking integration status
CREATE TABLE sync_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    sync_type ENUM('measurement', 'customer', 'device_status', 'bulk_sync') NOT NULL,
    entity_type ENUM('tanita_measurement', 'inbody_measurement', 'customer', 'device') NOT NULL,
    entity_id BIGINT NOT NULL,
    sync_direction ENUM('to_actiwell', 'from_actiwell', 'bidirectional') NOT NULL,
    
    -- Sync details
    sync_status ENUM('pending', 'success', 'failed', 'partial') NOT NULL,
    sync_attempts SMALLINT DEFAULT 1,
    
    -- Request/Response data
    request_payload JSON,
    response_data JSON,
    error_message TEXT,
    response_code SMALLINT,
    
    -- Timing
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INT,
    
    -- Metadata
    actiwell_entity_id BIGINT,
    sync_batch_id VARCHAR(36),
    user_agent VARCHAR(100) DEFAULT 'BodyCompositionGateway/1.0',
    
    INDEX idx_sync_status (sync_status),
    INDEX idx_entity (entity_type, entity_id),
    INDEX idx_sync_date (started_at),
    INDEX idx_batch_id (sync_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create views for common queries
CREATE VIEW latest_measurements_view AS
SELECT 
    tm.id,
    tm.device_id,
    tm.extracted_phone_number,
    c.name as customer_name,
    tm.measurement_timestamp,
    tm.weight_kg,
    tm.body_fat_percent,
    tm.muscle_mass_kg,
    tm.visceral_fat_rating,
    tm.metabolic_age,
    tm.health_score,
    tm.fitness_level,
    tm.synced_to_actiwell,
    ds.device_type
FROM tanita_measurements tm
LEFT JOIN customers c ON tm.customer_id = c.id
LEFT JOIN device_status ds ON tm.device_id = ds.device_id
ORDER BY tm.measurement_timestamp DESC;

CREATE VIEW customer_measurement_summary AS
SELECT 
    c.id as customer_id,
    c.phone,
    c.name,
    COUNT(tm.id) as total_measurements,
    MAX(tm.measurement_timestamp) as last_measurement_date,
    AVG(tm.weight_kg) as avg_weight_kg,
    AVG(tm.body_fat_percent) as avg_body_fat_percent,
    AVG(tm.muscle_mass_kg) as avg_muscle_mass_kg,
    AVG(tm.health_score) as avg_health_score
FROM customers c
LEFT JOIN tanita_measurements tm ON c.id = tm.customer_id
GROUP BY c.id, c.phone, c.name;

CREATE VIEW device_health_view AS
SELECT 
    ds.device_id,
    ds.device_type,
    ds.status,
    ds.last_heartbeat,
    COUNT(tm.id) as daily_measurements,
    MAX(tm.measurement_timestamp) as last_measurement
FROM device_status ds
LEFT JOIN tanita_measurements tm ON ds.device_id = tm.device_id 
    AND DATE(tm.measurement_timestamp) = CURDATE()
GROUP BY ds.device_id, ds.device_type, ds.status, ds.last_heartbeat;

-- Create stored procedures for common operations
DELIMITER //

CREATE PROCEDURE GetCustomerTrends(
    IN p_customer_id BIGINT,
    IN p_days INT DEFAULT 30
)
BEGIN
    SELECT 
        DATE(measurement_timestamp) as measurement_date,
        AVG(weight_kg) as avg_weight,
        AVG(body_fat_percent) as avg_body_fat,
        AVG(muscle_mass_kg) as avg_muscle_mass,
        AVG(visceral_fat_rating) as avg_visceral_fat,
        COUNT(*) as measurement_count
    FROM tanita_measurements
    WHERE customer_id = p_customer_id
        AND measurement_timestamp >= DATE_SUB(NOW(), INTERVAL p_days DAY)
    GROUP BY DATE(measurement_timestamp)
    ORDER BY measurement_date DESC;
END //

CREATE PROCEDURE UpdateSyncStatus(
    IN p_measurement_id BIGINT,
    IN p_actiwell_id BIGINT,
    IN p_success BOOLEAN,
    IN p_error_message TEXT
)
BEGIN
    UPDATE tanita_measurements 
    SET 
        synced_to_actiwell = p_success,
        actiwell_measurement_id = p_actiwell_id,
        sync_attempts = sync_attempts + 1,
        last_sync_attempt = NOW(),
        sync_error_message = p_error_message
    WHERE id = p_measurement_id;
END //

CREATE PROCEDURE CleanupOldData(
    IN p_retention_days INT DEFAULT 30
)
BEGIN
    -- Archive old measurements to backup table first (if needed)
    -- Then delete old records
    DELETE FROM sync_logs 
    WHERE started_at < DATE_SUB(NOW(), INTERVAL p_retention_days DAY);
    
    DELETE FROM measurement_analytics 
    WHERE analysis_date < DATE_SUB(NOW(), INTERVAL p_retention_days DAY);
    
    -- Update device heartbeat cleanup
    UPDATE device_status 
    SET status = 'disconnected' 
    WHERE last_heartbeat < DATE_SUB(NOW(), INTERVAL 1 HOUR);
END //

DELIMITER ;

-- Create triggers for data integrity and automation
DELIMITER //

CREATE TRIGGER tr_tanita_measurement_insert
AFTER INSERT ON tanita_measurements
FOR EACH ROW
BEGIN
    -- Generate UUID if not provided
    IF NEW.measurement_uuid IS NULL THEN
        UPDATE tanita_measurements 
        SET measurement_uuid = UUID() 
        WHERE id = NEW.id;
    END IF;
    
    -- Create sync log entry
    INSERT INTO sync_logs (
        sync_type, entity_type, entity_id, sync_direction, sync_status
    ) VALUES (
        'measurement', 'tanita_measurement', NEW.id, 'to_actiwell', 'pending'
    );
END //

CREATE TRIGGER tr_customer_phone_update
BEFORE UPDATE ON customers
FOR EACH ROW
BEGIN
    -- Update last_sync_at when customer data changes
    IF OLD.phone != NEW.phone OR OLD.name != NEW.name OR OLD.email != NEW.email THEN
        SET NEW.last_sync_at = NULL;  -- Force re-sync
    END IF;
END //

DELIMITER ;

-- Insert sample data for testing
INSERT INTO device_status (device_id, device_type, serial_port, status, firmware_version) VALUES
('TANITA_001', 'tanita_mc780ma', '/dev/ttyUSB0', 'connected', '1.2.3'),
('INBODY_001', 'inbody_270', '/dev/ttyUSB1', 'connected', '2.1.0');

INSERT INTO customers (phone, name, email, gender, height_cm) VALUES
('0901234567', 'Nguyen Van A', 'nguyenvana@email.com', 'M', 175.0),
('0902345678', 'Tran Thi B', 'tranthib@email.com', 'F', 165.0);

-- Create indexes for performance optimization
CREATE INDEX idx_tanita_phone_date ON tanita_measurements(extracted_phone_number, measurement_timestamp);
CREATE INDEX idx_tanita_sync_pending ON tanita_measurements(synced_to_actiwell, last_sync_attempt);
CREATE INDEX idx_sync_logs_status_date ON sync_logs(sync_status, started_at);

-- Final optimization
ANALYZE TABLE tanita_measurements;
ANALYZE TABLE customers;
ANALYZE TABLE device_status;
ANALYZE TABLE sync_logs;