"""add department university affiliation

Revision ID: e7f8g9h0i1j2
Revises: d6e7f8g9h0i1
Create Date: 2026-05-23 13:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f8g9h0i1j2'
down_revision = 'd6e7f8g9h0i1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('departments', sa.Column('university_id', sa.Integer(), nullable=True))
    op.create_index('ix_departments_university_id', 'departments', ['university_id'], unique=False)
    op.create_foreign_key(
        'fk_departments_university_id_universities',
        'departments',
        'universities',
        ['university_id'],
        ['id'],
    )

    op.execute(
        """
        UPDATE departments d
        JOIN colleges c ON c.id = d.college_id
        SET d.university_id = c.university_id
        WHERE d.university_id IS NULL
          AND c.university_id IS NOT NULL
        """
    )


def downgrade():
    op.drop_constraint('fk_departments_university_id_universities', 'departments', type_='foreignkey')
    op.drop_index('ix_departments_university_id', table_name='departments')
    op.drop_column('departments', 'university_id')
