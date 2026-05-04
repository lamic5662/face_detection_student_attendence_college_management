from extensions import db
from utils.time import utc_now_naive


class CollegeSetting(db.Model):
    __tablename__ = 'college_settings'

    id           = db.Column(db.Integer, primary_key=True)
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

    @staticmethod
    def get():
        """Return the single settings row, creating it if it doesn't exist."""
        row = CollegeSetting.query.first()
        if not row:
            row = CollegeSetting()
            db.session.add(row)
            db.session.commit()
        return row
