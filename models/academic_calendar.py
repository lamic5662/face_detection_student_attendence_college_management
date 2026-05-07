from extensions import db
from utils.time import utc_now_naive

DAYS_OF_WEEK = [
    (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'),
    (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
]

CALENDAR_EVENT_CATEGORIES = ('holiday', 'exam_week', 'event')

CATEGORY_META = {
    'holiday': {'label': 'Holiday', 'badge': 'danger'},
    'exam_week': {'label': 'Exam Week', 'badge': 'warning'},
    'event': {'label': 'Event', 'badge': 'info'},
}


class AcademicCalendarEvent(db.Model):
    __tablename__ = 'academic_calendar_events'
    __table_args__ = (
        db.Index('ix_calendar_events_college_dates', 'college_id', 'start_date', 'end_date'),
        db.Index('ix_calendar_events_college_scope', 'college_id', 'department_id', 'semester'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.Enum(*CALENDAR_EVENT_CATEGORIES), nullable=False, default='event')
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    semester = db.Column(db.Integer, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    department = db.relationship('Department', backref='calendar_events')
    creator = db.relationship('User', backref='calendar_events_created', lazy=True)

    @property
    def category_label(self) -> str:
        return CATEGORY_META.get(self.category, {}).get('label', self.category.replace('_', ' ').title())

    @property
    def category_badge(self) -> str:
        return CATEGORY_META.get(self.category, {}).get('badge', 'secondary')

    @property
    def scope_label(self) -> str:
        if self.department and self.semester:
            return f'{self.department.code or self.department.name} • Semester {self.semester}'
        if self.department:
            return f'{self.department.code or self.department.name} • All Semesters'
        if self.semester:
            return f'All Departments • Semester {self.semester}'
        return 'All College'


class SemesterSchedule(db.Model):
    """Stores official start/end dates for each semester per college/department/year.
    Used by the batch tracker and attendance % calculations.
    """
    __tablename__ = 'semester_schedules'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'department_id', 'semester', 'academic_year',
                            name='uq_semester_schedule'),
        db.Index('ix_semester_schedules_college', 'college_id', 'academic_year', 'semester'),
    )

    id            = db.Column(db.Integer, primary_key=True)
    college_id    = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)  # None = all depts
    semester      = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.Integer, nullable=False)
    start_date    = db.Column(db.Date, nullable=False)
    end_date      = db.Column(db.Date, nullable=False)
    created_by    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at    = db.Column(db.DateTime, default=utc_now_naive)

    department = db.relationship('Department', backref='semester_schedules', lazy=True)
    creator    = db.relationship('User', backref='semester_schedules_created', lazy=True)

    @property
    def label(self) -> str:
        dept = self.department.code if self.department else 'All Depts'
        return f'{dept} • Sem {self.semester} • {self.academic_year}'


class ReportScheduleConfig(db.Model):
    """Per-college config for automated weekly attendance report emails."""
    __tablename__ = 'report_schedule_configs'

    id         = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, unique=True)

    # Schedule
    enabled    = db.Column(db.Boolean, default=False, nullable=False)
    send_day   = db.Column(db.Integer, default=0, nullable=False)   # 0=Mon … 6=Sun
    send_hour  = db.Column(db.Integer, default=7, nullable=False)
    send_minute = db.Column(db.Integer, default=0, nullable=False)

    # Filters — None or empty list means "all"
    filter_department_ids  = db.Column(db.JSON, default=list, nullable=True)
    filter_semesters       = db.Column(db.JSON, default=list, nullable=True)
    filter_admission_years = db.Column(db.JSON, default=list, nullable=True)

    last_sent_at = db.Column(db.DateTime, nullable=True)
    updated_at   = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    updated_by   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    @property
    def send_day_label(self) -> str:
        return dict(DAYS_OF_WEEK).get(self.send_day, 'Monday')

    @property
    def send_time_display(self) -> str:
        return f'{self.send_hour:02d}:{self.send_minute:02d}'
