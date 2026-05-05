from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, jsonify, send_file, current_app, abort)
from flask_login import login_required, current_user
from extensions import db, csrf, limiter
from models.student import Student
from models.subject import Subject
from models.attendance import AttendanceSession, AttendanceRecord
from models.department import Department
from models.notice import Notice
from models.exam import Exam
from models.content import TeacherContent, content_extension, is_allowed_content_upload
from models.assignment import AssignmentSubmission
from models.parent import TeacherStatus
from utils.decorators import teacher_required
from services.face_service import decode_base64_image, recognize_faces
from services.liveness_service import liveness_manager, process_frame_for_liveness
from services.notification_service import send_session_summary, send_low_attendance_alert
from services.report_service import (generate_session_report, generate_subject_report,
                                     dataframe_to_excel_bytes, dataframe_to_csv_bytes)
from datetime import datetime, date, timedelta
import io
import os
from utils.content_storage import build_content_relpath, resolve_content_path
from utils.assignment_storage import build_submission_relpath, resolve_submission_path
from utils.dashboard import build_dashboard_preferences
from utils.time import utc_now_naive

teacher_bp = Blueprint('teacher', __name__)


def _current_teacher():
    return current_user.teacher_profile


def _teacher_owns_session(session: AttendanceSession) -> bool:
    return session.teacher_id == _current_teacher().id


def _teacher_owns_subject(subject: Subject) -> bool:
    return subject.teacher_id == _current_teacher().id


def _assignment_for_teacher(cid: int, teacher):
    return TeacherContent.query.filter_by(
        id=cid,
        college_id=teacher.college_id,
        teacher_id=teacher.id,
        content_type='assignment',
    ).first_or_404()


def _next_unreviewed_submission_id(content_id: int, current_submission_id: int | None = None) -> int | None:
    submissions = (
        AssignmentSubmission.query
        .join(Student, Student.id == AssignmentSubmission.student_id)
        .filter(
            AssignmentSubmission.college_id == current_user.college_id,
            AssignmentSubmission.content_id == content_id,
            AssignmentSubmission.status == 'submitted',
        )
        .order_by(Student.roll_number, AssignmentSubmission.submitted_at, AssignmentSubmission.id)
        .all()
    )
    if not submissions:
        return None
    if current_submission_id is None:
        return submissions[0].id

    ids = [submission.id for submission in submissions]
    for sid in ids:
        if sid != current_submission_id:
            return sid
    return None


@teacher_bp.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    dashboard_prefs = build_dashboard_preferences(current_user)
    teacher = _current_teacher()
    subjects = teacher.subjects
    active_session = AttendanceSession.query.filter_by(
        college_id=teacher.college_id, teacher_id=teacher.id, status='active'
    ).first()
    recent_sessions = AttendanceSession.query.filter_by(
        college_id=teacher.college_id, teacher_id=teacher.id
    ).order_by(AttendanceSession.created_at.desc()).limit(5).all()

    stats = {
        'total_subjects': len(subjects),
        'total_sessions': AttendanceSession.query.filter_by(college_id=teacher.college_id, teacher_id=teacher.id).count(),
        'today_sessions': AttendanceSession.query.filter_by(
            college_id=teacher.college_id, teacher_id=teacher.id, date=date.today()
        ).count(),
    }
    # Upcoming exams for subjects this teacher teaches
    today = date.today()
    subject_ids = [s.id for s in subjects]
    upcoming_exams = Exam.query.filter(
        Exam.college_id == teacher.college_id,
        Exam.subject_id.in_(subject_ids),
        Exam.exam_date >= today,
        Exam.exam_date <= today + timedelta(days=7)
    ).order_by(Exam.exam_date).limit(5).all() if subject_ids else []

    # Active notices
    notices = Notice.query.filter(
        Notice.college_id == teacher.college_id,
        Notice.target_role.in_(['all', 'teacher']),
        db.or_(Notice.expires_at == None, Notice.expires_at > utc_now_naive())
    ).order_by(Notice.is_pinned.desc(), Notice.created_at.desc()).limit(4).all()

    teacher_status = TeacherStatus.query.filter_by(college_id=teacher.college_id, teacher_id=teacher.id).first()

    return render_template('teacher/dashboard.html',
                           dashboard_prefs=dashboard_prefs,
                           teacher=teacher, subjects=subjects,
                           active_session=active_session,
                           recent_sessions=recent_sessions, stats=stats,
                           upcoming_exams=upcoming_exams,
                           notices=notices, today=today,
                           teacher_status=teacher_status)


# ─── Sessions ────────────────────────────────────────────────────────────────

