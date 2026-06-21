"""add library location hierarchy

Revision ID: q3r4s5t6u7v8
Revises: p2q3r4s5t6u7
Create Date: 2026-05-21 00:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'q3r4s5t6u7v8'
down_revision = 'p2q3r4s5t6u7'
branch_labels = None
depends_on = None


library_location_type = sa.Enum(
    'zone',
    'department_section',
    'room',
    'aisle',
    'rack',
    'shelf',
    'bin',
    name='library_location_type',
)


def upgrade():
    bind = op.get_bind()
    library_location_type.create(bind, checkfirst=True)

    op.create_table(
        'library_locations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=True),
        sa.Column('location_type', library_location_type, nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.ForeignKeyConstraint(['parent_id'], ['library_locations.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('college_id', 'code', name='uq_library_locations_college_code'),
        sa.UniqueConstraint('college_id', 'parent_id', 'name', name='uq_library_locations_college_parent_name'),
    )
    op.create_index('ix_library_locations_college_parent_active', 'library_locations', ['college_id', 'parent_id', 'is_active'], unique=False)
    op.create_index(op.f('ix_library_locations_college_id'), 'library_locations', ['college_id'], unique=False)
    op.create_index(op.f('ix_library_locations_department_id'), 'library_locations', ['department_id'], unique=False)
    op.create_index(op.f('ix_library_locations_parent_id'), 'library_locations', ['parent_id'], unique=False)

    op.add_column('library_books', sa.Column('default_location_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_library_books_default_location_id_library_locations',
        'library_books',
        'library_locations',
        ['default_location_id'],
        ['id'],
    )
    op.create_index(op.f('ix_library_books_default_location_id'), 'library_books', ['default_location_id'], unique=False)

    op.add_column('library_book_copies', sa.Column('location_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_library_book_copies_location_id_library_locations',
        'library_book_copies',
        'library_locations',
        ['location_id'],
        ['id'],
    )
    op.create_index(op.f('ix_library_book_copies_location_id'), 'library_book_copies', ['location_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_library_book_copies_location_id'), table_name='library_book_copies')
    op.drop_constraint('fk_library_book_copies_location_id_library_locations', 'library_book_copies', type_='foreignkey')
    op.drop_column('library_book_copies', 'location_id')

    op.drop_index(op.f('ix_library_books_default_location_id'), table_name='library_books')
    op.drop_constraint('fk_library_books_default_location_id_library_locations', 'library_books', type_='foreignkey')
    op.drop_column('library_books', 'default_location_id')

    op.drop_index(op.f('ix_library_locations_parent_id'), table_name='library_locations')
    op.drop_index(op.f('ix_library_locations_department_id'), table_name='library_locations')
    op.drop_index(op.f('ix_library_locations_college_id'), table_name='library_locations')
    op.drop_index('ix_library_locations_college_parent_active', table_name='library_locations')
    op.drop_table('library_locations')

    bind = op.get_bind()
    library_location_type.drop(bind, checkfirst=True)
