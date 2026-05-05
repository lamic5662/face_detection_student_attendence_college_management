from extensions import db

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


class TimetableSlot(db.Model):
    __tablename__ = 'timetable_slots'

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)   # 0=Mon … 6=Sun
    period_no = db.Column(db.Integer, nullable=False)      # 1-based
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True)
    room = db.Column(db.String(50), nullable=True)
    slot_type = db.Column(
        db.Enum('lecture', 'lab', 'break', 'free'),
        default='lecture'
    )

    department = db.relationship('Department', backref='timetable_slots', lazy=True)
    subject = db.relationship('Subject', backref='timetable_slots', lazy=True)
    teacher = db.relationship('Teacher', backref='timetable_slots', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('department_id', 'semester', 'day_of_week', 'period_no',
                            name='uq_slot'),
        db.Index('ix_timetable_slots_college_scope_day', 'college_id', 'department_id', 'semester', 'day_of_week'),
        db.Index('ix_timetable_slots_college_teacher_day', 'college_id', 'teacher_id', 'day_of_week'),
    )

    @property
    def day_name(self):
        return DAYS[self.day_of_week] if 0 <= self.day_of_week < len(DAYS) else ''

    def __repr__(self):
        return f'<Slot {self.day_name} P{self.period_no}>'
