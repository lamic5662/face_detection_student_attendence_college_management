"""add password setup fields to users

Revision ID: d6e7f8a9b0c1
Revises: c6d7e8f9a0b1
Create Date: 2026-05-06 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd6e7f8a9b0c1'
down_revision = 'c6d7e8f9a0b1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('password_changed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('password_setup_email_sent_at', sa.DateTime(), nullable=True))

    op.execute(
        "UPDATE users SET must_change_password = 0 "
        "WHERE must_change_password IS NULL"
    )


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('password_setup_email_sent_at')
        batch_op.drop_column('password_changed_at')
        batch_op.drop_column('must_change_password')
