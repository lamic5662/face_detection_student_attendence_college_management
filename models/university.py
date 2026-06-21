from extensions import db
from utils.time import utc_now_naive


class University(db.Model):
    __tablename__ = 'universities'
    __table_args__ = (
        db.UniqueConstraint('code', name='uq_universities_code'),
        db.UniqueConstraint('name', name='uq_universities_name'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(30), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    colleges = db.relationship('College', backref='university', lazy=True)

    def __repr__(self):
        return f'<University {self.code}>'
