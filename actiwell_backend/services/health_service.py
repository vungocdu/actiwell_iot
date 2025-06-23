"""
Health Service - System health monitoring and alerts
"""

import logging
import psutil
from datetime import datetime

logger = logging.getLogger(__name__)

class HealthService:
    def __init__(self, db_manager, device_manager):
        self.db_manager = db_manager
        self.device_manager = device_manager
        
    def check_system_health(self) -> dict:
        """Perform comprehensive system health check"""
        try:
            health_status = {
                'timestamp': datetime.now().isoformat(),
                'overall_status': 'healthy',
                'critical_issues': [],
                'warnings': []
            }
            
            # Check CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > 90:
                health_status['critical_issues'].append(f"High CPU usage: {cpu_percent}%")
            elif cpu_percent > 70:
                health_status['warnings'].append(f"Elevated CPU usage: {cpu_percent}%")
            
            # Check memory usage
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                health_status['critical_issues'].append(f"High memory usage: {memory.percent}%")
            elif memory.percent > 70:
                health_status['warnings'].append(f"Elevated memory usage: {memory.percent}%")
            
            # Check disk space
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            if disk_percent > 90:
                health_status['critical_issues'].append(f"Low disk space: {disk_percent:.1f}% used")
            elif disk_percent > 80:
                health_status['warnings'].append(f"Disk space warning: {disk_percent:.1f}% used")
            
            # Determine overall status
            if health_status['critical_issues']:
                health_status['overall_status'] = 'critical'
            elif health_status['warnings']:
                health_status['overall_status'] = 'warning'
            
            return health_status
            
        except Exception as e:
            logger.error(f"Error checking system health: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'overall_status': 'error',
                'error': str(e)
            }