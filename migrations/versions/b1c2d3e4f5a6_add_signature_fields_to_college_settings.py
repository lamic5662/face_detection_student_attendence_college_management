"""add signature fields to college_settings

Revision ID: b1c2d3e4f5a6
Revises: 327c3c6d717a
Create Date: 2026-05-04 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'b1c2d3e4f5a6'
down_revision = '327c3c6d717a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('college_settings', sa.Column('principal_name', sa.String(100), nullable=True))
    op.add_column('college_settings', sa.Column('principal_sign_path', sa.String(255), nullable=True))
    op.add_column('college_settings', sa.Column('hod_name', sa.String(100), nullable=True))
    op.add_column('college_settings', sa.Column('hod_sign_path', sa.String(255), nullable=True))
    op.add_column('college_settings', sa.Column('class_teacher_name', sa.String(100), nullable=True))
    op.add_column('college_settings', sa.Column('class_teacher_sign_path', sa.String(255), nullable=True))


def downgrade():
    op.drop_column('college_settings', 'class_teacher_sign_path')
    op.drop_column('college_settings', 'class_teacher_name')
    op.drop_column('college_settings', 'hod_sign_path')
    op.drop_column('college_settings', 'hod_name')
    op.drop_column('college_settings', 'principal_sign_path')
    op.drop_column('college_settings', 'principal_name')
