"""Data transfer objects returned by a `MarketDataProvider`.

These are provider-agnostic: nothing here (or in `base.py`) knows about
Brapi. Using Pydantic gives free type validation/coercion for data coming
from an external, untrusted source (AGENTS.md rule 19 — never assume a
field exists or is well-formed).
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


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
    #: `ATZ` — *atualização*. The one marker that is a whole token rather
    #: than a letter inside an `E...` group, and the one counted
    #: increment on which **nothing leaves the holder**. Named on
    #: evidence, the same way `EB` and `R` were: across the 2020-2025
    #: archives there are 151 increments whose specification carries
    #: `ATZ` and no ex- marker, their **median price step is 1.0028** —
    #: three tenths of a percent, ordinary daily noise — and B3's own
    #: corporate-events service reports no distribution against any of
    #: them. PETR4 alone has five (2021-04-12, 2024-02-22, 2025-03-14,
    #: 2025-08-11, 2025-11-17), none moving price by as much as 3.1%.
    #:
    #: Six of the 151 did move price by more than 15%, and they are named
    #: here rather than rounded away: two BDRs (A2MC34, L1RC34), a fund
    #: quota (SNLG11) and three shares in drawdowns of 15-20% (RRRP3,
    #: AMBP3, AZUL4). So this name is a statement about what the marker
    #: accompanies, not a promise that the session was quiet.
    #:
    #: It matters because completeness is what decides whether a total
    #: return series may be built at all (ADR-026): an increment that
    #: carries no entitlement needs no magnitude, and reading it as a
    #: missing one would cut PETR4's adjustable history from 1,495
    #: sessions to 28.
    NOMINAL_UPDATE = "NOMINAL_UPDATE"
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


class SecurityIdentity(BaseModel):
    """Which security a negotiation code actually is.

    A ticker is how a paper is traded; it is not what a corporate action
    is filed against. B3's corporate-events service keys share events on
    the **ISIN** and cash payouts on the **share class**, and both are
    printed on every COTAHIST record — so the join is exact rather than
    inferred from the ticker's trailing digit.

    Reading them off the archive is what stops one event being counted
    several times. B3 repeats a share event once per ISIN the issuer has
    ever had: BBAS3's 1:2 split arrives three times, under
    `BRBBASA04OR8`, `BRBBASA05OR5` and `BRBBASACNOR3`, of which only the
    last is the paper that trades. Composing all three raises the factor
    to the cube — 8.0 against a measured price step of 2.02 — and while
    this was being validated *every* disagreement was exactly that, an
    exact power of the right answer.
    """

    ticker: str
    #: `BRPETRACNPR6`. `CODISI` in the archive.
    isin: str
    #: `ON`, `PN`, `PNA`, `UNT`, `CI`, `DRN` — the first token of
    #: `ESPECI`, and what the cash service calls `typeStock`.
    share_class: str


class CorporateActionKind(str, Enum):
    """What a sized corporate action did, as its source labels it.

    Deliberately a different vocabulary from `CorporateEventKind`, which
    reads B3's end-of-day archive. The archive writes one marker for
    several acts and so can only say `BONUS_OR_SPLIT`; the
    corporate-events service names the act itself, so the finer
    distinction here is the source's and not this project's.

    The four cash kinds move money and leave the share count alone; the
    three share kinds move the count.
    """

    #: `DIVIDENDO`.
    CASH_DIVIDEND = "CASH_DIVIDEND"
    #: `JRS CAP PROPRIO` — juros sobre capital próprio.
    INTEREST_ON_CAPITAL = "INTEREST_ON_CAPITAL"
    #: `RENDIMENTO` — a fund quota's monthly income, and what a share
    #: occasionally carries alongside another payout.
    INCOME = "INCOME"
    #: `REST CAP DIN` — capital returned in cash.
    CAPITAL_RETURN = "CAPITAL_RETURN"
    #: `BONIFICACAO` — free shares of the same paper. **Changes the
    #: share count.**
    BONUS = "BONUS"
    #: `DESDOBRAMENTO`. **Changes the share count.**
    SPLIT = "SPLIT"
    #: `GRUPAMENTO`. **Changes the share count.**
    REVERSE_SPLIT = "REVERSE_SPLIT"


class CorporateAction(BaseModel):
    """One corporate action, with the magnitude the exchange published.

    This is the half `CorporateEvent` deliberately does not carry
    (ADR-025). The two are separate observations of the same fact by two
    separate B3 systems, and they stay separate rather than being merged
    field by field (ADR-020): the archive dates the event by its own
    distribution counter, this carries the size, and each is whole from
    one source. That they agree is **evidence, not construction** —
    across PETR3, PETR4, VALE3, ITUB4 and BBAS3 every one of **157**
    in-window payout dates resolved to a session the counter had
    independently marked ex.

    ## The date is the last date *with* the right, not the ex-date

    `last_date_prior` is B3's `lastDatePrior`/`lastDatePriorEx` verbatim:
    the final session on which buying the paper still earned the right.
    The action takes effect on the **next trading session**, which is a
    calendar lookup rather than a magnitude, so it is resolved in the
    domain layer against the sessions actually stored for the asset
    instead of being guessed at here with a weekday rule.

    ## Exactly one magnitude, in the unit its kind implies

    `cash_amount` is reais **per share**; `share_ratio` is shares held
    after per share held before, so a 1:2 split is `2` and a 1:10 reverse
    split is `0.1`. Precisely one of the two is set, enforced below — a
    cash payout has no ratio and a split has no amount, and a zero or a
    one in the empty slot would be a fabricated number that reads as a
    real one (rule 44).
    """

    last_date_prior: date
    kind: CorporateActionKind
    cash_amount: Decimal | None = None
    share_ratio: Decimal | None = None
    #: The source's own label (`JRS CAP PROPRIO`, `GRUPAMENTO`), kept
    #: verbatim for the same reason `CorporateEvent.specification` is: a
    #: classification that turns out wrong should be revisable without
    #: re-fetching anything.
    label: str

    @model_validator(mode="after")
    def _exactly_one_magnitude(self) -> "CorporateAction":
        cash, ratio = self.cash_amount, self.share_ratio
        if (cash is None) == (ratio is None):
            raise ValueError(
                "A corporate action carries either a cash amount or a share "
                "ratio, never both and never neither."
            )
        if cash is not None and cash <= 0:
            raise ValueError("A cash amount that is not positive is not a payout.")
        if ratio is not None and ratio <= 0:
            raise ValueError("A share ratio that is not positive is not a ratio.")
        return self


class Timeframe(str, Enum):
    """The bar sizes this project ingests intraday (AGENTS.md rule 47).

    Three, and deliberately not the thirteen the vendor advertises. Rule
    47 names `1m`, `5m` and `15m`, and every one of them was confirmed
    served against a live response before being listed here — the same
    evidence standard `CorporateEventKind` is held to.
    """

    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"

    @property
    def seconds(self) -> int:
        """How long one bar covers, in seconds.

        This is the cadence a gap is measured against: two consecutive
        bars of the same session more than this far apart have something
        missing between them.
        """
        return _TIMEFRAME_SECONDS[self]


_TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.ONE_MINUTE: 60,
    Timeframe.FIVE_MINUTES: 300,
    Timeframe.FIFTEEN_MINUTES: 900,
}


class HistoryWindow(str, Enum):
    """How far back a single intraday request reached.

    Part of a bar's identity, not a detail of how it was fetched, and
    the reason is measured rather than assumed (ADR-036). The vendor
    exposes intraday history as range buckets anchored at now, and
    **two buckets partition the same session differently**: asking for
    `3mo` of PETR4's 15-minute bars returns a series whose every bar
    disagrees with the `5d` and `1mo` answer for the same timestamps —
    0 of 135 identical, and 0 of 567 against `1mo`.

    It is not noise and not a late revision. The same bucket asked twice
    returns byte-identical bars (135/135 and 1,194/1,194), and `5d`
    against `1mo` is also identical (135/135). Two regimes, then: one
    shared by `1d`/`5d`/`1mo`, another used by `3mo`, which additionally
    carries a 10:00 bar the short buckets never return.

    So a session's bars are only mutually consistent if they came from
    one window. Storing which one produced a row is what lets the
    ingestion refuse to interleave two partitions into a series that
    never traded.
    """

    ONE_DAY = "1d"
    FIVE_DAYS = "5d"
    ONE_MONTH = "1mo"
    THREE_MONTHS = "3mo"


class IntradayBar(BaseModel):
    """One OHLCV bar covering `timeframe` starting at `timestamp`.

    ## No adjusted close, because the source publishes none

    `DailyBar` carries an `adjusted_close` that is `None` when the
    source did not report one. This does not, and the difference is
    measured: across 1,389 live intraday bars spanning all three
    timeframes, `adjustedClose` came back null on **every single one**.
    A field that is present and null in 1,389 of 1,389 is an absent
    field (the lesson of W06-003), and carrying it here would invite
    exactly the fabrication ADR-023 exists to prevent. Intraday bars
    are raw traded prices; nothing in this project may treat them as a
    total-return series.

    ## The timestamp is aware, and that is enforced rather than assumed

    A one-minute bar without a timezone is a bar without a time (rule
    18). The vendor publishes epoch seconds, which are unambiguous, and
    everything downstream stores and compares UTC — so a naive datetime
    reaching here means a conversion was skipped somewhere, and it is
    rejected instead of being guessed at.

    ## The timestamp labels the bar's opening instant

    Verified against a live response: PETR4's 15-minute session tiles
    exactly to 17:00 local, so a bar stamped 16:45 covers 16:45-17:00.
    """

    timestamp: datetime
    timeframe: Timeframe
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Field(ge=0)

    @field_validator("timestamp")
    @classmethod
    def _must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError(
                "An intraday bar's timestamp must carry a timezone; a naive "
                "one names no instant (AGENTS.md rule 18)."
            )
        return value
