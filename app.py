import os
import logging
import ipaddress
from logging.handlers import RotatingFileHandler
from datetime import timedelta
from urllib.parse import urlparse
from flask import Flask, render_template, jsonify, request, url_for, redirect
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix
import redis
from config import get_config
from extensions import db, login_manager, mail, csrf, migrate, compress, limiter
from services.liveness_service import liveness_manager
from utils.content_storage import resolve_content_path
from utils.assignment_storage import resolve_submission_path
from utils.file_preview import get_missing_preview_dependencies
from utils.feature_access import endpoint_has_access, feature_access_message, user_has_feature
from utils.navigation import build_sidebar_navigation
from utils.platform_notifications import platform_notification_payload
from utils.tenancy import get_current_college, load_request_college
from utils.time import utc_now_naive


def _host_is_allowed(host: str, allowed_hosts: list[str]) -> bool:
    host = (host or '').split(':', 1)[0].lower()
    if not host:
        return False
    try:
        host_ip = ipaddress.ip_address(host)
    except ValueError:
        host_ip = None
    for allowed in allowed_hosts:
        candidate = allowed.strip().lower()
        if candidate == '*':
            return True
        if '/' in candidate and host_ip is not None:
            try:
                if host_ip in ipaddress.ip_network(candidate, strict=False):
                    return True
            except ValueError:
                pass
        if candidate.startswith('.'):
            suffix = candidate[1:]
            if host == suffix or host.endswith(f'.{suffix}'):
                return True
        elif host == candidate:
            return True
    return False


def _effective_allowed_hosts(app: Flask) -> list[str]:
    allowed_hosts = list(app.config.get('ALLOWED_HOSTS', []))
    public_base_url = (app.config.get('PUBLIC_BASE_URL') or '').strip()
    if public_base_url:
        parsed = urlparse(public_base_url)
        if parsed.hostname:
            allowed_hosts.append(parsed.hostname.lower())
    return allowed_hosts


