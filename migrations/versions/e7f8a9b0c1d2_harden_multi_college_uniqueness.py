"""harden multi college uniqueness

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-05-05 19:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def _drop_unique_on_columns(table_name, column_names):
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for constraint in inspector.get_unique_constraints(table_name):
        if constraint.get('column_names') == column_names:
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.drop_constraint(constraint['name'], type_='unique')

def _has_unique_constraint(table_name, constraint_name):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        constraint.get('name') == constraint_name
        for constraint in inspector.get_unique_constraints(table_name)
    )


def upgrade():
    _drop_unique_on_columns('leave_requests', ['ref_number'])
    _drop_unique_on_columns('student_id_cards', ['card_number'])

    if not _has_unique_constraint('leave_requests', 'uq_leave_requests_college_ref_number'):
        with op.batch_alter_table('leave_requests') as batch_op:
            batch_op.create_unique_constraint(
                'uq_leave_requests_college_ref_number',
                ['college_id', 'ref_number'],
            )

    if not _has_unique_constraint('student_id_cards', 'uq_student_id_cards_college_card_number'):
        with op.batch_alter_table('student_id_cards') as batch_op:
            batch_op.create_unique_constraint(
                'uq_student_id_cards_college_card_number',
                ['college_id', 'card_number'],
            )

    if not _has_unique_constraint('fee_payments', 'uq_fee_payments_college_receipt_no'):
        with op.batch_alter_table('fee_payments') as batch_op:
            batch_op.create_unique_constraint(
                'uq_fee_payments_college_receipt_no',
                ['college_id', 'receipt_no'],
            )


def downgrade():
    with op.batch_alter_table('fee_payments') as batch_op:
        batch_op.drop_constraint('uq_fee_payments_college_receipt_no', type_='unique')

    with op.batch_alter_table('student_id_cards') as batch_op:
        batch_op.drop_constraint('uq_student_id_cards_college_card_number', type_='unique')

    with op.batch_alter_table('leave_requests') as batch_op:
        batch_op.drop_constraint('uq_leave_requests_college_ref_number', type_='unique')

    with op.batch_alter_table('student_id_cards') as batch_op:
        batch_op.create_unique_constraint('card_number', ['card_number'])

    with op.batch_alter_table('leave_requests') as batch_op:
        batch_op.create_unique_constraint('ref_number', ['ref_number'])
