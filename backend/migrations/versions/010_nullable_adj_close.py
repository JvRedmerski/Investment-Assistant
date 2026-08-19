"""010_nullable_adj_close

Let `asset_prices.adjusted_close` be NULL, meaning "this source does not
publish an adjusted close".

Until now the column was `NOT NULL` and `validate_daily_bars` enforced
the invariant by rejecting any bar the source had not adjusted. That was
right for the reason ADR-016 gives: the vendor publishes the adjustment
one session late, so a rejected bar is re-offered complete on the next
sync, and the alternative was to freeze a fabricated value forever.

B3's open COTAHIST series (PRICE-001) breaks that premise. It prints the
prices actually traded and carries no adjusted series at all — not late,
never. Under the old invariant every one of its bars would be rejected,
which would discard decades of open history to protect against a
publication lag that this source does not have.

So the column now records what the source knew. `close` is the traded
close; `adjusted_close` is the total-return close, and NULL says the
source did not compute one. Nothing is fabricated, and nothing that
exists is thrown away.

The reason this does not push a null check onto every consumer — the
objection ADR-016 raised against exactly this change — is that no
consumer reads the column directly any more. Every return series is
built through `app.domain.market_data.series`, which keeps only the
adjusted rows. See ADR-023.

Existing rows all came from the vendor and all have a value, so the
change is widening only: no backfill, and no row loses anything.

Revision ID: 010_nullable_adj_close
Revises: 009_drop_dup_uniques
Create Date: 2026-08-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010_nullable_adj_close"
down_revision: Union[str, None] = "009_drop_dup_uniques"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MONEY = sa.Numeric(18, 6)


def upgrade() -> None:
    op.alter_column(
        "asset_prices",
        "adjusted_close",
        existing_type=MONEY,
        nullable=True,
    )


def downgrade() -> None:
    # Rows stored from an unadjusted source have no adjusted close and
    # none can be derived, so they are removed rather than filled with a
    # fabricated one (AGENTS.md rule 44). Re-running the sync against an
    # adjusting provider restores whatever that provider covers.
    op.execute(sa.text("DELETE FROM asset_prices WHERE adjusted_close IS NULL"))
    op.alter_column(
        "asset_prices",
        "adjusted_close",
        existing_type=MONEY,
        nullable=False,
    )
