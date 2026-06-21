"""add university management

Revision ID: d6e7f8g9h0i1
Revises: c5d6e7f8g9h0
Create Date: 2026-05-23 12:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'd6e7f8g9h0i1'
down_revision = 'c5d6e7f8g9h0'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    table_names = inspector.get_table_names()

    if 'universities' not in table_names:
        op.create_table(
            'universities',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('code', sa.String(length=30), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('code', name='uq_universities_code'),
            sa.UniqueConstraint('name', name='uq_universities_name'),
        )
        op.create_index('ix_universities_code', 'universities', ['code'], unique=False)

    college_columns = {col['name'] for col in inspector.get_columns('colleges')}
    if 'university_id' not in college_columns:
        op.add_column('colleges', sa.Column('university_id', sa.Integer(), nullable=True))
        op.create_index('ix_colleges_university_id', 'colleges', ['university_id'], unique=False)
        op.create_foreign_key(
            'fk_colleges_university_id_universities',
            'colleges',
            'universities',
            ['university_id'],
            ['id'],
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    college_columns = {col['name'] for col in inspector.get_columns('colleges')}
    if 'university_id' in college_columns:
        foreign_keys = {fk['name'] for fk in inspector.get_foreign_keys('colleges')}
        if 'fk_colleges_university_id_universities' in foreign_keys:
            op.drop_constraint('fk_colleges_university_id_universities', 'colleges', type_='foreignkey')
        indexes = {idx['name'] for idx in inspector.get_indexes('colleges')}
        if 'ix_colleges_university_id' in indexes:
            op.drop_index('ix_colleges_university_id', table_name='colleges')
        op.drop_column('colleges', 'university_id')

    if 'universities' in inspector.get_table_names():
        indexes = {idx['name'] for idx in inspector.get_indexes('universities')}
        if 'ix_universities_code' in indexes:
            op.drop_index('ix_universities_code', table_name='universities')
        op.drop_table('universities')
