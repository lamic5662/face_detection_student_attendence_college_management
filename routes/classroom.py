from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models.classroom import Classroom, ClassroomBooking
from models.department import Department
from utils.decorators import admin_required, strict_admin_required, student_required, teacher_required
from utils.time import utc_now_naive
from datetime import date, datetime, timedelta
from sqlalchemy import or_, and_

classroom_bp = Blueprint('classroom', __name__)

SCHEDULE_START = 7    # 7 AM
SCHEDULE_END   = 21   # 9 PM
TOTAL_MINS     = (SCHEDULE_END - SCHEDULE_START) * 60  # 840


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bookings_for_date(college_id: int, selected_date: date) -> list:
    dow = selected_date.weekday()
    return ClassroomBooking.query.filter(
        ClassroomBooking.college_id == college_id,
        ClassroomBooking.is_active  == True,
        or_(
            ClassroomBooking.booking_date == selected_date,
            and_(
                ClassroomBooking.is_recurring == True,
                ClassroomBooking.day_of_week  == dow,
                ClassroomBooking.valid_from   <= selected_date,
                or_(
                    ClassroomBooking.valid_until == None,
                    ClassroomBooking.valid_until >= selected_date,
                ),
            ),
        ),
    ).all()


def _position(b: ClassroomBooking) -> dict:
    """Return CSS left% and width% for a booking block on the timeline."""
    s = b.start_time.hour * 60 + b.start_time.minute - SCHEDULE_START * 60
    e = b.end_time.hour * 60   + b.end_time.minute   - SCHEDULE_START * 60
    left  = max(0.0, s / TOTAL_MINS * 100)
    width = max(0.5, (e - s) / TOTAL_MINS * 100)
    return {'booking': b, 'left': round(left, 3), 'width': round(width, 3)}


def _check_conflict(college_id, classroom_id, start_t, end_t,
                    is_recurring, booking_date, day_of_week,
                    valid_from, valid_until, exclude_id=None):
    """Return the first conflicting active booking or None.
    valid_until=None means ongoing (no end date).
    """
    q = ClassroomBooking.query.filter(
        ClassroomBooking.college_id   == college_id,
        ClassroomBooking.classroom_id == classroom_id,
        ClassroomBooking.is_active    == True,
    )
    if exclude_id:
        q = q.filter(ClassroomBooking.id != exclude_id)
    existing = q.all()

    for b in existing:
        # Time overlap?  [start_t, end_t) vs [b.start_time, b.end_time)
        if end_t <= b.start_time or b.end_time <= start_t:
            continue

        # Date / recurrence overlap?
        if is_recurring and b.is_recurring:
            if day_of_week != b.day_of_week:
                continue
            # Date range overlap (None = ongoing)
            if valid_until is not None and b.valid_from > valid_until:
                continue
            if b.valid_until is not None and valid_from > b.valid_until:
                continue

        elif is_recurring and not b.is_recurring:
            if b.booking_date.weekday() != day_of_week:
                continue
            if b.booking_date < valid_from:
                continue
            if valid_until is not None and b.booking_date > valid_until:
                continue

        elif not is_recurring and b.is_recurring:
            if booking_date.weekday() != b.day_of_week:
                continue
            if booking_date < b.valid_from:
                continue
            if b.valid_until is not None and booking_date > b.valid_until:
                continue

        else:   # both one-off
            if booking_date != b.booking_date:
                continue

        return b   # conflict found
    return None


