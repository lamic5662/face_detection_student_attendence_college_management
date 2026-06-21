"""add library rules

Revision ID: t6u7v8w9x0y1
Revises: s5t6u7v8w9x0
Create Date: 2026-05-22 13:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 't6u7v8w9x0y1'
down_revision = 's5t6u7v8w9x0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'library_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('student_max_active_loans', sa.Integer(), nullable=False),
        sa.Column('teacher_max_active_loans', sa.Integer(), nullable=False),
        sa.Column('student_due_days', sa.Integer(), nullable=False),
        sa.Column('teacher_due_days', sa.Integer(), nullable=False),
        sa.Column('student_max_renewals', sa.Integer(), nullable=False),
        sa.Column('teacher_max_renewals', sa.Integer(), nullable=False),
        sa.Column('student_renew_days', sa.Integer(), nullable=False),
        sa.Column('teacher_renew_days', sa.Integer(), nullable=False),
        sa.Column('student_fine_per_day', sa.Numeric(10, 2), nullable=False),
        sa.Column('teacher_fine_per_day', sa.Numeric(10, 2), nullable=False),
        sa.Column('grace_days', sa.Integer(), nullable=False),
        sa.Column('regulations', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('college_id', name='uq_library_rules_college'),
    )
    op.create_index(op.f('ix_library_rules_college_id'), 'library_rules', ['college_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_library_rules_college_id'), table_name='library_rules')
    op.drop_table('library_rules')
