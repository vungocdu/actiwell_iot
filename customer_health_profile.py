#!/usr/bin/env python3
"""
Customer Health Profile Management System for Body Composition Gateway
Comprehensive health tracking, goal setting, and personalized health management
"""

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import uuid
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import hashlib
import secrets

# Configure logging
logger = logging.getLogger(__name__)

class HealthGoalType(Enum):
    """Types of health goals"""
    WEIGHT_LOSS = "weight_loss"
    WEIGHT_GAIN = "weight_gain"
    MUSCLE_GAIN = "muscle_gain"
    FAT_LOSS = "fat_loss"
    FITNESS_IMPROVEMENT = "fitness_improvement"
    HEALTH_MAINTENANCE = "health_maintenance"
    BODY_RECOMPOSITION = "body_recomposition"

class HealthRiskLevel(Enum):
    """Health risk assessment levels"""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"

class GoalStatus(Enum):
    """Goal progress status"""
    ACTIVE = "active"
    ACHIEVED = "achieved"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class ActivityLevel(Enum):
    """Physical activity levels"""
    SEDENTARY = "sedentary"
    LIGHTLY_ACTIVE = "lightly_active"
    MODERATELY_ACTIVE = "moderately_active"
    VERY_ACTIVE = "very_active"
    EXTREMELY_ACTIVE = "extremely_active"

@dataclass
class PersonalInfo:
    """Personal information for health calculations"""
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None  # M, F, Other
    height_cm: Optional[float] = None
    activity_level: Optional[ActivityLevel] = None
    occupation: Optional[str] = None
    medical_conditions: List[str] = field(default_factory=list)
    medications: List[str] = field(default_factory=list)
    allergies: List[str] = field(default_factory=list)
    
    @property
    def age(self) -> Optional[int]:
        """Calculate current age"""
        if self.date_of_birth:
            today = date.today()
            return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return None

@dataclass
class HealthGoal:
    """Health goal definition and tracking"""
    id: str
    goal_type: HealthGoalType
    title: str
    description: str
    target_value: float
    target_unit: str
    current_value: Optional[float] = None
    start_date: datetime = field(default_factory=datetime.now)
    target_date: Optional[datetime] = None
    status: GoalStatus = GoalStatus.ACTIVE
    progress_percent: float = 0.0
    milestones: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def calculate_progress(self, starting_value: Optional[float] = None) -> float:
        """Calculate progress percentage towards goal"""
        if not self.current_value or not starting_value:
            return 0.0
        
        if self.goal_type in [HealthGoalType.WEIGHT_LOSS, HealthGoalType.FAT_LOSS]:
            # For loss goals, progress is reduction from start
            total_needed = starting_value - self.target_value
            achieved = starting_value - self.current_value
            progress = (achieved / total_needed) * 100 if total_needed > 0 else 0
        else:
            # For gain goals, progress is increase from start
            total_needed = self.target_value - starting_value
            achieved = self.current_value - starting_value
            progress = (achieved / total_needed) * 100 if total_needed > 0 else 0
        
        self.progress_percent = max(0, min(100, progress))
        return self.progress_percent
    
    def add_milestone(self, description: str, target_date: datetime, achieved: bool = False):
        """Add a milestone to the goal"""
        milestone = {
            'id': str(uuid.uuid4()),
            'description': description,
            'target_date': target_date.isoformat(),
            'achieved': achieved,
            'achieved_date': None
        }
        self.milestones.append(milestone)
    
    def mark_milestone_achieved(self, milestone_id: str):
        """Mark a milestone as achieved"""
        for milestone in self.milestones:
            if milestone['id'] == milestone_id:
                milestone['achieved'] = True
                milestone['achieved_date'] = datetime.now().isoformat()
                break

