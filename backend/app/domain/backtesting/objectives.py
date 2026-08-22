"""What one segment of a walk-forward is worth, and which figure decides.

Pure and I/O-free (rule 68): a price series and a rate go in, measurements
come out. Every figure is `quant`'s — nothing is re-derived here, for the
same reason `backtesting.metrics` leaves the series figures alone. A
second implementation of volatility is a second volatility.

## Measuring more than the figure that selects

Rule 63 is explicit that a backtest is not a win rate, and the same
applies to a fold: reporting only the objective would make the selection
unauditable, because *why* one candidate beat another — more return, or
less dispersion — is the whole content of the comparison. So every
segment carries the full set the series can answer, and the objective is
one named member of it.

## Choosing by risk-adjusted return, and what happens when it is missing

`SHARPE` is the default because rule 32 states the conservative profile
as quantitative restriction rather than as adjective, and because the
alternative — ranking by raw return — is what rule 60 warns about even
with validation stacked behind it.

Sharpe needs a risk-free rate, and this project takes exactly one: the
CDI, `None` until it has been ingested for the window
(`benchmarks.service.risk_free_rate_for`). When the rate is missing the
objective is missing, and a candidate with no objective value is **not
selectable** — reported as `OBJECTIVE_UNAVAILABLE` rather than quietly
falling back to a second figure. A silent fallback would make two runs
of the same command incomparable depending on what happened to be in the
database, which is the failure mode `ADR-014` and the coverage rules of
`scoring` keep guarding against.

`TOTAL_RETURN` is offered for exactly that case, and asking for it is a
choice the result then carries.

## ⚠️ The objective measures the money that was **deployed**, not the money
## that was given

Every figure here comes from the time-weighted index, which values
positions and not cash — the same index the live dashboard reports, and
deliberately the same (ADR-019). So a policy that invested a tenth of the
contributions and doubled that tenth outranks one that invested most of
them and gained a third.

Measured on the real database (W14-005): a 2023 segment over PETR4 and
BBAS3 with `min_score=30` ended holding **R$ 3.239,88 against
R$ 9.892,81 in cash** on R$ 12.000 contributed. The index reported
**+101,38%**; the money grew **9,44%**. Neither number is wrong and they
answer different questions.

The cash was not idleness, it was the ceiling working: with two assets and
`max_asset_weight` at 20%, no more than 40% of the portfolio can ever be
invested. `SegmentOutcome` carries `contributed` and `final_value` side by
side so the money reading is one subtraction away — reading only the
objective is the ADR-019 mistake with the operands swapped. An objective
that prices deployment is Future Work; inventing a second definition of
return here would be worse than naming the gap.

## Why CAGR is measured and never selected on

Within one fold all three segments are the same length by construction
(`folds`), so annualising cannot change any ordering — CAGR and total
return rank identically. It is reported because a reader comparing folds
of different schemes needs a rate, and it is not an objective because it
would be the same objective under another name.
"""

import enum
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.quant.returns import Periodicity, PricePoint, cagr, total_return
from app.quant.risk import max_drawdown, sharpe, sortino, volatility

#: No candidate could be scored on the objective asked for.
OBJECTIVE_UNAVAILABLE = "OBJECTIVE_UNAVAILABLE"


class SelectionObjective(str, enum.Enum):
    """The single figure a fold ranks its candidates by.

    A closed set of two, and both are *maximised*. Deliberately not a
    caller-supplied expression: a walk-forward whose objective can be
    anything is a walk-forward whose objective can be chosen after seeing
    the results, and that is the search it exists to prevent.
    """

    SHARPE = "sharpe"
    TOTAL_RETURN = "total-return"


@dataclass(frozen=True)
class SegmentMetrics:
    """What one segment's time-weighted index says (rule 63).

    Every figure may be `None`, and `None` means *not computable on this
    series* — too few observations, no dispersion, no risk-free rate —
    never zero. `observations` is what lets a reader tell a segment that
    measured nothing from one that measured a flat result.
    """

    observations: int
    total_return: Decimal | None
    cagr: Decimal | None
    volatility: Decimal | None
    max_drawdown: Decimal | None
    sharpe: Decimal | None
    sortino: Decimal | None


def measure_segment(
    index: list[PricePoint],
    risk_free_rate: Decimal | None = None,
    as_of: date | None = None,
) -> SegmentMetrics:
    """Measure a segment's own index with the project's quant engine.

    `index` is the backtest's time-weighted performance index — the same
    series `portfolio.performance` builds for the investor's real
    portfolio, so a fold is measured with the code that measures the
    dashboard (rule 26 is why it is time-weighted at all).
    """
    period = total_return(index, as_of)
    drawdown = max_drawdown(index, as_of)
    return SegmentMetrics(
        observations=len(index),
        total_return=period.value if period is not None else None,
        cagr=cagr(index, as_of),
        volatility=volatility(index, Periodicity.DAILY, as_of),
        max_drawdown=drawdown.value if drawdown is not None else None,
        sharpe=sharpe(index, risk_free_rate, Periodicity.DAILY, as_of),
        sortino=sortino(index, risk_free_rate, Periodicity.DAILY, as_of),
    )


def objective_value(
    metrics: SegmentMetrics, objective: SelectionObjective
) -> Decimal | None:
    """The one figure `objective` names, or `None` when it is missing.

    `None` is not a bad score. A candidate that cannot be scored is not
    ranked last, it is **not ranked** — see `walkforward.select`.
    """
    if objective is SelectionObjective.SHARPE:
        return metrics.sharpe
    return metrics.total_return
