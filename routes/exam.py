from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from extensions import db
from models.exam import Exam, Mark, compute_grade
from models.notice import Notice
from models.subject import Subject
from models.student import Student
from models.department import Department
from utils.decorators import teacher_required, student_required, admin_required, strict_admin_required
from datetime import date, datetime
from utils.time import utc_now_naive

exam_bp = Blueprint('exam', __name__)


# ── Marksheet builder (shared) ────────────────────────────────────────────────

def build_marksheet_data(student, semester=None):
    from models.setting import CollegeSetting
    from models.attendance import AttendanceSession, AttendanceRecord
    from models.marksheet_signature import MarksheetSignature
    college = CollegeSetting.get(student.college)

    viewed_semester = int(semester) if semester else student.semester
    viewed_semester = min(viewed_semester, student.semester)
    viewed_semester = max(viewed_semester, 1)

    principal_sig = MarksheetSignature.query.filter_by(
        college_id=student.college_id, role='principal').first()
    hod_sig = MarksheetSignature.query.filter_by(
        college_id=student.college_id, role='hod',
        department_id=student.department_id).first()

    subjects = Subject.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=viewed_semester,
    ).order_by(Subject.name).all()

    subject_rows = []
    total_obtained_all = 0.0
    grand_total_all = 0.0

    for subject in subjects:
        exams = Exam.query.filter_by(
            college_id=student.college_id, subject_id=subject.id
        ).order_by(Exam.exam_date).all()
        exam_rows = []
        sub_obtained = 0.0
        sub_total = 0.0

        for exam in exams:
            mark = Mark.query.filter_by(
                college_id=student.college_id, exam_id=exam.id, student_id=student.id
            ).first()
            obtained = None
            grade = '—'
            pct = None

            if mark:
                if mark.is_absent:
                    grade = 'AB'
                elif mark.marks_obtained is not None:
                    obtained = mark.marks_obtained
                    grade = mark.grade
                    pct = mark.percentage
                    sub_obtained += obtained
                    sub_total += exam.total_marks

            exam_rows.append({
                'exam': exam, 'mark': mark,
                'obtained': obtained, 'total': exam.total_marks,
                'pass_marks': exam.pass_marks, 'grade': grade, 'percentage': pct,
            })

        sub_pct = round(sub_obtained / sub_total * 100, 1) if sub_total > 0 else None
        sub_grade = compute_grade(sub_obtained, sub_total) if sub_total > 0 else '—'

        passed = True
        for er in exam_rows:
            if er['mark'] and er['mark'].is_absent:
                passed = False
                break
            if er['obtained'] is not None and er['pass_marks'] and er['obtained'] < er['pass_marks']:
                passed = False
                break

        from models.attendance import AttendanceSession, AttendanceRecord
        total_classes = AttendanceSession.query.filter_by(
            college_id=student.college_id, subject_id=subject.id, status='completed').count()
        present_count = (AttendanceRecord.query
                         .join(AttendanceSession)
                         .filter(
                             AttendanceRecord.college_id == student.college_id,
                             AttendanceSession.subject_id == subject.id,
                             AttendanceSession.status == 'completed',
                             AttendanceRecord.student_id == student.id,
                             AttendanceRecord.status == 'present',
                         ).count())
        att_pct = round(present_count / total_classes * 100, 1) if total_classes > 0 else None

        total_obtained_all += sub_obtained
        grand_total_all += sub_total

        subject_rows.append({
            'subject': subject, 'exams': exam_rows,
            'obtained': sub_obtained, 'total': sub_total,
            'percentage': sub_pct, 'grade': sub_grade, 'passed': passed,
            'has_marks': sub_total > 0,
            'total_classes': total_classes, 'present': present_count,
            'absent': total_classes - present_count, 'att_pct': att_pct,
        })

    if grand_total_all > 0:
        overall_pct = round(total_obtained_all / grand_total_all * 100, 1)
        overall_grade = compute_grade(total_obtained_all, grand_total_all)
        overall_passed = all(s['passed'] for s in subject_rows if s['has_marks'])
    else:
        overall_pct = None
        overall_grade = '—'
        overall_passed = False

    return {
        'college': college, 'student': student,
        'subjects': subject_rows,
        'principal_sig': principal_sig, 'hod_sig': hod_sig,
        'viewed_semester': viewed_semester,
        'overall': {
            'obtained': total_obtained_all, 'total': grand_total_all,
            'percentage': overall_pct, 'grade': overall_grade, 'passed': overall_passed,
        },
    }


# ── Shared helper ─────────────────────────────────────────────────────────────

