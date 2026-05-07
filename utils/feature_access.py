from __future__ import annotations

from collections import OrderedDict

from flask import g, has_request_context

from extensions import db
from models.college_feature import CollegeFeatureAccess


FEATURE_GROUPS = OrderedDict(
    [
        (
            'academic',
            {
                'label': 'Academic Modules',
                'description': 'Core teaching, attendance, and academic delivery features.',
                'features': [
                    'attendance',
                    'learning_content',
                    'exams',
                    'notices',
                    'calendar',
                    'timetable',
                    'leaves',
                    'batch_tracker',
                ],
            },
        ),
        (
            'operations',
            {
                'label': 'College Operations',
                'description': 'Operational modules used by the college office and college admin.',
                'features': [
                    'fees',
                    'fee_reminders',
                    'parent_portal',
                    'digital_id_cards',
                    'analytics',
                    'file_manager',
                    'report_emails',
                ],
            },
        ),
        (
            'advanced',
            {
                'label': 'Advanced Services',
                'description': 'Optional advanced platform capabilities that not every college needs.',
                'features': [
                    'face_biometrics',
                    'live_location',
                    'ai_assistant',
                ],
            },
        ),
    ]
)


FEATURE_CATALOG = {
    'attendance': {
        'label': 'Attendance',
        'description': 'Live sessions, attendance history, teacher reports, and attendance analytics.',
    },
    'learning_content': {
        'label': 'Learning Content',
        'description': 'Notes, assignments, content preview, submissions, and teacher grading workflows.',
    },
    'exams': {
        'label': 'Exams & Marksheets',
        'description': 'Exam setup, marks entry, results, and printable marksheets.',
    },
    'notices': {
        'label': 'Notice Board',
        'description': 'Notice board, notification bell, and notice feed visibility.',
    },
    'calendar': {
        'label': 'Academic Calendar',
        'description': 'Holidays, exam weeks, and calendar events.',
    },
    'timetable': {
        'label': 'Timetable',
        'description': 'Class schedule and timetable management.',
    },
    'leaves': {
        'label': 'Leave Management',
        'description': 'Student and teacher leave requests and approvals.',
    },
    'fees': {
        'label': 'Fees',
        'description': 'Fee structures, due tracking, payment history, and fee reports.',
    },
    'fee_reminders': {
        'label': 'Fee Reminder Emails',
        'description': 'Automated daily email reminders to students and parents for upcoming, due-today, and overdue fees.',
    },
    'parent_portal': {
        'label': 'Parent Portal',
        'description': 'Parent accounts, linked child access, and parent-facing dashboards.',
    },
    'digital_id_cards': {
        'label': 'Digital ID Cards',
        'description': 'ID card template management, approvals, and student ID card access.',
    },
    'analytics': {
        'label': 'Analytics',
        'description': 'College-wide attendance and performance analytics.',
    },
    'file_manager': {
        'label': 'File Manager',
        'description': 'Admin file preview, cleanup, and legacy/private storage review.',
    },
    'face_biometrics': {
        'label': 'Face Biometrics',
        'description': 'Face enrollment, liveness, and biometric attendance setup.',
    },
    'live_location': {
        'label': 'Live Location',
        'description': 'Student location sharing and parent live location access.',
    },
    'batch_tracker': {
        'label': 'Batch Tracker',
        'description': 'Admission-year batch management, expected semester tracking, semester date schedules, and bulk student promotion.',
    },
    'report_emails': {
        'label': 'Automated Report Emails',
        'description': 'Configurable weekly attendance email reports to students and parents, with department, semester, and admission-year filters.',
    },
    'ai_assistant': {
        'label': 'AI Assistant',
        'description': 'Contextual AI chatbot with live database access. Answers questions about students, attendance, notes, and college data.',
    },
}


