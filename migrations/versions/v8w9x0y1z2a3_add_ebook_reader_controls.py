"""add ebook reader controls

Revision ID: v8w9x0y1z2a3
Revises: u7v8w9x0y1z2
Create Date: 2026-05-22 16:50:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v8w9x0y1z2a3'
down_revision = 'u7v8w9x0y1z2'
branch_labels = None
depends_on = None


library_ebook_access_level = sa.Enum('preview_only', 'full_read', name='library_ebook_access_level')


def upgrade():
    bind = op.get_bind()
    library_ebook_access_level.create(bind, checkfirst=True)

    op.add_column(
        'library_books',
        sa.Column('ebook_access_level', library_ebook_access_level, nullable=False, server_default='full_read'),
    )
    op.add_column(
        'library_books',
        sa.Column('ebook_download_allowed', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'library_books',
        sa.Column('ebook_preview_page_limit', sa.Integer(), nullable=True),
    )

    op.create_table(
        'library_reading_progress',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('last_page', sa.Integer(), nullable=True),
        sa.Column('progress_percent', sa.Numeric(5, 2), nullable=True),
        sa.Column('last_position', sa.String(length=255), nullable=True),
        sa.Column('total_pages', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_read_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['library_books.id']),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('college_id', 'book_id', 'user_id', name='uq_library_reading_progress_user_book'),
    )
    op.create_index('ix_library_reading_progress_college_user', 'library_reading_progress', ['college_id', 'user_id'], unique=False)
    op.create_index('ix_library_reading_progress_college_book', 'library_reading_progress', ['college_id', 'book_id'], unique=False)


def downgrade():
    op.drop_index('ix_library_reading_progress_college_book', table_name='library_reading_progress')
    op.drop_index('ix_library_reading_progress_college_user', table_name='library_reading_progress')
    op.drop_table('library_reading_progress')

    op.drop_column('library_books', 'ebook_preview_page_limit')
    op.drop_column('library_books', 'ebook_download_allowed')
    op.drop_column('library_books', 'ebook_access_level')

    bind = op.get_bind()
    library_ebook_access_level.drop(bind, checkfirst=True)
