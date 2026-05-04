import io
import os

from extensions import db
from models.content import TeacherContent


def login(client, email, password='Password@123'):
    return client.post(
        '/login',
        data={'email': email, 'password': password},
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
    login(client, 'student1@example.com')

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

    login(client, 'student1@example.com')
    response = client.get(f'/student/content/{content_id}/file?download=0')

    assert response.status_code == 200
    assert response.data == b'private note body'
