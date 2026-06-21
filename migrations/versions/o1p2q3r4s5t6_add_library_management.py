"""add library management

Revision ID: o1p2q3r4s5t6
Revises: n0o1p2q3r4s5
Create Date: 2026-05-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'o1p2q3r4s5t6'
down_revision = 'n0o1p2q3r4s5'
branch_labels = None
depends_on = None


library_book_type = sa.Enum('physical', 'digital', 'hybrid', name='library_book_type')
library_copy_condition = sa.Enum('new', 'good', 'fair', 'damaged', name='library_copy_condition')
library_copy_status = sa.Enum('available', 'issued', 'maintenance', 'lost', name='library_copy_status')
library_loan_status = sa.Enum('active', 'returned', 'overdue', 'lost', name='library_loan_status')
library_access_action = sa.Enum('view', 'download', name='library_access_action')


def upgrade():
    bind = op.get_bind()
    library_book_type.create(bind, checkfirst=True)
    library_copy_condition.create(bind, checkfirst=True)
    library_copy_status.create(bind, checkfirst=True)
    library_loan_status.create(bind, checkfirst=True)
    library_access_action.create(bind, checkfirst=True)

    op.create_table(
        'library_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('college_id', 'name', name='uq_library_categories_college_name'),
    )
    op.create_index(op.f('ix_library_categories_college_id'), 'library_categories', ['college_id'], unique=False)

    op.create_table(
        'library_books',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('subject_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('author', sa.String(length=200), nullable=False),
        sa.Column('isbn', sa.String(length=32), nullable=True),
        sa.Column('publisher', sa.String(length=200), nullable=True),
        sa.Column('edition', sa.String(length=100), nullable=True),
        sa.Column('language', sa.String(length=50), nullable=True),
        sa.Column('semester', sa.Integer(), nullable=True),
        sa.Column('book_type', library_book_type, nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', sa.String(length=255), nullable=True),
        sa.Column('shelf_code', sa.String(length=100), nullable=True),
        sa.Column('ebook_file_path', sa.String(length=255), nullable=True),
        sa.Column('ebook_filename', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['library_categories.id']),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('college_id', 'isbn', name='uq_library_books_college_isbn'),
    )
    op.create_index('ix_library_books_college_department_semester', 'library_books', ['college_id', 'department_id', 'semester'], unique=False)
    op.create_index('ix_library_books_college_type_active', 'library_books', ['college_id', 'book_type', 'is_active'], unique=False)
    op.create_index(op.f('ix_library_books_category_id'), 'library_books', ['category_id'], unique=False)
    op.create_index(op.f('ix_library_books_college_id'), 'library_books', ['college_id'], unique=False)
    op.create_index(op.f('ix_library_books_department_id'), 'library_books', ['department_id'], unique=False)
    op.create_index(op.f('ix_library_books_subject_id'), 'library_books', ['subject_id'], unique=False)

    op.create_table(
        'library_book_copies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('accession_number', sa.String(length=50), nullable=False),
        sa.Column('barcode', sa.String(length=100), nullable=True),
        sa.Column('rack_location', sa.String(length=100), nullable=True),
        sa.Column('condition', library_copy_condition, nullable=False),
        sa.Column('status', library_copy_status, nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['library_books.id']),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('college_id', 'accession_number', name='uq_library_copies_college_accession'),
    )
    op.create_index('ix_library_copies_college_status', 'library_book_copies', ['college_id', 'status'], unique=False)
    op.create_index(op.f('ix_library_book_copies_book_id'), 'library_book_copies', ['book_id'], unique=False)
    op.create_index(op.f('ix_library_book_copies_college_id'), 'library_book_copies', ['college_id'], unique=False)

    op.create_table(
        'library_loans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('copy_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=True),
        sa.Column('teacher_id', sa.Integer(), nullable=True),
        sa.Column('issued_by_user_id', sa.Integer(), nullable=False),
        sa.Column('returned_to_user_id', sa.Integer(), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=False),
        sa.Column('due_at', sa.DateTime(), nullable=False),
        sa.Column('returned_at', sa.DateTime(), nullable=True),
        sa.Column('renewed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', library_loan_status, nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('fine_amount', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['book_id'], ['library_books.id']),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.ForeignKeyConstraint(['copy_id'], ['library_book_copies.id']),
        sa.ForeignKeyConstraint(['issued_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['returned_to_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['student_id'], ['students.id']),
        sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_library_loans_college_status_due', 'library_loans', ['college_id', 'status', 'due_at'], unique=False)
    op.create_index('ix_library_loans_college_student_status', 'library_loans', ['college_id', 'student_id', 'status'], unique=False)
    op.create_index('ix_library_loans_college_teacher_status', 'library_loans', ['college_id', 'teacher_id', 'status'], unique=False)
    op.create_index(op.f('ix_library_loans_book_id'), 'library_loans', ['book_id'], unique=False)
    op.create_index(op.f('ix_library_loans_college_id'), 'library_loans', ['college_id'], unique=False)
    op.create_index(op.f('ix_library_loans_copy_id'), 'library_loans', ['copy_id'], unique=False)
    op.create_index(op.f('ix_library_loans_issued_by_user_id'), 'library_loans', ['issued_by_user_id'], unique=False)
    op.create_index(op.f('ix_library_loans_returned_to_user_id'), 'library_loans', ['returned_to_user_id'], unique=False)
    op.create_index(op.f('ix_library_loans_student_id'), 'library_loans', ['student_id'], unique=False)
    op.create_index(op.f('ix_library_loans_teacher_id'), 'library_loans', ['teacher_id'], unique=False)

    op.create_table(
        'library_access_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=True),
        sa.Column('teacher_id', sa.Integer(), nullable=True),
        sa.Column('action', library_access_action, nullable=False),
        sa.Column('accessed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['library_books.id']),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.ForeignKeyConstraint(['student_id'], ['students.id']),
        sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_library_access_logs_college_book_action', 'library_access_logs', ['college_id', 'book_id', 'action'], unique=False)
    op.create_index(op.f('ix_library_access_logs_book_id'), 'library_access_logs', ['book_id'], unique=False)
    op.create_index(op.f('ix_library_access_logs_college_id'), 'library_access_logs', ['college_id'], unique=False)
    op.create_index(op.f('ix_library_access_logs_student_id'), 'library_access_logs', ['student_id'], unique=False)
    op.create_index(op.f('ix_library_access_logs_teacher_id'), 'library_access_logs', ['teacher_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_library_access_logs_teacher_id'), table_name='library_access_logs')
    op.drop_index(op.f('ix_library_access_logs_student_id'), table_name='library_access_logs')
    op.drop_index(op.f('ix_library_access_logs_college_id'), table_name='library_access_logs')
    op.drop_index(op.f('ix_library_access_logs_book_id'), table_name='library_access_logs')
    op.drop_index('ix_library_access_logs_college_book_action', table_name='library_access_logs')
    op.drop_table('library_access_logs')

    op.drop_index(op.f('ix_library_loans_teacher_id'), table_name='library_loans')
    op.drop_index(op.f('ix_library_loans_student_id'), table_name='library_loans')
    op.drop_index(op.f('ix_library_loans_returned_to_user_id'), table_name='library_loans')
    op.drop_index(op.f('ix_library_loans_issued_by_user_id'), table_name='library_loans')
    op.drop_index(op.f('ix_library_loans_copy_id'), table_name='library_loans')
    op.drop_index(op.f('ix_library_loans_college_id'), table_name='library_loans')
    op.drop_index(op.f('ix_library_loans_book_id'), table_name='library_loans')
    op.drop_index('ix_library_loans_college_teacher_status', table_name='library_loans')
    op.drop_index('ix_library_loans_college_student_status', table_name='library_loans')
    op.drop_index('ix_library_loans_college_status_due', table_name='library_loans')
    op.drop_table('library_loans')

    op.drop_index(op.f('ix_library_book_copies_college_id'), table_name='library_book_copies')
    op.drop_index(op.f('ix_library_book_copies_book_id'), table_name='library_book_copies')
    op.drop_index('ix_library_copies_college_status', table_name='library_book_copies')
    op.drop_table('library_book_copies')

    op.drop_index(op.f('ix_library_books_subject_id'), table_name='library_books')
    op.drop_index(op.f('ix_library_books_department_id'), table_name='library_books')
    op.drop_index(op.f('ix_library_books_college_id'), table_name='library_books')
    op.drop_index(op.f('ix_library_books_category_id'), table_name='library_books')
    op.drop_index('ix_library_books_college_type_active', table_name='library_books')
    op.drop_index('ix_library_books_college_department_semester', table_name='library_books')
    op.drop_table('library_books')

    op.drop_index(op.f('ix_library_categories_college_id'), table_name='library_categories')
    op.drop_table('library_categories')

    bind = op.get_bind()
    library_access_action.drop(bind, checkfirst=True)
    library_loan_status.drop(bind, checkfirst=True)
    library_copy_status.drop(bind, checkfirst=True)
    library_copy_condition.drop(bind, checkfirst=True)
    library_book_type.drop(bind, checkfirst=True)
