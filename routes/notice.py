from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from extensions import db
from models.notice import Notice
from utils.decorators import admin_required
from datetime import datetime
from utils.time import utc_now_naive

notice_bp = Blueprint('notice', __name__)

CATEGORY_COLORS = {
    'general': 'primary', 'exam': 'warning', 'holiday': 'success',
    'event': 'info', 'fee': 'danger', 'urgent': 'danger',
}


def _visible_notices():
    q = Notice.query.filter(
        db.or_(Notice.expires_at == None, Notice.expires_at > utc_now_naive())
    )
    if current_user.role == 'student':
        q = q.filter(Notice.target_role.in_(['all', 'student']))
    elif current_user.role == 'teacher':
        q = q.filter(Notice.target_role.in_(['all', 'teacher']))
    elif current_user.role == 'parent':
        q = q.filter(Notice.target_role.in_(['all', 'student']))
    return q.order_by(Notice.is_pinned.desc(), Notice.created_at.desc())


def _can_view_notice(notice: Notice) -> bool:
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
    return render_template('notice/detail.html', notice=notice, colors=CATEGORY_COLORS)


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
                            expires_at=expires_at, author_id=current_user.id)
            db.session.add(notice)
            db.session.commit()
            flash('Notice posted.', 'success')
            return redirect(url_for('notice.list_notices'))

    return render_template('notice/form.html', notice=None)


@notice_bp.route('/notices/<int:nid>/edit', methods=['GET', 'POST'])
@login_required
def edit(nid):
    notice = Notice.query.get_or_404(nid)
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
    if current_user.role != 'admin' and notice.author_id != current_user.id:
        flash('Not authorised.', 'danger')
        return redirect(url_for('notice.list_notices'))
    db.session.delete(notice)
    db.session.commit()
    flash('Notice deleted.', 'info')
    return redirect(url_for('notice.list_notices'))
