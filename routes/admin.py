from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, current_app
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
from utils.decorators import admin_required
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func
from datetime import datetime, date, timedelta
import csv, io, os
from utils.content_storage import is_valid_content_relpath, resolve_content_path
from utils.time import utc_now_naive

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    stats = {
        'total_students': Student.query.count(),
        'total_teachers': Teacher.query.count(),
        'total_subjects': Subject.query.count(),
        'total_sessions': AttendanceSession.query.count(),
        'active_sessions': AttendanceSession.query.filter_by(status='active').count(),
        'departments': Department.query.count(),
    }

    # Last 7 days attendance trend
    trend = []
    for i in range(6, -1, -1):
        day = date.today() - timedelta(days=i)
        sessions = AttendanceSession.query.filter_by(date=day, status='completed').all()
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
    for dept in Department.query.all():
        students = Student.query.filter_by(department_id=dept.id).all()
        if not students:
            continue
        rates = [s.get_attendance_percentage() for s in students]
        dept_stats.append({
            'name': dept.name,
            'code': dept.code,
            'avg_rate': round(sum(rates) / len(rates), 1) if rates else 0,
            'student_count': len(students),
        })

    recent_sessions = AttendanceSession.query.order_by(
        AttendanceSession.created_at.desc()
    ).limit(10).all()

    # Recent notices (pinned first)
    recent_notices = Notice.query.filter(
        db.or_(Notice.expires_at == None, Notice.expires_at > utc_now_naive())
    ).order_by(Notice.is_pinned.desc(), Notice.created_at.desc()).limit(5).all()

    # Upcoming exams (next 7 days)
    today = date.today()
    upcoming_exams = Exam.query.filter(
        Exam.exam_date >= today,
        Exam.exam_date <= today + timedelta(days=7)
    ).order_by(Exam.exam_date).limit(5).all()

    # Fee collection summary
    total_fee_expected = db.session.query(func.sum(FeeStructure.amount)).scalar() or 0
    total_fee_collected = db.session.query(func.sum(FeePayment.amount_paid)).filter(
        FeePayment.status.in_(['paid', 'partial'])
    ).scalar() or 0
    from models.leave import LeaveRequest
    pending_leaves = LeaveRequest.query.filter_by(status='pending').count()

    return render_template('admin/dashboard.html',
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

    query = User.query
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
    user = User.query.get_or_404(uid)
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
    user = User.query.get_or_404(uid)
    new_pw = request.form.get('new_password', '').strip()
    if len(new_pw) < 6:
        flash('Password must be at least 6 characters.', 'danger')
    else:
        user.set_password(new_pw)
        db.session.commit()
        flash(f"Password reset for {user.name}.", 'success')
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
        elif Department.query.filter_by(code=code).first():
            flash('Department code already exists.', 'danger')
        else:
            db.session.add(Department(name=name, code=code))
            db.session.commit()
            flash(f'Department {code} added.', 'success')
    return render_template('admin/departments.html',
                           departments=Department.query.all())


@admin_bp.route('/departments/edit/<int:did>', methods=['POST'])
@login_required
@admin_required
def edit_department(did):
    dept = Department.query.get_or_404(did)
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip().upper()
    if not name or not code:
        flash('Name and code are required.', 'danger')
        return redirect(url_for('admin.departments'))
    if code != dept.code and Department.query.filter_by(code=code).first():
        flash('Department code already exists.', 'danger')
        return redirect(url_for('admin.departments'))
    dept.name = name
    dept.code = code
    db.session.commit()
    flash(f'Department {code} updated.', 'success')
    return redirect(url_for('admin.departments'))


@admin_bp.route('/departments/delete/<int:did>', methods=['POST'])
@login_required
@admin_required
def delete_department(did):
    dept = Department.query.get_or_404(did)
    db.session.delete(dept)
    db.session.commit()
    flash('Department deleted.', 'success')
    return redirect(url_for('admin.departments'))


# ─── Students ────────────────────────────────────────────────────────────────

@admin_bp.route('/students')
@login_required
@admin_required
def students():
    page       = request.args.get('page', 1, type=int)
    dept_id    = request.args.get('department_id', type=int)
    semester   = request.args.get('semester', type=int)
    search     = request.args.get('q', '').strip()

    query = Student.query.join(User)
    if dept_id:
        query = query.filter(Student.department_id == dept_id)
    if semester:
        query = query.filter(Student.semester == semester)
    if search:
        query = query.filter(
            db.or_(User.name.ilike(f'%{search}%'),
                   Student.roll_number.ilike(f'%{search}%'))
        )

    pagination = query.order_by(Student.roll_number).paginate(
        page=page, per_page=15, error_out=False
    )
    departments = Department.query.order_by(Department.name).all()
    return render_template('admin/students.html',
                           pagination=pagination,
                           students=pagination.items,
                           departments=departments,
                           selected_dept=dept_id,
                           selected_sem=semester,
                           search=search)


@admin_bp.route('/students/add', methods=['POST'])
@login_required
@admin_required
def add_student():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    roll = request.form.get('roll_number', '').strip().upper()
    dept_id = request.form.get('department_id', type=int)
    semester = request.form.get('semester', type=int)

    if not all([name, email, password, roll, dept_id, semester]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('admin.students'))

    if User.query.filter_by(email=email).first():
        flash('Email already registered.', 'danger')
        return redirect(url_for('admin.students'))

    if Student.query.filter_by(roll_number=roll).first():
        flash('Roll number already exists.', 'danger')
        return redirect(url_for('admin.students'))

    user = User(name=name, email=email, role='student')
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    student = Student(user_id=user.id, roll_number=roll,
                      department_id=dept_id, semester=semester)
    db.session.add(student)
    db.session.commit()
    flash(f'Student {roll} added successfully.', 'success')
    return redirect(url_for('admin.students'))


@admin_bp.route('/students/edit/<int:sid>', methods=['POST'])
@login_required
@admin_required
def edit_student(sid):
    student = Student.query.get_or_404(sid)
    student.user.name  = request.form.get('name', student.user.name).strip()
    student.semester   = request.form.get('semester', student.semester, type=int)
    dept_id = request.form.get('department_id', type=int)
    if dept_id:
        student.department_id = dept_id
    new_email = request.form.get('email', '').strip().lower()
    if new_email and new_email != student.user.email:
        if User.query.filter(User.email == new_email, User.id != student.user_id).first():
            flash('Email already in use.', 'danger')
            return redirect(url_for('admin.students'))
        student.user.email = new_email
    db.session.commit()
    flash(f'Student {student.roll_number} updated.', 'success')
    return redirect(url_for('admin.students'))


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
        return redirect(url_for('admin.students'))

    stream = io.StringIO(f.stream.read().decode('utf-8-sig'))
    reader = csv.DictReader(stream)
    added = skipped = errors = 0

    for row in reader:
        try:
            name     = row.get('name', '').strip()
            email    = row.get('email', '').strip().lower()
            roll     = row.get('roll_number', '').strip().upper()
            dept_code= row.get('department_code', '').strip().upper()
            semester = int(row.get('semester', 1))
            password = row.get('password', 'Student@123').strip()

            if not all([name, email, roll, dept_code]):
                errors += 1
                continue

            if User.query.filter_by(email=email).first() or \
               Student.query.filter_by(roll_number=roll).first():
                skipped += 1
                continue

            dept = Department.query.filter_by(code=dept_code).first()
            if not dept:
                errors += 1
                continue

            u = User(name=name, email=email, role='student')
            u.set_password(password)
            db.session.add(u)
            db.session.flush()
            db.session.add(Student(user_id=u.id, roll_number=roll,
                                   department_id=dept.id, semester=semester))
            added += 1
        except Exception:
            errors += 1

    db.session.commit()
    flash(f'Import complete: {added} added, {skipped} skipped (duplicates), {errors} errors.', 'info')
    return redirect(url_for('admin.students'))


@admin_bp.route('/students/export')
@login_required
@admin_required
def export_students():
    students = Student.query.join(User).order_by(Student.roll_number).all()
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
    student = Student.query.get_or_404(sid)
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
    student = Student.query.get_or_404(sid)
    db.session.delete(student.user)
    db.session.commit()
    flash('Student removed.', 'success')
    return redirect(url_for('admin.students'))


# ─── Teachers ────────────────────────────────────────────────────────────────

@admin_bp.route('/teachers')
@login_required
@admin_required
def teachers():
    page    = request.args.get('page', 1, type=int)
    dept_id = request.args.get('department_id', type=int)
    search  = request.args.get('q', '').strip()

    query = Teacher.query.join(User)
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
    departments = Department.query.order_by(Department.name).all()
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
        return redirect(url_for('admin.teachers'))

    if User.query.filter_by(email=email).first():
        flash('Email already registered.', 'danger')
        return redirect(url_for('admin.teachers'))

    if Teacher.query.filter_by(employee_id=emp_id).first():
        flash('Employee ID already exists.', 'danger')
        return redirect(url_for('admin.teachers'))

    user = User(name=name, email=email, role='teacher')
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    teacher = Teacher(user_id=user.id, employee_id=emp_id, department_id=dept_id)
    db.session.add(teacher)
    db.session.commit()
    flash(f'Teacher {emp_id} added.', 'success')
    return redirect(url_for('admin.teachers'))


@admin_bp.route('/teachers/edit/<int:tid>', methods=['POST'])
@login_required
@admin_required
def edit_teacher(tid):
    teacher = Teacher.query.get_or_404(tid)
    teacher.user.name = request.form.get('name', teacher.user.name).strip()
    dept_id = request.form.get('department_id', type=int)
    if dept_id:
        teacher.department_id = dept_id
    new_email = request.form.get('email', '').strip().lower()
    if new_email and new_email != teacher.user.email:
        if User.query.filter(User.email == new_email, User.id != teacher.user_id).first():
            flash('Email already in use.', 'danger')
            return redirect(url_for('admin.teachers'))
        teacher.user.email = new_email
    db.session.commit()
    flash(f'Teacher {teacher.employee_id} updated.', 'success')
    return redirect(url_for('admin.teachers'))


@admin_bp.route('/teachers/delete/<int:tid>', methods=['POST'])
@login_required
@admin_required
def delete_teacher(tid):
    teacher = Teacher.query.get_or_404(tid)
    db.session.delete(teacher.user)
    db.session.commit()
    flash('Teacher removed.', 'success')
    return redirect(url_for('admin.teachers'))


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

        if Subject.query.filter_by(code=code).first():
            flash('Subject code already exists.', 'danger')
        else:
            db.session.add(Subject(name=name, code=code, department_id=dept_id,
                                   teacher_id=teacher_id, semester=semester,
                                   credit_hours=credits))
            db.session.commit()
            flash(f'Subject {code} added.', 'success')
        return redirect(url_for('admin.subjects',
                                department_id=request.form.get('department_id'),
                                semester=request.form.get('semester')))

    selected_dept = request.args.get('department_id', type=int)
    selected_sem  = request.args.get('semester', type=int)

    query = Subject.query
    if selected_dept:
        query = query.filter_by(department_id=selected_dept)
    if selected_sem:
        query = query.filter_by(semester=selected_sem)
    all_subjects = query.order_by(Subject.department_id, Subject.semester, Subject.name).all()

    departments = Department.query.order_by(Department.name).all()
    teachers = Teacher.query.join(User).order_by(User.name).all()
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
    subject = Subject.query.get_or_404(sid)
    subject.name = request.form.get('name', subject.name).strip()
    new_code = request.form.get('code', '').strip().upper()
    if new_code and new_code != subject.code:
        if Subject.query.filter(Subject.code == new_code, Subject.id != sid).first():
            flash('Subject code already in use.', 'danger')
            return redirect(url_for('admin.subjects'))
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
    return redirect(url_for('admin.subjects'))


@admin_bp.route('/subjects/delete/<int:sid>', methods=['POST'])
@login_required
@admin_required
def delete_subject(sid):
    subject = Subject.query.get_or_404(sid)
    db.session.delete(subject)
    db.session.commit()
    flash('Subject deleted.', 'success')
    return redirect(url_for('admin.subjects'))


# ─── Session Management ──────────────────────────────────────────────────────

@admin_bp.route('/sessions')
@login_required
@admin_required
def sessions():
    subject_id = request.args.get('subject_id', type=int)
    status_filter = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to   = request.args.get('date_to', '')

    query = AttendanceSession.query
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
    subjects = Subject.query.all()
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
    session = AttendanceSession.query.get_or_404(sid)
    if session.status != 'active':
        flash('Only active sessions can be cancelled.', 'warning')
    else:
        session.status = 'cancelled'
        session.end_time = utc_now_naive().time()
        db.session.commit()
        flash('Session cancelled.', 'info')
    return redirect(url_for('admin.sessions'))


# ─── Analytics ───────────────────────────────────────────────────────────────

@admin_bp.route('/analytics')
@login_required
@admin_required
def analytics():
    departments = Department.query.all()
    subjects = Subject.query.all()

    # Overall stats
    total_records = AttendanceRecord.query.join(AttendanceSession).filter(
        AttendanceSession.status == 'completed'
    ).count()
    present_records = AttendanceRecord.query.join(AttendanceSession).filter(
        AttendanceSession.status == 'completed',
        AttendanceRecord.status == 'present'
    ).count()
    overall_rate = round(present_records / total_records * 100, 1) if total_records > 0 else 0

    # Students below threshold
    threshold = 75
    low_attendance_students = []
    for student in Student.query.all():
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
        sessions = AttendanceSession.query.filter(
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
    parents_list = User.query.filter_by(role='parent', is_active=True).all()
    students = Student.query.order_by(Student.roll_number).all()
    links = ParentStudent.query.all()
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
        return redirect(url_for('admin.parents'))

    if User.query.filter_by(email=email).first():
        flash(f'Email {email} is already registered.', 'danger')
        return redirect(url_for('admin.parents'))

    student = db.session.get(Student, student_id)
    if not student:
        flash('Student not found.', 'danger')
        return redirect(url_for('admin.parents'))

    user = User(name=name, email=email, role='parent', is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    link = ParentStudent(parent_id=user.id, student_id=student_id,
                         relationship=relationship)
    db.session.add(link)
    db.session.commit()
    flash(f'Parent {name} created and linked to {student.user.name}.', 'success')
    return redirect(url_for('admin.parents'))


@admin_bp.route('/parents/<int:parent_id>/link', methods=['POST'])
@login_required
@admin_required
def link_parent_child(parent_id):
    parent_user = User.query.filter_by(id=parent_id, role='parent').first_or_404()
    student_id = request.form.get('student_id', type=int)
    relationship = request.form.get('relationship', 'guardian')

    if not student_id:
        flash('Select a student to link.', 'danger')
        return redirect(url_for('admin.parents'))

    if ParentStudent.query.filter_by(parent_id=parent_id,
                                      student_id=student_id).first():
        flash('This child is already linked to this parent.', 'warning')
        return redirect(url_for('admin.parents'))

    student = db.session.get(Student, student_id)
    if not student:
        flash('Student not found.', 'danger')
        return redirect(url_for('admin.parents'))

    db.session.add(ParentStudent(parent_id=parent_id, student_id=student_id,
                                  relationship=relationship))
    db.session.commit()
    flash(f'Linked {student.user.name} to {parent_user.name}.', 'success')
    return redirect(url_for('admin.parents'))


@admin_bp.route('/parents/unlink/<int:link_id>', methods=['POST'])
@login_required
@admin_required
def unlink_parent_child(link_id):
    link = ParentStudent.query.get_or_404(link_id)
    child_name = link.student.user.name
    db.session.delete(link)
    db.session.commit()
    flash(f'Unlinked {child_name} from parent.', 'success')
    return redirect(url_for('admin.parents'))


@admin_bp.route('/parents/delete/<int:parent_id>', methods=['POST'])
@login_required
@admin_required
def delete_parent(parent_id):
    user = User.query.filter_by(id=parent_id, role='parent').first_or_404()
    ParentStudent.query.filter_by(parent_id=parent_id).delete()
    db.session.delete(user)
    db.session.commit()
    flash('Parent account deleted.', 'success')
    return redirect(url_for('admin.parents'))


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

    slots = TimetableSlot.query.filter_by(
        day_of_week=today_dow, slot_type='class'
    ).all()

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
        db.session.add(ClassAlert(slot_id=slot.id, alert_date=today,
                                   recipient_count=sent, triggered_by='manual'))
        db.session.commit()
        total_sent += sent

    flash(f'Class alerts sent: {total_sent} notifications dispatched.', 'success')
    return redirect(url_for('admin.parents'))


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


def _save_template_file(file_obj, filename):
    path = os.path.join(_id_template_dir(), secure_filename(filename))
    file_obj.save(path)
    return 'uploads/id_templates/' + secure_filename(filename)


@admin_bp.route('/id-card-template', methods=['GET', 'POST'])
@login_required
@admin_required
def id_card_template():
    tpl = IDCardTemplate.get()
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
            tpl.logo_path = _save_template_file(logo, 'logo.png')

        sig = request.files.get('principal_signature')
        if sig and sig.filename:
            tpl.principal_signature_path = _save_template_file(sig, 'signature.png')

        college_img = request.files.get('college_image')
        if college_img and college_img.filename:
            tpl.college_image_path = _save_template_file(college_img, 'college_image.jpg')

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
    departments = Department.query.order_by(Department.name).all()
    tpl         = IDCardTemplate.get()
    cs          = CollegeSetting.get()
    counts = {
        'all':      StudentIDCard.query.count(),
        'pending':  StudentIDCard.query.filter_by(status='pending').count(),
        'approved': StudentIDCard.query.filter_by(status='approved').count(),
        'rejected': StudentIDCard.query.filter_by(status='rejected').count(),
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
    card = StudentIDCard.query.get_or_404(cid)
    card.status      = 'approved'
    card.reviewed_at = utc_now_naive()
    card.reviewed_by = current_user.id
    card.rejection_note = None
    if not card.card_number:
        s = card.student
        card.card_number = f"{s.department.code}-{s.roll_number}"
    db.session.commit()
    flash(f'ID card approved for {card.student.user.name}.', 'success')
    return redirect(url_for('admin.id_cards', status='pending'))


@admin_bp.route('/id-cards/<int:cid>/reject', methods=['POST'])
@login_required
@admin_required
def reject_id_card(cid):
    card = StudentIDCard.query.get_or_404(cid)
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
    card    = StudentIDCard.query.get_or_404(cid)
    tpl     = IDCardTemplate.get()
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
    upload_dir = current_app.config['CONTENT_UPLOAD_FOLDER']
    os.makedirs(upload_dir, exist_ok=True)

    # Build a lookup: rel_path → content record
    all_content = TeacherContent.query.all()
    path_map    = {c.file_path: c for c in all_content if c.file_path}

    type_filter = request.args.get('type', '')
    q           = request.args.get('q', '').strip().lower()

    files = []
    for fname in sorted(os.listdir(upload_dir)):
        fpath = os.path.join(upload_dir, fname)
        if not os.path.isfile(fpath):
            continue
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
    TeacherContent.query.filter_by(file_path=rel).update({'file_path': None})

    # Remove physical file
    if os.path.isfile(abs_path):
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
        upload_dir  = current_app.config['CONTENT_UPLOAD_FOLDER']
        linked      = {c.file_path for c in TeacherContent.query.all() if c.file_path}
        rels = []
        for fname in os.listdir(upload_dir):
            rel = 'uploads/content/' + fname
            if rel not in linked:
                rels.append(rel)

    if not rels:
        flash('No files to delete.', 'warning')
        return redirect(url_for('admin.file_manager'))

    deleted = 0
    for rel in rels:
        if not is_valid_content_relpath(rel):
            continue
        abs_path = resolve_content_path(current_app, rel)
        TeacherContent.query.filter_by(file_path=rel).update({'file_path': None})
        if os.path.isfile(abs_path):
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


# ── Admin: marksheet management ───────────────────────────────────────────────

@admin_bp.route('/marksheets')
@login_required
@admin_required
def marksheet_list():
    q       = request.args.get('q', '').strip()
    dept_id = request.args.get('dept_id', type=int)
    sem     = request.args.get('sem', type=int)

    query = Student.query.join(User, Student.user_id == User.id)
    if q:
        query = query.filter(
            db.or_(User.name.ilike(f'%{q}%'), Student.roll_number.ilike(f'%{q}%'))
        )
    if dept_id:
        query = query.filter(Student.department_id == dept_id)
    if sem:
        query = query.filter(Student.semester == sem)

    students    = query.order_by(Student.roll_number).all()
    departments = Department.query.order_by(Department.name).all()
    semesters   = sorted({s.semester for s in Student.query.all()})

    return render_template('admin/marksheets.html',
                           students=students, departments=departments,
                           semesters=semesters, q=q,
                           dept_id=dept_id, sem=sem)


@admin_bp.route('/marksheet/<int:student_id>')
@login_required
@admin_required
def admin_marksheet(student_id):
    from routes.exam import build_marksheet_data
    student = Student.query.get_or_404(student_id)
    data    = build_marksheet_data(student)
    return render_template('exam/marksheet.html', **data, is_admin=True, is_parent=False)


# ── Admin: marksheet signature management ─────────────────────────────────────

@admin_bp.route('/marksheet-signatures')
@login_required
@admin_required
def marksheet_signatures():
    from models.marksheet_signature import MarksheetSignature

    departments = Department.query.order_by(Department.name).all()
    principal   = MarksheetSignature.query.filter_by(role='principal').first()
    hod_map   = {s.department_id: s for s in
                 MarksheetSignature.query.filter_by(role='hod').all()}

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
        return redirect(url_for('admin.marksheet_signatures'))

    if role == 'principal':
        dept_id = None
        if not name:
            flash('Name is required for Principal.', 'danger')
            return redirect(url_for('admin.marksheet_signatures'))
    elif role == 'hod':
        if not dept_id or not name:
            flash('Department and name are required for HoD.', 'danger')
            return redirect(url_for('admin.marksheet_signatures'))

    # Upsert
    sig = MarksheetSignature.query.filter_by(
        role=role, department_id=dept_id, semester=None
    ).first()
    if not sig:
        sig = MarksheetSignature(role=role, department_id=dept_id, semester=None)
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
    return redirect(url_for('admin.marksheet_signatures'))


@admin_bp.route('/marksheet-signatures/<int:sig_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_marksheet_signature(sig_id):
    from models.marksheet_signature import MarksheetSignature
    sig = MarksheetSignature.query.get_or_404(sig_id)

    if sig.sign_path:
        abs_path = os.path.join(current_app.static_folder, sig.sign_path)
        if os.path.isfile(abs_path):
            os.remove(abs_path)

    db.session.delete(sig)
    db.session.commit()
    flash('Signature removed.', 'info')
    return redirect(url_for('admin.marksheet_signatures'))
