from __future__ import annotations

import os

from extensions import db
from utils.file_preview import get_missing_preview_dependencies


def evaluate_production_setup(app, college=None) -> dict:
    from models.department import Department
    from models.id_card import IDCardTemplate
    from models.setting import CollegeSetting
    from models.student import Student
    from models.subject import Subject
    from models.teacher import Teacher

    checks: list[dict] = []
    warnings = 0
    failures = 0

    def add_check(*, key, label, passed, level='fail', detail='', action_endpoint=None, action_label=None):
        nonlocal warnings, failures
        status = 'pass' if passed else ('warning' if level == 'warn' else 'fail')
        if status == 'warning':
            warnings += 1
        elif status == 'fail':
            failures += 1
        checks.append({
            'key': key,
            'label': label,
            'status': status,
            'detail': detail,
            'action_endpoint': action_endpoint,
            'action_label': action_label,
        })

    secret_key = app.config.get('SECRET_KEY', '')
    add_check(
        key='secret_key',
        label='Strong secret key configured',
        passed=bool(secret_key and len(secret_key) >= 32),
        detail='Set a long random SECRET_KEY before going live.',
    )

    try:
        db.session.execute(db.text('SELECT 1'))
        db_ok = True
        db_detail = 'Database connection is healthy.'
    except Exception as exc:  # noqa: BLE001
        db_ok = False
        db_detail = f'Database connectivity failed: {exc}'
    add_check(
        key='database',
        label='Database connectivity',
        passed=db_ok,
        detail=db_detail,
    )

    add_check(
        key='allowed_hosts',
        label='Allowed hosts configured',
        passed=bool(app.config.get('ALLOWED_HOSTS')),
        detail='Set ALLOWED_HOSTS for your real domains.',
    )

    rate_limit_storage = app.config.get('RATELIMIT_STORAGE_URI', '')
    add_check(
        key='rate_limit',
        label='Shared rate-limit backend',
        passed=not rate_limit_storage.startswith('memory://'),
        detail='Use Redis or another shared backend instead of memory://.',
    )

    static_dir = os.path.abspath(app.static_folder or '')
    content_dir = os.path.abspath(app.config['CONTENT_UPLOAD_FOLDER'])
    assignment_dir = os.path.abspath(app.config['ASSIGNMENT_UPLOAD_FOLDER'])
    uploads_private = True
    try:
        if os.path.commonpath([content_dir, static_dir]) == static_dir:
            uploads_private = False
        if os.path.commonpath([assignment_dir, static_dir]) == static_dir:
            uploads_private = False
    except ValueError:
        uploads_private = False
    add_check(
        key='private_uploads',
        label='Private upload storage',
        passed=uploads_private,
        detail='Keep content and assignment uploads outside the public static directory.',
    )

    add_check(
        key='proxy_headers',
        label='Trusted proxy headers',
        passed=bool(app.config.get('TRUST_PROXY_HEADERS', True)),
        level='warn',
        detail='Enable TRUST_PROXY_HEADERS when the app is behind Nginx, Caddy, or a load balancer.',
    )

    log_dir = app.config.get('LOG_DIR')
    add_check(
        key='log_dir',
        label='Log directory present',
        passed=bool(log_dir and os.path.isdir(log_dir)),
        level='warn',
        detail='Create LOG_DIR on the server so rotated logs persist.',
    )

    missing_preview = get_missing_preview_dependencies()
    add_check(
        key='preview_deps',
        label='Preview dependencies installed',
        passed=not missing_preview,
        level='warn',
        detail='Install optional packages for DOCX/PPTX previews.' if missing_preview else 'All optional preview packages are available.',
    )

    if college is not None:
        cs = CollegeSetting.get(college)
        tpl = IDCardTemplate.get(college)
        college_id = college.id

        add_check(
            key='college_profile',
            label='College profile completed',
            passed=bool(cs.college_name and cs.college_name != 'My College' and cs.address),
            level='warn',
            detail='Set the real college name and address in settings.',
            action_endpoint='admin.settings',
            action_label='Open Settings',
        )
        add_check(
            key='college_location',
            label='College location pinned',
            passed=bool(cs.latitude is not None and cs.longitude is not None),
            level='warn',
            detail='Pick the college location on the map for parent location views and identity details.',
            action_endpoint='admin.settings',
            action_label='Set Location',
        )
        add_check(
            key='id_card_branding',
            label='ID card branding ready',
            passed=bool(tpl.logo_path and tpl.principal_signature_path and tpl.principal_name),
            level='warn',
            detail='Upload logo, principal signature, and principal name for official cards.',
            action_endpoint='admin.id_card_template',
            action_label='Configure ID Card',
        )
        add_check(
            key='departments',
            label='Departments added',
            passed=Department.query.filter_by(college_id=college_id).count() > 0,
            detail='Create at least one department before onboarding students and teachers.',
            action_endpoint='admin.departments',
            action_label='Manage Departments',
        )
        add_check(
            key='teachers',
            label='Teachers added',
            passed=Teacher.query.filter_by(college_id=college_id).count() > 0,
            detail='Add teacher accounts before attendance sessions and assignments can run.',
            action_endpoint='admin.teachers',
            action_label='Manage Teachers',
        )
        add_check(
            key='students',
            label='Students added',
            passed=Student.query.filter_by(college_id=college_id).count() > 0,
            detail='Add student records to use attendance, fees, exams, and ID cards.',
            action_endpoint='admin.students',
            action_label='Manage Students',
        )
        add_check(
            key='subjects',
            label='Subjects configured',
            passed=Subject.query.filter_by(college_id=college_id).count() > 0,
            detail='Create subjects so attendance, exams, and content publishing are usable.',
            action_endpoint='admin.subjects',
            action_label='Manage Subjects',
        )

    total_checks = len(checks)
    passed_checks = sum(1 for item in checks if item['status'] == 'pass')
    progress = int(round((passed_checks / total_checks) * 100)) if total_checks else 100

    return {
        'checks': checks,
        'failures': failures,
        'warnings': warnings,
        'passed': passed_checks,
        'total': total_checks,
        'progress': progress,
        'is_ready': failures == 0,
    }
