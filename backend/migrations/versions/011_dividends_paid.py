"""011_dividends_paid

Add `fundamentals.dividends_paid`: what the company charged to equity as
distributions during the period — dividends plus interest on capital.

This is the last input any indicator was missing. `dy` had a formula
written and tested since W06-002 and no source to feed it: the market
data vendor publishes `dividendYield` only as a **present-day snapshot
with no period end**, and applying today's yield to a past statement is
the point-in-time violation rules 108/109 forbid.

The CVM's statement of changes in equity (DMPL) reports it per fiscal
year, dated to that year — `5.04.06` for dividends and `5.04.07` for
interest on capital, both in the `Patrimônio Líquido` column. Measured
across the archives the project already downloads, 147 to 210 companies
file a non-zero distribution per year; PETR4 shows R$ 224.06 bn for 2022
and R$ 100.90 bn for 2024.

Stored as the aggregate rather than per share, for the same reason
`net_income` and `equity` are: the per-share figure is derived at
indicator time from the share count belonging to the same period, so a
later restatement of either cannot leave the two out of step.

NULL means the filing reported no distribution line — which is the honest
answer for a company that paid nothing, and different from zero only in
that nobody said so.

Revision ID: 011_dividends_paid
Revises: 010_nullable_adj_close
Create Date: 2026-08-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011_dividends_paid"
down_revision: Union[str, None] = "010_nullable_adj_close"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Same precision as every other figure in `fundamentals` (migration 003).
STATEMENT_MONEY = sa.Numeric(24, 4)


def upgrade() -> None:
    op.add_column(
        "fundamentals",
        sa.Column("dividends_paid", STATEMENT_MONEY, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fundamentals", "dividends_paid")
