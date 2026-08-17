"""002_numeric_money_columns

Convert monetary/quantity columns on `transactions` and `asset_prices`
from FLOAT to NUMERIC(18, 6), per AGENTS.md rule 17 ("never use float
indiscriminately for critical monetary values; prefer Decimal/NUMERIC").

Scope of this migration (see docs/PROJECT_STATUS.md Technical Decisions,
2026-08-16, "Monetary precision"):
  - transactions.quantity, transactions.price, transactions.fees
  - asset_prices.open/high/low/close/adjusted_close (volume stays FLOAT,
    it is a share count, not a monetary value)

Deliberately out of scope for now (tracked as Future Work): intraday_prices
OHLC (Wave 15), portfolio_snapshots.total_value/cash_value and
investor_profiles.monthly_contribution. These will be converted in a later
migration when the waves that build on them are implemented.

Revision ID: 002_numeric_money_columns
Revises: 001_initial_schema
Create Date: 2026-08-16 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_numeric_money_columns"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NUMERIC = sa.Numeric(18, 6)

_TRANSACTIONS_COLUMNS = ["quantity", "price", "fees"]
_ASSET_PRICES_COLUMNS = ["open", "high", "low", "close", "adjusted_close"]


def upgrade() -> None:
    for column in _TRANSACTIONS_COLUMNS:
        op.alter_column(
            "transactions",
            column,
            existing_type=sa.Float(),
            type_=_NUMERIC,
            postgresql_using=f"{column}::numeric(18,6)",
            existing_nullable=False,
        )

    for column in _ASSET_PRICES_COLUMNS:
        op.alter_column(
            "asset_prices",
            column,
            existing_type=sa.Float(),
            type_=_NUMERIC,
            postgresql_using=f"{column}::numeric(18,6)",
            existing_nullable=False,
        )


def downgrade() -> None:
    for column in _ASSET_PRICES_COLUMNS:
        op.alter_column(
            "asset_prices",
            column,
            existing_type=_NUMERIC,
            type_=sa.Float(),
            postgresql_using=f"{column}::double precision",
            existing_nullable=False,
        )

    for column in _TRANSACTIONS_COLUMNS:
        op.alter_column(
            "transactions",
            column,
            existing_type=_NUMERIC,
            type_=sa.Float(),
            postgresql_using=f"{column}::double precision",
            existing_nullable=False,
        )
