"""add notice reads

Revision ID: d3e5f7a9b1c2
Revises: c2d4e6f8a1b0
Create Date: 2026-05-05 18:25:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'd3e5f7a9b1c2'
down_revision = 'c2d4e6f8a1b0'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if 'notice_reads' not in inspector.get_table_names():
        op.create_table(
            'notice_reads',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('notice_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('read_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['notice_id'], ['notices.id']),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('notice_id', 'user_id', name='uq_notice_read_notice_user'),
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if 'notice_reads' in inspector.get_table_names():
        op.drop_table('notice_reads')
