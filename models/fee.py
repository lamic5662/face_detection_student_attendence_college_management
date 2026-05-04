from extensions import db
from utils.time import utc_now_naive, utc_today


class FeeStructure(db.Model):
    __tablename__ = 'fee_structures'

    id = db.Column(db.Integer, primary_key=True)
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
    )

    def __repr__(self):
        return f'<FeePayment student={self.student_id} structure={self.fee_structure_id}>'