FEATURE_PRESETS = OrderedDict(
    [
        (
            'starter',
            {
                'label': 'Starter',
                'icon': 'bi-rocket-takeoff',
                'color': 'secondary',
                'description': 'Core essentials for a college just getting started — attendance, notices, calendar, and timetable.',
                'features': [
                    'attendance',
                    'notices',
                    'calendar',
                    'timetable',
                ],
            },
        ),
        (
            'standard',
            {
                'label': 'Standard',
                'icon': 'bi-award',
                'color': 'primary',
                'description': 'Full academic experience — adds learning content, exams, leaves, batch tracking, report emails, and digital ID cards.',
                'features': [
                    'attendance',
                    'notices',
                    'calendar',
                    'timetable',
                    'learning_content',
                    'exams',
                    'leaves',
                    'batch_tracker',
                    'report_emails',
                    'digital_id_cards',
                ],
            },
        ),
        (
            'professional',
            {
                'label': 'Professional',
                'icon': 'bi-gem',
                'color': 'success',
                'description': 'Everything in Standard plus fees, parent portal, analytics, and AI assistant.',
                'features': [
                    'attendance',
                    'notices',
                    'calendar',
                    'timetable',
                    'learning_content',
                    'exams',
                    'leaves',
                    'batch_tracker',
                    'report_emails',
                    'digital_id_cards',
                    'fees',
                    'fee_reminders',
                    'parent_portal',
                    'analytics',
                    'ai_assistant',
                ],
            },
        ),
        (
            'enterprise',
            {
                'label': 'Enterprise',
                'icon': 'bi-stars',
                'color': 'warning',
                'description': 'All 17 modules unlocked — includes biometrics, live location, and file manager.',
                'features': list(FEATURE_CATALOG.keys()),
            },
        ),
    ]
)


NAV_ITEM_FEATURES = {
    'admin': {
        'notice_board': 'notices',
        'academic_calendar': 'calendar',
        'sessions': 'attendance',
        'analytics': 'analytics',
        'leave_management': 'leaves',
        'file_manager': 'file_manager',
        'timetable': 'timetable',
        'exams': 'exams',
        'marksheets': 'exams',
        'signatures': 'exams',
        'fees': 'fees',
        'parents': 'parent_portal',
        'digital_id_cards': 'digital_id_cards',
        'batch_tracker': 'batch_tracker',
        'semester_schedules': 'batch_tracker',
    },
    'teacher': {
        'attendance_sessions': 'attendance',
        'content_manager': 'learning_content',
        'notice_board': 'notices',
        'academic_calendar': 'calendar',
        'leave_management': 'leaves',
        'reports': 'attendance',
        'timetable': 'timetable',
        'exams_marks': 'exams',
    },
    'student': {
        'my_attendance': 'attendance',
        'study_materials': 'learning_content',
        'my_results': 'exams',
        'notice_board': 'notices',
        'leave_applications': 'leaves',
        'face_enrollment': 'face_biometrics',
        'academic_calendar': 'calendar',
        'timetable': 'timetable',
        'marksheet': 'exams',
        'fees': 'fees',
        'my_id_card': 'digital_id_cards',
    },
    'parent': {
        'dashboard': 'parent_portal',
        'assignments': 'learning_content',
        'marksheets': 'exams',
        'notice_board': 'notices',
        'academic_calendar': 'calendar',
    },
}


DASHBOARD_WIDGET_FEATURES = {
    'admin': {
        'attendance_trend': 'attendance',
        'recent_notices': 'notices',
        'recent_sessions': 'attendance',
        'department_attendance': 'attendance',
        'upcoming_exams': 'exams',
        'fee_collection': 'fees',
    },
    'teacher': {
        'active_session': 'attendance',
        'start_session': 'attendance',
        'recent_sessions': 'attendance',
        'notice_board': 'notices',
        'upcoming_exams': 'exams',
    },
    'student': {
        'subject_attendance': 'attendance',
        'recent_attendance': 'attendance',
        'location_sharing': 'live_location',
        'low_attendance_alert': 'attendance',
        'upcoming_exams': 'exams',
        'fee_status': 'fees',
        'notices': 'notices',
    },
    'parent': {
        'children_overview': 'parent_portal',
        'college_notices': 'notices',
    },
}


ENDPOINT_PREFIX_FEATURES = (
    ('notice.', {'notices'}),
    ('calendar.', {'calendar'}),
    ('exam.', {'exams'}),
    ('fee.', {'fees'}),
    ('leave.', {'leaves'}),
    ('timetable.', {'timetable'}),
    ('ai.', {'ai_assistant'}),
)


