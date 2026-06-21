from __future__ import annotations

from datetime import timedelta

from flask import url_for

from extensions import db
from models.notice import Notice
from models.notice_read import NoticeRead
from models.user_notification import UserNotification
from utils.time import utc_now_naive


def visible_notice_query_for_user(user):
    query = Notice.query.filter(
        Notice.college_id == user.college_id,
        db.or_(Notice.expires_at.is_(None), Notice.expires_at > utc_now_naive()),
    )
    if user.role == 'student':
        query = query.filter(Notice.target_role.in_(['all', 'student']))
    elif user.role == 'teacher':
        query = query.filter(Notice.target_role.in_(['all', 'teacher']))
    elif user.role == 'parent':
        query = query.filter(Notice.target_role.in_(['all', 'student']))
    return query


def visible_private_notification_query_for_user(user):
    recent_cutoff = utc_now_naive() - timedelta(days=30)
    return (
        UserNotification.query
        .filter(
            UserNotification.college_id == user.college_id,
            UserNotification.user_id == user.id,
            UserNotification.dismissed_at.is_(None),
            db.or_(
                UserNotification.is_pinned.is_(True),
                UserNotification.created_at >= recent_cutoff,
                UserNotification.read_at.is_(None),
            ),
        )
    )


def private_notification_board_url(user) -> str:
    if user.role in {'student', 'teacher'}:
        return url_for('library.my_loans')
    if user.role == 'parent':
        return url_for('library.parent_overview')
    return url_for('library.admin_dashboard')


def _notice_items_for_user(user):
    recent_cutoff = utc_now_naive() - timedelta(days=7)
    scoped_query = visible_notice_query_for_user(user).filter(
        db.or_(
            Notice.is_pinned.is_(True),
            Notice.created_at >= recent_cutoff,
        )
    )
    scoped_query = scoped_query.filter(
        ~Notice.read_receipts.any(
            db.and_(
                NoticeRead.user_id == user.id,
                NoticeRead.dismissed_at.isnot(None),
            )
        )
    )
    notices = scoped_query.all()
    notice_ids = [notice.id for notice in notices]
    if notice_ids:
        read_notice_ids = {
            notice_id
            for (notice_id,) in db.session.query(NoticeRead.notice_id).filter(
                NoticeRead.user_id == user.id,
                NoticeRead.notice_id.in_(notice_ids),
            ).all()
        }
    else:
        read_notice_ids = set()

    items = [
        {
            'id': f'notice:{notice.id}',
            'title': notice.title,
            'content': notice.content[:140],
            'category': notice.category,
            'target_role': notice.target_role,
            'is_pinned': notice.is_pinned,
            'created_label': notice.created_at.strftime('%d %b'),
            'created_at': notice.created_at,
            'detail_url': url_for('notice.detail', nid=notice.id),
            'is_read': notice.id in read_notice_ids,
        }
        for notice in notices
    ]
    unread_count = scoped_query.filter(
        ~Notice.read_receipts.any(NoticeRead.user_id == user.id)
    ).count()
    return items, unread_count


def _private_items_for_user(user):
    notifications = (
        visible_private_notification_query_for_user(user)
        .order_by(UserNotification.is_pinned.desc(), UserNotification.created_at.desc())
        .all()
    )
    items = [
        {
            'id': f'private:{notification.id}',
            'title': notification.title,
            'content': notification.content[:140],
            'category': notification.category,
            'target_role': 'private',
            'is_pinned': notification.is_pinned,
            'created_label': notification.created_at.strftime('%d %b'),
            'created_at': notification.created_at,
            'detail_url': url_for('notice.open_user_notification', notification_id=notification.id),
            'is_read': notification.is_read,
        }
        for notification in notifications
    ]
    unread_count = (
        visible_private_notification_query_for_user(user)
        .filter(UserNotification.read_at.is_(None))
        .count()
    )
    return items, unread_count


def notification_center_payload(user, *, include_public_notices: bool, limit: int = 6) -> dict:
    items = []
    unread_count = 0

    if include_public_notices:
        public_items, public_unread = _notice_items_for_user(user)
        items.extend(public_items)
        unread_count += public_unread

    private_items, private_unread = _private_items_for_user(user)
    items.extend(private_items)
    unread_count += private_unread

    items.sort(key=lambda item: (item['is_pinned'], item['created_at']), reverse=True)
    items = items[:limit]
    for item in items:
        item.pop('created_at', None)

    return {'count': unread_count, 'items': items}


def mark_all_notifications_read(user, *, include_public_notices: bool) -> int:
    marked_count = 0

    if include_public_notices:
        recent_cutoff = utc_now_naive() - timedelta(days=7)
        notice_ids = [
            notice.id
            for notice in visible_notice_query_for_user(user)
            .filter(db.or_(Notice.is_pinned.is_(True), Notice.created_at >= recent_cutoff))
            .all()
        ]
        existing_ids = {
            notice_id
            for (notice_id,) in db.session.query(NoticeRead.notice_id).filter(
                NoticeRead.user_id == user.id,
                NoticeRead.notice_id.in_(notice_ids),
            ).all()
        }
        missing_ids = [notice_id for notice_id in notice_ids if notice_id not in existing_ids]
        if missing_ids:
            db.session.add_all(
                NoticeRead(college_id=user.college_id, notice_id=notice_id, user_id=user.id)
                for notice_id in missing_ids
            )
            marked_count += len(missing_ids)

    private_unread = (
        visible_private_notification_query_for_user(user)
        .filter(UserNotification.read_at.is_(None))
        .all()
    )
    now = utc_now_naive()
    for notification in private_unread:
        notification.read_at = now
    marked_count += len(private_unread)

    if marked_count:
        db.session.commit()
    return marked_count


def dismiss_read_notifications(user, *, include_public_notices: bool) -> int:
    dismissed_count = 0
    now = utc_now_naive()

    if include_public_notices:
        recent_cutoff = utc_now_naive() - timedelta(days=7)
        notice_ids = [
            notice.id
            for notice in visible_notice_query_for_user(user)
            .filter(db.or_(Notice.is_pinned.is_(True), Notice.created_at >= recent_cutoff))
            .all()
        ]
        receipts = NoticeRead.query.filter(
            NoticeRead.user_id == user.id,
            NoticeRead.notice_id.in_(notice_ids),
            NoticeRead.dismissed_at.is_(None),
        ).all()
        for receipt in receipts:
            receipt.dismissed_at = now
        dismissed_count += len(receipts)

    private_read = (
        visible_private_notification_query_for_user(user)
        .filter(UserNotification.read_at.isnot(None), UserNotification.dismissed_at.is_(None))
        .all()
    )
    for notification in private_read:
        notification.dismissed_at = now
    dismissed_count += len(private_read)

    if dismissed_count:
        db.session.commit()
    return dismissed_count
