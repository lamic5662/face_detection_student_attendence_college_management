import os
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, abort, current_app)
from flask_login import login_required, current_user
from extensions import db
from models.leave import LeaveRequest
from models.subject import Subject
from models.student import Student
from models.teacher import Teacher
from models.notice import Notice
from utils.decorators import student_required, teacher_required, admin_required
from datetime import datetime, date
from utils.time import utc_now_naive

leave_bp = Blueprint('leave', __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _current_student():
    return current_user.student_profile

def _current_teacher():
    return current_user.teacher_profile


def _auto_notify_teacher_leave(lr: LeaveRequest):
    """Create a notice to all students when a teacher leave is approved."""
    teacher  = lr.teacher
    subjects = teacher.subjects
    if not subjects:
        return

    subj_names = ', '.join(s.name for s in subjects)
    dept_name  = teacher.department.name if teacher.department else 'your department'

    notice = Notice(
        title      = f'Class Cancellation — {teacher.user.name} on Leave',
        content    = (
            f'{teacher.user.name} ({teacher.designation or "Faculty"}, {dept_name}) '
            f'has been granted leave from {lr.from_date.strftime("%d %b %Y")} '
            f'to {lr.to_date.strftime("%d %b %Y")} ({lr.days} day(s)).\n\n'
            f'Affected subject(s): {subj_names}.\n\n'
            f'Classes for these subjects may be rescheduled. '
            f'Please check the notice board for updates.'
        ),
        category    = 'urgent',
        target_role = 'student',
        is_pinned   = True,
        author_id   = current_user.id,
    )
    db.session.add(notice)


# ─────────────────────────────────────────────────────────────────────────────
# Student routes
# ─────────────────────────────────────────────────────────────────────────────

@leave_bp.route('/student/leaves')
@login_required
@student_required
def student_leaves():
    student  = _current_student()
    subjects = Subject.query.filter_by(
        department_id=student.department_id,
        semester=student.semester
    ).all()
    leaves = (LeaveRequest.query
              .filter_by(student_id=student.id)
              .order_by(LeaveRequest.created_at.desc())
              .all())
    return render_template('student/leaves.html',
                           student=student, subjects=subjects,
                           leaves=leaves, today=date.today().isoformat())


@leave_bp.route('/student/leaves/apply', methods=['POST'])
@login_required
@student_required
def apply_leave():
    student    = _current_student()
    scope      = request.form.get('scope', 'subject')   # 'subject' | 'fullday'
    from_str   = request.form.get('from_date', '').strip()
    to_str     = request.form.get('to_date', '').strip()
    reason     = request.form.get('reason', '').strip()
    subject_id = request.form.get('subject_id', type=int)

    if not all([from_str, to_str, reason]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('leave.student_leaves'))

    try:
        fd = date.fromisoformat(from_str)
        td = date.fromisoformat(to_str)
    except ValueError:
        flash('Invalid date.', 'danger')
        return redirect(url_for('leave.student_leaves'))

    if td < fd:
        flash('End date cannot be before start date.', 'danger')
        return redirect(url_for('leave.student_leaves'))

    if scope == 'subject':
        if not subject_id:
            flash('Please select a subject.', 'danger')
            return redirect(url_for('leave.student_leaves'))
        leave_type = 'student_subject'
    else:
        leave_type = 'student_fullday'
        subject_id = None

    lr = LeaveRequest(
        leave_type = leave_type,
        student_id = student.id,
        subject_id = subject_id,
        from_date  = fd,
        to_date    = td,
        reason     = reason,
        ref_number = LeaveRequest.generate_ref(),
    )
    db.session.add(lr)
    db.session.commit()
    flash('Leave application submitted. Ref: ' + lr.ref_number, 'success')
    return redirect(url_for('leave.student_leaves'))


@leave_bp.route('/student/leaves/<int:lid>/cancel', methods=['POST'])
@login_required
@student_required
def cancel_leave(lid):
    lr = LeaveRequest.query.get_or_404(lid)
    if lr.student_id != _current_student().id:
        abort(403)
    if lr.status != 'pending':
        flash('Cannot cancel a reviewed leave request.', 'warning')
    else:
        db.session.delete(lr)
        db.session.commit()
        flash('Leave application cancelled.', 'info')
    return redirect(url_for('leave.student_leaves'))


# ─────────────────────────────────────────────────────────────────────────────
# Teacher routes
# ─────────────────────────────────────────────────────────────────────────────

@leave_bp.route('/teacher/leaves')
@login_required
@teacher_required
def teacher_leaves():
    teacher     = _current_teacher()
    subject_ids = [s.id for s in teacher.subjects]

    # Student subject-leave requests waiting for this teacher
    stu_pending  = (LeaveRequest.query
                    .filter(LeaveRequest.subject_id.in_(subject_ids),
                            LeaveRequest.leave_type == 'student_subject',
                            LeaveRequest.status     == 'pending')
                    .order_by(LeaveRequest.created_at.asc()).all())

    stu_reviewed = (LeaveRequest.query
                    .filter(LeaveRequest.subject_id.in_(subject_ids),
                            LeaveRequest.leave_type == 'student_subject',
                            LeaveRequest.status     != 'pending')
                    .order_by(LeaveRequest.reviewed_at.desc())
                    .limit(40).all())

    # Teacher's own leave applications to admin
    own_leaves = (LeaveRequest.query
                  .filter_by(teacher_id=teacher.id, leave_type='teacher')
                  .order_by(LeaveRequest.created_at.desc()).all())

    subjects = teacher.subjects
    return render_template('teacher/leaves.html',
                           stu_pending=stu_pending, stu_reviewed=stu_reviewed,
                           own_leaves=own_leaves, subjects=subjects,
                           today=date.today().isoformat())


@leave_bp.route('/teacher/leaves/apply', methods=['POST'])
@login_required
@teacher_required
def teacher_apply_leave():
    teacher  = _current_teacher()
    from_str = request.form.get('from_date', '').strip()
    to_str   = request.form.get('to_date', '').strip()
    reason   = request.form.get('reason', '').strip()

    if not all([from_str, to_str, reason]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('leave.teacher_leaves'))

    try:
        fd = date.fromisoformat(from_str)
        td = date.fromisoformat(to_str)
    except ValueError:
        flash('Invalid date.', 'danger')
        return redirect(url_for('leave.teacher_leaves'))

    if td < fd:
        flash('End date cannot be before start date.', 'danger')
        return redirect(url_for('leave.teacher_leaves'))

    lr = LeaveRequest(
        leave_type = 'teacher',
        teacher_id = teacher.id,
        from_date  = fd,
        to_date    = td,
        reason     = reason,
        ref_number = LeaveRequest.generate_ref(),
    )
    db.session.add(lr)
    db.session.commit()
    flash('Leave application submitted to admin. Ref: ' + lr.ref_number, 'success')
    return redirect(url_for('leave.teacher_leaves'))


@leave_bp.route('/teacher/leaves/<int:lid>/review', methods=['POST'])
@login_required
@teacher_required
def review_leave(lid):
    lr = LeaveRequest.query.get_or_404(lid)
    if (lr.leave_type != 'student_subject'
            or lr.subject.teacher_id != _current_teacher().id):
        abort(403)

    action = request.form.get('action')
    remark = request.form.get('remark', '').strip()

    if action not in ('approved', 'rejected'):
        flash('Invalid action.', 'danger')
        return redirect(url_for('leave.teacher_leaves'))

    lr.status          = action
    lr.teacher_remark  = remark
    lr.approver_id     = current_user.id
    lr.reviewed_at     = utc_now_naive()
    db.session.commit()
    flash(f'Leave {action} for {lr.student.user.name}.', 'success')

    # Email notification (best-effort)
    if lr.student.user.email:
        try:
            from services.notification_service import send_leave_reviewed
            send_leave_reviewed(
                lr.student.user.email, lr.student.user.name,
                lr.subject.name, str(lr.from_date), str(lr.to_date),
                action, remark
            )
        except Exception:
            pass

    return redirect(url_for('leave.teacher_leaves'))


# ─────────────────────────────────────────────────────────────────────────────
# Admin routes
# ─────────────────────────────────────────────────────────────────────────────

@leave_bp.route('/admin/leaves')
@login_required
@admin_required
def admin_leaves():
    tab = request.args.get('tab', 'student')  # 'student' | 'teacher'

    stu_pending  = (LeaveRequest.query
                    .filter_by(leave_type='student_fullday', status='pending')
                    .order_by(LeaveRequest.created_at.asc()).all())
    stu_reviewed = (LeaveRequest.query
                    .filter_by(leave_type='student_fullday')
                    .filter(LeaveRequest.status != 'pending')
                    .order_by(LeaveRequest.reviewed_at.desc())
                    .limit(50).all())

    tch_pending  = (LeaveRequest.query
                    .filter_by(leave_type='teacher', status='pending')
                    .order_by(LeaveRequest.created_at.asc()).all())
    tch_reviewed = (LeaveRequest.query
                    .filter_by(leave_type='teacher')
                    .filter(LeaveRequest.status != 'pending')
                    .order_by(LeaveRequest.reviewed_at.desc())
                    .limit(50).all())

    return render_template('admin/leaves.html',
                           tab=tab,
                           stu_pending=stu_pending, stu_reviewed=stu_reviewed,
                           tch_pending=tch_pending, tch_reviewed=tch_reviewed)


@leave_bp.route('/admin/leaves/<int:lid>/review', methods=['POST'])
@login_required
@admin_required
def admin_review_leave(lid):
    lr     = LeaveRequest.query.get_or_404(lid)
    action = request.form.get('action')
    remark = request.form.get('remark', '').strip()
    tab    = 'teacher' if lr.leave_type == 'teacher' else 'student'

    if action not in ('approved', 'rejected'):
        flash('Invalid action.', 'danger')
        return redirect(url_for('leave.admin_leaves', tab=tab))

    lr.status       = action
    lr.teacher_remark = remark
    lr.approver_id  = current_user.id
    lr.reviewed_at  = utc_now_naive()

    if action == 'approved' and lr.leave_type == 'teacher':
        _auto_notify_teacher_leave(lr)

    db.session.commit()
    flash(f'Leave {action} for {lr.applicant_name}. Ref: {lr.ref_number}', 'success')
    return redirect(url_for('leave.admin_leaves', tab=tab))


# ─────────────────────────────────────────────────────────────────────────────
# Admin delete routes
# ─────────────────────────────────────────────────────────────────────────────

@leave_bp.route('/admin/leaves/<int:lid>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_leave(lid):
    lr  = LeaveRequest.query.get_or_404(lid)
    tab = 'teacher' if lr.leave_type == 'teacher' else 'student'
    db.session.delete(lr)
    db.session.commit()
    flash(f'Leave record {lr.ref_number} deleted.', 'info')
    return redirect(url_for('leave.admin_leaves', tab=tab))


@leave_bp.route('/admin/leaves/bulk-delete', methods=['POST'])
@login_required
@admin_required
def admin_bulk_delete_leaves():
    tab   = request.form.get('tab', 'student')
    scope = request.form.get('scope', 'rejected')   # 'rejected' | 'all_reviewed'
    leave_type = 'teacher' if tab == 'teacher' else 'student_fullday'

    q = LeaveRequest.query.filter_by(leave_type=leave_type)
    if scope == 'rejected':
        q = q.filter_by(status='rejected')
    else:
        q = q.filter(LeaveRequest.status != 'pending')

    count = q.count()
    q.delete(synchronize_session=False)
    db.session.commit()
    flash(f'{count} leave record(s) deleted.', 'info')
    return redirect(url_for('leave.admin_leaves', tab=tab))


# ─────────────────────────────────────────────────────────────────────────────
# Leave letter view (all roles)
# ─────────────────────────────────────────────────────────────────────────────

@leave_bp.route('/leave/<int:lid>/letter')
@login_required
def view_letter(lid):
    lr = LeaveRequest.query.get_or_404(lid)

    # Permission check
    if current_user.role == 'student':
        if not lr.student or lr.student_id != _current_student().id:
            abort(403)
    elif current_user.role == 'teacher':
        t = _current_teacher()
        own   = (lr.leave_type == 'teacher' and lr.teacher_id == t.id)
        subj  = (lr.leave_type == 'student_subject'
                 and lr.subject and lr.subject.teacher_id == t.id)
        if not (own or subj):
            abort(403)
    elif current_user.role != 'admin':
        abort(403)

    from models.setting import CollegeSetting
    cs        = CollegeSetting.get()
    back_url  = _back_url_for(lr)
    return render_template('leave/letter.html',
                           lr=lr, cs=cs, back_url=back_url)


def _back_url_for(lr: LeaveRequest) -> str:
    if current_user.role == 'student':
        return url_for('leave.student_leaves')
    if current_user.role == 'teacher':
        return url_for('leave.teacher_leaves')
    tab = 'teacher' if lr.leave_type == 'teacher' else 'student'
    return url_for('leave.admin_leaves', tab=tab)
