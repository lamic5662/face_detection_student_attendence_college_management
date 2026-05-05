"""add notice dismissed_at

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-05-05 10:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f0a1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('notice_reads')}

    if 'dismissed_at' not in columns:
        op.add_column('notice_reads', sa.Column('dismissed_at', sa.DateTime(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('notice_reads')}

    if 'dismissed_at' in columns:
        op.drop_column('notice_reads', 'dismissed_at')
