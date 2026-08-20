"""012_corporate_actions

Add `corporate_actions`: the **magnitude** of a corporate event, which is
the one thing standing between the project and a total-return series.

B3's end-of-day archive dates every event and never sizes it — it records
that a distribution happened and never how large (ADR-025). Without the
size there is no adjusted close, and without that `volatility`,
`max_drawdown`, `beta` and `sharpe` all stay `None`, which is the whole
Risk pillar and the reason the score's coverage sat at 0.75.

The size comes from B3's own listed-company events service: reais per
share for a payout, a factor for a split, open and without a token
(ADR-026). Its dates agree with the archive's independent distribution
counter on **157 of 157** in-window payouts across PETR3, PETR4, VALE3,
ITUB4 and BBAS3, and its factors reproduce **49 of 50** measured price
steps once joined on the ISIN.

Stored rather than re-fetched, unlike the events themselves: this is a
paginated remote service, not a file already cached on disk, and pulling
a decade of payouts on every read is what rule 23 exists to prevent.

Two nullable magnitude columns rather than one. `cash_amount` is reais
per share and `share_ratio` is shares-after-per-share-before; collapsing
them into a single column whose unit depended on `kind` is the same
conflation that made `close` and `adjusted_close` worth keeping apart.
Exactly one is set per row, enforced in the Pydantic schema before
anything reaches storage.

No unique constraint, deliberately. The identity of an action is the
tuple of everything reported about it, two of whose columns are nullable
— and a constraint over nullable columns does not fire in PostgreSQL,
so it would advertise a guarantee it cannot keep. Duplicate suppression
lives in the sync service, which is where `asset_prices` already keeps
it too.

Revision ID: 012_corporate_actions
Revises: 011_dividends_paid
Create Date: 2026-08-20 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012_corporate_actions"
down_revision: Union[str, None] = "011_dividends_paid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Same precision as every other money column (migration 002).
MONEY = sa.Numeric(18, 6)

#: A ratio is not money. B3 files a 1/3 bonus to eleven decimal places
#: (`33,33333333300`), and rounding that to six would leave a residue in
#: every adjusted price before the event.
RATIO = sa.Numeric(24, 12)


def upgrade() -> None:
    op.create_table(
        "corporate_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("last_date_prior", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("cash_amount", MONEY, nullable=True),
        sa.Column("share_ratio", RATIO, nullable=True),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_corporate_actions_id"), "corporate_actions", ["id"], unique=False
    )
    # Every read is "the actions for this asset, in date order", because
    # back-adjustment walks the series backwards applying them.
    op.create_index(
        "idx_corporate_action_ex_date",
        "corporate_actions",
        ["asset_id", "ex_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_corporate_action_ex_date", table_name="corporate_actions")
    op.drop_index(op.f("ix_corporate_actions_id"), table_name="corporate_actions")
    op.drop_table("corporate_actions")
