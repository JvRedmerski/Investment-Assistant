"""What the positions are worth now (roadmap §23, AGENTS.md rule 73).

Pure, deterministic and I/O-free. Loading lives in the route, as it does
for `compute_positions` — this module only combines a position with a
price.

Rule 73 puts the reason for this module's existence plainly: the frontend
presents, it does not compute. `quantity × price` is a financial
calculation and belongs on this side of the wire, once, rather than in
every screen that wants to show a total.

## `close`, never `adjusted_close`

`market_data/series.py` draws the line and this module stays on the
correct side of it: `close` is what the market printed and is the right
input for any *point-in-time* question, while `adjusted_close` is the
total-return price and is valid only for a return series.

Valuing a position with an adjusted close would report a number nobody
could have received. Adjustment is retroactive — a stock that has paid
six years of dividends has its old closes scaled *down*, so a position
held since 2020 valued at its adjusted price is worth a fraction of what
the shares would actually fetch.

## Absence is per line, and the total says what it covers

Two decisions already made in this codebase point in opposite
directions here, and both are right where they are:

- `performance_index._value_on` returns `None` for the **whole day** when
  one held asset lacks a price, because a time-weighted series whose
  constituents change between two dates is not a shorter series, it is a
  different portfolio.
- `recommendations/service.py` deliberately measures concentration on
  cost basis so that one missing price cannot make the pillar absent for
  the entire portfolio.

A positions table is a third case. Each row is read on its own, so a row
with no price is simply absent — `market_value` is `None`, never a
stand-in zero (ADR-014) and never the cost basis wearing a different
label.

What that costs is a total covering only part of the portfolio, and the
field name is what stops it being misread: `valued_market_value`, not
`total_market_value`. `unvalued_positions` and `unvalued_invested`
report the size of what it leaves out, so the gap is quantified rather
than merely absent.

A position of zero quantity is worth zero whatever the price, so it is
valued trivially and never counts as unvalued. Nothing held is not
something unknown.

## Staleness is a label (rules 103/104)

Every row carries the date of the price it used, and the totals carry
the oldest and the newest of them. A patrimônio that mixes today's close
with one from three months ago is not wrong, but it is not what it looks
like either, and `oldest_price_date` is what says so.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.portfolio.service import AssetPosition

ZERO = Decimal(0)


@dataclass(frozen=True)
class ClosingPrice:
    """One stored close, with the session it belongs to.

    Deliberately not the full bar, for the reason `PricePoint` is not
    either: valuation needs one price per asset, and narrowing the input
    keeps the function usable from anywhere that can produce a close.
    """

    date: date
    close: Decimal


@dataclass(frozen=True)
class ValuedPosition:
    """One position with a market value, or with a named absence.

    `market_value` and `unrealised_pnl` are `None` together: there is no
    partial answer here, because both derive from the same missing price.
    """

    asset_id: int
    quantity: Decimal
    invested_amount: Decimal
    last_price: Decimal | None
    price_date: date | None
    market_value: Decimal | None
    unrealised_pnl: Decimal | None

    @property
    def is_valued(self) -> bool:
        return self.market_value is not None


@dataclass(frozen=True)
class PortfolioValuation:
    """The valued positions and what the totals actually cover.

    `valued_market_value` is the sum over the rows that had a price, and
    `valued_invested` is the cost basis of **those same rows** — the two
    are the like-for-like pair `unrealised_pnl` is the difference of.
    Comparing the valued total against the whole portfolio's cost basis
    would report a loss made entirely of the positions nobody could
    price.
    """

    positions: tuple[ValuedPosition, ...]
    valued_market_value: Decimal
    valued_invested: Decimal
    unrealised_pnl: Decimal
    unvalued_positions: int
    unvalued_invested: Decimal
    oldest_price_date: date | None
    newest_price_date: date | None

    @property
    def is_complete(self) -> bool:
        """Whether the totals cover the whole portfolio."""
        return self.unvalued_positions == 0


def value_positions(
    positions: dict[int, AssetPosition],
    quotes: dict[int, ClosingPrice],
) -> PortfolioValuation:
    """Attach a market value to each position, or name what is missing.

    `positions` comes from `compute_positions` and `quotes` from whatever
    loaded the most recent close for each asset. Both are passed in so
    this stays pure (rule 68), and the result is ordered by `asset_id`
    so it does not depend on dictionary ordering (rule 113).
    """
    valued: list[ValuedPosition] = []
    for asset_id, position in sorted(positions.items()):
        valued.append(_value(asset_id, position, quotes.get(asset_id)))

    # Only positions that actually carry value widen the staleness
    # window. A closed position may well have a quote attached, and it
    # contributes nothing to the total, so letting its date drag
    # `oldest_price_date` back would report the totals as older than the
    # money in them.
    dates = [
        item.price_date
        for item in valued
        if item.quantity > 0 and item.price_date is not None
    ]
    unvalued = [item for item in valued if not item.is_valued]

    return PortfolioValuation(
        positions=tuple(valued),
        # `or ZERO` rather than a default of zero on the field: these are
        # sums over a possibly empty list, and an empty portfolio is
        # worth nothing rather than being unknown.
        valued_market_value=sum(
            (item.market_value or ZERO for item in valued if item.is_valued), ZERO
        ),
        valued_invested=sum(
            (item.invested_amount for item in valued if item.is_valued), ZERO
        ),
        unrealised_pnl=sum(
            (item.unrealised_pnl or ZERO for item in valued if item.is_valued), ZERO
        ),
        unvalued_positions=len(unvalued),
        unvalued_invested=sum((item.invested_amount for item in unvalued), ZERO),
        oldest_price_date=min(dates) if dates else None,
        newest_price_date=max(dates) if dates else None,
    )


def _value(
    asset_id: int, position: AssetPosition, quote: ClosingPrice | None
) -> ValuedPosition:
    """One position against one price, or against none.

    A closed position takes the first branch: it is worth zero because
    nothing is held, which is a measurement and not a gap, so it counts
    as valued even where no price exists. It still shows the last price
    when there is one — a sold-out holding's quote is real information —
    and `value_positions` keeps that date out of the staleness window,
    because no part of the total depends on it.
    """
    if position.quantity <= 0:
        return ValuedPosition(
            asset_id=asset_id,
            quantity=position.quantity,
            invested_amount=position.invested_amount,
            last_price=quote.close if quote else None,
            price_date=quote.date if quote else None,
            market_value=ZERO,
            unrealised_pnl=ZERO,
        )
    if quote is None:
        return ValuedPosition(
            asset_id=asset_id,
            quantity=position.quantity,
            invested_amount=position.invested_amount,
            last_price=None,
            price_date=None,
            market_value=None,
            unrealised_pnl=None,
        )

    market_value = position.quantity * quote.close
    return ValuedPosition(
        asset_id=asset_id,
        quantity=position.quantity,
        invested_amount=position.invested_amount,
        last_price=quote.close,
        price_date=quote.date,
        market_value=market_value,
        unrealised_pnl=market_value - position.invested_amount,
    )
