from flask_mail import Message
from extensions import mail
from flask import current_app
import logging

logger = logging.getLogger(__name__)


def send_low_attendance_alert(student_email: str, student_name: str,
                               subject_name: str, percentage: float):
    threshold = current_app.config.get('LOW_ATTENDANCE_THRESHOLD', 75)
    try:
        msg = Message(
            subject=f"Low Attendance Alert – {subject_name}",
            recipients=[student_email],
            html=f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #ddd;border-radius:8px;overflow:hidden">
              <div style="background:#dc3545;padding:20px;color:#fff;text-align:center">
                <h2>⚠️ Low Attendance Warning</h2>
              </div>
              <div style="padding:30px">
                <p>Dear <strong>{student_name}</strong>,</p>
                <p>Your attendance in <strong>{subject_name}</strong> has dropped to
                   <span style="color:#dc3545;font-size:1.4em;font-weight:bold">{percentage:.1f}%</span>.</p>
                <p>The minimum required attendance is <strong>{threshold}%</strong>.</p>
                <p>Please ensure regular attendance to avoid academic consequences.</p>
              </div>
              <div style="background:#f8f9fa;padding:15px;text-align:center;font-size:12px;color:#6c757d">
                Smart Attendance System &bull; College Management Portal
              </div>
            </div>
            """,
        )
        mail.send(msg)
    except Exception as e:
        logger.error(f"Failed to send alert to {student_email}: {e}")


def send_leave_reviewed(student_email: str, student_name: str,
                        subject_name: str, from_date: str, to_date: str,
                        status: str, remark: str = ''):
    color = '#198754' if status == 'approved' else '#dc3545'
    icon  = '✅' if status == 'approved' else '❌'
    try:
        msg = Message(
            subject=f"Leave {status.capitalize()} – {subject_name}",
            recipients=[student_email],
            html=f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #ddd;border-radius:8px;overflow:hidden">
              <div style="background:{color};padding:20px;color:#fff;text-align:center">
                <h2>{icon} Leave Request {status.capitalize()}</h2>
              </div>
              <div style="padding:30px">
                <p>Dear <strong>{student_name}</strong>,</p>
                <p>Your leave request for <strong>{subject_name}</strong> has been
                   <strong style="color:{color}">{status}</strong>.</p>
                <table style="width:100%;border-collapse:collapse;margin-top:16px">
                  <tr style="background:#f8f9fa">
                    <td style="padding:10px;border:1px solid #dee2e6">Period</td>
                    <td style="padding:10px;border:1px solid #dee2e6">{from_date} → {to_date}</td>
                  </tr>
                  <tr>
                    <td style="padding:10px;border:1px solid #dee2e6">Status</td>
                    <td style="padding:10px;border:1px solid #dee2e6;color:{color};font-weight:bold">{status.capitalize()}</td>
                  </tr>
                  {'<tr style="background:#f8f9fa"><td style="padding:10px;border:1px solid #dee2e6">Remark</td><td style="padding:10px;border:1px solid #dee2e6">' + remark + '</td></tr>' if remark else ''}
                </table>
              </div>
              <div style="background:#f8f9fa;padding:15px;text-align:center;font-size:12px;color:#6c757d">
                Smart Attendance System &bull; College Management Portal
              </div>
            </div>
            """,
        )
        mail.send(msg)
    except Exception as e:
        logger.error(f"Failed to send leave review email to {student_email}: {e}")


