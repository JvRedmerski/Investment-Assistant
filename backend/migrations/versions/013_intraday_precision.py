"""013_intraday_precision

Make `intraday_prices` fit to hold intraday bars (Wave 15).

Three changes, each answering a rule or a measurement:

  - OHLC FLOAT -> NUMERIC(18, 6), per AGENTS.md rule 17. Migration 002
    converted `transactions` and `asset_prices` and named this table
    explicitly as out of scope "until the wave that builds on it is
    implemented". This is that wave.
  - `timestamp` -> TIMESTAMPTZ, per rule 18. It is the only timestamp in
    the schema where the distinction changes an answer: a daily bar is a
    DATE and carries no ambiguity, while a bar stamped 10:15 with no zone
    could be three different instants.
  - `source_window` added NOT NULL. Which request window served a bar is
    part of what the bar means: the vendor returns different OHLCV for
    the same instant depending on it (0 of 135 bars agreed between `5d`
    and `3mo`, while the same window asked twice agreed 135 of 135). See
    ADR-036.

Safe as a plain conversion because the table is empty: nothing has ever
written intraday bars (verified against the development database on
2026-08-22, `SELECT count(*) = 0`). A populated table would have needed
`source_window` added nullable and backfilled first, because there is no
honest default - a stored bar whose window is unknown cannot be shown to
belong to either partition.

The UTC conversion is spelled out rather than left to PostgreSQL's
implicit cast, which would read the existing naive values in the
server's `TimeZone` setting. Every timestamp this project writes is UTC
(`app.data.database.utc_now`), so `AT TIME ZONE 'UTC'` is what preserves
the value's meaning regardless of where the server runs.

Revision ID: 013_intraday_precision_and_window
Revises: 012_corporate_actions
Create Date: 2026-08-22 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013_intraday_precision"
down_revision: Union[str, None] = "012_corporate_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NUMERIC = sa.Numeric(18, 6)
_OHLC_COLUMNS = ["open", "high", "low", "close"]


def upgrade() -> None:
    for column in _OHLC_COLUMNS:
        op.alter_column(
            "intraday_prices",
            column,
            existing_type=sa.Float(),
            type_=_NUMERIC,
            postgresql_using=f"{column}::numeric(18,6)",
            existing_nullable=False,
        )

    op.alter_column(
        "intraday_prices",
        "timestamp",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
        existing_nullable=False,
    )

    op.add_column(
        "intraday_prices",
        sa.Column("source_window", sa.String(length=10), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("intraday_prices", "source_window")

    op.alter_column(
        "intraday_prices",
        "timestamp",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
        existing_nullable=False,
    )

    for column in _OHLC_COLUMNS:
        op.alter_column(
            "intraday_prices",
            column,
            existing_type=_NUMERIC,
            type_=sa.Float(),
            postgresql_using=f"{column}::double precision",
            existing_nullable=False,
        )
