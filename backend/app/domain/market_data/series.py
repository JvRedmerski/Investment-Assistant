"""Turning stored bars into the series the quant engine can consume.

`asset_prices` holds two different prices, and mixing them up is a silent
error rather than a loud one:

- **`close`** is what the market printed. It is the right input for any
  point-in-time question — the P/E of a fiscal year end is that year's
  reported earnings against the price actually quoted then.
- **`adjusted_close`** is the total-return price: dividends reinvested,
  splits undone. It is the only valid input for a *return* series, and
  `app.quant` reads nothing else (`PricePoint.adjusted_close`).

Since PRICE-001 the column can be NULL, because B3's open COTAHIST
archive publishes traded prices and computes no adjustment (ADR-023).
This module is the single place that turns rows into `PricePoint`s, so
"a row without an adjusted close cannot enter a return series" is
enforced once instead of at every call site — which is what makes the
nullable column safe, and what ADR-016 was right to worry about when it
rejected the same change under different circumstances.

**Unadjusted rows are dropped, not defaulted.** A shorter series is a
visible, honest gap: the quant functions already answer `None` when they
have too few points, so an asset with only unadjusted history reports its
risk metrics as absent — the state the scoring engine was built to treat
as normal (W09-001). The alternative, feeding raw closes in as though
they were adjusted, would report a number that is not what it claims:
Magazine Luiza's 1:10 reverse split shows up in the raw series as a
+896% session, which volatility, drawdown and beta would all read as a
market event.

The real fix is upstream — ingesting corporate actions so the adjusted
series can be built (docs/memory/PROJECT_STATUS.md, Known Issue 1) — not
a default here.
"""

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from app.data.models.assets import AssetPrice
from app.quant.returns import PricePoint


def adjusted_price_points(rows: Iterable[AssetPrice]) -> list[PricePoint]:
    """Stored bars as a return series, in date order.

    Rows whose source published no adjusted close are left out; see the
    module docstring.
    """
    points = [
        PricePoint(date=row.date, adjusted_close=row.adjusted_close)
        for row in rows
        if row.adjusted_close is not None
    ]
    points.sort(key=lambda point: point.date)
    return points


def adjusted_closes_by_asset(
    rows: Iterable[AssetPrice],
) -> dict[int, dict[date, Decimal]]:
    """Adjusted closes keyed by asset and date, for valuing many assets.

    Same rule as `adjusted_price_points`: an unadjusted row is simply not
    there, so a date that cannot be valued stays unvalued rather than
    being valued wrongly.
    """
    closes: dict[int, dict[date, Decimal]] = {}
    for row in rows:
        if row.adjusted_close is None:
            continue
        closes.setdefault(row.asset_id, {})[row.date] = row.adjusted_close
    return closes


def closes_by_asset(
    rows: Iterable[AssetPrice],
) -> dict[int, dict[date, Decimal]]:
    """Raw closes keyed by asset and date, for valuing a portfolio.

    The counterpart of `adjusted_closes_by_asset`, and the two are not
    interchangeable — which is the whole reason this module exists. A
    wealth curve asks *what was this worth*, a point-in-time question, so
    it takes the price the market printed. A return series asks *what did
    this earn*, so it takes the adjusted one.

    No row is dropped here, because `close` is never null: the archive
    that publishes no adjustment still publishes a traded price. An asset
    simply missing from the store is missing from the result, and the
    caller reports the date as unvaluable rather than valuing it wrongly.
    """
    closes: dict[int, dict[date, Decimal]] = {}
    for row in rows:
        closes.setdefault(row.asset_id, {})[row.date] = row.close
    return closes