def send_session_summary(teacher_email: str, teacher_name: str,
                          subject_name: str, date: str,
                          present: int, total: int):
    try:
        percentage = (present / total * 100) if total > 0 else 0
        msg = Message(
            subject=f"Attendance Summary – {subject_name} ({date})",
            recipients=[teacher_email],
            html=f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #ddd;border-radius:8px;overflow:hidden">
              <div style="background:#0d6efd;padding:20px;color:#fff;text-align:center">
                <h2>Attendance Session Summary</h2>
              </div>
              <div style="padding:30px">
                <p>Dear <strong>{teacher_name}</strong>,</p>
                <p>Session for <strong>{subject_name}</strong> on <strong>{date}</strong> is complete.</p>
                <table style="width:100%;border-collapse:collapse;margin-top:20px">
                  <tr style="background:#f8f9fa">
                    <td style="padding:10px;border:1px solid #dee2e6">Total Students</td>
                    <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold">{total}</td>
                  </tr>
                  <tr>
                    <td style="padding:10px;border:1px solid #dee2e6">Present</td>
                    <td style="padding:10px;border:1px solid #dee2e6;color:#198754;font-weight:bold">{present}</td>
                  </tr>
                  <tr style="background:#f8f9fa">
                    <td style="padding:10px;border:1px solid #dee2e6">Absent</td>
                    <td style="padding:10px;border:1px solid #dee2e6;color:#dc3545;font-weight:bold">{total - present}</td>
                  </tr>
                  <tr>
                    <td style="padding:10px;border:1px solid #dee2e6">Attendance Rate</td>
                    <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold">{percentage:.1f}%</td>
                  </tr>
                </table>
              </div>
            </div>
            """,
        )
        mail.send(msg)
    except Exception as e:
        logger.error(f"Failed to send summary to {teacher_email}: {e}")


def send_absent_teacher_alert(recipients: list[str], subject_name: str,
                               teacher_name: str, slot_time: str,
                               department: str, semester: int):
    """Notify students/parents that a scheduled class has not started."""
    if not recipients:
        return 0
    sent = 0
    for email in recipients:
        try:
            msg = Message(
                subject=f"Class Alert – {subject_name} has not started",
                recipients=[email],
                html=f"""
                <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;
                            border:1px solid #ddd;border-radius:8px;overflow:hidden">
                  <div style="background:#fd7e14;padding:20px;color:#fff;text-align:center">
                    <h2>📢 Class Not Started</h2>
                  </div>
                  <div style="padding:30px">
                    <p>Your scheduled class has not started yet.</p>
                    <table style="width:100%;border-collapse:collapse;margin:16px 0">
                      <tr style="background:#f8f9fa">
                        <td style="padding:10px;border:1px solid #dee2e6">Subject</td>
                        <td style="padding:10px;border:1px solid #dee2e6"><strong>{subject_name}</strong></td>
                      </tr>
                      <tr>
                        <td style="padding:10px;border:1px solid #dee2e6">Teacher</td>
                        <td style="padding:10px;border:1px solid #dee2e6">{teacher_name}</td>
                      </tr>
                      <tr style="background:#f8f9fa">
                        <td style="padding:10px;border:1px solid #dee2e6">Scheduled Time</td>
                        <td style="padding:10px;border:1px solid #dee2e6">{slot_time}</td>
                      </tr>
                      <tr>
                        <td style="padding:10px;border:1px solid #dee2e6">Class</td>
                        <td style="padding:10px;border:1px solid #dee2e6">{department} — Semester {semester}</td>
                      </tr>
                    </table>
                    <p style="color:#6c757d;font-size:13px">
                      This is an automated alert. Please check with your department
                      if the class has been rescheduled.
                    </p>
                  </div>
                  <div style="background:#f8f9fa;padding:15px;text-align:center;
                              font-size:12px;color:#6c757d">
                    Smart Attendance System &bull; College Management Portal
                  </div>
                </div>
                """,
            )
            mail.send(msg)
            sent += 1
        except Exception as e:
            logger.error(f"Failed to send class alert to {email}: {e}")
    return sent


def send_parent_child_alert(parent_email: str, parent_name: str,
                             child_name: str, alert_type: str, detail: str):
    """Generic parent notification for child-related events."""
    icons = {
        'low_attendance': ('⚠️', '#dc3545'),
        'absent_class':   ('📢', '#fd7e14'),
        'exam_result':    ('📝', '#0d6efd'),
        'fee_due':        ('💰', '#198754'),
    }
    icon, color = icons.get(alert_type, ('ℹ️', '#6c757d'))
    title = alert_type.replace('_', ' ').title()
    try:
        msg = Message(
            subject=f"[Parent Alert] {title} — {child_name}",
            recipients=[parent_email],
            html=f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;
                        border:1px solid #ddd;border-radius:8px;overflow:hidden">
              <div style="background:{color};padding:20px;color:#fff;text-align:center">
                <h2>{icon} {title}</h2>
                <p style="margin:0;opacity:.9">Regarding: {child_name}</p>
              </div>
              <div style="padding:30px">
                <p>Dear <strong>{parent_name}</strong>,</p>
                <p>{detail}</p>
                <p style="margin-top:20px">
                  <a href="#" style="background:{color};color:#fff;padding:10px 24px;
                     border-radius:6px;text-decoration:none;font-weight:bold">
                    View Full Report
                  </a>
                </p>
              </div>
              <div style="background:#f8f9fa;padding:15px;text-align:center;
                          font-size:12px;color:#6c757d">
                Smart Attendance System &bull; College Management Portal
              </div>
            </div>
            """,
        )
        mail.send(msg)
    except Exception as e:
        logger.error(f"Failed to send parent alert to {parent_email}: {e}")
