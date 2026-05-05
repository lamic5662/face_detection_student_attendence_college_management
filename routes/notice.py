from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from extensions import db
from models.notice import Notice
from models.notice_read import NoticeRead
from datetime import datetime, timedelta
from utils.tenancy import current_college_id
from utils.time import utc_now_naive

notice_bp = Blueprint('notice', __name__)

CATEGORY_COLORS = {
    'general': 'primary', 'exam': 'warning', 'holiday': 'success',
    'event': 'info', 'fee': 'danger', 'urgent': 'danger',
}


def _visible_notices():
    q = Notice.query.filter(
        Notice.college_id == current_college_id(),
        db.or_(Notice.expires_at == None, Notice.expires_at > utc_now_naive())
    )
    if current_user.role == 'student':
        q = q.filter(Notice.target_role.in_(['all', 'student']))
    elif current_user.role == 'teacher':
        q = q.filter(Notice.target_role.in_(['all', 'teacher']))
    elif current_user.role == 'parent':
        q = q.filter(Notice.target_role.in_(['all', 'student']))
    return q.order_by(Notice.is_pinned.desc(), Notice.created_at.desc())


def _notification_scope_query():
    recent_cutoff = utc_now_naive() - timedelta(days=7)
    query = _visible_notices().filter(
        db.or_(
            Notice.is_pinned == True,
            Notice.created_at >= recent_cutoff,
        )
    )
    if current_user.is_authenticated:
        query = query.filter(
            ~Notice.read_receipts.any(
                db.and_(
                    NoticeRead.user_id == current_user.id,
                    NoticeRead.dismissed_at.isnot(None),
                )
            )
        )
    return query


def _read_notice_ids(notice_ids: list[int]) -> set[int]:
    if not notice_ids or not current_user.is_authenticated:
        return set()
    return {
        notice_id
        for (notice_id,) in db.session.query(NoticeRead.notice_id).filter(
            NoticeRead.user_id == current_user.id,
            NoticeRead.notice_id.in_(notice_ids),
        ).all()
    }


def _notification_payload(limit: int = 6) -> dict:
    scoped_query = _notification_scope_query()
    notices = scoped_query.limit(limit).all()
    notice_ids = [notice.id for notice in notices]
    read_notice_ids = _read_notice_ids(notice_ids)
    unread_count = scoped_query.filter(
        ~Notice.read_receipts.any(NoticeRead.user_id == current_user.id)
    ).count()
    return {
        'count': unread_count,
        'items': [
            {
                'id': notice.id,
                'title': notice.title,
                'content': notice.content[:140],
                'category': notice.category,
                'target_role': notice.target_role,
                'is_pinned': notice.is_pinned,
                'created_label': notice.created_at.strftime('%d %b'),
                'detail_url': url_for('notice.detail', nid=notice.id),
                'is_read': notice.id in read_notice_ids,
            }
            for notice in notices
        ],
    }


def _mark_notice_read(notice: Notice) -> None:
    if not current_user.is_authenticated:
        return
    existing = NoticeRead.query.filter_by(
        notice_id=notice.id,
        user_id=current_user.id,
    ).first()
    if existing is None:
        db.session.add(NoticeRead(
            college_id=current_user.college_id,
            notice_id=notice.id,
            user_id=current_user.id,
        ))
        db.session.commit()


