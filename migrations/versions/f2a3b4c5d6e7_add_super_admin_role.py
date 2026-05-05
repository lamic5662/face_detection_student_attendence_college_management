"""add super admin role

Revision ID: f2a3b4c5d6e7
Revises: e7f8a9b0c1d2
Create Date: 2026-05-05 20:05:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = 'f2a3b4c5d6e7'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE users MODIFY COLUMN role "
        "ENUM('super_admin', 'admin', 'teacher', 'student', 'parent') NOT NULL"
    )


def downgrade():
    op.execute("UPDATE users SET role='admin' WHERE role='super_admin'")
    op.execute(
        "ALTER TABLE users MODIFY COLUMN role "
        "ENUM('admin', 'teacher', 'student', 'parent') NOT NULL"
    )
