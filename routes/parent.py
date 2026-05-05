from flask import Blueprint, render_template, redirect, url_for, flash, abort, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db, limiter
from models.parent import ParentStudent, TeacherStatus
from models.student import Student
from models.attendance import AttendanceSession, AttendanceRecord
from models.subject import Subject
from models.exam import Exam, Mark
from models.fee import FeeStructure, FeePayment
from models.notice import Notice
from models.timetable import TimetableSlot, DAYS
from models.location import StudentLocation
from models.setting import CollegeSetting
from models.content import TeacherContent
from models.assignment import AssignmentSubmission
from datetime import date, datetime, timedelta
from utils.decorators import parent_required
from utils.assignment_storage import resolve_submission_path
from utils.dashboard import build_dashboard_preferences
from utils.time import utc_now_naive
from flask import request, send_file
import os

parent_bp = Blueprint('parent', __name__)


def _get_linked_students():
    links = ParentStudent.query.filter_by(
        college_id=current_user.college_id,
        parent_id=current_user.id,
    ).all()
    return [link.student for link in links]


def _attendance_summary(student):
    subjects = Subject.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester
    ).all()
    result = []
    for sub in subjects:
        total = AttendanceSession.query.filter_by(
            college_id=student.college_id,
            subject_id=sub.id, status='completed'
        ).count()
        present = AttendanceRecord.query.join(AttendanceSession).filter(
            AttendanceRecord.college_id == student.college_id,
            AttendanceRecord.student_id == student.id,
            AttendanceSession.college_id == student.college_id,
            AttendanceSession.subject_id == sub.id,
            AttendanceSession.status == 'completed',
            AttendanceRecord.status == 'present'
        ).count()
        pct = round(present / total * 100, 1) if total > 0 else 0
        result.append({
            'subject': sub,
            'total': total,
            'present': present,
            'absent': total - present,
            'percentage': pct,
            'low': pct < 75 and total > 0,
        })
    return result


def _assignment_rows_for_student(student, limit: int | None = None):
    assignments = (
        TeacherContent.query
        .filter_by(
            college_id=student.college_id,
            department_id=student.department_id,
            semester=student.semester,
            content_type='assignment',
            is_published=True,
        )
        .order_by(TeacherContent.due_date.asc(), TeacherContent.created_at.desc())
        .all()
    )
    if limit is not None:
        assignments = assignments[:limit]

    submission_map = {
        submission.content_id: submission
        for submission in AssignmentSubmission.query.filter(
            AssignmentSubmission.student_id == student.id,
            AssignmentSubmission.college_id == student.college_id,
            AssignmentSubmission.content_id.in_([assignment.id for assignment in assignments]) if assignments else db.text('0=1'),
        ).all()
    } if assignments else {}

    rows = []
    for assignment in assignments:
        submission = submission_map.get(assignment.id)
        rows.append({
            'assignment': assignment,
            'submission': submission,
            'state': (
                'reviewed' if submission and submission.status == 'reviewed'
                else 'submitted' if submission
                else 'pending'
            ),
            'score_pct': (
                round((submission.marks_awarded / assignment.marks) * 100, 1)
                if submission and submission.marks_awarded is not None and assignment.marks
                else None
            ),
        })
    return rows


