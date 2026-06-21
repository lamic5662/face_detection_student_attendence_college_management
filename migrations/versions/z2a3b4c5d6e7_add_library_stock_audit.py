"""add library stock audit

Revision ID: z2a3b4c5d6e7
Revises: y1z2a3b4c5d6
Create Date: 2026-05-22 22:50:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'z2a3b4c5d6e7'
down_revision = 'y1z2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'library_audit_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('college_id', sa.Integer(), nullable=False),
        sa.Column('rack_id', sa.Integer(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.Column('completed_by_user_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('open', 'completed', name='library_audit_status'), nullable=False),
        sa.Column('expected_count', sa.Integer(), nullable=False),
        sa.Column('scanned_count', sa.Integer(), nullable=False),
        sa.Column('missing_count', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['college_id'], ['colleges.id']),
        sa.ForeignKeyConstraint(['completed_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['rack_id'], ['library_locations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_library_audit_sessions_college_status_started', 'library_audit_sessions', ['college_id', 'status', 'started_at'], unique=False)

    op.create_table(
        'library_audit_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('copy_id', sa.Integer(), nullable=False),
        sa.Column('expected_status', sa.String(length=50), nullable=False),
        sa.Column('expected_condition', sa.String(length=50), nullable=True),
        sa.Column('is_present', sa.Boolean(), nullable=False),
        sa.Column('scanned_at', sa.DateTime(), nullable=True),
        sa.Column('scanned_by_user_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['copy_id'], ['library_book_copies.id']),
        sa.ForeignKeyConstraint(['scanned_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['session_id'], ['library_audit_sessions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'copy_id', name='uq_library_audit_entries_session_copy'),
    )
    op.create_index('ix_library_audit_entries_session_present', 'library_audit_entries', ['session_id', 'is_present'], unique=False)


def downgrade():
    op.drop_index('ix_library_audit_entries_session_present', table_name='library_audit_entries')
    op.drop_table('library_audit_entries')
    op.drop_index('ix_library_audit_sessions_college_status_started', table_name='library_audit_sessions')
    op.drop_table('library_audit_sessions')
