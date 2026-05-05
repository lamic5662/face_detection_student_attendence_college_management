from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db, csrf
from models.timetable import TimetableSlot, DAYS
from models.department import Department
from models.subject import Subject
from models.teacher import Teacher
from models.user import User
from utils.decorators import admin_required
from utils.tenancy import current_college_id
from datetime import datetime

timetable_bp = Blueprint('timetable', __name__)


def _get_timetable_grid(dept_id, semester):
    slots = TimetableSlot.query.filter_by(
        college_id=current_college_id(), department_id=dept_id, semester=semester
    ).order_by(TimetableSlot.day_of_week, TimetableSlot.period_no).all()

    grid = {d: {} for d in range(7)}
    for s in slots:
        grid[s.day_of_week][s.period_no] = s

    max_period = max((s.period_no for s in slots), default=8)
    return grid, list(range(1, max_period + 1)), slots


@timetable_bp.route('/timetable')
@login_required
def view():
    departments = Department.query.filter_by(college_id=current_college_id()).order_by(Department.name).all()
    dept_id  = request.args.get('department_id', type=int)
    semester = request.args.get('semester', type=int)

    if current_user.role == 'student':
        dept_id  = current_user.student_profile.department_id
        semester = current_user.student_profile.semester
    elif current_user.role == 'teacher':
        dept_id  = request.args.get('department_id', type=int) or current_user.teacher_profile.department_id
        semester = request.args.get('semester', type=int)

    grid = periods = []
    slots = []
    if dept_id and semester:
        grid, periods, slots = _get_timetable_grid(dept_id, semester)

    return render_template('timetable/view.html',
                           departments=departments,
                           selected_dept=dept_id,
                           selected_sem=semester,
                           grid=grid, periods=periods,
                           days=DAYS, slots=slots)


@timetable_bp.route('/timetable/manage', methods=['GET', 'POST'])
@login_required
@admin_required
def manage():
    departments = Department.query.order_by(Department.name).all()
    dept_id  = request.args.get('department_id', type=int)
    semester = request.args.get('semester', type=int)

    subjects = []
    teachers = []
    grid = {}
    periods = []
    subject_teacher_map = {}  # subject_id -> teacher_id for auto-fill

    if dept_id and semester:
        subjects = Subject.query.filter_by(
            college_id=current_college_id(), department_id=dept_id, semester=semester
        ).order_by(Subject.name).all()
        teachers = (Teacher.query
                    .join(User)
                    .filter(Teacher.college_id == current_college_id(), Teacher.department_id == dept_id)
                    .order_by(User.name)
                    .all())
        subject_teacher_map = {s.id: s.teacher_id for s in subjects}
        grid, periods, _ = _get_timetable_grid(dept_id, semester)

    return render_template('timetable/manage.html',
                           departments=departments,
                           selected_dept=dept_id,
                           selected_sem=semester,
                           subjects=subjects,
                           teachers=teachers,
                           subject_teacher_map=subject_teacher_map,
                           grid=grid, periods=periods,
                           days=DAYS)


@timetable_bp.route('/timetable/slot/save', methods=['POST'])
@csrf.exempt
@login_required
@admin_required
def save_slot():
    data       = request.get_json()
    dept_id    = data.get('department_id')
    semester   = data.get('semester')
    day        = data.get('day_of_week')
    period     = data.get('period_no')
    subject_id = data.get('subject_id') or None
    teacher_id = data.get('teacher_id') or None
    room       = data.get('room', '').strip() or None
    slot_type  = data.get('slot_type', 'lecture')
    start_str  = data.get('start_time', '')
    end_str    = data.get('end_time', '')

    try:
        start = datetime.strptime(start_str, '%H:%M').time() if start_str else None
        end   = datetime.strptime(end_str,   '%H:%M').time() if end_str   else None
    except ValueError:
        return jsonify({'error': 'Invalid time format'}), 400

    slot = TimetableSlot.query.filter_by(
        college_id=current_college_id(), department_id=dept_id, semester=semester,
        day_of_week=day, period_no=period
    ).first()

    if slot:
        slot.subject_id = subject_id
        slot.teacher_id = teacher_id
        slot.room       = room
        slot.slot_type  = slot_type
        slot.start_time = start
        slot.end_time   = end
    else:
        slot = TimetableSlot(
            college_id=current_college_id(),
            department_id=dept_id, semester=semester,
            day_of_week=day, period_no=period,
            subject_id=subject_id, teacher_id=teacher_id,
            room=room, slot_type=slot_type,
            start_time=start, end_time=end
        )
        db.session.add(slot)

    db.session.commit()
    return jsonify({'success': True, 'slot_id': slot.id})


@timetable_bp.route('/timetable/slot/<int:sid>/delete', methods=['POST'])
@csrf.exempt
@login_required
@admin_required
def delete_slot(sid):
    slot = TimetableSlot.query.filter_by(id=sid, college_id=current_college_id()).first_or_404()
    db.session.delete(slot)
    db.session.commit()
    return jsonify({'success': True})
