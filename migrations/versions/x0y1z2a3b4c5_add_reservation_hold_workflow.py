"""add reservation hold workflow

Revision ID: x0y1z2a3b4c5
Revises: w9x0y1z2a3b4
Create Date: 2026-05-22 20:55:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'x0y1z2a3b4c5'
down_revision = 'w9x0y1z2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('library_rules', sa.Column('reservation_hold_days', sa.Integer(), nullable=False, server_default='2'))
    op.alter_column('library_rules', 'reservation_hold_days', server_default=None)

    op.add_column('library_reservations', sa.Column('held_copy_id', sa.Integer(), nullable=True))
    op.add_column('library_reservations', sa.Column('ready_at', sa.DateTime(), nullable=True))
    op.add_column('library_reservations', sa.Column('pickup_expires_at', sa.DateTime(), nullable=True))
    op.add_column('library_reservations', sa.Column('expired_at', sa.DateTime(), nullable=True))
    op.create_index('ix_library_reservations_held_copy_id', 'library_reservations', ['held_copy_id'], unique=False)
    op.create_foreign_key(
        'fk_library_reservations_held_copy_id',
        'library_reservations',
        'library_book_copies',
        ['held_copy_id'],
        ['id'],
    )

    op.execute(
        "ALTER TABLE library_book_copies "
        "MODIFY COLUMN status ENUM('available','issued','held','maintenance','lost') NOT NULL DEFAULT 'available'"
    )
    op.execute(
        "ALTER TABLE library_reservations "
        "MODIFY COLUMN status ENUM('pending','ready_for_pickup','fulfilled','cancelled','expired') NOT NULL DEFAULT 'pending'"
    )


def downgrade():
    op.execute(
        "ALTER TABLE library_reservations "
        "MODIFY COLUMN status ENUM('pending','fulfilled','cancelled') NOT NULL DEFAULT 'pending'"
    )
    op.execute(
        "ALTER TABLE library_book_copies "
        "MODIFY COLUMN status ENUM('available','issued','maintenance','lost') NOT NULL DEFAULT 'available'"
    )

    op.drop_constraint('fk_library_reservations_held_copy_id', 'library_reservations', type_='foreignkey')
    op.drop_index('ix_library_reservations_held_copy_id', table_name='library_reservations')
    op.drop_column('library_reservations', 'expired_at')
    op.drop_column('library_reservations', 'pickup_expires_at')
    op.drop_column('library_reservations', 'ready_at')
    op.drop_column('library_reservations', 'held_copy_id')
    op.drop_column('library_rules', 'reservation_hold_days')
