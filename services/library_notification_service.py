from __future__ import annotations

import logging

from flask import current_app
from flask_mail import Message

from extensions import db, mail
from models.parent import ParentStudent
from models.teacher import Teacher
from models.user import User
from models.user_notification import UserNotification
from models.student import Student
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)


def create_private_notification(
    user: User,
    *,
    title: str,
    content: str,
    category: str = 'general',
    action_url: str | None = None,
    source_key: str | None = None,
    send_email: bool = False,
) -> UserNotification:
    notification = None
    if source_key:
        notification = UserNotification.query.filter_by(
            college_id=user.college_id,
            user_id=user.id,
            source_key=source_key,
        ).first()

    if notification is None:
        notification = UserNotification(
            college_id=user.college_id,
            user_id=user.id,
            source_key=source_key,
        )
        db.session.add(notification)

    notification.title = title
    notification.content = content
    notification.category = category
    notification.action_url = action_url
    notification.dismissed_at = None
    notification.read_at = None
    notification.created_at = utc_now_naive()

    if send_email and user.email:
        _send_private_notification_email(user, title=title, content=content, action_url=action_url)

    return notification


def notify_student_and_parents(
    student: Student,
    *,
    title: str,
    content: str,
    category: str = 'general',
    student_action_url: str | None = None,
    parent_action_url: str | None = None,
    source_key: str | None = None,
    send_email: bool = False,
) -> None:
    create_private_notification(
        student.user,
        title=title,
        content=content,
        category=category,
        action_url=student_action_url,
        source_key=source_key,
        send_email=send_email,
    )
    for link in ParentStudent.query.filter_by(college_id=student.college_id, student_id=student.id).all():
        create_private_notification(
            link.parent,
            title=title,
            content=content,
            category=category,
            action_url=parent_action_url,
            source_key=source_key,
            send_email=send_email,
        )


def notify_teacher(
    teacher: Teacher,
    *,
    title: str,
    content: str,
    category: str = 'general',
    action_url: str | None = None,
    source_key: str | None = None,
    send_email: bool = False,
) -> None:
    create_private_notification(
        teacher.user,
        title=title,
        content=content,
        category=category,
        action_url=action_url,
        source_key=source_key,
        send_email=send_email,
    )


def notify_roles(
    *,
    college_id: int,
    roles: set[str],
    title: str,
    content: str,
    category: str = 'general',
    action_url: str | None = None,
    source_key: str | None = None,
    send_email: bool = False,
) -> None:
    recipients = User.query.filter(
        User.college_id == college_id,
        User.role.in_(list(roles)),
        User.is_active.is_(True),
    ).all()
    for user in recipients:
        create_private_notification(
            user,
            title=title,
            content=content,
            category=category,
            action_url=action_url,
            source_key=source_key,
            send_email=send_email,
        )


def _send_private_notification_email(user: User, *, title: str, content: str, action_url: str | None) -> None:
    try:
        public_base = (current_app.config.get('PUBLIC_BASE_URL') or '').rstrip('/')
        link = f'{public_base}{action_url}' if public_base and action_url and action_url.startswith('/') else action_url
        button_html = ''
        if link:
            button_html = f"""
              <p style="margin:20px 0 0">
                <a href="{link}" style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;font-weight:700;padding:12px 18px;border-radius:10px">
                  Open Notification
                </a>
              </p>
            """
        msg = Message(
            subject=title,
            recipients=[user.email],
            html=f"""
            <div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:0 auto;background:#f8fafc;padding:24px;border-radius:16px">
              <div style="background:linear-gradient(135deg,#1d4ed8,#0f172a);padding:28px 24px;border-radius:14px 14px 0 0;text-align:left">
                <div style="color:#bfdbfe;font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px">SmartAttend Library</div>
                <h1 style="color:#fff;margin:0;font-size:22px;font-weight:800">{title}</h1>
              </div>
              <div style="background:#fff;padding:24px 28px;border-radius:0 0 14px 14px;border:1px solid #e2e8f0;border-top:none">
                <p style="margin:0;color:#0f172a;font-size:14px;line-height:1.7">Hello <strong>{user.name}</strong>,</p>
                <p style="margin:16px 0 0;color:#475569;font-size:14px;line-height:1.7">{content}</p>
                {button_html}
              </div>
            </div>
            """,
        )
        mail.send(msg)
    except Exception as exc:  # noqa: BLE001
        logger.error('Failed to send private library notification email to %s: %s', user.email, exc)
