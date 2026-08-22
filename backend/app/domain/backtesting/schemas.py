"""API shapes for a backtest.

Nothing is computed here — the figures come from `service.run_backtest`,
which reads a `Simulation` the pure engine produced. What this file does
is decide what a caller is *told*, and the answer is: everything needed
to read the result and everything needed to repeat it.

A backtest that reports only a return is not a result, it is a claim.
Rule 107 asks for costs, rule 63 for more than a win rate, rule 113 for
reproducibility — so the settings, the window, the exclusions and the
unfilled orders travel with the numbers rather than beside them.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.domain.benchmarks.schemas import BenchmarkComparisonResponse
from app.domain.recommendations.schemas import AllocationPolicyResponse


class CostModelResponse(BaseModel):
    """What a trade was charged, beyond the price of the shares.

    Echoed back because it is an assumption and not a fact about the
    reader's broker: a return is only interpretable next to the costs
    that produced it (rule 107).
    """

    brokerage: Decimal
    brokerage_rate: Decimal
    exchange_rate: Decimal


class BacktestSettingsResponse(BaseModel):
    """Everything the run was parameterised by (rule 113).

    `publication_lag_months` is the one that is easy to miss and hardest
    to notice the absence of: a fiscal year ending 31 December is not
    public on 1 January, so a run that reads it then is trading on a
    document that did not exist. Three months is the CVM's own filing
    deadline for the DFP — the latest legal date rather than a guess at a
    typical one.
    """

    start: date
    end: date
    strategy: str
    contribution: Decimal
    day_of_month: int
    publication_lag_months: int
    costs: CostModelResponse
    policy: AllocationPolicyResponse


class BacktestWindowResponse(BaseModel):
    """The period asked for, the period run, and what shortened it.

    They differ whenever an asset's total-return series starts later than
    the requested start. `bounded_by` names that asset, because "why does
    my ten-year backtest cover four years?" has to be answerable from the
    result.
    """

    requested_start: date
    requested_end: date
    start: date
    end: date
    bounded_by: str | None


class ExcludedAssetResponse(BaseModel):
    """One asset the run could not replay, and why.

    `NO_PRICES` — nothing stored, so it could only ever have produced
    unfilled orders. `NO_TOTAL_RETURN_SERIES` — prices but no complete
    adjustment, so its return cannot be measured at all (ADR-026).

    Reported rather than silently dropped: the universe a backtest ran on
    is part of what it measured, and rule 59 is about not reconstructing
    the past from a set nobody can see.
    """

    ticker: str
    reason: str


class WealthPointResponse(BaseModel):
    """One date on the money curve.

    ⚠️ **`total` is not performance.** A curve that doubled because
    R$ 1.000 arrived every month looks identical to one that doubled on
    returns until `contributed` is read under it (ADR-019). The
    time-weighted answer is `comparison`, which neutralises exactly this.

    `holdings` is priced at the raw close — what the market printed — and
    `cash` is what the strategy did not spend. They are separate because
    a strategy holding a third of its money in cash is a fact about the
    strategy, not a rounding detail.
    """

    date: date
    holdings: Decimal
    cash: Decimal
    total: Decimal
    contributed: Decimal


class IndexPointResponse(BaseModel):
    """One date on the time-weighted index, based at 100."""

    date: date
    value: Decimal


class TradeStatisticsResponse(BaseModel):
    """The execution side of the run (rules 63, 64 and 107).

    ⚠️ **`win_rate`, `average_win`, `average_loss`, `profit_factor` and
    `expectancy` are `null` on every strategy this project ships**, and
    that is the honest answer rather than a gap. All five are defined on
    *closed* trades, and nothing here sells: an overweight position is
    closed by dilution over later contributions (ADR-028). `closed_trades`
    at zero is what says so — reporting `0%` would read as *every trade
    lost*.

    **`slippage` is measured, not assumed.** The engine decides against
    one session's close and fills against the next one's, so the gap
    between those two prices is what the delay cost, in this run, on
    these days. Positive means it cost money. The two directions are
    reported separately because a run that paid R$ 40 on some fills and
    gained R$ 38 on others is not a run that barely moved.

    `unfilled` counts the orders that ended as nothing, by the reason
    that stopped them — `NO_PRICE`, `BELOW_ONE_SHARE`,
    `INSUFFICIENT_CASH`, `NOTHING_HELD`. A backtest that silently drops
    an order reports a strategy nobody ran.
    """

    trades: int
    buys: int
    sells: int
    closed_trades: int
    wins: int
    losses: int
    win_rate: Decimal | None
    average_win: Decimal | None
    average_loss: Decimal | None
    profit_factor: Decimal | None
    expectancy: Decimal | None
    realized_result: Decimal
    fees: Decimal
    slippage: Decimal
    slippage_paid: Decimal
    slippage_earned: Decimal
    dividends_received: Decimal
    contributed: Decimal
    unfilled: dict[str, int]


class BacktestResponse(BaseModel):
    """One replay, with everything needed to read it and to repeat it.

    Two answers to two different questions, and neither substitutes for
    the other:

    - `comparison` is the **time-weighted** index against a benchmark.
      Contributions are neutralised, so this is the figure that answers
      "did the strategy beat the CDI".
    - `wealth` is the **money**: what went in, what it became, and the
      cash between them.

    `alpha` is the return left after the market exposure is paid for —
    not the same as `comparison.excess_return`, which is a plain
    difference. A positive excess with a negative alpha means the
    strategy rose because the market did, and by less than its own beta
    entitled it to.

    ⚠️ **`comparison` describes a shorter period than `index` whenever
    the benchmark has less history**, because the two series are cut to
    the window they share before anything is measured (rule 28).
    Measured against the real database, a six-year run compared with the
    CDI reports four months in `comparison.subject`, since that is all
    the CDI that has been ingested. `subject.start_date` and
    `subject.end_date` are what say so, and they are required reading
    before a figure here is quoted next to the curve.

    ⚠️ The index assumes each payout was reinvested on the day it went
    ex, because that is what an adjusted close means; the simulation
    reinvests at the next contribution and holds cash until then. The
    drag is visible in `wealth` and not in `comparison`.
    """

    settings: BacktestSettingsResponse
    window: BacktestWindowResponse
    universe: list[str]
    excluded: list[ExcludedAssetResponse]
    comparison: BenchmarkComparisonResponse | None
    alpha: Decimal | None
    index: list[IndexPointResponse]
    wealth: list[WealthPointResponse]
    trades: TradeStatisticsResponse
    sources: list[str]


# -- walk-forward validation (W14-004) --------------------------------


class WalkForwardSchemeResponse(BaseModel):
    """How the history was cut, and how far the cut travelled.

    The three segments are the same length by construction, so one figure
    describes all of them: a shorter test segment would measure a younger
    portfolio, and the degradation below would be part strategy and part
    portfolio age with no way to tell which (`folds`).
    """

    segment_months: int
    step_months: int


class WalkForwardSettingsResponse(BaseModel):
    """Everything the walk-forward was parameterised by (rule 113).

    `policy` is the **base** the grid varies from, not the policy that
    was run: it is the grid's first candidate, and every other candidate
    differs from it in exactly one field.
    """

    start: date
    end: date
    strategy: str
    contribution: Decimal
    day_of_month: int
    publication_lag_months: int
    costs: CostModelResponse
    policy: AllocationPolicyResponse
    scheme: WalkForwardSchemeResponse
    objective: str
    shortlist: int


class SegmentResponse(BaseModel):
    """One period a candidate was measured over, both ends inclusive."""

    start: date
    end: date


class SegmentMetricsResponse(BaseModel):
    """What one segment's time-weighted index says (rule 63).

    Every figure may be `null`, and `null` means *not computable on this
    series* — never zero. `cagr` is absent on a segment shorter than
    `MIN_ANNUALISATION_DAYS`, and `sharpe`/`sortino` are absent whenever
    no CDI has been ingested for the segment, since this project takes
    exactly one risk-free rate and does not assume it to be zero.
    """

    observations: int
    total_return: Decimal | None
    cagr: Decimal | None
    volatility: Decimal | None
    max_drawdown: Decimal | None
    sharpe: Decimal | None
    sortino: Decimal | None


class SegmentOutcomeResponse(BaseModel):
    """One policy over one segment: the series, and what it cost.

    `objective` is the single figure the fold ranked on, lifted out of
    `metrics` so it is readable without knowing which objective was
    asked for. `null` there means the candidate was **not ranked** — not
    ranked last.
    """

    metrics: SegmentMetricsResponse
    objective: Decimal | None
    trades: int
    fees: Decimal
    slippage: Decimal
    contributed: Decimal
    final_value: Decimal | None


class PolicyCandidateResponse(BaseModel):
    """One policy the walk-forward could select, and the question it asks.

    `question` is part of the result rather than documentation of it. A
    candidate that cannot be stated as a question somebody would ask
    before seeing any number is a swept parameter, and rule 60 exists to
    keep those out.
    """

    name: str
    question: str
    policy: AllocationPolicyResponse


class CandidateRunResponse(BaseModel):
    """One candidate's result over one segment.

    The policy is not repeated here — `candidates` at the top of the
    response carries each one once, and `name` is what joins them.
    """

    name: str
    outcome: SegmentOutcomeResponse


class FoldResponse(BaseModel):
    """One `Train → Validate → Test`, and what survived it.

    ⚠️ **`degradation` is the figure to read**, not `out_of_sample` on
    its own: it is what the winner scored on validation less what it
    scored on test, so a positive value means the choice did worse on
    history it had not seen. That is what overfitting looks like from the
    outside.

    `refusal` at `OBJECTIVE_UNAVAILABLE` means no candidate could be
    scored — on the default objective, that no CDI covers the segment.
    The runs still happened and are still listed: a fold that could not
    choose is not a fold that did not run.
    """

    index: int
    train: SegmentResponse
    validation: SegmentResponse
    test: SegmentResponse
    trained: list[CandidateRunResponse]
    shortlist: list[str]
    validated: list[CandidateRunResponse]
    selected: str | None
    tested: SegmentOutcomeResponse | None
    in_sample: Decimal | None
    out_of_sample: Decimal | None
    degradation: Decimal | None
    refusal: str | None


class WalkForwardPartitionResponse(BaseModel):
    """How many folds the replayable window held, or why it held none.

    `required_months` and `available_months` travel with the refusal
    because *"why did my walk-forward return nothing?"* has to be
    answerable from the result — the same reason `window.bounded_by`
    exists.
    """

    folds: int
    required_months: int
    available_months: int
    refusal: str | None


class WalkForwardStabilityResponse(BaseModel):
    """What the folds agree on, or the named reason they cannot say.

    ⚠️ **Every aggregate is `null` with a single fold**, and `refusal` is
    `SINGLE_FOLD`. A mean of one observation and a spread of zero would
    read as *perfectly stable*, which is the opposite of what one
    observation supports. The fold's own out-of-sample figure is still
    reported — only the aggregate is withheld.

    `selection_rate` is the fraction of measured folds the most selected
    candidate won. A walk-forward that picks a different winner every
    time has found noise, not a parameter (rule 60).
    """

    folds: int
    measured_folds: int
    selections: dict[str, int]
    most_selected: str | None
    selection_rate: Decimal | None
    out_of_sample_mean: Decimal | None
    out_of_sample_min: Decimal | None
    out_of_sample_max: Decimal | None
    out_of_sample_stdev: Decimal | None
    degradation_mean: Decimal | None
    positive_folds: int | None
    refusal: str | None


class WalkForwardResponse(BaseModel):
    """One walk-forward: what was tried, what was chosen, what held up.

    Rules 61 and 62, as a response. The history is cut into
    `Train → Validate → Test`, the cut moves, and the strategy is judged
    on stability across repetitions rather than on one better number.

    ⚠️ **The figure that answers the wave's question is
    `stability.degradation_mean`**, not the returns. A strategy whose
    out-of-sample results track its in-sample ones has parameters that
    describe something; one whose results collapse has parameters that
    described the sample they were chosen on.

    ⚠️ **Every segment run starts from an empty portfolio.** That is what
    makes candidates comparable to each other and in-sample comparable to
    out-of-sample, and it means a segment measures the strategy
    *accumulating* rather than running on a mature portfolio.

    `window` is the replayable span, which may be far shorter than the one
    requested — a total-return series exists only where the price
    adjustment is complete (ADR-032), and `bounded_by` names the asset
    that decided it. `partition.refusal` at `WINDOW_TOO_SHORT` means that
    span could not hold three segments; the answer is to ingest the
    missing corporate actions, never to shorten the segments until they
    fit.
    """

    settings: WalkForwardSettingsResponse
    grid_version: str
    window: BacktestWindowResponse
    universe: list[str]
    excluded: list[ExcludedAssetResponse]
    candidates: list[PolicyCandidateResponse]
    partition: WalkForwardPartitionResponse
    folds: list[FoldResponse]
    stability: WalkForwardStabilityResponse
