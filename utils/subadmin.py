from __future__ import annotations


SUBADMIN_MODULES: dict[str, str] = {
    'students': 'Students',
    'teachers': 'Teachers',
    'parents': 'Parents',
    'attendance': 'Attendance & Sessions',
    'exams': 'Exams & Marksheets',
    'fees': 'Fees',
    'notices': 'Notice Board',
    'timetable': 'Timetable',
    'leaves': 'Leave Management',
    'id_cards': 'Digital ID Cards',
    'analytics': 'Analytics',
    'file_manager': 'File Manager',
    'reports': 'Semester Schedules & Reports',
    'classrooms': 'Classroom Management',
    'library': 'Library Management',
}

# Map endpoint name → (module, required_action) or None (always allowed for sub-admins)
ENDPOINT_PERMISSION_MAP: dict[str, tuple[str, str] | None] = {
    # Always allowed
    'admin.dashboard': None,
    'static': None,
    'help.guide': None,
    'auth.logout': None,
    'auth.change_password': None,
    'auth.update_sidebar_preferences': None,
    'auth.toggle_sidebar_pin': None,
    'auth.update_dashboard_preferences': None,
    'auth.password_setup_prompt': None,
    'auth.send_password_setup_email_to_current_user': None,
    'auth.set_password_from_email': None,
    'calendar.view_calendar': None,
    'ai.ai_chat': None,
    'ai.ai_generate_notice': None,

    # Students
    'admin.students': ('students', 'view'),
    'admin.preview_student_id': ('students', 'view'),
    'admin.add_student': ('students', 'edit'),
    'admin.edit_student': ('students', 'edit'),
    'admin.import_students': ('students', 'edit'),
    'admin.export_students': ('students', 'view'),
    'admin.student_attendance': ('students', 'view'),
    'admin.delete_student': ('students', 'delete'),
    'admin.batch_overview': ('students', 'view'),
    'admin.batch_promote': ('students', 'edit'),
    'admin.departments': ('students', 'view'),
    'admin.edit_department': ('students', 'edit'),
    'admin.delete_department': ('students', 'delete'),

    # Teachers & Subjects
    'admin.teachers': ('teachers', 'view'),
    'admin.add_teacher': ('teachers', 'edit'),
    'admin.edit_teacher': ('teachers', 'edit'),
    'admin.delete_teacher': ('teachers', 'delete'),
    'admin.subjects': ('teachers', 'view'),
    'admin.edit_subject': ('teachers', 'edit'),
    'admin.delete_subject': ('teachers', 'delete'),

    # Attendance
    'admin.sessions': ('attendance', 'view'),
    'admin.cancel_session': ('attendance', 'edit'),
    'admin.trigger_class_alerts': ('attendance', 'edit'),

    # Analytics
    'admin.analytics': ('analytics', 'view'),

    # Parents
    'admin.parents': ('parents', 'view'),
    'admin.add_parent': ('parents', 'edit'),
    'admin.link_parent_child': ('parents', 'edit'),
    'admin.unlink_parent_child': ('parents', 'edit'),
    'admin.delete_parent': ('parents', 'delete'),

    # Exams & Marksheets
    'exam.admin_exams': ('exams', 'view'),
    'exam.admin_bulk_exams': ('exams', 'edit'),
    'exam.admin_delete_exam': ('exams', 'delete'),
    'admin.marksheet_list': ('exams', 'view'),
    'admin.admin_marksheet': ('exams', 'view'),
    'admin.marksheet_signatures': ('exams', 'view'),
    'admin.save_marksheet_signature': ('exams', 'edit'),
    'admin.delete_marksheet_signature': ('exams', 'delete'),

    # Fees
    'fee.admin_fees': ('fees', 'view'),
    'fee.create_structure': ('fees', 'edit'),
    'fee.delete_structure': ('fees', 'delete'),
    'fee.structure_payments': ('fees', 'view'),
    'fee.record_payment': ('fees', 'edit'),
    'fee.save_fee_reminder_config': ('fees', 'edit'),
    'fee.send_fee_reminders_now': ('fees', 'edit'),

    # Notice Board
    'notice.list_notices': ('notices', 'view'),
    'notice.detail': ('notices', 'view'),
    'notice.feed': ('notices', 'view'),
    'notice.mark_all_read': ('notices', 'view'),
    'notice.delete_read': ('notices', 'view'),
    'notice.create': ('notices', 'edit'),
    'notice.edit': ('notices', 'edit'),
    'notice.delete': ('notices', 'delete'),

    # Timetable
    'timetable.view': ('timetable', 'view'),
    'timetable.manage': ('timetable', 'edit'),
    'timetable.save_slot': ('timetable', 'edit'),
    'timetable.delete_slot': ('timetable', 'delete'),

    # Classroom Management
    'classroom.classrooms': ('classrooms', 'view'),
    'classroom.add_classroom': ('classrooms', 'edit'),
    'classroom.edit_classroom': ('classrooms', 'edit'),
    'classroom.delete_classroom': ('classrooms', 'delete'),
    'classroom.add_booking': ('classrooms', 'edit'),
    'classroom.edit_booking': ('classrooms', 'edit'),
    'classroom.delete_booking': ('classrooms', 'delete'),
    'classroom.bulk_delete_bookings': ('classrooms', 'delete'),

    # Library
    'library.index': ('library', 'view'),
    'library.admin_dashboard': ('library', 'view'),
    'library.catalog': ('library', 'view'),
    'library.book_detail': ('library', 'view'),
    'library.download_ebook': ('library', 'view'),
    'library.create_book': ('library', 'edit'),
    'library.edit_book': ('library', 'edit'),
    'library.add_copies': ('library', 'edit'),
    'library.issue_book': ('library', 'edit'),
    'library.return_loan': ('library', 'edit'),
    'library.renew_loan': ('library', 'edit'),

    # Leave Management
    'leave.admin_leaves': ('leaves', 'view'),
    'leave.admin_review_leave': ('leaves', 'edit'),
    'leave.admin_delete_leave': ('leaves', 'delete'),
    'leave.admin_bulk_delete_leaves': ('leaves', 'delete'),
    'leave.view_letter': ('leaves', 'view'),

    # Digital ID Cards
    'admin.id_cards': ('id_cards', 'view'),
    'admin.id_card_template': ('id_cards', 'edit'),
    'admin.view_id_card': ('id_cards', 'view'),
    'admin.approve_id_card': ('id_cards', 'edit'),
    'admin.reject_id_card': ('id_cards', 'edit'),

    # File Manager
    'admin.file_manager': ('file_manager', 'view'),
    'admin.view_file': ('file_manager', 'view'),
    'admin.preview_file': ('file_manager', 'view'),
    'admin.delete_file': ('file_manager', 'delete'),
    'admin.bulk_delete_files': ('file_manager', 'delete'),

    # Semester Schedules & Reports
    'admin.semester_schedules': ('reports', 'view'),
    'admin.save_semester_schedule': ('reports', 'edit'),
    'admin.delete_semester_schedule': ('reports', 'delete'),
    'admin.send_weekly_report_now': ('reports', 'edit'),
    'admin.save_report_schedule': ('reports', 'edit'),
}

