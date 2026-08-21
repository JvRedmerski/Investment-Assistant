"""Checking generated prose against the facts it was given.

AGENTS.md rule 44 forbids the model to invent a price, an indicator or a
result. A prompt can *ask* for that, and every prompt here does — but an
instruction is not a control. This module is the control: after the text
comes back, every figure in it is matched against the closed set of
figures the backend actually supplied, and anything unmatched is
reported.

## Why it reports instead of rejecting

Rejecting looked right at first and is wrong in practice. A rejected
completion means the user sees an error where an explanation should be,
the call is retried, and the retry is another non-deterministic draw —
so the feature's reliability would depend on how a language model
happened to phrase a sentence. Worse, a strict filter has false
positives (an ordinal, a year, "os 5 pilares"), and a control that cries
wolf gets switched off.

Reporting keeps the failure *visible and attached to the artefact*: the
`Explanation` carries both the prose and the list of figures that could
not be traced, so a screen can flag them, a test can assert on them, and
a reviewer can see immediately whether the model is quoting or inventing.
That is the same choice the scoring engine makes with `coverage` — say
what the number rests on rather than hide the weak case.

## What counts as legitimate

Anything the backend itself wrote. That is wider than the values alone:
labels are backend-authored too, so "nota de 0 a 100" makes `0` and
`100` quotable, and a date rendered `21/08/2026` makes `21`, `8` and
`2026` quotable. The model may repeat what it was told; it may not
produce a figure that appears nowhere in its input.
"""

import re

from app.domain.ai.schemas import Fact

#: Numbers as they appear in Brazilian prose: `12,4`, `1.234,56`, `2026`.
#:
#: Deliberately anchored on a digit at both ends so a percent sign, a
#: currency prefix or a trailing period ending the sentence stays out of
#: the captured token.
_NUMBER = re.compile(r"\d[\d.,]*\d|\d")


def _normalise(token: str, *, decimal_separator: str) -> str | None:
    """One numeric token reduced to a comparable canonical string.

    Thousands separators go, the decimal separator becomes a point, and
    trailing zeros are dropped so `12,40` and `12,4` compare equal —
    they are the same quantity, and flagging one against the other would
    be reporting a formatting choice as a hallucination.

    Returns `None` for a token that is not a number at all, which is the
    honest answer for something like a lone `.` inside a version string.
    """
    grouping = "." if decimal_separator == "," else ","
    cleaned = token.replace(grouping, "")
    cleaned = cleaned.replace(decimal_separator, ".")
    if cleaned.count(".") > 1 or not cleaned.strip("."):
        return None
    whole, _, fraction = cleaned.partition(".")
    fraction = fraction.rstrip("0")
    whole = whole.lstrip("0") or "0"
    return f"{whole}.{fraction}" if fraction else whole


def _tokens(text: str, *, decimal_separator: str) -> list[tuple[str, str]]:
    """Every numeric token in `text`, as (raw, canonical) pairs."""
    found: list[tuple[str, str]] = []
    for match in _NUMBER.finditer(text):
        raw = match.group()
        canonical = _normalise(raw, decimal_separator=decimal_separator)
        if canonical is not None:
            found.append((raw, canonical))
    return found


def allowed_figures(facts: tuple[Fact, ...]) -> frozenset[str]:
    """Every figure the model is entitled to write, canonicalised.

    Drawn from three places, all of them backend-authored: the rendered
    `formatted` string the model was told to quote, the canonical `value`
    behind it, and the `label`, which can legitimately carry a number
    ("0 a 100", "Pilar 1").
    """
    allowed: set[str] = set()
    for fact in facts:
        for source_text in (fact.formatted, fact.label):
            allowed.update(
                canonical
                for _, canonical in _tokens(source_text, decimal_separator=",")
            )
        if fact.value is not None:
            allowed.update(
                canonical for _, canonical in _tokens(fact.value, decimal_separator=".")
            )
            # A canonical value is stored the way the backend computes it
            # (`0.124`), while the prose quotes the rendered percent
            # (`12,4%`). `formatted` already covers the rendered side; this
            # keeps the raw side quotable too, for a fact a prompt passes
            # through verbatim such as a formula version.
    return frozenset(allowed)


def unverified_figures(text: str, facts: tuple[Fact, ...]) -> tuple[str, ...]:
    """Figures present in `text` that match no fact, in order of appearance.

    Deduplicated by the raw token, so a number the model repeats three
    times is reported once — the finding is "this figure came from
    nowhere", and saying it three times does not make it more true.
    """
    allowed = allowed_figures(facts)
    seen: set[str] = set()
    flagged: list[str] = []
    for raw, canonical in _tokens(text, decimal_separator=","):
        if canonical in allowed or raw in seen:
            continue
        seen.add(raw)
        flagged.append(raw)
    return tuple(flagged)
