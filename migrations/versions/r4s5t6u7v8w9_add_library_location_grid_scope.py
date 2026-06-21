"""add library location grid scope

Revision ID: r4s5t6u7v8w9
Revises: q3r4s5t6u7v8
Create Date: 2026-05-21 01:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'r4s5t6u7v8w9'
down_revision = 'q3r4s5t6u7v8'
branch_labels = None
depends_on = None


old_location_enum = sa.Enum(
    'zone',
    'department_section',
    'room',
    'aisle',
    'rack',
    'shelf',
    'bin',
    name='library_location_type',
)
new_location_enum = sa.Enum(
    'zone',
    'department_section',
    'room',
    'aisle',
    'rack',
    'shelf',
    'bin',
    'cell',
    name='library_location_type',
)


def upgrade():
    op.alter_column(
        'library_locations',
        'location_type',
        existing_type=old_location_enum,
        type_=new_location_enum,
        existing_nullable=False,
    )
    op.add_column('library_locations', sa.Column('subject_id', sa.Integer(), nullable=True))
    op.add_column('library_locations', sa.Column('semester', sa.Integer(), nullable=True))
    op.add_column('library_locations', sa.Column('row_label', sa.String(length=30), nullable=True))
    op.add_column('library_locations', sa.Column('column_label', sa.String(length=30), nullable=True))
    op.create_foreign_key(
        'fk_library_locations_subject_id_subjects',
        'library_locations',
        'subjects',
        ['subject_id'],
        ['id'],
    )
    op.create_index(op.f('ix_library_locations_subject_id'), 'library_locations', ['subject_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_library_locations_subject_id'), table_name='library_locations')
    op.drop_constraint('fk_library_locations_subject_id_subjects', 'library_locations', type_='foreignkey')
    op.drop_column('library_locations', 'column_label')
    op.drop_column('library_locations', 'row_label')
    op.drop_column('library_locations', 'semester')
    op.drop_column('library_locations', 'subject_id')
    op.execute("UPDATE library_locations SET location_type = 'bin' WHERE location_type = 'cell'")
    op.alter_column(
        'library_locations',
        'location_type',
        existing_type=new_location_enum,
        type_=old_location_enum,
        existing_nullable=False,
    )
