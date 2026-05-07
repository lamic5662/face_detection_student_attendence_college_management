"""add_semester_schedules

Revision ID: 4d669cbbdcac
Revises: d6e7f8a9b0c1
Create Date: 2026-05-07 14:55:03.659585

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4d669cbbdcac'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('semester_schedules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('semester', sa.Integer(), nullable=False),
        sa.Column('academic_year', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('college_id', 'department_id', 'semester', 'academic_year',
                            name='uq_semester_schedule'),
    )
    op.create_index('ix_semester_schedules_college',
                    'semester_schedules', ['college_id', 'academic_year', 'semester'])


def downgrade():
    op.drop_index('ix_semester_schedules_college', table_name='semester_schedules')
    op.drop_table('semester_schedules')
