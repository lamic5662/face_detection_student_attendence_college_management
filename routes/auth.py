import re
from urllib.parse import urlparse, urljoin
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db, limiter
from models.user import User
from utils.dashboard import normalize_dashboard_widget_keys
from utils.navigation import PIN_LIMIT, allowed_pin_keys, normalize_sidebar_pins
from utils.tenancy import get_current_college, is_college_locked, resolve_login_college, store_login_college

auth_bp = Blueprint('auth', __name__)

_PASSWORD_RE = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^a-zA-Z0-9]).{8,}$'
)


def _is_safe_url(target: str) -> bool:
    """Prevent open-redirect: only allow same-host relative URLs."""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for(f'{current_user.role}.dashboard'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute; 50 per hour', methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(f'{current_user.role}.dashboard'))

    login_college = get_current_college(optional=True)
    college_locked = is_college_locked()

    if request.method == 'POST':
        college_code = request.form.get('college_code', '').strip().upper()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        login_college = resolve_login_college(college_code)

        if login_college is None:
            if college_locked:
                flash('This college portal is unavailable or inactive.', 'danger')
            else:
                flash('Enter a valid college code to continue.', 'danger')
            return render_template(
                'auth/login.html',
                login_college=None,
                college_locked=college_locked,
                submitted_college_code=college_code,
            )

        user = User.query.filter_by(
            college_id=login_college.id,
            email=email,
            is_active=True,
        ).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            store_login_college(login_college)
            current_app.logger.info('User %s logged in from %s', user.email, request.remote_addr)
            next_page = request.args.get('next')
            if next_page and _is_safe_url(next_page):
                return redirect(next_page)
            return redirect(url_for(f'{user.role}.dashboard'))

        current_app.logger.warning(
            'Failed login for %s in college %s from %s',
            email,
            login_college.code if login_college else 'unknown',
            request.remote_addr,
        )
        flash('Invalid email or password.', 'danger')

    return render_template(
        'auth/login.html',
        login_college=login_college,
        college_locked=college_locked,
        submitted_college_code=(login_college.code if login_college and not college_locked else ''),
    )


@auth_bp.route('/logout')
@login_required
def logout():
    current_app.logger.info('User %s logged out', current_user.email)
    name = current_user.name
    logout_user()
    store_login_college(None)
    flash(f'Goodbye, {name}!', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
@limiter.limit('10 per hour', methods=['POST'])
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not current_user.check_password(current_pw):
            flash('Current password is incorrect.', 'danger')
        elif not _PASSWORD_RE.match(new_pw):
            flash(
                'Password must be at least 8 characters and include uppercase, '
                'lowercase, a digit, and a special character.',
                'danger',
            )
        elif new_pw != confirm_pw:
            flash('Passwords do not match.', 'danger')
        else:
            current_user.set_password(new_pw)
            db.session.commit()
            current_app.logger.info('User %s changed password', current_user.email)
            flash('Password changed successfully!', 'success')
            return redirect(url_for(f'{current_user.role}.dashboard'))

    return render_template('auth/change_password.html')


@auth_bp.route('/preferences/sidebar', methods=['POST'])
@login_required
def update_sidebar_preferences():
    requested = request.form.getlist('pinned_features')
    pins, trimmed = normalize_sidebar_pins(current_user.role, requested)
    current_user.set_sidebar_pin_keys(pins)
    db.session.commit()

    if trimmed:
        flash(
            f'Quick access updated. Only the first {PIN_LIMIT} extra tools were pinned to keep the menu compact.',
            'warning',
        )
    else:
        flash('Quick access updated.', 'success')

    next_page = request.form.get('next') or request.referrer or url_for(f'{current_user.role}.dashboard')
    if next_page and _is_safe_url(next_page):
        return redirect(next_page)
    return redirect(url_for(f'{current_user.role}.dashboard'))


@auth_bp.route('/preferences/sidebar/toggle', methods=['POST'])
@login_required
def toggle_sidebar_pin():
    feature_key = (request.form.get('feature_key') or '').strip()
    allowed = set(allowed_pin_keys(current_user.role))

    if feature_key not in allowed:
        flash('That tool cannot be pinned here.', 'warning')
    else:
        pins = current_user.get_sidebar_pin_keys()
        if feature_key in pins:
            pins = [key for key in pins if key != feature_key]
        else:
            pins.append(feature_key)
        pins, trimmed = normalize_sidebar_pins(current_user.role, pins)
        current_user.set_sidebar_pin_keys(pins)
        db.session.commit()

        if trimmed:
            flash(
                f'Only the first {PIN_LIMIT} extra tools can stay pinned in quick access.',
                'warning',
            )

    next_page = request.form.get('next') or request.referrer or url_for(f'{current_user.role}.dashboard')
    if next_page and _is_safe_url(next_page):
        return redirect(next_page)
    return redirect(url_for(f'{current_user.role}.dashboard'))


@auth_bp.route('/preferences/dashboard', methods=['POST'])
@login_required
def update_dashboard_preferences():
    selected = request.form.getlist('dashboard_widgets')
    widgets = normalize_dashboard_widget_keys(current_user.role, selected)
    current_user.set_dashboard_widget_keys(widgets)
    db.session.commit()

    flash('Dashboard widgets updated.', 'success')

    next_page = request.form.get('next') or request.referrer or url_for(f'{current_user.role}.dashboard')
    if next_page and _is_safe_url(next_page):
        return redirect(next_page)
    return redirect(url_for(f'{current_user.role}.dashboard'))
