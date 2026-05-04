import os
from app import create_app
from extensions import db
from utils.time import utc_now_naive

# Import all models so Flask-Migrate can detect them
from models import (  # noqa: F401
    User, Department, Student, Teacher, Subject,
    AttendanceSession, AttendanceRecord, LeaveRequest,
    Notice, TimetableSlot, Exam, Mark, FeeStructure, FeePayment,
)
from models.parent import ParentStudent, TeacherStatus, ClassAlert  # noqa: F401
from models.location import StudentLocation  # noqa: F401
from models.setting import CollegeSetting   # noqa: F401

app = create_app()


@app.cli.command('init-db')
def init_db():
    """Create all tables and seed default departments."""
    with app.app_context():
        db.create_all()
        print('Tables created.')

        depts = [
            ('Bachelor of Computer Applications', 'BCA'),
            ('Bachelor of Information Technology', 'BIT'),
            ('Bachelor of Science CSIT', 'BSc.CSIT'),
            ('Bachelor of Business Administration', 'BBA'),
            ('Bachelor of Engineering', 'BE'),
        ]
        for name, code in depts:
            if not Department.query.filter_by(code=code).first():
                db.session.add(Department(name=name, code=code))

        db.session.commit()
        print('Default departments seeded.')
        if not User.query.filter_by(role='admin').first():
            print('No admin account exists yet. Run: flask create-admin')
        else:
            print('Admin account already exists.')


@app.cli.command('create-admin')
def create_admin():
    """Interactively create a new admin user."""
    with app.app_context():
        email = input('Admin email: ').strip().lower()
        name  = input('Full name: ').strip()
        pw    = input('Password: ').strip()
        if User.query.filter_by(email=email).first():
            print(f'User {email} already exists.')
            return
        u = User(name=name, email=email, role='admin', is_active=True)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        print(f'Admin {email} created.')


@app.cli.command('check-classes')
def check_classes():
    """Notify students/parents about classes that haven't started 15+ min past scheduled time."""
    from datetime import datetime, date, time as dtime
    from models.timetable import TimetableSlot
    from models.attendance import AttendanceSession
    from models.parent import ParentStudent, ClassAlert
    from services.notification_service import send_absent_teacher_alert

    with app.app_context():
        now = datetime.now()
        today = date.today()
        today_dow = today.weekday()
        cutoff = now.replace(second=0, microsecond=0)

        slots = TimetableSlot.query.filter_by(
            day_of_week=today_dow, slot_type='class'
        ).all()

        total_sent = 0
        for slot in slots:
            if not slot.subject:
                continue

            # Check if slot ended 15+ min ago with no session started
            slot_end = datetime.combine(today, slot.end_time)
            if (cutoff - slot_end).total_seconds() < 15 * 60:
                continue

            # Skip if a session was started
            session = AttendanceSession.query.filter(
                AttendanceSession.subject_id == slot.subject_id,
                AttendanceSession.date == today,
                AttendanceSession.status.in_(['active', 'completed'])
            ).first()
            if session:
                continue

            # Prevent duplicate alert for same slot today
            existing = ClassAlert.query.filter_by(
                slot_id=slot.id, alert_date=today
            ).first()
            if existing:
                continue

            # Collect student + parent emails
            from models.student import Student
            students = Student.query.filter_by(
                department_id=slot.department_id,
                semester=slot.semester
            ).all()

            recipients = []
            for s in students:
                if s.user.email:
                    recipients.append(s.user.email)
                for link in ParentStudent.query.filter_by(student_id=s.id).all():
                    parent_user = db.session.get(User, link.parent_id)
                    if parent_user and parent_user.email:
                        recipients.append(parent_user.email)

            recipients = list(set(recipients))
            teacher = slot.subject.teacher
            teacher_name = teacher.user.name if teacher else 'Unknown'
            slot_time = f"{slot.start_time.strftime('%H:%M')} – {slot.end_time.strftime('%H:%M')}"
            dept_name = slot.department.name if slot.department else 'N/A'

            sent = send_absent_teacher_alert(
                recipients=recipients,
                subject_name=slot.subject.name,
                teacher_name=teacher_name,
                slot_time=slot_time,
                department=dept_name,
                semester=slot.semester or 0,
            )

            alert = ClassAlert(
                slot_id=slot.id,
                alert_date=today,
                recipient_count=sent,
                triggered_by='auto',
            )
            db.session.add(alert)
            db.session.commit()
            total_sent += sent
            print(f'  Alert sent: {slot.subject.name} @ {slot_time} — {sent} recipients')

        print(f'check-classes done. Total notifications sent: {total_sent}')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    app.run(debug=debug, host='0.0.0.0', port=port)
