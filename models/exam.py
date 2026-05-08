from extensions import db
from utils.time import utc_now_naive


class Exam(db.Model):
    __tablename__ = 'exams'
    __table_args__ = (
        db.Index('ix_exams_college_subject_date', 'college_id', 'subject_id', 'exam_date'),
        db.Index('ix_exams_college_creator_date', 'college_id', 'created_by', 'exam_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    exam_type = db.Column(
        db.Enum('quiz', 'mid_term', 'final', 'practical', 'assignment'),
        nullable=False
    )
    exam_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=True)
    duration_mins = db.Column(db.Integer, nullable=True)
    total_marks = db.Column(db.Float, nullable=False, default=100)
    pass_marks = db.Column(db.Float, nullable=True)
    room = db.Column(db.String(50), nullable=True)
    instructions = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)
    deleted_at = db.Column(db.DateTime, nullable=True)

    subject = db.relationship('Subject', backref='exams', lazy=True)
    creator = db.relationship('Teacher', backref='exams', lazy=True)
    marks = db.relationship('Mark', backref='exam', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Exam {self.title}>'


GRADE_SCALE = [
    (90, 'A+'), (80, 'A'), (70, 'B+'), (60, 'B'),
    (50, 'C+'), (40, 'C'), (33, 'D'), (0, 'F'),
]


def compute_grade(obtained: float, total: float) -> str:
    if total <= 0:
        return '—'
    pct = obtained / total * 100
    for threshold, grade in GRADE_SCALE:
        if pct >= threshold:
            return grade
    return 'F'


class Mark(db.Model):
    __tablename__ = 'marks'

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    marks_obtained = db.Column(db.Float, nullable=True)
    is_absent = db.Column(db.Boolean, default=False)
    remarks = db.Column(db.String(200), nullable=True)
    entered_by = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True)
    entered_at = db.Column(db.DateTime, default=utc_now_naive)

    student = db.relationship('Student', backref='marks', lazy=True)
    teacher = db.relationship('Teacher', backref='marks_entered', lazy=True,
                              foreign_keys=[entered_by])

    __table_args__ = (
        db.UniqueConstraint('exam_id', 'student_id', name='uq_exam_student'),
        db.Index('ix_marks_college_student', 'college_id', 'student_id'),
        db.Index('ix_marks_college_exam', 'college_id', 'exam_id'),
    )

    @property
    def grade(self):
        if self.is_absent or self.marks_obtained is None:
            return 'AB'
        return compute_grade(self.marks_obtained, self.exam.total_marks)

    @property
    def percentage(self):
        if self.is_absent or self.marks_obtained is None:
            return None
        total = self.exam.total_marks
        return round(self.marks_obtained / total * 100, 1) if total > 0 else None

    def __repr__(self):
        return f'<Mark exam={self.exam_id} student={self.student_id}>'