@teacher_bp.route('/sessions')
@login_required
@teacher_required
def sessions():
    teacher = _current_teacher()
    subject_id = request.args.get('subject_id', type=int)
    date_from  = request.args.get('date_from')
    date_to    = request.args.get('date_to')
    status_filter = request.args.get('status', '')

    query = AttendanceSession.query.filter_by(college_id=teacher.college_id, teacher_id=teacher.id)
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    if status_filter:
        query = query.filter_by(status=status_filter)
    if date_from:
        try:
            query = query.filter(AttendanceSession.date >= date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(AttendanceSession.date <= date.fromisoformat(date_to))
        except ValueError:
            pass

    all_sessions = query.order_by(
        AttendanceSession.date.desc(), AttendanceSession.start_time.desc()
    ).all()
    return render_template('teacher/sessions.html',
                           sessions=all_sessions, subjects=teacher.subjects,
                           selected_subject_id=subject_id,
                           date_from=date_from or '', date_to=date_to or '',
                           selected_status=status_filter)


@teacher_bp.route('/sessions/start', methods=['POST'])
@login_required
@teacher_required
def start_session():
    teacher = _current_teacher()
    subject_id = request.form.get('subject_id', type=int)
    subject = Subject.query.filter_by(id=subject_id, college_id=teacher.college_id).first_or_404()

    if subject.teacher_id != teacher.id:
        flash('Unauthorised subject.', 'danger')
        return redirect(url_for('teacher.sessions'))

    # Allow only one active session per teacher
    existing = AttendanceSession.query.filter_by(
        college_id=teacher.college_id, teacher_id=teacher.id, status='active'
    ).first()
    if existing:
        flash('You already have an active session. Please complete it first.', 'warning')
        return redirect(url_for('teacher.live_attendance', session_id=existing.id))

    now = utc_now_naive()
    session = AttendanceSession(
        college_id=teacher.college_id,
        subject_id=subject_id,
        teacher_id=teacher.id,
        date=now.date(),
        start_time=now.time(),
    )
    db.session.add(session)
    db.session.flush()

    # Pre-populate records (all absent by default)
    students = Student.query.filter_by(
        college_id=subject.college_id,
        department_id=subject.department_id,
        semester=subject.semester
    ).all()
    for student in students:
        db.session.add(AttendanceRecord(
            college_id=student.college_id,
            session_id=session.id,
            student_id=student.id,
            status='absent'
        ))

    db.session.commit()
    flash(f'Session started for {subject.name}.', 'success')
    return redirect(url_for('teacher.live_attendance', session_id=session.id))


@teacher_bp.route('/sessions/<int:session_id>/live')
@login_required
@teacher_required
def live_attendance(session_id):
    teacher = _current_teacher()
    session = AttendanceSession.query.filter_by(id=session_id, college_id=teacher.college_id).first_or_404()

    if session.teacher_id != teacher.id:
        flash('Unauthorised.', 'danger')
        return redirect(url_for('teacher.sessions'))

    records = AttendanceRecord.query.filter_by(college_id=teacher.college_id, session_id=session_id).all()
    students_info = []
    for r in records:
        students_info.append({
            'id': r.student.id,
            'name': r.student.user.name,
            'roll': r.student.roll_number,
            'status': r.status,
            'face_enrolled': r.student.is_face_enrolled,
            'liveness': r.liveness_verified,
            'marked_at': r.marked_at.strftime('%H:%M:%S') if r.marked_at else None,
        })

    return render_template('teacher/live_attendance.html',
                           session=session, students_info=students_info,
                           subject=session.subject)


@teacher_bp.route('/sessions/<int:session_id>/process_frame', methods=['POST'])
@csrf.exempt
@limiter.limit('300 per minute', methods=['POST'])
@login_required
@teacher_required
def process_frame(session_id):
    """Receive a webcam frame, run face recognition + liveness, mark attendance."""
    session = AttendanceSession.query.filter_by(id=session_id, college_id=current_user.college_id).first_or_404()
    if not _teacher_owns_session(session):
        return jsonify({'error': 'Unauthorised'}), 403
    if session.status != 'active':
        return jsonify({'error': 'Session not active'}), 400

    data = request.get_json(silent=True)
    if not data or 'frame' not in data:
        return jsonify({'error': 'No frame data'}), 400

    frame = decode_base64_image(data['frame'])
    if frame is None:
        return jsonify({'error': 'Could not decode frame'}), 400

    # Load enrolled students for this session's subject
    subject = session.subject
    students = Student.query.filter_by(
        college_id=subject.college_id,
        department_id=subject.department_id,
        semester=subject.semester
    ).all()

    known_encodings = []
    known_ids = []
    for s in students:
        enc = s.get_face_encoding()
        if enc is not None:
            known_encodings.append(enc)
            known_ids.append(s.id)

    tolerance = current_app.config['FACE_RECOGNITION_TOLERANCE']
    recognitions = recognize_faces(frame, known_encodings, known_ids, tolerance)

    results = []
    for rec in recognitions:
        student_id = rec['student_id']
        if student_id is None:
            results.append({'student_id': None, 'message': 'Unknown face'})
            continue

        liveness_key = f"{session_id}_{student_id}"
        already_verified = liveness_manager.is_verified(liveness_key)

        if not already_verified:
            state = liveness_manager.get_state(liveness_key)
            liveness_result = process_frame_for_liveness(
                frame, state, face_location=rec['location']
            )
            verified = liveness_result['verified']
        else:
            verified = True

        record = AttendanceRecord.query.filter_by(
            college_id=subject.college_id,
            session_id=session_id, student_id=student_id
        ).first()

        if record and record.status == 'absent' and verified:
            record.status = 'present'
            record.marked_at = utc_now_naive()
            record.liveness_verified = True
            record.confidence_score = rec['confidence']
            db.session.commit()

        student = next(s for s in students if s.id == student_id)
        results.append({
            'student_id': student_id,
            'name': student.user.name,
            'roll': student.roll_number,
            'confidence': rec['confidence'],
            'liveness_verified': verified,
            'status': record.status if record else 'unknown',
        })

    return jsonify({'results': results})


@teacher_bp.route('/sessions/<int:session_id>/manual_mark', methods=['POST'])
@csrf.exempt
@login_required
@teacher_required
def manual_mark(session_id):
    """Teacher manually toggles a student present/absent."""
    session = AttendanceSession.query.filter_by(id=session_id, college_id=_current_teacher().college_id).first_or_404()
    if session.teacher_id != _current_teacher().id:
        return jsonify({'error': 'Unauthorised'}), 403

    data = request.get_json()
    student_id = data.get('student_id')
    new_status  = data.get('status')   # 'present' or 'absent'

    if new_status not in ('present', 'absent'):
        return jsonify({'error': 'Invalid status'}), 400

    record = AttendanceRecord.query.filter_by(
        college_id=_current_teacher().college_id, session_id=session_id, student_id=student_id
    ).first_or_404()

    record.status = new_status
    record.liveness_verified = False
    record.marked_at = utc_now_naive() if new_status == 'present' else None
    db.session.commit()

    return jsonify({
        'success': True,
        'student_id': student_id,
        'status': new_status,
        'marked_at': record.marked_at.strftime('%H:%M:%S') if record.marked_at else None,
    })


@teacher_bp.route('/sessions/<int:session_id>/cancel', methods=['POST'])
@login_required
@teacher_required
def cancel_session(session_id):
    teacher = _current_teacher()
    session = AttendanceSession.query.filter_by(id=session_id, college_id=teacher.college_id).first_or_404()

    if session.teacher_id != teacher.id:
        flash('Unauthorised.', 'danger')
        return redirect(url_for('teacher.sessions'))

    if session.status != 'active':
        flash('Only active sessions can be cancelled.', 'warning')
        return redirect(url_for('teacher.sessions'))

    session.status = 'cancelled'
    session.end_time = utc_now_naive().time()
    db.session.commit()

    liveness_manager.cleanup_session(session_id)
    flash('Session cancelled.', 'info')
    return redirect(url_for('teacher.sessions'))


@teacher_bp.route('/sessions/<int:session_id>/complete', methods=['POST'])
@login_required
@teacher_required
def complete_session(session_id):
    teacher = _current_teacher()
    session = AttendanceSession.query.filter_by(id=session_id, college_id=teacher.college_id).first_or_404()

    if session.teacher_id != teacher.id:
        flash('Unauthorised.', 'danger')
        return redirect(url_for('teacher.sessions'))

    session.status = 'completed'
    session.end_time = utc_now_naive().time()
    db.session.commit()

    liveness_manager.cleanup_session(session_id)

    # Send alerts for low attendance
    threshold = current_app.config['LOW_ATTENDANCE_THRESHOLD']
    for record in session.records:
        student = record.student
        pct = student.get_attendance_percentage(subject_id=session.subject_id)
        if pct < threshold and student.user.email:
            send_low_attendance_alert(
                student.user.email, student.user.name,
                session.subject.name, pct
            )

    try:
        send_session_summary(
            teacher.user.email, teacher.user.name,
            session.subject.name, str(session.date),
            session.present_count, session.total_students
        )
    except Exception:
        pass

    flash('Session completed successfully.', 'success')
    return redirect(url_for('teacher.sessions'))


@teacher_bp.route('/sessions/<int:session_id>/status')
@login_required
@teacher_required
def session_status(session_id):
    session = AttendanceSession.query.filter_by(id=session_id, college_id=current_user.college_id).first_or_404()
    if not _teacher_owns_session(session):
        return jsonify({'error': 'Unauthorised'}), 403
    records = []
    for r in session.records:
        records.append({
            'student_id': r.student_id,
            'name': r.student.user.name,
            'roll': r.student.roll_number,
            'status': r.status,
            'liveness': r.liveness_verified,
            'marked_at': r.marked_at.strftime('%H:%M:%S') if r.marked_at else None,
        })
    return jsonify({
        'session_status': session.status,
        'present': session.present_count,
        'absent': session.absent_count,
        'total': session.total_students,
        'records': records,
    })


# ─── Print Sheet ─────────────────────────────────────────────────────────────

@teacher_bp.route('/sessions/<int:session_id>/print')
@login_required
@teacher_required
def print_session(session_id):
    session = AttendanceSession.query.get_or_404(session_id)
    if session.teacher_id != _current_teacher().id:
        flash('Unauthorised.', 'danger')
        return redirect(url_for('teacher.sessions'))
    records = sorted(session.records, key=lambda r: r.student.roll_number)
    from datetime import datetime
    now = datetime.now().strftime('%d %b %Y %H:%M')
    return render_template('teacher/print_sheet.html', session=session,
                           records=records, now=now)


# ─── Reports ─────────────────────────────────────────────────────────────────

@teacher_bp.route('/reports')
@login_required
@teacher_required
def reports():
    teacher = _current_teacher()
    subjects = teacher.subjects
    selected_subject_id = request.args.get('subject_id', type=int)
    sessions_list = []
    if selected_subject_id:
        sessions_list = AttendanceSession.query.filter_by(
            college_id=teacher.college_id,
            subject_id=selected_subject_id,
            teacher_id=teacher.id,
            status='completed'
        ).order_by(AttendanceSession.date.desc()).all()

    return render_template('teacher/reports.html',
                           subjects=subjects,
                           selected_subject_id=selected_subject_id,
                           sessions=sessions_list)


@teacher_bp.route('/reports/session/<int:session_id>/download')
@login_required
@teacher_required
def download_session_report(session_id):
    session = db.session.get(AttendanceSession, session_id)
    if session is None:
        abort(404)
    if not _teacher_owns_session(session):
        abort(403)
    fmt = request.args.get('fmt', 'excel')
    df = generate_session_report(session_id)
    filename = f"attendance_{session.subject.code}_{session.date}"

    if fmt == 'csv':
        return send_file(
            io.BytesIO(dataframe_to_csv_bytes(df)),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"{filename}.csv"
        )
    return send_file(
        io.BytesIO(dataframe_to_excel_bytes(df, 'Session Report')),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"{filename}.xlsx"
    )


@teacher_bp.route('/reports/subject/<int:subject_id>/download')
@login_required
@teacher_required
def download_subject_report(subject_id):
    subject = db.session.get(Subject, subject_id)
    if subject is None:
        abort(404)
    if not _teacher_owns_subject(subject):
        abort(403)
    fmt = request.args.get('fmt', 'excel')
    df = generate_subject_report(subject_id)
    filename = f"attendance_{subject.code}_full"

    if fmt == 'csv':
        return send_file(
            io.BytesIO(dataframe_to_csv_bytes(df)),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"{filename}.csv"
        )
    return send_file(
        io.BytesIO(dataframe_to_excel_bytes(df, 'Subject Report')),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"{filename}.xlsx"
    )


# ─── Teacher Status (voluntary check-in) ─────────────────────────────────────

@teacher_bp.route('/status/update', methods=['POST'])
@login_required
@teacher_required
def update_status():
    teacher = _current_teacher()
    status = request.form.get('status', '').strip()
    note = request.form.get('note', '').strip()[:200]

    valid = ('on_campus', 'in_class', 'unavailable', 'off_campus')
    if status not in valid:
        flash('Invalid status value.', 'danger')
        return redirect(url_for('teacher.dashboard'))

    ts = TeacherStatus.query.filter_by(college_id=teacher.college_id, teacher_id=teacher.id).first()
    if ts:
        ts.status = status
        ts.note = note or None
        ts.updated_at = utc_now_naive()
    else:
        ts = TeacherStatus(college_id=teacher.college_id, teacher_id=teacher.id, status=status,
                           note=note or None)
        db.session.add(ts)
    db.session.commit()
    flash('Status updated successfully.', 'success')
    return redirect(url_for('teacher.dashboard'))


# ── Content Management (Notes / Assignments / Labs / Questions) ──────────────

def _content_upload(teacher_id):
    """Save uploaded attachment, return app-relative content path or None."""
    from werkzeug.utils import secure_filename
    f = request.files.get('attachment')
    if not f or not f.filename:
        return None
    if not is_allowed_content_upload(f.filename):
        flash(
            'Unsupported attachment type. Allowed: PDF, Office docs, spreadsheets, text, and safe images.',
            'danger',
        )
        return False
    upload_dir = current_app.config['CONTENT_UPLOAD_FOLDER']
    os.makedirs(upload_dir, exist_ok=True)
    ext  = os.path.splitext(secure_filename(f.filename))[1].lower()
    fname = f'{teacher_id}_{utc_now_naive().strftime("%Y%m%d%H%M%S%f")}{ext}'
    f.save(os.path.join(upload_dir, fname))
    return build_content_relpath(fname)


def _submission_upload(student_id):
    from werkzeug.utils import secure_filename

    f = request.files.get('submission_file')
    if not f or not f.filename:
        return None
    if not is_allowed_content_upload(f.filename):
        flash(
            'Unsupported submission type. Allowed: PDF, Office docs, spreadsheets, text, and safe images.',
            'danger',
        )
        return False

    upload_dir = current_app.config['ASSIGNMENT_UPLOAD_FOLDER']
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(secure_filename(f.filename))[1].lower()
    fname = f'{student_id}_{utc_now_naive().strftime("%Y%m%d%H%M%S%f")}{ext}'
    f.save(os.path.join(upload_dir, fname))
    return build_submission_relpath(fname)


def _assignment_stats(item: TeacherContent) -> dict:
    total_students = Student.query.filter_by(
        college_id=item.college_id,
        department_id=item.department_id,
        semester=item.semester,
    ).count()
    submitted = AssignmentSubmission.query.filter_by(college_id=item.college_id, content_id=item.id).count()
    reviewed = AssignmentSubmission.query.filter_by(college_id=item.college_id, content_id=item.id, status='reviewed').count()
    return {
        'total': total_students,
        'submitted': submitted,
        'pending': max(total_students - submitted, 0),
        'reviewed': reviewed,
    }


@teacher_bp.route('/content/<int:cid>/file')
@login_required
@teacher_required
def content_file(cid):
    teacher = _current_teacher()
    item = TeacherContent.query.filter_by(id=cid, college_id=teacher.college_id, teacher_id=teacher.id).first_or_404()
    if not item.file_path:
        abort(404)

    abs_path = resolve_content_path(current_app, item.file_path)
    if not abs_path or not os.path.isfile(abs_path):
        abort(404)

    return send_file(
        abs_path,
        as_attachment=request.args.get('download', '1') != '0',
        download_name=os.path.basename(item.file_path),
        conditional=True,
    )


@teacher_bp.route('/content')
@login_required
@teacher_required
def content_list():
    teacher      = _current_teacher()
    type_filter  = request.args.get('type', '')
    subj_filter  = request.args.get('subject', 0, type=int)
    pub_filter   = request.args.get('pub', '')
    q            = request.args.get('q', '').strip()
    page         = request.args.get('page', 1, type=int)

    query = TeacherContent.query.filter_by(college_id=teacher.college_id, teacher_id=teacher.id)
    if type_filter in ('note', 'assignment', 'lab', 'question'):
        query = query.filter_by(content_type=type_filter)
    if subj_filter:
        query = query.filter_by(subject_id=subj_filter)
    if pub_filter == 'published':
        query = query.filter_by(is_published=True)
    elif pub_filter == 'draft':
        query = query.filter_by(is_published=False)
    if q:
        query = query.filter(TeacherContent.title.ilike(f'%{q}%'))

    pagination = query.order_by(TeacherContent.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False)

    subjects = Subject.query.filter_by(teacher_id=teacher.id).order_by(Subject.name).all()
    base_q   = TeacherContent.query.filter_by(college_id=teacher.college_id, teacher_id=teacher.id)
    counts   = {
        'all':        base_q.count(),
        'note':       base_q.filter_by(content_type='note').count(),
        'assignment': base_q.filter_by(content_type='assignment').count(),
        'lab':        base_q.filter_by(content_type='lab').count(),
        'question':   base_q.filter_by(content_type='question').count(),
    }
    assignment_stats = {
        item.id: _assignment_stats(item)
        for item in pagination.items
        if item.content_type == 'assignment'
    }
    return render_template('teacher/content.html',
                           pagination=pagination, items=pagination.items,
                           subjects=subjects, counts=counts,
                           type_filter=type_filter, subj_filter=subj_filter,
                           pub_filter=pub_filter, q=q,
                           assignment_stats=assignment_stats)


@teacher_bp.route('/content/new', methods=['GET', 'POST'])
@login_required
@teacher_required
def content_create():
    teacher  = _current_teacher()
    subjects = Subject.query.filter_by(college_id=teacher.college_id, teacher_id=teacher.id).order_by(Subject.name).all()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'danger')
            return redirect(request.url)

        ctype    = request.form.get('content_type', 'note')
        subj_id  = request.form.get('subject_id') or None
        sem      = request.form.get('semester', 1, type=int)
        body     = request.form.get('body', '').strip()
        due_str  = request.form.get('due_date', '').strip()
        marks_s  = request.form.get('marks', '').strip()

        if subj_id:
            subject = Subject.query.filter_by(id=subj_id, college_id=teacher.college_id, teacher_id=teacher.id).first()
            if not subject:
                flash('Invalid subject selection.', 'danger')
                return redirect(request.url)
            sem = subject.semester

        due_date = None
        if due_str:
            try:
                from datetime import date as _date
                due_date = _date.fromisoformat(due_str)
            except ValueError:
                flash('Invalid due date.', 'danger')
                return redirect(request.url)

        if ctype == 'assignment' and not due_date:
            flash('Assignments must have a due date.', 'danger')
            return redirect(request.url)

        if marks_s and not marks_s.isdigit():
            flash('Marks must be a whole number.', 'danger')
            return redirect(request.url)
        marks = int(marks_s) if marks_s.isdigit() else None

        file_path = _content_upload(teacher.id)
        if file_path is False:
            return redirect(request.url)

        item = TeacherContent(
            college_id    = teacher.college_id,
            teacher_id    = teacher.id,
            subject_id    = subj_id,
            department_id = teacher.department_id,
            semester      = sem,
            content_type  = ctype,
            title         = title,
            body          = body,
            file_path     = file_path,
            due_date      = due_date,
            marks         = marks,
            is_published  = bool(request.form.get('is_published')),
        )
        db.session.add(item)
        db.session.commit()
        flash(f'{ctype.capitalize()} "{title}" created.', 'success')
        return redirect(url_for('teacher.content_list'))

    return render_template('teacher/content_form.html',
                           subjects=subjects, teacher=teacher,
                           item=None, action='Create')


