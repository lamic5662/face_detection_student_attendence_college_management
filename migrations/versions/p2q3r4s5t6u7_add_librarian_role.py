"""add librarian role

Revision ID: p2q3r4s5t6u7
Revises: o1p2q3r4s5t6
Create Date: 2026-05-21 00:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p2q3r4s5t6u7'
down_revision = 'o1p2q3r4s5t6'
branch_labels = None
depends_on = None


old_role_enum = sa.Enum('super_admin', 'admin', 'sub_admin', 'teacher', 'student', 'parent', name='users_role')
new_role_enum = sa.Enum('super_admin', 'admin', 'sub_admin', 'teacher', 'student', 'parent', 'librarian', name='users_role')


def upgrade():
    op.alter_column(
        'users',
        'role',
        existing_type=old_role_enum,
        type_=new_role_enum,
        existing_nullable=False,
    )


def downgrade():
    op.execute("DELETE FROM users WHERE role = 'librarian'")
    op.alter_column(
        'users',
        'role',
        existing_type=new_role_enum,
        type_=old_role_enum,
        existing_nullable=False,
    )