def get_upcoming_exams_for_student(student):
    subject_ids = [s.id for s in Subject.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester,
    ).all()]
    return Exam.query.filter(
        Exam.college_id == student.college_id,
        Exam.subject_id.in_(subject_ids),
        Exam.exam_date >= date.today(),
    ).order_by(Exam.exam_date, Exam.start_time).all()


def _create_exam_from_form(college_id, form, subject_scope_check=None):
    """Shared exam creation logic. Returns (exam, error_message)."""
    subject_id = form.get('subject_id', type=int)
    title = form.get('title', '').strip()
    exam_type = form.get('exam_type', 'mid_term')
    exam_date_str = form.get('exam_date', '')
    start_str = form.get('start_time', '')
    duration = form.get('duration_mins', type=int)
    total_marks = form.get('total_marks', 100, type=float)
    pass_marks = form.get('pass_marks', type=float)
    room = form.get('room', '').strip()
    instructions = form.get('instructions', '').strip()

    if not all([subject_id, title, exam_date_str]):
        return None, 'Subject, title, and date are required.'

    sub = Subject.query.filter_by(id=subject_id, college_id=college_id).first()
    if sub is None:
        return None, 'Subject not found.'
    if subject_scope_check and not subject_scope_check(sub):
        return None, 'Unauthorised subject.'

    try:
        exam_date = date.fromisoformat(exam_date_str)
    except ValueError:
        return None, 'Invalid exam date.'

    start_time = None
    if start_str:
        try:
            start_time = datetime.strptime(start_str, '%H:%M').time()
        except ValueError:
            return None, 'Invalid exam start time.'

    exam = Exam(
        college_id=college_id,
        subject_id=subject_id, title=title, exam_type=exam_type,
        exam_date=exam_date, start_time=start_time,
        duration_mins=duration, total_marks=total_marks, pass_marks=pass_marks,
        room=room, instructions=instructions,
        created_by=None,
    )
    db.session.add(exam)
    db.session.flush()

    students = Student.query.filter_by(
        college_id=college_id,
        department_id=sub.department_id,
        semester=sub.semester,
    ).all()
    for s in students:
        db.session.add(Mark(college_id=s.college_id, exam_id=exam.id, student_id=s.id))

    return exam, None


def _post_exam_notice(exam, sub, author_id):
    exam_type_label = exam.exam_type.replace('_', ' ').title()
    parts = [
        f"Subject: {sub.name} ({sub.code})",
        f"Type: {exam_type_label}",
        f"Date: {exam.exam_date.strftime('%A, %d %B %Y')}",
    ]
    if exam.start_time:
        parts.append(f"Time: {exam.start_time.strftime('%I:%M %p')}")
    if exam.duration_mins:
        parts.append(f"Duration: {exam.duration_mins} minutes")
    if exam.room:
        parts.append(f"Room / Venue: {exam.room}")
    parts.append(f"Total Marks: {int(exam.total_marks)}")
    if exam.pass_marks:
        parts.append(f"Pass Marks: {int(exam.pass_marks)}")
    if exam.instructions:
        parts.append(f"\nInstructions: {exam.instructions}")

    db.session.add(Notice(
        college_id=sub.college_id,
        title=f"Exam Scheduled: {exam.title}",
        content="\n".join(parts),
        category='exam',
        target_role='student',
        is_pinned=False,
        author_id=author_id,
    ))


# ── Admin: create / view / delete exams ───────────────────────────────────────

