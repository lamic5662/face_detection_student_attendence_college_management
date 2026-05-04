import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from config import TestingConfig
from extensions import db
from models import Department, Subject, User
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

    class Config(TestConfig):
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'
        CONTENT_UPLOAD_FOLDER = upload_root

    app = create_app(Config)

    with app.app_context():
        db.create_all()

        dept = Department(name='Computer Science', code='CS')
        db.session.add(dept)
        db.session.flush()

        teacher_user = User(name='Teacher One', email='teacher1@example.com', role='teacher')
        teacher_user.set_password('Password@123')
        other_teacher_user = User(name='Teacher Two', email='teacher2@example.com', role='teacher')
        other_teacher_user.set_password('Password@123')
        student_user = User(name='Student One', email='student1@example.com', role='student')
        student_user.set_password('Password@123')
        parent_user = User(name='Parent One', email='parent1@example.com', role='parent')
        parent_user.set_password('Password@123')
        admin_user = User(name='Admin User', email='admin@example.com', role='admin')
        admin_user.set_password('Password@123')
        db.session.add_all([teacher_user, other_teacher_user, student_user, parent_user, admin_user])
        db.session.flush()

        teacher = Teacher(user_id=teacher_user.id, employee_id='T-001', department_id=dept.id)
        other_teacher = Teacher(user_id=other_teacher_user.id, employee_id='T-002', department_id=dept.id)
        student = Student(
            user_id=student_user.id,
            roll_number='CS-001',
            department_id=dept.id,
            semester=1,
        )
        db.session.add_all([teacher, other_teacher, student])
        db.session.flush()

        own_subject = Subject(
            name='Programming',
            code='CS101',
            department_id=dept.id,
            teacher_id=teacher.id,
            semester=1,
            credit_hours=3,
        )
        other_subject = Subject(
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
            subject_id=other_subject.id,
            teacher_id=other_teacher.id,
            status='completed',
        )
        db.session.add(foreign_session)

        teacher_only_notice = Notice(
            title='Teachers Only',
            content='Hidden from students',
            category='general',
            target_role='teacher',
            author_id=teacher_user.id,
        )
        db.session.add(teacher_only_notice)

        content = TeacherContent(
            teacher_id=teacher.id,
            subject_id=own_subject.id,
            department_id=dept.id,
            semester=1,
            content_type='note',
            title='Week 1 Notes',
            is_published=True,
        )
        db.session.add(content)
        db.session.add(ParentStudent(parent_id=parent_user.id, student_id=student.id, relationship='guardian'))
        db.session.commit()

        app.config['TEST_DATA'] = {
            'teacher_user_id': teacher_user.id,
            'student_user_id': student_user.id,
            'student_profile_id': student.id,
            'parent_user_id': parent_user.id,
            'foreign_session_id': foreign_session.id,
            'other_subject_id': other_subject.id,
            'teacher_notice_id': teacher_only_notice.id,
            'own_subject_id': own_subject.id,
            'content_id': content.id,
        }

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()

    os.unlink(db_path)
    shutil.rmtree(upload_root, ignore_errors=True)


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, email, password='Password@123'):
    return client.post(
        '/login',
        data={'email': email, 'password': password},
        follow_redirects=False,
    )