def _dismiss_read_notifications() -> int:
    if not current_user.is_authenticated:
        return 0

    notice_ids = [notice.id for notice in _notification_scope_query().all()]
    if not notice_ids:
        return 0

    receipts = NoticeRead.query.filter(
        NoticeRead.user_id == current_user.id,
        NoticeRead.notice_id.in_(notice_ids),
        NoticeRead.dismissed_at.is_(None),
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


def _mark_notice_ids_read(notice_ids: list[int]) -> int:
    if not notice_ids or not current_user.is_authenticated:
        return 0

    existing_ids = _read_notice_ids(notice_ids)
    missing_ids = [notice_id for notice_id in notice_ids if notice_id not in existing_ids]
    if not missing_ids:
        return 0

    db.session.add_all(
        NoticeRead(college_id=current_user.college_id, notice_id=notice_id, user_id=current_user.id)
        for notice_id in missing_ids
    )
    db.session.commit()
    return len(missing_ids)


def _can_view_notice(notice: Notice) -> bool:
    if notice.college_id != current_user.college_id:
        return False
    if current_user.role == 'admin':
        return True
    if notice.is_expired:
        return False
    if current_user.role == 'teacher':
        return notice.target_role in ('all', 'teacher')
    if current_user.role in ('student', 'parent'):
        return notice.target_role in ('all', 'student')
    return False


@notice_bp.route('/notices')
@login_required
def list_notices():
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', '')
    q = _visible_notices()
    if category:
        q = q.filter_by(category=category)
    pagination = q.paginate(page=page, per_page=15, error_out=False)
    return render_template('notice/list.html',
                           pagination=pagination,
                           notices=pagination.items,
                           category=category,
                           colors=CATEGORY_COLORS)


@notice_bp.route('/notices/<int:nid>')
@login_required
def detail(nid):
    notice = db.session.get(Notice, nid)
    if notice is None:
        abort(404)
    if not _can_view_notice(notice):
        abort(404)
    _mark_notice_read(notice)
    return render_template('notice/detail.html', notice=notice, colors=CATEGORY_COLORS)


@notice_bp.route('/notices/feed')
@login_required
def feed():
    return jsonify(_notification_payload())


@notice_bp.route('/notices/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    notice_ids = [notice.id for notice in _notification_scope_query().all()]
    marked_count = _mark_notice_ids_read(notice_ids)

    if request.accept_mimetypes.best == 'application/json' or request.is_json:
        payload = _notification_payload()
        payload['marked_count'] = marked_count
        return jsonify(payload)

    if marked_count:
        flash(f'Marked {marked_count} notification(s) as read.', 'success')
    else:
        flash('No unread notifications to mark.', 'info')
    return redirect(url_for('notice.list_notices'))


@notice_bp.route('/notices/delete-read', methods=['POST'])
@login_required
def delete_read():
    deleted_count = _dismiss_read_notifications()

    if request.accept_mimetypes.best == 'application/json' or request.is_json:
        payload = _notification_payload()
        payload['deleted_count'] = deleted_count
        return jsonify(payload)

    if deleted_count:
        flash(f'Removed {deleted_count} read notification(s) from the tray.', 'success')
    else:
        flash('No read notifications to remove.', 'info')
    return redirect(url_for('notice.list_notices'))


@notice_bp.route('/notices/create', methods=['GET', 'POST'])
@login_required
def create():
    if current_user.role not in ('admin', 'teacher'):
        flash('Not authorised.', 'danger')
        return redirect(url_for('notice.list_notices'))

    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        content     = request.form.get('content', '').strip()
        category    = request.form.get('category', 'general')
        target_role = request.form.get('target_role', 'all')
        is_pinned   = request.form.get('is_pinned') == 'on'
        expires_str = request.form.get('expires_at', '').strip()

        if not title or not content:
            flash('Title and content are required.', 'danger')
        else:
            expires_at = None
            if expires_str:
                try:
                    expires_at = datetime.fromisoformat(expires_str)
                except ValueError:
                    pass

            notice = Notice(title=title, content=content, category=category,
                            target_role=target_role, is_pinned=is_pinned,
                            expires_at=expires_at, author_id=current_user.id,
                            college_id=current_user.college_id)
            db.session.add(notice)
            db.session.commit()
            flash('Notice posted.', 'success')
            return redirect(url_for('notice.list_notices'))

    return render_template('notice/form.html', notice=None)


@notice_bp.route('/notices/<int:nid>/edit', methods=['GET', 'POST'])
@login_required
def edit(nid):
    notice = Notice.query.get_or_404(nid)
    if notice.college_id != current_user.college_id:
        flash('Not authorised.', 'danger')
        return redirect(url_for('notice.list_notices'))
    if current_user.role not in ('admin', 'teacher') or \
       (current_user.role == 'teacher' and notice.author_id != current_user.id):
        flash('Not authorised.', 'danger')
        return redirect(url_for('notice.list_notices'))

    if request.method == 'POST':
        notice.title       = request.form.get('title', '').strip()
        notice.content     = request.form.get('content', '').strip()
        notice.category    = request.form.get('category', 'general')
        notice.target_role = request.form.get('target_role', 'all')
        notice.is_pinned   = request.form.get('is_pinned') == 'on'
        expires_str        = request.form.get('expires_at', '').strip()
        if expires_str:
            try:
                notice.expires_at = datetime.fromisoformat(expires_str)
            except ValueError:
                flash('Invalid expiry date/time.', 'danger')
                return redirect(request.url)
        else:
            notice.expires_at = None
        db.session.commit()
        flash('Notice updated.', 'success')
        return redirect(url_for('notice.list_notices'))

    return render_template('notice/form.html', notice=notice)


@notice_bp.route('/notices/<int:nid>/delete', methods=['POST'])
@login_required
def delete(nid):
    notice = Notice.query.get_or_404(nid)
    if notice.college_id != current_user.college_id:
        flash('Not authorised.', 'danger')
        return redirect(url_for('notice.list_notices'))
    if current_user.role != 'admin' and notice.author_id != current_user.id:
        flash('Not authorised.', 'danger')
        return redirect(url_for('notice.list_notices'))
    db.session.delete(notice)
    db.session.commit()
    flash('Notice deleted.', 'info')
    return redirect(url_for('notice.list_notices'))
