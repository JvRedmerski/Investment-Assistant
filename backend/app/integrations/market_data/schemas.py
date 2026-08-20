"""Data transfer objects returned by a `MarketDataProvider`.

These are provider-agnostic: nothing here (or in `base.py`) knows about
Brapi. Using Pydantic gives free type validation/coercion for data coming
from an external, untrusted source (AGENTS.md rule 19 — never assume a
field exists or is well-formed).
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class DailyBar(BaseModel):
    """One OHLCV daily bar for an asset.

    `adjusted_close` is `None` when the source did not report one. It is
    deliberately not defaulted to `close`: the adjusted close is a
    different quantity (it nets out dividends and splits), so filling it
    from the raw close would substitute a fabricated figure for a missing
    one — what AGENTS.md rule 44 and ADR-014 forbid. `validate_daily_bars`
    rejects such bars, so nothing unadjusted reaches storage.
    """

    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal | None
    volume: Decimal = Field(ge=0)


class CorporateEventKind(str, Enum):
    """Which right went ex on a session.

    The names describe **what the holder stopped being entitled to**, not
    what the company called the act, because that is the only reading the
    source supports. Each is one letter of B3's ex- marker, and every one
    below was checked against a real 2024 price step before it was named
    here (see `cotahist.py`).

    Two of them move the share count and therefore break an unadjusted
    price series; the rest move cash.
    """

    #: `D` — dividendo.
    DIVIDEND = "DIVIDEND"
    #: `J` — juros sobre capital próprio.
    INTEREST_ON_CAPITAL = "INTEREST_ON_CAPITAL"
    #: `R` — a payout the exchange files under neither of the two above,
    #: and the one kind named for what it is *observed* to be rather than
    #: for what it is called. It is a fund's monthly *rendimento* in
    #: 3,544 of 2024's events, every one of them a fund quota. But it
    #: also lands on shares alongside another payout — PETR4 carries
    #: `EDR` on four dividend sessions, VIVT3 carries `ERJ` — and what
    #: it covers there is not established by the file. What every
    #: observed case does share is that money left and the share count
    #: did not move, so that, and only that, is what the name claims.
    OTHER_DISTRIBUTION = "OTHER_DISTRIBUTION"
    #: `A` — amortização. Capital returned to the holder, which is why it
    #: moves a price by a third where a distribution moves it by one
    #: percent.
    AMORTISATION = "AMORTISATION"
    #: `B` — the holder receives more shares of the same paper for free.
    #: Named for both acts because B3 writes `EB` for either: BBAS3's 1:2
    #: *desdobramento* on 2024-04-16 and NVDC34's 10:1 split on
    #: 2024-06-10 carry the same marker as a *bonificação*. Splitting the
    #: name on the legal act would claim a distinction the file does not
    #: make, and the range it has to cover is real: the same marker
    #: carries MGLU3's 1:4 split in 2020 (104.00 -> 25.59) and its 4.5%
    #: bonus in 2025 (9.35 -> 8.94). **Changes the share count.**
    BONUS_OR_SPLIT = "BONUS_OR_SPLIT"
    #: `G` — grupamento. MGLU3's 1:10 on 2024-05-27 is this, and it is
    #: the event that shows up as +896% in a raw series (ADR-023).
    #: **Changes the share count.**
    REVERSE_SPLIT = "REVERSE_SPLIT"
    #: `S` — subscrição. A right to buy, not something received.
    SUBSCRIPTION = "SUBSCRIPTION"
    #: The exchange counted a distribution this session, and what went ex
    #: cannot be read off the file: either the specification carries no
    #: ex- marker at all (7.5% of the 2024 events), or it carries a
    #: letter this project has no evidence for. The event is still
    #: reported, because it happened; only its nature is unknown, and
    #: guessing one would be rule 44 all over again.
    UNCLASSIFIED = "UNCLASSIFIED"


class CorporateEvent(BaseModel):
    """One right that an asset stopped carrying on one session.

    This is an **observation, not an interpretation**: the date is the
    session B3's own end-of-day file first counted the paper as trading
    ex, so the fact and the date are the exchange's statement rather than
    this project's inference.

    There is deliberately **no factor and no amount**. The file records
    that a distribution occurred and never how large it was — a marker is
    not a magnitude — and deriving one from the price step would be the
    heuristic ADR-023 rejected. Sizing these events is a separate problem
    with a separate source.

    A session can carry more than one right (`EDJ` is a dividend and
    interest on capital), and each becomes its own event. They share a
    `distribution_number`, which is B3's own counter for the paper, so
    what the exchange counted as one distribution stays recoverable.

    `specification` is the raw `ESPECI` field, verbatim, spacing and all
    (`ON  EG  NM`). It is kept whole rather than reduced to the marker so
    that a classification which turns out wrong can be revisited without
    re-reading tens of gigabytes of archive.
    """

    date: date
    kind: CorporateEventKind
    specification: str
    distribution_number: int = Field(ge=0)


class Quote(BaseModel):
    """A single latest-price quote for an asset."""

    ticker: str
    price: Decimal
    currency: str
    as_of: datetime
