"""add_academic_calendar_events

Revision ID: f1a2b3c4d5e6
Revises: 327c3c6d717a
Create Date: 2026-05-04 21:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = '327c3c6d717a'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'academic_calendar_events' not in inspector.get_table_names():
        op.create_table(
            'academic_calendar_events',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=False),
            sa.Column('category', sa.Enum('holiday', 'exam_week', 'event'), nullable=False),
            sa.Column('start_date', sa.Date(), nullable=False),
            sa.Column('end_date', sa.Date(), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('department_id', sa.Integer(), nullable=True),
            sa.Column('semester', sa.Integer(), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    indexes = {idx['name'] for idx in inspector.get_indexes('academic_calendar_events')}
    if 'ix_academic_calendar_events_dates' not in indexes:
        op.create_index(
            'ix_academic_calendar_events_dates',
            'academic_calendar_events',
            ['start_date', 'end_date'],
            unique=False,
        )


def downgrade():
    op.drop_index('ix_academic_calendar_events_dates', table_name='academic_calendar_events')
    op.drop_table('academic_calendar_events')
