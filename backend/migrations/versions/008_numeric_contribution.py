"""008_numeric_contribution

Convert `investor_profiles.monthly_contribution` from `Float` to
`NUMERIC(18, 6)`.

Rule 17 forbids binary floating point for money, and this column is the
monthly contribution the whole Wave 09 allocator divides up — the R$
1.000 that the contribution plan turns into per-asset amounts. It was the
last money column with a live consumer still stored as a float:
`intraday_prices` (W15) and `portfolio_snapshots` (W11) have none yet and
convert with the wave that starts using them.

The old shape was visible at the call site. `monthly_contribution_for`
read the float and laundered it through `str` — `Decimal(str(value))` —
precisely because `Decimal(float)` would carry the binary representation
error into an exact-arithmetic pipeline. That workaround only ever hid
the storage problem; with a NUMERIC column SQLAlchemy hands back a
`Decimal` directly and the conversion disappears.

`NUMERIC(18, 6)` matches `transactions` and `asset_prices` from migration
002, so every money column in the schema now has the same precision.

Revision ID: 008_numeric_contribution
Revises: 007_shares_outstanding
Create Date: 2026-08-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_numeric_contribution"
down_revision: Union[str, None] = "007_shares_outstanding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NUMERIC = sa.Numeric(precision=18, scale=6)


def upgrade() -> None:
    op.alter_column(
        "investor_profiles",
        "monthly_contribution",
        existing_type=sa.Float(),
        type_=_NUMERIC,
        postgresql_using="monthly_contribution::numeric(18,6)",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "investor_profiles",
        "monthly_contribution",
        existing_type=_NUMERIC,
        type_=sa.Float(),
        postgresql_using="monthly_contribution::double precision",
        existing_nullable=False,
    )
