import os
import logging
import secrets
from urllib.parse import quote_plus
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


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
        'pool_recycle': int(os.environ.get('DB_POOL_RECYCLE', 300)),
        'pool_pre_ping': os.environ.get('DB_POOL_PRE_PING', 'True') == 'True',
        'pool_size': int(os.environ.get('DB_POOL_SIZE', 10)),
        'max_overflow': int(os.environ.get('DB_MAX_OVERFLOW', 20)),
        'pool_timeout': int(os.environ.get('DB_POOL_TIMEOUT', 30)),
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
    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER',
        os.path.join(BASE_DIR, 'static', 'uploads', 'faces'),
    )
    PRIVATE_UPLOAD_FOLDER = os.environ.get(
        'PRIVATE_UPLOAD_FOLDER',
        os.path.join(BASE_DIR, 'instance', 'uploads'),
    )
    CONTENT_UPLOAD_FOLDER = os.environ.get(
        'CONTENT_UPLOAD_FOLDER',
        os.path.join(PRIVATE_UPLOAD_FOLDER, 'content'),
    )
    ASSIGNMENT_UPLOAD_FOLDER = os.environ.get(
        'ASSIGNMENT_UPLOAD_FOLDER',
        os.path.join(PRIVATE_UPLOAD_FOLDER, 'assignment_submissions'),
    )
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 10 * 1024 * 1024))

    # ── App-specific ──────────────────────────────────────────────────────────
    LOW_ATTENDANCE_THRESHOLD = int(os.environ.get('LOW_ATTENDANCE_THRESHOLD', 75))
    COLLEGE_LAT = float(os.environ.get('COLLEGE_LAT', 27.7172))   # default: Kathmandu
    COLLEGE_LNG = float(os.environ.get('COLLEGE_LNG', 85.3240))
    COLLEGE_NAME = os.environ.get('COLLEGE_NAME', 'College')
    DEFAULT_COLLEGE_CODE = os.environ.get('DEFAULT_COLLEGE_CODE', 'MAIN')
    MULTI_COLLEGE_ROOT_DOMAIN = os.environ.get('MULTI_COLLEGE_ROOT_DOMAIN', '')
    PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', '').strip()
    ALLOWED_HOSTS = [host.strip().lower() for host in os.environ.get('ALLOWED_HOSTS', '').split(',') if host.strip()]
    TRUST_PROXY_HEADERS = os.environ.get('TRUST_PROXY_HEADERS', 'True') == 'True'
    TRUSTED_PROXY_HOPS = int(os.environ.get('TRUSTED_PROXY_HOPS', 1))
    ALLOW_INSECURE_LOCAL_HTTP = _env_bool('ALLOW_INSECURE_LOCAL_HTTP', False)
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
    FACE_RECOGNITION_TOLERANCE = float(os.environ.get('FACE_RECOGNITION_TOLERANCE', 0.5))
    SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'support@smartattend.com')
    SUPPORT_PHONE = os.environ.get('SUPPORT_PHONE', '')
    EAR_THRESHOLD = 0.25
    EAR_CONSEC_FRAMES = 2
    REQUIRED_BLINKS = 1
    LIVENESS_STATE_TTL_SECONDS = int(os.environ.get('LIVENESS_STATE_TTL_SECONDS', 600))
    PASSWORD_SETUP_TOKEN_MAX_AGE = int(os.environ.get('PASSWORD_SETUP_TOKEN_MAX_AGE', 86400))

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATELIMIT_STORAGE_URI = (
        os.environ.get('RATELIMIT_STORAGE_URI')
        or os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')
    )
    RATELIMIT_DEFAULT = '200 per day; 50 per hour'
    RATELIMIT_HEADERS_ENABLED = True

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_DIR = os.environ.get('LOG_DIR', os.path.join(BASE_DIR, 'logs'))


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
    PREFERRED_URL_SCHEME = 'https'
    SESSION_COOKIE_SECURE = _env_bool('SESSION_COOKIE_SECURE', True)
    REMEMBER_COOKIE_SECURE = _env_bool('REMEMBER_COOKIE_SECURE', True)
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