@parent_bp.route('/parent/dashboard')
@login_required
@parent_required
def dashboard():
    dashboard_prefs = build_dashboard_preferences(current_user)
    students = _get_linked_students()
    if not students:
        flash('No children linked to your account yet. Contact the admin.', 'warning')

    children_data = []
    for student in students:
        link = ParentStudent.query.filter_by(
            college_id=current_user.college_id, parent_id=current_user.id, student_id=student.id
        ).first()
        att_summary = _attendance_summary(student)
        overall_pct = round(
            sum(s['percentage'] for s in att_summary) / len(att_summary), 1
        ) if att_summary else 0

        # Fee dues
        structures = FeeStructure.query.filter(
            FeeStructure.college_id == student.college_id,
            db.or_(FeeStructure.department_id == student.department_id,
                   FeeStructure.department_id == None),
            db.or_(FeeStructure.semester == student.semester,
                   FeeStructure.semester == None),
            FeeStructure.is_active == True
        ).all()
        paid_map = {p.fee_structure_id: p for p in
                    FeePayment.query.filter_by(college_id=student.college_id, student_id=student.id).all()}
        fee_due = sum(
            max(fs.amount - (paid_map[fs.id].amount_paid if fs.id in paid_map else 0), 0)
            for fs in structures
        )

        # Upcoming exams
        subject_ids = [s['subject'].id for s in att_summary]
        upcoming = Exam.query.filter(
            Exam.college_id == student.college_id,
            Exam.subject_id.in_(subject_ids),
            Exam.exam_date >= date.today(),
            Exam.exam_date <= date.today() + timedelta(days=7)
        ).order_by(Exam.exam_date).limit(3).all() if subject_ids else []

        # Low attendance subjects
        low_subjects = [s for s in att_summary if s['low']]

        location = StudentLocation.query.filter_by(college_id=student.college_id, student_id=student.id).first()
        assignment_rows = _assignment_rows_for_student(student, limit=3)
        assignment_summary = {
            'pending': sum(1 for row in assignment_rows if row['state'] == 'pending'),
            'submitted': sum(1 for row in assignment_rows if row['state'] == 'submitted'),
            'reviewed': sum(1 for row in assignment_rows if row['state'] == 'reviewed'),
        }

        children_data.append({
            'student': student,
            'relationship': link.relationship if link else 'guardian',
            'overall_pct': overall_pct,
            'fee_due': fee_due,
            'upcoming_exams': upcoming,
            'low_subjects': low_subjects,
            'att_summary': att_summary,
            'location': location,
            'assignment_rows': assignment_rows,
            'assignment_summary': assignment_summary,
        })

    # Notices for parents
    notices = Notice.query.filter(
        Notice.college_id == current_user.college_id,
        Notice.target_role.in_(['all', 'student']),
        db.or_(Notice.expires_at == None, Notice.expires_at > utc_now_naive())
    ).order_by(Notice.is_pinned.desc(), Notice.created_at.desc()).limit(5).all()

    cs = CollegeSetting.get()

    return render_template('parent/dashboard.html',
                           dashboard_prefs=dashboard_prefs,
                           children_data=children_data,
                           notices=notices,
                           college_lat=cs.latitude if cs.latitude else current_app.config['COLLEGE_LAT'],
                           college_lng=cs.longitude if cs.longitude else current_app.config['COLLEGE_LNG'],
                           today=date.today())


@parent_bp.route('/parent/child/<int:student_id>')
@login_required
@parent_required
def child_detail(student_id):
    link = ParentStudent.query.filter_by(
        college_id=current_user.college_id, parent_id=current_user.id, student_id=student_id
    ).first_or_404()
    student = link.student

    att_summary = _attendance_summary(student)
    overall_pct = round(
        sum(s['percentage'] for s in att_summary) / len(att_summary), 1
    ) if att_summary else 0

    # Recent attendance records
    recent_records = (
        AttendanceRecord.query
        .join(AttendanceSession)
        .filter(AttendanceRecord.student_id == student.id)
        .order_by(AttendanceSession.date.desc())
        .limit(20).all()
    )

    # Exam results
    subject_ids = [s['subject'].id for s in att_summary]
    marks = (
        Mark.query
        .join(Exam)
        .filter(Mark.student_id == student.id)
        .order_by(Exam.exam_date.desc())
        .all()
    ) if subject_ids else []

    # Fee details
    structures = FeeStructure.query.filter(
        FeeStructure.college_id == student.college_id,
        db.or_(FeeStructure.department_id == student.department_id,
               FeeStructure.department_id == None),
        db.or_(FeeStructure.semester == student.semester,
               FeeStructure.semester == None),
        FeeStructure.is_active == True
    ).order_by(FeeStructure.academic_year.desc()).all()
    paid_map = {p.fee_structure_id: p for p in
                FeePayment.query.filter_by(college_id=student.college_id, student_id=student.id).all()}
    fee_data = []
    for fs in structures:
        payment = paid_map.get(fs.id)
        paid = payment.amount_paid if payment else 0
        fee_data.append({
            'structure': fs,
            'payment': payment,
            'paid': paid,
            'due': max(fs.amount - paid, 0),
        })

    # Today's timetable with teacher status
    today_dow = date.today().weekday()  # 0=Mon
    today_slots = TimetableSlot.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester,
        day_of_week=today_dow
    ).order_by(TimetableSlot.period_no).all()

    slot_statuses = []
    for slot in today_slots:
        teacher_status = None
        if slot.subject and slot.subject.teacher:
            teacher_status = TeacherStatus.query.filter_by(
                college_id=student.college_id,
                teacher_id=slot.subject.teacher.id
            ).first()
        # Check if session has started for this slot today
        session_started = None
        if slot.subject:
            session_started = AttendanceSession.query.filter(
                AttendanceSession.college_id == student.college_id,
                AttendanceSession.subject_id == slot.subject_id,
                AttendanceSession.date == date.today(),
                AttendanceSession.status.in_(['active', 'completed'])
            ).first()
        slot_statuses.append({
            'slot': slot,
            'teacher_status': teacher_status,
            'session_started': session_started,
        })

    location = StudentLocation.query.filter_by(college_id=student.college_id, student_id=student.id).first()
    assignment_rows = _assignment_rows_for_student(student)
    cs = CollegeSetting.get()

    return render_template('parent/child.html',
                           student=student,
                           relationship=link.relationship,
                           att_summary=att_summary,
                           overall_pct=overall_pct,
                           recent_records=recent_records,
                           marks=marks,
                           fee_data=fee_data,
                           slot_statuses=slot_statuses,
                           assignment_rows=assignment_rows,
                           location=location,
                           college_lat=cs.latitude if cs.latitude else current_app.config['COLLEGE_LAT'],
                           college_lng=cs.longitude if cs.longitude else current_app.config['COLLEGE_LNG'],
                           college_name=cs.college_name,
                           today=date.today())


