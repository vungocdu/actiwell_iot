# ====================================================================================
# 5. DEVICE COMMUNICATION (device_manager.py)
# ====================================================================================

class DeviceProtocol:
    """Base protocol class for body composition devices"""
    
    def __init__(self, port: str, baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        self.serial_connection = None
        self.is_connected = False
        
    def connect(self) -> bool:
        """Connect to device"""
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=Config.DEVICE_TIMEOUT,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            
            # Test communication
            time.sleep(1)
            self.serial_connection.flushInput()
            self.serial_connection.flushOutput()
            
            self.is_connected = True
            logger.info(f"Connected to device on {self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Device connection error on {self.port}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from device"""
        try:
            if self.serial_connection and self.serial_connection.is_open:
                self.serial_connection.close()
            self.is_connected = False
            logger.info(f"Disconnected from device on {self.port}")
        except Exception as e:
            logger.error(f"Disconnection error: {e}")
    
    def read_measurement(self) -> Optional[BodyMeasurement]:
        """Read measurement from device - to be implemented by subclasses"""
        raise NotImplementedError

class TanitaProtocol(DeviceProtocol):
    """Tanita MC-780MA protocol implementation"""
    
    def __init__(self, port: str):
        super().__init__(port, Config.TANITA_BAUDRATE)
        self.device_type = "tanita_mc780ma"
    
    def read_measurement(self) -> Optional[BodyMeasurement]:
        """Read measurement data from Tanita device"""
        if not self.is_connected or not self.serial_connection:
            return None
        
        try:
            # Check if data is available
            if self.serial_connection.in_waiting > 0:
                raw_data = ""
                start_time = time.time()
                
                # Read data with timeout
                while time.time() - start_time < 30:  # 30 second timeout
                    if self.serial_connection.in_waiting > 0:
                        chunk = self.serial_connection.read(self.serial_connection.in_waiting)
                        raw_data += chunk.decode('utf-8', errors='ignore')
                        
                        # Check if we have a complete message
                        if 'END' in raw_data or len(raw_data) > 500:
                            break
                    
                    time.sleep(0.1)
                
                if raw_data.strip():
                    return self._parse_tanita_data(raw_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Tanita read error: {e}")
            return None
    
    def _parse_tanita_data(self, raw_data: str) -> Optional[BodyMeasurement]:
        """Parse Tanita data format"""
        try:
            measurement = BodyMeasurement()
            measurement.device_id = f"tanita_{self.port.replace('/', '_')}"
            measurement.device_type = self.device_type
            measurement.measurement_uuid = str(uuid.uuid4())
            measurement.measurement_timestamp = datetime.now()
            measurement.raw_data = raw_data
            
            lines = raw_data.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Parse different data fields
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().upper()
                    value = value.strip()
                    
                    try:
                        if key == 'ID':
                            measurement.customer_phone = value
                        elif key == 'WT' or key == 'WEIGHT':
                            measurement.weight_kg = float(value.replace('kg', ''))
                        elif key == 'BF' or key == 'BODY_FAT':
                            measurement.body_fat_percent = float(value.replace('%', ''))
                        elif key == 'MM' or key == 'MUSCLE_MASS':
                            measurement.muscle_mass_kg = float(value.replace('kg', ''))
                        elif key == 'BM' or key == 'BONE_MASS':
                            measurement.bone_mass_kg = float(value.replace('kg', ''))
                        elif key == 'TBW' or key == 'TOTAL_BODY_WATER':
                            measurement.total_body_water_percent = float(value.replace('%', ''))
                        elif key == 'VF' or key == 'VISCERAL_FAT':
                            measurement.visceral_fat_rating = int(value)
                        elif key == 'MA' or key == 'METABOLIC_AGE':
                            measurement.metabolic_age = int(value)
                        elif key == 'BMR':
                            measurement.bmr_kcal = int(value.replace('kcal', ''))
                        elif key == 'BMI':
                            measurement.bmi = float(value)
                        elif key == 'HEIGHT':
                            measurement.height_cm = float(value.replace('cm', ''))
                    except ValueError as e:
                        logger.warning(f"Could not parse {key}={value}: {e}")
            
            # Validate measurement
            errors = measurement.validate()
            if errors:
                logger.warning(f"Measurement validation errors: {errors}")
                measurement.processing_notes = "; ".join(errors)
            
            if measurement.customer_phone and measurement.weight_kg > 0:
                return measurement
            
            return None
            
        except Exception as e:
            logger.error(f"Tanita parsing error: {e}")
            return None

class InBodyProtocol(DeviceProtocol):
    """InBody device protocol implementation"""
    
    def __init__(self, port: str):
        super().__init__(port, Config.INBODY_BAUDRATE)
        self.device_type = "inbody_270"
    
    def read_measurement(self) -> Optional[BodyMeasurement]:
        """Read measurement data from InBody device"""
        if not self.is_connected or not self.serial_connection:
            return None
        
        try:
            # InBody specific reading logic
            if self.serial_connection.in_waiting > 0:
                raw_data = ""
                start_time = time.time()
                
                while time.time() - start_time < 30:
                    if self.serial_connection.in_waiting > 0:
                        chunk = self.serial_connection.read(self.serial_connection.in_waiting)
                        raw_data += chunk.decode('utf-8', errors='ignore')
                        
                        if '\r\n\r\n' in raw_data or len(raw_data) > 500:
                            break
                    
                    time.sleep(0.1)
                
                if raw_data.strip():
                    return self._parse_inbody_data(raw_data)
            
            return None
            
        except Exception as e:
            logger.error(f"InBody read error: {e}")
            return None
    
    def _parse_inbody_data(self, raw_data: str) -> Optional[BodyMeasurement]:
        """Parse InBody data format"""
        try:
            measurement = BodyMeasurement()
            measurement.device_id = f"inbody_{self.port.replace('/', '_')}"
            measurement.device_type = self.device_type
            measurement.measurement_uuid = str(uuid.uuid4())
            measurement.measurement_timestamp = datetime.now()
            measurement.raw_data = raw_data
            
            # InBody parsing logic (simplified)
            lines = raw_data.strip().split('\n')
            
            for line in lines:
                if 'ID:' in line:
                    measurement.customer_phone = line.split(':', 1)[1].strip()
                elif 'Weight:' in line:
                    weight_str = line.split(':', 1)[1].strip()
                    measurement.weight_kg = float(weight_str.replace('kg', ''))
                elif 'BodyFat:' in line:
                    bf_str = line.split(':', 1)[1].strip()
                    measurement.body_fat_percent = float(bf_str.replace('%', ''))
                elif 'MuscleMass:' in line:
                    mm_str = line.split(':', 1)[1].strip()
                    measurement.skeletal_muscle_mass_kg = float(mm_str.replace('kg', ''))
                # Add more InBody specific parsing...
            
            # Calculate BMI if height is available
            if measurement.weight_kg > 0 and measurement.height_cm > 0:
                measurement.bmi = measurement.weight_kg / ((measurement.height_cm / 100) ** 2)
            
            if measurement.customer_phone and measurement.weight_kg > 0:
                return measurement
            
            return None
            
        except Exception as e:
            logger.error(f"InBody parsing error: {e}")
            return None

class DeviceManager:
    """Manages multiple body composition devices"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.devices: Dict[str, DeviceProtocol] = {}
        self.measurement_queue = queue.Queue()
        self.monitoring_active = False
        self.monitor_thread = None
    
    def auto_detect_devices(self) -> Dict[str, str]:
        """Auto-detect connected devices"""
        detected_devices = {}
        
        # Scan USB ports
        usb_ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
        
        for port in usb_ports:
            try:
                # Test connection
                test_serial = serial.Serial(port, 9600, timeout=1)
                time.sleep(0.5)
                
                # Send identification command
                test_serial.write(b'ID\r\n')
                time.sleep(1)
                
                response = ""
                if test_serial.in_waiting > 0:
                    response = test_serial.read(test_serial.in_waiting).decode('utf-8', errors='ignore')
                
                test_serial.close()
                
                # Identify device type based on response
                response_lower = response.lower()
                if 'tanita' in response_lower or 'mc-780' in response_lower:
                    detected_devices[port] = 'tanita'
                elif 'inbody' in response_lower:
                    detected_devices[port] = 'inbody'
                else:
                    # Try to identify by default behavior
                    detected_devices[port] = 'unknown'
                
                logger.info(f"Detected device on {port}: {detected_devices[port]}")
                
            except Exception as e:
                logger.debug(f"No device or error on {port}: {e}")
        
        return detected_devices
    
    def connect_devices(self):
        """Connect to all detected devices"""
        detected = self.auto_detect_devices()
        
        for port, device_type in detected.items():
            try:
                if device_type == 'tanita':
                    device = TanitaProtocol(port)
                elif device_type == 'inbody':
                    device = InBodyProtocol(port)
                else:
                    # Default to Tanita protocol for unknown devices
                    device = TanitaProtocol(port)
                
                if device.connect():
                    device_id = f"{device_type}_{port.replace('/', '_')}"
                    self.devices[device_id] = device
                    
                    # Update device status in database
                    status = DeviceStatus(
                        device_id=device_id,
                        device_type=device.device_type,
                        serial_port=port,
                        connection_status='connected',
                        last_heartbeat=datetime.now()
                    )
                    self.db_manager.update_device_status(status)
                    
                    logger.info(f"Connected to {device_type} device: {device_id}")
                else:
                    logger.error(f"Failed to connect to {device_type} on {port}")
                    
            except Exception as e:
                logger.error(f"Error connecting to device on {port}: {e}")
    
    def start_monitoring(self):
        """Start monitoring devices for measurements"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self._monitor_devices, daemon=True)
        self.monitor_thread.start()
        logger.info("Device monitoring started")
    
    def stop_monitoring(self):
        """Stop monitoring devices"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join()
        logger.info("Device monitoring stopped")
    
    def _monitor_devices(self):
        """Monitor devices for incoming measurements"""
        while self.monitoring_active:
            try:
                for device_id, device in self.devices.items():
                    if device.is_connected:
                        measurement = device.read_measurement()
                        if measurement:
                            self.measurement_queue.put(measurement)
                            logger.info(f"New measurement from {device_id}: {measurement.customer_phone}")
                    else:
                        # Try to reconnect
                        if device.connect():
                            logger.info(f"Reconnected to device: {device_id}")
                
                time.sleep(1)  # Check every second
                
            except Exception as e:
                logger.error(f"Device monitoring error: {e}")
                time.sleep(5)
    
    def get_measurement(self, timeout: float = None) -> Optional[BodyMeasurement]:
        """Get next measurement from queue"""
        try:
            return self.measurement_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def disconnect_all(self):
        """Disconnect all devices"""
        for device_id, device in self.devices.items():
            device.disconnect()
        self.devices.clear()