"""add platform audit logs

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-05-05 23:55:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5c6d7e8f9a0'
down_revision = 'a4b5c6d7e8f9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'platform_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('college_id', sa.Integer(), nullable=True),
        sa.Column('action_key', sa.String(length=80), nullable=False),
        sa.Column('target_type', sa.String(length=80), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('summary', sa.String(length=255), nullable=False),
        sa.Column('detail_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_platform_audit_logs_actor_user_id'), 'platform_audit_logs', ['actor_user_id'], unique=False)
    op.create_index(op.f('ix_platform_audit_logs_college_id'), 'platform_audit_logs', ['college_id'], unique=False)
    op.create_index('ix_platform_audit_logs_created_at', 'platform_audit_logs', ['created_at'], unique=False)
    op.create_index('ix_platform_audit_logs_college_created', 'platform_audit_logs', ['college_id', 'created_at'], unique=False)
    op.create_index('ix_platform_audit_logs_action_created', 'platform_audit_logs', ['action_key', 'created_at'], unique=False)


def downgrade():
    op.drop_index('ix_platform_audit_logs_action_created', table_name='platform_audit_logs')
    op.drop_index('ix_platform_audit_logs_college_created', table_name='platform_audit_logs')
    op.drop_index('ix_platform_audit_logs_created_at', table_name='platform_audit_logs')
    op.drop_index(op.f('ix_platform_audit_logs_college_id'), table_name='platform_audit_logs')
    op.drop_index(op.f('ix_platform_audit_logs_actor_user_id'), table_name='platform_audit_logs')
    op.drop_table('platform_audit_logs')
