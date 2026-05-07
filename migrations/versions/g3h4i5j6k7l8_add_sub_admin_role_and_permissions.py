"""add sub_admin role and permissions table

Revision ID: g3h4i5j6k7l8
Revises: b3c4d5e6f7a8
Create Date: 2026-05-07 10:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = 'g3h4i5j6k7l8'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE users MODIFY COLUMN role "
        "ENUM('super_admin', 'admin', 'sub_admin', 'teacher', 'student', 'parent') NOT NULL"
    )

    op.create_table(
        'sub_admin_permissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('module', sa.String(50), nullable=False),
        sa.Column('can_view', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('can_edit', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('can_delete', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('college_id', 'user_id', 'module', name='uq_sub_admin_perm'),
    )
    op.create_index('ix_sub_admin_permissions_college_id', 'sub_admin_permissions', ['college_id'])
    op.create_index('ix_sub_admin_permissions_user_id', 'sub_admin_permissions', ['user_id'])


def downgrade():
    op.drop_index('ix_sub_admin_permissions_user_id', table_name='sub_admin_permissions')
    op.drop_index('ix_sub_admin_permissions_college_id', table_name='sub_admin_permissions')
    op.drop_table('sub_admin_permissions')

    op.execute("UPDATE users SET role='admin' WHERE role='sub_admin'")
    op.execute(
        "ALTER TABLE users MODIFY COLUMN role "
        "ENUM('super_admin', 'admin', 'teacher', 'student', 'parent') NOT NULL"
    )
