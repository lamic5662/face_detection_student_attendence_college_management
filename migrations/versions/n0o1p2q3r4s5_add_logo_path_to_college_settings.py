"""add logo_path to college_settings

Revision ID: n0o1p2q3r4s5
Revises: m9n0o1p2q3r4
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = 'n0o1p2q3r4s5'
down_revision = 'm9n0o1p2q3r4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('college_settings', sa.Column('logo_path', sa.String(255), nullable=True))


def downgrade():
    op.drop_column('college_settings', 'logo_path')
