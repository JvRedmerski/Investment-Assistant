"""When a financial statement became something the market could read.

AGENTS.md rule 109 is written for exactly this wave: *"Indicadores
fundamentalistas devem respeitar a data em que estavam disponíveis ao
mercado quando utilizados em backtests."*

The scoring engine already refuses to read a statement dated after the
date being scored (`_latest_indicator`, rule 108). That is the right
rule for a score shown today and **not enough for a backtest**, because
a fiscal year ending 31 December is not public on 1 January. It is filed
months later. A backtest that scored an asset on 2 January 2025 using
the 2024 annual results would be trading on a document that did not
exist, and it would look like a strategy that works.

## The rule, and what it is standing in for

A statement counts as available `PUBLICATION_LAG_MONTHS` after the end
of the period it reports. Three months is the CVM's own filing deadline
for the DFP, so this is the **latest legal** date rather than a guess at
a typical one — deliberately conservative, since erring late costs the
backtest a little information and erring early gives it information
nobody had.

⚠️ **It is an approximation, and the correct answer exists.** The CVM's
own archives carry the date each filing was received; ingesting that
column would replace this rule with the fact it stands in for. That is a
schema change and a re-ingestion of every fiscal year, so it is recorded
in Future Work rather than done here — and until it is, a backtest is
reading "three months after year end", not "the day it was filed".

The lag applies to the **backtest** and not to the live scoring path,
which is left exactly as it was (rule 134). See Future Work for the
related gap: `GET /portfolios/{id}/scores?as_of=` can ask a historical
question of the live engine, and that path has no lag.
"""

from datetime import date

#: Months between the end of a reporting period and the day its
#: statement is treated as public.
#:
#: The CVM requires the DFP within three months of fiscal year end.
#: Named and configurable rather than inlined, because it is a modelling
#: assumption and every result computed under it should be able to say
#: which one it used.
PUBLICATION_LAG_MONTHS = 3


def _shift_months(day: date, months: int) -> date:
    """`day` moved by `months`, clamped to the end of the target month.

    31 January shifted by one month is 28 (or 29) February, not an
    error and not 3 March. Written out rather than pulled from
    `dateutil`, which is a dependency this project does not have and
    would not be adding for eleven lines (rule 92).
    """
    total = day.year * 12 + (day.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, min(day.day, _days_in_month(year, month)))


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def available_from(
    reference_date: date, lag_months: int = PUBLICATION_LAG_MONTHS
) -> date:
    """The first date a statement for `reference_date` may be read."""
    return _shift_months(reference_date, lag_months)


def latest_readable_period(
    as_of: date, lag_months: int = PUBLICATION_LAG_MONTHS
) -> date:
    """The newest `reference_date` whose statement is public by `as_of`.

    The inverse of `available_from`, and the form a database filter can
    use: `reference_date <= latest_readable_period(as_of)` selects
    exactly the periods that had been filed, without evaluating a shift
    per row.

    Month-end clamping makes the two directions differ by at most a day
    at a month boundary — 31 May shifted back three months is 28
    February, whose forward shift is 28 May. The difference can only
    ever *withhold* a statement for a day longer, never release one
    early, which is the direction this module is allowed to err in.
    """
    return _shift_months(as_of, -lag_months)
