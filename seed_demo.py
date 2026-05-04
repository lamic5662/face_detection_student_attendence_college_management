"""
Seed realistic demo data: teachers, students, subjects, and past attendance.
Run: python seed_demo.py
"""
from app import create_app
from extensions import db
from models.user import User
from models.department import Department
from models.student import Student
from models.teacher import Teacher
from models.subject import Subject
from models.attendance import AttendanceSession, AttendanceRecord
from datetime import date, time, timedelta
import random

app = create_app()

def seed():
    with app.app_context():
        def get_or_create_dept(name, code):
            d = Department.query.filter_by(code=code).first()
            if not d:
                d = Department(name=name, code=code)
                db.session.add(d)
                db.session.flush()
            return d

        dept_cs  = get_or_create_dept('Computer Science', 'CS')
        dept_it  = get_or_create_dept('Information Technology', 'IT')
        dept_ece = get_or_create_dept('Electronics & Communication', 'ECE')
        db.session.commit()

        # ── Teachers ────────────────────────────────────────────────────────
        teachers_data = [
            ('Dr. Ramesh Sharma',   'ramesh@college.edu',   'EMP001', dept_cs.id),
            ('Prof. Sunita Patel',  'sunita@college.edu',   'EMP002', dept_cs.id),
            ('Dr. Anil Gupta',      'anil@college.edu',     'EMP003', dept_it.id),
            ('Prof. Meena Joshi',   'meena@college.edu',    'EMP004', dept_ece.id),
        ]
        teachers = []
        for name, email, emp_id, dept_id in teachers_data:
            if not User.query.filter_by(email=email).first():
                u = User(name=name, email=email, role='teacher')
                u.set_password('Teacher@123')
                db.session.add(u)
                db.session.flush()
                t = Teacher(user_id=u.id, employee_id=emp_id, department_id=dept_id)
                db.session.add(t)
                db.session.flush()
                teachers.append(t)
                print(f"  Teacher: {name} / Teacher@123")
            else:
                t = Teacher.query.join(User).filter(User.email == email).first()
                if t:
                    teachers.append(t)

        # ── Students (CS Sem 5) ──────────────────────────────────────────────
        students_data = [
            ('Aarav Singh',     'aarav@student.edu',   'CS2021001'),
            ('Priya Kumari',    'priya@student.edu',   'CS2021002'),
            ('Rohit Verma',     'rohit@student.edu',   'CS2021003'),
            ('Sneha Mishra',    'sneha@student.edu',   'CS2021004'),
            ('Arjun Nair',      'arjun@student.edu',   'CS2021005'),
            ('Divya Reddy',     'divya@student.edu',   'CS2021006'),
            ('Karan Mehta',     'karan@student.edu',   'CS2021007'),
            ('Pooja Sharma',    'pooja@student.edu',   'CS2021008'),
            ('Vikram Yadav',    'vikram@student.edu',  'CS2021009'),
            ('Ananya Iyer',     'ananya@student.edu',  'CS2021010'),
            ('Suresh Pillai',   'suresh@student.edu',  'CS2021011'),
            ('Riya Gupta',      'riya@student.edu',    'CS2021012'),
        ]
        students = []
        for name, email, roll in students_data:
            if not User.query.filter_by(email=email).first():
                u = User(name=name, email=email, role='student')
                u.set_password('Student@123')
                db.session.add(u)
                db.session.flush()
                s = Student(user_id=u.id, roll_number=roll,
                            department_id=dept_cs.id, semester=5)
                db.session.add(s)
                db.session.flush()
                students.append(s)
            else:
                s = Student.query.join(User).filter(User.email == email).first()
                if s:
                    students.append(s)
        print(f"  {len(students)} students seeded (CS Sem 5) / Student@123")

        db.session.commit()

        # ── Subjects ────────────────────────────────────────────────────────
        t0, t1 = teachers[0], teachers[1]
        subjects_data = [
            ('Data Structures & Algorithms', 'CS501', dept_cs.id, t0.id, 5, 4),
            ('Database Management Systems',  'CS502', dept_cs.id, t1.id, 5, 4),
            ('Operating Systems',            'CS503', dept_cs.id, t0.id, 5, 3),
            ('Computer Networks',            'CS504', dept_cs.id, t1.id, 5, 3),
        ]
        subjects = []
        for name, code, dept_id, teacher_id, sem, credits in subjects_data:
            if not Subject.query.filter_by(code=code).first():
                sub = Subject(name=name, code=code, department_id=dept_id,
                              teacher_id=teacher_id, semester=sem, credit_hours=credits)
                db.session.add(sub)
                db.session.flush()
                subjects.append(sub)
                print(f"  Subject: {code} — {name}")
            else:
                s = Subject.query.filter_by(code=code).first()
                subjects.append(s)
        db.session.commit()

        # ── Past Attendance Sessions (last 20 school days) ──────────────────
        if AttendanceSession.query.count() > 0:
            print("  Attendance sessions already seeded. Skipping.")
            return

        school_days = []
        d = date.today() - timedelta(days=1)
        while len(school_days) < 20:
            if d.weekday() < 5:   # Mon–Fri
                school_days.append(d)
            d -= timedelta(days=1)
        school_days.reverse()

        for idx, sub in enumerate(subjects):
            for day in school_days:
                # Only 3 sessions per week per subject
                if day.weekday() not in [0, 2, 4]:
                    continue
                session = AttendanceSession(
                    subject_id=sub.id,
                    teacher_id=sub.teacher_id,
                    date=day,
                    start_time=time(8 + idx, 0),
                    end_time=time(9 + idx, 0),
                    status='completed'
                )
                db.session.add(session)
                db.session.flush()

                for student in students:
                    # Simulate realistic attendance: some students more regular
                    base_rate = random.uniform(0.65, 1.0)
                    present = random.random() < base_rate
                    rec = AttendanceRecord(
                        session_id=session.id,
                        student_id=student.id,
                        status='present' if present else 'absent',
                        liveness_verified=present,
                        confidence_score=round(random.uniform(0.82, 0.97), 3) if present else None,
                    )
                    if present:
                        from datetime import datetime
                        rec.marked_at = datetime.combine(day, time(8 + idx, random.randint(0, 8)))
                    db.session.add(rec)

        db.session.commit()
        sessions_count = AttendanceSession.query.count()
        records_count  = AttendanceRecord.query.count()
        print(f"  {sessions_count} sessions, {records_count} attendance records seeded.")
        print("\nDemo data ready!")
        print("Teacher login: ramesh@college.edu / Teacher@123")
        print("Student login: aarav@student.edu  / Student@123")

if __name__ == '__main__':
    seed()