def _parse_booking_form(form, college_id):
    """Parse booking form. Returns (data_dict, error_str).
    booking_type='class' → always recurring, multi-day, valid_until optional (None=ongoing).
    Other types → one-off with a specific date.
    """
    classroom_id  = form.get('classroom_id', type=int)
    title         = form.get('title', '').strip()
    booking_type  = form.get('booking_type', 'class')
    start_str     = form.get('start_time', '')
    end_str       = form.get('end_time', '')
    notes         = form.get('notes', '').strip()

    if not classroom_id or not start_str or not end_str:
        return None, 'Room, start time and end time are required.'
    if booking_type != 'class' and not title:
        return None, 'Title is required.'

    room = Classroom.query.filter_by(id=classroom_id, college_id=college_id).first()
    if not room:
        return None, 'Room not found.'

    try:
        start_t = datetime.strptime(start_str, '%H:%M').time()
        end_t   = datetime.strptime(end_str,   '%H:%M').time()
    except ValueError:
        return None, 'Invalid time format.'
    if end_t <= start_t:
        return None, 'End time must be after start time.'

    if booking_type == 'class':
        department_id = form.get('department_id', type=int) or None
        semester      = form.get('semester', type=int) or None

        # Auto-generate title from dept + semester
        dept = Department.query.filter_by(id=department_id, college_id=college_id).first() if department_id else None
        if dept:
            title = dept.name + (f' — Sem {semester}' if semester else '')
        elif not title:
            title = f'Sem {semester}' if semester else 'Class'

        days_raw = form.getlist('day_of_week')
        if not days_raw:
            return None, 'Select at least one day of the week.'
        try:
            days_of_week = [int(d) for d in days_raw]
        except ValueError:
            return None, 'Invalid day selection.'

        vf_raw = form.get('valid_from', '').strip()
        if not vf_raw:
            return None, 'Active from date is required.'
        try:
            valid_from = date.fromisoformat(vf_raw)
        except ValueError:
            return None, 'Invalid active from date.'

        vu_raw = form.get('valid_until', '').strip()
        valid_until = None
        if vu_raw:
            try:
                valid_until = date.fromisoformat(vu_raw)
                if valid_until < valid_from:
                    return None, 'Active until must be on or after active from.'
            except ValueError:
                return None, 'Invalid active until date.'

        return {
            'classroom_id': classroom_id, 'department_id': department_id,
            'semester': semester, 'title': title, 'booking_type': 'class',
            'is_recurring': True, 'booking_date': None,
            'days_of_week': days_of_week, 'valid_from': valid_from,
            'valid_until': valid_until,
            'start_t': start_t, 'end_t': end_t, 'notes': notes,
        }, None

    else:
        # One-off: exam, event, other
        department_id = form.get('department_id', type=int) or None
        semester      = form.get('semester', type=int) or None

        bd_raw = form.get('booking_date', '').strip()
        if not bd_raw:
            return None, 'Date is required for one-off schedules.'
        try:
            booking_date = date.fromisoformat(bd_raw)
        except ValueError:
            return None, 'Invalid date.'

        return {
            'classroom_id': classroom_id, 'department_id': department_id,
            'semester': semester, 'title': title, 'booking_type': booking_type,
            'is_recurring': False, 'booking_date': booking_date,
            'days_of_week': None, 'valid_from': None, 'valid_until': None,
            'start_t': start_t, 'end_t': end_t, 'notes': notes,
        }, None


# ── Views ─────────────────────────────────────────────────────────────────────

@classroom_bp.route('/admin/classrooms')
@login_required
@admin_required
def classrooms():
    cid = current_user.college_id

    date_str = request.args.get('date', date.today().isoformat())
    try:
        sel_date = date.fromisoformat(date_str)
    except ValueError:
        sel_date = date.today()

    rooms        = Classroom.query.filter_by(college_id=cid).order_by(Classroom.name).all()
    active_rooms = [r for r in rooms if r.is_active]
    departments  = Department.query.filter_by(college_id=cid).order_by(Department.name).all()

    # Build timeline grid for selected date
    day_bkgs = _bookings_for_date(cid, sel_date)
    by_room  = {}
    for b in day_bkgs:
        by_room.setdefault(b.classroom_id, []).append(b)

    grid = []
    for room in active_rooms:
        bkgs = sorted(by_room.get(room.id, []), key=lambda x: x.start_time)
        grid.append({
            'room':     room,
            'bookings': [_position(b) for b in bkgs],
        })

    hours = list(range(SCHEDULE_START, SCHEDULE_END))

    # Week strip (Mon–Sun of selected date's week)
    week_start = sel_date - timedelta(days=sel_date.weekday())
    week_strip = [week_start + timedelta(days=i) for i in range(7)]

    # All active schedules for list tab — newest first
    all_bkgs = (
        ClassroomBooking.query
        .filter_by(college_id=cid, is_active=True)
        .order_by(ClassroomBooking.created_at.desc())
        .limit(200).all()
    )

    return render_template(
        'admin/classrooms.html',
        rooms=rooms, active_rooms=active_rooms,
        departments=departments,
        grid=grid, hours=hours,
        sel_date=sel_date,
        today=date.today(),
        prev_date=(sel_date - timedelta(days=1)).isoformat(),
        next_date=(sel_date + timedelta(days=1)).isoformat(),
        week_strip=week_strip,
        all_bkgs=all_bkgs,
        SCHEDULE_START=SCHEDULE_START,
        SCHEDULE_END=SCHEDULE_END,
        TOTAL_MINS=TOTAL_MINS,
    )


