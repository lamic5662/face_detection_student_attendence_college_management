"""Add soft delete to exams

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'i5j6k7l8m9n0'
down_revision = 'h4i5j6k7l8m9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('exams', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('exams', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.create_index('ix_exams_is_deleted', 'exams', ['is_deleted'])


def downgrade():
    op.drop_index('ix_exams_is_deleted', table_name='exams')
    op.drop_column('exams', 'deleted_at')
    op.drop_column('exams', 'is_deleted')
