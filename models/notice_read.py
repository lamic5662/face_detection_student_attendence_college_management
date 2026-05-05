from extensions import db
from utils.time import utc_now_naive


class NoticeRead(db.Model):
    __tablename__ = 'notice_reads'
    __table_args__ = (
        db.UniqueConstraint('notice_id', 'user_id', name='uq_notice_read_notice_user'),
        db.Index('ix_notice_reads_college_user_dismissed', 'college_id', 'user_id', 'dismissed_at'),
        db.Index('ix_notice_reads_college_notice', 'college_id', 'notice_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    notice_id = db.Column(db.Integer, db.ForeignKey('notices.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    read_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    dismissed_at = db.Column(db.DateTime, nullable=True)

    notice = db.relationship(
        'Notice',
        backref=db.backref('read_receipts', cascade='all, delete-orphan', lazy='select'),
    )
    user = db.relationship(
        'User',
        backref=db.backref('notice_reads', cascade='all, delete-orphan', lazy='select'),
    )
