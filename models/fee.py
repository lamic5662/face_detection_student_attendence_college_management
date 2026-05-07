from extensions import db
from utils.time import utc_now_naive, utc_today
from datetime import date as _date


class FeeStructure(db.Model):
    __tablename__ = 'fee_structures'
    __table_args__ = (
        db.Index(
            'ix_fee_structures_college_department_semester_year',
            'college_id', 'department_id', 'semester', 'academic_year'
        ),
        db.Index('ix_fee_structures_college_active_due', 'college_id', 'is_active', 'due_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    semester = db.Column(db.Integer, nullable=True)
    academic_year = db.Column(db.String(10), nullable=False)   # e.g. "2024-25"
    amount = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    description = db.Column(db.String(300), nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    department = db.relationship('Department', backref='fee_structures', lazy=True)
    payments = db.relationship('FeePayment', backref='fee_structure', lazy=True,
                               cascade='all, delete-orphan')

    def __repr__(self):
        return f'<FeeStructure {self.title}>'


class FeePayment(db.Model):
    __tablename__ = 'fee_payments'

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    fee_structure_id = db.Column(db.Integer, db.ForeignKey('fee_structures.id'), nullable=False)
    amount_paid = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False, default=utc_today)
    transaction_id = db.Column(db.String(100), nullable=True)
    payment_method = db.Column(
        db.Enum('cash', 'bank_transfer', 'online', 'cheque'),
        default='cash'
    )
    status = db.Column(db.Enum('paid', 'partial', 'waived'), default='paid')
    receipt_no = db.Column(db.String(50), nullable=True)
    remarks = db.Column(db.String(200), nullable=True)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive)

    student = db.relationship('Student', backref='fee_payments', lazy=True)
    recorded_by_user = db.relationship('User', backref='fee_payments_recorded', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('student_id', 'fee_structure_id', name='uq_fee_payment'),
        db.UniqueConstraint('college_id', 'receipt_no', name='uq_fee_payments_college_receipt_no'),
        db.Index('ix_fee_payments_college_student_status', 'college_id', 'student_id', 'status'),
        db.Index('ix_fee_payments_college_structure_status', 'college_id', 'fee_structure_id', 'status'),
    )

    def __repr__(self):
        return f'<FeePayment student={self.student_id} structure={self.fee_structure_id}>'


class FeeReminderConfig(db.Model):
    """Per-college config for automated fee reminder emails."""
    __tablename__ = 'fee_reminder_configs'

    id         = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, unique=True)

    enabled            = db.Column(db.Boolean, default=False, nullable=False)
    days_before_due    = db.Column(db.Integer, default=7,    nullable=False)  # remind X days before
    remind_on_due_date = db.Column(db.Boolean, default=True, nullable=False)  # also remind on due day
    remind_overdue     = db.Column(db.Boolean, default=True, nullable=False)  # remind for overdue fees
    send_hour          = db.Column(db.Integer, default=8,    nullable=False)  # 0-23

    last_sent_at = db.Column(db.DateTime, nullable=True)
    updated_by   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at   = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    @property
    def send_hour_display(self) -> str:
        return f'{self.send_hour:02d}:00'
