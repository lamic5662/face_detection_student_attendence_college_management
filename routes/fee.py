from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from extensions import db
from models.fee import FeeStructure, FeePayment
from models.student import Student
from models.department import Department
from utils.decorators import admin_required, student_required
from datetime import date, datetime
import random, string

fee_bp = Blueprint('fee', __name__)


def _generate_receipt():
    return 'RCT-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


# ── Admin ─────────────────────────────────────────────────────────────────────

@fee_bp.route('/admin/fees')
@login_required
@admin_required
def admin_fees():
    page       = request.args.get('page', 1, type=int)
    dept_id    = request.args.get('department_id', type=int)
    year       = request.args.get('year', '')
    departments = Department.query.order_by(Department.name).all()

    query = FeeStructure.query
    if dept_id:
        query = query.filter(db.or_(
            FeeStructure.department_id == dept_id,
            FeeStructure.department_id == None
        ))
    if year:
        query = query.filter_by(academic_year=year)

    pagination = query.order_by(FeeStructure.academic_year.desc(), FeeStructure.id.desc()).paginate(
        page=page, per_page=15, error_out=False
    )
    years = db.session.query(FeeStructure.academic_year).distinct().all()
    return render_template('fee/admin_structures.html',
                           pagination=pagination, structures=pagination.items,
                           departments=departments,
                           years=[y[0] for y in years],
                           selected_dept=dept_id, selected_year=year,
                           today=date.today())


@fee_bp.route('/admin/fees/create', methods=['POST'])
@login_required
@admin_required
def create_structure():
    title       = request.form.get('title', '').strip()
    dept_id     = request.form.get('department_id', type=int) or None
    semester    = request.form.get('semester', type=int) or None
    year        = request.form.get('academic_year', '').strip()
    amount      = request.form.get('amount', type=float)
    due_date_s  = request.form.get('due_date', '')
    description = request.form.get('description', '').strip()

    if not title or not year or not amount:
        flash('Title, academic year, and amount are required.', 'danger')
        return redirect(url_for('fee.admin_fees'))

    if due_date_s:
        try:
            due = date.fromisoformat(due_date_s)
        except ValueError:
            flash('Invalid due date.', 'danger')
            return redirect(url_for('fee.admin_fees'))
    else:
        due = None
    fs = FeeStructure(title=title, department_id=dept_id, semester=semester,
                      academic_year=year, amount=amount, due_date=due,
                      description=description)
    db.session.add(fs)
    db.session.commit()
    flash(f'Fee structure "{title}" created.', 'success')
    return redirect(url_for('fee.admin_fees'))


@fee_bp.route('/admin/fees/<int:fid>/delete', methods=['POST'])
@login_required
@admin_required
def delete_structure(fid):
    fs = FeeStructure.query.get_or_404(fid)
    db.session.delete(fs)
    db.session.commit()
    flash('Fee structure deleted.', 'info')
    return redirect(url_for('fee.admin_fees'))


@fee_bp.route('/admin/fees/<int:fid>/payments')
@login_required
@admin_required
def structure_payments(fid):
    fs = FeeStructure.query.get_or_404(fid)
    page = request.args.get('page', 1, type=int)
    dept_id  = request.args.get('department_id', type=int)
    semester = request.args.get('semester', type=int)
    departments = Department.query.order_by(Department.name).all()

    # All relevant students
    student_q = Student.query
    if fs.department_id:
        student_q = student_q.filter_by(department_id=fs.department_id)
    elif dept_id:
        student_q = student_q.filter_by(department_id=dept_id)
    if fs.semester:
        student_q = student_q.filter_by(semester=fs.semester)
    elif semester:
        student_q = student_q.filter_by(semester=semester)

    all_students = student_q.order_by(Student.roll_number).all()
    paid_map = {p.student_id: p for p in FeePayment.query.filter_by(fee_structure_id=fid).all()}

    students_data = []
    for s in all_students:
        students_data.append({
            'student': s,
            'payment': paid_map.get(s.id),
        })

    paid_total = sum(p.amount_paid for p in paid_map.values())
    return render_template('fee/payments.html',
                           fs=fs, students_data=students_data,
                           paid_total=paid_total,
                           total_expected=fs.amount * len(all_students),
                           departments=departments,
                           selected_dept=dept_id, selected_sem=semester,
                           today=date.today())


@fee_bp.route('/admin/fees/<int:fid>/record', methods=['POST'])
@login_required
@admin_required
def record_payment(fid):
    fs = FeeStructure.query.get_or_404(fid)
    student_id     = request.form.get('student_id', type=int)
    amount_paid    = request.form.get('amount_paid', type=float)
    method         = request.form.get('payment_method', 'cash')
    transaction_id = request.form.get('transaction_id', '').strip() or None
    remarks        = request.form.get('remarks', '').strip() or None
    payment_date_s = request.form.get('payment_date', '')
    status         = request.form.get('status', 'paid')

    if not student_id or not amount_paid:
        flash('Student and amount are required.', 'danger')
        return redirect(url_for('fee.structure_payments', fid=fid))

    existing = FeePayment.query.filter_by(
        student_id=student_id, fee_structure_id=fid
    ).first()
    if payment_date_s:
        try:
            pdate = date.fromisoformat(payment_date_s)
        except ValueError:
            flash('Invalid payment date.', 'danger')
            return redirect(url_for('fee.structure_payments', fid=fid))
    else:
        pdate = date.today()

    if existing:
        existing.amount_paid    = amount_paid
        existing.payment_method = method
        existing.transaction_id = transaction_id
        existing.remarks        = remarks
        existing.payment_date   = pdate
        existing.status         = status
        existing.recorded_by    = current_user.id
    else:
        payment = FeePayment(
            student_id=student_id, fee_structure_id=fid,
            amount_paid=amount_paid, payment_method=method,
            transaction_id=transaction_id, remarks=remarks,
            payment_date=pdate, status=status,
            receipt_no=_generate_receipt(),
            recorded_by=current_user.id
        )
        db.session.add(payment)

    db.session.commit()
    flash('Payment recorded.', 'success')
    return redirect(url_for('fee.structure_payments', fid=fid))


# ── Student ───────────────────────────────────────────────────────────────────

@fee_bp.route('/student/fees')
@login_required
@student_required
def student_fees():
    student = current_user.student_profile
    structures = FeeStructure.query.filter(
        db.or_(
            FeeStructure.department_id == student.department_id,
            FeeStructure.department_id == None
        ),
        db.or_(
            FeeStructure.semester == student.semester,
            FeeStructure.semester == None
        ),
        FeeStructure.is_active == True
    ).order_by(FeeStructure.academic_year.desc()).all()

    paid_map = {p.fee_structure_id: p for p in
                FeePayment.query.filter_by(student_id=student.id).all()}

    fee_data = []
    total_due = total_paid = 0
    for fs in structures:
        payment = paid_map.get(fs.id)
        paid = payment.amount_paid if payment else 0
        due  = max(fs.amount - paid, 0)
        total_due  += due
        total_paid += paid
        fee_data.append({'structure': fs, 'payment': payment, 'paid': paid, 'due': due})

    return render_template('fee/student_view.html',
                           fee_data=fee_data,
                           total_due=total_due,
                           total_paid=total_paid,
                           today=date.today())
