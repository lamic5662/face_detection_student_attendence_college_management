"""Add is_active to classroom_bookings

Revision ID: k7l8m9n0o1p2
Revises: j6k7l8m9n0o1
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'k7l8m9n0o1p2'
down_revision = 'j6k7l8m9n0o1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('classroom_bookings',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1')
    )
    op.create_index('ix_cb_is_active', 'classroom_bookings', ['college_id', 'is_active'])


def downgrade():
    op.drop_index('ix_cb_is_active', table_name='classroom_bookings')
    op.drop_column('classroom_bookings', 'is_active')
