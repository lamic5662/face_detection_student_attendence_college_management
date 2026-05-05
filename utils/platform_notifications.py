from __future__ import annotations

from datetime import timedelta

from flask import url_for

from models.platform_audit import PlatformAuditLog
from models.platform_audit_read import PlatformAuditRead
from extensions import db
from utils.time import utc_now_naive


def _platform_scope_query(user):
    recent_cutoff = utc_now_naive() - timedelta(days=7)
    return (
        PlatformAuditLog.query
        .filter(
            PlatformAuditLog.created_at >= recent_cutoff,
            ~PlatformAuditLog.read_receipts.any(
                db.and_(
                    PlatformAuditRead.user_id == user.id,
                    PlatformAuditRead.dismissed_at.isnot(None),
                )
            ),
        )
        .order_by(PlatformAuditLog.created_at.desc())
    )


def _platform_read_ids(user, log_ids: list[int]) -> set[int]:
    if not log_ids:
        return set()
    return {
        log_id
        for (log_id,) in db.session.query(PlatformAuditRead.audit_log_id).filter(
            PlatformAuditRead.user_id == user.id,
            PlatformAuditRead.audit_log_id.in_(log_ids),
        ).all()
    }


def platform_notification_payload(user, limit: int = 6) -> dict:
    scoped_query = _platform_scope_query(user)
    logs = scoped_query.limit(limit).all()
    log_ids = [log.id for log in logs]
    read_ids = _platform_read_ids(user, log_ids)
    count = scoped_query.filter(
        ~PlatformAuditLog.read_receipts.any(PlatformAuditRead.user_id == user.id)
    ).count()
    items = []
    for log in logs:
        actor_label = log.actor.name if log.actor else 'System'
        college_label = log.college.name if log.college else 'Platform'
        items.append({
            'id': log.id,
            'title': log.summary,
            'content': f'{actor_label} · {college_label} · {log.action_key}',
            'category': 'platform',
            'target_role': 'all',
            'is_pinned': False,
            'created_label': log.created_at.strftime('%d %b'),
            'detail_url': (
                url_for('super_admin.college_detail', college_id=log.college_id)
                if log.college_id else url_for('super_admin.audit_logs')
            ),
            'is_read': log.id in read_ids,
        })

    return {
        'count': count,
        'items': items,
    }


def mark_all_platform_notifications_read(user) -> int:
    log_ids = [log.id for log in _platform_scope_query(user).all()]
    if not log_ids:
        return 0

    existing_ids = _platform_read_ids(user, log_ids)
    missing_ids = [log_id for log_id in log_ids if log_id not in existing_ids]
    if not missing_ids:
        return 0

    db.session.add_all(
        PlatformAuditRead(audit_log_id=log_id, user_id=user.id)
        for log_id in missing_ids
    )
    db.session.commit()
    return len(missing_ids)


def dismiss_read_platform_notifications(user) -> int:
    log_ids = [log.id for log in _platform_scope_query(user).all()]
    if not log_ids:
        return 0

    receipts = PlatformAuditRead.query.filter(
        PlatformAuditRead.user_id == user.id,
        PlatformAuditRead.audit_log_id.in_(log_ids),
        PlatformAuditRead.dismissed_at.is_(None),
    ).all()

    updated = 0
    now = utc_now_naive()
    for receipt in receipts:
        if receipt.dismissed_at is None:
            receipt.dismissed_at = now
            updated += 1

    if updated:
        db.session.commit()
    return updated
