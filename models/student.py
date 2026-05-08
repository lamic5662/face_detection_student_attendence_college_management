from extensions import db
import pickle
import numpy as np
from utils.time import utc_now_naive


class Student(db.Model):
    __tablename__ = 'students'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'roll_number', name='uq_students_college_roll_number'),
        db.Index('ix_students_college_department_semester', 'college_id', 'department_id', 'semester'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    roll_number = db.Column(db.String(20), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    # Extended profile
    phone = db.Column(db.String(20), nullable=True)
    dob = db.Column(db.Date, nullable=True)
    blood_group = db.Column(db.String(5), nullable=True)
    address = db.Column(db.Text, nullable=True)
    parent_name = db.Column(db.String(100), nullable=True)
    parent_phone = db.Column(db.String(20), nullable=True)
    admission_year = db.Column(db.Integer, nullable=True)
    # Face
    face_encoding = db.Column(db.LargeBinary, nullable=True)
    face_image_path = db.Column(db.String(255), nullable=True)
    enrolled_at = db.Column(db.DateTime, default=utc_now_naive)

    attendance_records = db.relationship('AttendanceRecord', backref='student', lazy=True,
                                         cascade='all, delete-orphan')

    def set_face_encoding(self, encoding_array):
        self.face_encoding = pickle.dumps(encoding_array)

    def get_face_encoding(self):
        if self.face_encoding:
            return pickle.loads(self.face_encoding)
        return None

    @property
    def is_face_enrolled(self):
        return self.face_encoding is not None

    def get_attendance_percentage(self, subject_id=None):
        from models.attendance import AttendanceRecord, AttendanceSession
        query = AttendanceRecord.query.join(AttendanceSession).filter(
            AttendanceRecord.student_id == self.id,
            AttendanceSession.status == 'completed'
        )
        if subject_id:
            query = query.filter(AttendanceSession.subject_id == subject_id)

        total = query.count()
        if total == 0:
            return 100.0
        present = query.filter(AttendanceRecord.status == 'present').count()
        return round((present / total) * 100, 2)

    @classmethod
    def generate_roll_number(cls, college_id: int, department_id: int, year: int) -> str:
        from models.college import College
        from models.department import Department
        college = College.query.get(college_id)
        dept = Department.query.get(department_id)
        college_code = (college.code if college else 'COL').upper()
        dept_code = (dept.code if dept else 'DEPT').upper()
        prefix = f"{college_code}-{dept_code}-{year}-"
        existing = cls.query.filter(
            cls.college_id == college_id,
            cls.roll_number.like(f"{prefix}%")
        ).count()
        seq = existing + 1
        candidate = f"{prefix}{seq:03d}"
        while cls.query.filter_by(college_id=college_id, roll_number=candidate).first():
            seq += 1
            candidate = f"{prefix}{seq:03d}"
        return candidate

    def __repr__(self):
        return f'<Student {self.roll_number}>'
