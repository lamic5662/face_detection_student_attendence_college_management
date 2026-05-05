"""add college feature access

Revision ID: a4b5c6d7e8f9
Revises: f2a3b4c5d6e7
Create Date: 2026-05-05 23:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4b5c6d7e8f9'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'college_feature_access',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('feature_key', sa.String(length=64), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('college_id', 'feature_key', name='uq_college_feature_access'),
    )
    op.create_index(
        'ix_college_feature_access_college_enabled',
        'college_feature_access',
        ['college_id', 'enabled'],
        unique=False,
    )
    op.create_index(
        op.f('ix_college_feature_access_college_id'),
        'college_feature_access',
        ['college_id'],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f('ix_college_feature_access_college_id'), table_name='college_feature_access')
    op.drop_index('ix_college_feature_access_college_enabled', table_name='college_feature_access')
    op.drop_table('college_feature_access')
