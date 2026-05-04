import os
import logging
import secrets
from urllib.parse import quote_plus
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


def _db_uri(echo=False):
    return (
        f"mysql+pymysql://{quote_plus(os.environ.get('DB_USER', 'root'))}:"
        f"{quote_plus(os.environ.get('DB_PASSWORD', ''))}@"
        f"{os.environ.get('DB_HOST', 'localhost')}:"
        f"{os.environ.get('DB_PORT', '3306')}/"
        f"{os.environ.get('DB_NAME', 'smart_attendance')}"
        f"?charset=utf8mb4"
    )


class Config:
    # ── Core ──────────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # ── Database ──────────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = _db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': 300,
        'pool_pre_ping': True,
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,
    }

    # ── Session / Cookies ─────────────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    REMEMBER_COOKIE_SAMESITE = 'Lax'

    # ── CSRF ──────────────────────────────────────────────────────────────────
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour

    # ── Mail ──────────────────────────────────────────────────────────────────
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME')
    MAIL_MAX_EMAILS = 10

    # ── Uploads ───────────────────────────────────────────────────────────────
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'faces')
    PRIVATE_UPLOAD_FOLDER = os.path.join(BASE_DIR, 'instance', 'uploads')
    CONTENT_UPLOAD_FOLDER = os.path.join(PRIVATE_UPLOAD_FOLDER, 'content')
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB

    # ── App-specific ──────────────────────────────────────────────────────────
    LOW_ATTENDANCE_THRESHOLD = int(os.environ.get('LOW_ATTENDANCE_THRESHOLD', 75))
    COLLEGE_LAT = float(os.environ.get('COLLEGE_LAT', 27.7172))   # default: Kathmandu
    COLLEGE_LNG = float(os.environ.get('COLLEGE_LNG', 85.3240))
    COLLEGE_NAME = os.environ.get('COLLEGE_NAME', 'College')
    FACE_RECOGNITION_TOLERANCE = float(os.environ.get('FACE_RECOGNITION_TOLERANCE', 0.5))
    EAR_THRESHOLD = 0.25
    EAR_CONSEC_FRAMES = 2
    REQUIRED_BLINKS = 1
    LIVENESS_STATE_TTL_SECONDS = int(os.environ.get('LIVENESS_STATE_TTL_SECONDS', 600))

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATELIMIT_STORAGE_URI = (
        os.environ.get('RATELIMIT_STORAGE_URI')
        or os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')
    )
    RATELIMIT_DEFAULT = '200 per day; 50 per hour'
    RATELIMIT_HEADERS_ENABLED = True

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_DIR = os.path.join(BASE_DIR, 'logs')


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    SQLALCHEMY_ECHO = False
    WTF_CSRF_ENABLED = True
    LOG_LEVEL = 'DEBUG'


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    # Enforce strong key in prod
    SECRET_KEY = os.environ['SECRET_KEY']
    LOG_LEVEL = 'WARNING'
    # Tighter pool for production
    SQLALCHEMY_ENGINE_OPTIONS = {
        **Config.SQLALCHEMY_ENGINE_OPTIONS,
        'pool_size': 20,
        'max_overflow': 40,
    }


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SESSION_COOKIE_SECURE = False


config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}


def get_config():
    env = os.environ.get('FLASK_ENV', 'development')
    return config_map.get(env, DevelopmentConfig)
