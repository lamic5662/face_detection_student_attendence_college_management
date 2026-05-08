from __future__ import annotations

from datetime import date, timedelta

from utils.time import utc_now_naive


def college_health(college_id: int) -> dict:
    """Return a health score dict for a college based on recent activity."""
    from models.attendance import AttendanceSession
    from models.platform_audit import PlatformAuditLog
    from models.student import Student
    from models.user import User

    today = date.today()
    now = utc_now_naive()

    score = 100
    reasons = []

    # No attendance sessions in last 7 days → -40
    recent_sessions = (
        AttendanceSession.query
        .filter_by(college_id=college_id)
        .filter(AttendanceSession.date >= today - timedelta(days=7))
        .count()
    )
    if recent_sessions == 0:
        score -= 40
        reasons.append('No attendance taken in 7 days')

    # No admin login in last 14 days → -30
    recent_admin = (
        User.query
        .filter_by(college_id=college_id, role='admin')
        .filter(User.last_login_at >= now - timedelta(days=14))
        .first()
    )
    if recent_admin is None:
        score -= 30
        reasons.append('No admin login in 14 days')

    # No students enrolled → -20
    if Student.query.filter_by(college_id=college_id).count() == 0:
        score -= 20
        reasons.append('No students enrolled')

    # No platform activity in last 30 days → -10
    recent_log = (
        PlatformAuditLog.query
        .filter_by(college_id=college_id)
        .filter(PlatformAuditLog.created_at >= now - timedelta(days=30))
        .count()
    )
    if recent_log == 0:
        score -= 10
        reasons.append('No platform activity in 30 days')

    score = max(0, score)

    if score >= 70:
        label, color = 'Healthy', 'success'
    elif score >= 40:
        label, color = 'At Risk', 'warning'
    else:
        label, color = 'Inactive', 'danger'

    return {
        'score': score,
        'label': label,
        'color': color,
        'reasons': reasons,
    }
