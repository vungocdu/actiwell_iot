# /opt/actiwell_iot/actiwell_backend/api/auth_routes.py

import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, current_app
from config import Config

auth_bp = Blueprint('auth_bp', __name__)

def token_required(f):
    """
    Decorator để yêu cầu JWT authentication.
    Được định nghĩa ở đây để các blueprints khác có thể import và sử dụng.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            try:
                token = request.headers['Authorization'].split(" ")[1]
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            # Sử dụng secret key từ app config
            data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
            request.current_user = data.get('user')
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token is invalid'}), 401
        
        return f(*args, **kwargs)
    return decorated

@auth_bp.route('/login', methods=['POST'])
def login():
    """Authentication endpoint"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Simple authentication
        if username == 'admin' and password == 'actiwell123':
            token = jwt.encode({
                'user': username,
                'exp': datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRE_HOURS)
            }, current_app.config['SECRET_KEY'], algorithm='HS256')
            
            return jsonify({
                'success': True,
                'token': token,
                'user': username,
                'expires_at': (datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRE_HOURS)).isoformat()
            })
        
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500