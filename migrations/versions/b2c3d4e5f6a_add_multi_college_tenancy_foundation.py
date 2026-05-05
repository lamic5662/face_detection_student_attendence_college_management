"""add multi college tenancy foundation

Revision ID: b2c3d4e5f6a
Revises: a1b2c3d4e5f6
Create Date: 2026-05-05 17:35:00.000000
"""

from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def _drop_unique_artifacts(table_name: str, column_names: list[str]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for unique in inspector.get_unique_constraints(table_name):
        if unique.get('column_names') == column_names and unique.get('name'):
            op.drop_constraint(unique['name'], table_name, type_='unique')

    inspector = sa.inspect(bind)
    for index in inspector.get_indexes(table_name):
        if index.get('unique') and index.get('column_names') == column_names and index.get('name'):
            op.drop_index(index['name'], table_name=table_name)


def upgrade():
    op.create_table(
        'colleges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('subdomain', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_colleges_code'),
        sa.UniqueConstraint('subdomain', name='uq_colleges_subdomain'),
    )

    op.add_column('users', sa.Column('college_id', sa.Integer(), nullable=True))
    op.add_column('departments', sa.Column('college_id', sa.Integer(), nullable=True))
    op.add_column('students', sa.Column('college_id', sa.Integer(), nullable=True))
    op.add_column('teachers', sa.Column('college_id', sa.Integer(), nullable=True))
    op.add_column('subjects', sa.Column('college_id', sa.Integer(), nullable=True))
    op.add_column('college_settings', sa.Column('college_id', sa.Integer(), nullable=True))
    op.add_column('notices', sa.Column('college_id', sa.Integer(), nullable=True))
    op.add_column('academic_calendar_events', sa.Column('college_id', sa.Integer(), nullable=True))

    bind = op.get_bind()
    existing_name = bind.execute(
        sa.text('SELECT college_name FROM college_settings ORDER BY id LIMIT 1')
    ).scalar() or 'College'

    bind.execute(
        sa.text(
            """
            INSERT INTO colleges (name, code, subdomain, is_active, created_at)
            VALUES (:name, :code, NULL, :is_active, :created_at)
            """
        ),
        {
            'name': existing_name,
            'code': 'MAIN',
            'is_active': True,
            'created_at': datetime.utcnow(),
        },
    )
    default_college_id = bind.execute(
        sa.text('SELECT id FROM colleges WHERE code = :code'),
        {'code': 'MAIN'},
    ).scalar_one()

    for table_name in (
        'users',
        'departments',
        'students',
        'teachers',
        'subjects',
        'college_settings',
        'notices',
        'academic_calendar_events',
    ):
        bind.execute(
            sa.text(f'UPDATE {table_name} SET college_id = :college_id WHERE college_id IS NULL'),
            {'college_id': default_college_id},
        )

    _drop_unique_artifacts('users', ['email'])
    _drop_unique_artifacts('departments', ['code'])
    _drop_unique_artifacts('students', ['roll_number'])
    _drop_unique_artifacts('teachers', ['employee_id'])
    _drop_unique_artifacts('subjects', ['code'])

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('college_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_users_college_id', 'colleges', ['college_id'], ['id'])
        batch_op.create_index('ix_users_college_id', ['college_id'])
        batch_op.create_unique_constraint('uq_users_college_email', ['college_id', 'email'])

    with op.batch_alter_table('departments') as batch_op:
        batch_op.alter_column('college_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_departments_college_id', 'colleges', ['college_id'], ['id'])
        batch_op.create_index('ix_departments_college_id', ['college_id'])
        batch_op.create_unique_constraint('uq_departments_college_code', ['college_id', 'code'])

    with op.batch_alter_table('students') as batch_op:
        batch_op.alter_column('college_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_students_college_id', 'colleges', ['college_id'], ['id'])
        batch_op.create_index('ix_students_college_id', ['college_id'])
        batch_op.create_unique_constraint('uq_students_college_roll_number', ['college_id', 'roll_number'])

    with op.batch_alter_table('teachers') as batch_op:
        batch_op.alter_column('college_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_teachers_college_id', 'colleges', ['college_id'], ['id'])
        batch_op.create_index('ix_teachers_college_id', ['college_id'])
        batch_op.create_unique_constraint('uq_teachers_college_employee_id', ['college_id', 'employee_id'])

    with op.batch_alter_table('subjects') as batch_op:
        batch_op.alter_column('college_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_subjects_college_id', 'colleges', ['college_id'], ['id'])
        batch_op.create_index('ix_subjects_college_id', ['college_id'])
        batch_op.create_unique_constraint('uq_subjects_college_code', ['college_id', 'code'])

    with op.batch_alter_table('college_settings') as batch_op:
        batch_op.alter_column('college_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_college_settings_college_id', 'colleges', ['college_id'], ['id'])
        batch_op.create_index('ix_college_settings_college_id', ['college_id'], unique=True)

    with op.batch_alter_table('notices') as batch_op:
        batch_op.alter_column('college_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_notices_college_id', 'colleges', ['college_id'], ['id'])
        batch_op.create_index('ix_notices_college_id', ['college_id'])

    with op.batch_alter_table('academic_calendar_events') as batch_op:
        batch_op.alter_column('college_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_calendar_events_college_id', 'colleges', ['college_id'], ['id'])
        batch_op.create_index('ix_academic_calendar_events_college_id', ['college_id'])