ENDPOINT_FEATURES = {
    'admin.sessions': {'attendance'},
    'admin.cancel_session': {'attendance'},
    'admin.student_attendance': {'attendance'},
    'admin.trigger_class_alerts': {'attendance'},
    'admin.analytics': {'analytics'},
    'admin.parents': {'parent_portal'},
    'admin.add_parent': {'parent_portal'},
    'admin.link_parent_child': {'parent_portal'},
    'admin.unlink_parent_child': {'parent_portal'},
    'admin.delete_parent': {'parent_portal'},
    'admin.id_card_template': {'digital_id_cards'},
    'admin.id_cards': {'digital_id_cards'},
    'admin.approve_id_card': {'digital_id_cards'},
    'admin.reject_id_card': {'digital_id_cards'},
    'admin.view_id_card': {'digital_id_cards'},
    'admin.file_manager': {'file_manager'},
    'admin.delete_file': {'file_manager'},
    'admin.bulk_delete_files': {'file_manager'},
    'admin.view_file': {'file_manager'},
    'admin.preview_file': {'file_manager'},
    # Batch Tracker
    'admin.batch_overview': {'batch_tracker'},
    'admin.batch_promote': {'batch_tracker'},
    'admin.semester_schedules': {'batch_tracker'},
    'admin.save_semester_schedule': {'batch_tracker'},
    'admin.delete_semester_schedule': {'batch_tracker'},
    'admin.preview_student_id': {'batch_tracker'},
    # Report Emails
    'admin.save_report_schedule': {'report_emails'},
    'admin.send_weekly_report_now': {'report_emails'},
    # Fee Reminders
    'fee.save_fee_reminder_config': {'fees', 'fee_reminders'},
    'fee.send_fee_reminders_now': {'fees', 'fee_reminders'},
    'admin.marksheet_list': {'exams'},
    'admin.admin_marksheet': {'exams'},
    'admin.marksheet_signatures': {'exams'},
    'admin.save_marksheet_signature': {'exams'},
    'admin.delete_marksheet_signature': {'exams'},
    'teacher.sessions': {'attendance'},
    'teacher.start_session': {'attendance'},
    'teacher.live_attendance': {'attendance'},
    'teacher.process_frame': {'attendance'},
    'teacher.manual_mark': {'attendance'},
    'teacher.cancel_session': {'attendance'},
    'teacher.complete_session': {'attendance'},
    'teacher.session_status': {'attendance'},
    'teacher.print_session': {'attendance'},
    'teacher.reports': {'attendance'},
    'teacher.download_session_report': {'attendance'},
    'teacher.download_subject_report': {'attendance'},
    'teacher.content_file': {'learning_content'},
    'teacher.content_list': {'learning_content'},
    'teacher.content_create': {'learning_content'},
    'teacher.content_edit': {'learning_content'},
    'teacher.content_delete': {'learning_content'},
    'teacher.content_toggle': {'learning_content'},
    'teacher.content_preview': {'learning_content'},
    'teacher.assignment_review': {'learning_content'},
    'teacher.assignment_submission_file': {'learning_content'},
    'teacher.assignment_submission_preview': {'learning_content'},
    'teacher.assignment_grade': {'learning_content'},
    'student.my_attendance': {'attendance'},
    'student.download_attendance': {'attendance'},
    'student.enroll': {'face_biometrics'},
    'student.capture_face': {'face_biometrics'},
    'student.delete_face': {'face_biometrics'},
    'student.location_toggle': {'live_location'},
    'student.location_update': {'live_location'},
    'student.id_card': {'digital_id_cards'},
    'student.student_content': {'learning_content'},
    'student.content_file': {'learning_content'},
    'student.content_preview': {'learning_content'},
    'student.submit_assignment': {'learning_content'},
    'student.submission_file': {'learning_content'},
    'parent.dashboard': {'parent_portal'},
    'parent.child_detail': {'parent_portal'},
    'parent.child_location': {'parent_portal', 'live_location'},
    'parent.parent_marksheets': {'parent_portal', 'exams'},
    'parent.parent_marksheet': {'parent_portal', 'exams'},
    'parent.parent_assignments': {'parent_portal', 'learning_content'},
    'parent.parent_submission_file': {'parent_portal', 'learning_content'},
}


def feature_specs() -> list[dict]:
    specs = []
    for key, meta in FEATURE_CATALOG.items():
        group_key = next(
            (
                group
                for group, group_meta in FEATURE_GROUPS.items()
                if key in group_meta['features']
            ),
            'advanced',
        )
        specs.append({'key': key, 'group': group_key, **meta})
    return specs


def feature_count() -> int:
    return len(FEATURE_CATALOG)


def normalize_feature_keys(requested_keys) -> list[str]:
    keys = []
    for key in requested_keys or []:
        if key in FEATURE_CATALOG and key not in keys:
            keys.append(key)
    return keys