@teacher_bp.route('/content/<int:cid>/edit', methods=['GET', 'POST'])
@login_required
@teacher_required
def content_edit(cid):
    teacher  = _current_teacher()
    item     = TeacherContent.query.filter_by(id=cid, college_id=teacher.college_id, teacher_id=teacher.id).first_or_404()
    subjects = Subject.query.filter_by(college_id=teacher.college_id, teacher_id=teacher.id).order_by(Subject.name).all()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'danger')
            return redirect(request.url)

        item.title        = title
        item.content_type = request.form.get('content_type', item.content_type)
        subj_id           = request.form.get('subject_id') or None
        if subj_id:
            subject = Subject.query.filter_by(id=subj_id, college_id=teacher.college_id, teacher_id=teacher.id).first()
            if not subject:
                flash('Invalid subject selection.', 'danger')
                return redirect(request.url)
            item.subject_id = subject.id
            item.semester = subject.semester
        else:
            item.subject_id = None
            item.semester = request.form.get('semester', item.semester, type=int)
        item.body         = request.form.get('body', '').strip()
        item.is_published = bool(request.form.get('is_published'))

        due_str = request.form.get('due_date', '').strip()
        if due_str:
            try:
                from datetime import date as _date
                item.due_date = _date.fromisoformat(due_str)
            except ValueError:
                flash('Invalid due date.', 'danger')
                return redirect(request.url)
        else:
            item.due_date = None

        if item.content_type == 'assignment' and not item.due_date:
            flash('Assignments must have a due date.', 'danger')
            return redirect(request.url)

        marks_s = request.form.get('marks', '').strip()
        if marks_s and not marks_s.isdigit():
            flash('Marks must be a whole number.', 'danger')
            return redirect(request.url)
        item.marks = int(marks_s) if marks_s.isdigit() else None

        new_fp = _content_upload(teacher.id)
        if new_fp is False:
            return redirect(request.url)
        if new_fp:
            item.file_path = new_fp
        item.updated_at = utc_now_naive()
        db.session.commit()
        flash('Content updated.', 'success')
        return redirect(url_for('teacher.content_list'))

    return render_template('teacher/content_form.html',
                           subjects=subjects, teacher=teacher,
                           item=item, action='Edit')


