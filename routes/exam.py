from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models.exam import Exam, Mark, compute_grade
from models.notice import Notice
from models.subject import Subject
from models.student import Student
from models.attendance import AttendanceSession
from utils.decorators import teacher_required, student_required
from datetime import date, datetime
from utils.time import utc_now_naive

exam_bp = Blueprint('exam', __name__)


# ── Marksheet builder (shared by student + admin views) ───────────────────────

def build_marksheet_data(student):
    from models.setting import CollegeSetting
    from models.attendance import AttendanceSession, AttendanceRecord
    from models.marksheet_signature import MarksheetSignature
    college = CollegeSetting.get(student.college)

    principal_sig = MarksheetSignature.query.filter_by(
        college_id=student.college_id,
        role='principal',
    ).first()
    hod_sig       = MarksheetSignature.query.filter_by(
                        college_id=student.college_id,
                        role='hod', department_id=student.department_id).first()

    subjects = Subject.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester
    ).order_by(Subject.name).all()

    subject_rows = []
    total_obtained_all = 0.0
    grand_total_all    = 0.0

    for subject in subjects:
        exams = Exam.query.filter_by(college_id=student.college_id, subject_id=subject.id).order_by(Exam.exam_date).all()
        exam_rows  = []
        sub_obtained = 0.0
        sub_total    = 0.0

        for exam in exams:
            mark    = Mark.query.filter_by(college_id=student.college_id, exam_id=exam.id, student_id=student.id).first()
            obtained = None
            grade    = '—'
            pct      = None

            if mark:
                if mark.is_absent:
                    grade = 'AB'
                elif mark.marks_obtained is not None:
                    obtained      = mark.marks_obtained
                    grade         = mark.grade
                    pct           = mark.percentage
                    sub_obtained += obtained
                    sub_total    += exam.total_marks

            exam_rows.append({
                'exam':       exam,
                'mark':       mark,
                'obtained':   obtained,
                'total':      exam.total_marks,
                'pass_marks': exam.pass_marks,
                'grade':      grade,
                'percentage': pct,
            })

        if sub_total > 0:
            sub_pct   = round(sub_obtained / sub_total * 100, 1)
            sub_grade = compute_grade(sub_obtained, sub_total)
        else:
            sub_pct   = None
            sub_grade = '—'

        # Subject pass: no absent AND all entered marks >= pass_marks (if set)
        passed = True
        for er in exam_rows:
            if er['mark'] and er['mark'].is_absent:
                passed = False
                break
            if er['obtained'] is not None and er['pass_marks'] and er['obtained'] < er['pass_marks']:
                passed = False
                break

        # Attendance for this subject
        total_classes = (AttendanceSession.query
                         .filter_by(college_id=student.college_id, subject_id=subject.id, status='completed')
                         .count())
        present_count = (AttendanceRecord.query
                         .join(AttendanceSession)
                         .filter(AttendanceRecord.college_id == student.college_id,
                                 AttendanceSession.college_id == student.college_id,
                                 AttendanceSession.subject_id == subject.id,
                                 AttendanceSession.status == 'completed',
                                 AttendanceRecord.student_id == student.id,
                                 AttendanceRecord.status == 'present')
                         .count())
        absent_count  = total_classes - present_count
        att_pct       = round(present_count / total_classes * 100, 1) if total_classes > 0 else None

        total_obtained_all += sub_obtained
        grand_total_all    += sub_total

        subject_rows.append({
            'subject':        subject,
            'exams':          exam_rows,
            'obtained':       sub_obtained,
            'total':          sub_total,
            'percentage':     sub_pct,
            'grade':          sub_grade,
            'passed':         passed,
            'has_marks':      sub_total > 0,
            'total_classes':  total_classes,
            'present':        present_count,
            'absent':         absent_count,
            'att_pct':        att_pct,
        })

    if grand_total_all > 0:
        overall_pct    = round(total_obtained_all / grand_total_all * 100, 1)
        overall_grade  = compute_grade(total_obtained_all, grand_total_all)
        overall_passed = all(s['passed'] for s in subject_rows if s['has_marks'])
    else:
        overall_pct    = None
        overall_grade  = '—'
        overall_passed = False

    return {
        'college':       college,
        'student':       student,
        'subjects':      subject_rows,
        'principal_sig': principal_sig,
        'hod_sig':       hod_sig,
        'overall': {
            'obtained':   total_obtained_all,
            'total':      grand_total_all,
            'percentage': overall_pct,
            'grade':      overall_grade,
            'passed':     overall_passed,
        },
    }


