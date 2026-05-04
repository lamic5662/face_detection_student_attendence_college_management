from extensions import db
from utils.time import utc_now_naive


class StudentLocation(db.Model):
    __tablename__ = 'student_locations'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'),
                           unique=True, nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    accuracy = db.Column(db.Float, nullable=True)   # metres
    is_sharing = db.Column(db.Boolean, default=False, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    # Date of last "arrived at college" notification — prevents duplicate emails per day
    last_arrival_date = db.Column(db.Date, nullable=True)

    student = db.relationship('Student', backref=db.backref('location', uselist=False))
