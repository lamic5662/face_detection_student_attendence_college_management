"""add library fine ledger

Revision ID: w9x0y1z2a3b4
Revises: v8w9x0y1z2a3
Create Date: 2026-05-22 17:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'w9x0y1z2a3b4'
down_revision = 'v8w9x0y1z2a3'
branch_labels = None
depends_on = None


library_fine_status = sa.Enum('unpaid', 'partial', 'paid', 'waived', name='library_fine_status')


def upgrade():
    bind = op.get_bind()
    library_fine_status.create(bind, checkfirst=True)

    op.create_table(
        'library_fines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('loan_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=True),
        sa.Column('teacher_id', sa.Integer(), nullable=True),
        sa.Column('status', library_fine_status, nullable=False, server_default='unpaid'),
        sa.Column('reason', sa.String(length=100), nullable=False, server_default='overdue'),
        sa.Column('amount_assessed', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('amount_paid', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('amount_waived', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('settled_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('settled_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['book_id'], ['library_books.id']),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['loan_id'], ['library_loans.id']),
        sa.ForeignKeyConstraint(['settled_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['student_id'], ['students.id']),
        sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_library_fines_college_status_created', 'library_fines', ['college_id', 'status', 'created_at'], unique=False)
    op.create_index('ix_library_fines_college_student_status', 'library_fines', ['college_id', 'student_id', 'status'], unique=False)
    op.create_index('ix_library_fines_college_teacher_status', 'library_fines', ['college_id', 'teacher_id', 'status'], unique=False)


def downgrade():
    op.drop_index('ix_library_fines_college_teacher_status', table_name='library_fines')
    op.drop_index('ix_library_fines_college_student_status', table_name='library_fines')
    op.drop_index('ix_library_fines_college_status_created', table_name='library_fines')
    op.drop_table('library_fines')

    bind = op.get_bind()
    library_fine_status.drop(bind, checkfirst=True)
