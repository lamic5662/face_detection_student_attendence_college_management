"""add multi college performance indexes

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-05-05 19:10:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


INDEXES = [
    ('attendance_sessions', 'ix_attendance_sessions_college_status_date', ['college_id', 'status', 'date']),
    ('attendance_sessions', 'ix_attendance_sessions_college_teacher_status', ['college_id', 'teacher_id', 'status']),
    ('attendance_records', 'ix_attendance_records_college_student', ['college_id', 'student_id']),
    ('attendance_records', 'ix_attendance_records_college_session_status', ['college_id', 'session_id', 'status']),
    ('teacher_contents', 'ix_teacher_contents_college_scope_publish', ['college_id', 'department_id', 'semester', 'is_published']),
    ('teacher_contents', 'ix_teacher_contents_college_teacher_created', ['college_id', 'teacher_id', 'created_at']),
    ('teacher_contents', 'ix_teacher_contents_college_type_publish', ['college_id', 'content_type', 'is_published']),
    ('notices', 'ix_notices_college_role_pinned_created', ['college_id', 'target_role', 'is_pinned', 'created_at']),
    ('notices', 'ix_notices_college_expires_at', ['college_id', 'expires_at']),
    ('fee_structures', 'ix_fee_structures_college_department_semester_year', ['college_id', 'department_id', 'semester', 'academic_year']),
    ('fee_structures', 'ix_fee_structures_college_active_due', ['college_id', 'is_active', 'due_date']),
    ('fee_payments', 'ix_fee_payments_college_student_status', ['college_id', 'student_id', 'status']),
    ('fee_payments', 'ix_fee_payments_college_structure_status', ['college_id', 'fee_structure_id', 'status']),
    ('exams', 'ix_exams_college_subject_date', ['college_id', 'subject_id', 'exam_date']),
    ('exams', 'ix_exams_college_creator_date', ['college_id', 'created_by', 'exam_date']),
    ('marks', 'ix_marks_college_student', ['college_id', 'student_id']),
    ('marks', 'ix_marks_college_exam', ['college_id', 'exam_id']),
    ('assignment_submissions', 'ix_assignment_submissions_college_content_status', ['college_id', 'content_id', 'status']),
    ('assignment_submissions', 'ix_assignment_submissions_college_student_status', ['college_id', 'student_id', 'status']),
    ('academic_calendar_events', 'ix_calendar_events_college_dates', ['college_id', 'start_date', 'end_date']),
    ('academic_calendar_events', 'ix_calendar_events_college_scope', ['college_id', 'department_id', 'semester']),
    ('notice_reads', 'ix_notice_reads_college_user_dismissed', ['college_id', 'user_id', 'dismissed_at']),
    ('notice_reads', 'ix_notice_reads_college_notice', ['college_id', 'notice_id']),
    ('parent_students', 'ix_parent_students_college_parent', ['college_id', 'parent_id']),
    ('parent_students', 'ix_parent_students_college_student', ['college_id', 'student_id']),
    ('teacher_statuses', 'ix_teacher_statuses_college_status', ['college_id', 'status']),
    ('class_alerts', 'ix_class_alerts_college_date', ['college_id', 'alert_date']),
    ('timetable_slots', 'ix_timetable_slots_college_scope_day', ['college_id', 'department_id', 'semester', 'day_of_week']),
    ('timetable_slots', 'ix_timetable_slots_college_teacher_day', ['college_id', 'teacher_id', 'day_of_week']),
    ('student_id_cards', 'ix_student_id_cards_college_status_submitted', ['college_id', 'status', 'submitted_at']),
    ('leave_requests', 'ix_leave_requests_college_status_created', ['college_id', 'status', 'created_at']),
    ('leave_requests', 'ix_leave_requests_college_student_status', ['college_id', 'student_id', 'status']),
    ('leave_requests', 'ix_leave_requests_college_teacher_status', ['college_id', 'teacher_id', 'status']),
    ('students', 'ix_students_college_department_semester', ['college_id', 'department_id', 'semester']),
    ('teachers', 'ix_teachers_college_department', ['college_id', 'department_id']),
]


def upgrade():
    for table_name, index_name, columns in INDEXES:
        op.create_index(index_name, table_name, columns)


def downgrade():
    for table_name, index_name, _columns in reversed(INDEXES):
        op.drop_index(index_name, table_name=table_name)
