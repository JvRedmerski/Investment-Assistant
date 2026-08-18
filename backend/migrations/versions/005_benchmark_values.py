"""005_benchmark_values

Create `benchmark_values`, the store for benchmark series (CDI, IBOV,
IPCA, Selic) ingested in Wave 08.

Two shape decisions are worth stating here, because both are the kind
that is expensive to reverse once rows exist:

1. **No `benchmarks` table.** The catalog of benchmarks — code, name,
   kind, periodicity, source, source series id — lives in code, at
   `app/domain/benchmarks/catalog.py`. A benchmark's definition is not
   user data; it is a reviewed fact about an external source, and
   version control is a better home for it than a seed migration two
   environments can drift apart on. `benchmark_code` is therefore a
   plain string, not a foreign key.

2. **NUMERIC(24, 12), wider than the NUMERIC(18, 6) used for money.**
   The column holds both an index level (166,978.9375 points) and a
   daily rate as a fraction (0.00043739). Six decimals would truncate
   the rate's last two significant digits, and that error compounds 252
   times a year into the accumulated index that every
   portfolio-versus-CDI comparison rests on.

No accumulated index column: accumulation depends on the base date the
caller asks about, so it is derived on read rather than frozen at write
(ADR-018).

Revision ID: 005_benchmark_values
Revises: 004_fundamentals_income_detail
Create Date: 2026-08-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_benchmark_values"
down_revision: Union[str, None] = "004_fundamentals_income_detail"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "benchmark_values",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("benchmark_code", sa.String(length=20), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(precision=24, scale=12), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("benchmark_code", "date", name="uq_benchmark_value_date"),
    )
    op.create_index(
        op.f("ix_benchmark_values_id"), "benchmark_values", ["id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_benchmark_values_id"), table_name="benchmark_values")
    op.drop_table("benchmark_values")
