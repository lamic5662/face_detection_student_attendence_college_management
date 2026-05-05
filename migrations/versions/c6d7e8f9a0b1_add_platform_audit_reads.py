"""add platform audit reads

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-05-06 00:12:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6d7e8f9a0b1'
down_revision = 'b5c6d7e8f9a0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'platform_audit_reads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('audit_log_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=False),
        sa.Column('dismissed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['audit_log_id'], ['platform_audit_logs.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('audit_log_id', 'user_id', name='uq_platform_audit_read_log_user'),
    )
    op.create_index('ix_platform_audit_reads_user_dismissed', 'platform_audit_reads', ['user_id', 'dismissed_at'], unique=False)
    op.create_index('ix_platform_audit_reads_user_log', 'platform_audit_reads', ['user_id', 'audit_log_id'], unique=False)
    op.create_index(op.f('ix_platform_audit_reads_user_id'), 'platform_audit_reads', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_platform_audit_reads_user_id'), table_name='platform_audit_reads')
    op.drop_index('ix_platform_audit_reads_user_log', table_name='platform_audit_reads')
    op.drop_index('ix_platform_audit_reads_user_dismissed', table_name='platform_audit_reads')
    op.drop_table('platform_audit_reads')
