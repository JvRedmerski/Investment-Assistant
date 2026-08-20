"""Rebuilding a total-return series from raw closes and sized actions.

B3's archive prints what was traded and computes no adjustment, so
`adjusted_close` arrives `NULL` from it and every risk metric downstream
stays absent (ADR-023). This module is what fills that column — and the
only thing that ever may, because it is the one place where "the
adjustment is complete" is decided rather than assumed.

## The arithmetic

Back-adjustment, walking the series from newest to oldest. The most
recent close is the truth and is never touched; every earlier close is
multiplied by the product of the factors of every action that has gone ex
since. So the series ends where the market ended and the past is
restated, rather than the other way round.

One action contributes one factor:

- **A share action** contributes `1 / share_ratio`. BBAS3's 1:2 split has
  `share_ratio` 2, so closes before 2024-04-16 are halved: 56.46 becomes
  28.23 against the 27.91 that actually printed.
- **A cash action** contributes `(P - amount) / P`, where `P` is the
  close on the last session *before* the ex-date. A R$1 dividend on a
  R$50 share scales the past by 0.98 — the standard total-return
  restatement, which is what makes a dividend show up as return instead
  of as a fall.

Several actions on one session compose by multiplication, and that is not
a convenience: VIVT3 went ex a `DESDOBRAMENTO` of 7,900 and a
`GRUPAMENTO` of 0.025 on the same 2025-04-15, which multiply to exactly
2.0 against a measured step of 2.0031. Handling only one of them would
have been wrong by a factor of forty.

## Completeness, which is the part that matters

The arithmetic is easy and the honesty is not. An adjusted series built
from *some* of the actions is not a shorter total-return series — it is a
wrong one, and a wrong one that looks entirely plausible. So the series
is not produced wherever the inputs are incomplete.

Completeness is decided by the **archive's distribution counter**, not by
the events service, because the service is demonstrably not a complete
enumeration: ITUB4 went ex on 2025-03-18 with the archive's
`EB` marker and a **-8.60%** step, and B3's own events service reports no
action for it whatsoever. Trusting the service to have listed everything
would have adjusted straight through a real share-count event.

So: every session the counter marked ex must have a sized action against
it. The most recent one that does not is a floor, and nothing before it
is adjustable. The gap is reported rather than papered over, and a
shorter series is the honest outcome — `app.quant` already answers `None`
with too few points, and the scoring engine already treats an absent
pillar as normal (W09-001, ADR-021).

The one exception is `NOMINAL_UPDATE`, the archive's `ATZ`: an increment
on which nothing left the holder, so there is no magnitude to be missing.
Reading those as gaps would cut PETR4's adjustable history from 1,495
sessions to 28 and leave the wave delivering nothing. The evidence for
treating them differently — 151 increments, a median step of 1.0028, six
named counterexamples — is on `CorporateEventKind.NOMINAL_UPDATE`, and
ADR-026 records that this was a judgement call and whose it was.

Nothing here does I/O and nothing here rounds a decision: it is given
rows and returns numbers, so every case below is reachable from a test.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.data.models.assets import AssetPrice
from app.data.models.assets import CorporateAction as StoredAction
from app.integrations.market_data.schemas import CorporateEvent, CorporateEventKind

#: `asset_prices.adjusted_close` is `Numeric(18, 6)`, so the result is
#: quantised to what the column can hold. Rounding here rather than
#: letting the driver do it keeps the value in the database identical to
#: the value the tests assert on.
_CENTS = Decimal("0.000001")

#: Counted events that need no magnitude, because nothing left the
#: holder. See the module docstring and ADR-026.
_NEEDS_NO_MAGNITUDE = frozenset({CorporateEventKind.NOMINAL_UPDATE})


@dataclass(frozen=True)
class AdjustmentResult:
    """Adjusted closes, and an account of everything left out.

    The absences are returned rather than logged because they are the
    answer to "why does this asset still have no risk metrics", and that
    question is asked from an API response, not from a log file.
    """

    #: Session -> total-return close, for the adjustable window only.
    adjusted: dict[date, Decimal] = field(default_factory=dict)
    #: Sessions the archive counted ex with no sized action against them.
    #: The most recent of these is what bounds the window.
    unaccounted: list[date] = field(default_factory=list)
    #: Sessions where an action was sized but could not be applied — a
    #: payout at least as large as the price before it, which no factor
    #: can express. Kept apart from `unaccounted` because the cause is
    #: different: the datum is present and unusable, not missing.
    unusable: list[date] = field(default_factory=list)

    @property
    def first_adjustable(self) -> date | None:
        return min(self.adjusted) if self.adjusted else None

    @property
    def last_adjustable(self) -> date | None:
        return max(self.adjusted) if self.adjusted else None


def adjusted_closes(
    bars: Iterable[AssetPrice],
    actions: Iterable[StoredAction],
    events: Iterable[CorporateEvent],
) -> AdjustmentResult:
    """Total-return closes for as much of `bars` as is fully accounted for.

    `events` is the archive's own record of which sessions went ex and is
    what decides how far back the result reaches; `actions` supplies the
    magnitudes. Passing no events at all therefore does **not** mean "no
    events happened" — it means nothing is known to be missing, which is
    only true when the caller has genuinely checked.
    """
    sessions = sorted({bar.date: bar for bar in bars}.values(), key=lambda b: b.date)
    if not sessions:
        return AdjustmentResult()

    closes = {bar.date: bar.close for bar in sessions}
    order = [bar.date for bar in sessions]

    actions_on: dict[date, list[StoredAction]] = {}
    for action in actions:
        actions_on.setdefault(action.ex_date, []).append(action)

    counted = {
        event.date
        for event in events
        if event.kind not in _NEEDS_NO_MAGNITUDE
        # An event outside the stored price range cannot bound a series
        # that does not reach it.
        and order[0] <= event.date <= order[-1]
    }
    unaccounted = sorted(counted - set(actions_on))
    floor = unaccounted[-1] if unaccounted else None

    adjusted: dict[date, Decimal] = {}
    unusable: list[date] = []
    cumulative = Decimal(1)

    for index in range(len(order) - 1, -1, -1):
        today = order[index]
        if floor is not None and today <= floor:
            break

        adjusted[today] = (closes[today] * cumulative).quantize(_CENTS)

        # Whatever went ex today restates everything before today, so the
        # factor is folded in *after* today's value is written.
        previous_close = closes[order[index - 1]] if index else None
        step = _factor_for(actions_on.get(today, []), previous_close)
        if step is None:
            # Cannot be expressed; everything earlier is unadjustable.
            unusable.append(today)
            break
        cumulative *= step

    return AdjustmentResult(
        adjusted=adjusted, unaccounted=unaccounted, unusable=unusable
    )


def _factor_for(
    actions: list[StoredAction], previous_close: Decimal | None
) -> Decimal | None:
    """The combined factor that today's actions apply to earlier closes.

    `None` means at least one action cannot be expressed as a factor, in
    which case the caller stops rather than applying the others — a
    partial restatement of one session is not a smaller error than none,
    it is an invisible one.
    """
    combined = Decimal(1)
    for action in actions:
        if action.share_ratio is not None:
            if action.share_ratio <= 0:
                return None
            combined /= action.share_ratio
            continue

        if action.cash_amount is None:
            return None
        if previous_close is None:
            # The action went ex on the first stored session, so there is
            # nothing before it to restate. Neutral rather than fatal.
            continue
        if previous_close <= action.cash_amount:
            # A payout at or above the whole price. Either the amount is
            # wrong or the price is, and multiplying by a factor that is
            # zero or negative would put a nonsense price into every
            # earlier session (rule 44).
            return None
        combined *= (previous_close - action.cash_amount) / previous_close

    return combined
