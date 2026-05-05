import io
import os
from datetime import date

from extensions import db
from models.academic_calendar import AcademicCalendarEvent
from models.assignment import AssignmentSubmission
from models.college import College
from models.content import TeacherContent
from models.department import Department
from models.fee import FeePayment, FeeStructure
from models.id_card import IDCardTemplate, StudentIDCard
from models.leave import LeaveRequest
from models.notice import Notice
from models.notice_read import NoticeRead
from models.student import Student
from models.user import User


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


def test_admin_system_setup_page_loads(app, client):
    login(client, 'admin@example.com', college_code=app.config['TEST_DATA']['college_code'])

    response = client.get('/admin/system-setup')

    assert response.status_code == 200
    assert b'Production Readiness' in response.data
    assert b'Launch Checklist' in response.data


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
