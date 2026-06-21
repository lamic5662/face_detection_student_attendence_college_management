"""add user notifications

Revision ID: b4c5d6e7f8g9
Revises: a3b4c5d6e7f8
Create Date: 2026-05-23 00:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'b4c5d6e7f8g9'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


user_notification_category = sa.Enum(
    'general',
    'exam',
    'holiday',
    'event',
    'fee',
    'urgent',
    name='user_notification_category',
)


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    user_notification_category.create(bind, checkfirst=True)

    if 'user_notifications' not in inspector.get_table_names():
        op.create_table(
            'user_notifications',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('college_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('category', user_notification_category, nullable=False, server_default='general'),
            sa.Column('action_url', sa.String(length=255), nullable=True),
            sa.Column('source_key', sa.String(length=120), nullable=True),
            sa.Column('is_pinned', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('read_at', sa.DateTime(), nullable=True),
            sa.Column('dismissed_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('user_id', 'source_key', name='uq_user_notifications_user_source'),
        )
        op.create_index(op.f('ix_user_notifications_college_id'), 'user_notifications', ['college_id'], unique=False)
        op.create_index(op.f('ix_user_notifications_user_id'), 'user_notifications', ['user_id'], unique=False)
        op.create_index(
            'ix_user_notifications_college_user_created',
            'user_notifications',
            ['college_id', 'user_id', 'created_at'],
            unique=False,
        )
        op.create_index(
            'ix_user_notifications_college_user_dismissed',
            'user_notifications',
            ['college_id', 'user_id', 'dismissed_at'],
            unique=False,
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if 'user_notifications' in inspector.get_table_names():
        op.drop_index('ix_user_notifications_college_user_dismissed', table_name='user_notifications')
        op.drop_index('ix_user_notifications_college_user_created', table_name='user_notifications')
        op.drop_index(op.f('ix_user_notifications_user_id'), table_name='user_notifications')
        op.drop_index(op.f('ix_user_notifications_college_id'), table_name='user_notifications')
        op.drop_table('user_notifications')

    user_notification_category.drop(bind, checkfirst=True)
