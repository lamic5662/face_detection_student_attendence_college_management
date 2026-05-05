"""add dashboard widgets to users

Revision ID: f0a1b2c3d4e5
Revises: e6f8a0b1c2d3
Create Date: 2026-05-05 23:40:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'f0a1b2c3d4e5'
down_revision = 'e6f8a0b1c2d3'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('users')}

    if 'dashboard_widgets' not in columns:
        op.add_column('users', sa.Column('dashboard_widgets', sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('users')}

    if 'dashboard_widgets' in columns:
        op.drop_column('users', 'dashboard_widgets')
