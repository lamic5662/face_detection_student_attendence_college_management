import re
from urllib.parse import urlparse, urljoin
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db, limiter
from models.user import User

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

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(email=email, is_active=True).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            current_app.logger.info('User %s logged in from %s', user.email, request.remote_addr)
            next_page = request.args.get('next')
            if next_page and _is_safe_url(next_page):
                return redirect(next_page)
            return redirect(url_for(f'{user.role}.dashboard'))

        current_app.logger.warning(
            'Failed login for %s from %s', email, request.remote_addr
        )
        flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    current_app.logger.info('User %s logged out', current_user.email)
    name = current_user.name
    logout_user()
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
