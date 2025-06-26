#!/usr/bin/env python3
"""
Measurement Service - Common business logic for processing body measurements
Handles both Tanita and InBody devices with unified processing pipeline
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
import json

from ..devices.base_protocol import MeasurementData, MeasurementStatus
from ..core.database_manager import DatabaseManager
from ..core.actiwell_api import ActiwellAPI

logger = logging.getLogger(__name__)

class MeasurementService:
    """
    Common measurement processing service for all body composition devices
    Provides unified business logic for Tanita, InBody, and other devices
    """
    
    def __init__(self, database_manager: DatabaseManager, actiwell_api: ActiwellAPI = None, config: Dict = None):
        """
        Initialize measurement service
        
        Args:
            database_manager: Database manager for storing measurements
            actiwell_api: Actiwell API for customer lookup and sync
            config: Service configuration
        """
        self.database_manager = database_manager
        self.actiwell_api = actiwell_api
        self.config = config or {}
        
        # Business rules configuration
        self.auto_customer_creation = self.config.get('auto_customer_creation', True)
        self.measurement_validation_enabled = self.config.get('measurement_validation_enabled', True)
        self.health_alerts_enabled = self.config.get('health_alerts_enabled', True)
        self.analytics_update_enabled = self.config.get('analytics_update_enabled', True)
        
        # Device-specific processing rules
        self.device_processors = {
            'tanita_mc780ma': self._process_tanita_measurement,
            'tanita': self._process_tanita_measurement,
            'inbody_270': self._process_inbody_measurement,
            'inbody': self._process_inbody_measurement,
        }
        
        logger.info("Measurement Service initialized")
    
    async def process_measurement_async(self, measurement: MeasurementData, device_type: str = None) -> bool:
        """
        Asynchronously process a body composition measurement
        
        Args:
            measurement: Measurement data to process
            device_type: Type of device (for device-specific processing)
            
        Returns:
            bool: True if processing successful
        """
        try:
            start_time = datetime.now()
            logger.info(f"Processing measurement for customer: {measurement.customer_phone}")
            
            # Step 1: Validate measurement data
            if self.measurement_validation_enabled:
                validation_result = await self._validate_measurement(measurement)
                if not validation_result['valid']:
                    logger.warning(f"Measurement validation failed: {validation_result['errors']}")
                    measurement.status = MeasurementStatus.INVALID
                    # Still save invalid measurements for debugging
                    await self._save_measurement_to_database(measurement, customer_info={})
                    return False
            
            # Step 2: Customer identification and lookup
            customer_info = await self._identify_customer(measurement)
            
            # Step 3: Device-specific processing
            device_type = device_type or measurement.device_type
            if device_type in self.device_processors:
                await self.device_processors[device_type](measurement, customer_info)
            else:
                logger.warning(f"No specific processor for device type: {device_type}")
                await self._process_generic_measurement(measurement, customer_info)
            
            # Step 4: Save to database
            measurement_id = await self._save_measurement_to_database(measurement, customer_info)
            
            if not measurement_id:
                logger.error("Failed to save measurement to database")
                return False
            
            # Step 5: Post-processing tasks
            await self._post_process_measurement(measurement_id, measurement, customer_info)
            
            # Step 6: Update analytics
            if self.analytics_update_enabled and customer_info.get('id'):
                await self._update_customer_analytics(customer_info['id'], measurement)
            
            # Step 7: Health alerts
            if self.health_alerts_enabled:
                await self._check_health_alerts(measurement, customer_info)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"Successfully processed measurement {measurement_id} in {processing_time:.2f}s")
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing measurement: {e}")
            return False
    
    def process_measurement(self, measurement: MeasurementData, device_type: str = None) -> bool:
        """
        Synchronous wrapper for measurement processing
        
        Args:
            measurement: Measurement data to process
            device_type: Type of device
            
        Returns:
            bool: True if processing successful
        """
        try:
            # Run async processing in sync context
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                self.process_measurement_async(measurement, device_type)
            )
        except Exception as e:
            logger.error(f"Error in synchronous measurement processing: {e}")
            return False
    
    async def _validate_measurement(self, measurement: MeasurementData) -> Dict[str, Any]:
        """
        Validate measurement data using comprehensive business rules
        
        Args:
            measurement: Measurement to validate
            
        Returns:
            Dict: Validation result with 'valid' status and 'errors' list
        """
        try:
            errors = []
            warnings = []
            
            # Basic required fields validation
            if not measurement.customer_phone:
                errors.append("Missing customer phone number")
            
            if not measurement.weight_kg or measurement.weight_kg <= 0:
                errors.append("Invalid or missing weight")
            
            # Phone number format validation (Vietnamese)
            if measurement.customer_phone:
                import re
                phone_pattern = r'^0[2-9][0-9]{8}$'
                if not re.match(phone_pattern, measurement.customer_phone):
                    errors.append(f"Invalid phone number format: {measurement.customer_phone}")
            
            # Physiological validation
            if measurement.weight_kg:
                if measurement.weight_kg < 10 or measurement.weight_kg > 300:
                    errors.append(f"Weight outside realistic range: {measurement.weight_kg}kg")
                elif measurement.weight_kg < 30 or measurement.weight_kg > 200:
                    warnings.append(f"Weight outside typical range: {measurement.weight_kg}kg")
            
            if measurement.height_cm:
                if measurement.height_cm < 50 or measurement.height_cm > 250:
                    errors.append(f"Height outside realistic range: {measurement.height_cm}cm")
                elif measurement.height_cm < 100 or measurement.height_cm > 220:
                    warnings.append(f"Height outside typical range: {measurement.height_cm}cm")
            
            if measurement.age:
                if measurement.age < 3 or measurement.age > 120:
                    errors.append(f"Age outside realistic range: {measurement.age}")
                elif measurement.age < 10 or measurement.age > 100:
                    warnings.append(f"Age outside typical range: {measurement.age}")
            
            # Body composition validation
            if measurement.body_fat_percent:
                if measurement.body_fat_percent < 0 or measurement.body_fat_percent > 70:
                    errors.append(f"Body fat percentage outside realistic range: {measurement.body_fat_percent}%")
                elif measurement.body_fat_percent < 3 or measurement.body_fat_percent > 50:
                    warnings.append(f"Body fat percentage outside typical range: {measurement.body_fat_percent}%")
            
            if measurement.muscle_mass_kg and measurement.weight_kg:
                muscle_ratio = measurement.muscle_mass_kg / measurement.weight_kg
                if muscle_ratio > 0.85:
                    errors.append(f"Muscle mass ratio too high: {muscle_ratio:.2f}")
                elif muscle_ratio < 0.2:
                    errors.append(f"Muscle mass ratio too low: {muscle_ratio:.2f}")
            
            # BMI validation
            if measurement.weight_kg and measurement.height_cm:
                calculated_bmi = measurement.weight_kg / ((measurement.height_cm / 100) ** 2)
                if measurement.bmi:
                    bmi_difference = abs(measurement.bmi - calculated_bmi)
                    if bmi_difference > 2.0:
                        warnings.append(f"BMI calculation discrepancy: {bmi_difference:.1f}")
                else:
                    measurement.bmi = calculated_bmi
            
            # Device-specific validation
            await self._device_specific_validation(measurement, errors, warnings)
            
            # Update measurement with validation results
            measurement.validation_errors = errors + warnings
            
            return {
                'valid': len(errors) == 0,
                'errors': errors,
                'warnings': warnings,
                'validation_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error validating measurement: {e}")
            return {
                'valid': False,
                'errors': [f"Validation error: {str(e)}"],
                'warnings': []
            }
    
    async def _device_specific_validation(self, measurement: MeasurementData, errors: List[str], warnings: List[str]):
        """Apply device-specific validation rules"""
        try:
            device_type = measurement.device_type.lower()
            
            if 'tanita' in device_type:
                # Tanita-specific validations
                if measurement.visceral_fat_rating:
                    if measurement.visceral_fat_rating < 1 or measurement.visceral_fat_rating > 59:
                        errors.append(f"Tanita visceral fat rating outside range: {measurement.visceral_fat_rating}")
                
                # Check for segmental data completeness
                segmental_fields = [
                    measurement.right_leg_muscle_kg, measurement.left_leg_muscle_kg,
                    measurement.right_arm_muscle_kg, measurement.left_arm_muscle_kg,
                    measurement.trunk_muscle_kg
                ]
                if any(segmental_fields) and not all(segmental_fields):
                    warnings.append("Incomplete segmental analysis data")
            
            elif 'inbody' in device_type:
                # InBody-specific validations
                if measurement.total_body_water_percent:
                    if measurement.total_body_water_percent < 30 or measurement.total_body_water_percent > 80:
                        warnings.append(f"Body water percentage outside typical range: {measurement.total_body_water_percent}%")
                
                # InBody phase angle validation
                if measurement.phase_angle:
                    if measurement.phase_angle < 2.0 or measurement.phase_angle > 15.0:
                        warnings.append(f"Phase angle outside typical range: {measurement.phase_angle}°")
            
        except Exception as e:
            logger.error(f"Error in device-specific validation: {e}")
            warnings.append(f"Device validation error: {str(e)}")
    
    async def _identify_customer(self, measurement: MeasurementData) -> Dict[str, Any]:
        """
        Identify customer from measurement data
        
        Args:
            measurement: Measurement containing customer identification
            
        Returns:
            Dict: Customer information
        """
        try:
            customer_info = {}
            
            if not measurement.customer_phone:
                logger.warning("No customer phone number in measurement")
                return customer_info
            
            # First check local database
            local_customer = await self.database_manager.get_customer_by_phone(measurement.customer_phone)
            
            if local_customer:
                logger.debug(f"Found customer in local database: {measurement.customer_phone}")
                customer_info = local_customer
                
                # Check if we have Actiwell ID
                if not customer_info.get('actiwell_customer_id') and self.actiwell_api:
                    # Try to find in Actiwell and update local record
                    actiwell_customer = await self._lookup_customer_in_actiwell(measurement.customer_phone)
                    if actiwell_customer:
                        customer_info.update(actiwell_customer)
                        await self.database_manager.update_customer(measurement.customer_phone, actiwell_customer)
            
            else:
                # Customer not in local database, check Actiwell
                if self.actiwell_api:
                    actiwell_customer = await self._lookup_customer_in_actiwell(measurement.customer_phone)
                    if actiwell_customer:
                        logger.info(f"Found customer in Actiwell: {measurement.customer_phone}")
                        customer_info = actiwell_customer
                        
                        # Save to local database
                        await self.database_manager.create_customer(customer_info)
                    
                # If still no customer found and auto-creation enabled
                if not customer_info and self.auto_customer_creation:
                    customer_info = await self._create_pending_customer(measurement)
            
            return customer_info
            
        except Exception as e:
            logger.error(f"Error identifying customer: {e}")
            return {}
    
    async def _lookup_customer_in_actiwell(self, phone_number: str) -> Optional[Dict]:
        """Lookup customer in Actiwell system"""
        try:
            if not self.actiwell_api:
                return None
            
            # Use config for location/operator IDs
            location_id = self.config.get('actiwell_location_id', 1)
            operator_id = self.config.get('actiwell_operator_id', 1)
            
            customer = await self.actiwell_api.search_customer_by_phone(
                phone_number,
                location_id=location_id,
                operator_id=operator_id
            )
            
            return customer
            
        except Exception as e:
            logger.error(f"Error looking up customer in Actiwell: {e}")
            return None
    
    async def _create_pending_customer(self, measurement: MeasurementData) -> Dict:
        """Create pending customer entry for unknown customers"""
        try:
            customer_data = {
                'phone': measurement.customer_phone,
                'name': f'Customer {measurement.customer_phone[-4:]}',  # Temporary name
                'gender': measurement.gender or 'M',
                'age': measurement.age,
                'height_cm': measurement.height_cm,
                'status': 'pending_verification',
                'created_from': f'{measurement.device_type}_measurement',
                'first_measurement_date': measurement.measurement_timestamp,
                'notes': 'Auto-created from body composition measurement'
            }
            
            customer_id = await self.database_manager.create_customer(customer_data)
            
            if customer_id:
                logger.info(f"Created pending customer: {measurement.customer_phone}")
                customer_data['id'] = customer_id
                return customer_data
            
            return {}
            
        except Exception as e:
            logger.error(f"Error creating pending customer: {e}")
            return {}
    
    async def _process_tanita_measurement(self, measurement: MeasurementData, customer_info: Dict):
        """Process Tanita-specific measurement data"""
        try:
            logger.debug("Applying Tanita-specific processing")
            
            # Tanita-specific business rules
            if measurement.processing_notes:
                measurement.processing_notes += "; Tanita MC-780MA processed"
            else:
                measurement.processing_notes = "Tanita MC-780MA processed"
            
            # Tanita data quality assessment
            if not measurement.measurement_quality:
                measurement.measurement_quality = self._assess_tanita_quality(measurement)
            
            # Tanita segmental balance analysis
            self._analyze_tanita_segmental_balance(measurement)
            
        except Exception as e:
            logger.error(f"Error in Tanita-specific processing: {e}")
    
    async def _process_inbody_measurement(self, measurement: MeasurementData, customer_info: Dict):
        """Process InBody-specific measurement data"""
        try:
            logger.debug("Applying InBody-specific processing")
            
            # InBody-specific business rules
            if measurement.processing_notes:
                measurement.processing_notes += "; InBody HL7 processed"
            else:
                measurement.processing_notes = "InBody HL7 processed"
            
            # InBody data quality assessment
            if not measurement.measurement_quality:
                measurement.measurement_quality = self._assess_inbody_quality(measurement)
            
            # InBody lean mass analysis
            self._analyze_inbody_lean_mass(measurement)
            
        except Exception as e:
            logger.error(f"Error in InBody-specific processing: {e}")
    
    async def _process_generic_measurement(self, measurement: MeasurementData, customer_info: Dict):
        """Process generic measurement data"""
        try:
            logger.debug("Applying generic measurement processing")
            
            if measurement.processing_notes:
                measurement.processing_notes += "; Generic processing applied"
            else:
                measurement.processing_notes = "Generic processing applied"
            
            # Generic quality assessment
            if not measurement.measurement_quality:
                measurement.measurement_quality = self._assess_generic_quality(measurement)
            
        except Exception as e:
            logger.error(f"Error in generic processing: {e}")
    
    def _assess_tanita_quality(self, measurement: MeasurementData) -> str:
        """Assess measurement quality for Tanita devices"""
        try:
            quality_score = 0
            
            # Basic measurements
            if measurement.weight_kg and measurement.weight_kg > 0:
                quality_score += 1
            if measurement.body_fat_percent and measurement.body_fat_percent > 0:
                quality_score += 1
            if measurement.muscle_mass_kg and measurement.muscle_mass_kg > 0:
                quality_score += 1
            
            # Tanita-specific features
            if measurement.visceral_fat_rating and measurement.visceral_fat_rating > 0:
                quality_score += 1
            if measurement.metabolic_age and measurement.metabolic_age > 0:
                quality_score += 1
            
            # Segmental data (Tanita strength)
            segmental_count = sum(1 for attr in [
                'right_leg_muscle_kg', 'left_leg_muscle_kg',
                'right_arm_muscle_kg', 'left_arm_muscle_kg', 'trunk_muscle_kg'
            ] if getattr(measurement, attr, 0) > 0)
            
            if segmental_count >= 4:
                quality_score += 2
            elif segmental_count >= 2:
                quality_score += 1
            
            # Impedance data
            if measurement.impedance_50khz and measurement.impedance_50khz > 0:
                quality_score += 1
            
            # Quality determination
            if quality_score >= 7:
                return "excellent"
            elif quality_score >= 5:
                return "good"
            elif quality_score >= 3:
                return "fair"
            else:
                return "poor"
                
        except Exception as e:
            logger.error(f"Error assessing Tanita quality: {e}")
            return "unknown"
    
    def _assess_inbody_quality(self, measurement: MeasurementData) -> str:
        """Assess measurement quality for InBody devices"""
        try:
            quality_score = 0
            
            # Basic measurements
            if measurement.weight_kg and measurement.weight_kg > 0:
                quality_score += 1
            if measurement.muscle_mass_kg and measurement.muscle_mass_kg > 0:
                quality_score += 1
            if measurement.total_body_water_kg and measurement.total_body_water_kg > 0:
                quality_score += 1
            
            # InBody-specific features
            if measurement.phase_angle and measurement.phase_angle > 0:
                quality_score += 2  # Phase angle is InBody's key feature
            
            # Segmental lean mass (InBody strength)
            segmental_count = sum(1 for attr in [
                'right_leg_muscle_kg', 'left_leg_muscle_kg',
                'right_arm_muscle_kg', 'left_arm_muscle_kg', 'trunk_muscle_kg'
            ] if getattr(measurement, attr, 0) > 0)
            
            if segmental_count >= 4:
                quality_score += 2
            elif segmental_count >= 2:
                quality_score += 1
            
            # Quality determination
            if quality_score >= 6:
                return "excellent"
            elif quality_score >= 4:
                return "good"
            elif quality_score >= 2:
                return "fair"
            else:
                return "poor"
                
        except Exception as e:
            logger.error(f"Error assessing InBody quality: {e}")
            return "unknown"
    
    def _assess_generic_quality(self, measurement: MeasurementData) -> str:
        """Assess measurement quality for generic devices"""
        try:
            quality_score = 0
            
            # Count available measurements
            if measurement.weight_kg and measurement.weight_kg > 0:
                quality_score += 1
            if measurement.body_fat_percent and measurement.body_fat_percent > 0:
                quality_score += 1
            if measurement.muscle_mass_kg and measurement.muscle_mass_kg > 0:
                quality_score += 1
            
            # Quality determination
            if quality_score >= 3:
                return "good"
            elif quality_score >= 2:
                return "fair"
            else:
                return "poor"
                
        except Exception as e:
            logger.error(f"Error assessing generic quality: {e}")
            return "unknown"
    
    def _analyze_tanita_segmental_balance(self, measurement: MeasurementData):
        """Analyze segmental balance for Tanita measurements"""
        try:
            notes = []
            
            # Leg balance analysis
            if measurement.right_leg_muscle_kg and measurement.left_leg_muscle_kg:
                leg_diff = abs(measurement.right_leg_muscle_kg - measurement.left_leg_muscle_kg)
                if leg_diff > 1.0:  # >1kg difference
                    notes.append(f"Leg muscle imbalance: {leg_diff:.1f}kg difference")
            
            # Arm balance analysis
            if measurement.right_arm_muscle_kg and measurement.left_arm_muscle_kg:
                arm_diff = abs(measurement.right_arm_muscle_kg - measurement.left_arm_muscle_kg)
                if arm_diff > 0.5:  # >0.5kg difference
                    notes.append(f"Arm muscle imbalance: {arm_diff:.1f}kg difference")
            
            if notes:
                if measurement.processing_notes:
                    measurement.processing_notes += f"; {'; '.join(notes)}"
                else:
                    measurement.processing_notes = '; '.join(notes)
                    
        except Exception as e:
            logger.error(f"Error analyzing Tanita segmental balance: {e}")
    
    def _analyze_inbody_lean_mass(self, measurement: MeasurementData):
        """Analyze lean mass distribution for InBody measurements"""
        try:
            notes = []
            
            # Calculate total segmental lean mass
            if all([measurement.right_leg_muscle_kg, measurement.left_leg_muscle_kg,
                   measurement.right_arm_muscle_kg, measurement.left_arm_muscle_kg,
                   measurement.trunk_muscle_kg]):
                
                total_segmental = (measurement.right_leg_muscle_kg + measurement.left_leg_muscle_kg +
                                 measurement.right_arm_muscle_kg + measurement.left_arm_muscle_kg +
                                 measurement.trunk_muscle_kg)
                
                if measurement.muscle_mass_kg:
                    segmental_ratio = total_segmental / measurement.muscle_mass_kg
                    if abs(segmental_ratio - 1.0) > 0.1:  # >10% difference
                        notes.append(f"Segmental-total muscle mass discrepancy: {segmental_ratio:.2f}")
            
            if notes:
                if measurement.processing_notes:
                    measurement.processing_notes += f"; {'; '.join(notes)}"
                else:
                    measurement.processing_notes = '; '.join(notes)
                    
        except Exception as e:
            logger.error(f"Error analyzing InBody lean mass: {e}")
    
    async def _save_measurement_to_database(self, measurement: MeasurementData, customer_info: Dict) -> Optional[int]:
        """Save measurement to database"""
        try:
            # Convert measurement to database format
            measurement_data = {
                'device_id': measurement.device_id,
                'device_type': measurement.device_type,
                'customer_id': customer_info.get('id'),
                'extracted_phone_number': measurement.customer_phone,
                'measurement_timestamp': measurement.measurement_timestamp,
                'measurement_uuid': measurement.measurement_uuid,
                
                # Personal info
                'gender': measurement.gender,
                'age': measurement.age,
                'height_cm': measurement.height_cm,
                
                # Basic measurements
                'weight_kg': measurement.weight_kg,
                'bmi': measurement.bmi,
                
                # Body composition
                'body_fat_percent': measurement.body_fat_percent,
                'muscle_mass_kg': measurement.muscle_mass_kg,
                'bone_mass_kg': measurement.bone_mass_kg,
                'total_body_water_kg': measurement.total_body_water_kg,
                'total_body_water_percent': measurement.total_body_water_percent,
                'visceral_fat_rating': measurement.visceral_fat_rating,
                'metabolic_age': measurement.metabolic_age,
                'bmr_kcal': measurement.bmr_kcal,
                
                # Segmental analysis
                'right_arm_muscle_kg': measurement.right_arm_muscle_kg,
                'left_arm_muscle_kg': measurement.left_arm_muscle_kg,
                'trunk_muscle_kg': measurement.trunk_muscle_kg,
                'right_leg_muscle_kg': measurement.right_leg_muscle_kg,
                'left_leg_muscle_kg': measurement.left_leg_muscle_kg,
                'right_arm_fat_percent': measurement.right_arm_fat_percent,
                'left_arm_fat_percent': measurement.left_arm_fat_percent,
                'trunk_fat_percent': measurement.trunk_fat_percent,
                'right_leg_fat_percent': measurement.right_leg_fat_percent,
                'left_leg_fat_percent': measurement.left_leg_fat_percent,
                
                # Technical data
                'impedance_50khz': measurement.impedance_50khz,
                'impedance_250khz': measurement.impedance_250khz,
                'phase_angle': measurement.phase_angle,
                
                # Quality and metadata
                'measurement_quality': measurement.measurement_quality,
                'data_completeness': measurement.data_completeness,
                'validation_errors': json.dumps(measurement.validation_errors) if measurement.validation_errors else None,
                'status': measurement.status.value if measurement.status else 'unknown',
                'raw_data': measurement.raw_data,
                'processing_notes': measurement.processing_notes,
                
                # Sync status
                'synced_to_actiwell': False,
                'sync_attempts': 0
            }
            
            measurement_id = await self.database_manager.save_measurement(measurement_data)
            
            if measurement_id:
                logger.info(f"Measurement saved to database: ID {measurement_id}")
                return measurement_id
            
            return None
            
        except Exception as e:
            logger.error(f"Error saving measurement to database: {e}")
            return None
    
    async def _post_process_measurement(self, measurement_id: int, measurement: MeasurementData, customer_info: Dict):
        """Post-processing tasks after measurement is saved"""
        try:
            # Generate measurement report
            await self._generate_measurement_report(measurement_id, measurement, customer_info)
            
            # Update measurement statistics
            await self._update_measurement_statistics(measurement_id, measurement)
            
        except Exception as e:
            logger.error(f"Error in post-processing: {e}")
    
    async def _generate_measurement_report(self, measurement_id: int, measurement: MeasurementData, customer_info: Dict):
        """Generate measurement report"""
        try:
            report = {
                'measurement_id': measurement_id,
                'customer_phone': measurement.customer_phone,
                'customer_name': customer_info.get('name', 'Unknown'),
                'device_type': measurement.device_type,
                'measurement_date': measurement.measurement_timestamp.isoformat(),
                'summary': {
                    'weight_kg': measurement.weight_kg,
                    'bmi': measurement.bmi,
                    'body_fat_percent': measurement.body_fat_percent,
                    'muscle_mass_kg': measurement.muscle_mass_kg,
                    'metabolic_age': measurement.metabolic_age,
                    'bmr_kcal': measurement.bmr_kcal
                },
                'quality': {
                    'measurement_quality': measurement.measurement_quality,
                    'data_completeness': measurement.data_completeness,
                    'validation_errors': measurement.validation_errors
                }
            }
            
            await self.database_manager.save_measurement_report(measurement_id, report)
            logger.debug(f"Generated report for measurement {measurement_id}")
            
        except Exception as e:
            logger.error(f"Error generating measurement report: {e}")
    
    async def _update_measurement_statistics(self, measurement_id: int, measurement: MeasurementData):
        """Update measurement statistics"""
        try:
            stats = {
                'measurement_id': measurement_id,
                'device_type': measurement.device_type,
                'processing_date': datetime.now(),
                'data_points_count': sum(1 for attr, value in measurement.__dict__.items() 
                                       if value and value != 0 and not attr.startswith('_')),
                'has_segmental_data': any([
                    measurement.right_leg_muscle_kg, measurement.left_leg_muscle_kg,
                    measurement.right_arm_muscle_kg, measurement.left_arm_muscle_kg,
                    measurement.trunk_muscle_kg
                ]),
                'has_impedance_data': bool(measurement.impedance_50khz or measurement.impedance_250khz),
                'has_phase_angle': bool(measurement.phase_angle)
            }
            
            await self.database_manager.save_measurement_statistics(stats)
            logger.debug(f"Updated statistics for measurement {measurement_id}")
            
        except Exception as e:
            logger.error(f"Error updating measurement statistics: {e}")
    
    async def _update_customer_analytics(self, customer_id: int, measurement: MeasurementData):
        """Update customer analytics and trends"""
        try:
            analytics_data = {
                'customer_id': customer_id,
                'analysis_date': measurement.measurement_timestamp.date(),
                'measurement_count': 1,
                'avg_weight_kg': measurement.weight_kg,
                'avg_body_fat_percent': measurement.body_fat_percent,
                'avg_muscle_mass_kg': measurement.muscle_mass_kg,
                'avg_visceral_fat_rating': measurement.visceral_fat_rating,
                'avg_metabolic_age': measurement.metabolic_age
            }
            
            await self.database_manager.update_customer_analytics(analytics_data)
            logger.debug(f"Updated analytics for customer {customer_id}")
            
        except Exception as e:
            logger.error(f"Error updating customer analytics: {e}")
    
    async def _check_health_alerts(self, measurement: MeasurementData, customer_info: Dict):
        """Check for health alerts based on measurement values"""
        try:
            alerts = []
            
            # BMI alerts
            if measurement.bmi:
                if measurement.bmi < 18.5:
                    alerts.append("BMI below normal range (underweight)")
                elif measurement.bmi > 30:
                    alerts.append("BMI above normal range (obese)")
                elif measurement.bmi > 25:
                    alerts.append("BMI above normal range (overweight)")
            
            # Body fat alerts (gender-specific)
            if measurement.body_fat_percent and measurement.gender:
                if measurement.gender == 'M' and measurement.body_fat_percent > 25:
                    alerts.append("Body fat percentage high for males")
                elif measurement.gender == 'F' and measurement.body_fat_percent > 32:
                    alerts.append("Body fat percentage high for females")
            
            # Visceral fat alerts
            if measurement.visceral_fat_rating and measurement.visceral_fat_rating > 12:
                alerts.append("Visceral fat rating elevated - health risk")
            
            # Muscle mass alerts
            if measurement.muscle_mass_kg and measurement.weight_kg:
                muscle_ratio = measurement.muscle_mass_kg / measurement.weight_kg
                if muscle_ratio < 0.3:
                    alerts.append("Low muscle mass ratio - sarcopenia risk")
            
            # Phase angle alerts (if available)
            if measurement.phase_angle:
                if measurement.phase_angle < 4.0:
                    alerts.append("Low phase angle - cellular health concern")
            
            # Save alerts if any
            if alerts:
                logger.info(f"Health alerts for {measurement.customer_phone}: {', '.join(alerts)}")
                await self.database_manager.save_health_alerts(
                    customer_info.get('id'),
                    alerts,
                    measurement.measurement_timestamp
                )
            
        except Exception as e:
            logger.error(f"Error checking health alerts: {e}")
    
    async def get_customer_measurements(self, phone_number: str, days: int = 30, device_type: str = None) -> List[Dict]:
        """Get customer measurements with optional device filtering"""
        try:
            measurements = await self.database_manager.get_customer_measurements(
                phone_number, 
                days, 
                device_type=device_type
            )
            
            return measurements
            
        except Exception as e:
            logger.error(f"Error getting customer measurements: {e}")
            return []
    
    async def get_measurement_trends(self, phone_number: str, days: int = 90) -> Dict:
        """Get measurement trends for a customer"""
        try:
            measurements = await self.get_customer_measurements(phone_number, days)
            
            if len(measurements) < 2:
                return {'message': 'Insufficient data for trend analysis'}
            
            # Sort by date
            sorted_measurements = sorted(measurements, key=lambda x: x['measurement_timestamp'])
            
            trends = {}
            
            # Calculate trends for key metrics
            for metric in ['weight_kg', 'body_fat_percent', 'muscle_mass_kg', 'visceral_fat_rating']:
                values = [m.get(metric) for m in sorted_measurements if m.get(metric)]
                if len(values) >= 2:
                    trends[metric] = self._calculate_metric_trend(values)
            
            return {
                'phone_number': phone_number,
                'analysis_period_days': days,
                'measurement_count': len(measurements),
                'trends': trends,
                'latest_measurement': sorted_measurements[-1],
                'analysis_date': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating measurement trends: {e}")
            return {'error': str(e)}
    
    def _calculate_metric_trend(self, values: List[float]) -> Dict:
        """Calculate trend for a specific metric"""
        try:
            if len(values) < 2:
                return {'trend': 'insufficient_data'}
            
            # Simple linear trend calculation
            first_value = values[0]
            last_value = values[-1]
            change = last_value - first_value
            change_percent = (change / first_value) * 100 if first_value != 0 else 0
            
            # Determine trend direction
            if abs(change_percent) < 2:  # Less than 2% change
                trend_direction = 'stable'
            elif change_percent > 0:
                trend_direction = 'increasing'
            else:
                trend_direction = 'decreasing'
            
            return {
                'trend': trend_direction,
                'change_absolute': round(change, 2),
                'change_percent': round(change_percent, 1),
                'first_value': first_value,
                'last_value': last_value,
                'data_points': len(values)
            }
            
        except Exception as e:
            logger.error(f"Error calculating metric trend: {e}")
            return {'trend': 'error', 'error': str(e)}
    
    async def get_service_statistics(self) -> Dict:
        """Get measurement service statistics"""
        try:
            stats = await self.database_manager.get_measurement_service_statistics()
            
            return {
                'total_measurements': stats.get('total_measurements', 0),
                'measurements_by_device': stats.get('measurements_by_device', {}),
                'quality_distribution': stats.get('quality_distribution', {}),
                'processing_statistics': {
                    'auto_customer_creation_enabled': self.auto_customer_creation,
                    'validation_enabled': self.measurement_validation_enabled,
                    'health_alerts_enabled': self.health_alerts_enabled,
                    'analytics_enabled': self.analytics_update_enabled
                },
                'supported_devices': list(self.device_processors.keys()),
                'service_uptime': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting service statistics: {e}")
            return {'error': str(e)}