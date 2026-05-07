"""
Fee reminder email service.
Sends consolidated fee due / overdue reminders to students and parents.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from flask_mail import Message

from extensions import db, mail

logger = logging.getLogger(__name__)


def _amount_due(student_id: int, fs) -> float:
    from models.fee import FeePayment
    payment = FeePayment.query.filter_by(
        student_id=student_id, fee_structure_id=fs.id
    ).first()
    paid = payment.amount_paid if payment else 0.0
    return max(fs.amount - paid, 0.0)


def _fee_status_label(due_date: date, today: date) -> tuple[str, str]:
    """Returns (label, color) for email."""
    delta = (due_date - today).days
    if delta < 0:
        return f'{abs(delta)} day{"s" if abs(delta) != 1 else ""} overdue', '#dc3545'
    if delta == 0:
        return 'Due today', '#fd7e14'
    return f'Due in {delta} day{"s" if delta != 1 else ""}', '#0d6efd'


def _build_student_email(student, college_name: str, due_fees: list[dict]) -> str:
    rows_html = ''
    for item in due_fees:
        fs        = item['structure']
        amount    = item['amount_due']
        label, color = _fee_status_label(fs.due_date, date.today())
        rows_html += f"""
        <tr>
          <td style="padding:10px;border:1px solid #dee2e6">{fs.title}</td>
          <td style="padding:10px;border:1px solid #dee2e6;text-align:right">
            Rs. {amount:,.0f}
          </td>
          <td style="padding:10px;border:1px solid #dee2e6;text-align:center">
            {fs.due_date.strftime('%d %b %Y')}
          </td>
          <td style="padding:10px;border:1px solid #dee2e6;text-align:center;
                     color:{color};font-weight:bold">{label}</td>
        </tr>"""

    total_due = sum(i['amount_due'] for i in due_fees)
    overdue   = [i for i in due_fees if i['structure'].due_date < date.today()]
    overdue_block = ''
    if overdue:
        overdue_block = f"""
        <div style="background:#fff3cd;border-left:4px solid #ffc107;padding:14px 18px;
                    margin-top:20px;border-radius:4px">
          <strong>⚠️ {len(overdue)} overdue fee{"s" if len(overdue) != 1 else ""}.</strong>
          Please clear outstanding dues immediately to avoid penalties.
        </div>"""

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;
                border:1px solid #ddd;border-radius:8px;overflow:hidden">
      <div style="background:#0d6efd;padding:22px 28px;color:#fff">
        <h2 style="margin:0;font-size:20px">💳 Fee Reminder</h2>
        <p style="margin:6px 0 0 0;opacity:.85;font-size:13px">{college_name}</p>
      </div>
      <div style="padding:28px">
        <p>Dear <strong>{student.user.name}</strong>,</p>
        <p>This is a reminder about the following outstanding fee(s):</p>
        <table style="width:100%;border-collapse:collapse;margin-top:12px">
          <thead>
            <tr style="background:#f8f9fa">
              <th style="padding:10px;border:1px solid #dee2e6;text-align:left">Fee</th>
              <th style="padding:10px;border:1px solid #dee2e6;text-align:right">Amount Due</th>
              <th style="padding:10px;border:1px solid #dee2e6;text-align:center">Due Date</th>
              <th style="padding:10px;border:1px solid #dee2e6;text-align:center">Status</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
          <tfoot>
            <tr style="background:#f8f9fa;font-weight:bold">
              <td colspan="1" style="padding:10px;border:1px solid #dee2e6">Total Outstanding</td>
              <td style="padding:10px;border:1px solid #dee2e6;text-align:right;color:#dc3545">
                Rs. {total_due:,.0f}
              </td>
              <td colspan="2" style="border:1px solid #dee2e6"></td>
            </tr>
          </tfoot>
        </table>
        {overdue_block}
        <p style="margin-top:20px;font-size:13px;color:#6c757d">
          Please visit the college office or contact your administrator to clear the dues.
        </p>
      </div>
      <div style="background:#f8f9fa;padding:14px 28px;font-size:12px;
                  color:#6c757d;text-align:center">
        {college_name} — Smart Attendance System &bull; This is an automated reminder.
      </div>
    </div>"""


