from flask import current_app, has_app_context

from extensions import db
from utils.time import utc_now_naive

COLLEGE_PLANS = {
    'free': {
        'label': 'Free Trial',
        'color': 'secondary',
        'icon': 'bi-gift',
        'description': 'Full module access for a limited evaluation period.',
        'price_label': 'Free for limited trial',
        'includes': ['*'],
    },
    'starter': {
        'label': 'Starter',
        'color': 'primary',
        'icon': 'bi-rocket-takeoff',
        'description': 'Core essentials — Attendance, Notices, Academic Calendar, Timetable.',
        'price_label': 'Rs. 2,999 / month',
        'includes': ['attendance', 'notices', 'calendar', 'timetable'],
    },
    'standard': {
        'label': 'Standard',
        'color': 'info',
        'icon': 'bi-award',
        'description': 'Full academic suite — adds Exams, Learning Content, Library, Classrooms, Leaves, ID Cards, Batch Tracker, and Report Emails.',
        'price_label': 'Rs. 5,999 / month',
        'includes': ['attendance', 'notices', 'calendar', 'timetable', 'classrooms',
                     'learning_content', 'library', 'exams', 'leaves', 'batch_tracker',
                     'report_emails', 'digital_id_cards'],
    },
    'professional': {
        'label': 'Professional',
        'color': 'success',
        'icon': 'bi-gem',
        'description': 'Standard + Fees, Fee Reminders, Parent Portal, Analytics, and AI Assistant.',
        'price_label': 'Rs. 8,999 / month',
        'includes': ['attendance', 'notices', 'calendar', 'timetable', 'classrooms',
                     'learning_content', 'library', 'exams', 'leaves', 'batch_tracker',
                     'report_emails', 'digital_id_cards', 'fees', 'fee_reminders',
                     'parent_portal', 'analytics', 'ai_assistant'],
    },
    'enterprise': {
        'label': 'Enterprise',
        'color': 'warning',
        'icon': 'bi-stars',
        'description': 'All modules unlocked — includes Face Biometrics, Live Location, File Manager.',
        'price_label': 'Custom pricing',
        'includes': [],  # all features
    },
}


def normalize_college_plan_key(plan_key: str | None) -> str:
    normalized = (plan_key or 'free').strip().lower()
    if normalized == 'pro':
        return 'professional'
    if normalized in COLLEGE_PLANS:
        return normalized
    return 'free'


def resolved_college_plans() -> dict:
    plans = {key: dict(meta) for key, meta in COLLEGE_PLANS.items()}
    if not has_app_context():
        return plans

    from models.plan_pricing import PlanPricing

    for row in PlanPricing.query.all():
        if row.plan_key in plans:
            plans[row.plan_key]['price_label'] = row.price_label
    return plans


class College(db.Model):
    __tablename__ = 'colleges'

    id = db.Column(db.Integer, primary_key=True)
    university_id = db.Column(db.Integer, db.ForeignKey('universities.id'), nullable=True, index=True)
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
        plans = resolved_college_plans()
        return plans.get(normalize_college_plan_key(self.plan), plans['free'])

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

    @property
    def affiliated_universities(self):
        seen_ids = set()
        universities = []
        for department in self.departments:
            university = department.university
            if university and university.id not in seen_ids:
                universities.append(university)
                seen_ids.add(university.id)
        if self.university and self.university.id not in seen_ids:
            universities.append(self.university)
        return universities

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
