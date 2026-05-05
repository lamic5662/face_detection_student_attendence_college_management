from extensions import db
from utils.time import utc_now_naive


SUBMISSION_STATUSES = ('submitted', 'reviewed')


class AssignmentSubmission(db.Model):
    __tablename__ = 'assignment_submissions'
    __table_args__ = (
        db.UniqueConstraint('content_id', 'student_id', name='uq_assignment_submission_content_student'),
        db.Index('ix_assignment_submissions_college_content_status', 'college_id', 'content_id', 'status'),
        db.Index('ix_assignment_submissions_college_student_status', 'college_id', 'student_id', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    content_id = db.Column(db.Integer, db.ForeignKey('teacher_contents.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    submission_text = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(255), nullable=True)
    status = db.Column(db.Enum(*SUBMISSION_STATUSES), nullable=False, default='submitted')
    submitted_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)
    graded_at = db.Column(db.DateTime, nullable=True)
    marks_awarded = db.Column(db.Integer, nullable=True)
    feedback = db.Column(db.Text, nullable=True)

    content = db.relationship(
        'TeacherContent',
        backref=db.backref('assignment_submissions', cascade='all, delete-orphan', lazy='select'),
    )
    student = db.relationship(
        'Student',
        backref=db.backref('assignment_submissions', cascade='all, delete-orphan', lazy='select'),
    )

    @property
    def is_reviewed(self) -> bool:
        return self.status == 'reviewed'

    @property
    def is_late(self) -> bool:
        due_date = self.content.due_date if self.content else None
        if not due_date or not self.submitted_at:
            return False
        return self.submitted_at.date() > due_date
