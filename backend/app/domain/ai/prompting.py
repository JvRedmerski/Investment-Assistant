"""Loading the versioned prompts and rendering a fact pack into one.

AGENTS.md rule 43 asks for two things, and this module is where both are
kept honest.

**Prompts are versioned files, not string literals.** They live in
`prompts/*_v1.txt` and the version travels on every `Explanation`, so a
piece of prose can always be matched to the instruction that produced
it. Changing the wording means writing `_v2.txt` and pointing
`PROMPT_FILES` at it — never editing `_v1` in place, which would leave
already-generated explanations attributed to text that no longer exists.

**No business logic hides in them.** The prompts carry role, guardrails
and the order of an argument. Every threshold, weight, ceiling and
version arrives as a *fact*, with its own value and its own source, so a
reader who wants to know why an allocation stopped at a ceiling reads
the ceiling rather than trusting a sentence. A prompt that started
saying "o teto por ativo é 20%" would have moved a rule out of the code
and into a text file, which is exactly what rule 43 forbids.

## The rendered prompt has two sections, always

Available facts and unavailable ones are listed separately, under
headings that say what each list means. Rule 44's `Data unavailable` is
a *behaviour*, and a behaviour needs the model to be able to tell the
two apart at a glance — a dash buried in a single long list is easy to
read past, and reading past it produces exactly the confident invented
number the rule exists to prevent.

## What is deliberately left out of the prompt

A fact's `key` and `source` do not go to the model. They exist for the
audit trail, and the audit trail travels on the `Explanation`, where a
reader can hold every figure next to the endpoint that produced it —
sending them as well would buy nothing the model can use.

It would also cost something. `GET /api/v1/portfolios/1/benchmarks/CDI`
puts two bare digits in front of a model instructed to quote only the
numbers it was given, which is a needless invitation and one that the
guard cannot distinguish from a real one. Rule 91 asks for the minimum;
here the minimum is also the safer prompt.
"""

from functools import cache
from pathlib import Path

from app.domain.ai.schemas import ExplanationTopic, FactPack
from app.integrations.ai.schemas import CompletionRequest

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

#: The shared instruction: role, the six absolute rules, and the style.
SYSTEM_PROMPT = "system_v1"

#: Which task prompt serves which topic. Bumping a version is an edit here.
PROMPT_FILES: dict[ExplanationTopic, str] = {
    ExplanationTopic.PORTFOLIO_PERFORMANCE: "portfolio_performance_v1",
    ExplanationTopic.CONTRIBUTION_PLAN: "contribution_plan_v1",
    ExplanationTopic.ASSET_SCORE: "asset_score_v1",
}

_AVAILABLE_HEADING = (
    "FATOS DISPONÍVEIS — são estes, e apenas estes, os números que você "
    "pode citar. Copie cada um exatamente como está escrito."
)
_UNAVAILABLE_HEADING = (
    "FATOS INDISPONÍVEIS — o backend não conseguiu calcular estes valores. "
    "Não estime, não infira a partir dos outros e não trate como zero. "
    "Se forem relevantes, diga que estão indisponíveis."
)
_NO_UNAVAILABLE = "FATOS INDISPONÍVEIS — nenhum. Todos os valores foram calculados."


@cache
def load_prompt(name: str) -> str:
    """The text of a versioned prompt file.

    Cached because a prompt is immutable by policy: a new wording is a
    new file. Raises `FileNotFoundError` at first use rather than
    returning a silent empty string, so a mistyped version fails where a
    developer can see it.
    """
    return (_PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8").strip()


def prompt_version(topic: ExplanationTopic) -> str:
    """The identifier recorded on every explanation of `topic`.

    Both halves, because both shape the output: a change to the shared
    guardrails is as much a change to the result as a change to the task
    prompt, and an audit trail that named only one would be misleading.
    """
    return f"{SYSTEM_PROMPT}+{PROMPT_FILES[topic]}"


def render_facts(pack: FactPack) -> str:
    """The fact pack as the two labelled blocks the model reads."""
    lines: list[str] = [_AVAILABLE_HEADING, ""]
    lines += [f"- {fact.label}: {fact.formatted}" for fact in pack.available]

    unavailable = pack.unavailable
    lines.extend(["", _UNAVAILABLE_HEADING if unavailable else _NO_UNAVAILABLE, ""])
    lines += [f"- {fact.label}" for fact in unavailable]

    return "\n".join(lines).strip()


def build_request(
    pack: FactPack,
    *,
    temperature: float,
    max_output_tokens: int,
) -> CompletionRequest:
    """The complete request for one explanation.

    The task prompt is rendered with the subject and the facts, and the
    guardrails ride in `system`. Keeping them in separate fields is what
    lets a provider hand the vendor its native system instruction, and
    it also draws the line the whole wave rests on: `system` is what the
    model must obey, `user` is the data it may quote, and nothing else
    is in the request at all.
    """
    template = load_prompt(PROMPT_FILES[pack.topic])
    return CompletionRequest(
        system=load_prompt(SYSTEM_PROMPT),
        user=template.format(subject=pack.subject, facts=render_facts(pack)),
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
