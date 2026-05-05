from extensions import db
from utils.time import utc_now_naive

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
