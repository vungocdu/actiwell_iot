#!/usr/bin/env python3
"""
Sync Service - Common synchronization logic for all body composition devices
Handles syncing to Actiwell platform and other external systems
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from enum import Enum

from ..devices.base_protocol import MeasurementData, MeasurementStatus
from ..core.database_manager import DatabaseManager
from ..core.actiwell_api import ActiwellAPI

logger = logging.getLogger(__name__)

class SyncStatus(Enum):
    """Sync status enumeration"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    RETRYING = "retrying"

class SyncPriority(Enum):
    """Sync priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

class SyncService:
    """
    Common synchronization service for all body composition devices
    Handles syncing measurements to Actiwell and other external systems
    """
    
    def __init__(self, database_manager: DatabaseManager, actiwell_api: ActiwellAPI = None, config: Dict = None):
        """
        Initialize sync service
        
        Args:
            database_manager: Database manager for tracking sync status
            actiwell_api: Actiwell API for syncing measurements
            config: Sync service configuration
        """
        self.database_manager = database_manager
        self.actiwell_api = actiwell_api
        self.config = config or {}
        
        # Sync configuration
        self.auto_sync_enabled = self.config.get('auto_sync_enabled', True)
        self.batch_sync_enabled = self.config.get('batch_sync_enabled', True)
        self.retry_enabled = self.config.get('retry_enabled', True)
        self.max_retry_attempts = self.config.get('max_retry_attempts', 3)
        self.retry_delay_seconds = self.config.get('retry_delay_seconds', 300)  # 5 minutes
        
        # Device-specific sync handlers
        self.device_sync_handlers = {
            'tanita_mc780ma': self._sync_tanita_measurement,
            'tanita': self._sync_tanita_measurement,
            'inbody_270': self._sync_inbody_measurement,
            'inbody': self._sync_inbody_measurement,
        }
        
        # Sync queue and processing
        self.sync_queue = asyncio.Queue()
        self.is_processing = False
        self.sync_workers = []
        self.worker_count = self.config.get('sync_workers', 2)
        
        # Statistics
        self.sync_stats = {
            'total_syncs': 0,
            'successful_syncs': 0,
            'failed_syncs': 0,
            'retry_syncs': 0,
            'start_time': datetime.now()
        }
        
        logger.info("Sync Service initialized")
    
    async def start(self) -> bool:
        """Start sync service with background workers"""
        try:
            if not self.actiwell_api:
                logger.warning("No Actiwell API configured - sync service will only log operations")
            
            # Start sync workers
            self.is_processing = True
            for i in range(self.worker_count):
                worker = asyncio.create_task(self._sync_worker(f"worker-{i}"))
                self.sync_workers.append(worker)
            
            # Start retry worker if enabled
            if self.retry_enabled:
                retry_worker = asyncio.create_task(self._retry_worker())
                self.sync_workers.append(retry_worker)
            
            logger.info(f"Sync Service started with {self.worker_count} workers")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Sync Service: {e}")
            return False
    
    async def stop(self):
        """Stop sync service and workers"""
        try:
            self.is_processing = False
            
            # Cancel all workers
            for worker in self.sync_workers:
                worker.cancel()
            
            # Wait for workers to finish
            await asyncio.gather(*self.sync_workers, return_exceptions=True)
            
            logger.info("Sync Service stopped")
            
        except Exception as e:
            logger.error(f"Error stopping Sync Service: {e}")
    
    async def sync_measurement_async(self, measurement: MeasurementData, device_type: str = None, 
                                   priority: SyncPriority = SyncPriority.NORMAL) -> bool:
        """
        Asynchronously sync a measurement to external systems
        
        Args:
            measurement: Measurement data to sync
            device_type: Type of device (for device-specific processing)
            priority: Sync priority level
            
        Returns:
            bool: True if sync was queued successfully
        """
        try:
            if not self.auto_sync_enabled:
                logger.debug("Auto-sync disabled, skipping sync")
                return True
            
            device_type = device_type or measurement.device_type
            
            sync_request = {
                'measurement': measurement,
                'device_type': device_type,
                'priority': priority,
                'created_at': datetime.now(),
                'attempts': 0
            }
            
            # Add to sync queue
            await self.sync_queue.put(sync_request)
            logger.debug(f"Measurement queued for sync: {measurement.customer_phone}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error queuing measurement for sync: {e}")
            return False
    
    def sync_measurement(self, measurement: MeasurementData, device_type: str = None) -> bool:
        """
        Synchronous wrapper for measurement sync
        
        Args:
            measurement: Measurement data to sync
            device_type: Type of device
            
        Returns:
            bool: True if sync successful
        """
        try:
            # Run async sync in sync context
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                self.sync_measurement_async(measurement, device_type)
            )
        except Exception as e:
            logger.error(f"Error in synchronous measurement sync: {e}")
            return False
    
    async def _sync_worker(self, worker_name: str):
        """Background worker for processing sync requests"""
        logger.info(f"Sync worker {worker_name} started")
        
        while self.is_processing:
            try:
                # Get sync request from queue (with timeout)
                sync_request = await asyncio.wait_for(
                    self.sync_queue.get(),
                    timeout=1.0
                )
                
                # Process sync request
                await self._process_sync_request(sync_request, worker_name)
                
            except asyncio.TimeoutError:
                # No sync request in queue, continue
                continue
            except Exception as e:
                logger.error(f"Sync worker {worker_name} error: {e}")
                await asyncio.sleep(1)
        
        logger.info(f"Sync worker {worker_name} stopped")
    
    async def _retry_worker(self):
        """Background worker for retrying failed syncs"""
        logger.info("Sync retry worker started")
        
        while self.is_processing:
            try:
                # Check for failed syncs to retry
                await self._retry_failed_syncs()
                
                # Wait before next retry check
                await asyncio.sleep(self.retry_delay_seconds)
                
            except Exception as e:
                logger.error(f"Retry worker error: {e}")
                await asyncio.sleep(60)  # Wait longer on error
        
        logger.info("Sync retry worker stopped")
    
    async def _process_sync_request(self, sync_request: Dict, worker_name: str):
        """Process a single sync request"""
        try:
            measurement = sync_request['measurement']
            device_type = sync_request['device_type']
            priority = sync_request['priority']
            
            logger.info(f"[{worker_name}] Processing sync for {measurement.customer_phone} ({device_type})")
            
            # Update attempts
            sync_request['attempts'] += 1
            self.sync_stats['total_syncs'] += 1
            
            # Choose sync handler based on device type
            if device_type in self.device_sync_handlers:
                sync_handler = self.device_sync_handlers[device_type]
            else:
                sync_handler = self._sync_generic_measurement
            
            # Perform sync
            sync_result = await sync_handler(measurement, sync_request)
            
            if sync_result['success']:
                self.sync_stats['successful_syncs'] += 1
                logger.info(f"[{worker_name}] Successfully synced measurement for {measurement.customer_phone}")
            else:
                self.sync_stats['failed_syncs'] += 1
                logger.error(f"[{worker_name}] Failed to sync measurement: {sync_result.get('error', 'Unknown error')}")
                
                # Queue for retry if enabled and not exceeded max attempts
                if (self.retry_enabled and 
                    sync_request['attempts'] < self.max_retry_attempts):
                    await self._queue_for_retry(sync_request, sync_result)
            
        except Exception as e:
            logger.error(f"Error processing sync request: {e}")
            self.sync_stats['failed_syncs'] += 1
    
    async def _sync_tanita_measurement(self, measurement: MeasurementData, sync_request: Dict) -> Dict:
        """Sync Tanita measurement to Actiwell"""
        try:
            if not self.actiwell_api:
                return {'success': False, 'error': 'No Actiwell API configured'}
            
            # Get customer information
            customer_info = await self._get_customer_info(measurement.customer_phone)
            
            if not customer_info or not customer_info.get('actiwell_customer_id'):
                return {'success': False, 'error': 'Customer not found in Actiwell'}
            
            # Prepare Tanita-specific data for Actiwell
            actiwell_data = {
                'customer_id': customer_info['actiwell_customer_id'],
                'activity_type': 5,  # Body composition measurement
                'location_id': self.config.get('actiwell_location_id', 1),
                'operator_id': self.config.get('actiwell_operator_id', 1),
                'measurement_timestamp': measurement.measurement_timestamp.isoformat(),
                'device_type': 'tanita_mc780ma',
                'data': {
                    'basic_measurements': {
                        'weight_kg': measurement.weight_kg,
                        'height_cm': measurement.height_cm,
                        'bmi': measurement.bmi,
                        'age': measurement.age,
                        'gender': measurement.gender
                    },
                    'body_composition': {
                        'body_fat_percent': measurement.body_fat_percent,
                        'muscle_mass_kg': measurement.muscle_mass_kg,
                        'bone_mass_kg': measurement.bone_mass_kg,
                        'total_body_water_kg': measurement.total_body_water_kg,
                        'total_body_water_percent': measurement.total_body_water_percent,
                        'visceral_fat_rating': measurement.visceral_fat_rating
                    },
                    'metabolic_data': {
                        'metabolic_age': measurement.metabolic_age,
                        'bmr_kcal': measurement.bmr_kcal
                    },
                    'segmental_analysis': {
                        'right_leg_muscle_kg': measurement.right_leg_muscle_kg,
                        'left_leg_muscle_kg': measurement.left_leg_muscle_kg,
                        'right_arm_muscle_kg': measurement.right_arm_muscle_kg,
                        'left_arm_muscle_kg': measurement.left_arm_muscle_kg,
                        'trunk_muscle_kg': measurement.trunk_muscle_kg,
                        'right_leg_fat_percent': measurement.right_leg_fat_percent,
                        'left_leg_fat_percent': measurement.left_leg_fat_percent,
                        'right_arm_fat_percent': measurement.right_arm_fat_percent,
                        'left_arm_fat_percent': measurement.left_arm_fat_percent,
                        'trunk_fat_percent': measurement.trunk_fat_percent
                    },
                    'bioelectrical_impedance': {
                        'impedance_50khz': measurement.impedance_50khz,
                        'impedance_250khz': measurement.impedance_250khz,
                        'phase_angle': measurement.phase_angle
                    },
                    'quality_metrics': {
                        'measurement_quality': measurement.measurement_quality,
                        'data_completeness': measurement.data_completeness
                    }
                },
                'raw_data': measurement.raw_data,
                'processing_notes': measurement.processing_notes
            }
            
            # Send to Actiwell
            result = await self.actiwell_api.save_body_composition(actiwell_data)
            
            if result and result.get('success'):
                # Update sync status in database
                await self._update_sync_status(
                    measurement,
                    SyncStatus.SUCCESS,
                    actiwell_measurement_id=result.get('measurement_id'),
                    sync_attempts=sync_request['attempts']
                )
                
                return {'success': True, 'actiwell_id': result.get('measurement_id')}
            else:
                error_msg = result.get('error', 'Unknown Actiwell API error') if result else 'No response from Actiwell API'
                
                await self._update_sync_status(
                    measurement,
                    SyncStatus.FAILED,
                    error_message=error_msg,
                    sync_attempts=sync_request['attempts']
                )
                
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            logger.error(f"Error syncing Tanita measurement: {e}")
            
            await self._update_sync_status(
                measurement,
                SyncStatus.FAILED,
                error_message=str(e),
                sync_attempts=sync_request['attempts']
            )
            
            return {'success': False, 'error': str(e)}
    
    async def _sync_inbody_measurement(self, measurement: MeasurementData, sync_request: Dict) -> Dict:
        """Sync InBody measurement to Actiwell"""
        try:
            if not self.actiwell_api:
                return {'success': False, 'error': 'No Actiwell API configured'}
            
            # Get customer information
            customer_info = await self._get_customer_info(measurement.customer_phone)
            
            if not customer_info or not customer_info.get('actiwell_customer_id'):
                return {'success': False, 'error': 'Customer not found in Actiwell'}
            
            # Prepare InBody-specific data for Actiwell
            actiwell_data = {
                'customer_id': customer_info['actiwell_customer_id'],
                'activity_type': 5,  # Body composition measurement
                'location_id': self.config.get('actiwell_location_id', 1),
                'operator_id': self.config.get('actiwell_operator_id', 1),
                'measurement_timestamp': measurement.measurement_timestamp.isoformat(),
                'device_type': 'inbody_270',
                'data': {
                    'basic_measurements': {
                        'weight_kg': measurement.weight_kg,
                        'height_cm': measurement.height_cm,
                        'bmi': measurement.bmi,
                        'age': measurement.age,
                        'gender': measurement.gender
                    },
                    'body_composition': {
                        'body_fat_percent': measurement.body_fat_percent,
                        'muscle_mass_kg': measurement.muscle_mass_kg,
                        'total_body_water_kg': measurement.total_body_water_kg,
                        'total_body_water_percent': measurement.total_body_water_percent,
                        'bmr_kcal': measurement.bmr_kcal
                    },
                    'segmental_lean_analysis': {
                        'right_leg_muscle_kg': measurement.right_leg_muscle_kg,
                        'left_leg_muscle_kg': measurement.left_leg_muscle_kg,
                        'right_arm_muscle_kg': measurement.right_arm_muscle_kg,
                        'left_arm_muscle_kg': measurement.left_arm_muscle_kg,
                        'trunk_muscle_kg': measurement.trunk_muscle_kg
                    },
                    'bioelectrical_impedance': {
                        'impedance_50khz': measurement.impedance_50khz,
                        'impedance_250khz': measurement.impedance_250khz,
                        'phase_angle': measurement.phase_angle
                    },
                    'quality_metrics': {
                        'measurement_quality': measurement.measurement_quality,
                        'data_completeness': measurement.data_completeness
                    }
                },
                'raw_data': measurement.raw_data,
                'processing_notes': measurement.processing_notes
            }
            
            # Send to Actiwell
            result = await self.actiwell_api.save_body_composition(actiwell_data)
            
            if result and result.get('success'):
                # Update sync status in database
                await self._update_sync_status(
                    measurement,
                    SyncStatus.SUCCESS,
                    actiwell_measurement_id=result.get('measurement_id'),
                    sync_attempts=sync_request['attempts']
                )
                
                return {'success': True, 'actiwell_id': result.get('measurement_id')}
            else:
                error_msg = result.get('error', 'Unknown Actiwell API error') if result else 'No response from Actiwell API'
                
                await self._update_sync_status(
                    measurement,
                    SyncStatus.FAILED,
                    error_message=error_msg,
                    sync_attempts=sync_request['attempts']
                )
                
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            logger.error(f"Error syncing InBody measurement: {e}")
            
            await self._update_sync_status(
                measurement,
                SyncStatus.FAILED,
                error_message=str(e),
                sync_attempts=sync_request['attempts']
            )
            
            return {'success': False, 'error': str(e)}
    
    async def _sync_generic_measurement(self, measurement: MeasurementData, sync_request: Dict) -> Dict:
        """Sync generic measurement to Actiwell"""
        try:
            logger.warning(f"Using generic sync for unknown device type: {measurement.device_type}")
            
            if not self.actiwell_api:
                return {'success': False, 'error': 'No Actiwell API configured'}
            
            # Get customer information
            customer_info = await self._get_customer_info(measurement.customer_phone)
            
            if not customer_info or not customer_info.get('actiwell_customer_id'):
                return {'success': False, 'error': 'Customer not found in Actiwell'}
            
            # Prepare generic data for Actiwell
            actiwell_data = {
                'customer_id': customer_info['actiwell_customer_id'],
                'activity_type': 5,  # Body composition measurement
                'location_id': self.config.get('actiwell_location_id', 1),
                'operator_id': self.config.get('actiwell_operator_id', 1),
                'measurement_timestamp': measurement.measurement_timestamp.isoformat(),
                'device_type': 'generic_body_composition',
                'data': {
                    'basic_measurements': {
                        'weight_kg': measurement.weight_kg,
                        'height_cm': measurement.height_cm,
                        'bmi': measurement.bmi
                    },
                    'body_composition': {
                        'body_fat_percent': measurement.body_fat_percent,
                        'muscle_mass_kg': measurement.muscle_mass_kg
                    }
                },
                'raw_data': measurement.raw_data,
                'processing_notes': measurement.processing_notes
            }
            
            # Send to Actiwell
            result = await self.actiwell_api.save_body_composition(actiwell_data)
            
            if result and result.get('success'):
                await self._update_sync_status(
                    measurement,
                    SyncStatus.SUCCESS,
                    actiwell_measurement_id=result.get('measurement_id'),
                    sync_attempts=sync_request['attempts']
                )
                
                return {'success': True, 'actiwell_id': result.get('measurement_id')}
            else:
                error_msg = result.get('error', 'Unknown error') if result else 'No response'
                
                await self._update_sync_status(
                    measurement,
                    SyncStatus.FAILED,
                    error_message=error_msg,
                    sync_attempts=sync_request['attempts']
                )
                
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            logger.error(f"Error syncing generic measurement: {e}")
            
            await self._update_sync_status(
                measurement,
                SyncStatus.FAILED,
                error_message=str(e),
                sync_attempts=sync_request['attempts']
            )
            
            return {'success': False, 'error': str(e)}
    
    async def _get_customer_info(self, phone_number: str) -> Optional[Dict]:
        """Get customer information for sync"""
        try:
            # Check local database first
            customer_info = await self.database_manager.get_customer_by_phone(phone_number)
            
            if customer_info and customer_info.get('actiwell_customer_id'):
                return customer_info
            
            # Try to find in Actiwell if API available
            if self.actiwell_api:
                actiwell_customer = await self.actiwell_api.search_customer_by_phone(
                    phone_number,
                    location_id=self.config.get('actiwell_location_id', 1),
                    operator_id=self.config.get('actiwell_operator_id', 1)
                )
                
                if actiwell_customer:
                    # Update local database
                    if customer_info:
                        await self.database_manager.update_customer(phone_number, actiwell_customer)
                    else:
                        await self.database_manager.create_customer(actiwell_customer)
                    
                    return actiwell_customer
            
            return customer_info
            
        except Exception as e:
            logger.error(f"Error getting customer info for sync: {e}")
            return None
    
    async def _update_sync_status(self, measurement: MeasurementData, status: SyncStatus, 
                                 actiwell_measurement_id: int = None, error_message: str = None,
                                 sync_attempts: int = 1):
        """Update sync status in database"""
        try:
            sync_data = {
                'customer_phone': measurement.customer_phone,
                'device_type': measurement.device_type,
                'measurement_timestamp': measurement.measurement_timestamp,
                'sync_status': status.value,
                'sync_attempts': sync_attempts,
                'last_sync_attempt': datetime.now(),
                'actiwell_measurement_id': actiwell_measurement_id,
                'error_message': error_message
            }
            
            await self.database_manager.update_measurement_sync_status(sync_data)
            
        except Exception as e:
            logger.error(f"Error updating sync status: {e}")
    
    async def _queue_for_retry(self, sync_request: Dict, sync_result: Dict):
        """Queue failed sync for retry"""
        try:
            # Update sync request for retry
            sync_request['retry_after'] = datetime.now() + timedelta(seconds=self.retry_delay_seconds)
            sync_request['last_error'] = sync_result.get('error', 'Unknown error')
            sync_request['priority'] = SyncPriority.HIGH  # Higher priority for retries
            
            # Save retry request to database
            await self.database_manager.save_sync_retry_request(sync_request)
            
            self.sync_stats['retry_syncs'] += 1
            logger.info(f"Queued measurement for retry: {sync_request['measurement'].customer_phone}")
            
        except Exception as e:
            logger.error(f"Error queuing sync for retry: {e}")
    
    async def _retry_failed_syncs(self):
        """Process failed syncs for retry"""
        try:
            # Get retry requests that are ready
            retry_requests = await self.database_manager.get_pending_sync_retries()
            
            for retry_request in retry_requests:
                if retry_request['retry_after'] <= datetime.now():
                    # Add back to sync queue
                    await self.sync_queue.put(retry_request)
                    logger.info(f"Retrying sync for: {retry_request['measurement'].customer_phone}")
            
        except Exception as e:
            logger.error(f"Error processing retry requests: {e}")
    
    async def batch_sync_pending_measurements(self, limit: int = 100) -> Dict:
        """Batch sync pending measurements"""
        try:
            if not self.batch_sync_enabled:
                return {'error': 'Batch sync disabled'}
            
            logger.info(f"Starting batch sync of pending measurements (limit: {limit})")
            
            # Get pending measurements
            pending_measurements = await self.database_manager.get_pending_sync_measurements(limit)
            
            if not pending_measurements:
                return {'message': 'No pending measurements to sync', 'count': 0}
            
            batch_results = {
                'total': len(pending_measurements),
                'successful': 0,
                'failed': 0,
                'errors': []
            }
            
            # Process each measurement
            for measurement_data in pending_measurements:
                try:
                    # Convert database record to MeasurementData object
                    measurement = self._convert_db_record_to_measurement(measurement_data)
                    
                    # Sync measurement
                    success = await self.sync_measurement_async(measurement, priority=SyncPriority.LOW)
                    
                    if success:
                        batch_results['successful'] += 1
                    else:
                        batch_results['failed'] += 1
                        
                except Exception as e:
                    batch_results['failed'] += 1
                    batch_results['errors'].append(f"Error processing measurement {measurement_data.get('id')}: {str(e)}")
                    logger.error(f"Error in batch sync: {e}")
            
            logger.info(f"Batch sync completed: {batch_results['successful']}/{batch_results['total']} successful")
            return batch_results
            
        except Exception as e:
            logger.error(f"Error in batch sync: {e}")
            return {'error': str(e)}
    
    def _convert_db_record_to_measurement(self, db_record: Dict) -> MeasurementData:
        """Convert database record to MeasurementData object"""
        measurement = MeasurementData()
        
        # Map database fields to MeasurementData attributes
        field_mapping = {
            'device_id': 'device_id',
            'device_type': 'device_type',
            'extracted_phone_number': 'customer_phone',
            'measurement_timestamp': 'measurement_timestamp',
            'weight_kg': 'weight_kg',
            'height_cm': 'height_cm',
            'bmi': 'bmi',
            'body_fat_percent': 'body_fat_percent',
            'muscle_mass_kg': 'muscle_mass_kg',
            'bone_mass_kg': 'bone_mass_kg',
            'total_body_water_kg': 'total_body_water_kg',
            'total_body_water_percent': 'total_body_water_percent',
            'visceral_fat_rating': 'visceral_fat_rating',
            'metabolic_age': 'metabolic_age',
            'bmr_kcal': 'bmr_kcal',
            'raw_data': 'raw_data',
            'processing_notes': 'processing_notes'
        }
        
        for db_field, measurement_field in field_mapping.items():
            if db_field in db_record:
                setattr(measurement, measurement_field, db_record[db_field])
        
        return measurement
    
    async def get_sync_statistics(self) -> Dict:
        """Get sync service statistics"""
        try:
            # Get database sync statistics
            db_stats = await self.database_manager.get_sync_statistics()
            
            # Calculate uptime
            uptime_seconds = (datetime.now() - self.sync_stats['start_time']).total_seconds()
            
            # Combine statistics
            stats = {
                'service_stats': {
                    **self.sync_stats,
                    'uptime_seconds': uptime_seconds,
                    'success_rate': (
                        (self.sync_stats['successful_syncs'] / max(1, self.sync_stats['total_syncs'])) * 100
                    ),
                    'queue_size': self.sync_queue.qsize(),
                    'workers_active': len([w for w in self.sync_workers if not w.done()]),
                    'auto_sync_enabled': self.auto_sync_enabled,
                    'batch_sync_enabled': self.batch_sync_enabled,
                    'retry_enabled': self.retry_enabled
                },
                'database_stats': db_stats,
                'configuration': {
                    'max_retry_attempts': self.max_retry_attempts,
                    'retry_delay_seconds': self.retry_delay_seconds,
                    'worker_count': self.worker_count,
                    'supported_devices': list(self.device_sync_handlers.keys())
                }
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting sync statistics: {e}")
            return {'error': str(e)}
    
    async def get_pending_sync_count(self, device_type: str = None) -> int:
        """Get count of pending sync measurements"""
        try:
            return await self.database_manager.get_pending_sync_count(device_type)
        except Exception as e:
            logger.error(f"Error getting pending sync count: {e}")
            return 0
    
    async def force_sync_customer_measurements(self, phone_number: str, days: int = 7) -> Dict:
        """Force sync all measurements for a specific customer"""
        try:
            logger.info(f"Force syncing measurements for customer: {phone_number}")
            
            # Get customer measurements
            measurements = await self.database_manager.get_customer_measurements(
                phone_number, 
                days, 
                include_synced=False  # Only unsynced measurements
            )
            
            if not measurements:
                return {'message': 'No unsynced measurements found', 'count': 0}
            
            results = {
                'total': len(measurements),
                'successful': 0,
                'failed': 0
            }
            
            # Sync each measurement with high priority
            for measurement_data in measurements:
                try:
                    measurement = self._convert_db_record_to_measurement(measurement_data)
                    success = await self.sync_measurement_async(
                        measurement, 
                        priority=SyncPriority.URGENT
                    )
                    
                    if success:
                        results['successful'] += 1
                    else:
                        results['failed'] += 1
                        
                except Exception as e:
                    results['failed'] += 1
                    logger.error(f"Error force syncing measurement: {e}")
            
            logger.info(f"Force sync completed for {phone_number}: {results['successful']}/{results['total']} successful")
            return results
            
        except Exception as e:
            logger.error(f"Error in force sync: {e}")
            return {'error': str(e)}