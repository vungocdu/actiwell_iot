"""
Measurement Service - Business logic for processing body measurements
"""

import logging
from typing import Optional
from ..models import BodyMeasurement

logger = logging.getLogger(__name__)

class MeasurementService:
    def __init__(self, db_manager, device_manager, actiwell_api):
        self.db_manager = db_manager
        self.device_manager = device_manager
        self.actiwell_api = actiwell_api
        
    def process_measurement(self, measurement: BodyMeasurement) -> bool:
        """Process and validate measurement data"""
        try:
            # Validate measurement
            errors = measurement.validate()
            if errors:
                logger.warning(f"Measurement validation errors: {errors}")
                return False
            
            # Save to database
            measurement_id = self.db_manager.save_measurement(measurement)
            logger.info(f"Measurement saved with ID: {measurement_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing measurement: {e}")
            return False