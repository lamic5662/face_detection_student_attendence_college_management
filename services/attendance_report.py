"""
Weekly attendance report emailer.
Sends each student their subject-wise attendance summary.
Sends parents a warning email if any subject is below threshold.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from flask import current_app
from flask_mail import Message

from extensions import db, mail

logger = logging.getLogger(__name__)


def _week_bounds(ref: date | None = None) -> tuple[date, date]:
    ref = ref or date.today()
    week_end   = ref - timedelta(days=ref.weekday() + 1)   # last Sunday
    week_start = week_end - timedelta(days=6)               # last Monday
    return week_start, week_end


def _subject_attendance(student, subject_id: int, week_start: date, week_end: date):
    from models.attendance import AttendanceRecord, AttendanceSession
    base = (
        AttendanceRecord.query
        .join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id)
        .filter(
            AttendanceRecord.student_id == student.id,
            AttendanceSession.subject_id == subject_id,
            AttendanceSession.status == 'completed',
        )
    )
    total_all   = base.count()
    present_all = base.filter(AttendanceRecord.status == 'present').count()

    week = base.filter(
        AttendanceSession.date >= week_start,
        AttendanceSession.date <= week_end,
    )
    total_week   = week.count()
    present_week = week.filter(AttendanceRecord.status == 'present').count()

    overall_pct = round(present_all / total_all * 100, 1) if total_all else 100.0
    week_pct    = round(present_week / total_week * 100, 1) if total_week else None

    return {
        'total_all':    total_all,
        'present_all':  present_all,
        'overall_pct':  overall_pct,
        'total_week':   total_week,
        'present_week': present_week,
        'week_pct':     week_pct,
    }


def _pct_color(pct: float, threshold: int) -> str:
    if pct >= threshold:
        return '#198754'
    if pct >= threshold - 10:
        return '#fd7e14'
    return '#dc3545'


def _build_student_email(student, college_name: str, threshold: int,
                         week_start: date, week_end: date) -> tuple[str, list[dict]]:
    from models.subject import Subject
    subjects = Subject.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester,
    ).order_by(Subject.name).all()

    rows = []
    low_subjects = []

    table_rows_html = ''
    for subj in subjects:
        data = _subject_attendance(student, subj.id, week_start, week_end)
        rows.append({'subject': subj, **data})

        week_cell = (
            f"{data['present_week']}/{data['total_week']} ({data['week_pct']}%)"
            if data['total_week'] else '—'
        )
        color = _pct_color(data['overall_pct'], threshold)
        warn  = ' ⚠️' if data['overall_pct'] < threshold else ''
        if data['overall_pct'] < threshold:
            low_subjects.append({'name': subj.name, 'pct': data['overall_pct']})

        table_rows_html += f"""
        <tr>
          <td style="padding:10px;border:1px solid #dee2e6">{subj.name}</td>
          <td style="padding:10px;border:1px solid #dee2e6;text-align:center">{week_cell}</td>
          <td style="padding:10px;border:1px solid #dee2e6;text-align:center;
                     color:{color};font-weight:bold">{data['overall_pct']}%{warn}</td>
        </tr>"""

    warning_block = ''
    if low_subjects:
        items = ''.join(f'<li><strong>{s["name"]}</strong>: {s["pct"]}%</li>' for s in low_subjects)
        warning_block = f"""
        <div style="background:#fff3cd;border-left:4px solid #ffc107;padding:14px 18px;
                    margin-top:20px;border-radius:4px">
          <strong>⚠️ Below {threshold}% threshold:</strong>
          <ul style="margin:8px 0 0 0">{items}</ul>
          <p style="margin:8px 0 0 0;font-size:13px;color:#856404">
            Please attend classes regularly to avoid academic consequences.
          </p>
        </div>"""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;
                border:1px solid #ddd;border-radius:8px;overflow:hidden">
      <div style="background:#0d6efd;padding:22px 28px;color:#fff">
        <h2 style="margin:0;font-size:20px">📊 Weekly Attendance Report</h2>
        <p style="margin:6px 0 0 0;opacity:.85;font-size:13px">
          {week_start.strftime('%d %b')} – {week_end.strftime('%d %b, %Y')}
        </p>
      </div>
      <div style="padding:28px">
        <p>Dear <strong>{student.user.name}</strong>,</p>
        <p>Here is your attendance summary for <strong>{college_name}</strong>:</p>
        <table style="width:100%;border-collapse:collapse;margin-top:12px">
          <thead>
            <tr style="background:#f8f9fa">
              <th style="padding:10px;border:1px solid #dee2e6;text-align:left">Subject</th>
              <th style="padding:10px;border:1px solid #dee2e6;text-align:center">This Week</th>
              <th style="padding:10px;border:1px solid #dee2e6;text-align:center">Overall</th>
            </tr>
          </thead>
          <tbody>{table_rows_html}</tbody>
        </table>
        {warning_block}
      </div>
      <div style="background:#f8f9fa;padding:14px 28px;font-size:12px;color:#6c757d;text-align:center">
        {college_name} — Smart Attendance System &bull;
        This is an automated weekly report.
      </div>
    </div>"""

    return html, low_subjects


def _send_student_report(student, college_name: str, threshold: int,
                         week_start: date, week_end: date) -> list[dict]:
    try:
        html, low_subjects = _build_student_email(
            student, college_name, threshold, week_start, week_end)
        msg = Message(
            subject=f'Weekly Attendance Report — {week_start.strftime("%d %b")} to {week_end.strftime("%d %b, %Y")}',
            recipients=[student.user.email],
            html=html,
        )
        mail.send(msg)
        logger.info(f'Weekly report sent to {student.user.email}')
        return low_subjects
    except Exception as exc:
        logger.error(f'Failed to send weekly report to {student.user.email}: {exc}')
        return []


