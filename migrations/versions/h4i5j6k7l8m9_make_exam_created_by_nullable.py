"""make exam created_by nullable for admin-created exams

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-05-07 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = 'h4i5j6k7l8m9'
down_revision = 'g3h4i5j6k7l8'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('exams', 'created_by',
                    existing_type=sa.Integer(),
                    nullable=True)


def downgrade():
    op.execute("UPDATE exams SET created_by = (SELECT id FROM teachers LIMIT 1) WHERE created_by IS NULL")
    op.alter_column('exams', 'created_by',
                    existing_type=sa.Integer(),
                    nullable=False)
