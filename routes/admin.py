from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, current_app, abort
from flask_login import login_required, current_user
from extensions import db, limiter
import urllib.request
import urllib.parse
import json as _json
from models.user import User
from models.student import Student
from models.teacher import Teacher
from models.subject import Subject
from models.department import Department
from models.attendance import AttendanceSession, AttendanceRecord
from models.notice import Notice
from models.exam import Exam
from models.fee import FeeStructure, FeePayment
from models.parent import ParentStudent
from models.setting import CollegeSetting
from models.id_card import IDCardTemplate, StudentIDCard
from utils.decorators import admin_required, strict_admin_required
from utils.subadmin import SUBADMIN_MODULES
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func
from datetime import datetime, date, timedelta
import csv, io, os
from utils.content_storage import is_valid_content_relpath, resolve_content_path, content_storage_dirs
from utils.dashboard import build_dashboard_preferences
from utils.tenancy import current_college_id
from utils.time import utc_now_naive
import re

admin_bp = Blueprint('admin', __name__)
_TEMP_PASSWORD_RE = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^a-zA-Z0-9]).{8,}$'
)


def _admin_college_id() -> int:
    return current_user.college_id


def _scoped_model_or_404(model, object_id):
    obj = db.session.get(model, object_id)
    if obj is None or getattr(obj, 'college_id', None) != _admin_college_id():
        abort(404)
    return obj


def _scoped_department_query():
    return Department.query.filter_by(college_id=_admin_college_id())


def _scoped_student_query():
    return Student.query.filter_by(college_id=_admin_college_id())


def _scoped_teacher_query():
    return Teacher.query.filter_by(college_id=_admin_college_id())


def _scoped_subject_query():
    return Subject.query.filter_by(college_id=_admin_college_id())


def _scoped_user_query():
    return User.query.filter_by(college_id=_admin_college_id())


def _validate_temporary_password(password: str) -> bool:
    return bool(_TEMP_PASSWORD_RE.match(password))


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    dashboard_prefs = build_dashboard_preferences(current_user)
    stats = {
        'total_students': _scoped_student_query().count(),
        'total_teachers': _scoped_teacher_query().count(),
        'total_subjects': _scoped_subject_query().count(),
        'total_sessions': AttendanceSession.query.join(Subject).filter(Subject.college_id == _admin_college_id()).count(),
        'active_sessions': AttendanceSession.query.join(Subject).filter(
            Subject.college_id == _admin_college_id(),
            AttendanceSession.status == 'active',
        ).count(),
        'departments': _scoped_department_query().count(),
    }

    # Last 7 days attendance trend
    trend = []
    for i in range(6, -1, -1):
        day = date.today() - timedelta(days=i)
        sessions = AttendanceSession.query.join(Subject).filter(
            Subject.college_id == _admin_college_id(),
            AttendanceSession.date == day,
            AttendanceSession.status == 'completed',
        ).all()
        total = sum(s.total_students for s in sessions)
        present = sum(s.present_count for s in sessions)
        trend.append({
            'date': day.strftime('%d %b'),
            'total': total,
            'present': present,
            'rate': round(present / total * 100, 1) if total > 0 else 0,
        })

    # Department-wise attendance
    dept_stats = []
    for dept in _scoped_department_query().all():
        students = _scoped_student_query().filter_by(department_id=dept.id).all()
        if not students:
            continue
        rates = [s.get_attendance_percentage() for s in students]
        dept_stats.append({
            'name': dept.name,
            'code': dept.code,
            'avg_rate': round(sum(rates) / len(rates), 1) if rates else 0,
            'student_count': len(students),
        })

    recent_sessions = (
        AttendanceSession.query
        .join(Subject)
        .filter(Subject.college_id == _admin_college_id())
        .order_by(AttendanceSession.created_at.desc())
        .limit(10)
        .all()
    )

    # Recent notices (pinned first)
    recent_notices = Notice.query.filter(
        Notice.college_id == _admin_college_id(),
        db.or_(Notice.expires_at == None, Notice.expires_at > utc_now_naive())
    ).order_by(Notice.is_pinned.desc(), Notice.created_at.desc()).limit(5).all()

    # Upcoming exams (next 7 days)
    today = date.today()
    upcoming_exams = (
        Exam.query
        .join(Subject)
        .filter(
            Subject.college_id == _admin_college_id(),
            Exam.exam_date >= today,
            Exam.exam_date <= today + timedelta(days=7),
        )
        .order_by(Exam.exam_date)
        .limit(5)
        .all()
    )

    # Fee collection summary
    total_fee_expected = (
        db.session.query(func.sum(FeeStructure.amount))
        .outerjoin(Department, FeeStructure.department_id == Department.id)
        .filter(
            db.or_(
                FeeStructure.department_id.is_(None),
                Department.college_id == _admin_college_id(),
            )
        )
        .scalar()
        or 0
    )
    total_fee_collected = (
        db.session.query(func.sum(FeePayment.amount_paid))
        .join(Student, FeePayment.student_id == Student.id)
        .filter(
            Student.college_id == _admin_college_id(),
            FeePayment.status.in_(['paid', 'partial'])
        )
        .scalar()
        or 0
    )
    from models.leave import LeaveRequest
    pending_leaves = (
        LeaveRequest.query
        .join(Student, LeaveRequest.student_id == Student.id)
        .filter(
            Student.college_id == _admin_college_id(),
            LeaveRequest.status == 'pending',
        )
        .count()
    )

    return render_template('admin/dashboard.html',
                           dashboard_prefs=dashboard_prefs,
                           stats=stats, trend=trend,
                           dept_stats=dept_stats,
                           recent_sessions=recent_sessions,
                           recent_notices=recent_notices,
                           upcoming_exams=upcoming_exams,
                           total_fee_expected=total_fee_expected,
                           total_fee_collected=total_fee_collected,
                           pending_leaves=pending_leaves,
                           today=today)


# ─── Users ───────────────────────────────────────────────────────────────────

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    page   = request.args.get('page', 1, type=int)
    role   = request.args.get('role', '')
    search = request.args.get('q', '').strip()

    query = _scoped_user_query()
    if role:
        query = query.filter_by(role=role)
    if search:
        query = query.filter(
            db.or_(User.name.ilike(f'%{search}%'),
                   User.email.ilike(f'%{search}%'))
        )

    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=15, error_out=False
    )
    return render_template('admin/users.html',
                           pagination=pagination,
                           users=pagination.items,
                           selected_role=role,
                           search=search)


