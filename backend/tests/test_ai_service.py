"""Tests for `app.domain.ai.service`, with a fake provider — no network.

Same shape as `tests/test_market_data_routes.py`: the abstract type is
what the domain depends on, so a test supplies its own implementation
and the vendor never enters the picture.
"""

from decimal import Decimal

import pytest

from app.domain.ai.facts import portfolio_performance_facts
from app.domain.ai.schemas import ExplanationTopic, Fact, FactPack, FactUnit
from app.domain.ai.service import NO_DATA_TEXT, NO_MODEL, explain
from app.integrations.ai.base import AIProvider
from app.integrations.ai.exceptions import AIResponseBlockedError, AIUnavailableError
from app.integrations.ai.schemas import Completion, CompletionRequest
from tests.test_ai_facts import _comparison


class FakeProvider(AIProvider):
    """Answers with a canned text and records what it was asked."""

    def __init__(
        self,
        text: str = "Tudo certo.",
        *,
        raises: Exception | None = None,
        truncated: bool = False,
    ):
        self._text = text
        self._raises = raises
        self._truncated = truncated
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        self.requests.append(request)
        if self._raises is not None:
            raise self._raises
        return Completion(
            text=self._text,
            model="fake-model-001",
            finish_reason="MAX_TOKENS" if self._truncated else "STOP",
            prompt_tokens=100,
            output_tokens=50,
            truncated=self._truncated,
        )

    @property
    def model(self) -> str:
        return "fake-model"


def _pack() -> FactPack:
    return portfolio_performance_facts("Carteira Local", 1, _comparison())


def _explain(provider: AIProvider, pack: FactPack | None = None):
    return explain(
        provider,
        pack or _pack(),
        temperature=0.2,
        max_output_tokens=512,
    )


def test_the_explanation_carries_the_prose_and_its_evidence():
    provider = FakeProvider("Sua carteira rendeu 12,4% contra 5,3% do CDI.")
    result = _explain(provider)

    assert result.text == "Sua carteira rendeu 12,4% contra 5,3% do CDI."
    assert result.topic is ExplanationTopic.PORTFOLIO_PERFORMANCE
    assert result.subject == "Carteira Local"
    assert result.prompt_version == "system_v1+portfolio_performance_v1"
    assert result.unverified_figures == ()
    # The pack ships with the text: that is what makes it checkable.
    assert result.facts == _pack().facts


def test_the_model_recorded_is_the_one_that_answered():
    """Not the one requested — vendors resolve aliases server-side."""
    provider = FakeProvider()
    assert _explain(provider).model == "fake-model-001"
    assert provider.model == "fake-model"


def test_a_figure_that_traces_to_no_fact_is_reported_on_the_result():
    provider = FakeProvider("A carteira rendeu 12,4%, contra inflação de 4,8%.")
    result = _explain(provider)

    assert result.unverified_figures == ("4,8",)
    # Reported, not withheld: the reader still gets the explanation, with
    # the untraceable figure flagged next to it.
    assert "4,8%" in result.text


def test_the_provider_receives_the_facts_and_the_guardrails():
    provider = FakeProvider()
    _explain(provider)

    (request,) = provider.requests
    assert "12,4%" in request.user
    assert "NÃO CALCULE" in request.system
    assert request.max_output_tokens == 512


def test_a_pack_with_nothing_computed_never_reaches_the_provider():
    """Rule 44: no data means "no data", not a prompt to fill the gap."""
    empty = FactPack(
        topic=ExplanationTopic.PORTFOLIO_PERFORMANCE,
        subject="Carteira Vazia",
        facts=(
            Fact(
                key="portfolio.total_return",
                label="Carteira — retorno acumulado",
                value=None,
                formatted="—",
                unit=FactUnit.PERCENT,
                source="GET /api/v1/portfolios/1/benchmarks/CDI",
            ),
        ),
    )
    provider = FakeProvider()
    result = _explain(provider, empty)

    assert provider.requests == []
    assert result.text == NO_DATA_TEXT
    assert result.model == NO_MODEL
    assert result.unverified_figures == ()
    assert result.facts == empty.facts


def test_the_short_circuit_still_records_the_prompt_version():
    """The topic was answered; which instruction governs it is unchanged."""
    empty = FactPack(
        topic=ExplanationTopic.ASSET_SCORE,
        subject="XXXX",
        facts=(
            Fact(
                key="score.final",
                label="Score final",
                value=None,
                formatted="—",
                unit=FactUnit.SCORE,
                source="GET /api/v1/portfolios/1/scores",
            ),
        ),
    )
    assert _explain(FakeProvider(), empty).prompt_version == (
        "system_v1+asset_score_v1"
    )


@pytest.mark.parametrize(
    "error",
    [AIUnavailableError("down"), AIResponseBlockedError("safety")],
    ids=["unavailable", "blocked"],
)
def test_a_provider_failure_propagates_rather_than_becoming_an_apology(error):
    """An explanation that failed is not an explanation with a note in it."""
    with pytest.raises(type(error)):
        _explain(FakeProvider(raises=error))


def test_generated_at_is_timezone_aware_utc():
    result = _explain(FakeProvider())
    assert result.generated_at.utcoffset() == __import__("datetime").timedelta(0)


def test_a_single_available_fact_is_enough_to_call_the_provider():
    """The short circuit is for *nothing* computed, not for a thin pack."""
    comparison = _comparison(
        subject=_comparison().subject.model_copy(
            update={
                "total_return": Decimal("0.1238"),
                "annualised_return": None,
                "volatility": None,
                "max_drawdown": None,
            }
        )
    )
    provider = FakeProvider()
    _explain(provider, portfolio_performance_facts("Carteira Local", 1, comparison))
    assert len(provider.requests) == 1


def test_a_truncated_completion_reaches_the_reader_labelled_as_truncated():
    """The flag travels; the text is neither discarded nor repaired.

    Found by a live call on 2026-08-22: at the then-default budget, a
    reasoning model spent 981 of 1.024 tokens thinking and returned a
    sentence cut after a colon. It was served as a finished explanation
    because `MAX_TOKENS` counted as a normal finish (ADR-033).
    """
    fragment = "O plano alocou R$ 742,30 entre tres ativos:"
    result = _explain(FakeProvider(fragment, truncated=True))

    assert result.truncated is True
    assert result.text == fragment


def test_an_ordinary_completion_is_not_flagged_as_truncated():
    assert _explain(FakeProvider()).truncated is False


def test_the_no_facts_short_circuit_is_never_truncated():
    """It calls no provider, so there is no budget to run out of."""
    empty = _pack().model_copy(
        update={
            "facts": tuple(
                fact.model_copy(update={"value": None, "formatted": "—"})
                for fact in _pack().facts
            )
        }
    )
    provider = FakeProvider()
    result = _explain(provider, empty)

    assert result.truncated is False
    assert provider.requests == []
