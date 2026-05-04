from extensions import db
from utils.time import utc_now_naive


class IDCardTemplate(db.Model):
    __tablename__ = 'id_card_templates'

    id                      = db.Column(db.Integer, primary_key=True)
    logo_path               = db.Column(db.String(255), nullable=True)
    principal_name          = db.Column(db.String(100), nullable=True)
    principal_title         = db.Column(db.String(100), default='Principal')
    principal_signature_path = db.Column(db.String(255), nullable=True)
    college_phone           = db.Column(db.String(30), nullable=True)
    college_website         = db.Column(db.String(200), nullable=True)
    card_color              = db.Column(db.String(20), default='#1e3a5f')
    accent_color            = db.Column(db.String(20), default='#e63946')
    valid_years             = db.Column(db.Integer, default=4)
    map_lat                 = db.Column(db.Float, nullable=True)
    map_lng                 = db.Column(db.Float, nullable=True)
    college_image_path      = db.Column(db.String(255), nullable=True)
    updated_at              = db.Column(db.DateTime, default=utc_now_naive,
                                        onupdate=utc_now_naive)

    @staticmethod
    def get():
        row = IDCardTemplate.query.first()
        if not row:
            row = IDCardTemplate()
            db.session.add(row)
            db.session.commit()
        return row


class StudentIDCard(db.Model):
    __tablename__ = 'student_id_cards'

    id              = db.Column(db.Integer, primary_key=True)
    student_id      = db.Column(db.Integer, db.ForeignKey('students.id'),
                                unique=True, nullable=False)
    photo_path      = db.Column(db.String(255), nullable=True)
    card_number     = db.Column(db.String(50), unique=True, nullable=True)
    status          = db.Column(
                        db.Enum('pending', 'approved', 'rejected'),
                        default='pending', nullable=False)
    rejection_note  = db.Column(db.Text, nullable=True)
    submitted_at    = db.Column(db.DateTime, default=utc_now_naive)
    reviewed_at     = db.Column(db.DateTime, nullable=True)
    reviewed_by     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    student  = db.relationship('Student',
                               backref=db.backref('id_card', uselist=False))
    reviewer = db.relationship('User', foreign_keys=[reviewed_by],
                               backref='reviewed_id_cards')
