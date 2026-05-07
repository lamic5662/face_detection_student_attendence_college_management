"""add fee_reminder_configs table

Revision ID: b3c4d5e6f7a8
Revises: 9a8b7c6d5e4f
Create Date: 2026-05-07 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = 'b3c4d5e6f7a8'
down_revision = '9a8b7c6d5e4f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fee_reminder_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('days_before_due', sa.Integer(), nullable=False, server_default='7'),
        sa.Column('remind_on_due_date', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('remind_overdue', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('send_hour', sa.Integer(), nullable=False, server_default='8'),
        sa.Column('last_sent_at', sa.DateTime(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('college_id', name='uq_fee_reminder_college'),
    )
    op.create_index('ix_fee_reminder_configs_college', 'fee_reminder_configs', ['college_id'])


def downgrade():
    op.drop_index('ix_fee_reminder_configs_college', table_name='fee_reminder_configs')
    op.drop_table('fee_reminder_configs')