# ── Shared: upcoming exams list (for dashboards) ─────────────────────────────

def get_upcoming_exams_for_student(student):
    subject_ids = [s.id for s in Subject.query.filter_by(
        college_id=student.college_id, department_id=student.department_id, semester=student.semester
    ).all()]
    return Exam.query.filter(
        Exam.college_id == student.college_id,
        Exam.subject_id.in_(subject_ids),
        Exam.exam_date >= date.today()
    ).order_by(Exam.exam_date).limit(5).all()


# ── Teacher: manage exams ─────────────────────────────────────────────────────

@exam_bp.route('/teacher/exams')
@login_required
@teacher_required
def teacher_exams():
    teacher = current_user.teacher_profile
    subject_id = request.args.get('subject_id', type=int)
    subjects = teacher.subjects
    exams = []
    if subject_id:
        exams = Exam.query.filter_by(college_id=teacher.college_id, subject_id=subject_id).order_by(Exam.exam_date.desc()).all()
    else:
        sub_ids = [s.id for s in subjects]
        exams = Exam.query.filter(
            Exam.college_id == teacher.college_id,
            Exam.subject_id.in_(sub_ids)
        ).order_by(Exam.exam_date.desc()).all()
    return render_template('exam/teacher_list.html',
                           exams=exams, subjects=subjects,
                           selected_subject=subject_id)