@teacher_bp.route('/content/<int:cid>/delete', methods=['POST'])
@login_required
@teacher_required
def content_delete(cid):
    teacher = _current_teacher()
    item    = TeacherContent.query.filter_by(id=cid, college_id=teacher.college_id, teacher_id=teacher.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash('Content deleted.', 'info')
    return redirect(url_for('teacher.content_list'))


@teacher_bp.route('/content/<int:cid>/toggle', methods=['POST'])
@login_required
@teacher_required
def content_toggle(cid):
    teacher = _current_teacher()
    item    = TeacherContent.query.filter_by(id=cid, college_id=teacher.college_id, teacher_id=teacher.id).first_or_404()
    item.is_published = not item.is_published
    db.session.commit()
    return jsonify(published=item.is_published,
                   label='Published' if item.is_published else 'Draft')


@teacher_bp.route('/content/<int:cid>/preview')
@login_required
@teacher_required
def content_preview(cid):
    import html
    from utils.file_preview import (
        pptx_to_html,
        docx_to_html,
        preview_exception_message,
        infer_preview_type,
    )

    teacher = _current_teacher()
    item    = TeacherContent.query.filter_by(id=cid, college_id=teacher.college_id, teacher_id=teacher.id).first_or_404()

    abs_path = resolve_content_path(current_app, item.file_path) if item.file_path else None
    ext = infer_preview_type(item.file_path, abs_path)
    file_url = url_for('teacher.content_file', cid=item.id, download=0) if item.file_path else None
    download_url = url_for('teacher.content_file', cid=item.id) if item.file_path else None

    show_note_body = item.content_type == 'note' and bool(item.body)
    preview_type = ext
    preview_html = None
    error        = None
    if item.file_path:
        if not abs_path or not os.path.isfile(abs_path):
            error = 'Attached file is missing from the server.'
        elif ext == 'pptx':
            try:
                preview_html = pptx_to_html(abs_path)
            except Exception as e:
                error = preview_exception_message(ext, e)
        elif ext in ('docx', 'doc'):
            try:
                preview_html = docx_to_html(abs_path)
            except Exception as e:
                error = preview_exception_message(ext, e)
        elif ext in ('txt', 'csv'):
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='replace') as fh:
                    preview_html = f"<pre class=\"text-file-preview mb-0\">{html.escape(fh.read())}</pre>"
            except Exception as e:
                error = preview_exception_message(ext, e)
    else:
        preview_type = 'content'

    return render_template('student/content_preview.html',
                           item=item, preview_type=preview_type,
                           file_url=file_url, download_url=download_url,
                           preview_html=preview_html, error=error,
                           back_url=url_for('teacher.content_list'),
                           show_note_body=show_note_body)