def preset_feature_keys(preset_key: str | None) -> list[str]:
    preset = FEATURE_PRESETS.get((preset_key or '').strip())
    if not preset:
        return list(FEATURE_CATALOG.keys())
    return normalize_feature_keys(preset['features'])


def _default_matrix() -> dict[str, bool]:
    return {key: True for key in FEATURE_CATALOG}


def _load_feature_matrix(college_id: int) -> dict[str, bool]:
    matrix = _default_matrix()
    rows = CollegeFeatureAccess.query.filter_by(college_id=college_id).all()
    for row in rows:
        if row.feature_key in matrix:
            matrix[row.feature_key] = bool(row.enabled)
    return matrix


def invalidate_feature_cache(college_id: int | None = None) -> None:
    if not has_request_context():
        return
    cache = getattr(g, '_college_feature_matrix_cache', None)
    if not cache:
        return
    if college_id is None:
        cache.clear()
    else:
        cache.pop(college_id, None)


def college_feature_matrix(college_id: int | None) -> dict[str, bool]:
    if college_id is None:
        return _default_matrix()

    if not has_request_context():
        return _load_feature_matrix(college_id)

    cache = getattr(g, '_college_feature_matrix_cache', None)
    if cache is None:
        cache = {}
        g._college_feature_matrix_cache = cache

    if college_id not in cache:
        cache[college_id] = _load_feature_matrix(college_id)

    return dict(cache[college_id])


def college_enabled_feature_count(college_id: int | None) -> int:
    return sum(1 for enabled in college_feature_matrix(college_id).values() if enabled)


def college_has_feature(college_or_id, feature_key: str) -> bool:
    if feature_key not in FEATURE_CATALOG:
        return True

    college_id = getattr(college_or_id, 'id', college_or_id)
    return college_feature_matrix(college_id).get(feature_key, True)


def user_has_feature(user, feature_key: str) -> bool:
    if getattr(user, 'role', None) == 'super_admin':
        return True
    return college_has_feature(getattr(user, 'college_id', None), feature_key)


def nav_item_is_enabled(user, item_key: str) -> bool:
    nav_role = 'admin' if getattr(user, 'role', None) == 'sub_admin' else getattr(user, 'role', None)
    feature_key = NAV_ITEM_FEATURES.get(nav_role, {}).get(item_key)
    if not feature_key:
        return True
    return user_has_feature(user, feature_key)


def dashboard_widget_is_enabled(user, widget_key: str) -> bool:
    feature_key = DASHBOARD_WIDGET_FEATURES.get(user.role, {}).get(widget_key)
    if not feature_key:
        return True
    return user_has_feature(user, feature_key)


def endpoint_required_features(endpoint: str | None) -> set[str]:
    if not endpoint:
        return set()

    direct = ENDPOINT_FEATURES.get(endpoint)
    if direct is not None:
        return set(direct)

    for prefix, features in ENDPOINT_PREFIX_FEATURES:
        if endpoint.startswith(prefix):
            return set(features)
    return set()


def endpoint_has_access(user, endpoint: str | None) -> bool:
    required = endpoint_required_features(endpoint)
    return all(user_has_feature(user, feature_key) for feature_key in required)


def feature_access_message(endpoint: str | None) -> str:
    required = endpoint_required_features(endpoint)
    if not required:
        return 'This module is not available for your college.'
    labels = [FEATURE_CATALOG[key]['label'] for key in required if key in FEATURE_CATALOG]
    if not labels:
        return 'This module is not available for your college.'
    if len(labels) == 1:
        return f'{labels[0]} is disabled for your college.'
    return f"{', '.join(labels[:-1])} and {labels[-1]} are disabled for your college."


def save_college_feature_access(college_id: int, enabled_keys) -> None:
    enabled = set(normalize_feature_keys(enabled_keys))
    existing = {
        row.feature_key: row
        for row in CollegeFeatureAccess.query.filter_by(college_id=college_id).all()
    }

    for feature_key in FEATURE_CATALOG:
        should_enable = feature_key in enabled
        row = existing.get(feature_key)
        if row is None:
            row = CollegeFeatureAccess(
                college_id=college_id,
                feature_key=feature_key,
                enabled=should_enable,
            )
            db.session.add(row)
        else:
            row.enabled = should_enable

    invalidate_feature_cache(college_id)
