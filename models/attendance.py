from extensions import db
from utils.time import utc_now_naive, utc_time_now, utc_today


class AttendanceSession(db.Model):
    __tablename__ = 'attendance_sessions'
    __table_args__ = (
        db.Index('ix_attendance_sessions_college_status_date', 'college_id', 'status', 'date'),
        db.Index('ix_attendance_sessions_college_teacher_status', 'college_id', 'teacher_id', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=utc_today)
    start_time = db.Column(db.Time, nullable=False, default=utc_time_now)
    end_time = db.Column(db.Time, nullable=True)
    status = db.Column(db.Enum('active', 'completed', 'cancelled'), default='active')
    created_at = db.Column(db.DateTime, default=utc_now_naive)

    records = db.relationship('AttendanceRecord', backref='session', lazy=True,
                              cascade='all, delete-orphan')

    @property
    def present_count(self):
        return sum(1 for r in self.records if r.status == 'present')

    @property
    def absent_count(self):
        return sum(1 for r in self.records if r.status == 'absent')

    @property
    def total_students(self):
        return len(self.records)

    def __repr__(self):
        return f'<Session {self.id} {self.date}>'


class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_records'

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_sessions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    status = db.Column(db.Enum('present', 'absent', 'late'), default='absent')
    marked_at = db.Column(db.DateTime, nullable=True)
    liveness_verified = db.Column(db.Boolean, default=False)
    confidence_score = db.Column(db.Float, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('session_id', 'student_id', name='uq_session_student'),
        db.Index('ix_attendance_records_college_student', 'college_id', 'student_id'),
        db.Index('ix_attendance_records_college_session_status', 'college_id', 'session_id', 'status'),
    )

    def __repr__(self):
        return f'<Record session={self.session_id} student={self.student_id} {self.status}>'
