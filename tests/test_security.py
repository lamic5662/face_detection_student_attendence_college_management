import io
import os
from datetime import date
from unittest.mock import patch

from PIL import Image
from extensions import db, mail
from models.academic_calendar import AcademicCalendarEvent
from models.assignment import AssignmentSubmission
from models.college import College
from models.college_feature import CollegeFeatureAccess
from models.content import TeacherContent
from models.department import Department
from models.fee import FeePayment, FeeStructure
from models.id_card import IDCardTemplate, StudentIDCard
from models.leave import LeaveRequest
from models.notice import Notice
from models.notice_read import NoticeRead
from models.platform_audit import PlatformAuditLog
from models.setting import CollegeSetting
from models.student import Student
from models.user import User
from utils.account_setup import build_public_url, generate_password_setup_token


def make_valid_png_bytes(size=(64, 64), color=(13, 110, 253, 255)):
    buf = io.BytesIO()
    Image.new('RGBA', size, color).save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue()


def login(client, email, password='Password@123', college_code=None):
    data = {'email': email, 'password': password}
    if college_code:
        data['college_code'] = college_code
    return client.post(
        '/login',
        data=data,
        follow_redirects=False,
    )


def test_teacher_cannot_download_another_teachers_session_report(app, client):
    login(client, 'teacher1@example.com')

    foreign_session_id = app.config['TEST_DATA']['foreign_session_id']
    response = client.get(f'/teacher/reports/session/{foreign_session_id}/download')

    assert response.status_code == 403


def test_student_with_temporary_password_is_prompted_on_first_login(app, client):
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        user.set_temporary_password('TempPass@123')
        db.session.commit()

    response = login(
        client,
        'student1@example.com',
        password='TempPass@123',
        college_code=app.config['TEST_DATA']['college_code'],
    )

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/password-setup-prompt')


def test_student_with_temporary_password_cannot_open_dashboard_before_changing_it(app, client):
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        user.set_temporary_password('TempPass@123')
        db.session.commit()

    login(
        client,
        'student1@example.com',
        password='TempPass@123',
        college_code=app.config['TEST_DATA']['college_code'],
    )
    response = client.get('/student/dashboard', follow_redirects=False)

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/password-setup-prompt')


def test_student_can_request_password_setup_email(app, client):
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        user.set_temporary_password('TempPass@123')
        db.session.commit()

    login(
        client,
        'student1@example.com',
        password='TempPass@123',
        college_code=app.config['TEST_DATA']['college_code'],
    )

    sent_messages = []

    def _capture_message(message):
        sent_messages.append(message)

    with patch.object(mail, 'send', side_effect=_capture_message):
        response = client.post('/password-setup-prompt/send-email', follow_redirects=True)

    assert response.status_code == 200
    assert sent_messages
    assert sent_messages[0].recipients == ['student1@example.com']
    assert b'you still need to set your new password before continuing' in response.data
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        assert user.password_setup_email_sent_at is not None


