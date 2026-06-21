from __future__ import annotations

from flask import request, url_for

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
            'key': 'universities',
            'label': 'Universities',
            'icon': 'bi-bank2',
            'endpoint': 'super_admin.universities',
            'description': 'Manage university affiliations and compare cross-college academic counts.',
            'section': 'core',
            'active_contains': ['university'],
        },
        {
            'key': 'monitor',
            'label': 'System Monitor',
            'icon': 'bi-activity',
            'endpoint': 'super_admin.monitor',
            'description': 'Live system health, active sessions, and background jobs.',
            'section': 'core',
        },
        {
            'key': 'broadcast',
            'label': 'Broadcast',
            'icon': 'bi-megaphone-fill',
            'endpoint': 'super_admin.broadcast',
            'description': 'Send announcements to all college admins.',
            'section': 'more',
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
            'key': 'plan_demo',
            'label': 'Plan Demo',
            'icon': 'bi-display',
            'endpoint': 'super_admin.plan_demo',
            'description': 'Present pricing tiers and included modules to colleges.',
            'section': 'more',
            'active_contains': ['plan_demo'],
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
            'key': 'teachers',
            'label': 'Teachers',
            'icon': 'bi-person-badge-fill',
            'endpoint': 'admin.teachers',
            'description': 'Faculty accounts and assignments.',
            'section': 'core',
        },
        {
            'key': 'subjects',
            'label': 'Subjects',
            'icon': 'bi-journal-bookmark-fill',
            'endpoint': 'admin.subjects',
            'description': 'Course list and ownership.',
            'section': 'core',
        },
        {
            'key': 'exams',
            'label': 'Exams',
            'icon': 'bi-journals',
            'endpoint': 'exam.admin_exams',
            'description': 'Exam setup and results management.',
            'section': 'core',
        },
        {
            'key': 'timetable',
            'label': 'Timetable',
            'icon': 'bi-calendar3',
            'endpoint': 'timetable.view',
            'description': 'Weekly schedule and class timing.',
            'section': 'core',
            'active_contains': ['timetable'],
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
            'key': 'fees',
            'label': 'Fees',
            'icon': 'bi-cash-stack',
            'endpoint': 'fee.admin_fees',
            'description': 'Fee structures and payments.',
            'section': 'core',
            'active_contains': ['fee'],
        },
        {
            'key': 'library',
            'label': 'Library',
            'icon': 'bi-journal-richtext',
            'endpoint': 'library.admin_dashboard',
            'description': 'Review library growth, circulation, and librarian activity.',
            'section': 'core',
            'active_contains': ['library'],
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
        # ── People ──────────────────────────────────────────────────────
        {
            'key': 'departments',
            'label': 'Departments',
            'icon': 'bi-building-fill',
            'endpoint': 'admin.departments',
            'description': 'Department structure and codes.',
            'section': 'more',
            'group': 'People',
        },
        {
            'key': 'parents',
            'label': 'Parents',
            'icon': 'bi-house-heart-fill',
            'endpoint': 'admin.parents',
            'description': 'Linked parent accounts.',
            'section': 'more',
            'active_contains': ['parent'],
            'group': 'People',
        },
        {
            'key': 'librarians',
            'label': 'Librarians',
            'icon': 'bi-journal-richtext',
            'endpoint': 'admin.librarians',
            'description': 'Manage dedicated librarian accounts.',
            'section': 'more',
            'active_contains': ['librarian'],
            'group': 'People',
        },
        {
            'key': 'sub_admins',
            'label': 'Sub-Admins',
            'icon': 'bi-person-lock',
            'endpoint': 'admin.sub_admins',
            'description': 'Delegate access to staff with limited permissions.',
            'section': 'more',
            'active_endpoints': ['admin.add_sub_admin', 'admin.edit_sub_admin', 'admin.delete_sub_admin'],
            'group': 'People',
        },
        {
            'key': 'all_users',
            'label': 'All Users',
            'icon': 'bi-person-gear',
            'endpoint': 'admin.users',
            'description': 'Reset access and manage accounts.',
            'section': 'more',
            'group': 'People',
        },
        # ── Attendance ───────────────────────────────────────────────────
        {
            'key': 'sessions',
            'label': 'Sessions',
            'icon': 'bi-camera-video-fill',
            'endpoint': 'admin.attendance_hub',
            'endpoint_kwargs': {'tab': 'sessions'},
            'description': 'Monitor live and completed attendance sessions.',
            'section': 'more',
            'active_endpoints': ['admin.cancel_session'],
            'active_tab': 'sessions',
            'group': 'Attendance',
        },
        {
            'key': 'batch_tracker',
            'label': 'Batch Tracker',
            'icon': 'bi-bar-chart-steps',
            'endpoint': 'admin.attendance_hub',
            'endpoint_kwargs': {'tab': 'batch_tracker'},
            'description': 'Track batch progress and promote students.',
            'section': 'more',
            'active_endpoints': ['admin.batch_promote'],
            'active_tab': 'batch_tracker',
            'group': 'Attendance',
        },
        {
            'key': 'analytics',
            'label': 'Analytics',
            'icon': 'bi-bar-chart-fill',
            'endpoint': 'admin.attendance_hub',
            'endpoint_kwargs': {'tab': 'analytics'},
            'description': 'Attendance and performance insights.',
            'section': 'more',
            'active_tab': 'analytics',
            'group': 'Attendance',
        },
        # ── Scheduling ───────────────────────────────────────────────────
        {
            'key': 'classrooms',
            'label': 'Classrooms',
            'icon': 'bi-building',
            'endpoint': 'classroom.classrooms',
            'description': 'Manage rooms and room schedules.',
            'section': 'more',
            'active_contains': ['classrooms'],
            'group': 'Scheduling',
        },
        {
            'key': 'leave_management',
            'label': 'Leave Management',
            'icon': 'bi-calendar-x-fill',
            'endpoint': 'leave.admin_leaves',
            'description': 'Review student and teacher leave requests.',
            'section': 'more',
            'active_contains': ['leave'],
            'group': 'Scheduling',
        },
        {
            'key': 'semester_schedules',
            'label': 'Semester Schedules',
            'icon': 'bi-calendar2-range',
            'endpoint': 'admin.semester_schedules',
            'description': 'Set semester dates and send weekly reports.',
            'section': 'more',
            'active_endpoints': ['admin.semester_schedules', 'admin.save_semester_schedule',
                                 'admin.send_weekly_report_now'],
            'group': 'Scheduling',
        },
        # ── Exams & Records ──────────────────────────────────────────────
        {
            'key': 'marksheets',
            'label': 'Marksheets',
            'icon': 'bi-award-fill',
            'endpoint': 'admin.marksheet_list',
            'description': 'Printable official marksheets.',
            'section': 'more',
            'active_endpoints': ['admin.admin_marksheet'],
            'group': 'Exams & Records',
        },
        {
            'key': 'signatures',
            'label': 'Signatures',
            'icon': 'bi-pen-fill',
            'endpoint': 'admin.marksheet_signatures',
            'description': 'Signature assets for official documents.',
            'section': 'more',
            'active_contains': ['marksheet_signature'],
            'group': 'Exams & Records',
        },
        # ── System ───────────────────────────────────────────────────────
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
            'group': 'System',
        },
        {
            'key': 'digital_id_cards',
            'label': 'Digital ID Cards',
            'icon': 'bi-person-vcard-fill',
            'endpoint': 'admin.id_cards',
            'description': 'Approve and review student ID cards.',
            'section': 'more',
            'active_contains': ['id_card'],
            'group': 'System',
        },
        {
            'key': 'my_plan',
            'label': 'My Plan',
            'icon': 'bi-layers-fill',
            'endpoint': 'admin.my_plan',
            'description': 'Your subscription plan, active modules, expiry, and how to renew.',
            'section': 'more',
            'group': 'System',
        },
        {
            'key': 'settings',
            'label': 'Settings',
            'icon': 'bi-gear-fill',
            'endpoint': 'admin.settings',
            'description': 'College-wide configuration.',
            'section': 'more',
            'active_endpoints': ['admin.save_settings'],
            'group': 'System',
        },
        {
            'key': 'user_guide',
            'label': 'User Guide',
            'icon': 'bi-book-fill',
            'endpoint': 'help.guide',
            'description': 'Built-in documentation and walkthroughs.',
            'section': 'more',
            'group': 'System',
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
            'key': 'timetable',
            'label': 'Timetable',
            'icon': 'bi-calendar3',
            'endpoint': 'timetable.view',
            'description': 'Assigned schedule.',
            'section': 'core',
            'active_contains': ['timetable'],
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
            'key': 'library',
            'label': 'Library',
            'icon': 'bi-journal-richtext',
            'endpoint': 'library.catalog',
            'description': 'Browse books, e-books, and your loan history.',
            'section': 'core',
            'active_contains': ['library'],
        },
        {
            'key': 'exams_marks',
            'label': 'Exams & Marks',
            'icon': 'bi-journals',
            'endpoint': 'exam.teacher_exams',
            'description': 'Enter marks and manage exam work.',
            'section': 'core',
            'active_contains': ['exam'],
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
            'section': 'more',
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
            'key': 'classrooms',
            'label': 'Classrooms',
            'icon': 'bi-building',
            'endpoint': 'classroom.teacher_classrooms',
            'description': 'Rooms assigned to your classes this week.',
            'section': 'more',
            'active_contains': ['classrooms'],
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
            'key': 'study_materials',
            'label': 'Study Materials',
            'icon': 'bi-collection-fill',
            'endpoint': 'student.student_content',
            'description': 'Notes, assignments, and study content.',
            'section': 'core',
            'active_contains': ['content'],
        },
        {
            'key': 'library',
            'label': 'Library',
            'icon': 'bi-journal-richtext',
            'endpoint': 'library.catalog',
            'description': 'Search the college library and manage your issued books.',
            'section': 'core',
            'active_contains': ['library'],
        },
        {
            'key': 'timetable',
            'label': 'Timetable',
            'icon': 'bi-calendar3',
            'endpoint': 'timetable.view',
            'description': 'Weekly class schedule.',
            'section': 'core',
            'active_contains': ['timetable'],
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
            'key': 'my_results',
            'label': 'My Results',
            'icon': 'bi-award-fill',
            'endpoint': 'exam.student_results',
            'description': 'Exam results and progress.',
            'section': 'core',
        },
        {
            'key': 'marksheet',
            'label': 'Marksheet',
            'icon': 'bi-file-earmark-text-fill',
            'endpoint': 'exam.student_marksheet',
            'description': 'Official semester marksheet.',
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
            'key': 'fees',
            'label': 'My Fees',
            'icon': 'bi-cash-stack',
            'endpoint': 'fee.student_fees',
            'description': 'Fee due and payment history.',
            'section': 'core',
            'active_contains': ['fee'],
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
            'key': 'academic_calendar',
            'label': 'Academic Calendar',
            'icon': 'bi-calendar-event-fill',
            'endpoint': 'calendar.view_calendar',
            'description': 'Holidays, events, and exam weeks.',
            'section': 'more',
            'active_contains': ['calendar'],
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
            'key': 'classrooms',
            'label': 'Classrooms',
            'icon': 'bi-building',
            'endpoint': 'classroom.student_classrooms',
            'description': 'Which room your class is in this week.',
            'section': 'more',
            'active_contains': ['classrooms'],
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
            'key': 'library',
            'label': 'Library',
            'icon': 'bi-journal-richtext',
            'endpoint': 'library.parent_overview',
            'description': 'Review child library loans, due dates, and returns.',
            'section': 'core',
            'active_contains': ['library'],
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
    'librarian': [
        {
            'key': 'dashboard',
            'label': 'Library Dashboard',
            'icon': 'bi-speedometer2',
            'endpoint': 'library.admin_dashboard',
            'description': 'Overview of library growth, activity, and health.',
            'section': 'core',
        },
        {
            'key': 'circulation_desk',
            'label': 'Circulation Desk',
            'icon': 'bi-upc-scan',
            'endpoint': 'library.circulation_desk',
            'description': 'Issue, return, renew, and scan borrower or copy QR codes.',
            'section': 'core',
            'active_endpoints': [
                'library.issue_book',
                'library.scan_issue_book',
                'library.scan_return_book',
                'library.return_loan',
                'library.renew_loan',
                'library.settle_fine',
                'library.borrower_cards',
                'library.print_student_borrower_card',
                'library.print_teacher_borrower_card',
                'library.print_copy_label',
                'library.print_book_copy_labels',
            ],
        },
        {
            'key': 'catalog',
            'label': 'Catalog',
            'icon': 'bi-collection-fill',
            'endpoint': 'library.catalog',
            'description': 'Browse the full library catalog.',
            'section': 'core',
            'active_endpoints': [
                'library.book_detail',
                'library.download_ebook',
            ],
        },
        {
            'key': 'rack_setup',
            'label': 'Rack Setup',
            'icon': 'bi-grid-3x3-gap',
            'endpoint': 'library.manage_racks',
            'description': 'Create racks and define row/column capacity.',
            'section': 'core',
        },
        {
            'key': 'rack_assignments',
            'label': 'Rack Assignment',
            'icon': 'bi-ui-checks-grid',
            'endpoint': 'library.manage_rack_assignments',
            'description': 'Assign department, semester, and subject to rack cells.',
            'section': 'core',
        },
        {
            'key': 'stock_audit',
            'label': 'Stock Audit',
            'icon': 'bi-clipboard2-check',
            'endpoint': 'library.stock_audit',
            'description': 'Run shelf verification and stock audit sessions.',
            'section': 'core',
            'active_endpoints': [
                'library.create_stock_audit',
                'library.scan_stock_audit_copy',
                'library.toggle_stock_audit_entry',
                'library.finalize_stock_audit',
                'library.resolve_stock_audit_discrepancy',
            ],
        },
        {
            'key': 'add_books',
            'label': 'Add Books',
            'icon': 'bi-journal-plus',
            'endpoint': 'library.create_book',
            'description': 'Add books into an assigned rack cell.',
            'section': 'core',
            'active_endpoints': [
                'library.edit_book',
            ],
        },
        {
            'key': 'hierarchy_tree',
            'label': 'Hierarchy Tree',
            'icon': 'bi-diagram-3',
            'endpoint': 'library.manage_locations',
            'description': 'View the full rack and cell tree structure.',
            'section': 'core',
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
        active_tab = spec.get('active_tab')
        if active_tab and endpoint == 'admin.attendance_hub':
            return request.args.get('tab', 'sessions') == active_tab
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
            'url': url_for(spec['endpoint'], **spec.get('endpoint_kwargs', {})),
            'active': _is_active(spec, endpoint),
            'badge': _badge_for_item(user, spec['key']),
            'group': spec.get('group', ''),
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

    # Build grouped more_items — preserving insertion order, skip empty groups
    _groups: dict[str, list] = {}
    for item in more_items:
        g = item['group'] or 'Other'
        _groups.setdefault(g, []).append(item)
    more_groups = [{'label': label, 'nav_items': items} for label, items in _groups.items()]

    return {
        'quick_items': quick_items,
        'more_items': more_items,
        'more_groups': more_groups,
        'customizable_items': customizable_items,
        'always_visible_items': always_visible_items,
        'has_customizable_items': bool(customizable_items),
        'more_open': any(item['active'] for item in more_items),
        'pin_limit': PIN_LIMIT,
    }
