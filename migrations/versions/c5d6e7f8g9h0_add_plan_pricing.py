"""add plan pricing

Revision ID: c5d6e7f8g9h0
Revises: b4c5d6e7f8g9
Create Date: 2026-05-23 09:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'c5d6e7f8g9h0'
down_revision = 'b4c5d6e7f8g9'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if 'plan_pricing' not in inspector.get_table_names():
        op.create_table(
            'plan_pricing',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('plan_key', sa.String(length=32), nullable=False),
            sa.Column('price_label', sa.String(length=120), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('plan_key', name='uq_plan_pricing_plan_key'),
        )
        op.create_index(op.f('ix_plan_pricing_plan_key'), 'plan_pricing', ['plan_key'], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if 'plan_pricing' in inspector.get_table_names():
        op.drop_index(op.f('ix_plan_pricing_plan_key'), table_name='plan_pricing')
        op.drop_table('plan_pricing')
