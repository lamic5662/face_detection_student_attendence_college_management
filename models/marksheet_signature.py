from extensions import db
from utils.time import utc_now_naive


class MarksheetSignature(db.Model):
    __tablename__ = 'marksheet_signatures'

    id            = db.Column(db.Integer, primary_key=True)
    role          = db.Column(db.Enum('principal', 'hod', 'class_teacher'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    semester      = db.Column(db.Integer, nullable=True)
    name          = db.Column(db.String(100), nullable=True)
    designation   = db.Column(db.String(100), nullable=True)
    sign_path     = db.Column(db.String(255), nullable=True)
    teacher_id    = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True)
    updated_at    = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    department = db.relationship('Department', backref='signatures', lazy=True)
    teacher    = db.relationship('Teacher', backref='class_teacher_sigs', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('role', 'department_id', 'semester', name='uq_ms_signature'),
    )

    @property
    def role_label(self):
        return {'principal': 'Principal / Registrar',
                'hod':       'Head of Department',
                'class_teacher': 'Class Teacher'}[self.role]
