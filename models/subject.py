from extensions import db


class Subject(db.Model):
    __tablename__ = 'subjects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    credit_hours = db.Column(db.Integer, default=3)

    sessions = db.relationship('AttendanceSession', backref='subject', lazy=True)

    def __repr__(self):
        return f'<Subject {self.code}>'
