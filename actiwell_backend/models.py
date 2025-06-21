# ====================================================================================
# 2. MODELS.PY - DATA MODELS
# ====================================================================================

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List
import uuid

@dataclass
class BodyMeasurement:
    """Body composition measurement data model"""
    
    # Device Info
    device_id: str = ""
    device_type: str = ""  # tanita, inbody
    measurement_uuid: str = ""
    
    # Customer Info
    customer_phone: str = ""
    customer_id: Optional[int] = None
    
    # Measurement Time
    measurement_timestamp: Optional[datetime] = None
    
    # Basic Measurements
    weight_kg: float = 0.0
    height_cm: float = 0.0
    bmi: float = 0.0
    
    # Body Composition
    body_fat_percent: float = 0.0
    muscle_mass_kg: float = 0.0
    bone_mass_kg: float = 0.0
    total_body_water_percent: float = 0.0
    protein_percent: float = 0.0
    mineral_percent: float = 0.0
    
    # Advanced Metrics
    visceral_fat_rating: int = 0
    subcutaneous_fat_percent: float = 0.0
    skeletal_muscle_mass_kg: float = 0.0
    
    # Metabolic Data
    bmr_kcal: int = 0
    metabolic_age: int = 0
    
    # Segmental Analysis
    right_arm_muscle_kg: float = 0.0
    left_arm_muscle_kg: float = 0.0
    trunk_muscle_kg: float = 0.0
    right_leg_muscle_kg: float = 0.0
    left_leg_muscle_kg: float = 0.0
    
    # Quality Indicators
    measurement_quality: str = "good"
    impedance_values: str = ""
    
    # Sync Status
    synced_to_actiwell: bool = False
    sync_attempts: int = 0
    last_sync_attempt: Optional[datetime] = None
    sync_error_message: str = ""
    
    # Raw Data
    raw_data: str = ""
    processing_notes: str = ""
    
    def __post_init__(self):
        """Post initialization"""
        if not self.measurement_uuid:
            self.measurement_uuid = str(uuid.uuid4())
        
        if not self.measurement_timestamp:
            self.measurement_timestamp = datetime.now()
    
    def to_dict(self):
        """Convert to dictionary with proper datetime handling"""
        result = asdict(self)
        
        # Convert datetime objects to ISO strings
        if self.measurement_timestamp:
            result['measurement_timestamp'] = self.measurement_timestamp.isoformat()
        if self.last_sync_attempt:
            result['last_sync_attempt'] = self.last_sync_attempt.isoformat()
        
        return result
    
    def validate(self) -> List[str]:
        """Validate measurement data and return error messages"""
        errors = []
        
        # Required fields validation
        if not self.customer_phone or len(self.customer_phone) < 10:
            errors.append("Valid customer phone number required")
        
        if not self.device_id:
            errors.append("Device ID is required")
        
        # Range validations
        if self.weight_kg <= 0 or self.weight_kg > 300:
            errors.append("Weight must be between 0-300 kg")
        
        if self.height_cm > 0 and (self.height_cm < 50 or self.height_cm > 250):
            errors.append("Height must be between 50-250 cm")
        
        if self.body_fat_percent < 0 or self.body_fat_percent > 60:
            errors.append("Body fat percentage must be between 0-60%")
        
        if self.age > 0 and (self.age < 5 or self.age > 120):
            errors.append("Age must be between 5-120 years")
        
        return errors

@dataclass
class DeviceStatus:
    """Device status information"""
    device_id: str
    device_type: str  # tanita_mc780ma, inbody_270, etc.
    serial_port: str
    connection_status: str  # connected, disconnected, error
    firmware_version: str = ""
    last_heartbeat: Optional[datetime] = None
    last_measurement: Optional[datetime] = None
    total_measurements: int = 0
    error_count: int = 0
    configuration: dict = None
    
    def __post_init__(self):
        if self.configuration is None:
            self.configuration = {}
