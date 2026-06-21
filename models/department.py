from extensions import db


class Department(db.Model):
    __tablename__ = 'departments'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'code', name='uq_departments_college_code'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    university_id = db.Column(db.Integer, db.ForeignKey('universities.id'), nullable=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), nullable=False)

    students = db.relationship('Student', backref='department', lazy=True)
    teachers = db.relationship('Teacher', backref='department', lazy=True)
    subjects = db.relationship('Subject', backref='department', lazy=True)
    university = db.relationship('University', backref='departments', lazy=True)

    @property
    def resolved_university(self):
        return self.university or self.college.university

    def __repr__(self):
        return f'<Department {self.code}>'