@exam_bp.route('/teacher/exams/create', methods=['GET', 'POST'])
@login_required
@teacher_required
def create_exam():
    teacher = current_user.teacher_profile
    if request.method == 'POST':
        subject_id    = request.form.get('subject_id', type=int)
        title         = request.form.get('title', '').strip()
        exam_type     = request.form.get('exam_type', 'mid_term')
        exam_date_str = request.form.get('exam_date', '')
        start_str     = request.form.get('start_time', '')
        duration      = request.form.get('duration_mins', type=int)
        total_marks   = request.form.get('total_marks', 100, type=float)
        pass_marks    = request.form.get('pass_marks', type=float)
        room          = request.form.get('room', '').strip()
        instructions  = request.form.get('instructions', '').strip()

        if not all([subject_id, title, exam_date_str]):
            flash('Subject, title, and date are required.', 'danger')
            return redirect(url_for('exam.create_exam'))

        sub = Subject.query.filter_by(id=subject_id, college_id=teacher.college_id).first_or_404()
        if sub.teacher_id != teacher.id:
            flash('Unauthorised subject.', 'danger')
            return redirect(url_for('exam.teacher_exams'))

        try:
            exam_date = date.fromisoformat(exam_date_str)
        except ValueError:
            flash('Invalid exam date.', 'danger')
            return redirect(url_for('exam.create_exam'))

        start_time = None
        if start_str:
            try:
                start_time = datetime.strptime(start_str, '%H:%M').time()
            except ValueError:
                flash('Invalid exam start time.', 'danger')
                return redirect(url_for('exam.create_exam'))

        exam = Exam(
            college_id=sub.college_id,
            subject_id=subject_id, title=title, exam_type=exam_type,
            exam_date=exam_date,
            start_time=start_time,
            duration_mins=duration, total_marks=total_marks, pass_marks=pass_marks,
            room=room, instructions=instructions, created_by=teacher.id
        )
        db.session.add(exam)
        db.session.flush()

        # Pre-populate mark rows for all students in subject's dept+sem
        students = Student.query.filter_by(
            college_id=sub.college_id,
            department_id=sub.department_id, semester=sub.semester
        ).all()
        for s in students:
            db.session.add(Mark(college_id=s.college_id, exam_id=exam.id, student_id=s.id))

        db.session.commit()

        # Auto-post an exam notice so students are informed
        exam_type_label = exam_type.replace('_', ' ').title()
        date_str = exam.exam_date.strftime('%A, %d %B %Y')
        parts = [
            f"Subject: {sub.name} ({sub.code})",
            f"Type: {exam_type_label}",
            f"Date: {date_str}",
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

        notice = Notice(
            college_id=sub.college_id,
            title=f"Exam Scheduled: {title}",
            content="\n".join(parts),
            category='exam',
            target_role='student',
            is_pinned=False,
            author_id=current_user.id,
        )
        db.session.add(notice)
        db.session.commit()

        flash(f'Exam "{title}" created.', 'success')
        return redirect(url_for('exam.enter_marks', exam_id=exam.id))

    return render_template('exam/create.html', subjects=teacher.subjects)


@exam_bp.route('/teacher/exams/<int:exam_id>/marks', methods=['GET', 'POST'])
@login_required
@teacher_required
def enter_marks(exam_id):
    exam = Exam.query.filter_by(id=exam_id, college_id=teacher.college_id).first_or_404()
    teacher = current_user.teacher_profile
    if exam.subject.teacher_id != teacher.id:
        flash('Unauthorised.', 'danger')
        return redirect(url_for('exam.teacher_exams'))

    if request.method == 'POST':
        for mark in exam.marks:
            key = f'marks_{mark.student_id}'
            absent_key = f'absent_{mark.student_id}'
            is_absent = request.form.get(absent_key) == 'on'
            raw = request.form.get(key, '').strip()
            mark.is_absent = is_absent
            mark.marks_obtained = None if is_absent or not raw else float(raw)
            mark.entered_by = teacher.id
            mark.entered_at = utc_now_naive()
        db.session.commit()
        flash('Marks saved.', 'success')
        return redirect(url_for('exam.teacher_exams'))

    marks_list = sorted(exam.marks, key=lambda m: m.student.roll_number)
    return render_template('exam/enter_marks.html', exam=exam, marks=marks_list)


@exam_bp.route('/teacher/exams/<int:exam_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_exam(exam_id):
    exam = Exam.query.filter_by(id=exam_id, college_id=current_user.teacher_profile.college_id).first_or_404()
    if exam.subject.teacher_id != current_user.teacher_profile.id:
        flash('Unauthorised.', 'danger')
    else:
        # Remove the auto-generated exam notice so students don't see stale info
        Notice.query.filter_by(
            college_id=current_user.college_id,
            title=f"Exam Scheduled: {exam.title}",
            category='exam',
            author_id=current_user.id
        ).delete()
        db.session.delete(exam)
        db.session.commit()
        flash('Exam deleted.', 'info')
    return redirect(url_for('exam.teacher_exams'))


# ── Student: view results ─────────────────────────────────────────────────────

@exam_bp.route('/student/results')
@login_required
@student_required
def student_results():
    student = current_user.student_profile
    subject_id = request.args.get('subject_id', type=int)
    subjects = Subject.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id, semester=student.semester
    ).all()

    results = []
    if subject_id:
        exams = Exam.query.filter_by(college_id=student.college_id, subject_id=subject_id).order_by(Exam.exam_date).all()
        for exam in exams:
            mark = Mark.query.filter_by(college_id=student.college_id, exam_id=exam.id, student_id=student.id).first()
            results.append({'exam': exam, 'mark': mark})

    upcoming = get_upcoming_exams_for_student(student)
    return render_template('exam/student_results.html',
                           subjects=subjects, results=results,
                           selected_subject=subject_id,
                           upcoming=upcoming)


# ── Admin: exam schedule overview ─────────────────────────────────────────────

@exam_bp.route('/admin/exams')
@login_required
def admin_exams():
    from utils.decorators import admin_required
    if current_user.role != 'admin':
        flash('Not authorised.', 'danger')
        return redirect(url_for('auth.login'))

    dept_id    = request.args.get('department_id', type=int)
    subject_id = request.args.get('subject_id', type=int)

    from models.department import Department
    departments = Department.query.filter_by(college_id=current_user.college_id).order_by(Department.name).all()
    subjects = Subject.query.filter_by(college_id=current_user.college_id).all()

    query = Exam.query.filter_by(college_id=current_user.college_id)
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    elif dept_id:
        sub_ids = [s.id for s in Subject.query.filter_by(college_id=current_user.college_id, department_id=dept_id).all()]
        query = query.filter(Exam.subject_id.in_(sub_ids))

    page = request.args.get('page', 1, type=int)
    pagination = query.order_by(Exam.exam_date.desc()).paginate(page=page, per_page=15, error_out=False)

    return render_template('exam/admin_list.html',
                           pagination=pagination, exams=pagination.items,
                           departments=departments, subjects=subjects,
                           selected_dept=dept_id, selected_subject=subject_id)


# ── Student: marksheet ────────────────────────────────────────────────────────

@exam_bp.route('/student/marksheet')
@login_required
@student_required
def student_marksheet():
    student = current_user.student_profile
    data = build_marksheet_data(student)
    return render_template('exam/marksheet.html', **data, is_admin=False, is_parent=False)
