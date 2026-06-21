from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from urllib.parse import urlparse, urlunparse
from flask import current_app, url_for
from flask_mail import Message

from extensions import db, mail
from models.college import College
from models.user import User


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def _subdomain_base_url(college: College | None) -> str:
    base_url = (current_app.config.get('PUBLIC_BASE_URL') or '').rstrip('/')
    if not base_url:
        return ''

    root_domain = (current_app.config.get('MULTI_COLLEGE_ROOT_DOMAIN') or '').strip().lower().lstrip('.')
    subdomain = (getattr(college, 'subdomain', None) or '').strip().lower()
    if not root_domain or not subdomain:
        return base_url

    parsed = urlparse(base_url)
    hostname = (parsed.hostname or '').strip().lower()
    if not hostname:
        return base_url

    if hostname == root_domain or hostname.endswith(f'.{root_domain}'):
        target_host = f'{subdomain}.{root_domain}'
        if parsed.port:
            netloc = f'{target_host}:{parsed.port}'
        else:
            netloc = target_host
        return urlunparse(parsed._replace(netloc=netloc)).rstrip('/')

    return base_url


def build_public_url(endpoint: str, *, college: College | None = None, **values) -> str:
    base_url = _subdomain_base_url(college)
    if base_url:
        with current_app.test_request_context(base_url=base_url):
            path = url_for(endpoint, **values)
        return f'{base_url}{path}'
    return url_for(endpoint, _external=True, **values)


def generate_password_setup_token(user: User) -> str:
    return _serializer().dumps(
        {
            'uid': user.id,
            'ph': user.password_hash[-16:],
        },
        salt='password-setup',
    )


def verify_password_setup_token(token: str, *, max_age: int | None = None) -> User | None:
    try:
        data = _serializer().loads(
            token,
            salt='password-setup',
            max_age=max_age or current_app.config.get('PASSWORD_SETUP_TOKEN_MAX_AGE', 86400),
        )
    except (BadSignature, SignatureExpired):
        return None

    user = db.session.get(User, data.get('uid'))
    if user is None:
        return None
    if user.password_hash[-16:] != data.get('ph'):
        return None
    return user


def send_password_setup_email(user: User) -> None:
    token = generate_password_setup_token(user)
    setup_link = build_public_url('auth.set_password_from_email', college=user.college, token=token)
    college_name = user.college.name if user.college else current_app.config.get('COLLEGE_NAME', 'College')

    local_note = """
    <p style="margin:18px 0 0;color:#64748b;font-size:12px;line-height:1.6">
      This button opens a password page in your browser. Email apps cannot show the password form directly inside the email.
    </p>
"""
    if not current_app.config.get('PUBLIC_BASE_URL'):
        local_note = """
    <p style="margin:18px 0 0;color:#64748b;font-size:12px;line-height:1.6">
      This button opens a password page in your browser. Email apps cannot show the password form directly inside the email.
      If SmartAttend is running only on your local computer, open this link on that same device.
    </p>
"""

    html = f"""
<div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:0 auto;background:#f8fafc;padding:24px;border-radius:16px">
  <div style="background:linear-gradient(135deg,#1d4ed8,#0f172a);padding:28px 24px;border-radius:14px 14px 0 0;text-align:left">
    <div style="color:#bfdbfe;font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px">SmartAttend</div>
    <h1 style="color:#fff;margin:0;font-size:24px;font-weight:800">Set your own password</h1>
    <p style="color:rgba(255,255,255,.8);margin:10px 0 0;font-size:14px;line-height:1.6">
      Your account for {college_name} is ready. Use the secure link below to choose a personal password.
    </p>
  </div>
  <div style="background:#fff;padding:24px 28px;border-radius:0 0 14px 14px;border:1px solid #e2e8f0;border-top:none">
    <p style="margin:0 0 18px;color:#0f172a;font-size:14px;line-height:1.7">
      Hello <strong>{user.name}</strong>,<br>
      This link lets you replace your temporary password with one only you know.
    </p>
    <p style="margin:0 0 22px">
      <a href="{setup_link}" style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;font-weight:700;padding:12px 18px;border-radius:10px">
        Set My Password
      </a>
    </p>
    <p style="margin:0 0 12px;color:#475569;font-size:13px;line-height:1.6">
      If the button does not work, open this link:
    </p>
    <p style="margin:0 0 18px;color:#1d4ed8;font-size:13px;word-break:break-all">{setup_link}</p>
    <p style="margin:0;color:#64748b;font-size:12px;line-height:1.6">
      This secure link expires automatically. If you did not expect this email, you can ignore it.
    </p>
    {local_note}
  </div>
</div>
"""

    msg = Message(
        subject='Set your SmartAttend password',
        recipients=[user.email],
        html=html,
    )
    mail.send(msg)
    user.mark_password_setup_email_sent()


def send_password_reset_email(user: User) -> None:
    token = generate_password_setup_token(user)
    reset_link = build_public_url('auth.set_password_from_email', college=user.college, token=token, mode='reset')
    college_name = user.college.name if user.college else current_app.config.get('COLLEGE_NAME', 'College')

    local_note = """
    <p style="margin:18px 0 0;color:#64748b;font-size:12px;line-height:1.6">
      This button opens the password reset page in your browser. Email apps cannot show the password form directly inside the email.
    </p>
"""
    if not current_app.config.get('PUBLIC_BASE_URL'):
        local_note = """
    <p style="margin:18px 0 0;color:#64748b;font-size:12px;line-height:1.6">
      This button opens the password reset page in your browser. Email apps cannot show the password form directly inside the email.
      If SmartAttend is running only on your local computer, open this link on that same device.
    </p>
"""

    html = f"""
<div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:0 auto;background:#f8fafc;padding:24px;border-radius:16px">
  <div style="background:linear-gradient(135deg,#0f172a,#1d4ed8);padding:28px 24px;border-radius:14px 14px 0 0;text-align:left">
    <div style="color:#bfdbfe;font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px">SmartAttend</div>
    <h1 style="color:#fff;margin:0;font-size:24px;font-weight:800">Reset your password</h1>
    <p style="color:rgba(255,255,255,.84);margin:10px 0 0;font-size:14px;line-height:1.6">
      We received a password reset request for your {college_name} account.
    </p>
  </div>
  <div style="background:#fff;padding:24px 28px;border-radius:0 0 14px 14px;border:1px solid #e2e8f0;border-top:none">
    <p style="margin:0 0 18px;color:#0f172a;font-size:14px;line-height:1.7">
      Hello <strong>{user.name}</strong>,<br>
      Use the secure link below to choose a new password for your account.
    </p>
    <p style="margin:0 0 22px">
      <a href="{reset_link}" style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;font-weight:700;padding:12px 18px;border-radius:10px">
        Reset My Password
      </a>
    </p>
    <p style="margin:0 0 12px;color:#475569;font-size:13px;line-height:1.6">
      If the button does not work, open this link:
    </p>
    <p style="margin:0 0 18px;color:#1d4ed8;font-size:13px;word-break:break-all">{reset_link}</p>
    <p style="margin:0;color:#64748b;font-size:12px;line-height:1.6">
      If you did not request a password reset, you can ignore this email. This secure link expires automatically.
    </p>
    {local_note}
  </div>
</div>
"""

    msg = Message(
        subject='Reset your SmartAttend password',
        recipients=[user.email],
        html=html,
    )
    mail.send(msg)