@teacher_bp.route('/assignments/<int:cid>')
@login_required
@teacher_required
def assignment_review(cid):
    teacher = _current_teacher()
    item = _assignment_for_teacher(cid, teacher)
    students = Student.query.filter_by(
        college_id=item.college_id,
        department_id=item.department_id,
        semester=item.semester,
    ).order_by(Student.roll_number).all()
    submissions = AssignmentSubmission.query.filter_by(college_id=item.college_id, content_id=item.id).all()
    submission_map = {submission.student_id: submission for submission in submissions}

    rows = []
    late_count = 0
    for student in students:
        submission = submission_map.get(student.id)
        if submission and submission.is_late:
            late_count += 1
        rows.append({
            'student': student,
            'submission': submission,
            'score_pct': (
                round((submission.marks_awarded / item.marks) * 100, 1)
                if submission and submission.marks_awarded is not None and item.marks
                else None
            ),
        })

    stats = _assignment_stats(item)
    stats['late'] = late_count
    stats['awaiting_review'] = AssignmentSubmission.query.filter_by(
        college_id=item.college_id,
        content_id=item.id,
        status='submitted',
    ).count()
    first_unreviewed_submission_id = _next_unreviewed_submission_id(item.id)

    return render_template(
        'teacher/assignment_submissions.html',
        item=item,
        rows=rows,
        stats=stats,
        first_unreviewed_submission_id=first_unreviewed_submission_id,
    )


