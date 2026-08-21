"""Rendering a computed number as the text a person reads.

The mirror image of `frontend/src/lib/format.ts`, and deliberately so.
When the Dashboard shows `12,4%` and the explanation below it says
"rendeu 12,4%", those two strings have to be the *same* string. The
alternative — the model receiving `0.12384` and writing its own rounding
— is arithmetic performed by a language model, which is the one thing
this wave is forbidden to do (AGENTS.md rule 3, ADR-009). Rounding is a
calculation; it happens here.

The rules match the frontend's `Intl.NumberFormat('pt-BR')` exactly:

- `.` groups thousands, `,` separates decimals;
- money and plain decimals carry two digits, percents and points one;
- half-way values round **away from zero** (`ROUND_HALF_UP` in Python is
  half-away-from-zero, which is what ECMA-402's default half-expand mode
  does), so `12,35` never disagrees between screen and prose;
- an absent value is one dash, never a zero (ADR-014, rule 44).

One intentional difference: the currency separator here is an ordinary
space, where ICU emits a non-breaking one. Nothing compares the two
strings byte for byte — `app.domain.ai.guard` compares the digits — and
a non-breaking space inside a prompt is a needless surprise.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

#: What an absent value looks like. One dash, everywhere — the same
#: character `format.ts` exports as `ABSENT`.
ABSENT = "—"

_MONEY_DIGITS = 2
_DECIMAL_DIGITS = 2
_PERCENT_DIGITS = 1


def _grouped(digits: str) -> str:
    """`1234567` becomes `1.234.567`."""
    head = digits
    groups: list[str] = []
    while len(head) > 3:
        groups.insert(0, head[-3:])
        head = head[:-3]
    groups.insert(0, head)
    return ".".join(groups)


def _fixed(value: Decimal, digits: int) -> str:
    """`value` at exactly `digits` decimals, pt-BR separators, signed."""
    quantum = Decimal(1).scaleb(-digits)
    try:
        rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    except InvalidOperation:  # pragma: no cover - guards absurd magnitudes
        return ABSENT
    sign = "-" if rounded < 0 else ""
    whole, _, fraction = f"{abs(rounded):.{digits}f}".partition(".")
    rendered = _grouped(whole)
    if digits:
        rendered = f"{rendered},{fraction}"
    return f"{sign}{rendered}"


def money(value: Decimal | None) -> str:
    """Money as `R$ 1.234,56`."""
    if value is None:
        return ABSENT
    return f"R$ {_fixed(value, _MONEY_DIGITS)}"


def percent(value: Decimal | None, digits: int = _PERCENT_DIGITS) -> str:
    """A fraction as `12,3%`. `Decimal("0.123")` becomes `12,3%`.

    The multiplication by 100 is the only arithmetic in this module, and
    it is unit conversion rather than a financial computation: the
    backend stores returns as fractions (`app.quant.returns`) and people
    read them as percents.
    """
    if value is None:
        return ABSENT
    return f"{_fixed(value * 100, digits)}%"


def points(value: Decimal | None, digits: int = _PERCENT_DIGITS) -> str:
    """A difference of two percentages, signed: `+7,1 p.p.`

    Percentage points rather than percent, for the reason rule 74 gives:
    "7,1%" for a gap between two percentages is ambiguous, and the
    ambiguity is exactly where a reader's misunderstanding would land.
    """
    if value is None:
        return ABSENT
    rendered = _fixed(value * 100, digits)
    sign = "+" if value > 0 else ""
    return f"{sign}{rendered} p.p."


def decimal_value(value: Decimal | None) -> str:
    """A plain number with two decimals, for scores, betas and ratios."""
    if value is None:
        return ABSENT
    return _fixed(value, _DECIMAL_DIGITS)


def count(value: int | None) -> str:
    """A whole number, grouped but never given decimals."""
    if value is None:
        return ABSENT
    sign = "-" if value < 0 else ""
    return f"{sign}{_grouped(str(abs(value)))}"


def short_date(value: date | None) -> str:
    """An ISO date as `21/08/2026`."""
    if value is None:
        return ABSENT
    return f"{value.day:02d}/{value.month:02d}/{value.year:04d}"
