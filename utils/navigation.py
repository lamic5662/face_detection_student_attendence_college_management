from __future__ import annotations

from flask import url_for

from extensions import db
from models.id_card import StudentIDCard
from models.leave import LeaveRequest
from models.subject import Subject
from utils.feature_access import nav_item_is_enabled
from utils.subadmin import nav_key_visible_for_subadmin, subadmin_visible_modules


PIN_LIMIT = 4


NAV_ITEMS = {
    'super_admin': [
        {
            'key': 'dashboard',
            'label': 'Dashboard',
            'icon': 'bi-speedometer2',
            'endpoint': 'super_admin.dashboard',
            'description': 'Platform overview across all colleges.',
            'section': 'core',
        },
        {
            'key': 'system_setup',
            'label': 'System Setup',
            'icon': 'bi-shield-check',
            'endpoint': 'super_admin.system_setup',
            'description': 'Platform production readiness and checks.',
            'section': 'core',
        },
        {
            'key': 'colleges',
            'label': 'Colleges',
            'icon': 'bi-buildings-fill',
            'endpoint': 'super_admin.colleges',
            'description': 'View tenant colleges and platform onboarding status.',
            'section': 'core',
        },
        {
            'key': 'audit_logs',
            'label': 'Audit Logs',
            'icon': 'bi-journal-text',
            'endpoint': 'super_admin.audit_logs',
            'description': 'Review platform-level admin actions and changes.',
            'section': 'more',
            'active_contains': ['audit_logs'],
        },
        {
            'key': 'user_guide',
            'label': 'User Guide',
            'icon': 'bi-book-fill',
            'endpoint': 'help.guide',
            'description': 'Built-in documentation and walkthroughs.',
            'section': 'more',
        },
    ],
    'admin': [
        {
            'key': 'dashboard',
            'label': 'Dashboard',
            'icon': 'bi-speedometer2',
            'endpoint': 'admin.dashboard',
            'description': 'System overview and recent activity.',
            'section': 'core',
        },
        {
            'key': 'students',
            'label': 'Students',
            'icon': 'bi-people-fill',
            'endpoint': 'admin.students',
            'description': 'Admissions, profiles, and records.',
            'section': 'core',
        },
        {
            'key': 'batch_tracker',
            'label': 'Batch Tracker',
            'icon': 'bi-bar-chart-steps',
            'endpoint': 'admin.batch_overview',
            'description': 'Track batch progress and promote students.',
            'section': 'core',
            'active_endpoints': ['admin.batch_overview', 'admin.batch_promote'],
        },
        {
            'key': 'semester_schedules',
            'label': 'Semester Schedules',
            'icon': 'bi-calendar2-range',
            'endpoint': 'admin.semester_schedules',
            'description': 'Set semester dates and send weekly reports.',
            'section': 'core',
            'active_endpoints': ['admin.semester_schedules', 'admin.save_semester_schedule',
                                 'admin.send_weekly_report_now'],
        },
        {
            'key': 'teachers',
            'label': 'Teachers',
            'icon': 'bi-person-badge-fill',
            'endpoint': 'admin.teachers',
            'description': 'Faculty accounts and assignments.',
            'section': 'core',
        },
        {
            'key': 'notice_board',
            'label': 'Notice Board',
            'icon': 'bi-megaphone-fill',
            'endpoint': 'notice.list_notices',
            'description': 'Post and manage announcements.',
            'section': 'core',
            'active_contains': ['notice'],
        },
        {
            'key': 'academic_calendar',
            'label': 'Academic Calendar',
            'icon': 'bi-calendar-event-fill',
            'endpoint': 'calendar.view_calendar',
            'description': 'Holidays, exam weeks, and events.',
            'section': 'core',
            'active_contains': ['calendar'],
        },
        {
            'key': 'subjects',
            'label': 'Subjects',
            'icon': 'bi-journal-bookmark-fill',
            'endpoint': 'admin.subjects',
            'description': 'Course list and ownership.',
            'section': 'more',
        },
        {
            'key': 'departments',
            'label': 'Departments',
            'icon': 'bi-building-fill',
            'endpoint': 'admin.departments',
            'description': 'Department structure and codes.',
            'section': 'more',
        },
        {
            'key': 'all_users',
            'label': 'All Users',
            'icon': 'bi-person-gear',
            'endpoint': 'admin.users',
            'description': 'Reset access and manage accounts.',
            'section': 'more',
        },
        {
            'key': 'sessions',
            'label': 'Sessions',
            'icon': 'bi-camera-video-fill',
            'endpoint': 'admin.sessions',
            'description': 'Monitor live and completed attendance sessions.',
            'section': 'more',
            'active_endpoints': ['admin.cancel_session'],
        },
        {
            'key': 'analytics',
            'label': 'Analytics',
            'icon': 'bi-bar-chart-fill',
            'endpoint': 'admin.analytics',
            'description': 'Attendance and performance insights.',
            'section': 'more',
        },
        {
            'key': 'leave_management',
            'label': 'Leave Management',
            'icon': 'bi-calendar-x-fill',
            'endpoint': 'leave.admin_leaves',
            'description': 'Review student and teacher leave requests.',
            'section': 'more',
            'active_contains': ['leave'],
        },
        {
            'key': 'file_manager',
            'label': 'File Manager',
            'icon': 'bi-folder2-open',
            'endpoint': 'admin.file_manager',
            'description': 'Preview and manage uploaded files.',
            'section': 'more',
            'active_endpoints': [
                'admin.delete_file',
                'admin.bulk_delete_files',
                'admin.preview_file',
                'admin.view_file',
            ],
        },
        {
            'key': 'timetable',
            'label': 'Timetable',
            'icon': 'bi-calendar3',
            'endpoint': 'timetable.view',
            'description': 'Weekly schedule and class timing.',
            'section': 'more',
            'active_contains': ['timetable'],
        },
        {
            'key': 'exams',
            'label': 'Exams',
            'icon': 'bi-journals',
            'endpoint': 'exam.admin_exams',
            'description': 'Exam setup and results management.',
            'section': 'more',
        },
        {
            'key': 'marksheets',
            'label': 'Marksheets',
            'icon': 'bi-award-fill',
            'endpoint': 'admin.marksheet_list',
            'description': 'Printable official marksheets.',
            'section': 'more',
            'active_endpoints': ['admin.admin_marksheet'],
        },
        {
            'key': 'signatures',
            'label': 'Signatures',
            'icon': 'bi-pen-fill',
            'endpoint': 'admin.marksheet_signatures',
            'description': 'Signature assets for official documents.',
            'section': 'more',
            'active_contains': ['marksheet_signature'],
        },
        {
            'key': 'fees',
            'label': 'Fees',
            'icon': 'bi-cash-stack',
            'endpoint': 'fee.admin_fees',
            'description': 'Fee structures and payments.',
            'section': 'more',
            'active_contains': ['fee'],
        },
        {
            'key': 'parents',
            'label': 'Parents',
            'icon': 'bi-house-heart-fill',
            'endpoint': 'admin.parents',
            'description': 'Linked parent accounts.',
            'section': 'more',
            'active_contains': ['parent'],
        },
        {
            'key': 'settings',
            'label': 'Settings',
            'icon': 'bi-gear-fill',
            'endpoint': 'admin.settings',
            'description': 'College-wide configuration.',
            'section': 'more',
            'active_endpoints': ['admin.save_settings'],
        },
        {
            'key': 'sub_admins',
            'label': 'Sub-Admins',
            'icon': 'bi-person-lock',
            'endpoint': 'admin.sub_admins',
            'description': 'Delegate access to staff with limited permissions.',
            'section': 'more',
            'active_endpoints': ['admin.add_sub_admin', 'admin.edit_sub_admin', 'admin.delete_sub_admin'],
        },
        {
            'key': 'digital_id_cards',
            'label': 'Digital ID Cards',
            'icon': 'bi-person-vcard-fill',
            'endpoint': 'admin.id_cards',
            'description': 'Approve and review student ID cards.',
            'section': 'more',
            'active_contains': ['id_card'],
        },
        {
            'key': 'user_guide',
            'label': 'User Guide',
            'icon': 'bi-book-fill',
            'endpoint': 'help.guide',
            'description': 'Built-in documentation and walkthroughs.',
            'section': 'more',
        },
    ],
    'teacher': [
        {
            'key': 'dashboard',
            'label': 'Dashboard',
            'icon': 'bi-speedometer2',
            'endpoint': 'teacher.dashboard',
            'description': 'Today’s classes and status.',
            'section': 'core',
        },
        {
            'key': 'attendance_sessions',
            'label': 'Attendance Sessions',
            'icon': 'bi-camera-video-fill',
            'endpoint': 'teacher.sessions',
            'description': 'Start and manage live attendance.',
            'section': 'core',
            'active_endpoints': [
                'teacher.start_session',
                'teacher.live_attendance',
                'teacher.process_frame',
                'teacher.manual_mark',
                'teacher.cancel_session',
                'teacher.complete_session',
                'teacher.session_status',
                'teacher.print_session',
            ],
            'active_contains': ['session'],
        },
        {
            'key': 'content_manager',
            'label': 'Content Manager',
            'icon': 'bi-collection-fill',
            'endpoint': 'teacher.content_list',
            'description': 'Notes, assignments, labs, and questions.',
            'section': 'core',
            'active_contains': ['content', 'assignment'],
        },
        {
            'key': 'notice_board',
            'label': 'Notice Board',
            'icon': 'bi-megaphone-fill',
            'endpoint': 'notice.list_notices',
            'description': 'Recent announcements and alerts.',
            'section': 'core',
            'active_contains': ['notice'],
        },
        {
            'key': 'academic_calendar',
            'label': 'Academic Calendar',
            'icon': 'bi-calendar-event-fill',
            'endpoint': 'calendar.view_calendar',
            'description': 'Events, holidays, and exam weeks.',
            'section': 'core',
            'active_contains': ['calendar'],
        },
        {
            'key': 'leave_management',
            'label': 'Leave Management',
            'icon': 'bi-calendar-x-fill',
            'endpoint': 'leave.teacher_leaves',
            'description': 'Review student leave requests and apply your own.',
            'section': 'more',
            'active_contains': ['leave'],
        },
        {
            'key': 'reports',
            'label': 'Reports',
            'icon': 'bi-file-earmark-bar-graph-fill',
            'endpoint': 'teacher.reports',
            'description': 'Export attendance reports.',
            'section': 'more',
        },
        {
            'key': 'timetable',
            'label': 'Timetable',
            'icon': 'bi-calendar3',
            'endpoint': 'timetable.view',
            'description': 'Assigned schedule.',
            'section': 'more',
            'active_contains': ['timetable'],
        },
        {
            'key': 'exams_marks',
            'label': 'Exams & Marks',
            'icon': 'bi-journals',
            'endpoint': 'exam.teacher_exams',
            'description': 'Enter marks and manage exam work.',
            'section': 'more',
            'active_contains': ['exam'],
        },
        {
            'key': 'user_guide',
            'label': 'User Guide',
            'icon': 'bi-book-fill',
            'endpoint': 'help.guide',
            'description': 'Built-in documentation and walkthroughs.',
            'section': 'more',
        },
    ],
    'student': [
        {
            'key': 'dashboard',
            'label': 'Dashboard',
            'icon': 'bi-speedometer2',
            'endpoint': 'student.dashboard',
            'description': 'Overview, alerts, and status.',
            'section': 'core',
        },
        {
            'key': 'my_attendance',
            'label': 'My Attendance',
            'icon': 'bi-calendar-check-fill',
            'endpoint': 'student.my_attendance',
            'description': 'Attendance history and exports.',
            'section': 'core',
            'active_endpoints': ['student.download_attendance'],
        },
        {
            'key': 'study_materials',
            'label': 'Study Materials',
            'icon': 'bi-collection-fill',
            'endpoint': 'student.student_content',
            'description': 'Notes, assignments, and study content.',
            'section': 'core',
            'active_contains': ['content'],
        },
        {
            'key': 'my_results',
            'label': 'My Results',
            'icon': 'bi-award-fill',
            'endpoint': 'exam.student_results',
            'description': 'Exam results and progress.',
            'section': 'core',
        },
        {
            'key': 'notice_board',
            'label': 'Notice Board',
            'icon': 'bi-megaphone-fill',
            'endpoint': 'notice.list_notices',
            'description': 'Recent notices and alerts.',
            'section': 'core',
            'active_contains': ['notice'],
        },
        {
            'key': 'my_profile',
            'label': 'My Profile',
            'icon': 'bi-person-circle',
            'endpoint': 'student.profile',
            'description': 'Profile and personal information.',
            'section': 'more',
        },
        {
            'key': 'leave_applications',
            'label': 'Leave Applications',
            'icon': 'bi-calendar-x-fill',
            'endpoint': 'leave.student_leaves',
            'description': 'Apply for leave and track status.',
            'section': 'more',
            'active_contains': ['leave'],
        },
        {
            'key': 'face_enrollment',
            'label': 'Face Enrollment',
            'icon': 'bi-person-bounding-box',
            'endpoint': 'student.enroll',
            'description': 'Enroll or refresh face data.',
            'section': 'more',
            'active_endpoints': ['student.capture_face', 'student.delete_face'],
        },
        {
            'key': 'academic_calendar',
            'label': 'Academic Calendar',
            'icon': 'bi-calendar-event-fill',
            'endpoint': 'calendar.view_calendar',
            'description': 'Holidays, events, and exam weeks.',
            'section': 'more',
            'active_contains': ['calendar'],
        },
        {
            'key': 'timetable',
            'label': 'Timetable',
            'icon': 'bi-calendar3',
            'endpoint': 'timetable.view',
            'description': 'Weekly class schedule.',
            'section': 'more',
            'active_contains': ['timetable'],
        },
        {
            'key': 'marksheet',
            'label': 'Marksheet',
            'icon': 'bi-file-earmark-text-fill',
            'endpoint': 'exam.student_marksheet',
            'description': 'Official semester marksheet.',
            'section': 'more',
        },
        {
            'key': 'fees',
            'label': 'My Fees',
            'icon': 'bi-cash-stack',
            'endpoint': 'fee.student_fees',
            'description': 'Fee due and payment history.',
            'section': 'more',
            'active_contains': ['fee'],
        },
        {
            'key': 'my_id_card',
            'label': 'My ID Card',
            'icon': 'bi-person-vcard-fill',
            'endpoint': 'student.id_card',
            'description': 'Digital ID card request and preview.',
            'section': 'more',
        },
        {
            'key': 'user_guide',
            'label': 'User Guide',
            'icon': 'bi-book-fill',
            'endpoint': 'help.guide',
            'description': 'Built-in documentation and walkthroughs.',
            'section': 'more',
        },
    ],
    'parent': [
        {
            'key': 'dashboard',
            'label': 'Dashboard',
            'icon': 'bi-house-heart-fill',
            'endpoint': 'parent.dashboard',
            'description': 'Child overview and recent status.',
            'section': 'core',
        },
        {
            'key': 'assignments',
            'label': 'Assignments',
            'icon': 'bi-clipboard-check-fill',
            'endpoint': 'parent.parent_assignments',
            'description': 'Track child submissions and results.',
            'section': 'core',
        },
        {
            'key': 'marksheets',
            'label': 'Marksheets',
            'icon': 'bi-award-fill',
            'endpoint': 'parent.parent_marksheets',
            'description': 'Official child marksheets.',
            'section': 'core',
            'active_endpoints': ['parent.parent_marksheet'],
        },
        {
            'key': 'notice_board',
            'label': 'Notice Board',
            'icon': 'bi-megaphone-fill',
            'endpoint': 'notice.list_notices',
            'description': 'Important notices and updates.',
            'section': 'core',
            'active_contains': ['notice'],
        },
        {
            'key': 'academic_calendar',
            'label': 'Academic Calendar',
            'icon': 'bi-calendar-event-fill',
            'endpoint': 'calendar.view_calendar',
            'description': 'Holidays, events, and exam weeks.',
            'section': 'core',
            'active_contains': ['calendar'],
        },
        {
            'key': 'user_guide',
            'label': 'User Guide',
            'icon': 'bi-book-fill',
            'endpoint': 'help.guide',
            'description': 'Built-in documentation and walkthroughs.',
            'section': 'more',
        },
    ],
}


