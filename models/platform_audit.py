import json

from extensions import db
from utils.time import utc_now_naive


class PlatformAuditLog(db.Model):
    __tablename__ = 'platform_audit_logs'
    __table_args__ = (
        db.Index('ix_platform_audit_logs_created_at', 'created_at'),
        db.Index('ix_platform_audit_logs_college_created', 'college_id', 'created_at'),
        db.Index('ix_platform_audit_logs_action_created', 'action_key', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=True, index=True)
    action_key = db.Column(db.String(80), nullable=False)
    target_type = db.Column(db.String(80), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    summary = db.Column(db.String(255), nullable=False)
    detail_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    actor = db.relationship('User', foreign_keys=[actor_user_id], lazy=True)
    college = db.relationship('College', foreign_keys=[college_id], lazy=True)

    def get_details(self):
        if not self.detail_json:
            return {}
        try:
            details = json.loads(self.detail_json)
        except (TypeError, ValueError):
            return {}
        return details if isinstance(details, dict) else {}

    def set_details(self, details):
        self.detail_json = json.dumps(details) if details else None

    def __repr__(self):
        return f'<PlatformAuditLog {self.action_key} #{self.id}>'
