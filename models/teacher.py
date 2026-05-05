from extensions import db


class Teacher(db.Model):
    __tablename__ = 'teachers'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'employee_id', name='uq_teachers_college_employee_id'),
        db.Index('ix_teachers_college_department', 'college_id', 'department_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    employee_id = db.Column(db.String(20), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    # Extended profile
    phone = db.Column(db.String(20), nullable=True)
    qualification = db.Column(db.String(200), nullable=True)
    designation = db.Column(db.String(100), nullable=True)
    joining_date = db.Column(db.Date, nullable=True)
    sign_path = db.Column(db.String(255), nullable=True)

    subjects = db.relationship('Subject', backref='teacher', lazy=True)
    sessions = db.relationship('AttendanceSession', backref='teacher', lazy=True)

    def __repr__(self):
        return f'<Teacher {self.employee_id}>'
