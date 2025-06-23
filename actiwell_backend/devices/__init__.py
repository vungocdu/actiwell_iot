"""
Device protocols package initialization
"""
import logging

logger = logging.getLogger(__name__)

# Import device protocols with error handling
try:
    from .base_protocol import DeviceProtocol, DeviceState, MeasurementStatus
    logger.debug("Base protocol imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import base protocol: {e}")
    DeviceProtocol = None
    DeviceState = None
    MeasurementStatus = None

try:
    from .tanita_protocol import TanitaProtocol
    logger.debug("Tanita protocol imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import Tanita protocol: {e}")
    TanitaProtocol = None

try:
    from .inbody_protocol import InBodyProtocol
    logger.debug("InBody protocol imported successfully")
except ImportError as e:
    logger.warning(f"Failed to import InBody protocol: {e}")
    InBodyProtocol = None

__all__ = [
    'DeviceProtocol',
    'DeviceState', 
    'MeasurementStatus',
    'TanitaProtocol',
    'InBodyProtocol'
]