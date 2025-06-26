#!/usr/bin/env python3
"""
InBody Integration Service
Business logic layer for InBody 370s measurements processing
"""

import logging
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import asdict

from ..devices.inbody_370s_handler import InBodyMeasurement, InBody370sHandler
from ..core.database_manager import DatabaseManager
from ..core.actiwell_api import ActiwellAPI
from .measurement_service import MeasurementService
from .sync_service import SyncService
from config import ACTIWELL_CONFIG, INBODY_CONFIG

logger = logging.getLogger(__name__)


class InBodyService:
    """Main service class for InBody 370s integration"""
    
    def __init__(self, database_manager: DatabaseManager, actiwell_api: ActiwellAPI):
        self.database_manager = database_manager
        self.actiwell_api = actiwell_api
        self.measurement_service = MeasurementService(database_manager)
        self.sync_service = SyncService(database_manager, actiwell_api)
        
        # Initialize InBody handler
        self.inbody_handler = InBody370sHandler(
            config=INBODY_CONFIG,
            database_manager=database_manager
        )
        
        # Register measurement callback
        self.inbody_handler.add_message_callback(self.process_measurement)
        
        # Processing queue
        self.processing_queue = asyncio.Queue()
        self.is_processing = False
        
        logger.info("InBody Service initialized")
    
    async def start(self) -> bool:
        """Start InBody integration service"""
        try:
            # Start InBody handler
            if not self.inbody_handler.start():
                logger.error("Failed to start InBody handler")
                return False
            
            # Start processing worker
            self.is_processing = True
            asyncio.create_task(self._processing_worker())
            
            logger.info("InBody Service started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start InBody Service: {e}")
            return False
    
    async def stop(self):
        """Stop InBody integration service"""
        self.is_processing = False
        self.inbody_handler.stop()
        logger.info("InBody Service stopped")
    
    def process_measurement(self, measurement: InBodyMeasurement):
        """Process incoming measurement from InBody device"""
        try:
            logger.info(f"Processing measurement for customer: {measurement.phone_number}")
            
            # Add to processing queue
            asyncio.create_task(self._queue_measurement(measurement))
            
        except Exception as e:
            logger.error(f"Error processing measurement: {e}")
    
    async def _queue_measurement(self, measurement: InBodyMeasurement):
        """Add measurement to processing queue"""
        await self.processing_queue.put(measurement)
        logger.debug("Measurement added to processing queue")
    
    async def _processing_worker(self):
        """Background worker for processing measurements"""
        logger.info("InBody processing worker started")
        
        while self.is_processing:
            try:
                # Get measurement from queue (with timeout)
                measurement = await asyncio.wait_for(
                    self.processing_queue.get(), 
                    timeout=1.0
                )
                
                # Process measurement
                await self._process_measurement_async(measurement)
                
            except asyncio.TimeoutError:
                # No measurement in queue, continue
                continue
            except Exception as e:
                logger.error(f"Processing worker error: {e}")
                await asyncio.sleep(1)
        
        logger.info("InBody processing worker stopped")
    
    async def _process_measurement_async(self, measurement: InBodyMeasurement):
        """Asynchronously process a single measurement"""
        try:
            logger.info(f"Processing measurement: {measurement.measurement_id}")
            
            # Step 1: Validate measurement
            if not self._validate_measurement(measurement):
                logger.warning("Measurement validation failed")
                return
            
            # Step 2: Customer lookup
            customer_info = await self._lookup_customer(measurement.phone_number)
            
            if not customer_info:
                logger.warning(f"Customer not found for phone: {measurement.phone_number}")
                # Create pending customer entry
                customer_info = await self._create_pending_customer(measurement)
            
            # Step 3: Save measurement to database
            measurement_id = await self._save_measurement_to_db(measurement, customer_info)
            
            if not measurement_id:
                logger.error("Failed to save measurement to database")
                return
            
            # Step 4: Sync to Actiwell (if configured)
            if ACTIWELL_CONFIG.get('send_to_actiwell', True):
                await self._sync_to_actiwell(measurement_id, measurement, customer_info)
            
            # Step 5: Generate reports and notifications
            await self._post_processing(measurement_id, measurement, customer_info)
            
            logger.info(f"Successfully processed measurement {measurement_id}")
            
        except Exception as e:
            logger.error(f"Error in async measurement processing: {e}")
    
    def _validate_measurement(self, measurement: InBodyMeasurement) -> bool:
        """Validate measurement data"""
        # Check required fields
        if not measurement.phone_number:
            logger.error("Missing phone number")
            return False
        
        if not measurement.weight_kg or measurement.weight_kg <= 0:
            logger.error("Invalid weight value")
            return False
        
        # Phone number format validation
        import re
        phone_pattern = r'^0[2-9][0-9]{8}$'
        if not re.match(phone_pattern, measurement.phone_number):
            logger.error(f"Invalid phone format: {measurement.phone_number}")
            return False
        
        # Reasonable value ranges
        if measurement.weight_kg and (measurement.weight_kg < 20 or measurement.weight_kg > 300):
            logger.warning(f"Weight outside normal range: {measurement.weight_kg}kg")
        
        if measurement.height_cm and (measurement.height_cm < 100 or measurement.height_cm > 250):
            logger.warning(f"Height outside normal range: {measurement.height_cm}cm")
        
        return True
    
    async def _lookup_customer(self, phone_number: str) -> Optional[Dict]:
        """Lookup customer in Actiwell system"""
        try:
            # First check local database
            local_customer = await self.database_manager.get_customer_by_phone(phone_number)
            
            if local_customer and local_customer.get('actiwell_customer_id'):
                logger.debug(f"Found customer in local database: {phone_number}")
                return local_customer
            
            # Query Actiwell API
            actiwell_customer = await self.actiwell_api.search_customer_by_phone(
                phone_number,
                location_id=ACTIWELL_CONFIG.get('location_id', 1),
                operator_id=ACTIWELL_CONFIG.get('operator_id', 1)
            )
            
            if actiwell_customer:
                logger.info(f"Found customer in Actiwell: {phone_number}")
                
                # Update local database
                await self.database_manager.update_customer(phone_number, actiwell_customer)
                
                return actiwell_customer
            
            logger.info(f"Customer not found: {phone_number}")
            return None
            
        except Exception as e:
            logger.error(f"Error looking up customer {phone_number}: {e}")
            return None
    
    async def _create_pending_customer(self, measurement: InBodyMeasurement) -> Dict:
        """Create pending customer entry for unknown phone numbers"""
        try:
            customer_data = {
                'phone': measurement.phone_number,
                'name': measurement.patient_name or 'Unknown Customer',
                'gender': measurement.gender,
                'age': measurement.age,
                'status': 'pending_verification',
                'created_from': 'inbody_measurement',
                'first_measurement_date': measurement.measurement_timestamp
            }
            
            customer_id = await self.database_manager.create_customer(customer_data)
            
            if customer_id:
                logger.info(f"Created pending customer: {measurement.phone_number}")
                customer_data['id'] = customer_id
                return customer_data
            
            return {}
            
        except Exception as e:
            logger.error(f"Error creating pending customer: {e}")
            return {}
    
    async def _save_measurement_to_db(self, measurement: InBodyMeasurement, customer_info: Dict) -> Optional[int]:
        """Save measurement to local database"""
        try:
            # Convert measurement to database format
            measurement_data = {
                'device_id': measurement.device_id,
                'customer_id': customer_info.get('id'),
                'extracted_phone_number': measurement.phone_number,
                'patient_id': measurement.patient_id,
                'measurement_timestamp': measurement.measurement_timestamp,
                
                # Basic measurements
                'height_cm': measurement.height_cm,
                'weight_kg': measurement.weight_kg,
                'bmi': measurement.bmi,
                
                # Body composition
                'body_fat_percent': measurement.body_fat_percent,
                'body_fat_mass_kg': measurement.body_fat_mass_kg,
                'skeletal_muscle_mass_kg': measurement.skeletal_muscle_mass_kg,
                'fat_free_mass_kg': measurement.fat_free_mass_kg,
                'total_body_water_kg': measurement.total_body_water_kg,
                'total_body_water_percent': measurement.total_body_water_percent,
                'protein_mass_kg': measurement.protein_mass_kg,
                'mineral_mass_kg': measurement.mineral_mass_kg,
                
                # Advanced metrics
                'visceral_fat_area_cm2': measurement.visceral_fat_area_cm2,
                'visceral_fat_level': measurement.visceral_fat_level,
                'basal_metabolic_rate_kcal': measurement.basal_metabolic_rate_kcal,
                
                # Segmental analysis
                'right_leg_lean_mass_kg': measurement.right_leg_lean_mass_kg,
                'left_leg_lean_mass_kg': measurement.left_leg_lean_mass_kg,
                'right_arm_lean_mass_kg': measurement.right_arm_lean_mass_kg,
                'left_arm_lean_mass_kg': measurement.left_arm_lean_mass_kg,
                'trunk_lean_mass_kg': measurement.trunk_lean_mass_kg,
                
                # Bioelectrical impedance
                'impedance_50khz_whole_body': measurement.impedance_50khz,
                'impedance_250khz_whole_body': measurement.impedance_250khz,
                'impedance_500khz_whole_body': measurement.impedance_500khz,
                'impedance_1000khz_whole_body': measurement.impedance_1000khz,
                
                # Phase angle
                'phase_angle_whole_body': measurement.phase_angle_whole_body,
                
                # Quality and metadata
                'measurement_quality': measurement.measurement_quality,
                'contact_quality': json.dumps(measurement.contact_quality),
                'hl7_message_type': measurement.hl7_message_type,
                'raw_hl7_message': measurement.raw_hl7_message,
                
                # Processing status
                'synced_to_actiwell': False,
                'sync_attempts': 0
            }
            
            measurement_id = await self.database_manager.save_inbody_measurement(measurement_data)
            
            if measurement_id:
                logger.info(f"Saved measurement to database: ID {measurement_id}")
                return measurement_id
            
            return None
            
        except Exception as e:
            logger.error(f"Error saving measurement to database: {e}")
            return None
    
    async def _sync_to_actiwell(self, measurement_id: int, measurement: InBodyMeasurement, customer_info: Dict):
        """Sync measurement to Actiwell platform"""
        try:
            if not customer_info.get('actiwell_customer_id'):
                logger.warning(f"No Actiwell customer ID for {measurement.phone_number}")
                return
            
            # Prepare data for Actiwell API
            actiwell_data = {
                'customer_id': customer_info['actiwell_customer_id'],
                'activity_type': 5,  # Body composition measurement
                'location_id': ACTIWELL_CONFIG.get('location_id', 1),
                'operator_id': ACTIWELL_CONFIG.get('operator_id', 1),
                'measurement_timestamp': measurement.measurement_timestamp.isoformat(),
                'device_type': 'inbody_370s',
                'data': {
                    'basic_measurements': {
                        'weight_kg': measurement.weight_kg,
                        'height_cm': measurement.height_cm,
                        'bmi': measurement.bmi
                    },
                    'body_composition': {
                        'body_fat_percent': measurement.body_fat_percent,
                        'skeletal_muscle_mass_kg': measurement.skeletal_muscle_mass_kg,
                        'visceral_fat_area_cm2': measurement.visceral_fat_area_cm2,
                        'basal_metabolic_rate_kcal': measurement.basal_metabolic_rate_kcal
                    },
                    'segmental_analysis': {
                        'right_leg_lean_mass_kg': measurement.right_leg_lean_mass_kg,
                        'left_leg_lean_mass_kg': measurement.left_leg_lean_mass_kg,
                        'right_arm_lean_mass_kg': measurement.right_arm_lean_mass_kg,
                        'left_arm_lean_mass_kg': measurement.left_arm_lean_mass_kg,
                        'trunk_lean_mass_kg': measurement.trunk_lean_mass_kg
                    },
                    'bioelectrical_impedance': {
                        'impedance_50khz': measurement.impedance_50khz,
                        'phase_angle_whole_body': measurement.phase_angle_whole_body
                    }
                },
                'raw_data': measurement.raw_hl7_message
            }
            
            # Send to Actiwell
            result = await self.actiwell_api.save_body_composition(actiwell_data)
            
            if result and result.get('success'):
                # Update sync status
                await self.database_manager.update_measurement_sync_status(
                    measurement_id,
                    actiwell_measurement_id=result.get('measurement_id'),
                    success=True
                )
                logger.info(f"Successfully synced measurement {measurement_id} to Actiwell")
            else:
                # Mark sync failed
                await self.database_manager.update_measurement_sync_status(
                    measurement_id,
                    success=False,
                    error_message=result.get('error', 'Unknown sync error')
                )
                logger.error(f"Failed to sync measurement {measurement_id} to Actiwell")
                
        except Exception as e:
            logger.error(f"Error syncing to Actiwell: {e}")
            # Mark sync failed
            await self.database_manager.update_measurement_sync_status(
                measurement_id,
                success=False,
                error_message=str(e)
            )
    
    async def _post_processing(self, measurement_id: int, measurement: InBodyMeasurement, customer_info: Dict):
        """Post-processing tasks after measurement is saved"""
        try:
            # Generate measurement report
            await self._generate_measurement_report(measurement_id, measurement, customer_info)
            
            # Update customer analytics
            await self._update_customer_analytics(customer_info.get('id'), measurement)
            
            # Check for health alerts
            await self._check_health_alerts(measurement, customer_info)
            
        except Exception as e:
            logger.error(f"Error in post-processing: {e}")
    
    async def _generate_measurement_report(self, measurement_id: int, measurement: InBodyMeasurement, customer_info: Dict):
        """Generate measurement report"""
        try:
            # Create summary report
            report = {
                'measurement_id': measurement_id,
                'customer_phone': measurement.phone_number,
                'customer_name': customer_info.get('name', 'Unknown'),
                'measurement_date': measurement.measurement_timestamp.isoformat(),
                'summary': {
                    'weight_kg': measurement.weight_kg,
                    'bmi': measurement.bmi,
                    'body_fat_percent': measurement.body_fat_percent,
                    'muscle_mass_kg': measurement.skeletal_muscle_mass_kg,
                    'metabolic_rate_kcal': measurement.basal_metabolic_rate_kcal
                },
                'device_info': {
                    'model': measurement.device_model,
                    'measurement_quality': measurement.measurement_quality
                }
            }
            
            # Save report
            await self.database_manager.save_measurement_report(measurement_id, report)
            
            logger.debug(f"Generated report for measurement {measurement_id}")
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
    
    async def _update_customer_analytics(self, customer_id: Optional[int], measurement: InBodyMeasurement):
        """Update customer analytics and trends"""
        if not customer_id:
            return
        
        try:
            # Calculate trends and analytics
            analytics_data = {
                'customer_id': customer_id,
                'analysis_date': measurement.measurement_timestamp.date(),
                'measurement_count': 1,
                'avg_weight_kg': measurement.weight_kg,
                'avg_body_fat_percent': measurement.body_fat_percent,
                'avg_muscle_mass_kg': measurement.skeletal_muscle_mass_kg,
                'avg_metabolic_rate_kcal': measurement.basal_metabolic_rate_kcal
            }
            
            await self.database_manager.update_customer_analytics(analytics_data)
            
            logger.debug(f"Updated analytics for customer {customer_id}")
            
        except Exception as e:
            logger.error(f"Error updating customer analytics: {e}")
    
    async def _check_health_alerts(self, measurement: InBodyMeasurement, customer_info: Dict):
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
            
            # Body fat alerts
            if measurement.body_fat_percent:
                gender = customer_info.get('gender', 'M')
                if gender == 'M' and measurement.body_fat_percent > 25:
                    alerts.append("Body fat percentage high for males")
                elif gender == 'F' and measurement.body_fat_percent > 32:
                    alerts.append("Body fat percentage high for females")
            
            # Visceral fat alerts
            if measurement.visceral_fat_area_cm2 and measurement.visceral_fat_area_cm2 > 100:
                alerts.append("Visceral fat area elevated - health risk")
            
            # Log alerts
            if alerts:
                logger.info(f"Health alerts for {measurement.phone_number}: {', '.join(alerts)}")
                
                # Save alerts to database
                await self.database_manager.save_health_alerts(
                    customer_info.get('id'),
                    alerts,
                    measurement.measurement_timestamp
                )
            
        except Exception as e:
            logger.error(f"Error checking health alerts: {e}")
    
    async def get_measurement_stats(self, phone_number: str, days: int = 30) -> Dict:
        """Get measurement statistics for a customer"""
        try:
            measurements = await self.database_manager.get_customer_measurements(phone_number, days)
            
            if not measurements:
                return {'error': 'No measurements found'}
            
            # Calculate statistics
            stats = {
                'total_measurements': len(measurements),
                'date_range': {
                    'start': min(m['measurement_timestamp'] for m in measurements).isoformat(),
                    'end': max(m['measurement_timestamp'] for m in measurements).isoformat()
                },
                'averages': {
                    'weight_kg': sum(m['weight_kg'] for m in measurements if m['weight_kg']) / len(measurements),
                    'body_fat_percent': sum(m['body_fat_percent'] for m in measurements if m['body_fat_percent']) / len(measurements),
                    'muscle_mass_kg': sum(m['skeletal_muscle_mass_kg'] for m in measurements if m['skeletal_muscle_mass_kg']) / len(measurements)
                },
                'trends': self._calculate_trends(measurements)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting measurement stats: {e}")
            return {'error': str(e)}
    
    def _calculate_trends(self, measurements: List[Dict]) -> Dict:
        """Calculate measurement trends"""
        if len(measurements) < 2:
            return {'message': 'Insufficient data for trend analysis'}
        
        # Sort by date
        sorted_measurements = sorted(measurements, key=lambda x: x['measurement_timestamp'])
        first = sorted_measurements[0]
        last = sorted_measurements[-1]
        
        trends = {}
        
        # Weight trend
        if first.get('weight_kg') and last.get('weight_kg'):
            weight_change = last['weight_kg'] - first['weight_kg']
            trends['weight_change_kg'] = round(weight_change, 1)
            trends['weight_trend'] = 'increasing' if weight_change > 0.5 else 'decreasing' if weight_change < -0.5 else 'stable'
        
        # Body fat trend
        if first.get('body_fat_percent') and last.get('body_fat_percent'):
            fat_change = last['body_fat_percent'] - first['body_fat_percent']
            trends['body_fat_change_percent'] = round(fat_change, 1)
            trends['body_fat_trend'] = 'increasing' if fat_change > 1 else 'decreasing' if fat_change < -1 else 'stable'
        
        return trends
    
    def get_device_status(self) -> Dict:
        """Get InBody device status"""
        device_status = self.inbody_handler.get_status()
        return {
            'device_id': device_status.device_id,
            'device_type': device_status.device_type,
            'status': device_status.status,
            'connection_type': device_status.connection_type,
            'last_heartbeat': device_status.last_heartbeat.isoformat() if device_status.last_heartbeat else None,
            'data_port': self.inbody_handler.data_port,
            'listening_port': self.inbody_handler.listening_port,
            'device_ip': self.inbody_handler.device_ip
        }