from __future__ import annotations

from utils.feature_access import dashboard_widget_is_enabled


DASHBOARD_WIDGETS = {
    'admin': {
        'core': [
            {
                'key': 'stats_overview',
                'label': 'Stats Overview',
                'icon': 'bi-grid-1x2-fill',
                'description': 'Headline student, teacher, subject, and session counts.',
            },
            {
                'key': 'attendance_trend',
                'label': 'Attendance Trend',
                'icon': 'bi-graph-up',
                'description': 'Seven-day attendance movement chart.',
            },
            {
                'key': 'recent_notices',
                'label': 'Recent Notices',
                'icon': 'bi-megaphone-fill',
                'description': 'Pinned and recent announcement activity.',
            },
            {
                'key': 'recent_sessions',
                'label': 'Recent Sessions',
                'icon': 'bi-clock-history',
                'description': 'Latest attendance sessions across the college.',
            },
        ],
        'optional': [
            {
                'key': 'department_attendance',
                'label': 'Department Attendance',
                'icon': 'bi-building-fill',
                'description': 'Department-wise attendance averages.',
            },
            {
                'key': 'upcoming_exams',
                'label': 'Upcoming Exams',
                'icon': 'bi-journals',
                'description': 'Exam schedule for the next seven days.',
            },
            {
                'key': 'fee_collection',
                'label': 'Fee Collection',
                'icon': 'bi-cash-stack',
                'description': 'Collected vs expected fee progress.',
            },
        ],
    },
    'teacher': {
        'core': [
            {
                'key': 'teacher_status',
                'label': 'My Status',
                'icon': 'bi-person-check-fill',
                'description': 'Current availability and on-campus status.',
            },
            {
                'key': 'active_session',
                'label': 'Active Session',
                'icon': 'bi-record-circle-fill',
                'description': 'Resume a live attendance session quickly.',
            },
            {
                'key': 'start_session',
                'label': 'Start Session',
                'icon': 'bi-play-circle-fill',
                'description': 'Launch a new attendance session.',
            },
            {
                'key': 'recent_sessions',
                'label': 'Recent Sessions',
                'icon': 'bi-clock-history',
                'description': 'Latest sessions and their status.',
            },
        ],
        'optional': [
            {
                'key': 'stats_overview',
                'label': 'Stats Overview',
                'icon': 'bi-bar-chart-fill',
                'description': 'Assigned subjects and session counts.',
            },
            {
                'key': 'notice_board',
                'label': 'Notice Board',
                'icon': 'bi-megaphone-fill',
                'description': 'Recent teacher-facing notices.',
            },
            {
                'key': 'upcoming_exams',
                'label': 'Upcoming Exams',
                'icon': 'bi-journals',
                'description': 'Upcoming exams for your subjects.',
            },
        ],
    },
    'student': {
        'core': [
            {
                'key': 'profile_banner',
                'label': 'Profile Banner',
                'icon': 'bi-person-circle',
                'description': 'Identity, semester, and overall attendance.',
            },
            {
                'key': 'subject_attendance',
                'label': 'Subject Attendance',
                'icon': 'bi-journal-check',
                'description': 'Subject-wise attendance cards.',
            },
            {
                'key': 'recent_attendance',
                'label': 'Recent Attendance',
                'icon': 'bi-clock-history',
                'description': 'Most recent attendance records.',
            },
        ],
        'optional': [
            {
                'key': 'location_sharing',
                'label': 'Location Sharing',
                'icon': 'bi-geo-alt-fill',
                'description': 'Control parent-visible live location sharing.',
            },
            {
                'key': 'low_attendance_alert',
                'label': 'Low Attendance Alert',
                'icon': 'bi-exclamation-triangle-fill',
                'description': 'Warnings for low-attendance subjects.',
            },
            {
                'key': 'upcoming_exams',
                'label': 'Upcoming Exams',
                'icon': 'bi-alarm-fill',
                'description': 'Next exam schedule with timing and room.',
            },
            {
                'key': 'fee_status',
                'label': 'Fee Status',
                'icon': 'bi-cash-stack',
                'description': 'Outstanding or cleared fee status.',
            },
            {
                'key': 'notices',
                'label': 'Notices',
                'icon': 'bi-megaphone-fill',
                'description': 'Recent student-facing notices.',
            },
        ],
    },
    'parent': {
        'core': [
            {
                'key': 'children_overview',
                'label': 'Children Overview',
                'icon': 'bi-people-fill',
                'description': 'Attendance, fee, assignment, and location overview.',
            },
        ],
        'optional': [
            {
                'key': 'college_notices',
                'label': 'College Notices',
                'icon': 'bi-megaphone-fill',
                'description': 'Recent notices relevant to parents.',
            },
        ],
    },
}


def allowed_dashboard_widget_keys(role: str) -> list[str]:
    return [
        item['key']
        for item in DASHBOARD_WIDGETS.get(role, {}).get('optional', [])
    ]


def normalize_dashboard_widget_keys(role: str, requested_keys: list[str]) -> list[str]:
    allowed = set(allowed_dashboard_widget_keys(role))
    result = []
    for key in requested_keys:
        if key in allowed and key not in result:
            result.append(key)
    return result


def build_dashboard_preferences(user) -> dict:
    config = DASHBOARD_WIDGETS.get(user.role, {'core': [], 'optional': []})
    core_items = [
        item for item in config['core']
        if dashboard_widget_is_enabled(user, item['key'])
    ]
    optional_items = [
        item for item in config['optional']
        if dashboard_widget_is_enabled(user, item['key'])
    ]
    optional_map = {item['key']: item for item in optional_items}
    selected_optional_keys = normalize_dashboard_widget_keys(
        user.role,
        user.get_dashboard_widget_keys(),
    )
    selected_optional = set(selected_optional_keys)
    ordered_optional_keys = selected_optional_keys + [
        item['key'] for item in optional_items
        if item['key'] not in selected_optional
    ]
    visible_widget_keys = {item['key'] for item in core_items} | selected_optional

    return {
        'core_items': core_items,
        'optional_items': [
            {**optional_map[key], 'selected': key in selected_optional}
            for key in ordered_optional_keys
        ],
        'selected_optional_keys': selected_optional_keys,
        'visible_widget_keys': visible_widget_keys,
        'has_optional_items': bool(optional_items),
    }
