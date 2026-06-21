import json

from extensions import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from utils.time import utc_now_naive


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'email', name='uq_users_college_email'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('super_admin', 'admin', 'sub_admin', 'teacher', 'student', 'parent', 'librarian'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    password_changed_at = db.Column(db.DateTime, nullable=True)
    password_setup_email_sent_at = db.Column(db.DateTime, nullable=True)
    sidebar_pins = db.Column(db.Text, nullable=True)
    dashboard_widgets = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    last_login_at = db.Column(db.DateTime, nullable=True)

    student_profile = db.relationship('Student', backref='user', uselist=False, lazy=True, cascade='all, delete-orphan')
    teacher_profile = db.relationship('Teacher', backref='user', uselist=False, lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.must_change_password = False
        self.password_changed_at = utc_now_naive()

    def set_temporary_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.must_change_password = True
        self.password_changed_at = None

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def mark_password_setup_email_sent(self):
        self.password_setup_email_sent_at = utc_now_naive()

    def get_sidebar_pin_keys(self):
        if not self.sidebar_pins:
            return []
        try:
            keys = json.loads(self.sidebar_pins)
        except (TypeError, ValueError):
            return []
        return [key for key in keys if isinstance(key, str)]

    def set_sidebar_pin_keys(self, keys):
        self.sidebar_pins = json.dumps(list(keys)) if keys else None

    def get_dashboard_widget_keys(self):
        if not self.dashboard_widgets:
            return []
        try:
            keys = json.loads(self.dashboard_widgets)
        except (TypeError, ValueError):
            return []
        return [key for key in keys if isinstance(key, str)]

    def set_dashboard_widget_keys(self, keys):
        self.dashboard_widgets = json.dumps(list(keys)) if keys else None

    @property
    def is_admin(self):
        return self.role in ('admin', 'sub_admin')

    @property
    def is_sub_admin(self):
        return self.role == 'sub_admin'

    @property
    def is_super_admin(self):
        return self.role == 'super_admin'

    @property
    def is_teacher(self):
        return self.role == 'teacher'

    @property
    def is_student(self):
        return self.role == 'student'

    @property
    def is_parent(self):
        return self.role == 'parent'

    @property
    def is_librarian(self):
        return self.role == 'librarian'

    @property
    def full_name(self):
        return self.name

    def __repr__(self):
        return f'<User {self.email} ({self.role})>'
