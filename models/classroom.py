from __future__ import annotations
from extensions import db
from utils.time import utc_now_naive


class Classroom(db.Model):
    __tablename__ = 'classrooms'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'name', name='uq_classroom_college_name'),
        db.Index('ix_classrooms_college_active', 'college_id', 'is_active'),
    )

    id          = db.Column(db.Integer, primary_key=True)
    college_id  = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False)
    name        = db.Column(db.String(100), nullable=False)
    capacity    = db.Column(db.Integer, nullable=True)
    room_type   = db.Column(
        db.Enum('lecture_hall', 'lab', 'seminar', 'exam_hall', 'other'),
        default='lecture_hall', nullable=False
    )
    block       = db.Column(db.String(50), nullable=True)   # "Block A", "Ground Floor"
    is_active   = db.Column(db.Boolean, default=True, nullable=False)
    created_at  = db.Column(db.DateTime, default=utc_now_naive)

    bookings = db.relationship(
        'ClassroomBooking', backref='classroom', lazy=True, cascade='all, delete-orphan'
    )

    TYPE_LABELS = {
        'lecture_hall': 'Lecture Hall',
        'lab':          'Laboratory',
        'seminar':      'Seminar Room',
        'exam_hall':    'Exam Hall',
        'other':        'Other',
    }
    TYPE_ICONS = {
        'lecture_hall': 'bi-building',
        'lab':          'bi-cpu',
        'seminar':      'bi-people-fill',
        'exam_hall':    'bi-pencil-square',
        'other':        'bi-door-open',
    }

    @property
    def type_label(self):
        return self.TYPE_LABELS.get(self.room_type, self.room_type)

    @property
    def type_icon(self):
        return self.TYPE_ICONS.get(self.room_type, 'bi-door-open')

    def __repr__(self):
        return f'<Classroom {self.name}>'


class ClassroomBooking(db.Model):
    __tablename__ = 'classroom_bookings'
    __table_args__ = (
        db.Index('ix_cb_college_classroom', 'college_id', 'classroom_id'),
        db.Index('ix_cb_college_date',      'college_id', 'booking_date'),
        db.Index('ix_cb_recurring_dow',     'college_id', 'is_recurring', 'day_of_week'),
    )

    id            = db.Column(db.Integer, primary_key=True)
    college_id    = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False)
    classroom_id  = db.Column(db.Integer, db.ForeignKey('classrooms.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    semester      = db.Column(db.Integer, nullable=True)
    title         = db.Column(db.String(150), nullable=False)
    booking_type  = db.Column(
        db.Enum('class', 'exam', 'event', 'other'),
        default='class', nullable=False
    )

    # One-off booking
    is_recurring  = db.Column(db.Boolean, default=False, nullable=False)
    booking_date  = db.Column(db.Date, nullable=True)

    # Recurring / class schedule fields
    day_of_week   = db.Column(db.Integer, nullable=True)   # 0 = Monday … 6 = Sunday
    valid_from    = db.Column(db.Date, nullable=True)
    valid_until   = db.Column(db.Date, nullable=True)      # NULL = ongoing

    is_active     = db.Column(db.Boolean, default=True, nullable=False)

    start_time    = db.Column(db.Time, nullable=False)
    end_time      = db.Column(db.Time, nullable=False)
    notes         = db.Column(db.Text, nullable=True)
    created_by    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at    = db.Column(db.DateTime, default=utc_now_naive)

    department = db.relationship('Department', backref='classroom_bookings', lazy=True)
    creator    = db.relationship('User',       backref='classroom_bookings', lazy=True)

    DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    TYPE_COLORS = {
        'class': '#2563eb',
        'exam':  '#dc2626',
        'event': '#7c3aed',
        'other': '#64748b',
    }

    @property
    def duration_mins(self):
        s = self.start_time.hour * 60 + self.start_time.minute
        e = self.end_time.hour * 60 + self.end_time.minute
        return max(0, e - s)

    @property
    def day_name(self):
        if self.day_of_week is not None:
            return self.DAY_NAMES[self.day_of_week]
        return ''

    @property
    def color(self):
        return self.TYPE_COLORS.get(self.booking_type, '#64748b')

    def applies_to_date(self, d) -> bool:
        if self.is_recurring:
            return (
                self.day_of_week == d.weekday()
                and self.valid_from <= d
                and (self.valid_until is None or self.valid_until >= d)
            )
        return self.booking_date == d

    @property
    def is_ongoing(self) -> bool:
        return self.is_recurring and self.valid_until is None

    def __repr__(self):
        return f'<ClassroomBooking {self.title}>'
