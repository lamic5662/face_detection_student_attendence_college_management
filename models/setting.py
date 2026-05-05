from extensions import db
from utils.time import utc_now_naive


class CollegeSetting(db.Model):
    __tablename__ = 'college_settings'

    id           = db.Column(db.Integer, primary_key=True)
    college_id   = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, unique=True, index=True)
    college_name = db.Column(db.String(200), nullable=False, default='My College')
    address      = db.Column(db.String(500), nullable=True)
    latitude     = db.Column(db.Float, nullable=True)
    longitude    = db.Column(db.Float, nullable=True)
    updated_at   = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    # Digital signatures
    principal_name      = db.Column(db.String(100), nullable=True)
    principal_sign_path = db.Column(db.String(255), nullable=True)
    hod_name            = db.Column(db.String(100), nullable=True)
    hod_sign_path       = db.Column(db.String(255), nullable=True)
    class_teacher_name  = db.Column(db.String(100), nullable=True)
    class_teacher_sign_path = db.Column(db.String(255), nullable=True)

    college = db.relationship('College', backref=db.backref('setting', uselist=False))

    @staticmethod
    def get(college=None):
        """Return the settings row for the current college, creating it if needed."""
        from flask import has_request_context

        from models.college import College

        resolved_college = college
        if resolved_college is None and has_request_context():
            from utils.tenancy import get_current_college

            resolved_college = get_current_college(optional=True)
        if resolved_college is None:
            resolved_college = College.ensure_default()

        row = CollegeSetting.query.filter_by(college_id=resolved_college.id).first()
        if not row:
            row = CollegeSetting(
                college_id=resolved_college.id,
                college_name=resolved_college.name,
            )
            db.session.add(row)
            db.session.commit()
        return row
