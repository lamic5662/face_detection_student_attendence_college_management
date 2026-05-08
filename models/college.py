from flask import current_app, has_app_context

from extensions import db
from utils.time import utc_now_naive

COLLEGE_PLANS = {
    'free': {
        'label': 'Free',
        'color': 'secondary',
        'icon': 'bi-gift',
        'description': 'Trial / evaluation access. No production features enabled by default.',
        'includes': [],
    },
    'starter': {
        'label': 'Starter',
        'color': 'primary',
        'icon': 'bi-rocket-takeoff',
        'description': 'Core essentials — Attendance, Notices, Academic Calendar, Timetable.',
        'includes': ['attendance', 'notices', 'calendar', 'timetable'],
    },
    'standard': {
        'label': 'Standard',
        'color': 'info',
        'icon': 'bi-award',
        'description': 'Full academic suite — adds Exams, Learning Content, Classrooms, Leaves, ID Cards, Batch Tracker, Report Emails.',
        'includes': ['attendance', 'notices', 'calendar', 'timetable', 'classrooms',
                     'learning_content', 'exams', 'leaves', 'batch_tracker',
                     'report_emails', 'digital_id_cards'],
    },
    'professional': {
        'label': 'Professional',
        'color': 'success',
        'icon': 'bi-gem',
        'description': 'Standard + Fees, Fee Reminders, Parent Portal, Analytics, AI Assistant.',
        'includes': ['attendance', 'notices', 'calendar', 'timetable', 'classrooms',
                     'learning_content', 'exams', 'leaves', 'batch_tracker',
                     'report_emails', 'digital_id_cards', 'fees', 'fee_reminders',
                     'parent_portal', 'analytics', 'ai_assistant'],
    },
    'enterprise': {
        'label': 'Enterprise',
        'color': 'warning',
        'icon': 'bi-stars',
        'description': 'All modules unlocked — includes Face Biometrics, Live Location, File Manager.',
        'includes': [],  # all features
    },
}


class College(db.Model):
    __tablename__ = 'colleges'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    subdomain = db.Column(db.String(100), unique=True, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now_naive, nullable=False)

    # SaaS billing fields
    plan = db.Column(db.String(20), default='free', nullable=False)
    plan_expires_at = db.Column(db.DateTime, nullable=True)
    billing_notes = db.Column(db.Text, nullable=True)

    @property
    def plan_meta(self) -> dict:
        return COLLEGE_PLANS.get(self.plan or 'free', COLLEGE_PLANS['free'])

    @property
    def plan_expired(self) -> bool:
        if self.plan_expires_at is None:
            return False
        return utc_now_naive() > self.plan_expires_at

    users = db.relationship('User', backref='college', lazy=True)
    feature_access = db.relationship('CollegeFeatureAccess', backref='college', lazy=True, cascade='all, delete-orphan')
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