@classroom_bp.route('/admin/classrooms/add', methods=['POST'])
@login_required
@admin_required
def add_classroom():
    cid  = current_user.college_id
    name = request.form.get('name', '').strip()
    if not name:
        flash('Room name is required.', 'danger')
        return redirect(url_for('classroom.classrooms'))

    if Classroom.query.filter_by(college_id=cid, name=name).first():
        flash(f'A room named "{name}" already exists.', 'danger')
        return redirect(url_for('classroom.classrooms'))

    room = Classroom(
        college_id=cid,
        name=name,
        capacity=request.form.get('capacity', type=int),
        room_type=request.form.get('room_type', 'lecture_hall'),
        block=request.form.get('block', '').strip() or None,
        is_active=True,
    )
    db.session.add(room)
    db.session.commit()
    flash(f'Room "{name}" added.', 'success')
    return redirect(url_for('classroom.classrooms', _anchor='rooms-tab'))


@classroom_bp.route('/admin/classrooms/<int:rid>/edit', methods=['POST'])
@login_required
@admin_required
def edit_classroom(rid):
    room = Classroom.query.filter_by(id=rid, college_id=current_user.college_id).first_or_404()
    room.name      = request.form.get('name', room.name).strip()
    room.capacity  = request.form.get('capacity', type=int) or room.capacity
    room.room_type = request.form.get('room_type', room.room_type)
    room.block     = request.form.get('block', '').strip() or None
    room.is_active = request.form.get('is_active') == '1'
    db.session.commit()
    flash(f'Room "{room.name}" updated.', 'success')
    return redirect(url_for('classroom.classrooms', _anchor='rooms-tab'))


@classroom_bp.route('/admin/classrooms/<int:rid>/delete', methods=['POST'])
@login_required
@strict_admin_required
def delete_classroom(rid):
    room = Classroom.query.filter_by(id=rid, college_id=current_user.college_id).first_or_404()
    name = room.name
    db.session.delete(room)
    db.session.commit()
    flash(f'Room "{name}" deleted.', 'info')
    return redirect(url_for('classroom.classrooms', _anchor='rooms-tab'))


