from extensions import db
from utils.time import utc_now_naive


class SubAdminPermission(db.Model):
    __tablename__ = 'sub_admin_permissions'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'user_id', 'module', name='uq_sub_admin_perm'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    module = db.Column(db.String(50), nullable=False)
    can_view = db.Column(db.Boolean, default=False, nullable=False)
    can_edit = db.Column(db.Boolean, default=False, nullable=False)
    can_delete = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now_naive)

    user = db.relationship('User', backref='sub_admin_permissions', lazy=True)
