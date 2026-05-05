"""add assignment submissions

Revision ID: c2d4e6f8a1b0
Revises: a7b8c9d0e1f2
Create Date: 2026-05-05 17:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'c2d4e6f8a1b0'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    if 'assignment_submissions' not in inspector.get_table_names():
        op.create_table(
            'assignment_submissions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('content_id', sa.Integer(), nullable=False),
            sa.Column('student_id', sa.Integer(), nullable=False),
            sa.Column('submission_text', sa.Text(), nullable=True),
            sa.Column('file_path', sa.String(length=255), nullable=True),
            sa.Column('status', sa.Enum('submitted', 'reviewed', name='submission_statuses'), nullable=False),
            sa.Column('submitted_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('graded_at', sa.DateTime(), nullable=True),
            sa.Column('marks_awarded', sa.Integer(), nullable=True),
            sa.Column('feedback', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['content_id'], ['teacher_contents.id']),
            sa.ForeignKeyConstraint(['student_id'], ['students.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('content_id', 'student_id', name='uq_assignment_submission_content_student'),
        )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if 'assignment_submissions' in inspector.get_table_names():
        op.drop_table('assignment_submissions')
