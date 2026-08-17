"""003_numeric_fundamentals_columns

Convert the monetary line items on `fundamentals` from FLOAT to
NUMERIC(24, 4), per AGENTS.md rule 17, extending the same treatment
`002_numeric_money_columns` gave `transactions` and `asset_prices`.

Why NUMERIC(24, 4) here and not the NUMERIC(18, 6) used elsewhere: these
are whole-company figures (revenue, equity, debt) in the tens or hundreds
of billions of BRL, which would consume nearly all of the 12 integer
digits NUMERIC(18, 6) allows. 20 integer digits leaves ample headroom,
and 4 decimal places exceeds what any filing reports.

Scope: fundamentals.revenue/ebitda/net_income/equity/debt/cash/
free_cash_flow. All stay nullable — a source may genuinely not report a
line item, and NULL must never be read as zero.

`financial_indicators` is deliberately untouched: its columns are ratios
and growth rates (P/L, ROE, margins), not currency, so float remains
appropriate there (rule 17 allows float where adequate, provided the
decision is recorded — see app/data/models/fundamentals.py).

Revision ID: 003_numeric_fundamentals_columns
Revises: 002_numeric_money_columns
Create Date: 2026-08-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_numeric_fundamentals_columns"
down_revision: Union[str, None] = "002_numeric_money_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NUMERIC = sa.Numeric(24, 4)

_FUNDAMENTALS_COLUMNS = [
    "revenue",
    "ebitda",
    "net_income",
    "equity",
    "debt",
    "cash",
    "free_cash_flow",
]


def upgrade() -> None:
    for column in _FUNDAMENTALS_COLUMNS:
        op.alter_column(
            "fundamentals",
            column,
            existing_type=sa.Float(),
            type_=_NUMERIC,
            postgresql_using=f"{column}::numeric(24,4)",
            existing_nullable=True,
        )


def downgrade() -> None:
    for column in _FUNDAMENTALS_COLUMNS:
        op.alter_column(
            "fundamentals",
            column,
            existing_type=_NUMERIC,
            type_=sa.Float(),
            postgresql_using=f"{column}::double precision",
            existing_nullable=True,
        )
