from extensions import db
from utils.time import utc_now_naive


class UserNotification(db.Model):
    __tablename__ = 'user_notifications'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'source_key', name='uq_user_notifications_user_source'),
        db.Index('ix_user_notifications_college_user_created', 'college_id', 'user_id', 'created_at'),
        db.Index('ix_user_notifications_college_user_dismissed', 'college_id', 'user_id', 'dismissed_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(
        db.Enum('general', 'exam', 'holiday', 'event', 'fee', 'urgent'),
        nullable=False,
        default='general',
    )
    action_url = db.Column(db.String(255), nullable=True)
    source_key = db.Column(db.String(120), nullable=True)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    read_at = db.Column(db.DateTime, nullable=True)
    dismissed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref=db.backref('private_notifications', lazy='dynamic'))

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_read(self) -> None:
        if self.read_at is None:
            self.read_at = utc_now_naive()

    def __repr__(self):
        return f'<UserNotification {self.user_id}:{self.title[:30]}>'
