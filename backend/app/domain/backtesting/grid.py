"""What a walk-forward is allowed to tune, and the values it may try.

Pure and I/O-free (rule 68): policies in, policies out.

Rule 60 is the one this module exists to obey, and it is worth quoting
because it is easy to obey in the letter and break in the spirit: *"não
ajustar parâmetros até obter o melhor resultado histórico sem
validação"*, with `RSI = 31.7` as the named anti-pattern, and *"preferir
parâmetros simples e robustos"*.

## A grid is a hypothesis set, not a search space

The difference is what happens when it grows. A search space is swept:
more points make the best point better, and the best point is mostly a
description of the noise it was fitted to. A hypothesis set is *asked*:
each entry answers one question a person could state in words before
seeing any result.

So the grid here is built **one parameter at a time** from the policy the
caller is running — never as a cross product. Seven candidates, each
differing from the base in exactly one field, each with the question it
answers written next to it. A cross product of the same three axes would
be eighteen, and eighteen results over three folds is a sweep wearing a
walk-forward's clothes.

The values are round: 30 and 70 on a 0–100 score, a quarter and three
quarters of coverage, three and eight positions. None of them was chosen
by looking at a result, which is the only property that matters and the
only one a reader cannot check — hence this paragraph and the version
below.

## The grid is relative to the caller's policy, not to the shipped one

`policy_grid(base)` varies whatever the caller is actually running. An
investor who already tightened `min_coverage` is asking whether *their*
limits are stable, and testing variants of somebody else's defaults would
answer a question nobody asked.

A variant that lands on the base policy is dropped rather than reported
twice — it is the base, and two identical rows in a ranking are noise
with a second name.

## Versioned, because a plan that cannot say which rules produced it is
not reproducible

`WALK_FORWARD_GRID_VERSION` sits beside `SCORING_FORMULA_VERSION` and
`ALLOCATION_RULES_VERSION` for the same reason (rule 113): a stability
figure is a statement about a specific set of hypotheses, and the set
changing without the version changing makes two results silently
incomparable.
"""

from dataclasses import dataclass, replace
from decimal import Decimal

from app.domain.recommendations.allocation import AllocationPolicy

#: Version of the hypothesis set below: which fields are varied, and to
#: what. Bump on any change to the candidates — a stability figure is a
#: statement about *these* hypotheses.
WALK_FORWARD_GRID_VERSION = "1.0.0"

#: The name every grid's first entry carries: the policy as given.
#:
#: Always present and always first, which is also the tie-break: a
#: candidate that merely matches the shipped policy never displaces it
#: (`walkforward.select`).
BASELINE = "default"


@dataclass(frozen=True)
class PolicyCandidate:
    """One policy the walk-forward may select, and the question it asks.

    `question` is not documentation of the code — it is part of the
    result. A candidate that cannot be stated as a question somebody
    would ask before running anything is a swept parameter, and rule 60
    is precisely about not shipping those.
    """

    name: str
    question: str
    policy: AllocationPolicy


def policy_grid(base: AllocationPolicy) -> tuple[PolicyCandidate, ...]:
    """`base`, plus one single-field variant per hypothesis.

    Order is fixed and meaningful: the baseline first, then the two
    floors, then concentration. Selection breaks ties by this order, so
    it decides which policy wins a dead heat — and the answer is the one
    already in production.
    """
    candidates = [
        PolicyCandidate(
            name=BASELINE,
            question="Is the policy as configured the one to keep?",
            policy=base,
        ),
        PolicyCandidate(
            name="min-score-30",
            question="Does funding weaker scores help, or only add names?",
            policy=replace(base, min_score=Decimal(30)),
        ),
        PolicyCandidate(
            name="min-score-70",
            question="Does refusing everything but the strongest scores help?",
            policy=replace(base, min_score=Decimal(70)),
        ),
        PolicyCandidate(
            name="min-coverage-25",
            question="Does a looser evidence floor pay for the assets it lets in?",
            policy=replace(base, min_coverage=Decimal("0.25")),
        ),
        PolicyCandidate(
            name="min-coverage-75",
            question="Does demanding most of the formula pay for the assets it cuts?",
            policy=replace(base, min_coverage=Decimal("0.75")),
        ),
        PolicyCandidate(
            name="max-positions-3",
            question="Does concentrating each contribution into fewer names help?",
            policy=replace(base, max_positions=3),
        ),
        PolicyCandidate(
            name="max-positions-8",
            question="Does spreading each contribution wider help?",
            policy=replace(base, max_positions=8),
        ),
    ]
    return _deduplicated(candidates)


def _deduplicated(
    candidates: list[PolicyCandidate],
) -> tuple[PolicyCandidate, ...]:
    """Drop a variant that landed on a policy already in the grid.

    Happens whenever the caller's own policy already holds one of the
    values above. The variant *is* the baseline then, and reporting it
    under a second name would put the same run twice in a ranking.
    """
    seen: list[AllocationPolicy] = []
    unique: list[PolicyCandidate] = []
    for candidate in candidates:
        if candidate.policy in seen:
            continue
        seen.append(candidate.policy)
        unique.append(candidate)
    return tuple(unique)
