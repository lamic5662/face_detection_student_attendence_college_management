"""add library reservations

Revision ID: u7v8w9x0y1z2
Revises: t6u7v8w9x0y1
Create Date: 2026-05-22 16:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'u7v8w9x0y1z2'
down_revision = 't6u7v8w9x0y1'
branch_labels = None
depends_on = None


library_reservation_status = sa.Enum('pending', 'fulfilled', 'cancelled', name='library_reservation_status')


def upgrade():
    bind = op.get_bind()
    library_reservation_status.create(bind, checkfirst=True)

    op.create_table(
        'library_reservations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=True),
        sa.Column('teacher_id', sa.Integer(), nullable=True),
        sa.Column('status', library_reservation_status, nullable=False, server_default='pending'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('fulfilled_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['book_id'], ['library_books.id']),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.ForeignKeyConstraint(['student_id'], ['students.id']),
        sa.ForeignKeyConstraint(['teacher_id'], ['teachers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_library_reservations_college_status_created', 'library_reservations', ['college_id', 'status', 'created_at'], unique=False)
    op.create_index('ix_library_reservations_college_book_status', 'library_reservations', ['college_id', 'book_id', 'status'], unique=False)
    op.create_index('ix_library_reservations_college_student_status', 'library_reservations', ['college_id', 'student_id', 'status'], unique=False)
    op.create_index('ix_library_reservations_college_teacher_status', 'library_reservations', ['college_id', 'teacher_id', 'status'], unique=False)


def downgrade():
    op.drop_index('ix_library_reservations_college_teacher_status', table_name='library_reservations')
    op.drop_index('ix_library_reservations_college_student_status', table_name='library_reservations')
    op.drop_index('ix_library_reservations_college_book_status', table_name='library_reservations')
    op.drop_index('ix_library_reservations_college_status_created', table_name='library_reservations')
    op.drop_table('library_reservations')

    bind = op.get_bind()
    library_reservation_status.drop(bind, checkfirst=True)