@teacher_bp.route('/assignments/submissions/<int:sid>/file')
@login_required
@teacher_required
def assignment_submission_file(sid):
    teacher = _current_teacher()
    submission = (
        AssignmentSubmission.query
        .join(TeacherContent, TeacherContent.id == AssignmentSubmission.content_id)
        .filter(
            AssignmentSubmission.college_id == teacher.college_id,
            AssignmentSubmission.id == sid,
            TeacherContent.college_id == teacher.college_id,
            TeacherContent.teacher_id == teacher.id,
        )
        .first_or_404()
    )
    if not submission.file_path:
        abort(404)

    abs_path = resolve_submission_path(current_app, submission.file_path)
    if not abs_path or not os.path.isfile(abs_path):
        abort(404)

    return send_file(
        abs_path,
        as_attachment=request.args.get('download', '1') != '0',
        download_name=os.path.basename(submission.file_path),
        conditional=True,
    )


@teacher_bp.route('/assignments/submissions/<int:sid>/preview')
@login_required
@teacher_required
def assignment_submission_preview(sid):
    import html
    from utils.file_preview import (
        pptx_to_html,
        docx_to_html,
        preview_exception_message,
        infer_preview_type,
    )

    teacher = _current_teacher()
    submission = (
        AssignmentSubmission.query
        .join(TeacherContent, TeacherContent.id == AssignmentSubmission.content_id)
        .filter(
            AssignmentSubmission.college_id == teacher.college_id,
            AssignmentSubmission.id == sid,
            TeacherContent.college_id == teacher.college_id,
            TeacherContent.teacher_id == teacher.id,
        )
        .first_or_404()
    )

    abs_path = resolve_submission_path(current_app, submission.file_path) if submission.file_path else None
    ext = infer_preview_type(submission.file_path, abs_path)
    file_url = url_for('teacher.assignment_submission_file', sid=submission.id, download=0) if submission.file_path else None
    download_url = url_for('teacher.assignment_submission_file', sid=submission.id) if submission.file_path else None

    preview_type = ext if submission.file_path else 'content'
    preview_html = None
    error = None

    if submission.file_path:
        if not abs_path or not os.path.isfile(abs_path):
            error = 'Submitted file is missing from the server.'
        elif ext == 'pptx':
            try:
                preview_html = pptx_to_html(abs_path)
            except Exception as e:
                error = preview_exception_message(ext, e)
        elif ext in ('docx', 'doc'):
            try:
                preview_html = docx_to_html(abs_path)
            except Exception as e:
                error = preview_exception_message(ext, e)
        elif ext in ('txt', 'csv'):
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='replace') as fh:
                    preview_html = f"<pre class=\"text-file-preview mb-0\">{html.escape(fh.read())}</pre>"
            except Exception as e:
                error = preview_exception_message(ext, e)

    next_submission_id = _next_unreviewed_submission_id(submission.content_id, submission.id)

    return render_template(
        'student/content_preview.html',
        item=submission.content,
        preview_type=preview_type,
        file_url=file_url,
        download_url=download_url,
        preview_html=preview_html,
        error=error,
        back_url=url_for('teacher.assignment_review', cid=submission.content_id),
        show_note_body=False,
        submission=submission,
        preview_heading='Student Submission Preview',
        grade_action_url=url_for('teacher.assignment_grade', sid=submission.id),
        next_submission_id=next_submission_id,
    )


