"""004_fundamentals_income_detail

Add three income statement line items to `fundamentals`, all confirmed
present in every one of the 16 annual periods Brapi returns for PETR4
(W06-003 validated the provider against a live response for the first
time):

  - ebit                 -> unblocks ROIC
  - income_before_tax    -> \\
  - income_tax_expense   -> /  effective tax rate, derived per period

The two tax figures are stored as reported rather than storing a
precomputed rate, so the derivation stays in the pure calculation module
and the stored data remains exactly what the source published.

Storing the effective rate instead of the raw figures was rejected: it
would bake a derived value into the historical record, and ADR-014
requires that ROIC never rest on an assumed rate. Brapi's own
`cleanNopat` field applies a flat 34% to every period, while the actual
effective rates for PETR4 range from 26.6% to 32.4% — which is exactly
why the raw figures are kept.

All columns are nullable: a source may not report them, and NULL must
never be read as zero.

Revision ID: 004_fundamentals_income_detail
Revises: 003_numeric_fundamentals_columns
Create Date: 2026-08-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_fundamentals_income_detail"
down_revision: Union[str, None] = "003_numeric_fundamentals_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NUMERIC = sa.Numeric(24, 4)

_NEW_COLUMNS = ["ebit", "income_before_tax", "income_tax_expense"]


def upgrade() -> None:
    for column in _NEW_COLUMNS:
        op.add_column("fundamentals", sa.Column(column, _NUMERIC, nullable=True))


def downgrade() -> None:
    for column in reversed(_NEW_COLUMNS):
        op.drop_column("fundamentals", column)
