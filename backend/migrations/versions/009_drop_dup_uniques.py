"""009_drop_dup_uniques

Drop the redundant unique constraints on `assets.ticker` and
`users.email`.

Both columns are declared `unique=True, index=True` on the model, which
SQLAlchemy renders as a single **unique index** (`ix_assets_ticker`,
`ix_users_email`). Migration 001 created that index *and* a separate
`UniqueConstraint`, so the database ended up enforcing the same rule
twice, through two objects, one of which the models never declared.

Harmless at runtime — two identical guarantees — but it cost the project
a tool: `alembic check` compares the models against the live schema and
saw two constraints nobody had asked for, so every run reported drift:

    Detected removed unique constraint 'assets_ticker_key' on 'assets'
    Detected removed unique constraint 'users_email_key' on 'users'

A drift check that always fails is a drift check nobody can wire into
CI, which is exactly where it earns its keep. Removing the duplicate
makes `alembic check` pass and turns it back into a usable guard.

Uniqueness is not weakened: in PostgreSQL a unique index enforces the
constraint by itself — a `UNIQUE` constraint is in fact implemented as
one. The remaining `ix_*` indexes keep both the guarantee and the lookup
performance.

The names are the defaults PostgreSQL assigns (`<table>_<column>_key`)
because migration 001 declared the constraints unnamed.

Revision ID: 009_drop_dup_uniques
Revises: 008_numeric_contribution
Create Date: 2026-08-19 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_drop_dup_uniques"
down_revision: Union[str, None] = "008_numeric_contribution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("assets_ticker_key", "assets", type_="unique")
    op.drop_constraint("users_email_key", "users", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("users_email_key", "users", ["email"])
    op.create_unique_constraint("assets_ticker_key", "assets", ["ticker"])