def _private_ip_http_redirect_target(app: Flask):
    public_base_url = (app.config.get('PUBLIC_BASE_URL') or '').strip().rstrip('/')
    if not public_base_url:
        return None

    parsed_public = urlparse(public_base_url)
    if parsed_public.scheme != 'https':
        return None

    host = (request.host or '').split(':', 1)[0].lower()
    if host in {'localhost', '127.0.0.1'} or request.is_secure:
        return None

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return None

    if not ip.is_private:
        return None

    query = request.query_string.decode('utf-8', errors='ignore')
    target = f'{public_base_url}{request.path}'
    if query:
        target = f'{target}?{query}'
    return target


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
    from routes.super_admin import super_admin_bp
    from routes.admin import admin_bp
    from routes.teacher import teacher_bp
    from routes.student import student_bp
    from routes.leave import leave_bp
    from routes.notice import notice_bp
    from routes.timetable import timetable_bp
    from routes.calendar import calendar_bp
    from routes.exam import exam_bp
    from routes.fee import fee_bp
    from routes.parent import parent_bp
    from routes.help import help_bp
    from routes.ai import ai_bp
    from routes.classroom import classroom_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(help_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(super_admin_bp, url_prefix='/super-admin')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(teacher_bp, url_prefix='/teacher')
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(leave_bp)
    app.register_blueprint(notice_bp)
    app.register_blueprint(timetable_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(exam_bp)
    app.register_blueprint(fee_bp)
    app.register_blueprint(parent_bp)
    app.register_blueprint(classroom_bp)


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
    os.makedirs(app.config['ASSIGNMENT_UPLOAD_FOLDER'], exist_ok=True)

    if resolve_content_path(app, 'uploads/content/check.txt') is None:
        raise RuntimeError('CONTENT_UPLOAD_FOLDER is invalid or unsafe.')
    if resolve_submission_path(app, 'uploads/submissions/check.txt') is None:
        raise RuntimeError('ASSIGNMENT_UPLOAD_FOLDER is invalid or unsafe.')

    if not app.debug and not app.testing:
        if not app.config.get('SESSION_COOKIE_SECURE'):
            raise RuntimeError('SESSION_COOKIE_SECURE must be enabled outside development/testing.')
        if not app.config.get('REMEMBER_COOKIE_SECURE'):
            raise RuntimeError('REMEMBER_COOKIE_SECURE must be enabled outside development/testing.')

        storage_uri = app.config.get('RATELIMIT_STORAGE_URI', 'memory://')
        if storage_uri.startswith('memory://'):
            raise RuntimeError(
                'RATELIMIT_STORAGE_URI must use a shared backend such as Redis in production.'
            )

        content_dir = os.path.abspath(app.config['CONTENT_UPLOAD_FOLDER'])
        assignment_dir = os.path.abspath(app.config['ASSIGNMENT_UPLOAD_FOLDER'])
        static_dir = os.path.abspath(app.static_folder or '')
        if os.path.commonpath([content_dir, static_dir]) == static_dir:
            raise RuntimeError('CONTENT_UPLOAD_FOLDER must not be inside the public static directory.')
        if os.path.commonpath([assignment_dir, static_dir]) == static_dir:
            raise RuntimeError('ASSIGNMENT_UPLOAD_FOLDER must not be inside the public static directory.')

        if not app.config.get('ALLOWED_HOSTS'):
            raise RuntimeError('ALLOWED_HOSTS must be configured in production.')

    root_domain = (app.config.get('MULTI_COLLEGE_ROOT_DOMAIN') or '').strip()
    if root_domain and ('://' in root_domain or '/' in root_domain):
        raise RuntimeError('MULTI_COLLEGE_ROOT_DOMAIN must be a bare domain such as example.com.')

    college_code = (app.config.get('DEFAULT_COLLEGE_CODE') or '').strip()
    if not college_code:
        raise RuntimeError('DEFAULT_COLLEGE_CODE must not be empty.')


def _configure_runtime_services(app: Flask) -> None:
    liveness_manager.configure(app.config.get('LIVENESS_STATE_TTL_SECONDS', 600))


def _prepare_rate_limit_storage(app: Flask) -> None:
    storage_uri = app.config.get('RATELIMIT_STORAGE_URI', 'memory://')
    if not storage_uri.startswith('redis://'):
        return

    # In local development, fall back cleanly if Redis is not running.
    if not (app.debug or app.testing):
        return

    try:
        redis.Redis.from_url(
            storage_uri,
            socket_connect_timeout=0.3,
            socket_timeout=0.3,
        ).ping()
    except Exception:  # noqa: BLE001
        app.config['RATELIMIT_STORAGE_URI'] = 'memory://'
        app.config['_RATELIMIT_FALLBACK_MESSAGE'] = (
            f'Rate limiting fell back to memory:// because Redis is unreachable at {storage_uri}.'
        )


def _apply_proxy_fix(app: Flask) -> None:
    if app.config.get('TRUST_PROXY_HEADERS', True):
        hops = max(int(app.config.get('TRUSTED_PROXY_HOPS', 1)), 0)
        if hops > 0:
            app.wsgi_app = ProxyFix(  # type: ignore[assignment]
                app.wsgi_app,
                x_for=hops,
                x_proto=hops,
                x_host=hops,
                x_port=hops,
                x_prefix=hops,
            )


def create_app(config_override=None) -> Flask:
    app = Flask(__name__)

    cfg = config_override or get_config()
    app.config.from_object(cfg)
    _apply_proxy_fix(app)
    _prepare_rate_limit_storage(app)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    compress.init_app(app)
    limiter.init_app(app)

    @limiter.request_filter
    def _exempt_safe_auth_page_reads():
        return request.method in {'GET', 'HEAD', 'OPTIONS'} and request.endpoint in {
            'auth.login',
            'auth.index',
        }

    _configure_logging(app)
    if app.config.get('_RATELIMIT_FALLBACK_MESSAGE'):
        app.logger.warning(app.config['_RATELIMIT_FALLBACK_MESSAGE'])
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
        load_request_college()
        redirect_target = _private_ip_http_redirect_target(app)
        if redirect_target and request.method in {'GET', 'HEAD'}:
            return redirect(redirect_target, code=302)
        if not app.debug and not app.testing:
            allowed_hosts = _effective_allowed_hosts(app)
            if allowed_hosts and not _host_is_allowed(request.host, allowed_hosts):
                return render_template('errors/400.html'), 400
        if (
            current_user.is_authenticated
            and current_user.role in {'student', 'teacher', 'parent', 'sub_admin'}
            and getattr(current_user, 'must_change_password', False)
        ):
            allowed_endpoints = {
                'auth.password_setup_prompt',
                'auth.send_password_setup_email_to_current_user',
                'auth.set_password_from_email',
                'auth.logout',
                'static',
            }
            if request.endpoint not in allowed_endpoints:
                return redirect(url_for('auth.password_setup_prompt'))
        if current_user.is_authenticated and current_user.role != 'super_admin':
            if not endpoint_has_access(current_user, request.endpoint):
                message = feature_access_message(request.endpoint)
                if request.is_json:
                    return jsonify(error='Feature disabled', message=message), 403
                return render_template('errors/403.html', message=message), 403
        if current_user.is_authenticated and current_user.role == 'sub_admin':
            from utils.subadmin import check_subadmin_access
            if not check_subadmin_access(current_user, request.endpoint):
                if request.is_json:
                    return jsonify(error='Permission denied'), 403
                return render_template('errors/403.html', message='You do not have permission to access this section.'), 403

    @app.context_processor
    def inject_globals():
        from datetime import datetime as _dt
        try:
            college = get_current_college(optional=True)
            from models.setting import CollegeSetting
            from models.notice import Notice
            from models.notice_read import NoticeRead
            if current_user.is_authenticated and current_user.role != 'super_admin' and getattr(current_user, 'college', None) is not None:
                college = current_user.college
            cs = CollegeSetting.get(college=college) if college is not None else None
            notification_items = []
            notification_count = 0
            sidebar_navigation = None
            notices_enabled = False
            notification_mode = ''

            if current_user.is_authenticated:
                if current_user.role == 'super_admin':
                    payload = platform_notification_payload(current_user)
                    notification_items = payload['items']
                    notification_count = payload['count']
                    notices_enabled = True
                    notification_mode = 'platform'
                else:
                    notices_enabled = user_has_feature(current_user, 'notices')
                if notices_enabled and current_user.role != 'super_admin':
                    notice_query = Notice.query.filter(
                        Notice.college_id == current_user.college_id,
                        db.or_(Notice.expires_at == None, Notice.expires_at > utc_now_naive())
                    )
                    if current_user.role == 'student':
                        notice_query = notice_query.filter(Notice.target_role.in_(['all', 'student']))
                    elif current_user.role == 'teacher':
                        notice_query = notice_query.filter(Notice.target_role.in_(['all', 'teacher']))
                    elif current_user.role == 'parent':
                        notice_query = notice_query.filter(Notice.target_role.in_(['all', 'student']))
                    # admin and sub_admin see all notices (no filter)

                    recent_cutoff = utc_now_naive() - timedelta(days=7)
                    scoped_query = notice_query.filter(
                        db.or_(
                            Notice.is_pinned == True,
                            Notice.created_at >= recent_cutoff,
                        )
                    )
                    scoped_query = scoped_query.filter(
                        ~Notice.read_receipts.any(
                            db.and_(
                                NoticeRead.user_id == current_user.id,
                                NoticeRead.dismissed_at.isnot(None),
                            )
                        )
                    )
                    notices = (
                        scoped_query
                        .order_by(Notice.is_pinned.desc(), Notice.created_at.desc())
                        .limit(6)
                        .all()
                    )
                    if notices:
                        read_notice_ids = {
                            notice_id
                            for (notice_id,) in db.session.query(NoticeRead.notice_id).filter(
                                NoticeRead.user_id == current_user.id,
                                NoticeRead.notice_id.in_([notice.id for notice in notices]),
                            ).all()
                        }
                    else:
                        read_notice_ids = set()
                    notification_items = [
                        {
                            'id': notice.id,
                            'title': notice.title,
                            'content': notice.content[:140],
                            'category': notice.category,
                            'target_role': notice.target_role,
                            'is_pinned': notice.is_pinned,
                            'created_label': notice.created_at.strftime('%d %b'),
                            'detail_url': url_for('notice.detail', nid=notice.id),
                            'is_read': notice.id in read_notice_ids,
                        }
                        for notice in notices
                    ]

                    notification_count = scoped_query.filter(
                        ~Notice.read_receipts.any(NoticeRead.user_id == current_user.id)
                    ).count()
                    notification_mode = 'notice'
                sidebar_navigation = build_sidebar_navigation(current_user, request.endpoint)

            return dict(
                college_name=cs.college_name if cs is not None else app.config.get('COLLEGE_NAME', 'College'),
                college_lat=(cs.latitude if cs is not None and cs.latitude is not None else app.config['COLLEGE_LAT']),
                college_lng=(cs.longitude if cs is not None and cs.longitude is not None else app.config['COLLEGE_LNG']),
                college_logo=cs.logo_path if cs is not None else None,
                college_logo_version=(int(cs.updated_at.timestamp()) if cs is not None and cs.logo_path and cs.updated_at else None),
                now=_dt.now,
                notification_items=notification_items,
                notification_count=notification_count,
                notices_enabled=notices_enabled,
                notification_mode=notification_mode,
                sidebar_navigation=sidebar_navigation,
                current_college=college,
            )
        except Exception:
            return dict(
                college_name=app.config.get('COLLEGE_NAME', 'College'),
                college_lat=app.config.get('COLLEGE_LAT', 27.7172),
                college_lng=app.config.get('COLLEGE_LNG', 85.3240),
                college_logo=None,
                college_logo_version=None,
                now=_dt.now,
                notification_items=[],
                notification_count=0,
                notices_enabled=False,
                notification_mode='',
                sidebar_navigation=None,
                current_college=None,
            )

    _start_scheduler(app)

    from utils.time import utc_now_naive
    app.extensions['server_start_time'] = utc_now_naive()

    return app


def _start_scheduler(app: 'Flask') -> None:
    """Start APScheduler for background jobs.

    In Flask debug mode, Werkzeug spawns two processes:
      - parent (reloader): watches files, WERKZEUG_RUN_MAIN is NOT set
      - child  (serving):  handles requests, WERKZEUG_RUN_MAIN == 'true'
    We only start the scheduler in the serving process so it lives alongside
    the app that handles requests. In production (no reloader) it always starts.
    """
    import os
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return

    # Guard against double-start on Gunicorn multi-worker pre-fork setups
    if os.environ.get('SCHEDULER_STARTED') == '1':
        return
    os.environ['SCHEDULER_STARTED'] = '1'

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from services.attendance_report import check_and_run_scheduled_reports
        from services.fee_reminder import check_and_send_fee_reminders

        def _hourly_jobs():
            check_and_run_scheduled_reports(app)
            check_and_send_fee_reminders(app)

        scheduler = BackgroundScheduler(timezone='Asia/Kathmandu')
        # Poll every hour; each college's schedule config is checked inside each job
        scheduler.add_job(
            func=_hourly_jobs,
            trigger='cron',
            minute=0,
            id='hourly_background_jobs',
            replace_existing=True,
        )
        scheduler.start()
        app.extensions['scheduler'] = scheduler
        import logging
        logging.getLogger(__name__).info('APScheduler started — hourly background jobs (attendance reports + fee reminders)')

        import atexit
        atexit.register(lambda: scheduler.shutdown(wait=False))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(f'Scheduler failed to start: {exc}')
