"""apply multi college to remaining models

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a
Create Date: 2026-05-05 18:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a'
branch_labels = None
depends_on = None


TABLES = [
    'assignment_submissions',
    'attendance_sessions',
    'attendance_records',
    'teacher_contents',
    'exams',
    'marks',
    'fee_structures',
    'fee_payments',
    'id_card_templates',
    'student_id_cards',
    'leave_requests',
    'student_locations',
    'marksheet_signatures',
    'notice_reads',
    'parent_students',
    'teacher_statuses',
    'class_alerts',
    'timetable_slots',
]


def _default_college_id(bind):
    return bind.execute(sa.text('SELECT id FROM colleges ORDER BY id LIMIT 1')).scalar_one()


def upgrade():
    bind = op.get_bind()
    default_college_id = _default_college_id(bind)

    for table_name in TABLES:
        op.add_column(table_name, sa.Column('college_id', sa.Integer(), nullable=True))

    bind.execute(sa.text("""
        UPDATE assignment_submissions s
        JOIN students st ON st.id = s.student_id
        SET s.college_id = st.college_id
        WHERE s.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE attendance_sessions s
        JOIN subjects sub ON sub.id = s.subject_id
        SET s.college_id = sub.college_id
        WHERE s.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE attendance_records r
        JOIN attendance_sessions s ON s.id = r.session_id
        SET r.college_id = s.college_id
        WHERE r.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE teacher_contents c
        JOIN teachers t ON t.id = c.teacher_id
        SET c.college_id = t.college_id
        WHERE c.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE exams e
        JOIN subjects s ON s.id = e.subject_id
        SET e.college_id = s.college_id
        WHERE e.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE marks m
        JOIN exams e ON e.id = m.exam_id
        SET m.college_id = e.college_id
        WHERE m.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE fee_structures fs
        LEFT JOIN departments d ON d.id = fs.department_id
        SET fs.college_id = COALESCE(d.college_id, :default_college_id)
        WHERE fs.college_id IS NULL
    """), {'default_college_id': default_college_id})
    bind.execute(sa.text("""
        UPDATE fee_payments fp
        JOIN students s ON s.id = fp.student_id
        SET fp.college_id = s.college_id
        WHERE fp.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE id_card_templates
        SET college_id = :default_college_id
        WHERE college_id IS NULL
    """), {'default_college_id': default_college_id})
    bind.execute(sa.text("""
        UPDATE student_id_cards c
        JOIN students s ON s.id = c.student_id
        SET c.college_id = s.college_id
        WHERE c.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE leave_requests lr
        LEFT JOIN students s ON s.id = lr.student_id
        LEFT JOIN teachers t ON t.id = lr.teacher_id
        LEFT JOIN subjects sub ON sub.id = lr.subject_id
        LEFT JOIN users u ON u.id = lr.approver_id
        SET lr.college_id = COALESCE(s.college_id, t.college_id, sub.college_id, u.college_id, :default_college_id)
        WHERE lr.college_id IS NULL
    """), {'default_college_id': default_college_id})
    bind.execute(sa.text("""
        UPDATE student_locations sl
        JOIN students s ON s.id = sl.student_id
        SET sl.college_id = s.college_id
        WHERE sl.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE marksheet_signatures ms
        LEFT JOIN departments d ON d.id = ms.department_id
        LEFT JOIN teachers t ON t.id = ms.teacher_id
        SET ms.college_id = COALESCE(d.college_id, t.college_id, :default_college_id)
        WHERE ms.college_id IS NULL
    """), {'default_college_id': default_college_id})
    bind.execute(sa.text("""
        UPDATE notice_reads nr
        JOIN notices n ON n.id = nr.notice_id
        SET nr.college_id = n.college_id
        WHERE nr.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE parent_students ps
        JOIN students s ON s.id = ps.student_id
        SET ps.college_id = s.college_id
        WHERE ps.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE teacher_statuses ts
        JOIN teachers t ON t.id = ts.teacher_id
        SET ts.college_id = t.college_id
        WHERE ts.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE class_alerts ca
        JOIN timetable_slots ts ON ts.id = ca.slot_id
        SET ca.college_id = ts.college_id
        WHERE ca.college_id IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE timetable_slots ts
        JOIN departments d ON d.id = ts.department_id
        SET ts.college_id = d.college_id
        WHERE ts.college_id IS NULL
    """))

    for table_name in TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column('college_id', existing_type=sa.Integer(), nullable=False)
            batch_op.create_foreign_key(
                f'fk_{table_name}_college_id',
                'colleges',
                ['college_id'],
                ['id'],
            )
            batch_op.create_index(f'ix_{table_name}_college_id', ['college_id'])

    with op.batch_alter_table('id_card_templates') as batch_op:
        batch_op.create_unique_constraint('uq_id_card_templates_college_id', ['college_id'])


def downgrade():
    with op.batch_alter_table('id_card_templates') as batch_op:
        batch_op.drop_constraint('uq_id_card_templates_college_id', type_='unique')

    for table_name in reversed(TABLES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f'ix_{table_name}_college_id')
            batch_op.drop_constraint(f'fk_{table_name}_college_id', type_='foreignkey')
            batch_op.drop_column('college_id')
