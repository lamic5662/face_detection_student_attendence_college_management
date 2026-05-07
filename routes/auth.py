import re
from urllib.parse import urlparse, urljoin
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db, limiter
from models.user import User
from utils.account_setup import send_password_reset_email, send_password_setup_email, verify_password_setup_token
from utils.dashboard import normalize_dashboard_widget_keys
from utils.navigation import PIN_LIMIT, allowed_pin_keys, normalize_sidebar_pins
from utils.tenancy import get_current_college, is_college_locked, resolve_login_college, store_login_college

auth_bp = Blueprint('auth', __name__)

_PASSWORD_RE = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^a-zA-Z0-9]).{8,}$'
)


def _dashboard_url(role: str) -> str:
    if role == 'sub_admin':
        return url_for('admin.dashboard')
    return url_for(f'{role}.dashboard')


def _post_login_destination(user: User):
    if user.must_change_password and user.role in {'student', 'teacher', 'parent'}:
        return redirect(url_for('auth.password_setup_prompt'))
    next_page = request.args.get('next')
    if next_page and _is_safe_url(next_page):
        return redirect(next_page)
    return redirect(_dashboard_url(user.role))


def _find_global_super_admin(email: str) -> User | None:
    return User.query.filter_by(
        email=email,
        role='super_admin',
        is_active=True,
    ).first()


