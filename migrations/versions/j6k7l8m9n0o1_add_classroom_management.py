"""Add classroom management tables

Revision ID: j6k7l8m9n0o1
Revises: i5j6k7l8m9n0
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'j6k7l8m9n0o1'
down_revision = 'i5j6k7l8m9n0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'classrooms',
        sa.Column('id',         sa.Integer(),     primary_key=True),
        sa.Column('college_id', sa.Integer(),     sa.ForeignKey('colleges.id'), nullable=False),
        sa.Column('name',       sa.String(100),   nullable=False),
        sa.Column('capacity',   sa.Integer(),     nullable=True),
        sa.Column('room_type',  sa.Enum('lecture_hall', 'lab', 'seminar', 'exam_hall', 'other'),
                  nullable=False, server_default='lecture_hall'),
        sa.Column('block',      sa.String(50),    nullable=True),
        sa.Column('is_active',  sa.Boolean(),     nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(),    nullable=True),
        sa.UniqueConstraint('college_id', 'name', name='uq_classroom_college_name'),
    )
    op.create_index('ix_classrooms_college_active', 'classrooms', ['college_id', 'is_active'])

    op.create_table(
        'classroom_bookings',
        sa.Column('id',            sa.Integer(),  primary_key=True),
        sa.Column('college_id',    sa.Integer(),  sa.ForeignKey('colleges.id'),    nullable=False),
        sa.Column('classroom_id',  sa.Integer(),  sa.ForeignKey('classrooms.id'),  nullable=False),
        sa.Column('department_id', sa.Integer(),  sa.ForeignKey('departments.id'), nullable=True),
        sa.Column('semester',      sa.Integer(),  nullable=True),
        sa.Column('title',         sa.String(150), nullable=False),
        sa.Column('booking_type',  sa.Enum('class', 'exam', 'event', 'other'),
                  nullable=False, server_default='class'),
        sa.Column('is_recurring',  sa.Boolean(),  nullable=False, server_default='0'),
        sa.Column('booking_date',  sa.Date(),     nullable=True),
        sa.Column('day_of_week',   sa.Integer(),  nullable=True),
        sa.Column('valid_from',    sa.Date(),     nullable=True),
        sa.Column('valid_until',   sa.Date(),     nullable=True),
        sa.Column('start_time',    sa.Time(),     nullable=False),
        sa.Column('end_time',      sa.Time(),     nullable=False),
        sa.Column('notes',         sa.Text(),     nullable=True),
        sa.Column('created_by',    sa.Integer(),  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at',    sa.DateTime(), nullable=True),
    )
    op.create_index('ix_cb_college_classroom', 'classroom_bookings', ['college_id', 'classroom_id'])
    op.create_index('ix_cb_college_date',      'classroom_bookings', ['college_id', 'booking_date'])
    op.create_index('ix_cb_recurring_dow',     'classroom_bookings', ['college_id', 'is_recurring', 'day_of_week'])


def downgrade():
    op.drop_table('classroom_bookings')
    op.drop_table('classrooms')
