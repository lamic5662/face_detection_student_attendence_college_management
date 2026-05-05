import calendar as calendar_module
from datetime import date, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from extensions import db
from models.academic_calendar import AcademicCalendarEvent, CATEGORY_META, CALENDAR_EVENT_CATEGORIES
from models.department import Department
from models.parent import ParentStudent
from models.student import Student
from utils.decorators import admin_required
from utils.tenancy import current_college_id

calendar_bp = Blueprint('calendar', __name__)


def _normalize_year_month(year: int | None, month: int | None) -> tuple[int, int]:
    today = date.today()
    year = year or today.year
    month = month or today.month
    if month < 1:
        return year - 1, 12
    if month > 12:
        return year + 1, 1
    return year, month


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar_module.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _build_calendar_grid(year: int, month: int, events: list[AcademicCalendarEvent]) -> list[list[dict]]:
    today = date.today()
    month_start, month_end = _month_bounds(year, month)
    event_map: dict[date, list[AcademicCalendarEvent]] = {}

    for event in events:
        current = max(event.start_date, month_start)
        end_at = min(event.end_date, month_end)
        while current <= end_at:
            event_map.setdefault(current, []).append(event)
            current += timedelta(days=1)

    for day_events in event_map.values():
        day_events.sort(key=lambda item: (item.start_date, item.category, item.title.lower()))

    weeks = []
    cal = calendar_module.Calendar(firstweekday=0)
    for week in cal.monthdatescalendar(year, month):
        weeks.append([
            {
                'date': day,
                'in_month': day.month == month,
                'is_today': day == today,
                'events': event_map.get(day, []),
            }
            for day in week
        ])
    return weeks


def _apply_scope_filters(query, department_id: int | None = None, semester: int | None = None):
    if department_id:
        query = query.filter(
            db.or_(
                AcademicCalendarEvent.department_id == None,
                AcademicCalendarEvent.department_id == department_id,
            )
        )
    if semester:
        query = query.filter(
            db.or_(
                AcademicCalendarEvent.semester == None,
                AcademicCalendarEvent.semester == semester,
            )
        )
    return query


def _parent_children() -> list[Student]:
    return (
        Student.query
        .join(ParentStudent, ParentStudent.student_id == Student.id)
        .filter(
            ParentStudent.parent_id == current_user.id,
            Student.college_id == current_user.college_id,
        )
        .order_by(Student.roll_number)
        .all()
    )


def _parent_selected_child(children: list[Student], child_id: int | None) -> Student | None:
    if not children:
        return None
    for child in children:
        if child.id == child_id:
            return child
    return children[0]


def _calendar_context():
    today = date.today()
    year, month = _normalize_year_month(
        request.args.get('year', type=int),
        request.args.get('month', type=int),
    )
    month_start, month_end = _month_bounds(year, month)

    departments = (
        Department.query
        .filter_by(college_id=current_college_id())
        .order_by(Department.name)
        .all()
    )
    selected_dept = request.args.get('department_id', type=int)
    selected_sem = request.args.get('semester', type=int)
    selected_child_id = request.args.get('child_id', type=int)
    children = []
    selected_child = None
    context_label = None

    query = AcademicCalendarEvent.query.filter_by(college_id=current_college_id())

    if current_user.role == 'student':
        student = current_user.student_profile
        selected_dept = student.department_id
        selected_sem = student.semester
        context_label = f'{student.department.name} • Semester {student.semester}'
        query = _apply_scope_filters(query, selected_dept, selected_sem)
    elif current_user.role == 'teacher':
        teacher = current_user.teacher_profile
        selected_dept = teacher.department_id
        context_label = teacher.department.name if teacher.department else 'My Department'
        query = _apply_scope_filters(query, selected_dept, selected_sem)
    elif current_user.role == 'parent':
        children = _parent_children()
        selected_child = _parent_selected_child(children, selected_child_id)
        if selected_child:
            selected_dept = selected_child.department_id
            selected_sem = selected_child.semester
            context_label = f'{selected_child.user.name} • {selected_child.department.name} • Semester {selected_child.semester}'
            query = _apply_scope_filters(query, selected_dept, selected_sem)
        else:
            query = query.filter(
                AcademicCalendarEvent.department_id == None,
                AcademicCalendarEvent.semester == None,
            )
    else:
        query = _apply_scope_filters(query, selected_dept, selected_sem)
        if selected_dept and selected_sem:
            department = next((d for d in departments if d.id == selected_dept), None)
            if department:
                context_label = f'{department.name} • Semester {selected_sem}'
        elif selected_dept:
            department = next((d for d in departments if d.id == selected_dept), None)
            context_label = department.name if department else None

    month_events = (
        query
        .filter(
            AcademicCalendarEvent.start_date <= month_end,
            AcademicCalendarEvent.end_date >= month_start,
        )
        .order_by(AcademicCalendarEvent.start_date, AcademicCalendarEvent.category, AcademicCalendarEvent.title)
        .all()
    )

    upcoming_events = (
        query
        .filter(AcademicCalendarEvent.end_date >= today)
        .order_by(AcademicCalendarEvent.start_date, AcademicCalendarEvent.category, AcademicCalendarEvent.title)
        .limit(10)
        .all()
    )

    prev_year, prev_month = _normalize_year_month(year, month - 1)
    next_year, next_month = _normalize_year_month(year, month + 1)

    nav_filters = {}
    if current_user.role == 'admin':
        if selected_dept:
            nav_filters['department_id'] = selected_dept
        if selected_sem:
            nav_filters['semester'] = selected_sem
    elif current_user.role == 'teacher':
        if selected_sem:
            nav_filters['semester'] = selected_sem
    elif current_user.role == 'parent' and selected_child:
        nav_filters['child_id'] = selected_child.id

    return {
        'category_meta': CATEGORY_META,
        'children': children,
        'context_label': context_label,
        'departments': departments,
        'month_events': month_events,
        'month_label': date(year, month, 1).strftime('%B %Y'),
        'next_url': url_for('calendar.view_calendar', year=next_year, month=next_month, **nav_filters),
        'prev_url': url_for('calendar.view_calendar', year=prev_year, month=prev_month, **nav_filters),
        'selected_child': selected_child,
        'selected_dept': selected_dept,
        'selected_sem': selected_sem,
        'show_department_filter': current_user.role == 'admin',
        'show_semester_filter': current_user.role in ('admin', 'teacher'),
        'upcoming_events': upcoming_events,
        'weeks': _build_calendar_grid(year, month, month_events),
        'year': year,
        'month': month,
    }