def _build_parent_email(parent_name: str, child_name: str, college_name: str,
                        due_fees: list[dict]) -> str:
    total_due = sum(i['amount_due'] for i in due_fees)
    fee_list  = ''.join(
        f'<li><strong>{i["structure"].title}</strong> — Rs. {i["amount_due"]:,.0f} '
        f'(due {i["structure"].due_date.strftime("%d %b %Y")})</li>'
        for i in due_fees
    )
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;
                border:1px solid #ddd;border-radius:8px;overflow:hidden">
      <div style="background:#fd7e14;padding:22px 28px;color:#fff">
        <h2 style="margin:0;font-size:20px">💳 Fee Due — Action Required</h2>
        <p style="margin:6px 0 0 0;opacity:.85;font-size:13px">{college_name}</p>
      </div>
      <div style="padding:28px">
        <p>Dear <strong>{parent_name}</strong>,</p>
        <p>Your child <strong>{child_name}</strong> has outstanding fees totalling
           <strong>Rs. {total_due:,.0f}</strong>:</p>
        <ul style="padding-left:20px;line-height:2">{fee_list}</ul>
        <p style="font-size:13px;color:#6c757d">
          Please ensure payment is made on time to avoid academic disruptions.
        </p>
      </div>
      <div style="background:#f8f9fa;padding:14px 28px;font-size:12px;
                  color:#6c757d;text-align:center">
        {college_name} — Smart Attendance System
      </div>
    </div>"""


def _get_due_fees(student, cfg, today: date) -> list[dict]:
    """Return list of fee structures where student owes money and reminder should fire today."""
    from models.fee import FeeStructure

    structures = FeeStructure.query.filter(
        FeeStructure.college_id == student.college_id,
        FeeStructure.is_active == True,
        FeeStructure.due_date != None,
        db.or_(
            FeeStructure.department_id == student.department_id,
            FeeStructure.department_id == None,
        ),
        db.or_(
            FeeStructure.semester == student.semester,
            FeeStructure.semester == None,
        ),
    ).all()

    window_start = today - timedelta(days=1) if cfg.remind_overdue else today
    due_fees = []

    for fs in structures:
        amount = _amount_due(student.id, fs)
        if amount <= 0:
            continue  # fully paid

        days_until = (fs.due_date - today).days

        # upcoming reminder window
        if 0 < days_until <= cfg.days_before_due:
            due_fees.append({'structure': fs, 'amount_due': amount})
        # due today
        elif days_until == 0 and cfg.remind_on_due_date:
            due_fees.append({'structure': fs, 'amount_due': amount})
        # overdue
        elif days_until < 0 and cfg.remind_overdue:
            due_fees.append({'structure': fs, 'amount_due': amount})

    return due_fees


def run_fee_reminders(app, college_id: int | None = None) -> dict:
    """
    Send fee reminders for all (or one) college.
    Returns {sent, parent_alerts, skipped, errors}.
    """
    with app.app_context():
        from models.college import College
        from models.student import Student
        from models.fee import FeeReminderConfig
        from models.parent import ParentStudent
        from models.user import User

        today = date.today()
        colleges = (
            [College.query.get(college_id)] if college_id
            else College.query.filter_by(is_active=True).all()
        )

        sent = parent_alerts = skipped = errors = 0

        for college in colleges:
            if not college:
                continue

            cfg = FeeReminderConfig.query.filter_by(college_id=college.id).first()
            if not cfg or not cfg.enabled:
                continue

            students = Student.query.filter_by(college_id=college.id).all()

            for student in students:
                if not student.user or not student.user.email:
                    skipped += 1
                    continue

                due_fees = _get_due_fees(student, cfg, today)
                if not due_fees:
                    skipped += 1
                    continue

                try:
                    html = _build_student_email(student, college.name, due_fees)
                    msg = Message(
                        subject=f'Fee Reminder — {len(due_fees)} fee(s) due — {college.name}',
                        recipients=[student.user.email],
                        html=html,
                    )
                    mail.send(msg)
                    sent += 1
                    logger.info(f'Fee reminder sent to {student.user.email}')
                except Exception as exc:
                    logger.error(f'Fee reminder failed for {student.user.email}: {exc}')
                    errors += 1
                    continue

                # Notify parents
                links = ParentStudent.query.filter_by(
                    student_id=student.id, college_id=college.id).all()
                for link in links:
                    parent_user = User.query.get(link.parent_id)
                    if not parent_user or not parent_user.email:
                        continue
                    try:
                        html_p = _build_parent_email(
                            parent_user.name, student.user.name, college.name, due_fees)
                        msg_p = Message(
                            subject=f'[Fee Due] {student.user.name} — {college.name}',
                            recipients=[parent_user.email],
                            html=html_p,
                        )
                        mail.send(msg_p)
                        parent_alerts += 1
                    except Exception as exc:
                        logger.error(f'Parent fee alert failed for {parent_user.email}: {exc}')

        logger.info(f'Fee reminders: {sent} sent, {parent_alerts} parent alerts, '
                    f'{skipped} skipped, {errors} errors')
        return {'sent': sent, 'parent_alerts': parent_alerts,
                'skipped': skipped, 'errors': errors}


def check_and_send_fee_reminders(app) -> None:
    """
    Runs every hour. Fires for each college whose reminder is enabled,
    current hour matches send_hour, and hasn't sent today yet.
    """
    with app.app_context():
        from models.fee import FeeReminderConfig
        from utils.time import utc_now_naive

        now   = datetime.now()
        today = now.date()

        configs = FeeReminderConfig.query.filter_by(enabled=True).all()
        for cfg in configs:
            if cfg.send_hour != now.hour:
                continue
            if cfg.last_sent_at and cfg.last_sent_at.date() == today:
                logger.info(f'Fee reminder already sent today for college {cfg.college_id}')
                continue

            logger.info(f'Auto fee reminder for college {cfg.college_id}')
            try:
                result = run_fee_reminders(app, college_id=cfg.college_id)
                cfg.last_sent_at = utc_now_naive()
                db.session.commit()
                logger.info(f'Auto fee reminder college {cfg.college_id}: {result}')
            except Exception as exc:
                logger.error(f'Auto fee reminder failed college {cfg.college_id}: {exc}')
