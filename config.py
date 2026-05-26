import os

class Config:
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'smart_faculty_attendance_secret_key_13579')
    
    # Base directory of the app
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # SQLAlchemy configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "attendance.db")}?timeout=30')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    from sqlalchemy.pool import NullPool
    SQLALCHEMY_ENGINE_OPTIONS = {
        'poolclass': NullPool,
        'connect_args': {
            'timeout': 30
        }
    }
    
    # Timezone settings (standardized to India Standard Time)
    TIMEZONE = 'Asia/Kolkata'
    
    # File storage configuration
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB limit
    
    # Default Campus Coordinates (Dibrugarh, Assam, India)
    CAMPUS_LATITUDE = 27.475807921264003
    CAMPUS_LONGITUDE = 94.55106863579525
    CAMPUS_RADIUS_METERS = 100.0  # College campus radius
    
    # Timetable validation window settings
    START_WINDOW_BEFORE_MINS = 5   # Can mark 5 mins before class start
    END_WINDOW_AFTER_MINS = 15     # Can mark up to 15 mins after class starts
    
    # Debug / Development Mock settings
    # Set to True to allow the frontend to present a "Mock Location" slider/toggle for testing
    DEBUG_MOCK_LOCATION = True