@parent_bp.route('/parent/child/<int:student_id>/location')
@limiter.exempt
@login_required
@parent_required
def child_location(student_id):
    """JSON endpoint — returns child's latest location for live map polling."""
    link = ParentStudent.query.filter_by(
        parent_id=current_user.id, student_id=student_id
    ).first_or_404()
    loc = StudentLocation.query.filter_by(student_id=student_id).first()

    if not loc or not loc.is_sharing or loc.latitude is None:
        return jsonify(sharing=False)

    # Seconds since last update
    age = int((utc_now_naive() - loc.updated_at).total_seconds()) if loc.updated_at else None

    return jsonify(
        sharing=True,
        lat=loc.latitude,
        lng=loc.longitude,
        accuracy=loc.accuracy,
        updated_at=loc.updated_at.strftime('%H:%M:%S') if loc.updated_at else None,
        age_seconds=age,
    )


# ── Parent: child marksheet ───────────────────────────────────────────────────

@parent_bp.route('/parent/marksheets')
@login_required
@parent_required
def parent_marksheets():
    students = _get_linked_students()
    return render_template('parent/marksheets.html', students=students)


@parent_bp.route('/parent/marksheet/<int:student_id>')
@login_required
@parent_required
def parent_marksheet(student_id):
    from routes.exam import build_marksheet_data
    # Ensure this student is actually linked to this parent
    ParentStudent.query.filter_by(
        college_id=current_user.college_id, parent_id=current_user.id, student_id=student_id
    ).first_or_404()
    student = db.session.get(Student, student_id)
    if student is None or student.college_id != current_user.college_id:
        abort(404)
    data = build_marksheet_data(student)
    return render_template('exam/marksheet.html', **data, is_admin=False, is_parent=True)


@parent_bp.route('/parent/assignments')
@login_required
@parent_required
def parent_assignments():
    students = _get_linked_students()
    if not students:
        return render_template('parent/assignments.html', students=[], selected_student=None, assignment_rows=[])

    selected_id = request.args.get('child_id', type=int)
    selected_student = next((student for student in students if student.id == selected_id), students[0])
    assignment_rows = _assignment_rows_for_student(selected_student)
    summary = {
        'pending': sum(1 for row in assignment_rows if row['state'] == 'pending'),
        'submitted': sum(1 for row in assignment_rows if row['state'] == 'submitted'),
        'reviewed': sum(1 for row in assignment_rows if row['state'] == 'reviewed'),
    }
    return render_template(
        'parent/assignments.html',
        students=students,
        selected_student=selected_student,
        assignment_rows=assignment_rows,
        summary=summary,
    )


@parent_bp.route('/parent/assignments/submissions/<int:sid>/file')
@login_required
@parent_required
def parent_submission_file(sid):
    submission = (
        AssignmentSubmission.query
        .join(Student, Student.id == AssignmentSubmission.student_id)
        .join(ParentStudent, ParentStudent.student_id == Student.id)
        .filter(
            AssignmentSubmission.college_id == current_user.college_id,
            AssignmentSubmission.id == sid,
            ParentStudent.college_id == current_user.college_id,
            ParentStudent.parent_id == current_user.id,
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
