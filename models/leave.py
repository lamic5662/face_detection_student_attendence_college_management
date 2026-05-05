from extensions import db
from utils.time import utc_now_naive


LEAVE_TYPES = ('student_subject', 'student_fullday', 'teacher')


class LeaveRequest(db.Model):
    __tablename__ = 'leave_requests'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'ref_number', name='uq_leave_requests_college_ref_number'),
        db.Index('ix_leave_requests_college_status_created', 'college_id', 'status', 'created_at'),
        db.Index('ix_leave_requests_college_student_status', 'college_id', 'student_id', 'status'),
        db.Index('ix_leave_requests_college_teacher_status', 'college_id', 'teacher_id', 'status'),
    )

    id          = db.Column(db.Integer, primary_key=True)
    college_id  = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    leave_type  = db.Column(db.Enum(*LEAVE_TYPES), nullable=False, default='student_subject')
    student_id  = db.Column(db.Integer, db.ForeignKey('students.id'),  nullable=True)
    subject_id  = db.Column(db.Integer, db.ForeignKey('subjects.id'),  nullable=True)
    teacher_id  = db.Column(db.Integer, db.ForeignKey('teachers.id'),  nullable=True)
    approver_id = db.Column(db.Integer, db.ForeignKey('users.id'),     nullable=True)
    ref_number  = db.Column(db.String(30), nullable=True)
    from_date   = db.Column(db.Date, nullable=False)
    to_date     = db.Column(db.Date, nullable=False)
    reason      = db.Column(db.String(500), nullable=False)
    status      = db.Column(db.Enum('pending', 'approved', 'rejected'), default='pending')
    teacher_remark = db.Column(db.String(300), nullable=True)
    created_at  = db.Column(db.DateTime, default=utc_now_naive)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    student  = db.relationship('Student', backref='leave_requests',   lazy=True,
                               foreign_keys=[student_id])
    subject  = db.relationship('Subject', backref='leave_requests',   lazy=True,
                               foreign_keys=[subject_id])
    teacher  = db.relationship('Teacher', backref='own_leaves',       lazy=True,
                               foreign_keys=[teacher_id])
    approver = db.relationship('User',    backref='approved_leaves',  lazy=True,
                               foreign_keys=[approver_id])

    @property
    def days(self):
        return (self.to_date - self.from_date).days + 1

    @property
    def remark(self):
        return self.teacher_remark

    @staticmethod
    def generate_ref(college):
        year = utc_now_naive().year
        college_code = (getattr(college, 'code', None) or 'MAIN').upper()
        prefix = f'LV-{college_code}-{year}-'
        last = (LeaveRequest.query
                .filter(
                    LeaveRequest.college_id == college.id,
                    LeaveRequest.ref_number.like(f'{prefix}%')
                )
                .order_by(LeaveRequest.id.desc())
                .first())
        seq = 1
        if last and last.ref_number:
            try:
                seq = int(last.ref_number.split('-')[-1]) + 1
            except ValueError:
                pass
        return f'{prefix}{seq:05d}'

    @property
    def applicant_name(self):
        if self.student:
            return self.student.user.name
        if self.teacher:
            return self.teacher.user.name
        return '—'

    @property
    def applicant_id_str(self):
        if self.student:
            return self.student.roll_number
        if self.teacher:
            return self.teacher.employee_id
        return '—'

    @property
    def department(self):
        if self.student:
            return self.student.department
        if self.teacher:
            return self.teacher.department
        return None

    def __repr__(self):
        return f'<Leave #{self.id} {self.leave_type} {self.status}>'
