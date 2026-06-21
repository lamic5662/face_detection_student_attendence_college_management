"""add rack grid dimensions

Revision ID: s5t6u7v8w9x0
Revises: r4s5t6u7v8w9
Create Date: 2026-05-21 01:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 's5t6u7v8w9x0'
down_revision = 'r4s5t6u7v8w9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('library_locations', sa.Column('row_count', sa.Integer(), nullable=True))
    op.add_column('library_locations', sa.Column('column_count', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('library_locations', 'column_count')
    op.drop_column('library_locations', 'row_count')
