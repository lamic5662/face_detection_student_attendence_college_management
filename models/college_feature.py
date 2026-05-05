from extensions import db
from utils.time import utc_now_naive


class CollegeFeatureAccess(db.Model):
    __tablename__ = 'college_feature_access'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'feature_key', name='uq_college_feature_access'),
        db.Index('ix_college_feature_access_college_enabled', 'college_id', 'enabled'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    feature_key = db.Column(db.String(64), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return f'<CollegeFeatureAccess {self.college_id}:{self.feature_key}={self.enabled}>'
