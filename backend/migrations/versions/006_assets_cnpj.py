"""006_assets_cnpj

Add `assets.cnpj`, the join between the project's two fundamentals
sources.

The CVM's open data files — now the primary source for financial
statements — identify a company **only** by CNPJ and carry no ticker
column at all. The market data vendor is the opposite: it knows tickers,
and exposes the CNPJ on the one profile module still available on the
free plan. Neither can answer "what did PETR4 report" alone.

Stored rather than resolved on demand for two reasons: resolving costs a
request against a quota-limited plan and a company's CNPJ does not
change, and having it on the row makes the mapping auditable and
overridable when a vendor gets it wrong.

Nullable, and NULL carries meaning: either not resolved yet, or no filer
exists. A BDR represents a foreign company and an ETF is not a
`companhia aberta`; neither files a DFP, and neither ever will.

Not unique: a company with more than one class of share on the exchange
(ordinary and preferred, say) is one CNPJ against several tickers, which
is exactly right — they are claims on the same filing.

Revision ID: 006_assets_cnpj
Revises: 005_benchmark_values
Create Date: 2026-08-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_assets_cnpj"
down_revision: Union[str, None] = "005_benchmark_values"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("cnpj", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("assets", "cnpj")