@exam_bp.route('/admin/exams', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_exams():
    cid = current_user.college_id

    if request.method == 'POST':
        exam, err = _create_exam_from_form(cid, request.form)
        if err:
            flash(err, 'danger')
            return redirect(url_for('exam.admin_exams'))

        sub = Subject.query.get(exam.subject_id)
        _post_exam_notice(exam, sub, current_user.id)
        db.session.commit()
        flash(f'Exam "{exam.title}" scheduled.', 'success')
        return redirect(url_for('exam.admin_exams'))

    dept_id = request.args.get('department_id', type=int)
    subject_id = request.args.get('subject_id', type=int)

    departments = Department.query.filter_by(college_id=cid).order_by(Department.name).all()
    subjects = Subject.query.filter_by(college_id=cid).order_by(Subject.name).all()

    query = Exam.query.filter_by(college_id=cid)
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    elif dept_id:
        sub_ids = [s.id for s in Subject.query.filter_by(college_id=cid, department_id=dept_id).all()]
        query = query.filter(Exam.subject_id.in_(sub_ids))

    page = request.args.get('page', 1, type=int)
    pagination = query.order_by(Exam.exam_date.desc()).paginate(page=page, per_page=20, error_out=False)

    return render_template(
        'exam/admin_list.html',
        pagination=pagination, exams=pagination.items,
        departments=departments, subjects=subjects,
        selected_dept=dept_id, selected_subject=subject_id,
    )


@exam_bp.route('/admin/exams/<int:exam_id>/delete', methods=['POST'])
@login_required
@strict_admin_required
def admin_delete_exam(exam_id):
    exam = Exam.query.filter_by(id=exam_id, college_id=current_user.college_id).first_or_404()
    Notice.query.filter_by(
        college_id=current_user.college_id,
        title=f"Exam Scheduled: {exam.title}",
        category='exam',
    ).delete()
    db.session.delete(exam)
    db.session.commit()
    flash('Exam deleted.', 'info')
    return redirect(url_for('exam.admin_exams'))


# ── Teacher: enter marks only ─────────────────────────────────────────────────

@exam_bp.route('/teacher/exams')
@login_required
@teacher_required
def teacher_exams():
    teacher = current_user.teacher_profile
    subject_id = request.args.get('subject_id', type=int)
    subjects = teacher.subjects
    sub_ids = [s.id for s in subjects]

    if subject_id:
        exams = Exam.query.filter_by(
            college_id=teacher.college_id, subject_id=subject_id
        ).order_by(Exam.exam_date.desc()).all()
    else:
        exams = Exam.query.filter(
            Exam.college_id == teacher.college_id,
            Exam.subject_id.in_(sub_ids),
        ).order_by(Exam.exam_date.desc()).all()

    return render_template('exam/teacher_list.html',
                           exams=exams, subjects=subjects,
                           selected_subject=subject_id)


@exam_bp.route('/teacher/exams/<int:exam_id>/marks', methods=['GET', 'POST'])
@login_required
@teacher_required
def enter_marks(exam_id):
    teacher = current_user.teacher_profile
    exam = Exam.query.filter_by(id=exam_id, college_id=teacher.college_id).first_or_404()
    if exam.subject.teacher_id != teacher.id:
        flash('You are not assigned to this subject.', 'danger')
        return redirect(url_for('exam.teacher_exams'))

    if request.method == 'POST':
        for mark in exam.marks:
            is_absent = request.form.get(f'absent_{mark.student_id}') == 'on'
            raw = request.form.get(f'marks_{mark.student_id}', '').strip()
            mark.is_absent = is_absent
            mark.marks_obtained = None if is_absent or not raw else float(raw)
            mark.entered_by = teacher.id
            mark.entered_at = utc_now_naive()
        db.session.commit()
        flash('Marks saved.', 'success')
        return redirect(url_for('exam.teacher_exams'))

    marks_list = sorted(exam.marks, key=lambda m: m.student.roll_number)
    return render_template('exam/enter_marks.html', exam=exam, marks=marks_list)


# ── Student: exam routine + results ──────────────────────────────────────────

@exam_bp.route('/student/results')
@login_required
@student_required
def student_results():
    student = current_user.student_profile
    subjects = Subject.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester,
    ).order_by(Subject.name).all()

    # Auto-load results for all subjects — no filter required
    results = []
    for sub in subjects:
        exams = Exam.query.filter_by(
            college_id=student.college_id, subject_id=sub.id
        ).order_by(Exam.exam_date).all()
        for exam in exams:
            mark = Mark.query.filter_by(
                college_id=student.college_id,
                exam_id=exam.id,
                student_id=student.id,
            ).first()
            results.append({'exam': exam, 'mark': mark})

    # All upcoming exams — full routine, no limit
    upcoming = get_upcoming_exams_for_student(student)

    # Build date-grouped routine for table display
    today = date.today()
    routine_by_date = {}
    for exam in upcoming:
        key = exam.exam_date
        routine_by_date.setdefault(key, []).append(exam)
    routine_dates = sorted(routine_by_date.keys())

    return render_template(
        'exam/student_results.html',
        subjects=subjects,
        results=results,
        routine_by_date=routine_by_date,
        routine_dates=routine_dates,
        today=today,
    )


# ── Student: marksheet ────────────────────────────────────────────────────────

@exam_bp.route('/student/marksheet')
@login_required
@student_required
def student_marksheet():
    student = current_user.student_profile
    semester = request.args.get('semester', type=int)
    data = build_marksheet_data(student, semester=semester)
    return render_template('exam/marksheet.html', **data, is_admin=False, is_parent=False)