@classroom_bp.route('/admin/classrooms/bookings/add', methods=['POST'])
@login_required
@admin_required
def add_booking():
    cid  = current_user.college_id
    data, err = _parse_booking_form(request.form, cid)
    if err:
        flash(err, 'danger')
        return redirect(url_for('classroom.classrooms'))

    if data['is_recurring']:
        # Class schedule — create one record per selected day
        created = 0
        conflict_days = []
        for dow in data['days_of_week']:
            conflict = _check_conflict(
                cid, data['classroom_id'], data['start_t'], data['end_t'],
                True, None, dow, data['valid_from'], data['valid_until'],
            )
            if conflict:
                conflict_days.append(ClassroomBooking.DAY_NAMES[dow])
                continue
            db.session.add(ClassroomBooking(
                college_id=cid, classroom_id=data['classroom_id'],
                department_id=data['department_id'], semester=data['semester'],
                title=data['title'], booking_type='class',
                is_recurring=True, booking_date=None,
                day_of_week=dow, valid_from=data['valid_from'],
                valid_until=data['valid_until'],
                start_time=data['start_t'], end_time=data['end_t'],
                notes=data['notes'], created_by=current_user.id,
            ))
            created += 1

        if created:
            db.session.commit()
            flash(f'Schedule "{data["title"]}" saved for {created} day(s).', 'success')
        if conflict_days:
            flash(f'Skipped due to time conflict: {", ".join(conflict_days)}.', 'warning')
        if not created and not conflict_days:
            flash('Nothing was saved.', 'danger')
        return redirect(url_for('classroom.classrooms'))

    else:
        # One-off
        conflict = _check_conflict(
            cid, data['classroom_id'], data['start_t'], data['end_t'],
            False, data['booking_date'], None, None, None,
        )
        if conflict:
            flash(
                f'Time conflict with existing schedule: "{conflict.title}" '
                f'({conflict.start_time.strftime("%H:%M")} – {conflict.end_time.strftime("%H:%M")}).',
                'danger',
            )
            return redirect(url_for('classroom.classrooms'))

        booking = ClassroomBooking(
            college_id=cid, classroom_id=data['classroom_id'],
            department_id=data['department_id'], semester=data['semester'],
            title=data['title'], booking_type=data['booking_type'],
            is_recurring=False, booking_date=data['booking_date'],
            day_of_week=None, valid_from=None, valid_until=None,
            start_time=data['start_t'], end_time=data['end_t'],
            notes=data['notes'], created_by=current_user.id,
        )
        db.session.add(booking)
        db.session.commit()
        flash(f'Schedule "{booking.title}" added.', 'success')
        return redirect(url_for('classroom.classrooms', date=data['booking_date'].isoformat()))


@classroom_bp.route('/admin/classrooms/bookings/<int:bid>/edit', methods=['POST'])
@login_required
@admin_required
def edit_booking(bid):
    b   = ClassroomBooking.query.filter_by(id=bid, college_id=current_user.college_id).first_or_404()
    cid = current_user.college_id

    new_classroom_id = request.form.get('classroom_id', type=int) or b.classroom_id
    new_dept_id      = request.form.get('department_id', type=int) or None
    new_semester     = request.form.get('semester', type=int) or None
    new_title        = request.form.get('title', '').strip() or b.title
    new_notes        = request.form.get('notes', '').strip()
    start_str        = request.form.get('start_time', '')
    end_str          = request.form.get('end_time', '')

    try:
        new_start = datetime.strptime(start_str, '%H:%M').time()
        new_end   = datetime.strptime(end_str,   '%H:%M').time()
    except ValueError:
        flash('Invalid time format.', 'danger')
        return redirect(url_for('classroom.classrooms'))
    if new_end <= new_start:
        flash('End time must be after start time.', 'danger')
        return redirect(url_for('classroom.classrooms'))

    new_valid_from  = b.valid_from
    new_valid_until = b.valid_until

    if b.is_recurring:
        vf_raw = request.form.get('valid_from', '').strip()
        if vf_raw:
            try:
                new_valid_from = date.fromisoformat(vf_raw)
            except ValueError:
                flash('Invalid active from date.', 'danger')
                return redirect(url_for('classroom.classrooms'))
        vu_raw = request.form.get('valid_until', '').strip()
        new_valid_until = None
        if vu_raw:
            try:
                new_valid_until = date.fromisoformat(vu_raw)
                if new_valid_until < new_valid_from:
                    flash('Active until must be on or after active from.', 'danger')
                    return redirect(url_for('classroom.classrooms'))
            except ValueError:
                flash('Invalid active until date.', 'danger')
                return redirect(url_for('classroom.classrooms'))

    conflict = _check_conflict(
        cid, new_classroom_id, new_start, new_end,
        b.is_recurring, b.booking_date, b.day_of_week,
        new_valid_from, new_valid_until, exclude_id=bid,
    )
    if conflict:
        flash(
            f'Time conflict with "{conflict.title}" '
            f'({conflict.start_time.strftime("%H:%M")}–{conflict.end_time.strftime("%H:%M")}).',
            'danger',
        )
        return redirect(url_for('classroom.classrooms'))

    b.classroom_id  = new_classroom_id
    b.department_id = new_dept_id
    b.semester      = new_semester
    b.title         = new_title
    b.start_time    = new_start
    b.end_time      = new_end
    b.valid_from    = new_valid_from
    b.valid_until   = new_valid_until
    b.notes         = new_notes
    db.session.commit()
    flash(f'Schedule "{b.title}" updated.', 'success')
    return redirect(url_for('classroom.classrooms', _anchor='bookings-tab'))


