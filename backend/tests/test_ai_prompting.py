"""Tests for `app.domain.ai.prompting`.

Two of these are the mechanical ones — the files load, the placeholders
fill. The one that earns its place is
`test_no_prompt_introduces_a_figure_that_is_not_a_fact`: it turns rule
43's "do not hide business logic in prompts" from an instruction a
reviewer has to remember into something the suite fails on.
"""

import re
from datetime import date
from decimal import Decimal

import pytest

from app.domain.ai.facts import (
    asset_score_facts,
    contribution_plan_facts,
    portfolio_performance_facts,
)
from app.domain.ai.guard import allowed_figures, unverified_figures
from app.domain.ai.prompting import (
    PROMPT_FILES,
    SYSTEM_PROMPT,
    build_request,
    load_prompt,
    prompt_version,
    render_facts,
)
from app.domain.ai.schemas import ExplanationTopic
from tests.test_ai_facts import (
    _allocation,
    _comparison,
    _plan,
    _score,
)


def _packs():
    plan = _plan([_allocation("PETR4", "400", 1)], [])
    return [
        portfolio_performance_facts("Carteira Local", 1, _comparison()),
        contribution_plan_facts("Carteira Local", plan),
        asset_score_facts(_score(), portfolio_id=1),
    ]


def test_every_topic_has_a_prompt_file_that_loads():
    assert set(PROMPT_FILES) == set(ExplanationTopic)
    for name in [*PROMPT_FILES.values(), SYSTEM_PROMPT]:
        assert load_prompt(name).strip()


def test_every_task_prompt_declares_both_placeholders():
    for name in PROMPT_FILES.values():
        template = load_prompt(name)
        assert "{subject}" in template
        assert "{facts}" in template


def test_the_recorded_version_names_both_halves():
    """A change to the shared guardrails changes the output too."""
    version = prompt_version(ExplanationTopic.ASSET_SCORE)
    assert version == "system_v1+asset_score_v1"


def test_available_and_unavailable_facts_land_in_separate_blocks():
    pack = portfolio_performance_facts("Carteira Local", 1, _comparison())
    rendered = render_facts(pack)

    available_at = rendered.index("FATOS DISPONÍVEIS")
    unavailable_at = rendered.index("FATOS INDISPONÍVEIS")
    assert available_at < unavailable_at

    # `comparison.beta` is the absent one in this fixture, and it belongs
    # below the second heading, not the first.
    assert rendered.index("Beta da carteira contra o benchmark") > unavailable_at
    assert rendered.index("Carteira — retorno acumulado no período") < unavailable_at


def test_a_pack_with_nothing_missing_says_so_explicitly():
    """Silence would read as "the list ended", not "nothing is missing"."""
    comparison = _comparison(beta=Decimal("0.94"))
    pack = portfolio_performance_facts("Carteira Local", 1, comparison)
    assert "nenhum" in render_facts(pack)


def test_the_endpoint_and_key_stay_out_of_the_prompt():
    """They serve the audit trail, which rides on the `Explanation`.

    Sending them would also put the bare digits of `/api/v1/portfolios/3`
    in front of a model told to quote only the numbers it was given.
    """
    pack = asset_score_facts(_score(), portfolio_id=3)
    rendered = render_facts(pack)

    assert "score.final" not in rendered
    assert "/api/v1/" not in rendered
    assert "Score final do ativo (0 a 100): 76,72" in rendered
    assert all(fact.source for fact in pack.facts)


def test_build_request_fills_the_subject_and_the_facts():
    pack = portfolio_performance_facts("Carteira Local", 1, _comparison())
    request = build_request(pack, temperature=0.2, max_output_tokens=512)

    assert "Carteira Local" in request.user
    assert "12,4%" in request.user
    assert request.system == load_prompt(SYSTEM_PROMPT)
    assert request.temperature == pytest.approx(0.2)
    assert request.max_output_tokens == 512


@pytest.mark.parametrize("pack", _packs(), ids=lambda p: p.topic.value)
def test_no_prompt_introduces_a_figure_that_is_not_a_fact(pack):
    """Rule 43, made testable.

    Every number reaching the model has to be a number the backend
    computed. A prompt that grew a literal threshold — "o teto por ativo
    é 20%" — would have moved a business rule out of the code and into a
    text file, and would fail here.
    """
    request = build_request(pack, temperature=0.2, max_output_tokens=512)
    assert unverified_figures(request.user, pack.facts) == ()


def test_the_system_prompt_shows_no_example_figure_that_could_leak():
    """A plausible number in the guardrails is a number that gets echoed.

    The rules are numbered, so bare digits are expected there. What must
    not appear is anything shaped like a *measurement* — `12,4%` written
    as an example of how to quote a value would sit in every prompt,
    ready to be repeated into an explanation where it means nothing.
    """
    assert re.search(r"\d,\d", load_prompt(SYSTEM_PROMPT)) is None


def test_allowed_figures_is_empty_for_an_empty_pack():
    assert allowed_figures(()) == frozenset()


def test_an_unknown_prompt_name_fails_loudly():
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist_v9")


def test_a_date_only_pack_still_renders(tmp_path):
    """Guards the rendering path when every fact is a plain string."""
    pack = portfolio_performance_facts(
        "Carteira Local",
        1,
        _comparison(
            subject=_comparison().subject.model_copy(
                update={"start_date": date(2020, 3, 2)}
            )
        ),
    )
    assert "02/03/2020" in render_facts(pack)
