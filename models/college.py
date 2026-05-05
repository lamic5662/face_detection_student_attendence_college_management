from flask import current_app, has_app_context

from extensions import db
from utils.time import utc_now_naive


class College(db.Model):
    __tablename__ = 'colleges'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    subdomain = db.Column(db.String(100), unique=True, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)

    users = db.relationship('User', backref='college', lazy=True)
    departments = db.relationship('Department', backref='college', lazy=True)
    students = db.relationship('Student', backref='college', lazy=True)
    teachers = db.relationship('Teacher', backref='college', lazy=True)
    subjects = db.relationship('Subject', backref='college', lazy=True)

    @classmethod
    def default_code(cls) -> str:
        if has_app_context():
            return current_app.config.get('DEFAULT_COLLEGE_CODE', 'MAIN').strip().upper() or 'MAIN'
        return 'MAIN'

    @classmethod
    def default_name(cls) -> str:
        if has_app_context():
            return current_app.config.get('COLLEGE_NAME', 'College')
        return 'College'

    @classmethod
    def ensure_default(cls):
        college = cls.query.order_by(cls.id).first()
        if college is not None:
            return college

        college = cls(name=cls.default_name(), code=cls.default_code())
        db.session.add(college)
        db.session.commit()
        return college

    def __repr__(self):
        return f'<College {self.code}>'
