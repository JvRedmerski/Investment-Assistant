"""007_shares_outstanding

Add `fundamentals.shares_outstanding`, the last input P/L and P/VP were
waiting for.

Both formulas have been written and tested since W06-002 and have
returned `None` ever since, because the only share count available was
the vendor's **present-day snapshot**, with no period end attached.
Dividing a 2020 balance sheet by today's share count attributes a
present fact to a past period — the look-ahead rules 108/109 forbid — so
the honest answer was an absent Valuation pillar (ADR-014).

The CVM's own `composicao_capital` file, already inside the DFP archive
this project downloads, carries the count **per fiscal year**:
`QT_ACAO_TOTAL_CAP_INTEGR` less `QT_ACAO_TOTAL_TESOURO`. Shares held in
treasury are excluded because they receive no dividend and carry no
claim on earnings; including them would understate earnings per share.

NUMERIC(20, 0) rather than a money type: a share count is an exact whole
number, never a fraction, in every filing from 2020 to 2025. Nullable,
and NULL means the filing reported no count that could be reconciled —
see `app.integrations.fundamentals.cvm`, where the unit the count is
written in is checked against the filing's own earnings per share before
anything is stored.

Revision ID: 007_shares_outstanding
Revises: 006_assets_cnpj
Create Date: 2026-08-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_shares_outstanding"
down_revision: Union[str, None] = "006_assets_cnpj"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "fundamentals",
        sa.Column("shares_outstanding", sa.Numeric(20, 0), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fundamentals", "shares_outstanding")
