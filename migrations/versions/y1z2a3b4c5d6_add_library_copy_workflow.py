"""add library copy workflow

Revision ID: y1z2a3b4c5d6
Revises: x0y1z2a3b4c5
Create Date: 2026-05-22 22:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'y1z2a3b4c5d6'
down_revision = 'x0y1z2a3b4c5'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    with op.batch_alter_table('library_book_copies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('replacement_of_copy_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_library_book_copies_replacement_of_copy_id'), ['replacement_of_copy_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_library_book_copies_replacement_of_copy_id',
            'library_book_copies',
            ['replacement_of_copy_id'],
            ['id'],
        )

    op.create_table(
        'library_copy_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('copy_id', sa.Integer(), nullable=False),
        sa.Column('loan_id', sa.Integer(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('previous_status', sa.String(length=50), nullable=True),
        sa.Column('new_status', sa.String(length=50), nullable=True),
        sa.Column('previous_condition', sa.String(length=50), nullable=True),
        sa.Column('new_condition', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['library_books.id']),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.ForeignKeyConstraint(['copy_id'], ['library_book_copies.id']),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['loan_id'], ['library_loans.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_library_copy_events_college_created', 'library_copy_events', ['college_id', 'created_at'], unique=False)
    op.create_index('ix_library_copy_events_copy_created', 'library_copy_events', ['copy_id', 'created_at'], unique=False)

    if dialect_name == 'mysql':
        op.execute(
            "ALTER TABLE library_book_copies "
            "MODIFY status ENUM('available','issued','held','maintenance','damaged','lost','written_off') NOT NULL DEFAULT 'available'"
        )


def downgrade():
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == 'mysql':
        op.execute(
            "ALTER TABLE library_book_copies "
            "MODIFY status ENUM('available','issued','held','maintenance','lost') NOT NULL DEFAULT 'available'"
        )

    op.drop_index('ix_library_copy_events_copy_created', table_name='library_copy_events')
    op.drop_index('ix_library_copy_events_college_created', table_name='library_copy_events')
    op.drop_table('library_copy_events')

    with op.batch_alter_table('library_book_copies', schema=None) as batch_op:
        batch_op.drop_constraint('fk_library_book_copies_replacement_of_copy_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_library_book_copies_replacement_of_copy_id'))
        batch_op.drop_column('replacement_of_copy_id')