def _read_event_form():
    title = request.form.get('title', '').strip()
    category = request.form.get('category', 'event').strip()
    description = request.form.get('description', '').strip() or None
    department_id = request.form.get('department_id', type=int) or None
    semester = request.form.get('semester', type=int) or None

    start_raw = request.form.get('start_date', '').strip()
    end_raw = request.form.get('end_date', '').strip()

    if not title:
        raise ValueError('Title is required.')
    if category not in CALENDAR_EVENT_CATEGORIES:
        raise ValueError('Invalid category.')
    if not start_raw:
        raise ValueError('Start date is required.')

    try:
        start_date = date.fromisoformat(start_raw)
    except ValueError as exc:
        raise ValueError('Invalid start date.') from exc

    if end_raw:
        try:
            end_date = date.fromisoformat(end_raw)
        except ValueError as exc:
            raise ValueError('Invalid end date.') from exc
    else:
        end_date = start_date

    if end_date < start_date:
        raise ValueError('End date must be on or after the start date.')
    if semester and semester not in range(1, 9):
        raise ValueError('Semester must be between 1 and 8.')

    return {
        'title': title,
        'category': category,
        'description': description,
        'department_id': department_id,
        'semester': semester,
        'start_date': start_date,
        'end_date': end_date,
    }


@calendar_bp.route('/calendar')
@login_required
def view_calendar():
    context = _calendar_context()
    return render_template('calendar/view.html', **context)


@calendar_bp.route('/calendar/manage')
@login_required
@admin_required
def manage_calendar():
    department_id = request.args.get('department_id', type=int)
    semester = request.args.get('semester', type=int)
    category = request.args.get('category', '').strip()
    q = request.args.get('q', '').strip()

    query = AcademicCalendarEvent.query.filter_by(college_id=current_college_id())
    if department_id:
        query = query.filter(AcademicCalendarEvent.department_id == department_id)
    if semester:
        query = query.filter(AcademicCalendarEvent.semester == semester)
    if category in CALENDAR_EVENT_CATEGORIES:
        query = query.filter(AcademicCalendarEvent.category == category)
    if q:
        query = query.filter(
            db.or_(
                AcademicCalendarEvent.title.ilike(f'%{q}%'),
                AcademicCalendarEvent.description.ilike(f'%{q}%'),
            )
        )

    events = (
        query
        .order_by(AcademicCalendarEvent.start_date.desc(), AcademicCalendarEvent.title)
        .all()
    )

    return render_template(
        'calendar/manage.html',
        category_meta=CATEGORY_META,
        departments=Department.query.filter_by(college_id=current_college_id()).order_by(Department.name).all(),
        events=events,
        selected_dept=department_id,
        selected_sem=semester,
        selected_category=category,
        q=q,
    )


@calendar_bp.route('/calendar/events/create', methods=['POST'])
@login_required
@admin_required
def create_event():
    try:
        payload = _read_event_form()
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('calendar.manage_calendar'))

    event = AcademicCalendarEvent(**payload, created_by=current_user.id, college_id=current_user.college_id)
    db.session.add(event)
    db.session.commit()
    flash('Calendar event created.', 'success')
    return redirect(url_for('calendar.manage_calendar'))


@calendar_bp.route('/calendar/events/<int:event_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_event(event_id):
    event = db.session.get(AcademicCalendarEvent, event_id)
    if event is None or event.college_id != current_user.college_id:
        flash('Calendar event not found.', 'danger')
        return redirect(url_for('calendar.manage_calendar'))

    try:
        payload = _read_event_form()
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('calendar.manage_calendar'))

    for key, value in payload.items():
        setattr(event, key, value)

    db.session.commit()
    flash('Calendar event updated.', 'success')
    return redirect(url_for('calendar.manage_calendar'))


@calendar_bp.route('/calendar/events/<int:event_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_event(event_id):
    event = db.session.get(AcademicCalendarEvent, event_id)
    if event is None or event.college_id != current_user.college_id:
        flash('Calendar event not found.', 'danger')
        return redirect(url_for('calendar.manage_calendar'))

    db.session.delete(event)
    db.session.commit()
    flash('Calendar event deleted.', 'info')
    return redirect(url_for('calendar.manage_calendar'))