# Maps nav_item key → module (None = always visible for sub-admin)
NAV_KEY_TO_MODULE: dict[str, str | None] = {
    'dashboard': None,
    'students': 'students',
    'batch_tracker': 'students',
    'departments': 'students',
    'semester_schedules': 'reports',
    'teachers': 'teachers',
    'subjects': 'teachers',
    'notice_board': 'notices',
    'academic_calendar': None,
    'sessions': 'attendance',
    'analytics': 'analytics',
    'leave_management': 'leaves',
    'file_manager': 'file_manager',
    'timetable': 'timetable',
    'classrooms': 'classrooms',
    'library': 'library',
    'exams': 'exams',
    'marksheets': 'exams',
    'signatures': 'exams',
    'fees': 'fees',
    'parents': 'parents',
    'librarians': None,
    'settings': None,  # filtered out via explicit check
    'digital_id_cards': 'id_cards',
    'all_users': None,  # sub-admin cannot manage users
    'sub_admins': None,
    'user_guide': None,
    'ai_assistant': None,
}

# Nav keys completely hidden from sub-admins regardless of permissions
_SUBADMIN_HIDDEN_NAV_KEYS = {'settings', 'all_users', 'sub_admins', 'librarians'}


def get_subadmin_module_permissions(user_id: int, college_id: int) -> dict[str, set[str]]:
    """Returns {module: {action, ...}} for the given sub-admin user."""
    from models.sub_admin import SubAdminPermission
    perms = SubAdminPermission.query.filter_by(user_id=user_id, college_id=college_id).all()
    result: dict[str, set[str]] = {}
    for p in perms:
        actions: set[str] = set()
        if p.can_view:
            actions.add('view')
        if p.can_edit:
            actions.add('edit')
        if p.can_delete:
            actions.add('delete')
        result[p.module] = actions
    return result


def check_subadmin_access(user, endpoint: str | None) -> bool:
    """Returns True if this sub-admin is permitted to access the given endpoint."""
    if endpoint is None:
        return True

    if endpoint not in ENDPOINT_PERMISSION_MAP:
        return False  # deny unknown endpoints by default

    requirement = ENDPOINT_PERMISSION_MAP[endpoint]
    if requirement is None:
        return True  # no permission required

    module, action = requirement
    from models.sub_admin import SubAdminPermission
    perm = SubAdminPermission.query.filter_by(
        user_id=user.id,
        college_id=user.college_id,
        module=module,
    ).first()

    if perm is None:
        return False

    if action == 'view':
        return perm.can_view or perm.can_edit or perm.can_delete
    if action == 'edit':
        return perm.can_edit or perm.can_delete
    if action == 'delete':
        return perm.can_delete
    return False


def subadmin_visible_modules(user_id: int, college_id: int) -> set[str]:
    """Returns the set of modules where the sub-admin has at least can_view=True."""
    from models.sub_admin import SubAdminPermission
    perms = SubAdminPermission.query.filter_by(user_id=user_id, college_id=college_id).all()
    return {
        p.module
        for p in perms
        if p.can_view or p.can_edit or p.can_delete
    }


def nav_key_visible_for_subadmin(nav_key: str, visible_modules: set[str]) -> bool:
    """Returns True if a nav item should be visible for this sub-admin."""
    if nav_key in _SUBADMIN_HIDDEN_NAV_KEYS:
        return False
    module = NAV_KEY_TO_MODULE.get(nav_key)
    if module is None:
        return True  # always visible
    return module in visible_modules