def _is_active(spec: dict, endpoint: str | None) -> bool:
    if not endpoint:
        return False
    if endpoint == spec['endpoint']:
        return True
    if endpoint in spec.get('active_endpoints', []):
        return True
    if any(endpoint.startswith(prefix) for prefix in spec.get('active_prefixes', [])):
        return True
    if any(token in endpoint for token in spec.get('active_contains', [])):
        return True
    return False


def _badge_for_item(user, item_key: str) -> int | None:
    if user.role in ('admin', 'sub_admin') and item_key == 'digital_id_cards':
        count = StudentIDCard.query.filter_by(status='pending').count()
        return count or None

    if user.role == 'teacher' and item_key == 'leave_management' and user.teacher_profile:
        count = (
            db.session.query(LeaveRequest.id)
            .join(Subject, LeaveRequest.subject_id == Subject.id)
            .filter(
                Subject.teacher_id == user.teacher_profile.id,
                LeaveRequest.status == 'pending',
                LeaveRequest.leave_type == 'student_subject',
            )
            .count()
        )
        return count or None

    return None


def allowed_pin_keys(role: str) -> list[str]:
    nav_role = 'admin' if role == 'sub_admin' else role
    return [
        spec['key']
        for spec in NAV_ITEMS.get(nav_role, [])
        if spec.get('section') == 'more'
    ]


