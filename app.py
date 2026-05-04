import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, jsonify, request
from config import get_config
from extensions import db, login_manager, mail, csrf, migrate, compress, limiter
from services.liveness_service import liveness_manager
from utils.content_storage import resolve_content_path
from utils.file_preview import get_missing_preview_dependencies


def _configure_logging(app: Flask) -> None:
    log_dir = app.config['LOG_DIR']
    os.makedirs(log_dir, exist_ok=True)

    fmt = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s (%(funcName)s:%(lineno)d): %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # Rotating file handler (10 MB × 5 files)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.WARNING)

    # Separate error log
    error_handler = RotatingFileHandler(
        os.path.join(log_dir, 'error.log'),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8',
    )
    error_handler.setFormatter(fmt)
    error_handler.setLevel(logging.ERROR)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO'), logging.INFO)
    console_handler.setLevel(level)

    app.logger.handlers.clear()
    app.logger.addHandler(file_handler)
    app.logger.addHandler(error_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG)

    # Also configure Werkzeug / SQLAlchemy silence unless DEBUG
    if not app.debug:
        logging.getLogger('werkzeug').setLevel(logging.WARNING)


def _register_blueprints(app: Flask) -> None:
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.teacher import teacher_bp
    from routes.student import student_bp
    from routes.leave import leave_bp
    from routes.notice import notice_bp
    from routes.timetable import timetable_bp
    from routes.exam import exam_bp
    from routes.fee import fee_bp
    from routes.parent import parent_bp
    from routes.help import help_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(help_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(teacher_bp, url_prefix='/teacher')
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(leave_bp)
    app.register_blueprint(notice_bp)
    app.register_blueprint(timetable_bp)
    app.register_blueprint(exam_bp)
    app.register_blueprint(fee_bp)
    app.register_blueprint(parent_bp)


def _log_optional_preview_dependencies(app: Flask) -> None:
    missing = get_missing_preview_dependencies()
    if missing:
        app.logger.warning(
            'Optional preview dependencies missing: %s. File preview for some types will be unavailable until installed.',
            ', '.join(missing),
        )
    else:
        app.logger.info('Optional content preview dependencies are available.')


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(400)
    def bad_request(e):
        if request.is_json:
            return jsonify(error='Bad request', message=str(e)), 400
        return render_template('errors/400.html'), 400

    @app.errorhandler(403)
    def forbidden(e):
        if request.is_json:
            return jsonify(error='Forbidden'), 403
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        if request.is_json:
            return jsonify(error='Not found'), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(413)
    def request_too_large(e):
        if request.is_json:
            return jsonify(error='File too large'), 413
        return render_template('errors/413.html'), 413

    @app.errorhandler(429)
    def too_many_requests(e):
        if request.is_json:
            return jsonify(error='Too many requests', retry_after=e.retry_after), 429
        return render_template('errors/429.html'), 429

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception('Unhandled exception: %s', e)
        if request.is_json:
            return jsonify(error='Internal server error'), 500
        return render_template('errors/500.html'), 500


def _add_security_headers(app: Flask) -> None:
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = (
            'camera=(self), microphone=(), geolocation=()'
        )
        if not app.debug:
            response.headers['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains'
            )
        # Tailored CSP: allow Bootstrap CDN, Google Fonts, Chart.js, Bootstrap Icons
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            "img-src 'self' data: blob: https://*.tile.openstreetmap.org; "
            "media-src 'self' blob:; "
            "connect-src 'self' https://nominatim.openstreetmap.org; "
            "frame-ancestors 'self';"
        )
        return response


def _add_health_check(app: Flask) -> None:
    @app.route('/health')
    def health():
        try:
            db.session.execute(db.text('SELECT 1'))
            db_status = 'ok'
        except Exception as exc:  # noqa: BLE001
            app.logger.error('Health check DB failure: %s', exc)
            db_status = 'error'
        status = 'ok' if db_status == 'ok' else 'degraded'
        flask_env = os.environ.get('FLASK_ENV', 'production')
        return jsonify(status=status, db=db_status, env=flask_env), (200 if status == 'ok' else 503)


def _validate_runtime_config(app: Flask) -> None:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['CONTENT_UPLOAD_FOLDER'], exist_ok=True)

    if resolve_content_path(app, 'uploads/content/check.txt') is None:
        raise RuntimeError('CONTENT_UPLOAD_FOLDER is invalid or unsafe.')

    if not app.debug and not app.testing:
        if not app.config.get('SESSION_COOKIE_SECURE'):
            raise RuntimeError('SESSION_COOKIE_SECURE must be enabled outside development/testing.')
        if not app.config.get('REMEMBER_COOKIE_SECURE'):
            raise RuntimeError('REMEMBER_COOKIE_SECURE must be enabled outside development/testing.')

        storage_uri = app.config.get('RATELIMIT_STORAGE_URI', 'memory://')
        if storage_uri.startswith('memory://'):
            app.logger.warning(
                'Rate limiting is using in-memory storage. Use RATELIMIT_STORAGE_URI with Redis or another shared backend in production.'
            )

        content_dir = os.path.abspath(app.config['CONTENT_UPLOAD_FOLDER'])
        static_dir = os.path.abspath(app.static_folder or '')
        if os.path.commonpath([content_dir, static_dir]) == static_dir:
            raise RuntimeError('CONTENT_UPLOAD_FOLDER must not be inside the public static directory.')


def _configure_runtime_services(app: Flask) -> None:
    liveness_manager.configure(app.config.get('LIVENESS_STATE_TTL_SECONDS', 600))


def create_app(config_override=None) -> Flask:
    app = Flask(__name__)

    cfg = config_override or get_config()
    app.config.from_object(cfg)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    compress.init_app(app)
    limiter.init_app(app)

    _configure_logging(app)
    _validate_runtime_config(app)
    _configure_runtime_services(app)
    _log_optional_preview_dependencies(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _add_security_headers(app)
    _add_health_check(app)

    # Exempt AJAX endpoints from CSRF (they send JSON, protected by same-origin)
    @app.before_request
    def _csrf_exempt_ajax():
        pass  # handled per-route via @csrf.exempt where needed

    @app.context_processor
    def inject_globals():
        from datetime import datetime as _dt
        try:
            from models.setting import CollegeSetting
            cs = CollegeSetting.get()
            return dict(
                college_name=cs.college_name,
                college_lat=cs.latitude if cs.latitude is not None else app.config['COLLEGE_LAT'],
                college_lng=cs.longitude if cs.longitude is not None else app.config['COLLEGE_LNG'],
                now=_dt.now,
            )
        except Exception:
            return dict(
                college_name=app.config.get('COLLEGE_NAME', 'College'),
                college_lat=app.config.get('COLLEGE_LAT', 27.7172),
                college_lng=app.config.get('COLLEGE_LNG', 85.3240),
                now=_dt.now,
            )

    return app
