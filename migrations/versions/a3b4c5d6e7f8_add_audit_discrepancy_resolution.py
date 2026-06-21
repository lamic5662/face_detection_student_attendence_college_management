"""add audit discrepancy resolution

Revision ID: a3b4c5d6e7f8
Revises: z2a3b4c5d6e7
Create Date: 2026-05-22 23:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3b4c5d6e7f8'
down_revision = 'z2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('library_audit_entries', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'discrepancy_status',
                sa.Enum('unresolved', 'follow_up_required', 'marked_lost', 'marked_damaged', name='library_audit_discrepancy_status'),
                nullable=False,
                server_default='unresolved',
            )
        )
        batch_op.add_column(sa.Column('resolved_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('resolved_by_user_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_library_audit_entries_resolved_by_user_id'), ['resolved_by_user_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_library_audit_entries_resolved_by_user_id',
            'users',
            ['resolved_by_user_id'],
            ['id'],
        )


def downgrade():
    with op.batch_alter_table('library_audit_entries', schema=None) as batch_op:
        batch_op.drop_constraint('fk_library_audit_entries_resolved_by_user_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_library_audit_entries_resolved_by_user_id'))
        batch_op.drop_column('resolved_by_user_id')
        batch_op.drop_column('resolved_at')
        batch_op.drop_column('discrepancy_status')
