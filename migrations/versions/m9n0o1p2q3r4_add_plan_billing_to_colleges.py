"""Add plan and billing fields to colleges

Revision ID: m9n0o1p2q3r4
Revises: l8m9n0o1p2q3
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa

revision = 'm9n0o1p2q3r4'
down_revision = 'l8m9n0o1p2q3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('colleges', sa.Column('plan', sa.String(20), nullable=False, server_default='free'))
    op.add_column('colleges', sa.Column('plan_expires_at', sa.DateTime(), nullable=True))
    op.add_column('colleges', sa.Column('billing_notes', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('colleges', 'billing_notes')
    op.drop_column('colleges', 'plan_expires_at')
    op.drop_column('colleges', 'plan')