def _send_parent_alert(parent_user, child, college_name: str,
                       low_subjects: list[dict], threshold: int,
                       week_start: date, week_end: date) -> None:
    items_html = ''.join(
        f'<li><strong>{s["name"]}</strong>: {s["pct"]}% (required {threshold}%)</li>'
        for s in low_subjects
    )
    try:
        msg = Message(
            subject=f'[Parent Alert] Low Attendance — {child.user.name}',
            recipients=[parent_user.email],
            html=f"""
            <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;
                        border:1px solid #ddd;border-radius:8px;overflow:hidden">
              <div style="background:#dc3545;padding:22px 28px;color:#fff">
                <h2 style="margin:0;font-size:20px">⚠️ Low Attendance Warning</h2>
                <p style="margin:6px 0 0 0;opacity:.85;font-size:13px">
                  {week_start.strftime('%d %b')} – {week_end.strftime('%d %b, %Y')}
                </p>
              </div>
              <div style="padding:28px">
                <p>Dear Parent/Guardian,</p>
                <p>Your child <strong>{child.user.name}</strong> has attendance below the
                   required <strong>{threshold}%</strong> in the following subject(s):</p>
                <ul>{items_html}</ul>
                <p>Please encourage regular class attendance to avoid academic consequences.</p>
              </div>
              <div style="background:#f8f9fa;padding:14px 28px;font-size:12px;
                          color:#6c757d;text-align:center">
                {college_name} — Smart Attendance System
              </div>
            </div>""",
        )
        mail.send(msg)
        logger.info(f'Parent alert sent to {parent_user.email} for {child.user.name}')
    except Exception as exc:
        logger.error(f'Failed to send parent alert to {parent_user.email}: {exc}')


def run_weekly_reports(app, college_id: int | None = None,
                       department_ids: list[int] | None = None,
                       semesters: list[int] | None = None,
                       admission_years: list[int] | None = None) -> dict:
    """
    Main entry point. Call with an app context or from a scheduler.
    Filters narrow which students receive the report.
    Returns a summary dict: {sent: int, errors: int, parent_alerts: int}
    """
    with app.app_context():
        from models.college import College
        from models.student import Student
        from models.parent import ParentStudent
        from models.user import User

        week_start, week_end = _week_bounds()
        threshold = app.config.get('LOW_ATTENDANCE_THRESHOLD', 75)

        colleges = (
            [College.query.get(college_id)] if college_id
            else College.query.filter_by(is_active=True).all()
        )

        sent = errors = parent_alerts = 0

        for college in colleges:
            if not college:
                continue
            college_name = college.name

            q = Student.query.filter_by(college_id=college.id)

            if department_ids:
                q = q.filter(Student.department_id.in_(department_ids))
            if semesters:
                q = q.filter(Student.semester.in_(semesters))
            if admission_years:
                q = q.filter(Student.admission_year.in_(admission_years))

            students = q.all()
            for student in students:
                if not student.user or not student.user.email:
                    continue
                low_subjects = _send_student_report(
                    student, college_name, threshold, week_start, week_end)
                if low_subjects is not None:
                    sent += 1
                else:
                    errors += 1
                    continue

                if low_subjects:
                    links = ParentStudent.query.filter_by(
                        student_id=student.id, college_id=college.id).all()
                    for link in links:
                        parent_user = User.query.get(link.parent_id)
                        if parent_user and parent_user.email:
                            _send_parent_alert(
                                parent_user, student, college_name,
                                low_subjects, threshold, week_start, week_end)
                            parent_alerts += 1

        logger.info(f'Weekly reports done: {sent} students, {parent_alerts} parent alerts, {errors} errors')
        return {'sent': sent, 'errors': errors, 'parent_alerts': parent_alerts}


def check_and_run_scheduled_reports(app) -> None:
    """
    Runs every hour. For each college that has auto-reports enabled,
    checks whether current day+hour matches the configured schedule.
    Uses last_sent_at to prevent duplicate sends within the same day.
    """
    with app.app_context():
        from models.academic_calendar import ReportScheduleConfig
        from utils.time import utc_now_naive

        now = datetime.now()
        today = now.date()
        current_day  = now.weekday()   # 0=Mon … 6=Sun
        current_hour = now.hour

        configs = ReportScheduleConfig.query.filter_by(enabled=True).all()
        for cfg in configs:
            if cfg.send_day != current_day:
                continue
            if cfg.send_hour != current_hour:
                continue
            # Guard: skip if already sent today
            if cfg.last_sent_at and cfg.last_sent_at.date() == today:
                logger.info(f'Skipping college {cfg.college_id} — already sent today')
                continue

            dept_ids  = cfg.filter_department_ids  or []
            semesters = cfg.filter_semesters        or []
            adm_years = cfg.filter_admission_years  or []

            logger.info(f'Auto-sending weekly reports for college {cfg.college_id}')
            try:
                result = run_weekly_reports(
                    app,
                    college_id=cfg.college_id,
                    department_ids=dept_ids or None,
                    semesters=semesters or None,
                    admission_years=adm_years or None,
                )
                cfg.last_sent_at = utc_now_naive()
                db.session.commit()
                logger.info(f'Auto-report college {cfg.college_id}: {result}')
            except Exception as exc:
                logger.error(f'Auto-report failed for college {cfg.college_id}: {exc}')