@teacher_bp.route('/assignments/submissions/<int:sid>/grade', methods=['POST'])
@login_required
@teacher_required
def assignment_grade(sid):
    teacher = _current_teacher()
    submission = (
        AssignmentSubmission.query
        .join(TeacherContent, TeacherContent.id == AssignmentSubmission.content_id)
        .filter(
            AssignmentSubmission.college_id == teacher.college_id,
            AssignmentSubmission.id == sid,
            TeacherContent.college_id == teacher.college_id,
            TeacherContent.teacher_id == teacher.id,
    )
        .first_or_404()
    )
    return_to_preview = request.form.get('return_to_preview') == '1'
    next_submission_id = request.form.get('next_submission_id', type=int)
    go_next = request.form.get('go_next') == '1'

    marks_raw = request.form.get('marks_awarded', '').strip()
    feedback = request.form.get('feedback', '').strip()

    if marks_raw:
        if not marks_raw.isdigit():
            flash('Awarded marks must be a whole number.', 'danger')
            if return_to_preview:
                return redirect(url_for('teacher.assignment_submission_preview', sid=submission.id))
            return redirect(url_for('teacher.assignment_review', cid=submission.content_id))
        marks_awarded = int(marks_raw)
        if submission.content.marks is not None and marks_awarded > submission.content.marks:
            flash('Awarded marks cannot exceed total marks.', 'danger')
            if return_to_preview:
                return redirect(url_for('teacher.assignment_submission_preview', sid=submission.id))
            return redirect(url_for('teacher.assignment_review', cid=submission.content_id))
        submission.marks_awarded = marks_awarded
    else:
        submission.marks_awarded = None

    submission.feedback = feedback or None
    submission.status = 'reviewed'
    submission.graded_at = utc_now_naive()
    submission.updated_at = utc_now_naive()
    db.session.commit()

    if return_to_preview and go_next and next_submission_id:
        flash(
            f'Review saved for {submission.student.user.name}. Opening the next unreviewed submission.',
            'success',
        )
        return redirect(url_for('teacher.assignment_submission_preview', sid=next_submission_id))

    flash(f'Review saved for {submission.student.user.name}.', 'success')
    if return_to_preview:
        return redirect(url_for('teacher.assignment_submission_preview', sid=submission.id))
    return redirect(url_for('teacher.assignment_review', cid=submission.content_id))
