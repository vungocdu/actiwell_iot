# ====================================================================================
# 6. ACTIWELL API INTEGRATION (actiwell_api.py)
# ====================================================================================

class ActiwellAPI:
    """Actiwell API integration manager"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.api_url = Config.ACTIWELL_API_URL
        self.api_key = Config.ACTIWELL_API_KEY
        self.location_id = Config.ACTIWELL_LOCATION_ID
        
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'X-Location-ID': self.location_id
        }
    
    def find_customer_by_phone(self, phone: str) -> Optional[Dict]:
        """Find customer in Actiwell by phone number"""
        try:
            # Clean phone number
            clean_phone = phone.replace('+84', '0').replace('-', '').replace(' ', '')
            
            # Check local cache first
            connection = self.db_manager.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            query = """
                SELECT actiwell_customer_id, customer_name, customer_email
                FROM customer_mapping 
                WHERE phone_number = %s
                AND last_updated > DATE_SUB(NOW(), INTERVAL 1 DAY)
            """
            cursor.execute(query, (clean_phone,))
            cached_result = cursor.fetchone()
            
            cursor.close()
            connection.close()
            
            if cached_result:
                return {
                    'id': cached_result['actiwell_customer_id'],
                    'name': cached_result['customer_name'],
                    'email': cached_result['customer_email'],
                    'phone': phone
                }
            
            # Query Actiwell API
            url = f"{self.api_url}/api/customers/search"
            params = {'phone': clean_phone}
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get('success') and data.get('data'):
                customer = data['data'][0]
                
                # Cache the result
                self._cache_customer(clean_phone, customer)
                
                return customer
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding customer by phone {phone}: {e}")
            return None
    
    def _cache_customer(self, phone: str, customer: Dict):
        """Cache customer information"""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor()
            
            query = """
                INSERT INTO customer_mapping (
                    phone_number, actiwell_customer_id, customer_name, customer_email
                ) VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    actiwell_customer_id = VALUES(actiwell_customer_id),
                    customer_name = VALUES(customer_name),
                    customer_email = VALUES(customer_email),
                    last_updated = CURRENT_TIMESTAMP
            """
            
            cursor.execute(query, (
                phone, customer['id'], customer.get('name'), customer.get('email')
            ))
            
            connection.commit()
            cursor.close()
            connection.close()
            
        except Exception as e:
            logger.error(f"Error caching customer: {e}")
    
    def sync_measurement_to_actiwell(self, measurement: BodyMeasurement) -> bool:
        """Sync measurement to Actiwell system"""
        try:
            # Find customer
            customer = self.find_customer_by_phone(measurement.customer_phone)
            if not customer:
                logger.warning(f"Customer not found for phone: {measurement.customer_phone}")
                return False
            
            # Prepare payload
            payload = {
                'customer_id': customer['id'],
                'location_id': self.location_id,
                'measurement_date': measurement.measurement_timestamp.isoformat(),
                'device_type': measurement.device_type,
                'device_id': measurement.device_id,
                'measurement_uuid': measurement.measurement_uuid,
                'body_composition': {
                    'weight_kg': measurement.weight_kg,
                    'height_cm': measurement.height_cm,
                    'bmi': measurement.bmi,
                    'body_fat_percent': measurement.body_fat_percent,
                    'muscle_mass_kg': measurement.muscle_mass_kg,
                    'bone_mass_kg': measurement.bone_mass_kg,
                    'total_body_water_percent': measurement.total_body_water_percent,
                    'protein_percent': measurement.protein_percent,
                    'mineral_percent': measurement.mineral_percent,
                    'visceral_fat_rating': measurement.visceral_fat_rating,
                    'subcutaneous_fat_percent': measurement.subcutaneous_fat_percent,
                    'skeletal_muscle_mass_kg': measurement.skeletal_muscle_mass_kg,
                    'bmr_kcal': measurement.bmr_kcal,
                    'metabolic_age': measurement.metabolic_age,
                    'measurement_quality': measurement.measurement_quality
                },
                'segmental_analysis': {
                    'right_arm_muscle_kg': measurement.right_arm_muscle_kg,
                    'left_arm_muscle_kg': measurement.left_arm_muscle_kg,
                    'trunk_muscle_kg': measurement.trunk_muscle_kg,
                    'right_leg_muscle_kg': measurement.right_leg_muscle_kg,
                    'left_leg_muscle_kg': measurement.left_leg_muscle_kg
                } if measurement.right_arm_muscle_kg > 0 else None
            }
            
            # Send to Actiwell
            url = f"{self.api_url}/api/body-composition-measurements"
            response = requests.post(url, headers=self.headers, json=payload, timeout=15)
            response.raise_for_status()
            
            result = response.json()
            if result.get('success'):
                logger.info(f"Successfully synced measurement to Actiwell: {measurement.measurement_uuid}")
                return True
            else:
                logger.error(f"Actiwell sync failed: {result.get('message', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.error(f"Error syncing measurement to Actiwell: {e}")
            return False