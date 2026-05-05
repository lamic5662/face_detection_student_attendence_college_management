from __future__ import annotations

from models.platform_audit import PlatformAuditLog


def log_platform_action(
    *,
    actor=None,
    action_key: str,
    summary: str,
    college=None,
    target_type: str | None = None,
    target_id: int | None = None,
    details: dict | None = None,
):
    log = PlatformAuditLog(
        actor_user_id=getattr(actor, 'id', None),
        college_id=getattr(college, 'id', college),
        action_key=action_key,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
    )
    log.set_details(details)
    return log
