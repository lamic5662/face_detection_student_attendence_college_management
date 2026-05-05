import os
import shutil
import sys
import tempfile
from pathlib import Path
from datetime import date, timedelta

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from config import TestingConfig
from extensions import db
from models import College, Department, Subject, User
from models.attendance import AttendanceSession
from models.content import TeacherContent
from models.notice import Notice
from models.parent import ParentStudent
from models.student import Student
from models.teacher import Teacher


class TestConfig(TestingConfig):
    SECRET_KEY = 'test-secret-key'
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False
    MAIL_SUPPRESS_SEND = True


@pytest.fixture()
def app():
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    upload_root = tempfile.mkdtemp(prefix='smart-attendance-content-')
    submission_root = tempfile.mkdtemp(prefix='smart-attendance-submissions-')

    class Config(TestConfig):
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'
        CONTENT_UPLOAD_FOLDER = upload_root
        ASSIGNMENT_UPLOAD_FOLDER = submission_root

    app = create_app(Config)

    with app.app_context():
        db.create_all()

        college = College(name='Alpha College', code='ALPHA')
        db.session.add(college)
        db.session.flush()

        dept = Department(college_id=college.id, name='Computer Science', code='CS')
        db.session.add(dept)
        db.session.flush()

        teacher_user = User(college_id=college.id, name='Teacher One', email='teacher1@example.com', role='teacher')
        teacher_user.set_password('Password@123')
        other_teacher_user = User(college_id=college.id, name='Teacher Two', email='teacher2@example.com', role='teacher')
        other_teacher_user.set_password('Password@123')
        student_user = User(college_id=college.id, name='Student One', email='student1@example.com', role='student')
        student_user.set_password('Password@123')
        parent_user = User(college_id=college.id, name='Parent One', email='parent1@example.com', role='parent')
        parent_user.set_password('Password@123')
        admin_user = User(college_id=college.id, name='Admin User', email='admin@example.com', role='admin')
        admin_user.set_password('Password@123')
        super_admin_user = User(college_id=college.id, name='Platform Owner', email='superadmin@example.com', role='super_admin')
        super_admin_user.set_password('Password@123')
        db.session.add_all([teacher_user, other_teacher_user, student_user, parent_user, admin_user, super_admin_user])
        db.session.flush()

        teacher = Teacher(college_id=college.id, user_id=teacher_user.id, employee_id='T-001', department_id=dept.id)
        other_teacher = Teacher(college_id=college.id, user_id=other_teacher_user.id, employee_id='T-002', department_id=dept.id)
        student = Student(
            college_id=college.id,
            user_id=student_user.id,
            roll_number='CS-001',
            department_id=dept.id,
            semester=1,
        )
        db.session.add_all([teacher, other_teacher, student])
        db.session.flush()

        own_subject = Subject(
            college_id=college.id,
            name='Programming',
            code='CS101',
            department_id=dept.id,
            teacher_id=teacher.id,
            semester=1,
            credit_hours=3,
        )
        other_subject = Subject(
            college_id=college.id,
            name='Databases',
            code='CS102',
            department_id=dept.id,
            teacher_id=other_teacher.id,
            semester=1,
            credit_hours=3,
        )
        db.session.add_all([own_subject, other_subject])
        db.session.flush()

        foreign_session = AttendanceSession(
            college_id=college.id,
            subject_id=other_subject.id,
            teacher_id=other_teacher.id,
            status='completed',
        )
        db.session.add(foreign_session)

        teacher_only_notice = Notice(
            college_id=college.id,
            title='Teachers Only',
            content='Hidden from students',
            category='general',
            target_role='teacher',
            author_id=teacher_user.id,
        )
        db.session.add(teacher_only_notice)

        content = TeacherContent(
            college_id=college.id,
            teacher_id=teacher.id,
            subject_id=own_subject.id,
            department_id=dept.id,
            semester=1,
            content_type='note',
            title='Week 1 Notes',
            is_published=True,
        )
        assignment = TeacherContent(
            college_id=college.id,
            teacher_id=teacher.id,
            subject_id=own_subject.id,
            department_id=dept.id,
            semester=1,
            content_type='assignment',
            title='Week 1 Assignment',
            body='Solve the first programming exercise set.',
            due_date=date.today() + timedelta(days=3),
            marks=20,
            is_published=True,
        )
        db.session.add_all([content, assignment])
        db.session.add(ParentStudent(college_id=college.id, parent_id=parent_user.id, student_id=student.id, relationship='guardian'))
        db.session.commit()

        app.config['TEST_DATA'] = {
            'college_id': college.id,
            'college_code': college.code,
            'teacher_user_id': teacher_user.id,
            'student_user_id': student_user.id,
            'student_profile_id': student.id,
            'parent_user_id': parent_user.id,
            'super_admin_user_id': super_admin_user.id,
            'foreign_session_id': foreign_session.id,
            'other_subject_id': other_subject.id,
            'teacher_notice_id': teacher_only_notice.id,
            'own_subject_id': own_subject.id,
            'content_id': content.id,
            'assignment_id': assignment.id,
        }

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()

    os.unlink(db_path)
    shutil.rmtree(upload_root, ignore_errors=True)
    shutil.rmtree(submission_root, ignore_errors=True)


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, email, password='Password@123', college_code=None):
    data = {'email': email, 'password': password}
    if college_code:
        data['college_code'] = college_code
    return client.post(
        '/login',
        data=data,
        follow_redirects=False,
    )
