"""add report_schedule_configs table

Revision ID: a1b2c3d4e5f6
Revises: 4d669cbbdcac
Create Date: 2026-05-07 15:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = '9a8b7c6d5e4f'
down_revision = '4d669cbbdcac'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'report_schedule_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('send_day', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('send_hour', sa.Integer(), nullable=False, server_default='7'),
        sa.Column('send_minute', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('filter_department_ids', sa.JSON(), nullable=True),
        sa.Column('filter_semesters', sa.JSON(), nullable=True),
        sa.Column('filter_admission_years', sa.JSON(), nullable=True),
        sa.Column('last_sent_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('college_id', name='uq_report_schedule_college'),
    )
    op.create_index('ix_report_schedule_configs_college', 'report_schedule_configs', ['college_id'])


def downgrade():
    op.drop_index('ix_report_schedule_configs_college', table_name='report_schedule_configs')
    op.drop_table('report_schedule_configs')
