"""add check constraints and indexes for data integrity and query performance

Revision ID: df8beb210e38
Revises: 7cb52c44501f
Create Date: 2026-07-04 10:34:09.560770

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df8beb210e38'
down_revision: Union[str, Sequence[str], None] = '7cb52c44501f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(op.f('ix_claims_cause'), 'claims', ['cause'], unique=False)
    op.create_index(op.f('ix_claims_final_payout'), 'claims', ['final_payout'], unique=False)
    op.create_index(op.f('ix_claims_loss_date'), 'claims', ['loss_date'], unique=False)
    op.create_index(op.f('ix_claims_policy_id'), 'claims', ['policy_id'], unique=False)
    op.create_index(op.f('ix_customers_city'), 'customers', ['city'], unique=False)
    op.create_index(op.f('ix_policies_customer_id'), 'policies', ['customer_id'], unique=False)
    op.create_index(op.f('ix_policies_state'), 'policies', ['state'], unique=False)

    # NOTE: Alembic's autogenerate does not reliably detect CHECK constraint
    # changes (a known limitation, not specific to this schema) -- these five
    # were added to models.py but did not show up in the autogenerate diff
    # above. Added by hand here after manually diffing models.py against the
    # previous migration. SQLite also can't ALTER TABLE ADD CONSTRAINT
    # directly, so these go through batch mode, which rebuilds the table
    # under the hood.
    with op.batch_alter_table("customers") as batch_op:
        batch_op.create_check_constraint(
            "ck_customers_age_range", "age >= 0 AND age <= 130"
        )

    with op.batch_alter_table("policies") as batch_op:
        batch_op.create_check_constraint(
            "ck_policies_coverage_limit_positive", "coverage_limit > 0"
        )
        batch_op.create_check_constraint(
            "ck_policies_deductible_non_negative", "deductible >= 0"
        )

    with op.batch_alter_table("claims") as batch_op:
        batch_op.create_check_constraint(
            "ck_claims_loss_amount_non_negative", "loss_amount >= 0"
        )
        batch_op.create_check_constraint(
            "ck_claims_final_payout_non_negative", "final_payout >= 0"
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("claims") as batch_op:
        batch_op.drop_constraint("ck_claims_final_payout_non_negative", type_="check")
        batch_op.drop_constraint("ck_claims_loss_amount_non_negative", type_="check")

    with op.batch_alter_table("policies") as batch_op:
        batch_op.drop_constraint("ck_policies_deductible_non_negative", type_="check")
        batch_op.drop_constraint("ck_policies_coverage_limit_positive", type_="check")

    with op.batch_alter_table("customers") as batch_op:
        batch_op.drop_constraint("ck_customers_age_range", type_="check")

    op.drop_index(op.f('ix_policies_state'), table_name='policies')
    op.drop_index(op.f('ix_policies_customer_id'), table_name='policies')
    op.drop_index(op.f('ix_customers_city'), table_name='customers')
    op.drop_index(op.f('ix_claims_policy_id'), table_name='claims')
    op.drop_index(op.f('ix_claims_loss_date'), table_name='claims')
    op.drop_index(op.f('ix_claims_final_payout'), table_name='claims')
    op.drop_index(op.f('ix_claims_cause'), table_name='claims')