def _is_safe_url(target: str) -> bool:
    """Prevent open-redirect: only allow same-host relative URLs."""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return _post_login_destination(current_user)
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute; 50 per hour', methods=['POST'])
def login():
    if current_user.is_authenticated:
        return _post_login_destination(current_user)

    login_college = get_current_college(optional=True)
    college_locked = is_college_locked()

    if request.method == 'POST':
        college_code = request.form.get('college_code', '').strip().upper()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        if not college_locked and not college_code:
            super_admin = _find_global_super_admin(email)
            if super_admin and super_admin.check_password(password):
                login_user(super_admin, remember=remember)
                store_login_college(super_admin.college)
                current_app.logger.info('Super admin %s logged in from %s', super_admin.email, request.remote_addr)
                return _post_login_destination(super_admin)

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
            return _post_login_destination(user)

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


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def forgot_password():
    if current_user.is_authenticated:
        return _post_login_destination(current_user)

    login_college = get_current_college(optional=True)
    college_locked = is_college_locked()
    submitted_college_code = (login_college.code if login_college and not college_locked else '')

    if request.method == 'POST':
        college_code = request.form.get('college_code', '').strip().upper()
        email = request.form.get('email', '').strip().lower()
        submitted_college_code = college_code

        if not email:
            flash('Enter your email address to continue.', 'danger')
            return render_template(
                'auth/forgot_password.html',
                login_college=login_college,
                college_locked=college_locked,
                submitted_college_code=submitted_college_code,
            )

        user = None
        if not college_locked and not college_code:
            user = _find_global_super_admin(email)
            if user is None:
                flash('Enter your college code to reset a college account password.', 'danger')
                return render_template(
                    'auth/forgot_password.html',
                    login_college=login_college,
                    college_locked=college_locked,
                    submitted_college_code=submitted_college_code,
                )
        else:
            target_college = login_college if college_locked else resolve_login_college(college_code)
            if target_college is None:
                if college_locked:
                    flash('This college portal is unavailable or inactive.', 'danger')
                else:
                    flash('Enter a valid college code to continue.', 'danger')
                return render_template(
                    'auth/forgot_password.html',
                    login_college=login_college,
                    college_locked=college_locked,
                    submitted_college_code=submitted_college_code,
                )

            user = User.query.filter_by(
                college_id=target_college.id,
                email=email,
                is_active=True,
            ).first()

        try:
            if user is not None:
                send_password_reset_email(user)
                db.session.commit()
                current_app.logger.info('Password reset email issued for %s from %s', user.email, request.remote_addr)
            else:
                db.session.rollback()
                current_app.logger.info(
                    'Password reset requested for unknown user %s in college context %s from %s',
                    email,
                    college_code or (login_college.code if login_college else 'super-admin'),
                    request.remote_addr,
                )
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            current_app.logger.error('Password reset email failed for %s: %s', email, exc)

        flash(
            'If we found an active account for that email, a password reset link has been sent.',
            'success',
        )
        return redirect(url_for('auth.login'))

    return render_template(
        'auth/forgot_password.html',
        login_college=login_college,
        college_locked=college_locked,
        submitted_college_code=submitted_college_code,
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


@auth_bp.route('/password-setup-prompt', methods=['GET', 'POST'])
@login_required
def password_setup_prompt():
    if not current_user.must_change_password:
        return redirect(_dashboard_url(current_user.role))
    if current_user.role not in {'student', 'teacher', 'parent', 'sub_admin'}:
        return redirect(_dashboard_url(current_user.role))
    if request.method == 'POST':
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not _PASSWORD_RE.match(new_pw):
            flash(
                'Password must be at least 8 characters and include uppercase, '
                'lowercase, a digit, and a special character.',
                'danger',
            )
        elif current_user.check_password(new_pw):
            flash('Your new password must be different from the current one.', 'danger')
        elif new_pw != confirm_pw:
            flash('Passwords do not match.', 'danger')
        else:
            current_user.set_password(new_pw)
            db.session.commit()
            current_app.logger.info('User %s replaced temporary password and must sign in again', current_user.email)
            logout_user()
            store_login_college(None)
            flash('Password updated. Please sign in again with your new password.', 'success')
            return redirect(url_for('auth.login'))

    return render_template(
        'auth/set_password.html',
        setup_user=current_user,
        form_action=url_for('auth.password_setup_prompt'),
        helper_title='Use your own password',
        helper_copy='Your temporary password is only for first login. Set your own password now to continue.',
        force_relogin=True,
    )


@auth_bp.route('/password-setup-prompt/send-email', methods=['POST'])
@login_required
@limiter.limit('5 per hour', methods=['POST'])
def send_password_setup_email_to_current_user():
    if not current_user.must_change_password or current_user.role not in {'student', 'teacher', 'parent', 'sub_admin'}:
        return redirect(_dashboard_url(current_user.role))

    try:
        send_password_setup_email(current_user)
        db.session.commit()
        flash(f'A password setup email was sent to {current_user.email}.', 'success')
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        current_app.logger.error('Password setup email failed for %s: %s', current_user.email, exc)
        flash('We could not send the password setup email right now. Please try again later.', 'danger')
        return redirect(url_for('auth.password_setup_prompt'))

    flash('For security, you still need to set your new password before continuing.', 'info')
    return redirect(url_for('auth.password_setup_prompt'))


@auth_bp.route('/set-password/<token>', methods=['GET', 'POST'])
@limiter.limit('10 per hour', methods=['POST'])
def set_password_from_email(token):
    user = verify_password_setup_token(token)
    if user is None:
        flash('This password setup link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not _PASSWORD_RE.match(new_pw):
            flash(
                'Password must be at least 8 characters and include uppercase, '
                'lowercase, a digit, and a special character.',
                'danger',
            )
        elif user.check_password(new_pw):
            flash('Your new password must be different from the current one.', 'danger')
        elif new_pw != confirm_pw:
            flash('Passwords do not match.', 'danger')
        else:
            user.set_password(new_pw)
            db.session.commit()
            current_app.logger.info('User %s set a new password from email link and must sign in again', user.email)
            flash('Your password has been updated. Please sign in with your new password.', 'success')
            return redirect(url_for('auth.login'))

    return render_template(
        'auth/set_password.html',
        setup_user=user,
        form_action=url_for('auth.set_password_from_email', token=token),
        helper_title=('Reset your password' if request.args.get('mode') == 'reset' else 'Create your password'),
        helper_copy=(
            'Choose a new private password for your account.'
            if request.args.get('mode') == 'reset'
            else 'Choose a private password for your account.'
        ),
    )


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
        elif current_user.check_password(new_pw):
            flash('Your new password must be different from the current one.', 'danger')
        elif new_pw != confirm_pw:
            flash('Passwords do not match.', 'danger')
        else:
            current_user.set_password(new_pw)
            db.session.commit()
            current_app.logger.info('User %s changed password', current_user.email)
            flash('Password changed successfully!', 'success')
            return redirect(_dashboard_url(current_user.role))

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

    next_page = request.form.get('next') or request.referrer or _dashboard_url(current_user.role)
    if next_page and _is_safe_url(next_page):
        return redirect(next_page)
    return redirect(_dashboard_url(current_user.role))


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

    next_page = request.form.get('next') or request.referrer or _dashboard_url(current_user.role)
    if next_page and _is_safe_url(next_page):
        return redirect(next_page)
    return redirect(_dashboard_url(current_user.role))


@auth_bp.route('/preferences/dashboard', methods=['POST'])
@login_required
def update_dashboard_preferences():
    selected = request.form.getlist('dashboard_widgets')
    widgets = normalize_dashboard_widget_keys(current_user.role, selected)
    current_user.set_dashboard_widget_keys(widgets)
    db.session.commit()

    flash('Dashboard widgets updated.', 'success')

    next_page = request.form.get('next') or request.referrer or _dashboard_url(current_user.role)
    if next_page and _is_safe_url(next_page):
        return redirect(next_page)
    return redirect(_dashboard_url(current_user.role))
