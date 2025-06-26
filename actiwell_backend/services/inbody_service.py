#!/usr/bin/env python3
"""
InBody Integration Service - Fixed Version
Business logic layer for InBody device integration
Focuses on orchestration and business rules specific to InBody devices
Fixed issues with None handling and error management
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Union

try:
    from ..devices.inbody_protocol import InBodyProtocol
    from ..devices.base_protocol import MeasurementData
    from .measurement_service import MeasurementService
    from .sync_service import SyncService
except ImportError:
    # Fallback for direct testing
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from devices.inbody_protocol import InBodyProtocol
    from devices.base_protocol import MeasurementData
    from services.measurement_service import MeasurementService
    from services.sync_service import SyncService

logger = logging.getLogger(__name__)

class InBodyService:
    """
    InBody-specific business logic service
    Handles InBody device integration and business rules
    Fixed version with improved error handling
    """
    
    def __init__(self, measurement_service: MeasurementService, sync_service: SyncService, config: Dict = None):
        """
        Initialize InBody service
        
        Args:
            measurement_service: Common measurement processing service
            sync_service: Common sync service
            config: InBody-specific configuration
        """
        self.measurement_service = measurement_service
        self.sync_service = sync_service
        self.config = config or {}
        
        # InBody device protocol
        self.inbody_protocol: Optional[InBodyProtocol] = None
        
        # Processing queue for async operations
        self.processing_queue = asyncio.Queue()
        self.is_processing = False
        
        # InBody-specific configuration with safe defaults
        self.ip_address = self.config.get('ip_address', '192.168.1.100')
        self.data_port = self.config.get('data_port', 2575)
        self.listening_port = self.config.get('listening_port', 2580)
        
        # Business rules specific to InBody
        self.auto_sync_enabled = self.config.get('auto_sync_enabled', True)
        self.quality_threshold = self.config.get('quality_threshold', 'good')
        
        # Error tracking
        self.error_count = 0
        self.last_error_time = None
        
        logger.info(f"InBody Service initialized with config: {self.ip_address}:{self.data_port}")
    
    async def start(self) -> bool:
        """Start InBody integration service"""
        try:
            logger.info("Starting InBody integration service...")
            
            # Validate configuration first
            if not self._validate_configuration():
                logger.error("InBody configuration validation failed")
                return False
            
            # Initialize InBody protocol
            self.inbody_protocol = InBodyProtocol(
                ip_address=self.ip_address,
                data_port=self.data_port,
                listening_port=self.listening_port
            )
            
            # Set up measurement callback with error handling
            self.inbody_protocol.set_callbacks(
                measurement_cb=self._handle_measurement_safe,
                status_cb=self._handle_status,
                error_cb=self._handle_error
            )
            
            # Start protocol handler
            if not self.inbody_protocol.connect():
                logger.error("Failed to start InBody protocol handler")
                return False
            
            # Start processing worker
            self.is_processing = True
            asyncio.create_task(self._processing_worker())
            
            logger.info("InBody Service started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start InBody Service: {e}")
            self._increment_error_count()
            return False
    
    async def stop(self):
        """Stop InBody integration service"""
        try:
            logger.info("Stopping InBody integration service...")
            self.is_processing = False
            
            if self.inbody_protocol:
                self.inbody_protocol.disconnect()
                self.inbody_protocol = None
            
            # Clear processing queue
            while not self.processing_queue.empty():
                try:
                    self.processing_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            
            logger.info("InBody Service stopped")
            
        except Exception as e:
            logger.error(f"Error stopping InBody Service: {e}")
    
    def _validate_configuration(self) -> bool:
        """Validate InBody configuration"""
        try:
            # Check required fields
            if not self.ip_address:
                logger.error("InBody IP address not configured")
                return False
            
            if not (1024 <= self.data_port <= 65535):
                logger.error(f"Invalid InBody data port: {self.data_port}")
                return False
            
            if not (1024 <= self.listening_port <= 65535):
                logger.error(f"Invalid InBody listening port: {self.listening_port}")
                return False
            
            if self.data_port == self.listening_port:
                logger.error("Data port and listening port cannot be the same")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating InBody configuration: {e}")
            return False
    
    def _handle_measurement_safe(self, measurement: MeasurementData):
        """Safe wrapper for measurement handling"""
        try:
            self._handle_measurement(measurement)
        except Exception as e:
            logger.error(f"Error in measurement handler: {e}")
            self._increment_error_count()
    
    def _handle_measurement(self, measurement: MeasurementData):
        """Handle measurement from InBody device"""
        try:
            if measurement is None:
                logger.warning("Received None measurement data")
                return
            
            customer_phone = getattr(measurement, 'customer_phone', 'Unknown')
            logger.info(f"InBody measurement received for customer: {customer_phone}")
            
            # Apply InBody-specific business rules
            self._apply_inbody_business_rules(measurement)
            
            # Add to processing queue
            asyncio.create_task(self._queue_measurement(measurement))
            
        except Exception as e:
            logger.error(f"Error handling InBody measurement: {e}")
            self._increment_error_count()
    
    def _handle_status(self, device_id: str, status: str):
        """Handle device status updates"""
        try:
            logger.info(f"InBody device status: {device_id} -> {status}")
            
            # Reset error count on successful status update
            if status in ['connected', 'ready', 'measuring']:
                self.error_count = 0
                
        except Exception as e:
            logger.error(f"Error handling status update: {e}")
    
    def _handle_error(self, device_id: str, error: str):
        """Handle device errors"""
        try:
            logger.error(f"InBody device error: {device_id} -> {error}")
            self._increment_error_count()
            
        except Exception as e:
            logger.error(f"Error in error handler: {e}")
    
    def _apply_inbody_business_rules(self, measurement: MeasurementData):
        """Apply InBody-specific business rules - Fixed version"""
        try:
            if measurement is None:
                logger.warning("Cannot apply business rules to None measurement")
                return
            
            # InBody quality assessment (Fixed: Check None first)
            current_quality = getattr(measurement, 'measurement_quality', None)
            if current_quality is None or current_quality == '':
                measurement.measurement_quality = self._assess_inbody_quality(measurement)
                logger.debug(f"Assigned quality: {measurement.measurement_quality}")
            
            # InBody-specific validations
            self._validate_inbody_measurement(measurement)
            
            # Add InBody-specific processing notes (Fixed: Safe string handling)
            current_notes = getattr(measurement, 'processing_notes', None)
            if current_notes:
                measurement.processing_notes = f"{current_notes}; InBody HL7 processed"
            else:
                measurement.processing_notes = "InBody HL7 processed"
            
            # Add timestamp if missing
            if not hasattr(measurement, 'processed_at') or measurement.processed_at is None:
                measurement.processed_at = datetime.now()
            
            logger.debug("InBody business rules applied successfully")
            
        except Exception as e:
            logger.error(f"Error applying InBody business rules: {e}")
            # Don't raise exception, continue processing with warnings
            if hasattr(measurement, 'processing_notes'):
                measurement.processing_notes = f"{getattr(measurement, 'processing_notes', '')}; Warning: Business rules error"
    
    def _assess_inbody_quality(self, measurement: MeasurementData) -> str:
        """Assess measurement quality for InBody devices - Fixed version"""
        try:
            if measurement is None:
                return "unknown"
            
            # InBody-specific quality criteria
            quality_score = 0
            
            # Check basic data completeness (Fixed: Safe attribute access)
            weight_kg = getattr(measurement, 'weight_kg', None)
            if weight_kg and float(weight_kg) > 0:
                quality_score += 1
            
            muscle_mass_kg = getattr(measurement, 'muscle_mass_kg', None)
            if muscle_mass_kg and float(muscle_mass_kg) > 0:
                quality_score += 1
            
            total_body_water_kg = getattr(measurement, 'total_body_water_kg', None)
            if total_body_water_kg and float(total_body_water_kg) > 0:
                quality_score += 1
            
            # Check segmental data (InBody specialty) - Fixed: Safe access
            segmental_count = 0
            segmental_attributes = [
                'right_leg_muscle_kg', 'left_leg_muscle_kg', 
                'right_arm_muscle_kg', 'left_arm_muscle_kg', 'trunk_muscle_kg'
            ]
            
            for attr in segmental_attributes:
                value = getattr(measurement, attr, None)
                if value is not None and float(value) > 0:
                    segmental_count += 1
            
            if segmental_count >= 3:
                quality_score += 2
            elif segmental_count >= 1:
                quality_score += 1
            
            # Check impedance data (Fixed: Safe access)
            impedance_50khz = getattr(measurement, 'impedance_50khz', None)
            if impedance_50khz and float(impedance_50khz) > 0:
                quality_score += 1
            
            # Check customer identification
            customer_phone = getattr(measurement, 'customer_phone', None)
            if customer_phone and len(str(customer_phone).strip()) >= 10:
                quality_score += 1
            
            # Determine quality level
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
            return "error"
    
    def _validate_inbody_measurement(self, measurement: MeasurementData):
        """Validate InBody-specific measurement criteria - Fixed version"""
        try:
            if measurement is None:
                return
            
            errors = []
            
            # Initialize validation_errors if not exists
            if not hasattr(measurement, 'validation_errors'):
                measurement.validation_errors = []
            
            # InBody-specific validation rules (Fixed: Safe numeric conversion)
            muscle_mass_kg = getattr(measurement, 'muscle_mass_kg', None)
            weight_kg = getattr(measurement, 'weight_kg', None)
            
            if muscle_mass_kg and weight_kg:
                try:
                    muscle_ratio = float(muscle_mass_kg) / float(weight_kg)
                    if muscle_ratio > 0.8:  # Unrealistic muscle ratio
                        errors.append("Muscle mass ratio too high (>80%)")
                    elif muscle_ratio < 0.1:  # Too low muscle ratio
                        errors.append("Muscle mass ratio too low (<10%)")
                except (ValueError, ZeroDivisionError) as e:
                    errors.append(f"Invalid muscle/weight ratio calculation: {e}")
            
            # Check segmental balance (InBody feature) - Fixed: Safe access
            right_leg = getattr(measurement, 'right_leg_muscle_kg', None)
            left_leg = getattr(measurement, 'left_leg_muscle_kg', None)
            
            if right_leg and left_leg:
                try:
                    leg_difference = abs(float(right_leg) - float(left_leg))
                    if leg_difference > 2.0:  # >2kg difference
                        errors.append("Significant leg muscle imbalance detected (>2kg difference)")
                except ValueError as e:
                    errors.append(f"Invalid leg muscle data: {e}")
            
            # Check reasonable weight range
            if weight_kg:
                try:
                    weight_value = float(weight_kg)
                    if weight_value < 10 or weight_value > 300:
                        errors.append(f"Weight out of reasonable range: {weight_value}kg")
                except ValueError:
                    errors.append("Invalid weight value")
            
            # Phone number validation
            customer_phone = getattr(measurement, 'customer_phone', None)
            if customer_phone:
                phone_str = str(customer_phone).strip()
                if len(phone_str) < 10:
                    errors.append("Customer phone number too short")
                elif not phone_str.isdigit() and not phone_str.startswith('+'):
                    errors.append("Invalid customer phone number format")
            
            # Add validation errors to measurement (Fixed: Safe list handling)
            if errors:
                if isinstance(measurement.validation_errors, list):
                    measurement.validation_errors.extend(errors)
                else:
                    measurement.validation_errors = errors
                
                logger.warning(f"InBody validation errors: {errors}")
            
        except Exception as e:
            logger.error(f"Error validating InBody measurement: {e}")
            # Add error to validation_errors if possible
            try:
                if hasattr(measurement, 'validation_errors'):
                    if isinstance(measurement.validation_errors, list):
                        measurement.validation_errors.append(f"Validation process error: {str(e)}")
            except:
                pass
    
    async def _queue_measurement(self, measurement: MeasurementData):
        """Add measurement to processing queue - Fixed version"""
        try:
            if measurement is None:
                logger.warning("Cannot queue None measurement")
                return
            
            # Check queue size limit
            if self.processing_queue.qsize() >= 100:  # Prevent memory issues
                logger.warning("Processing queue full, dropping oldest measurement")
                try:
                    self.processing_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            
            await self.processing_queue.put(measurement)
            logger.debug("InBody measurement queued for processing")
            
        except Exception as e:
            logger.error(f"Error queuing measurement: {e}")
    
    async def _processing_worker(self):
        """Background worker for processing InBody measurements - Fixed version"""
        logger.info("InBody processing worker started")
        consecutive_errors = 0
        
        while self.is_processing:
            try:
                # Get measurement from queue (with timeout)
                measurement = await asyncio.wait_for(
                    self.processing_queue.get(), 
                    timeout=1.0
                )
                
                if measurement is None:
                    logger.warning("Received None measurement in processing worker")
                    continue
                
                # Process measurement through common service
                success = await self.measurement_service.process_measurement_async(
                    measurement, 
                    device_type='inbody'
                )
                
                if success:
                    consecutive_errors = 0  # Reset error counter
                    
                    if self.auto_sync_enabled:
                        # Sync to external systems if enabled
                        try:
                            await self.sync_service.sync_measurement_async(
                                measurement,
                                device_type='inbody'
                            )
                        except Exception as sync_error:
                            logger.error(f"Sync error (continuing): {sync_error}")
                else:
                    consecutive_errors += 1
                    logger.warning(f"Measurement processing failed (consecutive errors: {consecutive_errors})")
                
                # If too many consecutive errors, slow down processing
                if consecutive_errors >= 5:
                    logger.warning("Too many processing errors, slowing down worker")
                    await asyncio.sleep(5)
                    consecutive_errors = 0  # Reset after cooldown
                
            except asyncio.TimeoutError:
                # No measurement in queue, continue
                continue
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"InBody processing worker error: {e}")
                
                if consecutive_errors >= 10:
                    logger.error("Too many worker errors, stopping processing")
                    break
                
                await asyncio.sleep(1)
        
        logger.info("InBody processing worker stopped")
    
    def _increment_error_count(self):
        """Track error count for monitoring"""
        self.error_count += 1
        self.last_error_time = datetime.now()
        
        if self.error_count > 50:  # Reset after too many errors
            logger.warning(f"Error count reset after reaching {self.error_count}")
            self.error_count = 0
    
    async def get_measurement_statistics(self, phone_number: str, days: int = 30) -> Dict:
        """Get InBody-specific measurement statistics - Fixed version"""
        try:
            if not phone_number or not isinstance(phone_number, str):
                return {'error': 'Invalid phone number provided'}
            
            # Get measurements through common service
            measurements = await self.measurement_service.get_customer_measurements(
                phone_number.strip(), 
                days, 
                device_type='inbody'
            )
            
            if not measurements:
                return {'error': 'No InBody measurements found', 'phone_number': phone_number}
            
            # Calculate InBody-specific statistics
            stats = await self._calculate_inbody_statistics(measurements)
            stats['phone_number'] = phone_number
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting InBody measurement statistics: {e}")
            return {'error': str(e), 'phone_number': phone_number}
    
    async def _calculate_inbody_statistics(self, measurements: List[Dict]) -> Dict:
        """Calculate InBody-specific statistics - Fixed version"""
        try:
            if not measurements or not isinstance(measurements, list):
                return {'error': 'No valid measurements provided'}
            
            # Basic statistics
            total_measurements = len(measurements)
            latest_measurement = max(measurements, key=lambda x: x.get('measurement_timestamp', datetime.min))
            
            # InBody-specific averages (Fixed: Safe value extraction)
            muscle_mass_values = []
            water_values = []
            
            for m in measurements:
                if isinstance(m, dict):
                    muscle_val = m.get('muscle_mass_kg')
                    if muscle_val is not None and muscle_val > 0:
                        muscle_mass_values.append(float(muscle_val))
                    
                    water_val = m.get('total_body_water_kg')
                    if water_val is not None and water_val > 0:
                        water_values.append(float(water_val))
            
            # Segmental analysis trends (InBody specialty) - Fixed: Safe calculation
            segmental_stats = {}
            segmental_fields = [
                'right_leg_muscle_kg', 'left_leg_muscle_kg', 
                'right_arm_muscle_kg', 'left_arm_muscle_kg', 'trunk_muscle_kg'
            ]
            
            for segment in segmental_fields:
                values = []
                for m in measurements:
                    if isinstance(m, dict):
                        val = m.get(segment)
                        if val is not None and val > 0:
                            values.append(float(val))
                
                if values:
                    segmental_stats[segment] = {
                        'average': round(sum(values) / len(values), 2),
                        'latest': values[-1] if values else 0,
                        'trend': self._calculate_trend(values),
                        'count': len(values)
                    }
            
            # Build statistics dictionary
            stats = {
                'total_measurements': total_measurements,
                'date_range': {
                    'start': min(m.get('measurement_timestamp', datetime.now()) for m in measurements).isoformat(),
                    'end': max(m.get('measurement_timestamp', datetime.now()) for m in measurements).isoformat()
                },
                'averages': {
                    'muscle_mass_kg': round(sum(muscle_mass_values) / len(muscle_mass_values), 2) if muscle_mass_values else 0,
                    'total_body_water_kg': round(sum(water_values) / len(water_values), 2) if water_values else 0,
                },
                'latest_measurement': latest_measurement,
                'segmental_analysis': segmental_stats,
                'quality_distribution': self._calculate_quality_distribution(measurements),
                'device_type': 'inbody',
                'statistics_generated_at': datetime.now().isoformat()
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculating InBody statistics: {e}")
            return {'error': f'Statistics calculation failed: {str(e)}'}
    
    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend for a series of values - Fixed version"""
        try:
            if not values or len(values) < 2:
                return 'insufficient_data'
            
            # Simple trend calculation (Fixed: Safe division)
            mid_point = len(values) // 2
            if mid_point == 0:
                return 'insufficient_data'
            
            first_half = sum(values[:mid_point]) / mid_point
            second_half = sum(values[mid_point:]) / (len(values) - mid_point)
            
            difference = second_half - first_half
            
            if difference > 0.5:
                return 'increasing'
            elif difference < -0.5:
                return 'decreasing'
            else:
                return 'stable'
                
        except Exception as e:
            logger.error(f"Error calculating trend: {e}")
            return 'error'
    
    def _calculate_quality_distribution(self, measurements: List[Dict]) -> Dict:
        """Calculate distribution of measurement quality - Fixed version"""
        try:
            if not measurements:
                return {}
            
            quality_counts = {}
            
            for measurement in measurements:
                if isinstance(measurement, dict):
                    quality = measurement.get('measurement_quality', 'unknown')
                    quality_counts[quality] = quality_counts.get(quality, 0) + 1
            
            total = len(measurements)
            quality_distribution = {}
            
            for quality, count in quality_counts.items():
                quality_distribution[quality] = {
                    'count': count,
                    'percentage': round((count / total) * 100, 1) if total > 0 else 0
                }
            
            return quality_distribution
            
        except Exception as e:
            logger.error(f"Error calculating quality distribution: {e}")
            return {'error': str(e)}
    
    def get_device_status(self) -> Dict:
        """Get InBody device status - Fixed version"""
        try:
            base_status = {
                'service_status': 'running' if self.is_processing else 'stopped',
                'auto_sync_enabled': self.auto_sync_enabled,
                'quality_threshold': self.quality_threshold,
                'queue_size': self.processing_queue.qsize() if hasattr(self, 'processing_queue') else 0,
                'error_count': self.error_count,
                'last_error_time': self.last_error_time.isoformat() if self.last_error_time else None,
                'configuration': {
                    'ip_address': self.ip_address,
                    'data_port': self.data_port,
                    'listening_port': self.listening_port
                }
            }
            
            if self.inbody_protocol:
                try:
                    device_info = self.inbody_protocol.get_device_info()
                    base_status.update(device_info)
                except Exception as e:
                    base_status['device_info_error'] = str(e)
            else:
                base_status['error'] = 'InBody protocol not initialized'
            
            return base_status
                
        except Exception as e:
            logger.error(f"Error getting InBody device status: {e}")
            return {
                'error': str(e),
                'service_status': 'error'
            }
    
    async def trigger_calibration(self) -> Dict:
        """Trigger InBody device calibration (if supported) - Fixed version"""
        try:
            logger.info("InBody calibration check initiated")
            
            # InBody devices typically self-calibrate
            # This is more of a connectivity/status check
            
            if self.inbody_protocol and hasattr(self.inbody_protocol, 'is_connected') and self.inbody_protocol.is_connected:
                return {
                    'status': 'success',
                    'message': 'InBody device is connected and ready',
                    'calibration_required': False,
                    'note': 'InBody devices self-calibrate automatically',
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return {
                    'status': 'error',
                    'message': 'InBody device not connected',
                    'calibration_required': True,
                    'timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error checking InBody calibration: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def get_device_capabilities(self) -> Dict:
        """Get InBody device capabilities - Fixed version"""
        try:
            base_capabilities = {
                'hl7_support': True,
                'network_connection': True,
                'real_time_monitoring': True,
                'segmental_analysis_regions': 5,
                'measurement_frequencies': ['5kHz', '50kHz', '250kHz'],
                'supported_protocols': ['HL7 v2.5', 'TCP/IP'],
                'data_export_formats': ['HL7', 'CSV', 'JSON'],
                'auto_calibration': True,
                'quality_assessment': True
            }
            
            if self.inbody_protocol and hasattr(self.inbody_protocol, 'capabilities'):
                try:
                    device_capabilities = self.inbody_protocol.capabilities.__dict__
                    base_capabilities.update(device_capabilities)
                except Exception as e:
                    base_capabilities['capabilities_error'] = str(e)
            
            return base_capabilities
                
        except Exception as e:
            logger.error(f"Error getting InBody capabilities: {e}")
            return {'error': str(e)}
    
    def get_service_health(self) -> Dict:
        """Get service health information"""
        try:
            return {
                'service_name': 'InBodyService',
                'status': 'healthy' if self.is_processing and self.error_count < 10 else 'unhealthy',
                'uptime_status': 'running' if self.is_processing else 'stopped',
                'error_count': self.error_count,
                'queue_size': self.processing_queue.qsize() if hasattr(self, 'processing_queue') else 0,
                'last_error_time': self.last_error_time.isoformat() if self.last_error_time else None,
                'configuration_valid': self._validate_configuration(),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting service health: {e}")
            return {
                'service_name': 'InBodyService',
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }