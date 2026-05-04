from extensions import db
from utils.time import utc_now_naive


class ParentStudent(db.Model):
    """Links a parent user to one or more student records."""
    __tablename__ = 'parent_students'

    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    relationship = db.Column(
        db.Enum('father', 'mother', 'guardian', 'other'),
        default='guardian', nullable=False
    )
    created_at = db.Column(db.DateTime, default=utc_now_naive)

    parent = db.relationship('User', backref=db.backref('parent_links', lazy='dynamic'))
    student = db.relationship('Student', backref=db.backref('parent_links', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('parent_id', 'student_id', name='uq_parent_student'),
    )


class TeacherStatus(db.Model):
    """Voluntary presence/check-in status set by teacher."""
    __tablename__ = 'teacher_statuses'

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id', ondelete='CASCADE'),
                           unique=True, nullable=False)
    status = db.Column(
        db.Enum('on_campus', 'in_class', 'unavailable', 'off_campus'),
        default='off_campus', nullable=False
    )
    note = db.Column(db.String(200), nullable=True)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    teacher = db.relationship('Teacher', backref=db.backref('status_record', uselist=False))

    STATUS_LABELS = {
        'on_campus':   ('On Campus',   'success'),
        'in_class':    ('In Class',    'primary'),
        'unavailable': ('Unavailable', 'warning'),
        'off_campus':  ('Off Campus',  'secondary'),
    }

    @property
    def label(self):
        return self.STATUS_LABELS.get(self.status, ('Unknown', 'secondary'))[0]

    @property
    def badge_color(self):
        return self.STATUS_LABELS.get(self.status, ('Unknown', 'secondary'))[1]


class ClassAlert(db.Model):
    """Tracks absent-teacher alerts already sent to prevent duplicates."""
    __tablename__ = 'class_alerts'

    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer, db.ForeignKey('timetable_slots.id', ondelete='CASCADE'),
                        nullable=False)
    alert_date = db.Column(db.Date, nullable=False)
    sent_at = db.Column(db.DateTime, default=utc_now_naive)
    recipient_count = db.Column(db.Integer, default=0)
    triggered_by = db.Column(db.Enum('auto', 'manual'), default='auto')

    slot = db.relationship('TimetableSlot', backref='alerts')

    __table_args__ = (
        db.UniqueConstraint('slot_id', 'alert_date', name='uq_alert_per_day'),
    )
