from extensions import db
from utils.time import utc_now_naive


class Notice(db.Model):
    __tablename__ = 'notices'
    __table_args__ = (
        db.Index('ix_notices_college_role_pinned_created', 'college_id', 'target_role', 'is_pinned', 'created_at'),
        db.Index('ix_notices_college_expires_at', 'college_id', 'expires_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(
        db.Enum('general', 'exam', 'holiday', 'event', 'fee', 'urgent'),
        default='general'
    )
    target_role = db.Column(
        db.Enum('all', 'student', 'teacher'),
        default='all'
    )
    is_pinned = db.Column(db.Boolean, default=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    expires_at = db.Column(db.DateTime, nullable=True)

    author = db.relationship('User', backref='notices', lazy=True)

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        return utc_now_naive() > self.expires_at

    def __repr__(self):
        return f'<Notice {self.title[:30]}>'