def test_college_user_can_request_forgot_password_email(app, client):
    sent_messages = []

    def _capture_message(message):
        sent_messages.append(message)

    with patch.object(mail, 'send', side_effect=_capture_message):
        response = client.post(
            '/forgot-password',
            data={
                'college_code': app.config['TEST_DATA']['college_code'],
                'email': 'student1@example.com',
            },
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert sent_messages
    assert sent_messages[0].recipients == ['student1@example.com']
    assert b'If we found an active account for that email' in response.data


def test_super_admin_can_request_forgot_password_without_college_code(app, client):
    sent_messages = []

    def _capture_message(message):
        sent_messages.append(message)

    with patch.object(mail, 'send', side_effect=_capture_message):
        response = client.post(
            '/forgot-password',
            data={
                'email': 'superadmin@example.com',
            },
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert sent_messages
    assert sent_messages[0].recipients == ['superadmin@example.com']
    assert b'If we found an active account for that email' in response.data


def test_student_must_change_temporary_password_and_then_sign_in_again(app, client):
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        user.set_temporary_password('TempPass@123')
        db.session.commit()

    login(
        client,
        'student1@example.com',
        password='TempPass@123',
        college_code=app.config['TEST_DATA']['college_code'],
    )
    response = client.post(
        '/password-setup-prompt',
        data={
            'new_password': 'StudentDirect@123',
            'confirm_password': 'StudentDirect@123',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Please sign in again with your new password' in response.data
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        assert user.must_change_password is False
        assert user.check_password('StudentDirect@123') is True
    old_password_login = login(
        client,
        'student1@example.com',
        password='TempPass@123',
        college_code=app.config['TEST_DATA']['college_code'],
    )
    assert old_password_login.status_code == 200
    assert b'Invalid email or password' in old_password_login.data
    new_password_login = login(
        client,
        'student1@example.com',
        password='StudentDirect@123',
        college_code=app.config['TEST_DATA']['college_code'],
    )
    assert new_password_login.status_code == 302
    assert new_password_login.headers['Location'].endswith('/student/dashboard')


def test_student_cannot_reuse_temporary_password_as_new_password(app, client):
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        user.set_temporary_password('TempPass@123')
        db.session.commit()

    login(
        client,
        'student1@example.com',
        password='TempPass@123',
        college_code=app.config['TEST_DATA']['college_code'],
    )
    response = client.post(
        '/password-setup-prompt',
        data={
            'new_password': 'TempPass@123',
            'confirm_password': 'TempPass@123',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'must be different from the current one' in response.data
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        assert user.must_change_password is True
        assert user.check_password('TempPass@123') is True


def test_student_can_set_password_from_email_link(app, client):
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        user.set_temporary_password('TempPass@123')
        db.session.commit()
        token = generate_password_setup_token(user)

    response = client.post(
        f'/set-password/{token}',
        data={
            'new_password': 'StudentNew@123',
            'confirm_password': 'StudentNew@123',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Please sign in with your new password' in response.data
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        assert user.must_change_password is False
        assert user.password_changed_at is not None
        assert user.check_password('StudentNew@123') is True


def test_password_reset_link_rejects_reusing_existing_password(app, client):
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        token = generate_password_setup_token(user)

    response = client.post(
        f'/set-password/{token}?mode=reset',
        data={
            'new_password': 'Password@123',
            'confirm_password': 'Password@123',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'must be different from the current one' in response.data


def test_change_password_rejects_reusing_existing_password(app, client):
    login(client, 'student1@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.post(
        '/change-password',
        data={
            'current_password': 'Password@123',
            'new_password': 'Password@123',
            'confirm_password': 'Password@123',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'must be different from the current one' in response.data


def test_forgot_password_email_uses_reset_mode_link(app):
    with app.app_context():
        app.config['PUBLIC_BASE_URL'] = 'https://portal.smartattend.test'
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        sent_messages = []

        def _capture_message(message):
            sent_messages.append(message)

        with patch.object(mail, 'send', side_effect=_capture_message):
            from utils.account_setup import send_password_reset_email
            send_password_reset_email(user)

        assert sent_messages
        assert 'mode=reset' in sent_messages[0].html


def test_password_setup_email_uses_public_base_url_when_configured(app):
    with app.app_context():
        app.config['PUBLIC_BASE_URL'] = 'https://portal.smartattend.test'
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        token = generate_password_setup_token(user)
        link = build_public_url('auth.set_password_from_email', token=token)

        assert link.startswith('https://portal.smartattend.test/set-password/')


def test_parent_with_temporary_password_is_prompted_on_first_login(app, client):
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['parent_user_id'])
        user.set_temporary_password('ParentTemp@123')
        db.session.commit()

    response = login(
        client,
        'parent1@example.com',
        password='ParentTemp@123',
        college_code=app.config['TEST_DATA']['college_code'],
    )

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/password-setup-prompt')


def test_admin_password_reset_creates_temporary_password_state(app, client):
    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.post(
        f"/admin/users/reset-password/{app.config['TEST_DATA']['student_user_id']}",
        data={'new_password': 'ResetTemp@123'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        user = db.session.get(User, app.config['TEST_DATA']['student_user_id'])
        assert user.must_change_password is True
        assert user.password_changed_at is None
        assert user.check_password('ResetTemp@123') is True


def test_admin_can_add_parent_with_temporary_password(app, client):
    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.post(
        '/admin/parents/add',
        data={
            'name': 'Parent Two',
            'email': 'parent2@example.com',
            'password': 'ParentTemp@123',
            'student_id': str(app.config['TEST_DATA']['student_profile_id']),
            'relationship': 'guardian',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email='parent2@example.com').first()
        assert user is not None
        assert user.role == 'parent'
        assert user.must_change_password is True
        assert user.password_changed_at is None


def test_admin_can_edit_subject_credit_hours_without_500(app, client):
    from models.subject import Subject

    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])

    with app.app_context():
        subject = db.session.get(Subject, app.config['TEST_DATA']['own_subject_id'])
        assert subject is not None
        subject_id = subject.id
        teacher_id = subject.teacher_id
        department_id = subject.department_id

    response = client.post(
        f'/admin/subjects/edit/{subject_id}',
        data={
            'name': 'Programming Fundamentals',
            'code': 'CS101',
            'department_id': str(department_id),
            'teacher_id': str(teacher_id),
            'semester': '1',
            'credit_hours': '4',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Subject CS101 updated.' in response.data

    with app.app_context():
        updated = db.session.get(Subject, subject_id)
        assert updated.credit_hours == 4


def test_admin_can_delete_subject_without_500(app, client):
    from models.subject import Subject

    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])

    with app.app_context():
        base_subject = db.session.get(Subject, app.config['TEST_DATA']['own_subject_id'])
        subject = Subject(
            college_id=app.config['TEST_DATA']['college_id'],
            name='Temporary Subject',
            code='TMP401',
            department_id=base_subject.department_id,
            teacher_id=base_subject.teacher_id,
            semester=1,
            credit_hours=3,
        )
        db.session.add(subject)
        db.session.commit()
        subject_id = subject.id

    response = client.post(
        f'/admin/subjects/delete/{subject_id}',
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Subject deleted.' in response.data

    with app.app_context():
        deleted = db.session.get(Subject, subject_id)
        assert deleted is None


def test_admin_settings_page_renders_without_500(app, client):
    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])

    response = client.get('/admin/settings')

    assert response.status_code == 200
    assert b'collegeSettingsForm' in response.data
    assert b'Save Settings' in response.data
    assert b'name="college_logo"' in response.data


def test_admin_can_upload_college_logo_without_500(app, client):
    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])

    response = client.post(
        '/admin/settings/logo',
        data={
            'college_logo': (io.BytesIO(make_valid_png_bytes()), 'college-logo.png'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'College logo updated.' in response.data

    with app.app_context():
        college = db.session.get(College, app.config['TEST_DATA']['college_id'])
        cs = CollegeSetting.get(college=college)
        assert cs.logo_path
        assert cs.logo_path.startswith('uploads/college_logos/')
        assert os.path.exists(os.path.join(app.static_folder, cs.logo_path))


def test_admin_can_save_settings_and_logo_in_single_submit(app, client):
    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])

    response = client.post(
        '/admin/settings/save',
        data={
            'college_name': 'Updated Alpha College',
            'address': 'Kathmandu',
            'latitude': '27.717200',
            'longitude': '85.324000',
            'college_logo': (io.BytesIO(make_valid_png_bytes()), 'single-submit-logo.png'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'College settings and logo saved successfully.' in response.data

    with app.app_context():
        college = db.session.get(College, app.config['TEST_DATA']['college_id'])
        cs = CollegeSetting.get(college=college)
        assert college.name == 'Updated Alpha College'
        assert cs.college_name == 'Updated Alpha College'
        assert cs.address == 'Kathmandu'
        assert cs.logo_path
        assert cs.logo_path.startswith('uploads/college_logos/')
        assert os.path.exists(os.path.join(app.static_folder, cs.logo_path))


def test_admin_logo_upload_rejects_tiny_invalid_image(app, client):
    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])

    response = client.post(
        '/admin/settings/save',
        data={
            'college_name': 'Alpha College',
            'college_logo': (io.BytesIO(b'bad'), 'tiny-logo.png'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Logo file looks invalid or too small' in response.data

    with app.app_context():
        college = db.session.get(College, app.config['TEST_DATA']['college_id'])
        cs = CollegeSetting.get(college=college)
        assert cs.logo_path is None


def test_teacher_cannot_download_another_teachers_subject_report(app, client):
    login(client, 'teacher1@example.com')

    other_subject_id = app.config['TEST_DATA']['other_subject_id']
    response = client.get(f'/teacher/reports/subject/{other_subject_id}/download')

    assert response.status_code == 403


def test_student_cannot_open_teacher_only_notice(app, client):
    login(client, 'student1@example.com', college_code=app.config['TEST_DATA']['college_code'])

    notice_id = app.config['TEST_DATA']['teacher_notice_id']
    response = client.get(f'/notices/{notice_id}')

    assert response.status_code == 404


def test_teacher_attachment_rejects_active_html_upload(app, client):
    login(client, 'teacher1@example.com')

    subject_id = app.config['TEST_DATA']['own_subject_id']
    response = client.post(
        '/teacher/content/new',
        data={
            'title': 'Unsafe Upload',
            'content_type': 'note',
            'subject_id': str(subject_id),
            'semester': '1',
            'attachment': (io.BytesIO(b'<html><script>alert(1)</script></html>'), 'unsafe.html'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Unsupported attachment type' in response.data


def test_student_can_fetch_private_note_attachment(app, client):
    content_id = app.config['TEST_DATA']['content_id']
    upload_dir = app.config['CONTENT_UPLOAD_FOLDER']
    filename = 'fixture-note.txt'
    abs_path = os.path.join(upload_dir, filename)

    with app.app_context():
        item = db.session.get(TeacherContent, content_id)
        item.file_path = f'uploads/content/{filename}'
        db.session.commit()

    with open(abs_path, 'w', encoding='utf-8') as handle:
        handle.write('private note body')

    login(client, 'student1@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.get(f'/student/content/{content_id}/file?download=0')

    assert response.status_code == 200
    assert response.data == b'private note body'


def test_super_admin_system_setup_page_loads(app, client):
    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])

    response = client.get('/super-admin/system-setup')

    assert response.status_code == 200
    assert b'Platform Readiness' in response.data
    assert b'Platform Checks' in response.data


def test_admin_cannot_open_super_admin_system_setup(app, client):
    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])

    response = client.get('/super-admin/system-setup')

    assert response.status_code == 403


def test_super_admin_can_create_college(app, client):
    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])

    response = client.post(
        '/super-admin/colleges/create',
        data={
            'name': 'Gamma College',
            'code': 'GAMMA',
            'subdomain': 'gamma',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        college = College.query.filter_by(code='GAMMA').first()
        assert college is not None
        assert college.name == 'Gamma College'
        assert college.subdomain == 'gamma'
        log = PlatformAuditLog.query.filter_by(action_key='college.created', college_id=college.id).first()
        assert log is not None
        assert 'Created college Gamma College [GAMMA]' in log.summary


def test_super_admin_can_create_college_admin(app, client):
    with app.app_context():
        college = College(name='Beta College', code='BETA')
        db.session.add(college)
        db.session.commit()
        college_id = college.id

    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.post(
        f'/super-admin/colleges/{college_id}/admins/create',
        data={
            'name': 'Beta Admin',
            'email': 'beta.admin@example.com',
            'password': 'Password@123',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email='beta.admin@example.com', college_id=college_id).first()
        assert user is not None
        assert user.role == 'admin'


def test_super_admin_cannot_deactivate_host_college(app, client):
    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    college_id = app.config['TEST_DATA']['college_id']

    response = client.post(
        f'/super-admin/colleges/{college_id}/toggle',
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        college = db.session.get(College, college_id)
        assert college is not None
        assert college.is_active is True


def test_super_admin_can_update_college_feature_access(app, client):
    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    college_id = app.config['TEST_DATA']['college_id']

    response = client.post(
        f'/super-admin/colleges/{college_id}/features',
        data={
            'enabled_features': ['attendance', 'learning_content', 'notices'],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Feature access updated for Alpha College.' in response.data

    with app.app_context():
        fees_access = CollegeFeatureAccess.query.filter_by(college_id=college_id, feature_key='fees').first()
        content_access = CollegeFeatureAccess.query.filter_by(college_id=college_id, feature_key='learning_content').first()
        assert fees_access is not None
        assert fees_access.enabled is False
        assert content_access is not None
        assert content_access.enabled is True
        log = PlatformAuditLog.query.filter_by(
            action_key='college.features_updated',
            college_id=college_id,
        ).order_by(PlatformAuditLog.created_at.desc()).first()
        assert log is not None


def test_super_admin_can_open_college_detail_with_role_activity(app, client):
    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    college_id = app.config['TEST_DATA']['college_id']

    response = client.get(f'/super-admin/colleges/{college_id}')
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'Role Activity Summary' in page
    assert 'College Admin Accounts' in page
    assert 'College Setup Status' in page
    assert 'Feature Access Summary' in page
    assert 'College Admins' in page
    assert 'Teachers' in page
    assert 'Students' in page
    assert 'Parents' in page
    assert 'admin@example.com' in page


def test_super_admin_can_open_audit_logs_page(app, client):
    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])

    response = client.get('/super-admin/audit-logs')

    assert response.status_code == 200
    assert b'Platform Audit Trail' in response.data


def test_super_admin_can_export_audit_logs_csv(app, client):
    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    client.post(
        '/super-admin/colleges/create',
        data={
            'name': 'Export College',
            'code': 'EXPT',
            'subdomain': 'export-college',
        },
        follow_redirects=True,
    )

    response = client.get('/super-admin/audit-logs/export')

    assert response.status_code == 200
    assert response.mimetype == 'text/csv'
    assert 'attachment; filename=' in response.headers['Content-Disposition']
    body = response.get_data(as_text=True)
    assert 'action_key,summary' in body
    assert 'college.created' in body
    assert 'Created college Export College [EXPT]' in body


def test_super_admin_can_delete_single_audit_log(app, client):
    with app.app_context():
        log = PlatformAuditLog(
            actor_user_id=app.config['TEST_DATA']['super_admin_user_id'],
            college_id=app.config['TEST_DATA']['college_id'],
            action_key='audit.test_delete_single',
            summary='Delete me',
            target_type='test',
            target_id=101,
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.post(
        f'/super-admin/audit-logs/{log_id}/delete',
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(PlatformAuditLog, log_id) is None


def test_super_admin_can_delete_filtered_audit_logs(app, client):
    with app.app_context():
        college_id = app.config['TEST_DATA']['college_id']
        target_logs = [
            PlatformAuditLog(
                actor_user_id=app.config['TEST_DATA']['super_admin_user_id'],
                college_id=college_id,
                action_key='audit.bulk_delete_target',
                summary='Delete target A',
            ),
            PlatformAuditLog(
                actor_user_id=app.config['TEST_DATA']['super_admin_user_id'],
                college_id=college_id,
                action_key='audit.bulk_delete_target',
                summary='Delete target B',
            ),
            PlatformAuditLog(
                actor_user_id=app.config['TEST_DATA']['super_admin_user_id'],
                college_id=college_id,
                action_key='audit.keep_me',
                summary='Keep me',
            ),
        ]
        db.session.add_all(target_logs)
        db.session.commit()

    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.post(
        '/super-admin/audit-logs/delete-filtered',
        data={'action': 'audit.bulk_delete_target'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        assert PlatformAuditLog.query.filter_by(action_key='audit.bulk_delete_target').count() == 0
        assert PlatformAuditLog.query.filter_by(action_key='audit.keep_me').count() == 1


def test_super_admin_cannot_bulk_delete_audit_logs_without_filters(app, client):
    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.post(
        '/super-admin/audit-logs/delete-filtered',
        data={},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Apply at least one filter before deleting audit logs in bulk.' in response.data


def test_super_admin_topbar_uses_platform_activity_instead_of_college_notices(app, client):
    with app.app_context():
        college_id = app.config['TEST_DATA']['college_id']
        db.session.add(Notice(
            college_id=college_id,
            title='College Notice For Students',
            content='This should not appear in the super admin bell.',
            category='general',
            target_role='student',
            author_id=app.config['TEST_DATA']['teacher_user_id'],
        ))
        db.session.commit()

    login(client, 'superadmin@example.com')
    response = client.get('/super-admin/dashboard')
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'Platform Activity' in page
    assert 'Open Audit' in page
    assert 'Open Board' not in page
    assert 'College Notice For Students' not in page


def test_super_admin_notifications_feed_returns_platform_audit_entries(app, client):
    login(client, 'superadmin@example.com')
    client.post(
        '/super-admin/colleges/create',
        data={
            'name': 'Zeta College',
            'code': 'ZETA',
            'subdomain': 'zeta',
        },
        follow_redirects=True,
    )

    response = client.get('/super-admin/notifications/feed')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['items']
    assert any('Created college Zeta College [ZETA]' in item['title'] for item in payload['items'])


def test_super_admin_can_mark_platform_notifications_as_read(app, client):
    login(client, 'superadmin@example.com')
    client.post(
        '/super-admin/colleges/create',
        data={
            'name': 'Eta College',
            'code': 'ETA',
            'subdomain': 'eta',
        },
        follow_redirects=True,
    )

    response = client.post('/super-admin/notifications/mark-all-read')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['count'] == 0
    assert payload['marked_count'] >= 1
    assert payload['items']
    assert all(item['is_read'] is True for item in payload['items'])


def test_super_admin_can_delete_read_platform_notifications_from_tray(app, client):
    login(client, 'superadmin@example.com')
    client.post(
        '/super-admin/colleges/create',
        data={
            'name': 'Theta College',
            'code': 'THETA',
            'subdomain': 'theta',
        },
        follow_redirects=True,
    )
    client.post('/super-admin/notifications/mark-all-read')

    response = client.post('/super-admin/notifications/delete-read')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['deleted_count'] >= 1


def test_super_admin_notification_dropdown_has_platform_controls_and_scroll_list(app, client):
    login(client, 'superadmin@example.com')
    response = client.get('/super-admin/dashboard')
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'Platform Activity' in page
    assert 'topbarDeleteReadButton' in page
    assert 'topbarMarkReadButton' in page
    assert 'topbar-notice-list' in page


def test_super_admin_can_toggle_college_admin_status(app, client):
    with app.app_context():
        college = College(name='Beta College', code='BETA')
        db.session.add(college)
        db.session.flush()
        beta_admin = User(
            college_id=college.id,
            name='Beta Admin',
            email='beta.admin@example.com',
            role='admin',
            is_active=True,
        )
        beta_admin.set_password('Password@123')
        db.session.add(beta_admin)
        backup_admin = User(
            college_id=college.id,
            name='Beta Backup',
            email='beta.backup@example.com',
            role='admin',
            is_active=True,
        )
        backup_admin.set_password('Password@123')
        db.session.add(backup_admin)
        db.session.commit()
        college_id = college.id
        admin_id = beta_admin.id

    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.post(
        f'/super-admin/colleges/{college_id}/admins/{admin_id}/toggle',
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        beta_admin = db.session.get(User, admin_id)
        assert beta_admin is not None
        assert beta_admin.is_active is False
        log = PlatformAuditLog.query.filter_by(
            action_key='college_admin.toggled',
            college_id=college_id,
            target_id=admin_id,
        ).order_by(PlatformAuditLog.created_at.desc()).first()
        assert log is not None


def test_super_admin_can_reset_college_admin_password(app, client):
    with app.app_context():
        college = College(name='Gamma College', code='GAMMA')
        db.session.add(college)
        db.session.flush()
        gamma_admin = User(
            college_id=college.id,
            name='Gamma Admin',
            email='gamma.admin@example.com',
            role='admin',
            is_active=True,
        )
        gamma_admin.set_password('Password@123')
        db.session.add(gamma_admin)
        db.session.commit()
        college_id = college.id
        admin_id = gamma_admin.id

    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.post(
        f'/super-admin/colleges/{college_id}/admins/{admin_id}/reset-password',
        data={'new_password': 'NewStrong@123'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        gamma_admin = db.session.get(User, admin_id)
        assert gamma_admin is not None
        assert gamma_admin.check_password('NewStrong@123') is True
        log = PlatformAuditLog.query.filter_by(
            action_key='college_admin.password_reset',
            college_id=college_id,
            target_id=admin_id,
        ).order_by(PlatformAuditLog.created_at.desc()).first()
        assert log is not None


def test_super_admin_cannot_delete_last_active_admin_of_active_college(app, client):
    with app.app_context():
        college = College(name='Delta College', code='DELTA')
        db.session.add(college)
        db.session.flush()
        delta_admin = User(
            college_id=college.id,
            name='Delta Admin',
            email='delta.admin@example.com',
            role='admin',
            is_active=True,
        )
        delta_admin.set_password('Password@123')
        db.session.add(delta_admin)
        db.session.commit()
        college_id = college.id
        admin_id = delta_admin.id

    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.post(
        f'/super-admin/colleges/{college_id}/admins/{admin_id}/delete',
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        delta_admin = db.session.get(User, admin_id)
        assert delta_admin is not None


def test_super_admin_deleting_college_admin_creates_audit_log(app, client):
    with app.app_context():
        college = College(name='Epsilon College', code='EPSILON')
        db.session.add(college)
        db.session.flush()
        first_admin = User(
            college_id=college.id,
            name='Epsilon Admin One',
            email='epsilon.one@example.com',
            role='admin',
            is_active=True,
        )
        first_admin.set_password('Password@123')
        second_admin = User(
            college_id=college.id,
            name='Epsilon Admin Two',
            email='epsilon.two@example.com',
            role='admin',
            is_active=True,
        )
        second_admin.set_password('Password@123')
        db.session.add_all([first_admin, second_admin])
        db.session.commit()
        college_id = college.id
        admin_id = second_admin.id

    login(client, 'superadmin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.post(
        f'/super-admin/colleges/{college_id}/admins/{admin_id}/delete',
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        deleted_admin = db.session.get(User, admin_id)
        assert deleted_admin is None
        log = PlatformAuditLog.query.filter_by(
            action_key='college_admin.deleted',
            college_id=college_id,
            target_id=admin_id,
        ).order_by(PlatformAuditLog.created_at.desc()).first()
        assert log is not None


def test_disabled_feature_is_hidden_and_blocked_for_admin(app, client):
    with app.app_context():
        db.session.add(CollegeFeatureAccess(
            college_id=app.config['TEST_DATA']['college_id'],
            feature_key='fees',
            enabled=False,
        ))
        db.session.commit()

    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])

    dashboard = client.get('/admin/dashboard')
    page = dashboard.get_data(as_text=True)

    assert dashboard.status_code == 200
    assert 'data-nav-group="more" data-nav-key="fees"' not in page

    blocked = client.get('/admin/fees')
    assert blocked.status_code == 403


def test_disabled_notices_hide_bell_and_block_notice_board(app, client):
    with app.app_context():
        db.session.add(CollegeFeatureAccess(
            college_id=app.config['TEST_DATA']['college_id'],
            feature_key='notices',
            enabled=False,
        ))
        db.session.commit()

    login(client, 'student1@example.com', college_code=app.config['TEST_DATA']['college_code'])

    dashboard = client.get('/student/dashboard')
    page = dashboard.get_data(as_text=True)

    assert dashboard.status_code == 200
    assert 'topbarBellButton' not in page
    assert 'data-nav-group="quick" data-nav-key="notice_board"' not in page

    blocked = client.get('/notices')
    assert blocked.status_code == 403


def test_parent_can_open_linked_child_marksheet(app, client):
    login(client, 'parent1@example.com', college_code=app.config['TEST_DATA']['college_code'])
    student_id = app.config['TEST_DATA']['student_profile_id']

    response = client.get('/parent/marksheets')
    assert response.status_code == 200
    assert b'View Full Marksheet' in response.data

    child_response = client.get(f'/parent/marksheet/{student_id}')
    assert child_response.status_code == 200
    assert b'Child Marksheet' in child_response.data


def test_admin_id_card_list_hides_other_college_requests(app, client):
    with app.app_context():
        other_college = College(name='Beta College', code='BETA')
        db.session.add(other_college)
        db.session.flush()

        other_dept = Department(college_id=other_college.id, name='Management', code='BBA')
        db.session.add(other_dept)
        db.session.flush()

        other_user = User(
            college_id=other_college.id,
            name='Beta Student',
            email='beta.student@example.com',
            role='student',
        )
        other_user.set_password('Password@123')
        db.session.add(other_user)
        db.session.flush()

        other_student = Student(
            college_id=other_college.id,
            user_id=other_user.id,
            roll_number='BETA-001',
            department_id=other_dept.id,
            semester=1,
        )
        db.session.add(other_student)
        db.session.flush()

        db.session.add(StudentIDCard(
            college_id=other_college.id,
            student_id=other_student.id,
            status='pending',
        ))
        db.session.commit()

    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.get('/admin/id-cards')

    assert response.status_code == 200
    assert b'Beta Student' not in response.data
    assert b'BETA-001' not in response.data


def test_admin_cannot_view_another_college_id_card(app, client):
    with app.app_context():
        other_college = College(name='Gamma College', code='GAMMA')
        db.session.add(other_college)
        db.session.flush()

        other_dept = Department(college_id=other_college.id, name='Science', code='SCI')
        db.session.add(other_dept)
        db.session.flush()

        other_user = User(
            college_id=other_college.id,
            name='Gamma Student',
            email='gamma.student@example.com',
            role='student',
        )
        other_user.set_password('Password@123')
        db.session.add(other_user)
        db.session.flush()

        other_student = Student(
            college_id=other_college.id,
            user_id=other_user.id,
            roll_number='SCI-001',
            department_id=other_dept.id,
            semester=1,
        )
        db.session.add(other_student)
        db.session.flush()

        other_card = StudentIDCard(
            college_id=other_college.id,
            student_id=other_student.id,
            status='pending',
        )
        db.session.add(other_card)
        db.session.commit()
        foreign_card_id = other_card.id

    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.get(f'/admin/id-cards/{foreign_card_id}/view')

    assert response.status_code == 404


def test_id_card_template_assets_are_saved_per_college(app, client):
    with app.app_context():
        other_college = College(name='Delta College', code='DELTA')
        db.session.add(other_college)
        db.session.flush()

        other_admin = User(
            college_id=other_college.id,
            name='Delta Admin',
            email='delta.admin@example.com',
            role='admin',
        )
        other_admin.set_password('Password@123')
        db.session.add(other_admin)
        db.session.commit()

    first_login = login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])
    assert first_login.status_code == 302
    first_response = client.post(
        '/admin/id-card-template',
        data={
            'principal_name': 'Alpha Principal',
            'principal_title': 'Principal',
            'logo': (io.BytesIO(b'alpha-logo'), 'alpha.png'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )
    assert first_response.status_code == 200

    client.get('/logout', follow_redirects=True)
    second_login = login(client, 'delta.admin@example.com', college_code='DELTA')
    assert second_login.status_code == 302
    second_response = client.post(
        '/admin/id-card-template',
        data={
            'principal_name': 'Delta Principal',
            'principal_title': 'Principal',
            'logo': (io.BytesIO(b'delta-logo'), 'delta.png'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )
    assert second_response.status_code == 200

    with app.app_context():
        alpha_template = IDCardTemplate.query.join(College).filter(College.code == app.config['TEST_DATA']['college_code']).first()
        delta_template = IDCardTemplate.query.join(College).filter(College.code == 'DELTA').first()

        assert alpha_template.logo_path != delta_template.logo_path
        assert alpha_template.logo_path.endswith('/logo.png')
        assert delta_template.logo_path.endswith('/logo.png')
        assert '/alpha/' in alpha_template.logo_path
        assert '/delta/' in delta_template.logo_path


def test_leave_reference_numbers_are_scoped_by_college_code(app):
    with app.app_context():
        alpha = db.session.get(College, app.config['TEST_DATA']['college_id'])
        beta = College(name='Beta College', code='BETA')
        db.session.add(beta)
        db.session.commit()

        alpha_ref = LeaveRequest.generate_ref(alpha)
        beta_ref = LeaveRequest.generate_ref(beta)

        assert alpha_ref.startswith('LV-ALPHA-')
        assert beta_ref.startswith('LV-BETA-')


def test_same_id_card_number_can_exist_in_different_colleges(app):
    with app.app_context():
        alpha_student_id = app.config['TEST_DATA']['student_profile_id']
        alpha_college_id = app.config['TEST_DATA']['college_id']

        alpha_card = StudentIDCard(
            college_id=alpha_college_id,
            student_id=alpha_student_id,
            card_number='SHARED-CARD-001',
            status='approved',
        )
        db.session.add(alpha_card)
        db.session.flush()

        beta = College(name='Beta College', code='BETA')
        db.session.add(beta)
        db.session.flush()

        beta_dept = Department(college_id=beta.id, name='Business', code='BBA')
        db.session.add(beta_dept)
        db.session.flush()

        beta_user = User(
            college_id=beta.id,
            name='Beta Student',
            email='beta.card@example.com',
            role='student',
        )
        beta_user.set_password('Password@123')
        db.session.add(beta_user)
        db.session.flush()

        beta_student = Student(
            college_id=beta.id,
            user_id=beta_user.id,
            roll_number='BBA-001',
            department_id=beta_dept.id,
            semester=1,
        )
        db.session.add(beta_student)
        db.session.flush()

        beta_card = StudentIDCard(
            college_id=beta.id,
            student_id=beta_student.id,
            card_number='SHARED-CARD-001',
            status='approved',
        )
        db.session.add(beta_card)
        db.session.commit()

        assert beta_card.id is not None


def test_same_fee_receipt_number_can_exist_in_different_colleges(app):
    with app.app_context():
        alpha_student = db.session.get(Student, app.config['TEST_DATA']['student_profile_id'])
        alpha_structure = FeeStructure(
            college_id=alpha_student.college_id,
            title='Alpha Fee',
            department_id=alpha_student.department_id,
            semester=alpha_student.semester,
            academic_year='2026-27',
            amount=1000,
        )
        db.session.add(alpha_structure)
        db.session.flush()

        alpha_payment = FeePayment(
            college_id=alpha_student.college_id,
            student_id=alpha_student.id,
            fee_structure_id=alpha_structure.id,
            amount_paid=1000,
            receipt_no='RCT-SHARED-001',
        )
        db.session.add(alpha_payment)
        db.session.flush()

        beta = College(name='Gamma College', code='GAMMA')
        db.session.add(beta)
        db.session.flush()

        beta_dept = Department(college_id=beta.id, name='Science', code='SCI')
        db.session.add(beta_dept)
        db.session.flush()

        beta_user = User(
            college_id=beta.id,
            name='Gamma Student',
            email='gamma.fee@example.com',
            role='student',
        )
        beta_user.set_password('Password@123')
        db.session.add(beta_user)
        db.session.flush()

        beta_student = Student(
            college_id=beta.id,
            user_id=beta_user.id,
            roll_number='SCI-201',
            department_id=beta_dept.id,
            semester=1,
        )
        db.session.add(beta_student)
        db.session.flush()

        beta_structure = FeeStructure(
            college_id=beta.id,
            title='Gamma Fee',
            department_id=beta_dept.id,
            semester=1,
            academic_year='2026-27',
            amount=1200,
        )
        db.session.add(beta_structure)
        db.session.flush()

        beta_payment = FeePayment(
            college_id=beta.id,
            student_id=beta_student.id,
            fee_structure_id=beta_structure.id,
            amount_paid=1200,
            receipt_no='RCT-SHARED-001',
        )
        db.session.add(beta_payment)
        db.session.commit()

        assert beta_payment.id is not None


def test_student_sidebar_uses_quick_access_and_more_tools(app, client):
    login(client, 'student1@example.com', college_code=app.config['TEST_DATA']['college_code'])

    response = client.get('/student/dashboard')
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'Quick Access' in page
    assert 'More Tools' in page
    assert 'data-nav-group="quick" data-nav-key="dashboard"' in page
    assert 'data-nav-group="more" data-nav-key="academic_calendar"' in page


def test_user_can_pin_optional_sidebar_tool(app, client):
    login(client, 'student1@example.com', college_code=app.config['TEST_DATA']['college_code'])

    response = client.post(
        '/preferences/sidebar',
        data={'pinned_features': ['academic_calendar']},
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'Quick access updated.' in page
    assert 'data-nav-group="quick" data-nav-key="academic_calendar"' in page
    assert 'data-nav-group="more" data-nav-key="academic_calendar"' not in page

    with app.app_context():
        student_user = User.query.filter_by(email='student1@example.com').first()
        assert student_user.get_sidebar_pin_keys() == ['academic_calendar']


def test_user_can_directly_unpin_sidebar_tool(app, client):
    with app.app_context():
        student_user = User.query.filter_by(email='student1@example.com').first()
        student_user.set_sidebar_pin_keys(['academic_calendar'])
        db.session.commit()

    login(client, 'student1@example.com')
    response = client.post(
        '/preferences/sidebar/toggle',
        data={'feature_key': 'academic_calendar'},
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-nav-group="quick" data-nav-key="academic_calendar"' not in page
    assert 'data-nav-group="more" data-nav-key="academic_calendar"' in page

    with app.app_context():
        student_user = User.query.filter_by(email='student1@example.com').first()
        assert student_user.get_sidebar_pin_keys() == []


def test_user_can_enable_optional_dashboard_widget(app, client):
    login(client, 'student1@example.com')

    before = client.get('/student/dashboard')
    before_page = before.get_data(as_text=True)
    assert before.status_code == 200
    assert 'Live Location Sharing' not in before_page

    after = client.post(
        '/preferences/dashboard',
        data={'dashboard_widgets': ['location_sharing']},
        follow_redirects=True,
    )
    after_page = after.get_data(as_text=True)

    assert after.status_code == 200
    assert 'Dashboard widgets updated.' in after_page
    assert 'Live Location Sharing' in after_page

    with app.app_context():
        student_user = User.query.filter_by(email='student1@example.com').first()
        assert student_user.get_dashboard_widget_keys() == ['location_sharing']


def test_dashboard_widget_order_is_saved_in_request_order(app, client):
    login(client, 'student1@example.com')

    response = client.post(
        '/preferences/dashboard',
        data={'dashboard_widgets': ['notices', 'location_sharing', 'fee_status']},
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        student_user = User.query.filter_by(email='student1@example.com').first()
        assert student_user.get_dashboard_widget_keys() == [
            'notices',
            'location_sharing',
            'fee_status',
        ]


def test_student_calendar_shows_matching_semester_events_only(app, client):
    college_id = app.config['TEST_DATA']['college_id']
    with app.app_context():
        db.session.add_all([
            AcademicCalendarEvent(
                college_id=college_id,
                title='Semester 1 Orientation',
                category='event',
                start_date=date(2026, 5, 4),
                end_date=date(2026, 5, 4),
                department_id=1,
                semester=1,
            ),
            AcademicCalendarEvent(
                college_id=college_id,
                title='Semester 2 Only Event',
                category='event',
                start_date=date(2026, 5, 5),
                end_date=date(2026, 5, 5),
                department_id=1,
                semester=2,
            ),
        ])
        db.session.commit()

    login(client, 'student1@example.com')
    response = client.get('/calendar?year=2026&month=5')

    assert response.status_code == 200
    assert b'Semester 1 Orientation' in response.data
    assert b'Semester 2 Only Event' not in response.data


def test_parent_calendar_uses_linked_child_scope(app, client):
    college_id = app.config['TEST_DATA']['college_id']
    with app.app_context():
        db.session.add_all([
            AcademicCalendarEvent(
                college_id=college_id,
                title='Parent Visible Holiday',
                category='holiday',
                start_date=date(2026, 5, 6),
                end_date=date(2026, 5, 6),
                department_id=1,
                semester=1,
            ),
            AcademicCalendarEvent(
                college_id=college_id,
                title='Hidden Semester Event',
                category='event',
                start_date=date(2026, 5, 7),
                end_date=date(2026, 5, 7),
                department_id=1,
                semester=3,
            ),
        ])
        db.session.commit()

    login(client, 'parent1@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.get('/calendar?year=2026&month=5')

    assert response.status_code == 200
    assert b'Parent Visible Holiday' in response.data
    assert b'Hidden Semester Event' not in response.data


def test_student_can_submit_assignment(app, client):
    login(client, 'student1@example.com')
    assignment_id = app.config['TEST_DATA']['assignment_id']

    response = client.post(
        f'/student/assignments/{assignment_id}/submit',
        data={
            'submission_text': 'Completed all questions.',
            'submission_file': (io.BytesIO(b'print("done")\n'), 'solution.txt'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Assignment submitted successfully' in response.data

    with app.app_context():
        submission = AssignmentSubmission.query.filter_by(content_id=assignment_id).first()
        assert submission is not None
        assert submission.submission_text == 'Completed all questions.'
        assert submission.status == 'submitted'
        assert submission.file_path.endswith('.txt')


def test_teacher_can_review_assignment_submission(app, client):
    assignment_id = app.config['TEST_DATA']['assignment_id']
    student_id = app.config['TEST_DATA']['student_profile_id']

    with app.app_context():
        college_id = app.config['TEST_DATA']['college_id']
        submission = AssignmentSubmission(
            college_id=college_id,
            content_id=assignment_id,
            student_id=student_id,
            submission_text='My first draft',
        )
        db.session.add(submission)
        db.session.commit()
        submission_id = submission.id

    login(client, 'teacher1@example.com')
    response = client.post(
        f'/teacher/assignments/submissions/{submission_id}/grade',
        data={
            'marks_awarded': '18',
            'feedback': 'Clear work. Improve the final explanation.',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Review saved for Student One.' in response.data

    with app.app_context():
        submission = db.session.get(AssignmentSubmission, submission_id)
        assert submission.status == 'reviewed'
        assert submission.marks_awarded == 18
        assert submission.feedback == 'Clear work. Improve the final explanation.'


def test_parent_can_view_child_assignment_results(app, client):
    assignment_id = app.config['TEST_DATA']['assignment_id']
    student_id = app.config['TEST_DATA']['student_profile_id']

    with app.app_context():
        college_id = app.config['TEST_DATA']['college_id']
        submission = AssignmentSubmission(
            college_id=college_id,
            content_id=assignment_id,
            student_id=student_id,
            submission_text='Submitted from test fixture',
            status='reviewed',
            marks_awarded=17,
            feedback='Good effort',
        )
        db.session.add(submission)
        db.session.commit()

    login(client, 'parent1@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.get(f'/parent/assignments?child_id={student_id}')

    assert response.status_code == 200
    assert b'Week 1 Assignment' in response.data
    assert b'Reviewed' in response.data
    assert b'17/20' in response.data


def test_teacher_can_preview_student_submission(app, client):
    assignment_id = app.config['TEST_DATA']['assignment_id']
    student_id = app.config['TEST_DATA']['student_profile_id']

    with app.app_context():
        college_id = app.config['TEST_DATA']['college_id']
        submission = AssignmentSubmission(
            college_id=college_id,
            content_id=assignment_id,
            student_id=student_id,
            submission_text='Preview this submission in the app.',
            file_path='uploads/submissions/preview.txt',
        )
        db.session.add(submission)
        db.session.commit()
        submission_id = submission.id

    abs_path = os.path.join(app.config['ASSIGNMENT_UPLOAD_FOLDER'], 'preview.txt')
    with open(abs_path, 'w', encoding='utf-8') as handle:
        handle.write('student preview file body')

    login(client, 'teacher1@example.com')
    response = client.get(f'/teacher/assignments/submissions/{submission_id}/preview')

    assert response.status_code == 200
    assert b'Student Submission Preview' in response.data
    assert b'Preview this submission in the app.' in response.data
    assert b'student preview file body' in response.data


def test_teacher_can_save_and_open_next_unreviewed_submission(app, client):
    assignment_id = app.config['TEST_DATA']['assignment_id']
    first_student_id = app.config['TEST_DATA']['student_profile_id']

    with app.app_context():
        first_student = db.session.get(Student, first_student_id)
        second_user = User(
            college_id=first_student.college_id,
            name='Student Two',
            email='student2@example.com',
            role='student',
        )
        second_user.set_password('Password@123')
        db.session.add(second_user)
        db.session.flush()
        second_student = Student(
            college_id=first_student.college_id,
            user_id=second_user.id,
            roll_number='CS-002',
            department_id=first_student.department_id,
            semester=first_student.semester,
        )
        db.session.add(second_student)
        db.session.flush()

        first_submission = AssignmentSubmission(
            college_id=first_student.college_id,
            content_id=assignment_id,
            student_id=first_student_id,
            submission_text='First submission in queue',
        )
        second_submission = AssignmentSubmission(
            college_id=second_student.college_id,
            content_id=assignment_id,
            student_id=second_student.id,
            submission_text='Second submission in queue',
        )
        db.session.add_all([first_submission, second_submission])
        db.session.commit()
        first_submission_id = first_submission.id
        second_submission_id = second_submission.id

    login(client, 'teacher1@example.com')
    response = client.post(
        f'/teacher/assignments/submissions/{first_submission_id}/grade',
        data={
            'return_to_preview': '1',
            'next_submission_id': str(second_submission_id),
            'go_next': '1',
            'marks_awarded': '19',
            'feedback': 'Reviewed quickly',
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Opening the next unreviewed submission' in response.data
    assert b'Student Two' in response.data
    assert b'Second submission in queue' in response.data

    with app.app_context():
        first_submission = db.session.get(AssignmentSubmission, first_submission_id)
        assert first_submission.status == 'reviewed'
        assert first_submission.marks_awarded == 19


def test_notice_feed_returns_role_visible_items(app, client):
    college_id = app.config['TEST_DATA']['college_id']
    with app.app_context():
        student_notice = Notice(
            college_id=college_id,
            title='Student Alert',
            content='Visible in the live bell feed.',
            category='urgent',
            target_role='student',
            author_id=app.config['TEST_DATA']['teacher_user_id'],
        )
        teacher_notice = Notice(
            college_id=college_id,
            title='Teacher Alert',
            content='Should stay hidden from students.',
            category='general',
            target_role='teacher',
            author_id=app.config['TEST_DATA']['teacher_user_id'],
        )
        db.session.add_all([student_notice, teacher_notice])
        db.session.commit()

    login(client, 'student1@example.com')
    response = client.get('/notices/feed')

    assert response.status_code == 200
    payload = response.get_json()
    titles = {item['title'] for item in payload['items']}
    assert 'Student Alert' in titles
    assert 'Teacher Alert' not in titles


def test_opening_notice_marks_notification_as_read(app, client):
    college_id = app.config['TEST_DATA']['college_id']
    with app.app_context():
        notice = Notice(
            college_id=college_id,
            title='Read Me',
            content='This should be marked read after opening.',
            category='general',
            target_role='student',
            author_id=app.config['TEST_DATA']['teacher_user_id'],
        )
        db.session.add(notice)
        db.session.commit()
        notice_id = notice.id

    login(client, 'student1@example.com')

    before = client.get('/notices/feed')
    assert before.status_code == 200
    before_payload = before.get_json()
    assert any(item['id'] == notice_id and item['is_read'] is False for item in before_payload['items'])
    unread_before = before_payload['count']

    detail = client.get(f'/notices/{notice_id}')
    assert detail.status_code == 200

    after = client.get('/notices/feed')
    assert after.status_code == 200
    after_payload = after.get_json()
    assert any(item['id'] == notice_id and item['is_read'] is True for item in after_payload['items'])
    assert after_payload['count'] == max(unread_before - 1, 0)

    with app.app_context():
        receipt = NoticeRead.query.filter_by(
            notice_id=notice_id,
            user_id=app.config['TEST_DATA']['student_user_id'],
        ).first()
        assert receipt is not None


def test_mark_all_notifications_as_read_from_bell(app, client):
    college_id = app.config['TEST_DATA']['college_id']
    with app.app_context():
        first_notice = Notice(
            college_id=college_id,
            title='Bell First',
            content='First unread bell item.',
            category='general',
            target_role='student',
            author_id=app.config['TEST_DATA']['teacher_user_id'],
        )
        second_notice = Notice(
            college_id=college_id,
            title='Bell Second',
            content='Second unread bell item.',
            category='urgent',
            target_role='student',
            author_id=app.config['TEST_DATA']['teacher_user_id'],
        )
        db.session.add_all([first_notice, second_notice])
        db.session.commit()
        first_id = first_notice.id
        second_id = second_notice.id

    login(client, 'student1@example.com')
    response = client.post(
        '/notices/mark-all-read',
        headers={'Accept': 'application/json'},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['count'] == 0
    assert any(item['id'] == first_id and item['is_read'] is True for item in payload['items'])
    assert any(item['id'] == second_id and item['is_read'] is True for item in payload['items'])

    with app.app_context():
        receipts = NoticeRead.query.filter(
            NoticeRead.user_id == app.config['TEST_DATA']['student_user_id'],
            NoticeRead.notice_id.in_([first_id, second_id]),
        ).all()
        assert len(receipts) == 2


def test_delete_read_notifications_removes_them_from_bell_only(app, client):
    college_id = app.config['TEST_DATA']['college_id']
    with app.app_context():
        notice = Notice(
            college_id=college_id,
            title='Delete From Tray',
            content='This read notice should disappear from the bell only.',
            category='general',
            target_role='student',
            author_id=app.config['TEST_DATA']['teacher_user_id'],
        )
        db.session.add(notice)
        db.session.commit()
        notice_id = notice.id

    login(client, 'student1@example.com')
    client.get(f'/notices/{notice_id}')

    response = client.post(
        '/notices/delete-read',
        headers={'Accept': 'application/json'},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert all(item['id'] != notice_id for item in payload['items'])

    with app.app_context():
        receipt = NoticeRead.query.filter_by(
            notice_id=notice_id,
            user_id=app.config['TEST_DATA']['student_user_id'],
        ).first()
        assert receipt is not None
        assert receipt.dismissed_at is not None

        stored_notice = db.session.get(Notice, notice_id)
        assert stored_notice is not None


def test_admin_file_manager_lists_legacy_file_and_previews_in_app(app, client):
    legacy_dir = os.path.join(app.root_path, 'static', 'uploads', 'content')
    os.makedirs(legacy_dir, exist_ok=True)
    filename = 'legacy-preview.txt'
    abs_path = os.path.join(legacy_dir, filename)

    with open(abs_path, 'w', encoding='utf-8') as handle:
        handle.write('legacy file preview body')

    try:
        login(client, 'admin@example.com')

        listing = client.get('/admin/files')
        assert listing.status_code == 200
        assert b'legacy-preview.txt' in listing.data

        preview = client.get(f'/admin/files/preview?rel=uploads/content/{filename}')
        assert preview.status_code == 200
        assert b'legacy file preview body' in preview.data
    finally:
        if os.path.exists(abs_path):
            os.remove(abs_path)


def test_login_requires_college_code_when_multiple_colleges_exist(app, client):
    with app.app_context():
        from models import College

        db.session.add(College(name='Beta College', code='BETA'))
        db.session.commit()

    response = client.post(
        '/login',
        data={'email': 'student1@example.com', 'password': 'Password@123'},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b'Enter a valid college code to continue.' in response.data

    success = client.post(
        '/login',
        data={
            'college_code': app.config['TEST_DATA']['college_code'],
            'email': 'student1@example.com',
            'password': 'Password@123',
        },
        follow_redirects=False,
    )

    assert success.status_code == 302
    assert '/student/dashboard' in success.headers['Location']


def test_super_admin_can_login_without_college_code(app, client):
    response = client.post(
        '/login',
        data={
            'email': 'superadmin@example.com',
            'password': 'Password@123',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert '/super-admin/dashboard' in response.headers['Location']


def test_private_lan_login_page_redirects_to_public_https_url(app, client):
    with app.app_context():
        app.config['PUBLIC_BASE_URL'] = 'https://portal.smartattend.test'

    response = client.get(
        '/login',
        base_url='http://192.168.1.81:8081',
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers['Location'] == 'https://portal.smartattend.test/login'


def test_student_dashboard_hides_other_college_notice(app, client):
    with app.app_context():
        from models import College

        other_college = College(name='Beta College', code='BETA')
        db.session.add(other_college)
        db.session.flush()

        foreign_notice = Notice(
            college_id=other_college.id,
            title='Foreign College Notice',
            content='Should not appear on Alpha student dashboard.',
            category='general',
            target_role='student',
            author_id=app.config['TEST_DATA']['teacher_user_id'],
        )
        db.session.add(foreign_notice)
        db.session.commit()

    login(client, 'student1@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.get('/student/dashboard')

    assert response.status_code == 200
    assert b'Foreign College Notice' not in response.data


def test_parent_dashboard_hides_other_college_notice(app, client):
    with app.app_context():
        from models import College

        other_college = College(name='Gamma College', code='GAMMA')
        db.session.add(other_college)
        db.session.flush()

        foreign_notice = Notice(
            college_id=other_college.id,
            title='Gamma Parent Alert',
            content='Should not appear for Alpha parent users.',
            category='general',
            target_role='student',
            author_id=app.config['TEST_DATA']['teacher_user_id'],
        )
        db.session.add(foreign_notice)
        db.session.commit()

    login(client, 'parent1@example.com', college_code=app.config['TEST_DATA']['college_code'])
    response = client.get('/parent/dashboard')

    assert response.status_code == 200
    assert b'Gamma Parent Alert' not in response.data