@classroom_bp.route('/admin/classrooms/bookings/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_bookings():
    ids = request.form.getlist('booking_ids', type=int)
    if ids:
        ClassroomBooking.query.filter(
            ClassroomBooking.id.in_(ids),
            ClassroomBooking.college_id == current_user.college_id,
        ).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(ids)} schedule(s) deleted.', 'info')
    return redirect(url_for('classroom.classrooms', _anchor='bookings-tab'))


@classroom_bp.route('/admin/classrooms/bookings/<int:bid>/delete', methods=['POST'])
@login_required
@admin_required
def delete_booking(bid):
    b = ClassroomBooking.query.filter_by(
        id=bid, college_id=current_user.college_id
    ).first_or_404()
    date_ret = (b.booking_date or date.today()).isoformat()
    db.session.delete(b)
    db.session.commit()
    flash('Schedule removed.', 'info')
    return redirect(url_for('classroom.classrooms', date=date_ret))


# ── Shared helper for student / teacher views ─────────────────────────────────

def _week_schedule(college_id: int, dept_semester_pairs: list[tuple]) -> list[dict]:
    """Return 7-day week schedule (Mon→Sun of current week) for given dept+semester pairs."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_days  = [week_start + timedelta(days=i) for i in range(7)]

    # Fetch all active bookings for these dept+semester pairs
    from sqlalchemy import tuple_ as sa_tuple
    if not dept_semester_pairs:
        return [{'date': d, 'is_today': d == today, 'slots': []} for d in week_days]

    all_bkgs = ClassroomBooking.query.filter(
        ClassroomBooking.college_id == college_id,
        ClassroomBooking.is_active  == True,
        or_(*[
            and_(ClassroomBooking.department_id == did, ClassroomBooking.semester == sem)
            for did, sem in dept_semester_pairs
        ]),
    ).all()

    days = []
    for d in week_days:
        slots = sorted(
            [b for b in all_bkgs if b.applies_to_date(d)],
            key=lambda b: b.start_time,
        )
        days.append({'date': d, 'is_today': d == today, 'slots': slots})
    return days


# ── Student classroom view ────────────────────────────────────────────────────

@classroom_bp.route('/student/classrooms')
@login_required
@student_required
def student_classrooms():
    student = current_user.student_profile
    cid     = current_user.college_id
    today   = date.today()

    dept = Department.query.get(student.department_id) if student.department_id else None
    pairs = [(student.department_id, student.semester)] if student.department_id and student.semester else []
    week  = _week_schedule(cid, pairs)
    today_slots = next((d['slots'] for d in week if d['is_today']), [])

    return render_template(
        'student/classrooms.html',
        student=student, dept=dept,
        today=today, week=week, today_slots=today_slots,
    )


# ── Teacher classroom view ────────────────────────────────────────────────────

@classroom_bp.route('/teacher/classrooms')
@login_required
@teacher_required
def teacher_classrooms():
    teacher = current_user.teacher_profile
    cid     = current_user.college_id
    today   = date.today()

    subjects = teacher.subjects
    # Unique (dept_id, semester) pairs across all subjects
    seen  = set()
    pairs = []
    dept_map = {}
    for s in subjects:
        if s.department_id and s.semester:
            key = (s.department_id, s.semester)
            if key not in seen:
                seen.add(key)
                pairs.append(key)
                if s.department_id not in dept_map:
                    dept_map[s.department_id] = s.department

    week        = _week_schedule(cid, pairs)
    today_slots = next((d['slots'] for d in week if d['is_today']), [])

    return render_template(
        'teacher/classrooms.html',
        teacher=teacher, dept_map=dept_map,
        today=today, week=week, today_slots=today_slots,
        subjects=subjects,
    )
