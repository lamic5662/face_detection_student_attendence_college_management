from extensions import db
from utils.time import utc_now_naive


class PlatformAuditRead(db.Model):
    __tablename__ = 'platform_audit_reads'
    __table_args__ = (
        db.UniqueConstraint('audit_log_id', 'user_id', name='uq_platform_audit_read_log_user'),
        db.Index('ix_platform_audit_reads_user_dismissed', 'user_id', 'dismissed_at'),
        db.Index('ix_platform_audit_reads_user_log', 'user_id', 'audit_log_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    audit_log_id = db.Column(db.Integer, db.ForeignKey('platform_audit_logs.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    read_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    dismissed_at = db.Column(db.DateTime, nullable=True)

    audit_log = db.relationship(
        'PlatformAuditLog',
        backref=db.backref('read_receipts', cascade='all, delete-orphan', lazy='select'),
    )
    user = db.relationship(
        'User',
        backref=db.backref('platform_audit_reads', cascade='all, delete-orphan', lazy='select'),
    )
