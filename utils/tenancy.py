from __future__ import annotations

from flask import current_app, g, has_request_context, request, session

from models.college import College

SESSION_COLLEGE_ID_KEY = 'college_id'


def _normalized_host() -> str:
    if not has_request_context():
        return ''
    return (request.host or '').split(':', 1)[0].strip().lower()


def _root_domain() -> str:
    return (current_app.config.get('MULTI_COLLEGE_ROOT_DOMAIN') or '').strip().lower().lstrip('.')


def resolve_subdomain_college() -> College | None:
    if not has_request_context():
        return None

    root_domain = _root_domain()
    host = _normalized_host()
    if not root_domain or not host or host == root_domain or not host.endswith(root_domain):
        return None

    prefix = host[: -len(root_domain)].rstrip('.')
    if not prefix or prefix in {'www', 'app'}:
        return None

    subdomain = prefix.split('.')[-1]
    if not subdomain:
        return None
    return College.query.filter_by(subdomain=subdomain, is_active=True).first()


def resolve_login_college(college_code: str | None = None) -> College | None:
    college = resolve_subdomain_college()
    if college is not None:
        return college

    code = (college_code or '').strip().upper()
    if code:
        return College.query.filter_by(code=code, is_active=True).first()

    active_colleges = College.query.filter_by(is_active=True).order_by(College.id.asc()).limit(2).all()
    if len(active_colleges) == 1:
        return active_colleges[0]
    return None


def store_login_college(college: College | None) -> None:
    if college is None:
        session.pop(SESSION_COLLEGE_ID_KEY, None)
        return
    session[SESSION_COLLEGE_ID_KEY] = college.id


def load_request_college() -> College | None:
    college = resolve_subdomain_college()

    if college is None and has_request_context():
        college_id = session.get(SESSION_COLLEGE_ID_KEY)
        if college_id:
            college = db_session_get_college(college_id)

    if college is None:
        try:
            from flask_login import current_user

            if getattr(current_user, 'is_authenticated', False):
                college = db_session_get_college(current_user.college_id)
        except Exception:
            college = college

    if college is None:
        college = resolve_login_college(None)

    g.current_college = college
    return college


def get_current_college(optional: bool = False) -> College | None:
    college = getattr(g, 'current_college', None) if has_request_context() else None
    if college is None:
        college = load_request_college()

    if college is None and not optional:
        college = College.ensure_default()
        if has_request_context():
            g.current_college = college
    return college


def current_college_id(optional: bool = False) -> int | None:
    college = get_current_college(optional=optional)
    return college.id if college is not None else None


def is_college_locked() -> bool:
    return resolve_subdomain_college() is not None


def db_session_get_college(college_id: int | None) -> College | None:
    if college_id is None:
        return None
    from extensions import db

    return db.session.get(College, college_id)