@admin_bp.route('/users/toggle/<int:uid>', methods=['POST'])
@login_required
@admin_required
def toggle_user(uid):
    user = _scoped_model_or_404(User, uid)
    if user.role == 'admin':
        flash('Cannot deactivate admin accounts.', 'warning')
    else:
        user.is_active = not user.is_active
        db.session.commit()
        flash(f"User {'activated' if user.is_active else 'deactivated'}.", 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/reset-password/<int:uid>', methods=['POST'])
@login_required
@admin_required
def reset_user_password(uid):
    user = _scoped_model_or_404(User, uid)
    new_pw = request.form.get('new_password', '').strip()
    if not _validate_temporary_password(new_pw):
        flash('Temporary password must be at least 8 characters and include uppercase, lowercase, a digit, and a special character.', 'danger')
    else:
        user.set_temporary_password(new_pw)
        db.session.commit()
        flash(f"Temporary password reset for {user.name}. They will be prompted to set a personal password on next login.", 'success')
    return redirect(url_for('admin.users'))


# ─── Departments ─────────────────────────────────────────────────────────────

@admin_bp.route('/departments', methods=['GET', 'POST'])
@login_required
@admin_required
def departments():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip().upper()
        if not name or not code:
            flash('Name and code are required.', 'danger')
        elif _scoped_department_query().filter_by(code=code).first():
            flash('Department code already exists.', 'danger')
        else:
            db.session.add(Department(college_id=_admin_college_id(), name=name, code=code))
            db.session.commit()
            flash(f'Department {code} added.', 'success')
    return render_template('admin/departments.html',
                           departments=_scoped_department_query().all())


@admin_bp.route('/departments/edit/<int:did>', methods=['POST'])
@login_required
@admin_required
def edit_department(did):
    dept = _scoped_model_or_404(Department, did)
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip().upper()
    if not name or not code:
        flash('Name and code are required.', 'danger')
        return redirect(url_for('admin.people_hub', tab='departments'))
    if code != dept.code and _scoped_department_query().filter_by(code=code).first():
        flash('Department code already exists.', 'danger')
        return redirect(url_for('admin.people_hub', tab='departments'))
    dept.name = name
    dept.code = code
    db.session.commit()
    flash(f'Department {code} updated.', 'success')
    return redirect(url_for('admin.people_hub', tab='departments'))


@admin_bp.route('/departments/delete/<int:did>', methods=['POST'])
@login_required
@admin_required
def delete_department(did):
    dept = _scoped_model_or_404(Department, did)
    db.session.delete(dept)
    db.session.commit()
    flash('Department deleted.', 'success')
    return redirect(url_for('admin.people_hub', tab='departments'))


@admin_bp.route('/departments/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_departments():
    cid = _admin_college_id()
    ids = request.form.getlist('ids', type=int)
    if not ids:
        flash('No departments selected.', 'warning')
        return redirect(url_for('admin.people_hub', tab='departments'))
    # Only delete departments with no students or teachers
    deleted, skipped = 0, 0
    depts = Department.query.filter(Department.id.in_(ids), Department.college_id == cid).all()
    for d in depts:
        if d.students or d.teachers:
            skipped += 1
        else:
            db.session.delete(d)
            deleted += 1
    db.session.commit()
    if deleted:
        flash(f'{deleted} department{"s" if deleted != 1 else ""} deleted.', 'success')
    if skipped:
        flash(f'{skipped} department{"s" if skipped != 1 else ""} skipped — still have linked students or teachers.', 'warning')
    return redirect(url_for('admin.people_hub', tab='departments'))


# ─── Students ────────────────────────────────────────────────────────────────

def _expected_semester_from_schedules(college_id: int, dept_id: int,
                                       admission_year: int) -> int | None:
    """
    Use SemesterSchedule records to find which semester is currently active
    for a student admitted in admission_year. Falls back to None if no schedules set.
    """
    from models.academic_calendar import SemesterSchedule
    today = date.today()
    # Find the highest semester whose start_date has passed for this batch
    schedules = SemesterSchedule.query.filter(
        SemesterSchedule.college_id == college_id,
        SemesterSchedule.academic_year == admission_year,
        db.or_(
            SemesterSchedule.department_id == None,
            SemesterSchedule.department_id == dept_id,
        ),
        SemesterSchedule.start_date <= today,
    ).order_by(SemesterSchedule.semester.desc()).all()

    if schedules:
        return schedules[0].semester  # highest started semester
    return None


def _student_track_status(student, current_year):
    """Return (status, semesters_diff) for a student vs expected progress."""
    if not student.admission_year:
        return 'unknown', 0

    # Prefer schedule-based expected semester
    expected_sem = _expected_semester_from_schedules(
        student.college_id, student.department_id, student.admission_year)

    # Fall back to year-math if no schedules configured
    if expected_sem is None:
        years_elapsed = max(0, current_year - student.admission_year)
        expected_sem = min(years_elapsed * 2 + 1, 8)

    diff = student.semester - expected_sem
    if diff >= 0:
        return 'on_track', diff
    elif diff >= -2:
        return 'behind', abs(diff)
    else:
        return 'far_behind', abs(diff)


@admin_bp.route('/students')
@login_required
@admin_required
def students():
    page        = request.args.get('page', 1, type=int)
    dept_id     = request.args.get('department_id', type=int)
    semester    = request.args.get('semester', type=int)
    adm_year    = request.args.get('admission_year', type=int)
    search      = request.args.get('q', '').strip()

    query = Student.query.join(User).filter(Student.college_id == _admin_college_id())
    if dept_id:
        query = query.filter(Student.department_id == dept_id)
    if semester:
        query = query.filter(Student.semester == semester)
    if adm_year:
        query = query.filter(Student.admission_year == adm_year)
    if search:
        query = query.filter(
            db.or_(User.name.ilike(f'%{search}%'),
                   Student.roll_number.ilike(f'%{search}%'))
        )

    pagination = query.order_by(Student.roll_number).paginate(
        page=page, per_page=15, error_out=False
    )
    departments = _scoped_department_query().order_by(Department.name).all()
    current_year = datetime.now().year

    # Distinct admission years for filter dropdown
    adm_years = [
        r[0] for r in
        db.session.query(Student.admission_year)
        .filter(Student.college_id == _admin_college_id(), Student.admission_year.isnot(None))
        .distinct().order_by(Student.admission_year.desc()).all()
    ]

    # Attach track status to each student on this page
    students_with_status = [
        (s, *_student_track_status(s, current_year))
        for s in pagination.items
    ]

    return render_template('admin/students.html',
                           pagination=pagination,
                           students_with_status=students_with_status,
                           departments=departments,
                           adm_years=adm_years,
                           selected_dept=dept_id,
                           selected_sem=semester,
                           selected_adm_year=adm_year,
                           search=search,
                           now=datetime.now())


@admin_bp.route('/batch-overview')
@login_required
@admin_required
def batch_overview():
    """Batch-wise analysis — shows all admission-year batches with progress tracking."""
    college_id   = _admin_college_id()
    current_year = datetime.now().year
    dept_filter  = request.args.get('department_id', type=int)
    year_filter  = request.args.get('admission_year', type=int)

    base_q = Student.query.join(User).filter(Student.college_id == college_id)
    if dept_filter:
        base_q = base_q.filter(Student.department_id == dept_filter)
    if year_filter:
        base_q = base_q.filter(Student.admission_year == year_filter)

    all_students = base_q.order_by(Student.admission_year, Student.department_id, Student.roll_number).all()
    departments  = _scoped_department_query().order_by(Department.name).all()
    dept_map     = {d.id: d for d in departments}

    adm_years = [
        r[0] for r in
        db.session.query(Student.admission_year)
        .filter(Student.college_id == college_id, Student.admission_year.isnot(None))
        .distinct().order_by(Student.admission_year.desc()).all()
    ]

    # Build batch groups: {(adm_year, dept_id): [students]}
    from collections import defaultdict
    groups = defaultdict(list)
    for s in all_students:
        key = (s.admission_year or 0, s.department_id)
        groups[key].append(s)

    batches = []
    for (adm_year, dept_id), sts in sorted(groups.items(), key=lambda x: (-x[0][0], x[0][1])):
        dept   = dept_map.get(dept_id)
        years_elapsed = max(0, current_year - adm_year) if adm_year else 0
        expected_sem  = min(years_elapsed * 2 + 1, 8) if adm_year else None

        counts = {'on_track': 0, 'behind': 0, 'far_behind': 0, 'unknown': 0}
        student_rows = []
        for s in sts:
            status, diff = _student_track_status(s, current_year)
            counts[status] += 1
            student_rows.append({
                'student': s,
                'status':  status,
                'diff':    diff,
                'expected_sem': expected_sem,
            })

        batches.append({
            'adm_year':     adm_year,
            'dept':         dept,
            'dept_id':      dept_id,
            'expected_sem': expected_sem,
            'total':        len(sts),
            'counts':       counts,
            'students':     student_rows,
            'year_label':   f"Year {years_elapsed + 1}" if adm_year else 'Unknown',
        })

    return render_template('admin/batch_overview.html',
                           batches=batches,
                           departments=departments,
                           adm_years=adm_years,
                           dept_filter=dept_filter,
                           year_filter=year_filter,
                           current_year=current_year)


@admin_bp.route('/batch-promote', methods=['POST'])
@login_required
@admin_required
def batch_promote():
    """Promote all on-track students in a batch to the next semester."""
    college_id  = _admin_college_id()
    dept_id     = request.form.get('dept_id', type=int)
    adm_year    = request.form.get('adm_year', type=int)
    current_year = datetime.now().year

    if not dept_id or not adm_year:
        flash('Invalid batch.', 'danger')
        return redirect(url_for('admin.attendance_hub', tab='batch_tracker'))

    students_in_batch = Student.query.filter_by(
        college_id=college_id, department_id=dept_id, admission_year=adm_year
    ).all()

    promoted = skipped = 0
    for s in students_in_batch:
        status, _ = _student_track_status(s, current_year)
        if status == 'on_track' and s.semester < 8:
            s.semester += 1
            promoted += 1
        else:
            skipped += 1

    db.session.commit()

    dept = Department.query.get(dept_id)
    dept_name = dept.name if dept else 'Unknown'
    flash(
        f'{promoted} student(s) in {dept_name} {adm_year} batch promoted to next semester. '
        f'{skipped} skipped (behind schedule or already at Semester 8).',
        'success'
    )
    return redirect(url_for('admin.attendance_hub', tab='batch_tracker',
                            admission_year=adm_year, department_id=dept_id))


@admin_bp.route('/students/preview-id')
@login_required
@admin_required
def preview_student_id():
    from datetime import datetime
    dept_id = request.args.get('dept_id', type=int)
    year = request.args.get('year', type=int) or datetime.now().year
    if not dept_id:
        return jsonify(id='')
    preview = Student.generate_roll_number(_admin_college_id(), dept_id, year)
    return jsonify(id=preview)


@admin_bp.route('/students/add', methods=['POST'])
@login_required
@admin_required
def add_student():
    from datetime import datetime
    name        = request.form.get('name', '').strip()
    email       = request.form.get('email', '').strip().lower()
    password    = request.form.get('password', '')
    auto_id     = request.form.get('auto_id') == '1'
    roll        = request.form.get('roll_number', '').strip().upper()
    dept_id     = request.form.get('department_id', type=int)
    semester    = request.form.get('semester', type=int)
    adm_year    = request.form.get('admission_year', type=int) or datetime.now().year
    reopen_target = {'open_modal': 'add-student'}

    if not all([name, email, password, dept_id, semester]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('admin.people_hub', tab='students', **reopen_target))

    if not auto_id and not roll:
        flash('Enter a roll number or choose Auto Generate.', 'danger')
        return redirect(url_for('admin.people_hub', tab='students', **reopen_target))

    if not _validate_temporary_password(password):
        flash('Temporary password must be at least 8 characters and include uppercase, lowercase, a digit, and a special character.', 'danger')
        return redirect(url_for('admin.people_hub', tab='students', **reopen_target))

    if _scoped_user_query().filter_by(email=email).first():
        flash('Email already registered.', 'danger')
        return redirect(url_for('admin.people_hub', tab='students', **reopen_target))

    department = _scoped_model_or_404(Department, dept_id)

    if auto_id:
        roll = Student.generate_roll_number(_admin_college_id(), dept_id, adm_year)
    else:
        if _scoped_student_query().filter_by(roll_number=roll).first():
            flash('Roll number already exists.', 'danger')
            return redirect(url_for('admin.people_hub', tab='students', **reopen_target))

    user = User(college_id=_admin_college_id(), name=name, email=email, role='student')
    user.set_temporary_password(password)
    db.session.add(user)
    db.session.flush()

    student = Student(
        college_id=_admin_college_id(),
        user_id=user.id,
        roll_number=roll,
        department_id=department.id,
        semester=semester,
        admission_year=adm_year,
    )
    db.session.add(student)
    db.session.commit()
    flash(f'Student {roll} added with a temporary password. The student will be prompted to set a personal password on first login.', 'success')
    return redirect(url_for('admin.people_hub', tab='students'))


@admin_bp.route('/students/edit/<int:sid>', methods=['POST'])
@login_required
@admin_required
def edit_student(sid):
    student = _scoped_model_or_404(Student, sid)
    student.user.name  = request.form.get('name', student.user.name).strip()
    student.semester   = request.form.get('semester', student.semester, type=int)
    dept_id = request.form.get('department_id', type=int)
    if dept_id:
        student.department_id = dept_id
    new_email = request.form.get('email', '').strip().lower()
    if new_email and new_email != student.user.email:
        if _scoped_user_query().filter(User.email == new_email, User.id != student.user_id).first():
            flash('Email already in use.', 'danger')
            return redirect(url_for('admin.people_hub', tab='students'))
        student.user.email = new_email
    db.session.commit()
    flash(f'Student {student.roll_number} updated.', 'success')
    return redirect(url_for('admin.people_hub', tab='students'))


@admin_bp.route('/students/import', methods=['POST'])
@login_required
@admin_required
def import_students():
    """Bulk import students from a CSV file.
    Expected columns: name, email, roll_number, department_code, semester, password
    """
    f = request.files.get('csv_file')
    if not f or not f.filename.endswith('.csv'):
        flash('Please upload a valid CSV file.', 'danger')
        return redirect(url_for('admin.people_hub', tab='students'))

    stream = io.StringIO(f.stream.read().decode('utf-8-sig'))
    reader = csv.DictReader(stream)
    added = skipped = errors = 0

    from datetime import datetime
    current_year = datetime.now().year
    for row in reader:
        try:
            name      = row.get('name', '').strip()
            email     = row.get('email', '').strip().lower()
            roll      = row.get('roll_number', '').strip().upper()
            dept_code = row.get('department_code', '').strip().upper()
            semester  = int(row.get('semester', 1))
            password  = row.get('password', 'Student@123!').strip()
            adm_year  = int(row.get('admission_year', current_year))

            if not all([name, email, dept_code]):
                errors += 1
                continue

            if not _validate_temporary_password(password):
                errors += 1
                continue

            if _scoped_user_query().filter_by(email=email).first():
                skipped += 1
                continue

            dept = _scoped_department_query().filter_by(code=dept_code).first()
            if not dept:
                errors += 1
                continue

            # Auto-generate roll number if not provided — uses admission year
            if not roll:
                roll = Student.generate_roll_number(_admin_college_id(), dept.id, adm_year)
            elif _scoped_student_query().filter_by(roll_number=roll).first():
                skipped += 1
                continue

            u = User(college_id=_admin_college_id(), name=name, email=email, role='student')
            u.set_temporary_password(password)
            db.session.add(u)
            db.session.flush()
            db.session.add(Student(
                college_id=_admin_college_id(),
                user_id=u.id,
                roll_number=roll,
                department_id=dept.id,
                semester=semester,
                admission_year=adm_year,
            ))
            added += 1
        except Exception:
            errors += 1

    db.session.commit()
    flash(f'Import complete: {added} added, {skipped} skipped (duplicates), {errors} errors.', 'info')
    return redirect(url_for('admin.people_hub', tab='students'))


@admin_bp.route('/students/export')
@login_required
@admin_required
def export_students():
    students = Student.query.join(User).filter(Student.college_id == _admin_college_id()).order_by(Student.roll_number).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['name', 'email', 'roll_number', 'department_code', 'semester'])
    for s in students:
        writer.writerow([s.user.name, s.user.email, s.roll_number,
                         s.department.code, s.semester])
    buf.seek(0)
    return send_file(io.BytesIO(buf.read().encode()),
                     mimetype='text/csv', as_attachment=True,
                     download_name='students_export.csv')


@admin_bp.route('/students/<int:sid>/attendance')
@login_required
@admin_required
def student_attendance(sid):
    student = _scoped_model_or_404(Student, sid)
    subjects = Subject.query.filter_by(
        department_id=student.department_id,
        semester=student.semester
    ).all()

    subject_stats = []
    for sub in subjects:
        total = AttendanceSession.query.filter_by(subject_id=sub.id, status='completed').count()
        present = AttendanceRecord.query.join(AttendanceSession).filter(
            AttendanceRecord.student_id == student.id,
            AttendanceSession.subject_id == sub.id,
            AttendanceSession.status == 'completed',
            AttendanceRecord.status == 'present'
        ).count()
        subject_stats.append({
            'subject': sub,
            'total': total,
            'present': present,
            'absent': total - present,
            'percentage': round(present / total * 100, 1) if total > 0 else 100.0,
        })

    rec_page = request.args.get('page', 1, type=int)
    records_pg = (AttendanceRecord.query
                  .join(AttendanceSession)
                  .filter(
                      AttendanceRecord.student_id == student.id,
                      AttendanceSession.status == 'completed'
                  )
                  .order_by(AttendanceSession.date.desc())
                  .paginate(page=rec_page, per_page=20, error_out=False))

    return render_template('admin/student_attendance.html',
                           student=student,
                           subject_stats=subject_stats,
                           records=records_pg.items,
                           records_pg=records_pg,
                           threshold=75)


@admin_bp.route('/students/delete/<int:sid>', methods=['POST'])
@login_required
@admin_required
def delete_student(sid):
    student = _scoped_model_or_404(Student, sid)
    db.session.delete(student.user)
    db.session.commit()
    flash('Student removed.', 'success')
    return redirect(url_for('admin.people_hub', tab='students'))


@admin_bp.route('/students/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_students():
    cid = _admin_college_id()
    ids = request.form.getlist('ids', type=int)
    if not ids:
        flash('No students selected.', 'warning')
        return redirect(url_for('admin.people_hub', tab='students'))
    students = Student.query.filter(Student.id.in_(ids), Student.college_id == cid).all()
    count = len(students)
    for s in students:
        db.session.delete(s.user)
    db.session.commit()
    flash(f'{count} student{"s" if count != 1 else ""} deleted.', 'success')
    return redirect(url_for('admin.people_hub', tab='students'))


# ─── Teachers ────────────────────────────────────────────────────────────────

@admin_bp.route('/teachers')
@login_required
@admin_required
def teachers():
    page    = request.args.get('page', 1, type=int)
    dept_id = request.args.get('department_id', type=int)
    search  = request.args.get('q', '').strip()

    query = Teacher.query.join(User).filter(Teacher.college_id == _admin_college_id())
    if dept_id:
        query = query.filter(Teacher.department_id == dept_id)
    if search:
        query = query.filter(
            db.or_(User.name.ilike(f'%{search}%'),
                   Teacher.employee_id.ilike(f'%{search}%'))
        )

    pagination = query.order_by(Teacher.employee_id).paginate(
        page=page, per_page=15, error_out=False
    )
    departments = _scoped_department_query().order_by(Department.name).all()
    return render_template('admin/teachers.html',
                           pagination=pagination,
                           teachers=pagination.items,
                           departments=departments,
                           selected_dept=dept_id,
                           search=search)


@admin_bp.route('/teachers/add', methods=['POST'])
@login_required
@admin_required
def add_teacher():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    emp_id = request.form.get('employee_id', '').strip().upper()
    dept_id = request.form.get('department_id', type=int)

    if not all([name, email, password, emp_id, dept_id]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('admin.people_hub', tab='teachers'))

    if not _validate_temporary_password(password):
        flash('Temporary password must be at least 8 characters and include uppercase, lowercase, a digit, and a special character.', 'danger')
        return redirect(url_for('admin.people_hub', tab='teachers'))

    if _scoped_user_query().filter_by(email=email).first():
        flash('Email already registered.', 'danger')
        return redirect(url_for('admin.people_hub', tab='teachers'))

    if _scoped_teacher_query().filter_by(employee_id=emp_id).first():
        flash('Employee ID already exists.', 'danger')
        return redirect(url_for('admin.people_hub', tab='teachers'))

    department = _scoped_model_or_404(Department, dept_id)

    user = User(college_id=_admin_college_id(), name=name, email=email, role='teacher')
    user.set_temporary_password(password)
    db.session.add(user)
    db.session.flush()

    teacher = Teacher(
        college_id=_admin_college_id(),
        user_id=user.id,
        employee_id=emp_id,
        department_id=department.id,
    )
    db.session.add(teacher)
    db.session.commit()
    flash(f'Teacher {emp_id} added with a temporary password. The teacher will be prompted to set a personal password on first login.', 'success')
    return redirect(url_for('admin.people_hub', tab='teachers'))


@admin_bp.route('/teachers/edit/<int:tid>', methods=['POST'])
@login_required
@admin_required
def edit_teacher(tid):
    teacher = _scoped_model_or_404(Teacher, tid)
    teacher.user.name = request.form.get('name', teacher.user.name).strip()
    dept_id = request.form.get('department_id', type=int)
    if dept_id:
        teacher.department_id = dept_id
    new_email = request.form.get('email', '').strip().lower()
    if new_email and new_email != teacher.user.email:
        if _scoped_user_query().filter(User.email == new_email, User.id != teacher.user_id).first():
            flash('Email already in use.', 'danger')
            return redirect(url_for('admin.people_hub', tab='teachers'))
        teacher.user.email = new_email
    db.session.commit()
    flash(f'Teacher {teacher.employee_id} updated.', 'success')
    return redirect(url_for('admin.people_hub', tab='teachers'))


@admin_bp.route('/teachers/delete/<int:tid>', methods=['POST'])
@login_required
@admin_required
def delete_teacher(tid):
    teacher = _scoped_model_or_404(Teacher, tid)
    db.session.delete(teacher.user)
    db.session.commit()
    flash('Teacher removed.', 'success')
    return redirect(url_for('admin.people_hub', tab='teachers'))


@admin_bp.route('/teachers/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_teachers():
    cid = _admin_college_id()
    ids = request.form.getlist('ids', type=int)
    if not ids:
        flash('No teachers selected.', 'warning')
        return redirect(url_for('admin.people_hub', tab='teachers'))
    teachers = Teacher.query.filter(Teacher.id.in_(ids), Teacher.college_id == cid).all()
    count = len(teachers)
    for t in teachers:
        db.session.delete(t.user)
    db.session.commit()
    flash(f'{count} teacher{"s" if count != 1 else ""} deleted.', 'success')
    return redirect(url_for('admin.people_hub', tab='teachers'))


# ─── Subjects ────────────────────────────────────────────────────────────────

@admin_bp.route('/subjects', methods=['GET', 'POST'])
@login_required
@admin_required
def subjects():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip().upper()
        dept_id = request.form.get('department_id', type=int)
        teacher_id = request.form.get('teacher_id', type=int)
        semester = request.form.get('semester', type=int)
        credits = request.form.get('credit_hours', 3, type=int)

        department = _scoped_model_or_404(Department, dept_id)
        teacher = _scoped_model_or_404(Teacher, teacher_id)

        if _scoped_subject_query().filter_by(code=code).first():
            flash('Subject code already exists.', 'danger')
        else:
            db.session.add(Subject(college_id=_admin_college_id(), name=name, code=code, department_id=department.id,
                                   teacher_id=teacher.id, semester=semester,
                                   credit_hours=credits))
            db.session.commit()
            flash(f'Subject {code} added.', 'success')
        return redirect(url_for('admin.academics_hub', tab='subjects',
                                department_id=request.form.get('department_id'),
                                semester=request.form.get('semester')))

    selected_dept = request.args.get('department_id', type=int)
    selected_sem  = request.args.get('semester', type=int)

    query = _scoped_subject_query()
    if selected_dept:
        query = query.filter_by(department_id=selected_dept)
    if selected_sem:
        query = query.filter_by(semester=selected_sem)
    all_subjects = query.order_by(Subject.department_id, Subject.semester, Subject.name).all()

    departments = _scoped_department_query().order_by(Department.name).all()
    teachers = Teacher.query.join(User).filter(Teacher.college_id == _admin_college_id()).order_by(User.name).all()
    return render_template('admin/subjects.html',
                           subjects=all_subjects,
                           departments=departments,
                           teachers=teachers,
                           selected_dept=selected_dept,
                           selected_sem=selected_sem)


@admin_bp.route('/subjects/edit/<int:sid>', methods=['POST'])
@login_required
@admin_required
def edit_subject(sid):
    subject = _scoped_model_or_404(Subject, sid)
    subject.name = request.form.get('name', subject.name).strip()
    new_code = request.form.get('code', '').strip().upper()
    if new_code and new_code != subject.code:
        if _scoped_subject_query().filter(Subject.code == new_code, Subject.id != sid).first():
            flash('Subject code already in use.', 'danger')
            return redirect(url_for('admin.academics_hub', tab='subjects'))
        subject.code = new_code
    dept_id = request.form.get('department_id', type=int)
    if dept_id:
        subject.department_id = dept_id
    teacher_id = request.form.get('teacher_id', type=int)
    if teacher_id:
        subject.teacher_id = teacher_id
    semester = request.form.get('semester', type=int)
    if semester:
        subject.semester = semester
    credits = request.form.get('credit_hours', type=int)
    if credits:
        subject.credit_hours = credits
    db.session.commit()
    flash(f'Subject {subject.code} updated.', 'success')
    return redirect(url_for('admin.academics_hub', tab='subjects'))


@admin_bp.route('/subjects/delete/<int:sid>', methods=['POST'])
@login_required
@admin_required
def delete_subject(sid):
    subject = _scoped_model_or_404(Subject, sid)
    db.session.delete(subject)
    db.session.commit()
    flash('Subject deleted.', 'success')
    return redirect(url_for('admin.academics_hub', tab='subjects'))


@admin_bp.route('/subjects/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_subjects():
    cid = _admin_college_id()
    ids = request.form.getlist('ids', type=int)
    if not ids:
        flash('No subjects selected.', 'warning')
        return redirect(url_for('admin.academics_hub', tab='subjects'))
    subjects = Subject.query.filter(Subject.id.in_(ids), Subject.college_id == cid).all()
    count = len(subjects)
    for s in subjects:
        db.session.delete(s)
    db.session.commit()
    flash(f'{count} subject{"s" if count != 1 else ""} deleted.', 'success')
    return redirect(url_for('admin.academics_hub', tab='subjects'))


# ─── Session Management ──────────────────────────────────────────────────────

@admin_bp.route('/sessions')
@login_required
@admin_required
def sessions():
    subject_id = request.args.get('subject_id', type=int)
    status_filter = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to   = request.args.get('date_to', '')

    query = AttendanceSession.query.join(Subject).filter(Subject.college_id == _admin_college_id())
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

    page = request.args.get('page', 1, type=int)
    pagination = query.order_by(
        AttendanceSession.date.desc(), AttendanceSession.start_time.desc()
    ).paginate(page=page, per_page=15, error_out=False)
    subjects = _scoped_subject_query().all()
    return render_template('admin/sessions.html',
                           pagination=pagination,
                           sessions=pagination.items,
                           subjects=subjects,
                           selected_subject_id=subject_id,
                           selected_status=status_filter,
                           date_from=date_from, date_to=date_to)


@admin_bp.route('/sessions/<int:sid>/cancel', methods=['POST'])
@login_required
@admin_required
def cancel_session(sid):
    session = db.session.get(AttendanceSession, sid)
    if session is None or session.subject.college_id != _admin_college_id():
        abort(404)
    if session.status != 'active':
        flash('Only active sessions can be cancelled.', 'warning')
    else:
        session.status = 'cancelled'
        session.end_time = utc_now_naive().time()
        db.session.commit()
        flash('Session cancelled.', 'info')
    return redirect(url_for('admin.attendance_hub', tab='sessions'))


# ─── Analytics ───────────────────────────────────────────────────────────────

@admin_bp.route('/analytics')
@login_required
@admin_required
def analytics():
    departments = _scoped_department_query().all()
    subjects = _scoped_subject_query().all()

    # Overall stats
    total_records = AttendanceRecord.query.join(AttendanceSession).join(Subject).filter(
        Subject.college_id == _admin_college_id(),
        AttendanceSession.status == 'completed'
    ).count()
    present_records = AttendanceRecord.query.join(AttendanceSession).join(Subject).filter(
        Subject.college_id == _admin_college_id(),
        AttendanceSession.status == 'completed',
        AttendanceRecord.status == 'present'
    ).count()
    overall_rate = round(present_records / total_records * 100, 1) if total_records > 0 else 0

    # Students below threshold
    threshold = 75
    low_attendance_students = []
    for student in _scoped_student_query().all():
        pct = student.get_attendance_percentage()
        if pct < threshold:
            low_attendance_students.append({
                'name': student.user.name,
                'roll': student.roll_number,
                'dept': student.department.name,
                'percentage': pct,
            })
    low_attendance_students.sort(key=lambda x: x['percentage'])

    # Monthly trend (last 6 months)
    monthly = []
    for i in range(5, -1, -1):
        month_start = date.today().replace(day=1) - timedelta(days=i * 30)
        month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        sessions = AttendanceSession.query.join(Subject).filter(
            Subject.college_id == _admin_college_id(),
            AttendanceSession.date >= month_start,
            AttendanceSession.date < month_end,
            AttendanceSession.status == 'completed'
        ).all()
        total = sum(s.total_students for s in sessions)
        present = sum(s.present_count for s in sessions)
        monthly.append({
            'month': month_start.strftime('%b %Y'),
            'rate': round(present / total * 100, 1) if total > 0 else 0,
        })

    return render_template('admin/analytics.html',
                           overall_rate=overall_rate,
                           total_records=total_records,
                           low_attendance_students=low_attendance_students,
                           monthly=monthly,
                           departments=departments,
                           subjects=subjects)


# ─── Parent Management ────────────────────────────────────────────────────────

@admin_bp.route('/parents')
@login_required
@admin_required
def parents():
    parents_list = _scoped_user_query().filter_by(role='parent', is_active=True).all()
    students = _scoped_student_query().order_by(Student.roll_number).all()
    links = (
        ParentStudent.query
        .join(Student, ParentStudent.student_id == Student.id)
        .filter(Student.college_id == _admin_college_id())
        .all()
    )
    # Map parent_id -> list of (link, student)
    parent_children = {}
    for link in links:
        parent_children.setdefault(link.parent_id, []).append(link)
    return render_template('admin/parents.html',
                           parents_list=parents_list,
                           students=students,
                           parent_children=parent_children)


@admin_bp.route('/parents/add', methods=['POST'])
@login_required
@admin_required
def add_parent():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    student_id = request.form.get('student_id', type=int)
    relationship = request.form.get('relationship', 'guardian')

    if not all([name, email, password, student_id]):
        flash('Name, email, password and student are required.', 'danger')
        return redirect(url_for('admin.people_hub', tab='parents'))

    if not _validate_temporary_password(password):
        flash('Temporary password must be at least 8 characters and include uppercase, lowercase, a digit, and a special character.', 'danger')
        return redirect(url_for('admin.people_hub', tab='parents'))

    if _scoped_user_query().filter_by(email=email).first():
        flash(f'Email {email} is already registered.', 'danger')
        return redirect(url_for('admin.people_hub', tab='parents'))

    student = db.session.get(Student, student_id)
    if not student or student.college_id != _admin_college_id():
        flash('Student not found.', 'danger')
        return redirect(url_for('admin.people_hub', tab='parents'))

    user = User(college_id=_admin_college_id(), name=name, email=email, role='parent', is_active=True)
    user.set_temporary_password(password)
    db.session.add(user)
    db.session.flush()

    link = ParentStudent(college_id=_admin_college_id(), parent_id=user.id, student_id=student_id,
                         relationship=relationship)
    db.session.add(link)
    db.session.commit()
    flash(f'Parent {name} created and linked to {student.user.name}. They will be prompted to set a personal password on first login.', 'success')
    return redirect(url_for('admin.people_hub', tab='parents'))


@admin_bp.route('/parents/<int:parent_id>/link', methods=['POST'])
@login_required
@admin_required
def link_parent_child(parent_id):
    parent_user = _scoped_user_query().filter_by(id=parent_id, role='parent').first_or_404()
    student_id = request.form.get('student_id', type=int)
    relationship = request.form.get('relationship', 'guardian')

    if not student_id:
        flash('Select a student to link.', 'danger')
        return redirect(url_for('admin.people_hub', tab='parents'))

    if ParentStudent.query.filter_by(parent_id=parent_id, student_id=student_id).first():
        flash('This child is already linked to this parent.', 'warning')
        return redirect(url_for('admin.people_hub', tab='parents'))

    student = db.session.get(Student, student_id)
    if not student or student.college_id != _admin_college_id():
        flash('Student not found.', 'danger')
        return redirect(url_for('admin.people_hub', tab='parents'))

    db.session.add(ParentStudent(college_id=_admin_college_id(), parent_id=parent_id, student_id=student_id,
                                  relationship=relationship))
    db.session.commit()
    flash(f'Linked {student.user.name} to {parent_user.name}.', 'success')
    return redirect(url_for('admin.people_hub', tab='parents'))


@admin_bp.route('/parents/unlink/<int:link_id>', methods=['POST'])
@login_required
@admin_required
def unlink_parent_child(link_id):
    link = ParentStudent.query.get_or_404(link_id)
    if link.student.college_id != _admin_college_id():
        abort(404)
    child_name = link.student.user.name
    db.session.delete(link)
    db.session.commit()
    flash(f'Unlinked {child_name} from parent.', 'success')
    return redirect(url_for('admin.people_hub', tab='parents'))


@admin_bp.route('/parents/delete/<int:parent_id>', methods=['POST'])
@login_required
@admin_required
def delete_parent(parent_id):
    user = _scoped_user_query().filter_by(id=parent_id, role='parent').first_or_404()
    ParentStudent.query.filter_by(parent_id=parent_id).delete()
    db.session.delete(user)
    db.session.commit()
    flash('Parent account deleted.', 'success')
    return redirect(url_for('admin.people_hub', tab='parents'))


# ─── Class Alert Trigger ──────────────────────────────────────────────────────

@admin_bp.route('/class-alerts/trigger', methods=['POST'])
@login_required
@admin_required
def trigger_class_alerts():
    """Manual admin trigger: send absent-teacher alerts for overdue classes today."""
    from datetime import datetime, date
    from models.timetable import TimetableSlot
    from models.parent import ClassAlert
    from services.notification_service import send_absent_teacher_alert

    now = datetime.now()
    today = date.today()
    today_dow = today.weekday()
    cutoff = now.replace(second=0, microsecond=0)

    slots = (
        TimetableSlot.query
        .join(Department, TimetableSlot.department_id == Department.id)
        .filter(
            Department.college_id == _admin_college_id(),
            TimetableSlot.day_of_week == today_dow,
            TimetableSlot.slot_type == 'class',
        )
        .all()
    )

    total_sent = 0
    for slot in slots:
        if not slot.subject:
            continue
        slot_end = datetime.combine(today, slot.end_time)
        if (cutoff - slot_end).total_seconds() < 15 * 60:
            continue
        session = AttendanceSession.query.filter(
            AttendanceSession.subject_id == slot.subject_id,
            AttendanceSession.date == today,
            AttendanceSession.status.in_(['active', 'completed'])
        ).first()
        if session:
            continue
        existing = ClassAlert.query.filter_by(
            slot_id=slot.id, alert_date=today
        ).first()
        if existing:
            continue

        students = Student.query.filter_by(
            department_id=slot.department_id,
            semester=slot.semester
        ).all()
        recipients = []
        for s in students:
            if s.user.email:
                recipients.append(s.user.email)
            for link in ParentStudent.query.filter_by(student_id=s.id).all():
                pu = db.session.get(User, link.parent_id)
                if pu and pu.email:
                    recipients.append(pu.email)
        recipients = list(set(recipients))

        teacher = slot.subject.teacher
        teacher_name = teacher.user.name if teacher else 'Unknown'
        slot_time = f"{slot.start_time.strftime('%H:%M')} – {slot.end_time.strftime('%H:%M')}"
        dept_name = slot.department.name if slot.department else 'N/A'

        sent = send_absent_teacher_alert(
            recipients=recipients,
            subject_name=slot.subject.name,
            teacher_name=teacher_name,
            slot_time=slot_time,
            department=dept_name,
            semester=slot.semester or 0,
        )
        db.session.add(ClassAlert(college_id=_admin_college_id(), slot_id=slot.id, alert_date=today,
                                   recipient_count=sent, triggered_by='manual'))
        db.session.commit()
        total_sent += sent

    flash(f'Class alerts sent: {total_sent} notifications dispatched.', 'success')
    return redirect(url_for('admin.people_hub', tab='parents'))


# ─── College Settings ─────────────────────────────────────────────────────────

@admin_bp.route('/settings', methods=['GET'])
@login_required
@admin_required
def settings():
    cs = CollegeSetting.get()
    return render_template('admin/settings.html', cs=cs)


@admin_bp.route('/settings/save', methods=['POST'])
@login_required
@admin_required
def save_settings():
    cs = CollegeSetting.get()
    cs.college_name = request.form.get('college_name', '').strip() or cs.college_name
    cs.address = request.form.get('address', '').strip() or None

    lat = request.form.get('latitude', '').strip()
    lng = request.form.get('longitude', '').strip()
    try:
        if lat and lng:
            cs.latitude  = float(lat)
            cs.longitude = float(lng)
            if not (-90 <= cs.latitude <= 90 and -180 <= cs.longitude <= 180):
                raise ValueError
    except ValueError:
        flash('Invalid coordinates — please pick a location on the map.', 'danger')
        return redirect(url_for('admin.settings'))

    logo_file = request.files.get('college_logo')
    if logo_file and logo_file.filename:
        allowed = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'}
        ext = logo_file.filename.rsplit('.', 1)[-1].lower()
        if ext not in allowed:
            flash('Logo must be a PNG, JPG, GIF, SVG, or WebP image.', 'danger')
            return redirect(url_for('admin.settings'))
        logo_dir = os.path.join(current_app.static_folder, 'uploads', 'college_logos')
        os.makedirs(logo_dir, exist_ok=True)
        slug = current_user.college.code.lower()
        fname = f'{slug}_logo.{ext}'
        logo_file.save(os.path.join(logo_dir, fname))
        cs.logo_path = f'uploads/college_logos/{fname}'

    cs.updated_at = utc_now_naive()
    db.session.commit()
    flash('College settings saved successfully.', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/settings/signatures', methods=['POST'])
@login_required
@admin_required
def save_signatures():
    cs = CollegeSetting.get()
    sign_dir = os.path.join(current_app.static_folder, 'uploads', 'signatures')
    os.makedirs(sign_dir, exist_ok=True)

    cs.principal_name     = request.form.get('principal_sign_name', '').strip() or cs.principal_name
    cs.hod_name           = request.form.get('hod_sign_name', '').strip() or cs.hod_name
    cs.class_teacher_name = request.form.get('class_teacher_sign_name', '').strip() or cs.class_teacher_name

    for field, attr in [
        ('principal_sign',     'principal_sign_path'),
        ('hod_sign',           'hod_sign_path'),
        ('class_teacher_sign', 'class_teacher_sign_path'),
    ]:
        f = request.files.get(field)
        if f and f.filename:
            ext = secure_filename(f.filename).rsplit('.', 1)[-1].lower()
            if ext in ('png', 'jpg', 'jpeg', 'svg', 'webp'):
                fname = f'{field}.{ext}'
                f.save(os.path.join(sign_dir, fname))
                setattr(cs, attr, f'uploads/signatures/{fname}')

    db.session.commit()
    flash('Signatures saved successfully.', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/geocode')
@login_required
@admin_required
@limiter.limit('30 per minute')
def geocode():
    """Server-side proxy for Nominatim geocoding — avoids browser CORS/CSP issues."""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    try:
        url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode({
            'q': q, 'format': 'json', 'limit': 6, 'addressdetails': 0
        })
        req = urllib.request.Request(url, headers={
            'User-Agent': 'SmartAttend/1.0 (college-management)',
            'Accept-Language': 'en'
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read().decode())
        results = [{'name': item['display_name'], 'lat': float(item['lat']), 'lng': float(item['lon'])}
                   for item in data]
        return jsonify(results)
    except Exception as exc:
        return jsonify(error=str(exc)), 502


# ─── Digital ID Card ──────────────────────────────────────────────────────────

_ID_TEMPLATE_DIR = None

def _id_template_dir():
    global _ID_TEMPLATE_DIR
    if _ID_TEMPLATE_DIR is None:
        from flask import current_app
        d = os.path.join(current_app.root_path, 'static', 'uploads', 'id_templates')
        os.makedirs(d, exist_ok=True)
        _ID_TEMPLATE_DIR = d
    return _ID_TEMPLATE_DIR


def _save_template_file(file_obj, filename, college):
    college_slug = secure_filename((college.code or f'college-{college.id}').lower()) or f'college-{college.id}'
    rel_dir = os.path.join('uploads', 'id_templates', college_slug)
    abs_dir = os.path.join(current_app.root_path, 'static', rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    path = os.path.join(abs_dir, secure_filename(filename))
    file_obj.save(path)
    return f"{rel_dir}/{secure_filename(filename)}"


@admin_bp.route('/id-card-template', methods=['GET', 'POST'])
@login_required
@admin_required
def id_card_template():
    tpl = IDCardTemplate.get(current_user.college)
    if request.method == 'POST':
        tpl.principal_name  = request.form.get('principal_name', '').strip() or tpl.principal_name
        tpl.principal_title = request.form.get('principal_title', 'Principal').strip()
        tpl.college_phone   = request.form.get('college_phone', '').strip() or None
        tpl.college_website = request.form.get('college_website', '').strip() or None
        tpl.card_color      = request.form.get('card_color', '#1e3a5f')
        tpl.accent_color    = request.form.get('accent_color', '#e63946')
        try:
            tpl.valid_years = int(request.form.get('valid_years', 4))
        except ValueError:
            pass
        try:
            tpl.map_lat = float(request.form['map_lat']) if request.form.get('map_lat','').strip() else None
            tpl.map_lng = float(request.form['map_lng']) if request.form.get('map_lng','').strip() else None
        except ValueError:
            pass

        logo = request.files.get('logo')
        if logo and logo.filename:
            tpl.logo_path = _save_template_file(logo, 'logo.png', current_user.college)

        sig = request.files.get('principal_signature')
        if sig and sig.filename:
            tpl.principal_signature_path = _save_template_file(sig, 'signature.png', current_user.college)

        college_img = request.files.get('college_image')
        if college_img and college_img.filename:
            tpl.college_image_path = _save_template_file(college_img, 'college_image.jpg', current_user.college)

        tpl.updated_at = utc_now_naive()
        db.session.commit()
        flash('ID card template saved.', 'success')
        return redirect(url_for('admin.id_card_template'))

    from models.setting import CollegeSetting
    cs = CollegeSetting.get()
    return render_template('admin/id_card_template.html', tpl=tpl, cs=cs)


@admin_bp.route('/id-cards')
@login_required
@admin_required
def id_cards():
    status_filter = request.args.get('status', '')
    dept_filter   = request.args.get('dept', '').strip()
    sem_filter    = request.args.get('sem', '').strip()
    q             = request.args.get('q', '').strip()

    query = (StudentIDCard.query
             .filter(StudentIDCard.college_id == _admin_college_id())
             .join(Student)
             .join(User, Student.user_id == User.id)
             .join(Department, Student.department_id == Department.id)
             .order_by(Department.name, Student.semester, User.name))

    if status_filter in ('pending', 'approved', 'rejected'):
        query = query.filter(StudentIDCard.status == status_filter)
    if dept_filter:
        try:
            query = query.filter(Student.department_id == int(dept_filter))
        except ValueError:
            pass
    if sem_filter:
        try:
            query = query.filter(Student.semester == int(sem_filter))
        except ValueError:
            pass
    if q:
        query = query.filter(
            db.or_(
                User.name.ilike(f'%{q}%'),
                Student.roll_number.ilike(f'%{q}%')
            )
        )

    page     = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    if per_page not in (10, 20, 50):
        per_page = 20

    pagination  = query.paginate(page=page, per_page=per_page, error_out=False)
    cards       = pagination.items
    departments = _scoped_department_query().order_by(Department.name).all()
    tpl         = IDCardTemplate.get(current_user.college)
    cs          = CollegeSetting.get()
    counts = {
        'all': StudentIDCard.query.join(Student).filter(Student.college_id == _admin_college_id()).count(),
        'pending': StudentIDCard.query.join(Student).filter(
            Student.college_id == _admin_college_id(),
            StudentIDCard.status == 'pending',
        ).count(),
        'approved': StudentIDCard.query.join(Student).filter(
            Student.college_id == _admin_college_id(),
            StudentIDCard.status == 'approved',
        ).count(),
        'rejected': StudentIDCard.query.join(Student).filter(
            Student.college_id == _admin_college_id(),
            StudentIDCard.status == 'rejected',
        ).count(),
    }
    return render_template('admin/id_cards.html',
                           cards=cards, pagination=pagination,
                           per_page=per_page, tpl=tpl, cs=cs,
                           counts=counts, status_filter=status_filter,
                           dept_filter=dept_filter, sem_filter=sem_filter,
                           q=q, departments=departments)


@admin_bp.route('/id-cards/<int:cid>/approve', methods=['POST'])
@login_required
@admin_required
def approve_id_card(cid):
    card = _scoped_model_or_404(StudentIDCard, cid)
    card.status      = 'approved'
    card.reviewed_at = utc_now_naive()
    card.reviewed_by = current_user.id
    card.rejection_note = None
    if not card.card_number:
        s = card.student
        card.card_number = f"{current_user.college.code}-{s.department.code}-{s.roll_number}"
    db.session.commit()
    flash(f'ID card approved for {card.student.user.name}.', 'success')
    return redirect(url_for('admin.id_cards', status='pending'))


@admin_bp.route('/id-cards/<int:cid>/reject', methods=['POST'])
@login_required
@admin_required
def reject_id_card(cid):
    card = _scoped_model_or_404(StudentIDCard, cid)
    card.status         = 'rejected'
    card.reviewed_at    = utc_now_naive()
    card.reviewed_by    = current_user.id
    card.rejection_note = request.form.get('rejection_note', '').strip()
    db.session.commit()
    flash(f'ID card rejected for {card.student.user.name}.', 'warning')
    return redirect(url_for('admin.id_cards', status='pending'))


@admin_bp.route('/id-cards/<int:cid>/view')
@login_required
@admin_required
def view_id_card(cid):
    from utils.qr_utils import make_id_card_qr, get_map_tile_b64
    card    = _scoped_model_or_404(StudentIDCard, cid)
    tpl     = IDCardTemplate.get(current_user.college)
    cs      = CollegeSetting.get()
    qr_img  = make_id_card_qr(card.student, card)
    map_url = (get_map_tile_b64(tpl.map_lat, tpl.map_lng)
               if tpl.map_lat is not None and tpl.map_lng is not None else None)
    return render_template('admin/id_card_view.html',
                           card=card, student=card.student, tpl=tpl, cs=cs,
                           qr_img=qr_img, map_url=map_url)


# ─────────────────────────────────────────────────────────────────────────────
# File Manager
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_size(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} GB'


@admin_bp.route('/files')
@login_required
@admin_required
def file_manager():
    from models.content import TeacherContent
    for upload_dir in content_storage_dirs(current_app):
        os.makedirs(upload_dir, exist_ok=True)

    # Build a lookup: rel_path → content record
    all_content = TeacherContent.query.filter_by(college_id=_admin_college_id()).all()
    path_map    = {c.file_path: c for c in all_content if c.file_path}

    type_filter = request.args.get('type', '')
    q           = request.args.get('q', '').strip().lower()

    files = []
    seen = set()
    for upload_dir in content_storage_dirs(current_app):
        for fname in sorted(os.listdir(upload_dir)):
            if fname in seen:
                continue
            fpath = os.path.join(upload_dir, fname)
            if not os.path.isfile(fpath):
                continue
            seen.add(fname)
            rel   = f'uploads/content/{fname}'
            ext   = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            size  = os.path.getsize(fpath)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            ct    = path_map.get(rel)

            if type_filter and ext != type_filter:
                continue
            if q and q not in fname.lower() and (not ct or q not in ct.title.lower()):
                continue

            files.append({
                'name':    fname,
                'rel':     rel,
                'ext':     ext,
                'size':    size,
                'size_str': _fmt_size(size),
                'mtime':   mtime,
                'content': ct,
                'orphan':  ct is None,
                'location': 'private' if os.path.abspath(upload_dir) == os.path.abspath(current_app.config['CONTENT_UPLOAD_FOLDER']) else 'legacy',
            })

    total_size  = sum(f['size'] for f in files)
    orphan_count = sum(1 for f in files if f['orphan'])
    ext_counts  = {}
    for f in files:
        ext_counts[f['ext']] = ext_counts.get(f['ext'], 0) + 1

    return render_template('admin/files.html',
                           files=files,
                           total_size=_fmt_size(total_size),
                           orphan_count=orphan_count,
                           ext_counts=ext_counts,
                           type_filter=type_filter, q=q)


@admin_bp.route('/files/delete', methods=['POST'])
@login_required
@admin_required
def delete_file():
    from models.content import TeacherContent
    rel = request.form.get('rel', '').strip()

    # Safety: reject path traversal and anything outside uploads/content
    if not is_valid_content_relpath(rel):
        flash('Invalid file path.', 'danger')
        return redirect(url_for('admin.file_manager'))

    abs_path = resolve_content_path(current_app, rel)

    # Clear DB reference
    TeacherContent.query.filter_by(college_id=_admin_college_id(), file_path=rel).update({'file_path': None})

    # Remove physical file
    if abs_path and os.path.isfile(abs_path):
        os.remove(abs_path)
        flash(f'Deleted: {os.path.basename(rel)}', 'info')
    else:
        flash('File not found on disk — reference cleared.', 'warning')

    db.session.commit()
    return redirect(url_for('admin.file_manager'))


@admin_bp.route('/files/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_files():
    from models.content import TeacherContent
    rels     = request.form.getlist('files')
    scope    = request.form.get('scope', '')   # 'orphans' triggers orphan sweep

    if scope == 'orphans':
        # Collect all files on disk that have no matching content record
        linked      = {c.file_path for c in TeacherContent.query.filter_by(college_id=_admin_college_id()).all() if c.file_path}
        rels = []
        seen = set()
        for upload_dir in content_storage_dirs(current_app):
            for fname in os.listdir(upload_dir):
                if fname in seen:
                    continue
                rel = 'uploads/content/' + fname
                if rel not in linked:
                    rels.append(rel)
                seen.add(fname)

    if not rels:
        flash('No files to delete.', 'warning')
        return redirect(url_for('admin.file_manager'))

    deleted = 0
    for rel in rels:
        if not is_valid_content_relpath(rel):
            continue
        abs_path = resolve_content_path(current_app, rel)
        TeacherContent.query.filter_by(college_id=_admin_college_id(), file_path=rel).update({'file_path': None})
        if abs_path and os.path.isfile(abs_path):
            os.remove(abs_path)
            deleted += 1

    db.session.commit()
    flash(f'{deleted} file(s) deleted.', 'info')
    return redirect(url_for('admin.file_manager'))


@admin_bp.route('/files/view')
@login_required
@admin_required
def view_file():
    rel = request.args.get('rel', '').strip()
    abs_path = resolve_content_path(current_app, rel)
    if not abs_path or not os.path.isfile(abs_path):
        flash('File not found.', 'warning')
        return redirect(url_for('admin.file_manager'))

    return send_file(
        abs_path,
        as_attachment=request.args.get('download', '1') != '0',
        download_name=os.path.basename(abs_path),
        conditional=True,
    )


@admin_bp.route('/files/preview')
@login_required
@admin_required
def preview_file():
    import html
    from types import SimpleNamespace
    from utils.file_preview import (
        pptx_to_html,
        docx_to_html,
        preview_exception_message,
        infer_preview_type,
    )
    from models.content import TeacherContent

    rel = request.args.get('rel', '').strip()
    if not is_valid_content_relpath(rel):
        flash('Invalid file path.', 'danger')
        return redirect(url_for('admin.file_manager'))

    abs_path = resolve_content_path(current_app, rel)
    if not abs_path or not os.path.isfile(abs_path):
        flash('File not found.', 'warning')
        return redirect(url_for('admin.file_manager'))

    item = TeacherContent.query.filter_by(college_id=_admin_college_id(), file_path=rel).first()
    ext = infer_preview_type(rel, abs_path)
    file_url = url_for('admin.view_file', rel=rel, download=0)
    download_url = url_for('admin.view_file', rel=rel)
    preview_type = ext or 'content'
    preview_html = None
    error = None

    if ext == 'pptx':
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

    preview_item = SimpleNamespace(
        title=item.title if item else os.path.basename(abs_path),
        content_type=item.content_type if item else 'note',
        subject=item.subject if item else None,
        due_date=getattr(item, 'due_date', None) if item else None,
        marks=getattr(item, 'marks', None) if item else None,
        body=item.body if item else None,
    )

    return render_template(
        'student/content_preview.html',
        item=preview_item,
        preview_type=preview_type,
        file_url=file_url,
        download_url=download_url,
        preview_html=preview_html,
        error=error,
        back_url=url_for('admin.file_manager'),
        show_note_body=False,
        preview_heading='Admin File Preview',
    )


# ── Admin: marksheet management ───────────────────────────────────────────────

@admin_bp.route('/marksheets')
@login_required
@admin_required
def marksheet_list():
    q       = request.args.get('q', '').strip()
    dept_id = request.args.get('dept_id', type=int)
    sem     = request.args.get('sem', type=int)

    query = Student.query.join(User, Student.user_id == User.id).filter(Student.college_id == _admin_college_id())
    if q:
        query = query.filter(
            db.or_(User.name.ilike(f'%{q}%'), Student.roll_number.ilike(f'%{q}%'))
        )
    if dept_id:
        query = query.filter(Student.department_id == dept_id)
    if sem:
        query = query.filter(Student.semester == sem)

    students    = query.order_by(Student.roll_number).all()
    departments = _scoped_department_query().order_by(Department.name).all()
    semesters   = sorted({s.semester for s in _scoped_student_query().all()})

    return render_template('admin/marksheets.html',
                           students=students, departments=departments,
                           semesters=semesters, q=q,
                           dept_id=dept_id, sem=sem)


@admin_bp.route('/marksheet/<int:student_id>')
@login_required
@admin_required
def admin_marksheet(student_id):
    from routes.exam import build_marksheet_data
    student  = _scoped_model_or_404(Student, student_id)
    semester = request.args.get('semester', type=int)
    data     = build_marksheet_data(student, semester=semester)
    return render_template('exam/marksheet.html', **data, is_admin=True, is_parent=False)


# ── Admin: marksheet signature management ─────────────────────────────────────

@admin_bp.route('/marksheet-signatures')
@login_required
@admin_required
def marksheet_signatures():
    from models.marksheet_signature import MarksheetSignature

    departments = _scoped_department_query().order_by(Department.name).all()
    principal   = MarksheetSignature.query.filter_by(college_id=_admin_college_id(), role='principal').first()
    hod_map   = {s.department_id: s for s in
                 MarksheetSignature.query.filter_by(college_id=_admin_college_id(), role='hod').all()}

    return render_template('admin/marksheet_signatures.html',
                           departments=departments,
                           principal=principal,
                           hod_map=hod_map)


@admin_bp.route('/marksheet-signatures/save', methods=['POST'])
@login_required
@admin_required
def save_marksheet_signature():
    from models.marksheet_signature import MarksheetSignature

    role    = request.form.get('role', '').strip()
    dept_id = request.form.get('department_id', type=int)
    name    = request.form.get('name', '').strip()
    desig   = request.form.get('designation', '').strip()

    if role not in ('principal', 'hod'):
        flash('Invalid role.', 'danger')
        return redirect(url_for('admin.academics_hub', tab='signatures'))

    if role == 'principal':
        dept_id = None
        if not name:
            flash('Name is required for Principal.', 'danger')
            return redirect(url_for('admin.academics_hub', tab='signatures'))
    elif role == 'hod':
        if not dept_id or not name:
            flash('Department and name are required for HoD.', 'danger')
            return redirect(url_for('admin.academics_hub', tab='signatures'))

    # Upsert
    sig = MarksheetSignature.query.filter_by(
        college_id=_admin_college_id(), role=role, department_id=dept_id, semester=None
    ).first()
    if not sig:
        sig = MarksheetSignature(college_id=_admin_college_id(), role=role, department_id=dept_id, semester=None)
        db.session.add(sig)

    sig.teacher_id  = None
    sig.name        = name
    sig.designation = desig or None
    # Handle signature image upload
    sign_file = request.files.get('sign_image')
    if sign_file and sign_file.filename:
        ext = secure_filename(sign_file.filename).rsplit('.', 1)[-1].lower()
        if ext in ('png', 'jpg', 'jpeg', 'svg', 'webp'):
            sign_dir = os.path.join(current_app.static_folder, 'uploads', 'signatures')
            os.makedirs(sign_dir, exist_ok=True)
            tag   = f"{role}_{dept_id or 0}_0"
            fname = f"ms_sig_{tag}.{ext}"
            sign_file.save(os.path.join(sign_dir, fname))
            sig.sign_path = f'uploads/signatures/{fname}'

    db.session.commit()
    flash(f'Signature for {sig.role_label} saved.', 'success')
    return redirect(url_for('admin.academics_hub', tab='signatures'))


@admin_bp.route('/marksheet-signatures/<int:sig_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_marksheet_signature(sig_id):
    from models.marksheet_signature import MarksheetSignature
    sig = MarksheetSignature.query.filter_by(id=sig_id, college_id=_admin_college_id()).first_or_404()

    if sig.sign_path:
        abs_path = os.path.join(current_app.static_folder, sig.sign_path)
        if os.path.isfile(abs_path):
            os.remove(abs_path)

    db.session.delete(sig)
    db.session.commit()
    flash('Signature removed.', 'info')
    return redirect(url_for('admin.academics_hub', tab='signatures'))


# ─── Reports ──────────────────────────────────────────────────────────────────

@admin_bp.route('/reports/send-weekly', methods=['POST'])
@login_required
@admin_required
def send_weekly_report_now():
    """Manually trigger weekly attendance report for this college, respecting saved filters."""
    from threading import Thread
    from services.attendance_report import run_weekly_reports
    from models.academic_calendar import ReportScheduleConfig
    app = current_app._get_current_object()
    college_id = _admin_college_id()

    cfg = ReportScheduleConfig.query.filter_by(college_id=college_id).first()
    dept_ids  = (cfg.filter_department_ids  or []) if cfg else []
    semesters = (cfg.filter_semesters        or []) if cfg else []
    adm_years = (cfg.filter_admission_years  or []) if cfg else []

    def run():
        result = run_weekly_reports(
            app, college_id=college_id,
            department_ids=dept_ids or None,
            semesters=semesters or None,
            admission_years=adm_years or None,
        )
        app.logger.info(f'Manual weekly report: {result}')

    Thread(target=run, daemon=True).start()
    flash('Weekly attendance reports are being sent in the background. Students and parents will receive emails shortly.', 'success')
    return redirect(request.referrer or url_for('admin.semester_schedules'))


@admin_bp.route('/reports/schedule/save', methods=['POST'])
@login_required
@admin_required
def save_report_schedule():
    """Save or update the automated report schedule config for this college."""
    from models.academic_calendar import ReportScheduleConfig
    college_id = _admin_college_id()

    enabled    = request.form.get('enabled') == '1'
    send_day   = request.form.get('send_day', type=int, default=0)
    send_hour  = request.form.get('send_hour', type=int, default=7)
    send_minute = request.form.get('send_minute', type=int, default=0)

    dept_ids  = [int(x) for x in request.form.getlist('filter_department_ids')  if x.isdigit()]
    semesters = [int(x) for x in request.form.getlist('filter_semesters')        if x.isdigit()]
    adm_years = [int(x) for x in request.form.getlist('filter_admission_years')  if x.isdigit()]

    cfg = ReportScheduleConfig.query.filter_by(college_id=college_id).first()
    if not cfg:
        cfg = ReportScheduleConfig(college_id=college_id)
        db.session.add(cfg)

    cfg.enabled    = enabled
    cfg.send_day   = max(0, min(6, send_day))
    cfg.send_hour  = max(0, min(23, send_hour))
    cfg.send_minute = max(0, min(59, send_minute))
    cfg.filter_department_ids  = dept_ids
    cfg.filter_semesters       = semesters
    cfg.filter_admission_years = adm_years
    cfg.updated_by = current_user.id

    db.session.commit()
    flash('Report schedule saved successfully.', 'success')
    return redirect(url_for('admin.semester_schedules'))


# ─── Semester Schedules ───────────────────────────────────────────────────────

@admin_bp.route('/semester-schedules')
@login_required
@admin_required
def semester_schedules():
    from models.academic_calendar import SemesterSchedule, ReportScheduleConfig, DAYS_OF_WEEK
    college_id = _admin_college_id()
    schedules = SemesterSchedule.query.filter_by(college_id=college_id).order_by(
        SemesterSchedule.academic_year.desc(), SemesterSchedule.semester,
    ).all()
    departments = _scoped_department_query().order_by(Department.name).all()
    report_cfg  = ReportScheduleConfig.query.filter_by(college_id=college_id).first()

    # Distinct admission years present in this college
    adm_years_raw = db.session.query(Student.admission_year).filter(
        Student.college_id == college_id,
        Student.admission_year.isnot(None),
    ).distinct().order_by(Student.admission_year.desc()).all()
    adm_years = [r[0] for r in adm_years_raw]

    return render_template('admin/semester_schedules.html',
                           schedules=schedules,
                           departments=departments,
                           report_cfg=report_cfg,
                           adm_years=adm_years,
                           days_of_week=DAYS_OF_WEEK,
                           now=datetime.now())


@admin_bp.route('/semester-schedules/save', methods=['POST'])
@login_required
@admin_required
def save_semester_schedule():
    from models.academic_calendar import SemesterSchedule
    from datetime import date as _date
    college_id   = _admin_college_id()
    dept_id      = request.form.get('department_id', type=int) or None
    semester     = request.form.get('semester', type=int)
    acad_year    = request.form.get('academic_year', type=int)
    start_str    = request.form.get('start_date', '').strip()
    end_str      = request.form.get('end_date', '').strip()

    if not all([semester, acad_year, start_str, end_str]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('admin.semester_schedules'))

    try:
        start_date = _date.fromisoformat(start_str)
        end_date   = _date.fromisoformat(end_str)
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('admin.semester_schedules'))

    if end_date < start_date:
        flash('End date must be after start date.', 'danger')
        return redirect(url_for('admin.semester_schedules'))

    existing = SemesterSchedule.query.filter_by(
        college_id=college_id, department_id=dept_id,
        semester=semester, academic_year=acad_year,
    ).first()

    if existing:
        existing.start_date = start_date
        existing.end_date   = end_date
        flash('Semester schedule updated.', 'success')
    else:
        db.session.add(SemesterSchedule(
            college_id=college_id, department_id=dept_id,
            semester=semester, academic_year=acad_year,
            start_date=start_date, end_date=end_date,
            created_by=current_user.id,
        ))
        flash('Semester schedule added.', 'success')

    db.session.commit()
    return redirect(url_for('admin.semester_schedules'))


@admin_bp.route('/semester-schedules/<int:sid>/delete', methods=['POST'])
@login_required
@admin_required
def delete_semester_schedule(sid):
    from models.academic_calendar import SemesterSchedule
    schedule = SemesterSchedule.query.filter_by(
        id=sid, college_id=_admin_college_id()).first_or_404()
    db.session.delete(schedule)
    db.session.commit()
    flash('Semester schedule removed.', 'info')
    return redirect(url_for('admin.semester_schedules'))


# ---------------------------------------------------------------------------
# Sub-admin management (strict admin only)
# ---------------------------------------------------------------------------

@admin_bp.route('/sub-admins')
@login_required
@strict_admin_required
def sub_admins():
    from models.sub_admin import SubAdminPermission
    cid = _admin_college_id()
    sub_admin_users = User.query.filter_by(college_id=cid, role='sub_admin', is_active=True).all()
    perm_map: dict[int, dict[str, object]] = {}
    for u in sub_admin_users:
        perms = SubAdminPermission.query.filter_by(user_id=u.id, college_id=cid).all()
        perm_map[u.id] = {p.module: p for p in perms}
    return render_template(
        'admin/sub_admins.html',
        sub_admin_users=sub_admin_users,
        perm_map=perm_map,
        modules=SUBADMIN_MODULES,
    )


@admin_bp.route('/sub-admins/add', methods=['POST'])
@login_required
@strict_admin_required
def add_sub_admin():
    from models.sub_admin import SubAdminPermission
    cid = _admin_college_id()
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    temp_password = request.form.get('temp_password', '').strip()

    if not name or not email or not temp_password:
        flash('Name, email, and temporary password are required.', 'danger')
        return redirect(url_for('admin.people_hub', tab='sub_admins'))

    if not _validate_temporary_password(temp_password):
        flash('Temporary password must be at least 8 characters with uppercase, lowercase, digit, and special character.', 'danger')
        return redirect(url_for('admin.people_hub', tab='sub_admins'))

    if User.query.filter_by(college_id=cid, email=email).first():
        flash('A user with that email already exists in this college.', 'danger')
        return redirect(url_for('admin.people_hub', tab='sub_admins'))

    user = User(
        college_id=cid,
        name=name,
        email=email,
        role='sub_admin',
        is_active=True,
    )
    user.set_temporary_password(temp_password)
    db.session.add(user)
    db.session.flush()

    for module in SUBADMIN_MODULES:
        can_view = request.form.get(f'perm_{module}_view') == '1'
        can_edit = request.form.get(f'perm_{module}_edit') == '1'
        can_delete = request.form.get(f'perm_{module}_delete') == '1'
        if can_view or can_edit or can_delete:
            db.session.add(SubAdminPermission(
                college_id=cid,
                user_id=user.id,
                module=module,
                can_view=can_view,
                can_edit=can_edit,
                can_delete=can_delete,
            ))

    db.session.commit()
    flash(f'Sub-admin {name} created successfully.', 'success')
    return redirect(url_for('admin.people_hub', tab='sub_admins'))


@admin_bp.route('/sub-admins/<int:uid>/edit', methods=['POST'])
@login_required
@strict_admin_required
def edit_sub_admin(uid):
    from models.sub_admin import SubAdminPermission
    cid = _admin_college_id()
    user = User.query.filter_by(id=uid, college_id=cid, role='sub_admin').first_or_404()

    name = request.form.get('name', '').strip()
    if name:
        user.name = name

    for module in SUBADMIN_MODULES:
        can_view = request.form.get(f'perm_{module}_view') == '1'
        can_edit = request.form.get(f'perm_{module}_edit') == '1'
        can_delete = request.form.get(f'perm_{module}_delete') == '1'

        perm = SubAdminPermission.query.filter_by(
            college_id=cid, user_id=user.id, module=module).first()

        if can_view or can_edit or can_delete:
            if perm is None:
                perm = SubAdminPermission(college_id=cid, user_id=user.id, module=module)
                db.session.add(perm)
            perm.can_view = can_view
            perm.can_edit = can_edit
            perm.can_delete = can_delete
        elif perm is not None:
            db.session.delete(perm)

    db.session.commit()
    flash(f'Permissions updated for {user.name}.', 'success')
    return redirect(url_for('admin.people_hub', tab='sub_admins'))


@admin_bp.route('/sub-admins/<int:uid>/delete', methods=['POST'])
@login_required
@strict_admin_required
def delete_sub_admin(uid):
    from models.sub_admin import SubAdminPermission
    cid = _admin_college_id()
    user = User.query.filter_by(id=uid, college_id=cid, role='sub_admin').first_or_404()
    SubAdminPermission.query.filter_by(user_id=user.id, college_id=cid).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f'Sub-admin {user.name} removed.', 'info')
    return redirect(url_for('admin.people_hub', tab='sub_admins'))


# ── Hub: People ──────────────────────────────────────────────────────────────

@admin_bp.route('/people')
@login_required
@admin_required
def people_hub():
    from models.sub_admin import SubAdminPermission
    tab = request.args.get('tab', 'students')
    ctx: dict = {'active_tab': tab}

    if tab == 'students':
        page     = request.args.get('page', 1, type=int)
        dept_id  = request.args.get('department_id', type=int)
        semester = request.args.get('semester', type=int)
        adm_year = request.args.get('admission_year', type=int)
        search   = request.args.get('q', '').strip()
        query = Student.query.join(User).filter(Student.college_id == _admin_college_id())
        if dept_id:
            query = query.filter(Student.department_id == dept_id)
        if semester:
            query = query.filter(Student.semester == semester)
        if adm_year:
            query = query.filter(Student.admission_year == adm_year)
        if search:
            query = query.filter(
                db.or_(User.name.ilike(f'%{search}%'),
                       Student.roll_number.ilike(f'%{search}%'))
            )
        pagination = query.order_by(Student.roll_number).paginate(page=page, per_page=15, error_out=False)
        departments = _scoped_department_query().order_by(Department.name).all()
        current_year = datetime.now().year
        adm_years = [
            r[0] for r in
            db.session.query(Student.admission_year)
            .filter(Student.college_id == _admin_college_id(), Student.admission_year.isnot(None))
            .distinct().order_by(Student.admission_year.desc()).all()
        ]
        students_with_status = [(s, *_student_track_status(s, current_year)) for s in pagination.items]
        ctx.update(pagination=pagination, students_with_status=students_with_status,
                   departments=departments, adm_years=adm_years,
                   selected_dept=dept_id, selected_sem=semester,
                   selected_adm_year=adm_year, search=search, now=datetime.now())

    elif tab == 'teachers':
        page    = request.args.get('page', 1, type=int)
        dept_id = request.args.get('department_id', type=int)
        search  = request.args.get('q', '').strip()
        query = Teacher.query.join(User).filter(Teacher.college_id == _admin_college_id())
        if dept_id:
            query = query.filter(Teacher.department_id == dept_id)
        if search:
            query = query.filter(
                db.or_(User.name.ilike(f'%{search}%'),
                       Teacher.employee_id.ilike(f'%{search}%'))
            )
        pagination = query.order_by(Teacher.employee_id).paginate(page=page, per_page=15, error_out=False)
        departments = _scoped_department_query().order_by(Department.name).all()
        ctx.update(pagination=pagination, teachers=pagination.items,
                   departments=departments, selected_dept=dept_id, search=search)

    elif tab == 'departments':
        ctx['departments_list'] = _scoped_department_query().order_by(Department.name).all()

    elif tab == 'parents':
        parents_list = _scoped_user_query().filter_by(role='parent', is_active=True).all()
        all_students = _scoped_student_query().order_by(Student.roll_number).all()
        links = (ParentStudent.query
                 .join(Student, ParentStudent.student_id == Student.id)
                 .filter(Student.college_id == _admin_college_id()).all())
        parent_children = {}
        for link in links:
            parent_children.setdefault(link.parent_id, []).append(link)
        ctx.update(parents_list=parents_list, students=all_students, parent_children=parent_children)

    elif tab == 'sub_admins':
        cid = _admin_college_id()
        sub_admin_users = User.query.filter_by(college_id=cid, role='sub_admin', is_active=True).all()
        perm_map: dict = {}
        for u in sub_admin_users:
            perms = SubAdminPermission.query.filter_by(user_id=u.id, college_id=cid).all()
            perm_map[u.id] = {p.module: p for p in perms}
        ctx.update(sub_admin_users=sub_admin_users, perm_map=perm_map, modules=SUBADMIN_MODULES)

    template_map = {
        'students': 'admin/students.html',
        'teachers': 'admin/teachers.html',
        'departments': 'admin/departments.html',
        'parents': 'admin/parents.html',
        'sub_admins': 'admin/sub_admins.html',
    }
    return render_template(template_map.get(tab, 'admin/students.html'), **ctx)


# ── Hub: Academics ────────────────────────────────────────────────────────────

@admin_bp.route('/academics')
@login_required
@admin_required
def academics_hub():
    tab = request.args.get('tab', 'subjects')
    ctx: dict = {'active_tab': tab}

    if tab == 'subjects':
        selected_dept = request.args.get('department_id', type=int)
        selected_sem  = request.args.get('semester', type=int)
        query = _scoped_subject_query()
        if selected_dept:
            query = query.filter_by(department_id=selected_dept)
        if selected_sem:
            query = query.filter_by(semester=selected_sem)
        all_subjects = query.order_by(Subject.department_id, Subject.semester, Subject.name).all()
        departments = _scoped_department_query().order_by(Department.name).all()
        teachers = Teacher.query.join(User).filter(Teacher.college_id == _admin_college_id()).order_by(User.name).all()
        ctx.update(subjects=all_subjects, departments=departments, teachers=teachers,
                   selected_dept=selected_dept, selected_sem=selected_sem)

    elif tab == 'exams':
        from models.exam import Exam
        cid = _admin_college_id()
        dept_id    = request.args.get('department_id', type=int)
        subject_id = request.args.get('subject_id', type=int)
        page       = request.args.get('page', 1, type=int)
        departments = _scoped_department_query().order_by(Department.name).all()
        subjects    = _scoped_subject_query().order_by(Subject.name).all()
        query = Exam.query.filter_by(college_id=cid, is_deleted=False)
        if subject_id:
            query = query.filter_by(subject_id=subject_id)
        elif dept_id:
            sub_ids = [s.id for s in Subject.query.filter_by(college_id=cid, department_id=dept_id).all()]
            query = query.filter(Exam.subject_id.in_(sub_ids))
        pagination = query.order_by(Exam.exam_date.desc()).paginate(page=page, per_page=20, error_out=False)
        ctx.update(pagination=pagination, exams=pagination.items, departments=departments,
                   subjects=subjects, selected_dept=dept_id, selected_subject=subject_id)

    elif tab == 'marksheets':
        q       = request.args.get('q', '').strip()
        dept_id = request.args.get('dept_id', type=int)
        sem     = request.args.get('sem', type=int)
        query = Student.query.join(User, Student.user_id == User.id).filter(Student.college_id == _admin_college_id())
        if q:
            query = query.filter(db.or_(User.name.ilike(f'%{q}%'), Student.roll_number.ilike(f'%{q}%')))
        if dept_id:
            query = query.filter(Student.department_id == dept_id)
        if sem:
            query = query.filter(Student.semester == sem)
        students    = query.order_by(Student.roll_number).all()
        departments = _scoped_department_query().order_by(Department.name).all()
        semesters   = sorted({s.semester for s in _scoped_student_query().all()})
        ctx.update(students=students, departments=departments, semesters=semesters, q=q,
                   dept_id=dept_id, sem=sem)

    elif tab == 'signatures':
        from models.marksheet_signature import MarksheetSignature
        departments = _scoped_department_query().order_by(Department.name).all()
        principal   = MarksheetSignature.query.filter_by(college_id=_admin_college_id(), role='principal').first()
        hod_map     = {s.department_id: s for s in
                       MarksheetSignature.query.filter_by(college_id=_admin_college_id(), role='hod').all()}
        ctx.update(departments=departments, principal=principal, hod_map=hod_map)

    if tab == 'exams':
        return redirect(url_for('exam.admin_exams'))

    template_map = {
        'subjects': 'admin/subjects.html',
        'marksheets': 'admin/marksheets.html',
        'signatures': 'admin/marksheet_signatures.html',
    }
    return render_template(template_map.get(tab, 'admin/subjects.html'), **ctx)


# ── Hub: Attendance ───────────────────────────────────────────────────────────

@admin_bp.route('/attendance-hub')
@login_required
@admin_required
def attendance_hub():
    tab = request.args.get('tab', 'sessions')
    ctx: dict = {'active_tab': tab}

    if tab == 'sessions':
        subject_id    = request.args.get('subject_id', type=int)
        status_filter = request.args.get('status', '')
        date_from     = request.args.get('date_from', '')
        date_to       = request.args.get('date_to', '')
        page          = request.args.get('page', 1, type=int)
        query = AttendanceSession.query.join(Subject).filter(Subject.college_id == _admin_college_id())
        if subject_id:
            query = query.filter(AttendanceSession.subject_id == subject_id)
        if status_filter:
            query = query.filter(AttendanceSession.status == status_filter)
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
        pagination = query.order_by(AttendanceSession.date.desc(), AttendanceSession.start_time.desc()).paginate(page=page, per_page=15, error_out=False)
        subjects = _scoped_subject_query().all()
        ctx.update(pagination=pagination, sessions=pagination.items, subjects=subjects,
                   selected_subject_id=subject_id, selected_status=status_filter,
                   date_from=date_from, date_to=date_to)

    elif tab == 'analytics':
        total_records = AttendanceRecord.query.join(AttendanceSession).join(Subject).filter(
            Subject.college_id == _admin_college_id(), AttendanceSession.status == 'completed').count()
        present_records = AttendanceRecord.query.join(AttendanceSession).join(Subject).filter(
            Subject.college_id == _admin_college_id(), AttendanceSession.status == 'completed',
            AttendanceRecord.status == 'present').count()
        overall_rate = round(present_records / total_records * 100, 1) if total_records > 0 else 0
        threshold = 75
        low_attendance_students = []
        for student in _scoped_student_query().all():
            pct = student.get_attendance_percentage()
            if pct < threshold:
                low_attendance_students.append({
                    'name': student.user.name, 'roll': student.roll_number,
                    'dept': student.department.name, 'percentage': pct,
                })
        low_attendance_students.sort(key=lambda x: x['percentage'])
        monthly = []
        for i in range(5, -1, -1):
            month_start = date.today().replace(day=1) - timedelta(days=i * 30)
            month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            sessions = AttendanceSession.query.join(Subject).filter(
                Subject.college_id == _admin_college_id(),
                AttendanceSession.date >= month_start,
                AttendanceSession.date < month_end,
                AttendanceSession.status == 'completed').all()
            total = sum(s.total_students for s in sessions)
            present = sum(s.present_count for s in sessions)
            monthly.append({'month': month_start.strftime('%b %Y'),
                            'rate': round(present / total * 100, 1) if total > 0 else 0})
        ctx.update(overall_rate=overall_rate, total_records=total_records,
                   low_attendance_students=low_attendance_students, monthly=monthly)

    elif tab == 'batch_tracker':
        college_id   = _admin_college_id()
        current_year = datetime.now().year
        dept_filter  = request.args.get('department_id', type=int)
        year_filter  = request.args.get('admission_year', type=int)
        base_q = Student.query.join(User).filter(Student.college_id == college_id)
        if dept_filter:
            base_q = base_q.filter(Student.department_id == dept_filter)
        if year_filter:
            base_q = base_q.filter(Student.admission_year == year_filter)
        all_students = base_q.order_by(Student.admission_year, Student.department_id, Student.roll_number).all()
        departments  = _scoped_department_query().order_by(Department.name).all()
        dept_map     = {d.id: d for d in departments}
        adm_years = [
            r[0] for r in
            db.session.query(Student.admission_year)
            .filter(Student.college_id == college_id, Student.admission_year.isnot(None))
            .distinct().order_by(Student.admission_year.desc()).all()
        ]
        from collections import defaultdict
        groups: dict = defaultdict(list)
        for s in all_students:
            key = (s.admission_year or 0, s.department_id)
            groups[key].append(s)
        batches = []
        for (adm_year, dept_id), sts in sorted(groups.items(), key=lambda x: (-x[0][0], x[0][1])):
            dept = dept_map.get(dept_id)
            years_elapsed = max(0, current_year - adm_year) if adm_year else 0
            expected_sem  = min(years_elapsed * 2 + 1, 8) if adm_year else None
            counts = {'on_track': 0, 'behind': 0, 'far_behind': 0, 'unknown': 0}
            student_rows = []
            for s in sts:
                status, diff = _student_track_status(s, current_year)
                counts[status] += 1
                student_rows.append({'student': s, 'status': status, 'diff': diff, 'expected_sem': expected_sem})
            batches.append({'adm_year': adm_year, 'dept': dept, 'dept_id': dept_id,
                            'expected_sem': expected_sem, 'total': len(sts), 'counts': counts,
                            'students': student_rows,
                            'year_label': f"Year {years_elapsed + 1}" if adm_year else 'Unknown'})
        ctx.update(batches=batches, departments=departments, adm_years=adm_years,
                   dept_filter=dept_filter, year_filter=year_filter, current_year=current_year)

    return render_template('admin/hub_attendance.html', **ctx)


# ── My Plan ───────────────────────────────────────────────────────────────────

@admin_bp.route('/my-plan')
@login_required
@admin_required
def my_plan():
    from models.college import COLLEGE_PLANS
    from utils.feature_access import FEATURE_CATALOG, FEATURE_PRESETS, college_feature_matrix

    college = current_user.college
    plan_key = college.plan or 'free'
    plan_meta = COLLEGE_PLANS.get(plan_key, COLLEGE_PLANS['free'])

    # What features are actually enabled for this college
    feature_matrix = college_feature_matrix(college.id)
    enabled_features = [k for k, v in feature_matrix.items() if v]
    disabled_features = [k for k, v in feature_matrix.items() if not v]

    # Days until expiry
    days_left = None
    if college.plan_expires_at:
        from utils.time import utc_now_naive
        delta = college.plan_expires_at - utc_now_naive()
        days_left = delta.days

    support_email = current_app.config.get('SUPPORT_EMAIL', 'support@smartattend.com')
    support_phone = current_app.config.get('SUPPORT_PHONE', '')

    return render_template(
        'admin/my_plan.html',
        college=college,
        plan_key=plan_key,
        plan_meta=plan_meta,
        all_plans=COLLEGE_PLANS,
        feature_catalog=FEATURE_CATALOG,
        feature_presets=FEATURE_PRESETS,
        enabled_features=enabled_features,
        disabled_features=disabled_features,
        days_left=days_left,
        support_email=support_email,
        support_phone=support_phone,
    )