def normalize_sidebar_pins(role: str, requested_keys: list[str]) -> tuple[list[str], bool]:
    allowed = set(allowed_pin_keys(role))
    pins = []
    for key in requested_keys:
        if key in allowed and key not in pins:
            pins.append(key)

    trimmed = len(pins) > PIN_LIMIT
    return pins[:PIN_LIMIT], trimmed


def build_sidebar_navigation(user, endpoint: str | None) -> dict:
    nav_role = 'admin' if user.role == 'sub_admin' else user.role
    specs = NAV_ITEMS.get(nav_role, [])
    saved_pins, _ = normalize_sidebar_pins(user.role, user.get_sidebar_pin_keys())

    visible_modules: set[str] = set()
    if user.role == 'sub_admin':
        visible_modules = subadmin_visible_modules(user.id, user.college_id)
    saved_pin_set = set(saved_pins)

    quick_items = []
    more_items = []
    customizable_items = []
    always_visible_items = []

    for spec in specs:
        if not nav_item_is_enabled(user, spec['key']):
            continue
        if user.role == 'sub_admin' and not nav_key_visible_for_subadmin(spec['key'], visible_modules):
            continue

        item = {
            'key': spec['key'],
            'label': spec['label'],
            'icon': spec['icon'],
            'description': spec['description'],
            'url': url_for(spec['endpoint']),
            'active': _is_active(spec, endpoint),
            'badge': _badge_for_item(user, spec['key']),
        }

        if spec['section'] == 'core':
            always_visible_items.append(item)
            quick_items.append({**item, 'pinned': False})
            continue

        pinned = spec['key'] in saved_pin_set
        item['pinned'] = pinned
        customizable_items.append(item)
        if pinned:
            quick_items.append(item)
        else:
            more_items.append(item)

    return {
        'quick_items': quick_items,
        'more_items': more_items,
        'customizable_items': customizable_items,
        'always_visible_items': always_visible_items,
        'has_customizable_items': bool(customizable_items),
        'more_open': any(item['active'] for item in more_items),
        'pin_limit': PIN_LIMIT,
    }
