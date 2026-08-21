"""The contract between the deterministic backend and the model.

## The fact pack, and why it is the whole design

An explanation is auditable only if every number in it can be traced to
the endpoint that computed it (`CURRENT_TASK`, AGENTS.md rule 112). So
the model is never handed a portfolio, a database row, or a question. It
is handed a **fact pack**: a flat, closed list of already-computed
values, each one labelled, carrying its unit, already rendered as the
string the screen shows, and stamped with the endpoint it came from.

That shape buys three things at once:

1. **The model cannot calculate**, because there is nothing to calculate
   from — no series, no components, no raw inputs. It can only quote
   (rule 3, ADR-009).
2. **The model cannot round**, because `formatted` is already rounded by
   `app.domain.ai.formatting`, the mirror of the frontend's formatter.
3. **Every figure in the output can be checked**, because the set of
   legitimate figures is finite and known — which is what
   `app.domain.ai.guard` does after generation.

## Absence travels as absence

A fact whose `value` is `None` is kept in the pack, not dropped. Dropping
it would leave the model free to assume the number simply was not
interesting; carrying it, with `formatted` set to a dash, lets the prompt
state the one rule rule 44 demands — an unavailable number is reported as
unavailable and never explained.
"""

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FactUnit(str, enum.Enum):
    """What kind of quantity a fact is, so the prompt can name it.

    Carried explicitly because the unit is the difference between a
    correct sentence and a wrong one: `excess_return` and `total_return`
    are both fractions in the database and mean percentage points and
    percent respectively, which is precisely the confusion rule 74
    exists to prevent.
    """

    CURRENCY_BRL = "CURRENCY_BRL"
    PERCENT = "PERCENT"
    POINTS = "POINTS"
    DECIMAL = "DECIMAL"
    SCORE = "SCORE"
    COUNT = "COUNT"
    DATE = "DATE"
    TEXT = "TEXT"


class ExplanationTopic(str, enum.Enum):
    """What an explanation is about.

    A closed set, one entry per question the backend can already answer
    with numbers. There is no free-form topic on purpose: a topic
    without a fact builder would be a prompt with no facts, which is an
    invitation to invent them.
    """

    #: "Estou batendo o CDI?" — from the portfolio-versus-benchmark comparison.
    PORTFOLIO_PERFORMANCE = "PORTFOLIO_PERFORMANCE"
    #: "Onde colocar o próximo aporte, e por quê?" — from the contribution plan.
    CONTRIBUTION_PLAN = "CONTRIBUTION_PLAN"
    #: "Por que este ativo pontua assim?" — from the asset's sub-scores.
    ASSET_SCORE = "ASSET_SCORE"


class Fact(BaseModel):
    """One already-computed number, ready to be quoted.

    `value` is the canonical figure as the backend holds it, serialised
    as a string so no float ever enters the pack. `formatted` is that
    same figure rendered for a reader. The model is told to use
    `formatted` and nothing else; `value` is carried for the audit trail
    and for `guard`, not for the prompt.

    `source` is the API path that produced the number — the link that
    makes the explanation checkable against the system that made it.
    """

    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    value: str | None
    formatted: str
    unit: FactUnit
    source: str


class FactPack(BaseModel):
    """Everything the model is allowed to know for one explanation.

    `subject` names what is being explained in words the reader already
    sees on screen ("Carteira Local", "PETR4"). Nothing here identifies
    the user: no e-mail, no id beyond what the subject line needs, no
    credential (AGENTS.md rules 41 and 91 — send the minimum).
    """

    model_config = ConfigDict(frozen=True)

    topic: ExplanationTopic
    subject: str
    facts: tuple[Fact, ...]

    @property
    def available(self) -> tuple[Fact, ...]:
        """The facts that actually carry a value."""
        return tuple(fact for fact in self.facts if fact.value is not None)

    @property
    def unavailable(self) -> tuple[Fact, ...]:
        """The facts the backend could not compute."""
        return tuple(fact for fact in self.facts if fact.value is None)


class Explanation(BaseModel):
    """Generated prose, plus everything needed to audit it.

    The fact pack ships **with** the text rather than being discarded
    after the call. That is the difference between an explanation and a
    claim: a reader — or a reviewer, or a test — can hold the prose next
    to the exact figures it was given and check it.

    `unverified_figures` lists numbers that appear in the text and match
    no fact. It is a report, not a rejection; see `guard` for why.
    """

    model_config = ConfigDict(frozen=True)

    topic: ExplanationTopic
    subject: str
    text: str
    #: The model that actually answered, as the provider reported it.
    model: str
    #: Which versioned prompt produced this (AGENTS.md rule 43).
    prompt_version: str
    generated_at: datetime
    facts: tuple[Fact, ...]
    unverified_figures: tuple[str, ...]
