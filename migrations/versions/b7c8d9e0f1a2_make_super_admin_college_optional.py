"""make super admin college optional

Revision ID: b7c8d9e0f1a2
Revises: z2a3b4c5d6e7
Create Date: 2026-05-24 15:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c8d9e0f1a2'
down_revision = 'z2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'college_id',
            existing_type=sa.Integer(),
            nullable=True,
        )

    op.execute("UPDATE users SET college_id = NULL WHERE role = 'super_admin'")


def downgrade():
    op.execute(
        "UPDATE users "
        "SET college_id = (SELECT id FROM colleges ORDER BY id LIMIT 1) "
        "WHERE role = 'super_admin' AND college_id IS NULL"
    )

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'college_id',
            existing_type=sa.Integer(),
            nullable=False,
        )
