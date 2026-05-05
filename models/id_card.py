import os
import shutil

from flask import current_app, has_app_context

from extensions import db
from utils.time import utc_now_naive


class IDCardTemplate(db.Model):
    __tablename__ = 'id_card_templates'

    id                      = db.Column(db.Integer, primary_key=True)
    college_id              = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, unique=True, index=True)
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

    college = db.relationship('College', backref=db.backref('id_card_template', uselist=False))

    @staticmethod
    def _asset_relpath(college, filename):
        college_slug = getattr(college, 'code', None) or f'college-{college.id}'
        return f"uploads/id_templates/{college_slug.lower()}/{filename}"

    def _migrate_legacy_assets(self, college):
        if not has_app_context():
            return

        legacy_names = {
            'logo_path': 'logo.png',
            'principal_signature_path': 'signature.png',
            'college_image_path': 'college_image.jpg',
        }
        updated = False

        for field_name, filename in legacy_names.items():
            rel_path = getattr(self, field_name)
            if rel_path != f'uploads/id_templates/{filename}':
                continue

            source_path = os.path.join(current_app.root_path, 'static', rel_path)
            if not os.path.isfile(source_path):
                continue

            new_rel_path = self._asset_relpath(college, filename)
            target_path = os.path.join(current_app.root_path, 'static', new_rel_path)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(source_path, target_path)
            setattr(self, field_name, new_rel_path)
            updated = True

        if updated:
            db.session.commit()

    @staticmethod
    def get(college=None):
        from flask import has_request_context

        from models.college import College

        resolved_college = college
        if resolved_college is None and has_request_context():
            from utils.tenancy import get_current_college

            resolved_college = get_current_college(optional=True)
        if resolved_college is None:
            resolved_college = College.ensure_default()

        row = IDCardTemplate.query.filter_by(college_id=resolved_college.id).first()
        if not row:
            row = IDCardTemplate(college_id=resolved_college.id)
            db.session.add(row)
            db.session.commit()
        row._migrate_legacy_assets(resolved_college)
        return row


class StudentIDCard(db.Model):
    __tablename__ = 'student_id_cards'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'card_number', name='uq_student_id_cards_college_card_number'),
        db.Index('ix_student_id_cards_college_status_submitted', 'college_id', 'status', 'submitted_at'),
    )

    id              = db.Column(db.Integer, primary_key=True)
    college_id      = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    student_id      = db.Column(db.Integer, db.ForeignKey('students.id'),
                                unique=True, nullable=False)
    photo_path      = db.Column(db.String(255), nullable=True)
    card_number     = db.Column(db.String(50), nullable=True)
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
