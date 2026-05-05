"""add sidebar pins to users

Revision ID: e6f8a0b1c2d3
Revises: d3e5f7a9b1c2
Create Date: 2026-05-05 23:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'e6f8a0b1c2d3'
down_revision = 'd3e5f7a9b1c2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('users')}

    if 'sidebar_pins' not in columns:
        op.add_column('users', sa.Column('sidebar_pins', sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('users')}

    if 'sidebar_pins' in columns:
        op.drop_column('users', 'sidebar_pins')