def downgrade():
    with op.batch_alter_table('academic_calendar_events') as batch_op:
        batch_op.drop_index('ix_academic_calendar_events_college_id')
        batch_op.drop_constraint('fk_calendar_events_college_id', type_='foreignkey')
        batch_op.drop_column('college_id')

    with op.batch_alter_table('notices') as batch_op:
        batch_op.drop_index('ix_notices_college_id')
        batch_op.drop_constraint('fk_notices_college_id', type_='foreignkey')
        batch_op.drop_column('college_id')

    with op.batch_alter_table('college_settings') as batch_op:
        batch_op.drop_index('ix_college_settings_college_id')
        batch_op.drop_constraint('fk_college_settings_college_id', type_='foreignkey')
        batch_op.drop_column('college_id')

    with op.batch_alter_table('subjects') as batch_op:
        batch_op.drop_constraint('uq_subjects_college_code', type_='unique')
        batch_op.drop_index('ix_subjects_college_id')
        batch_op.drop_constraint('fk_subjects_college_id', type_='foreignkey')
        batch_op.drop_column('college_id')
        batch_op.create_unique_constraint('uq_subjects_code', ['code'])

    with op.batch_alter_table('teachers') as batch_op:
        batch_op.drop_constraint('uq_teachers_college_employee_id', type_='unique')
        batch_op.drop_index('ix_teachers_college_id')
        batch_op.drop_constraint('fk_teachers_college_id', type_='foreignkey')
        batch_op.drop_column('college_id')
        batch_op.create_unique_constraint('uq_teachers_employee_id', ['employee_id'])

    with op.batch_alter_table('students') as batch_op:
        batch_op.drop_constraint('uq_students_college_roll_number', type_='unique')
        batch_op.drop_index('ix_students_college_id')
        batch_op.drop_constraint('fk_students_college_id', type_='foreignkey')
        batch_op.drop_column('college_id')
        batch_op.create_unique_constraint('uq_students_roll_number', ['roll_number'])

    with op.batch_alter_table('departments') as batch_op:
        batch_op.drop_constraint('uq_departments_college_code', type_='unique')
        batch_op.drop_index('ix_departments_college_id')
        batch_op.drop_constraint('fk_departments_college_id', type_='foreignkey')
        batch_op.drop_column('college_id')
        batch_op.create_unique_constraint('uq_departments_code', ['code'])

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_constraint('uq_users_college_email', type_='unique')
        batch_op.drop_index('ix_users_college_id')
        batch_op.drop_constraint('fk_users_college_id', type_='foreignkey')
        batch_op.drop_column('college_id')
        batch_op.create_unique_constraint('uq_users_email', ['email'])

    op.drop_table('colleges')