@dataclass
class HealthAssessment:
    """Comprehensive health assessment result"""
    assessment_date: datetime
    bmi_category: str
    body_fat_category: str
    visceral_fat_category: str
    overall_health_score: int  # 0-100
    risk_level: HealthRiskLevel
    risk_factors: List[str]
    health_age: Optional[int]  # Biological age based on health metrics
    recommendations: List[str]
    strengths: List[str]
    areas_for_improvement: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/API"""
        return {
            'assessment_date': self.assessment_date.isoformat(),
            'bmi_category': self.bmi_category,
            'body_fat_category': self.body_fat_category,
            'visceral_fat_category': self.visceral_fat_category,
            'overall_health_score': self.overall_health_score,
            'risk_level': self.risk_level.value,
            'risk_factors': self.risk_factors,
            'health_age': self.health_age,
            'recommendations': self.recommendations,
            'strengths': self.strengths,
            'areas_for_improvement': self.areas_for_improvement
        }

@dataclass
class NutritionProfile:
    """Nutritional needs and tracking"""
    daily_calorie_needs: Optional[int] = None
    protein_needs_g: Optional[float] = None
    carb_needs_g: Optional[float] = None
    fat_needs_g: Optional[float] = None
    water_needs_l: Optional[float] = None
    dietary_restrictions: List[str] = field(default_factory=list)
    preferred_foods: List[str] = field(default_factory=list)
    avoided_foods: List[str] = field(default_factory=list)
    
    def calculate_needs(self, weight_kg: float, height_cm: float, age: int, 
                       gender: str, activity_level: ActivityLevel, goal: HealthGoalType):
        """Calculate nutritional needs based on personal data and goals"""
        
        # Calculate BMR using Mifflin-St Jeor equation
        if gender.upper() == 'M':
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
        else:
            bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
        
        # Activity multipliers
        activity_multipliers = {
            ActivityLevel.SEDENTARY: 1.2,
            ActivityLevel.LIGHTLY_ACTIVE: 1.375,
            ActivityLevel.MODERATELY_ACTIVE: 1.55,
            ActivityLevel.VERY_ACTIVE: 1.725,
            ActivityLevel.EXTREMELY_ACTIVE: 1.9
        }
        
        tdee = bmr * activity_multipliers.get(activity_level, 1.2)
        
        # Adjust for goals
        if goal == HealthGoalType.WEIGHT_LOSS:
            self.daily_calorie_needs = int(tdee - 500)  # 500 cal deficit
        elif goal == HealthGoalType.WEIGHT_GAIN:
            self.daily_calorie_needs = int(tdee + 300)  # 300 cal surplus
        else:
            self.daily_calorie_needs = int(tdee)
        
        # Calculate macronutrient needs
        if goal == HealthGoalType.MUSCLE_GAIN:
            self.protein_needs_g = weight_kg * 2.0  # Higher protein for muscle gain
        else:
            self.protein_needs_g = weight_kg * 1.6  # Standard protein needs
        
        # Standard macro distribution
        protein_calories = self.protein_needs_g * 4
        fat_calories = self.daily_calorie_needs * 0.25  # 25% from fat
        carb_calories = self.daily_calorie_needs - protein_calories - fat_calories
        
        self.fat_needs_g = fat_calories / 9  # 9 calories per gram of fat
        self.carb_needs_g = carb_calories / 4  # 4 calories per gram of carbs
        
        # Water needs (general recommendation)
        self.water_needs_l = weight_kg * 0.035  # 35ml per kg body weight

@dataclass
class ExerciseProfile:
    """Exercise preferences and recommendations"""
    preferred_activities: List[str] = field(default_factory=list)
    available_equipment: List[str] = field(default_factory=list)
    time_availability: Dict[str, int] = field(default_factory=dict)  # minutes per day
    fitness_level: str = "beginner"  # beginner, intermediate, advanced
    limitations: List[str] = field(default_factory=list)
    current_routine: List[Dict[str, Any]] = field(default_factory=list)
    
    def generate_recommendations(self, goal: HealthGoalType, 
                               available_days: int = 3) -> List[Dict[str, Any]]:
        """Generate exercise recommendations based on goals and preferences"""
        recommendations = []
        
        if goal == HealthGoalType.WEIGHT_LOSS:
            recommendations.extend([
                {
                    'type': 'cardio',
                    'activity': 'Brisk Walking',
                    'duration_minutes': 30,
                    'frequency_per_week': 5,
                    'intensity': 'moderate',
                    'description': 'Low-impact cardio for fat burning'
                },
                {
                    'type': 'strength',
                    'activity': 'Circuit Training',
                    'duration_minutes': 25,
                    'frequency_per_week': 3,
                    'intensity': 'moderate',
                    'description': 'Full-body strength training to maintain muscle'
                }
            ])
        
        elif goal == HealthGoalType.MUSCLE_GAIN:
            recommendations.extend([
                {
                    'type': 'strength',
                    'activity': 'Weight Training',
                    'duration_minutes': 45,
                    'frequency_per_week': 4,
                    'intensity': 'high',
                    'description': 'Progressive overload for muscle hypertrophy'
                },
                {
                    'type': 'cardio',
                    'activity': 'Light Cardio',
                    'duration_minutes': 20,
                    'frequency_per_week': 2,
                    'intensity': 'low',
                    'description': 'Maintain cardiovascular health'
                }
            ])
        
        elif goal == HealthGoalType.FITNESS_IMPROVEMENT:
            recommendations.extend([
                {
                    'type': 'cardio',
                    'activity': 'Running or Cycling',
                    'duration_minutes': 30,
                    'frequency_per_week': 3,
                    'intensity': 'moderate-high',
                    'description': 'Improve cardiovascular fitness'
                },
                {
                    'type': 'strength',
                    'activity': 'Functional Training',
                    'duration_minutes': 30,
                    'frequency_per_week': 2,
                    'intensity': 'moderate',
                    'description': 'Improve overall functional strength'
                },
                {
                    'type': 'flexibility',
                    'activity': 'Yoga or Stretching',
                    'duration_minutes': 20,
                    'frequency_per_week': 2,
                    'intensity': 'low',
                    'description': 'Improve flexibility and mobility'
                }
            ])
        
        return recommendations

class HealthCalculations:
    """Health calculations and assessments"""
    
    @staticmethod
    def calculate_bmi(weight_kg: float, height_cm: float) -> float:
        """Calculate Body Mass Index"""
        height_m = height_cm / 100
        return weight_kg / (height_m ** 2)
    
    @staticmethod
    def categorize_bmi(bmi: float) -> str:
        """Categorize BMI value"""
        if bmi < 18.5:
            return "Underweight"
        elif bmi < 25:
            return "Normal weight"
        elif bmi < 30:
            return "Overweight"
        else:
            return "Obese"
    
    @staticmethod
    def categorize_body_fat(body_fat_percent: float, gender: str, age: int) -> str:
        """Categorize body fat percentage based on age and gender"""
        if gender.upper() == 'M':
            if age < 40:
                if body_fat_percent < 8:
                    return "Very Low"
                elif body_fat_percent < 20:
                    return "Normal"
                elif body_fat_percent < 25:
                    return "High"
                else:
                    return "Very High"
            else:  # 40+
                if body_fat_percent < 11:
                    return "Very Low"
                elif body_fat_percent < 22:
                    return "Normal"
                elif body_fat_percent < 28:
                    return "High"
                else:
                    return "Very High"
        else:  # Female
            if age < 40:
                if body_fat_percent < 21:
                    return "Very Low"
                elif body_fat_percent < 32:
                    return "Normal"
                elif body_fat_percent < 38:
                    return "High"
                else:
                    return "Very High"
            else:  # 40+
                if body_fat_percent < 23:
                    return "Very Low"
                elif body_fat_percent < 35:
                    return "Normal"
                elif body_fat_percent < 40:
                    return "High"
                else:
                    return "Very High"
    
    @staticmethod
    def categorize_visceral_fat(visceral_fat_rating: int) -> str:
        """Categorize visceral fat rating"""
        if visceral_fat_rating < 10:
            return "Normal"
        elif visceral_fat_rating < 15:
            return "High"
        else:
            return "Very High"
    
    @staticmethod
    def calculate_health_age(measurements: Dict[str, float], 
                           personal_info: PersonalInfo) -> Optional[int]:
        """Calculate biological/health age based on measurements"""
        if not personal_info.age:
            return None
        
        age_adjustments = 0
        actual_age = personal_info.age
        
        # BMI impact
        bmi = measurements.get('bmi')
        if bmi:
            if bmi < 18.5 or bmi > 30:
                age_adjustments += 5
            elif bmi > 25:
                age_adjustments += 2
            elif 20 <= bmi <= 22:
                age_adjustments -= 2
        
        # Body fat impact
        body_fat = measurements.get('body_fat_percent')
        if body_fat and personal_info.gender:
            bf_category = HealthCalculations.categorize_body_fat(
                body_fat, personal_info.gender, actual_age
            )
            if bf_category == "Very High":
                age_adjustments += 8
            elif bf_category == "High":
                age_adjustments += 4
            elif bf_category == "Normal":
                age_adjustments -= 1
        
        # Visceral fat impact
        visceral_fat = measurements.get('visceral_fat_rating')
        if visceral_fat:
            if visceral_fat >= 15:
                age_adjustments += 10
            elif visceral_fat >= 10:
                age_adjustments += 5
            else:
                age_adjustments -= 1
        
        # Muscle mass impact (approximate)
        muscle_mass = measurements.get('muscle_mass_kg')
        weight = measurements.get('weight_kg')
        if muscle_mass and weight:
            muscle_percentage = (muscle_mass / weight) * 100
            if muscle_percentage > 40:  # High muscle mass
                age_adjustments -= 3
            elif muscle_percentage < 25:  # Low muscle mass
                age_adjustments += 3
        
        return max(18, min(100, actual_age + age_adjustments))
    
    @staticmethod
    def calculate_health_score(measurements: Dict[str, float],
                             personal_info: PersonalInfo,
                             risk_factors: List[str]) -> int:
        """Calculate overall health score (0-100)"""
        base_score = 100
        
        # BMI deductions
        bmi = measurements.get('bmi')
        if bmi:
            if bmi < 18.5 or bmi > 35:
                base_score -= 25
            elif bmi > 30:
                base_score -= 15
            elif bmi > 25:
                base_score -= 8
            elif 18.5 <= bmi <= 24.9:
                base_score += 5
        
        # Body fat deductions
        body_fat = measurements.get('body_fat_percent')
        if body_fat and personal_info.gender and personal_info.age:
            bf_category = HealthCalculations.categorize_body_fat(
                body_fat, personal_info.gender, personal_info.age
            )
            if bf_category == "Very High":
                base_score -= 20
            elif bf_category == "High":
                base_score -= 10
            elif bf_category == "Normal":
                base_score += 5
        
        # Visceral fat deductions
        visceral_fat = measurements.get('visceral_fat_rating')
        if visceral_fat:
            if visceral_fat >= 15:
                base_score -= 20
            elif visceral_fat >= 10:
                base_score -= 10
            else:
                base_score += 5
        
        # Risk factor deductions
        base_score -= len(risk_factors) * 5
        
        # Age adjustments
        if personal_info.age:
            if personal_info.age > 65:
                base_score -= 5
            elif personal_info.age < 25:
                base_score += 5
        
        return max(0, min(100, base_score))

class CustomerHealthManager:
    """Main class for managing customer health profiles"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.health_calculations = HealthCalculations()
    
    async def create_customer_profile(self, customer_id: str, phone_number: str,
                                    personal_info: PersonalInfo) -> bool:
        """Create a new customer health profile"""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor()
            
            # Insert or update customer
            query = """
            INSERT INTO customers (
                id, phone, name, gender, date_of_birth, height_cm, 
                activity_level, medical_conditions, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                gender = VALUES(gender),
                date_of_birth = VALUES(date_of_birth),
                height_cm = VALUES(height_cm),
                activity_level = VALUES(activity_level),
                medical_conditions = VALUES(medical_conditions),
                updated_at = NOW()
            """
            
            params = (
                customer_id,
                phone_number,
                getattr(personal_info, 'name', None),
                personal_info.gender,
                personal_info.date_of_birth,
                personal_info.height_cm,
                personal_info.activity_level.value if personal_info.activity_level else None,
                json.dumps(personal_info.medical_conditions)
            )
            
            cursor.execute(query, params)
            connection.commit()
            
            cursor.close()
            self.db_manager.return_connection(connection)
            
            logger.info(f"Customer profile created/updated: {customer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating customer profile: {e}")
            return False
    
    async def update_personal_info(self, customer_id: str, 
                                 personal_info: PersonalInfo) -> bool:
        """Update customer personal information"""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor()
            
            query = """
            UPDATE customers SET
                gender = %s,
                date_of_birth = %s,
                height_cm = %s,
                activity_level = %s,
                medical_conditions = %s,
                medications = %s,
                allergies = %s,
                updated_at = NOW()
            WHERE id = %s
            """
            
            params = (
                personal_info.gender,
                personal_info.date_of_birth,
                personal_info.height_cm,
                personal_info.activity_level.value if personal_info.activity_level else None,
                json.dumps(personal_info.medical_conditions),
                json.dumps(personal_info.medications),
                json.dumps(personal_info.allergies),
                customer_id
            )
            
            cursor.execute(query, params)
            connection.commit()
            
            cursor.close()
            self.db_manager.return_connection(connection)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating personal info: {e}")
            return False
    
    async def set_health_goal(self, customer_id: str, goal: HealthGoal) -> bool:
        """Set a health goal for customer"""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor()
            
            # Check if table exists, create if not
            self._ensure_health_goals_table(cursor)
            
            query = """
            INSERT INTO customer_health_goals (
                id, customer_id, goal_type, title, description,
                target_value, target_unit, current_value,
                start_date, target_date, status, milestones,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            """
            
            params = (
                goal.id,
                customer_id,
                goal.goal_type.value,
                goal.title,
                goal.description,
                goal.target_value,
                goal.target_unit,
                goal.current_value,
                goal.start_date,
                goal.target_date,
                goal.status.value,
                json.dumps(goal.milestones)
            )
            
            cursor.execute(query, params)
            connection.commit()
            
            cursor.close()
            self.db_manager.return_connection(connection)
            
            logger.info(f"Health goal set for customer {customer_id}: {goal.title}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting health goal: {e}")
            return False
    
    async def update_goal_progress(self, customer_id: str, goal_id: str,
                                 current_value: float) -> bool:
        """Update progress on a health goal"""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor()
            
            # Get goal details
            cursor.execute("""
                SELECT target_value, goal_type, start_date
                FROM customer_health_goals
                WHERE id = %s AND customer_id = %s AND status = 'active'
            """, (goal_id, customer_id))
            
            goal_data = cursor.fetchone()
            if not goal_data:
                return False
            
            # Get starting value from first measurement after start date
            cursor.execute("""
                SELECT weight_kg, body_fat_percent, muscle_mass_kg
                FROM tanita_measurements
                WHERE customer_id = %s AND measurement_timestamp >= %s
                ORDER BY measurement_timestamp ASC
                LIMIT 1
            """, (customer_id, goal_data['start_date']))
            
            start_measurement = cursor.fetchone()
            
            # Calculate progress
            goal = HealthGoal(
                id=goal_id,
                goal_type=HealthGoalType(goal_data['goal_type']),
                title="",
                description="",
                target_value=goal_data['target_value'],
                target_unit="",
                current_value=current_value
            )
            
            starting_value = None
            if start_measurement:
                if goal.goal_type in [HealthGoalType.WEIGHT_LOSS, HealthGoalType.WEIGHT_GAIN]:
                    starting_value = start_measurement['weight_kg']
                elif goal.goal_type == HealthGoalType.FAT_LOSS:
                    starting_value = start_measurement['body_fat_percent']
                elif goal.goal_type == HealthGoalType.MUSCLE_GAIN:
                    starting_value = start_measurement['muscle_mass_kg']
            
            progress = goal.calculate_progress(starting_value)
            
            # Update goal
            cursor.execute("""
                UPDATE customer_health_goals SET
                    current_value = %s,
                    progress_percent = %s,
                    updated_at = NOW()
                WHERE id = %s AND customer_id = %s
            """, (current_value, progress, goal_id, customer_id))
            
            # Check if goal is achieved
            if progress >= 100:
                cursor.execute("""
                    UPDATE customer_health_goals SET
                        status = 'achieved'
                    WHERE id = %s AND customer_id = %s
                """, (goal_id, customer_id))
            
            connection.commit()
            cursor.close()
            self.db_manager.return_connection(connection)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating goal progress: {e}")
            return False
    
    async def perform_health_assessment(self, customer_id: str) -> Optional[HealthAssessment]:
        """Perform comprehensive health assessment for customer"""
        try:
            # Get customer data
            customer_data = await self._get_customer_data(customer_id)
            if not customer_data:
                return None
            
            personal_info = PersonalInfo(
                date_of_birth=customer_data.get('date_of_birth'),
                gender=customer_data.get('gender'),
                height_cm=customer_data.get('height_cm'),
                medical_conditions=json.loads(customer_data.get('medical_conditions', '[]'))
            )
            
            # Get latest measurements
            latest_measurements = await self._get_latest_measurements(customer_id)
            if not latest_measurements:
                return None
            
            # Perform assessments
            bmi_category = self.health_calculations.categorize_bmi(
                latest_measurements['bmi']
            ) if latest_measurements.get('bmi') else "Unknown"
            
            body_fat_category = "Unknown"
            if (latest_measurements.get('body_fat_percent') and 
                personal_info.gender and personal_info.age):
                body_fat_category = self.health_calculations.categorize_body_fat(
                    latest_measurements['body_fat_percent'],
                    personal_info.gender,
                    personal_info.age
                )
            
            visceral_fat_category = "Unknown"
            if latest_measurements.get('visceral_fat_rating'):
                visceral_fat_category = self.health_calculations.categorize_visceral_fat(
                    latest_measurements['visceral_fat_rating']
                )
            
            # Assess risk factors
            risk_factors = self._assess_risk_factors(latest_measurements, personal_info)
            
            # Calculate health age
            health_age = self.health_calculations.calculate_health_age(
                latest_measurements, personal_info
            )
            
            # Calculate health score
            health_score = self.health_calculations.calculate_health_score(
                latest_measurements, personal_info, risk_factors
            )
            
            # Determine risk level
            risk_level = self._determine_risk_level(risk_factors, health_score)
            
            # Generate recommendations
            recommendations = self._generate_health_recommendations(
                latest_measurements, personal_info, risk_factors
            )
            
            # Identify strengths and areas for improvement
            strengths, improvements = self._analyze_strengths_and_improvements(
                latest_measurements, personal_info
            )
            
            assessment = HealthAssessment(
                assessment_date=datetime.now(),
                bmi_category=bmi_category,
                body_fat_category=body_fat_category,
                visceral_fat_category=visceral_fat_category,
                overall_health_score=health_score,
                risk_level=risk_level,
                risk_factors=risk_factors,
                health_age=health_age,
                recommendations=recommendations,
                strengths=strengths,
                areas_for_improvement=improvements
            )
            
            # Store assessment
            await self._store_health_assessment(customer_id, assessment)
            
            return assessment
            
        except Exception as e:
            logger.error(f"Error performing health assessment: {e}")
            return None
    
    async def generate_nutrition_profile(self, customer_id: str, 
                                       goal_type: HealthGoalType) -> Optional[NutritionProfile]:
        """Generate personalized nutrition profile"""
        try:
            # Get customer data
            customer_data = await self._get_customer_data(customer_id)
            latest_measurements = await self._get_latest_measurements(customer_id)
            
            if not customer_data or not latest_measurements:
                return None
            
            personal_info = PersonalInfo(
                date_of_birth=customer_data.get('date_of_birth'),
                gender=customer_data.get('gender'),
                height_cm=customer_data.get('height_cm'),
                activity_level=ActivityLevel(customer_data.get('activity_level', 'moderately_active'))
            )
            
            if not all([personal_info.age, personal_info.gender, personal_info.height_cm]):
                return None
            
            profile = NutritionProfile()
            profile.calculate_needs(
                weight_kg=latest_measurements['weight_kg'],
                height_cm=personal_info.height_cm,
                age=personal_info.age,
                gender=personal_info.gender,
                activity_level=personal_info.activity_level,
                goal=goal_type
            )
            
            return profile
            
        except Exception as e:
            logger.error(f"Error generating nutrition profile: {e}")
            return None
    
    async def generate_exercise_profile(self, customer_id: str,
                                      goal_type: HealthGoalType) -> Optional[ExerciseProfile]:
        """Generate personalized exercise profile"""
        try:
            # Get customer fitness level assessment
            latest_measurements = await self._get_latest_measurements(customer_id)
            if not latest_measurements:
                return None
            
            profile = ExerciseProfile()
            
            # Determine fitness level based on measurements
            if latest_measurements.get('health_score'):
                score = latest_measurements['health_score']
                if score >= 80:
                    profile.fitness_level = "advanced"
                elif score >= 60:
                    profile.fitness_level = "intermediate"
                else:
                    profile.fitness_level = "beginner"
            
            # Generate recommendations
            recommendations = profile.generate_recommendations(goal_type)
            profile.current_routine = recommendations
            
            return profile
            
        except Exception as e:
            logger.error(f"Error generating exercise profile: {e}")
            return None
    
    def _ensure_health_goals_table(self, cursor):
        """Ensure health goals table exists"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_health_goals (
                id VARCHAR(36) PRIMARY KEY,
                customer_id BIGINT NOT NULL,
                goal_type VARCHAR(50) NOT NULL,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                target_value DECIMAL(10,2) NOT NULL,
                target_unit VARCHAR(20) NOT NULL,
                current_value DECIMAL(10,2),
                start_date DATETIME NOT NULL,
                target_date DATETIME,
                status ENUM('active', 'achieved', 'paused', 'cancelled', 'expired') DEFAULT 'active',
                progress_percent DECIMAL(5,2) DEFAULT 0,
                milestones JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_customer_id (customer_id),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_health_assessments (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                customer_id BIGINT NOT NULL,
                assessment_data JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_customer_id (customer_id),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
    
    async def _get_customer_data(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Get customer personal data"""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT * FROM customers WHERE id = %s
            """, (customer_id,))
            
            result = cursor.fetchone()
            
            cursor.close()
            self.db_manager.return_connection(connection)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting customer data: {e}")
            return None
    
    async def _get_latest_measurements(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Get latest measurements for customer"""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT * FROM tanita_measurements
                WHERE customer_id = %s
                ORDER BY measurement_timestamp DESC
                LIMIT 1
            """, (customer_id,))
            
            result = cursor.fetchone()
            
            cursor.close()
            self.db_manager.return_connection(connection)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting latest measurements: {e}")
            return None
    
    def _assess_risk_factors(self, measurements: Dict[str, Any],
                           personal_info: PersonalInfo) -> List[str]:
        """Assess health risk factors"""
        risk_factors = []
        
        # BMI-based risks
        bmi = measurements.get('bmi')
        if bmi:
            if bmi >= 30:
                risk_factors.append("Obesity")
            elif bmi >= 25:
                risk_factors.append("Overweight")
            elif bmi < 18.5:
                risk_factors.append("Underweight")
        
        # Body fat risks
        if (measurements.get('body_fat_percent') and 
            personal_info.gender and personal_info.age):
            bf_category = self.health_calculations.categorize_body_fat(
                measurements['body_fat_percent'],
                personal_info.gender,
                personal_info.age
            )
            if bf_category in ["High", "Very High"]:
                risk_factors.append("Elevated Body Fat")
        
        # Visceral fat risks
        visceral_fat = measurements.get('visceral_fat_rating')
        if visceral_fat:
            if visceral_fat >= 15:
                risk_factors.append("High Visceral Fat")
            elif visceral_fat >= 10:
                risk_factors.append("Elevated Visceral Fat")
        
        # Age-related risks
        if personal_info.age and personal_info.age > 65:
            risk_factors.append("Age-Related Health Risks")
        
        # Medical condition risks
        if personal_info.medical_conditions:
            for condition in personal_info.medical_conditions:
                if condition.lower() in ['diabetes', 'hypertension', 'heart disease']:
                    risk_factors.append(f"Chronic Condition: {condition}")
        
        return risk_factors
    
    def _determine_risk_level(self, risk_factors: List[str], 
                            health_score: int) -> HealthRiskLevel:
        """Determine overall health risk level"""
        critical_conditions = ['diabetes', 'heart disease', 'high visceral fat']
        
        # Check for critical conditions
        for factor in risk_factors:
            if any(condition in factor.lower() for condition in critical_conditions):
                return HealthRiskLevel.CRITICAL
        
        # Based on health score and number of risk factors
        if health_score < 40 or len(risk_factors) > 4:
            return HealthRiskLevel.HIGH
        elif health_score < 60 or len(risk_factors) > 2:
            return HealthRiskLevel.MODERATE
        else:
            return HealthRiskLevel.LOW
    
    def _generate_health_recommendations(self, measurements: Dict[str, Any],
                                       personal_info: PersonalInfo,
                                       risk_factors: List[str]) -> List[str]:
        """Generate personalized health recommendations"""
        recommendations = []
        
        # BMI-based recommendations
        bmi = measurements.get('bmi')
        if bmi:
            if bmi >= 30:
                recommendations.append("Consult with a healthcare provider about weight management strategies")
                recommendations.append("Consider a structured weight loss program with diet and exercise")
            elif bmi >= 25:
                recommendations.append("Focus on gradual weight loss through balanced nutrition and regular exercise")
            elif bmi < 18.5:
                recommendations.append("Consider healthy weight gain through proper nutrition and strength training")
        
        # Body composition recommendations
        if "Elevated Body Fat" in risk_factors:
            recommendations.append("Incorporate cardiovascular exercise and strength training to improve body composition")
        
        if "High Visceral Fat" in risk_factors or "Elevated Visceral Fat" in risk_factors:
            recommendations.append("Reduce visceral fat through aerobic exercise and dietary modifications")
            recommendations.append("Limit processed foods and added sugars in your diet")
        
        # General health recommendations
        recommendations.extend([
            "Maintain regular measurement tracking to monitor progress",
            "Stay hydrated with at least 8 glasses of water daily",
            "Aim for 7-9 hours of quality sleep each night",
            "Include stress management techniques in your daily routine"
        ])
        
        # Age-specific recommendations
        if personal_info.age and personal_info.age > 50:
            recommendations.append("Consider calcium and vitamin D supplementation for bone health")
            recommendations.append("Include balance and flexibility exercises to prevent falls")
        
        return recommendations
    
    def _analyze_strengths_and_improvements(self, measurements: Dict[str, Any],
                                          personal_info: PersonalInfo) -> Tuple[List[str], List[str]]:
        """Analyze health strengths and areas for improvement"""
        strengths = []
        improvements = []
        
        # BMI analysis
        bmi = measurements.get('bmi')
        if bmi and 18.5 <= bmi <= 24.9:
            strengths.append("Healthy BMI range")
        elif bmi:
            improvements.append("BMI optimization")
        
        # Body composition analysis
        if measurements.get('body_fat_percent') and personal_info.gender and personal_info.age:
            bf_category = self.health_calculations.categorize_body_fat(
                measurements['body_fat_percent'],
                personal_info.gender,
                personal_info.age
            )
            if bf_category == "Normal":
                strengths.append("Healthy body fat percentage")
            else:
                improvements.append("Body fat optimization")
        
        # Visceral fat analysis
        visceral_fat = measurements.get('visceral_fat_rating')
        if visceral_fat:
            if visceral_fat < 10:
                strengths.append("Healthy visceral fat levels")
            else:
                improvements.append("Visceral fat reduction")
        
        # Muscle mass analysis
        muscle_mass = measurements.get('muscle_mass_kg')
        weight = measurements.get('weight_kg')
        if muscle_mass and weight:
            muscle_percentage = (muscle_mass / weight) * 100
            if muscle_percentage > 35:
                strengths.append("Good muscle mass")
            elif muscle_percentage < 25:
                improvements.append("Muscle mass development")
        
        return strengths, improvements
    
    async def _store_health_assessment(self, customer_id: str, 
                                     assessment: HealthAssessment) -> bool:
        """Store health assessment in database"""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor()
            
            self._ensure_health_goals_table(cursor)
            
            cursor.execute("""
                INSERT INTO customer_health_assessments (customer_id, assessment_data)
                VALUES (%s, %s)
            """, (customer_id, json.dumps(assessment.to_dict())))
            
            connection.commit()
            cursor.close()
            self.db_manager.return_connection(connection)
            
            return True
            
        except Exception as e:
            logger.error(f"Error storing health assessment: {e}")
            return False

# Example usage
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    print("Customer Health Profile Management System")
    print("========================================")
    print("Features:")
    print("- Comprehensive health profile management")
    print("- Personalized goal setting and tracking")
    print("- Advanced health risk assessment")
    print("- Nutrition and exercise recommendations")
    print("- Health age calculation")
    print("- Progress monitoring and analytics")
    print("- Medical condition consideration")
    print("- Automated health insights")
    
    # Example personal info
    personal_info = PersonalInfo(
        date_of_birth=date(1990, 5, 15),
        gender="M",
        height_cm=175.0,
        activity_level=ActivityLevel.MODERATELY_ACTIVE,
        medical_conditions=[]
    )
    
    print(f"\nExample: Age calculated as {personal_info.age} years")
    
    # Example goal
    goal = HealthGoal(
        id=str(uuid.uuid4()),
        goal_type=HealthGoalType.WEIGHT_LOSS,
        title="Lose 10kg",
        description="Healthy weight loss goal",
        target_value=70.0,
        target_unit="kg",
        current_value=80.0,
        target_date=datetime.now() + timedelta(days=120)
    )
    
    progress = goal.calculate_progress(starting_value=80.0)
    print(f"Goal progress: {progress}%")
    
    print("\nModule ready for integration with Body Composition Gateway")