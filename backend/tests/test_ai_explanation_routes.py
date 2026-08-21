"""End-to-end tests for the three explanation endpoints.

The whole chain — register, buy, sync prices, sync benchmarks, explain —
with a fake `AIProvider`, so nothing reaches a model. The seeding
helpers come from `test_scoring_routes` rather than being written again:
the endpoints under test explain exactly what those endpoints compute,
and duplicating the setup would let the two drift.
"""

import pytest

from app.api.dependencies import (
    get_ai_provider,
    get_benchmark_provider,
    get_market_data_provider,
)
from app.integrations.ai.base import AIProvider
from app.integrations.ai.exceptions import (
    AINotConfiguredError,
    AIResponseBlockedError,
    AIUnavailableError,
    InvalidAIResponseError,
)
from app.integrations.ai.schemas import Completion, CompletionRequest
from app.main import app
from tests.test_scoring_routes import (
    PORTFOLIOS_URL,
    STEADY,
    _auth_headers,
    _buy,
    _portfolio,
    _seed_asset,
    _seed_benchmarks,
    _window,
)


class RecordingProvider(AIProvider):
    """Answers with a fixed text and keeps what it was asked."""

    def __init__(self, text: str = "Explicação de teste.", raises=None):
        self._text = text
        self._raises = raises
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        self.requests.append(request)
        if self._raises is not None:
            raise self._raises
        return Completion(text=self._text, model="fake-001", finish_reason="STOP")

    @property
    def model(self) -> str:
        return "fake"


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    for dependency in (
        get_ai_provider,
        get_benchmark_provider,
        get_market_data_provider,
    ):
        app.dependency_overrides.pop(dependency, None)


def _use(provider: AIProvider) -> AIProvider:
    app.dependency_overrides[get_ai_provider] = lambda: provider
    return provider


def _seeded_portfolio(client, email: str) -> tuple[dict, int]:
    """A portfolio holding one asset, with prices and benchmarks synced."""
    headers = _auth_headers(client, email)
    asset_id = _seed_asset(client, headers, "PETR4", STEADY, sector="Petróleo")
    _seed_benchmarks(client, headers)
    portfolio_id = _portfolio(client, headers)
    _buy(client, headers, portfolio_id, asset_id, 100, "100")
    return headers, portfolio_id


# -- access control ---------------------------------------------------


def test_explaining_requires_authentication(client):
    response = client.post(f"{PORTFOLIOS_URL}/1/explain/performance")
    assert response.status_code == 401


def test_another_users_portfolio_cannot_be_explained(client):
    owner = _auth_headers(client, "ai-owner@example.com")
    portfolio_id = _portfolio(client, owner)
    _use(RecordingProvider())

    intruder = _auth_headers(client, "ai-intruder@example.com")
    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/explain/performance", headers=intruder
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PORTFOLIO_NOT_FOUND"


# -- performance ------------------------------------------------------


def test_performance_explanation_returns_prose_with_its_evidence(client):
    headers, portfolio_id = _seeded_portfolio(client, "ai-perf@example.com")
    _use(RecordingProvider("Sua carteira acompanhou o CDI na janela medida."))

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/explain/performance",
        params={"benchmark": "CDI", **_window()},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Sua carteira acompanhou o CDI na janela medida."
    assert body["topic"] == "PORTFOLIO_PERFORMANCE"
    assert body["model"] == "fake-001"
    assert body["prompt_version"] == "system_v1+portfolio_performance_v1"
    assert body["unverified_figures"] == []
    assert body["facts"], "the fact pack must travel with the explanation"


def test_every_fact_returned_names_the_endpoint_it_came_from(client):
    """Rule 112: the reader can go and check the number themselves."""
    headers, portfolio_id = _seeded_portfolio(client, "ai-trace@example.com")
    _use(RecordingProvider())

    body = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/explain/performance",
        params={"benchmark": "CDI", **_window()},
        headers=headers,
    ).json()

    expected = f"GET /api/v1/portfolios/{portfolio_id}/benchmarks/CDI"
    assert {fact["source"] for fact in body["facts"]} == {expected}


def test_the_model_receives_the_guardrails_and_the_rendered_facts(client):
    headers, portfolio_id = _seeded_portfolio(client, "ai-prompt@example.com")
    provider = _use(RecordingProvider())

    client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/explain/performance",
        params={"benchmark": "CDI", **_window()},
        headers=headers,
    )

    (request,) = provider.requests
    assert "NÃO CALCULE" in request.system
    assert "FATOS DISPONÍVEIS" in request.user
    # Never the raw database, the series, or the endpoint paths.
    assert "/api/v1/" not in request.user
    assert "SELECT" not in request.user.upper()


def test_an_unknown_benchmark_is_a_404_before_any_model_call(client):
    headers, portfolio_id = _seeded_portfolio(client, "ai-bench@example.com")
    provider = _use(RecordingProvider())

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/explain/performance",
        params={"benchmark": "NOPE"},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BENCHMARK_NOT_FOUND"
    assert provider.requests == []


def test_a_figure_the_model_invented_comes_back_flagged(client):
    """Reported next to the prose, not silently dropped or hidden."""
    headers, portfolio_id = _seeded_portfolio(client, "ai-flag@example.com")
    _use(RecordingProvider("A carteira rendeu 99,9% no período."))

    body = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/explain/performance",
        params={"benchmark": "CDI", **_window()},
        headers=headers,
    ).json()

    assert body["unverified_figures"] == ["99,9"]
    assert body["text"] == "A carteira rendeu 99,9% no período."


# -- contribution plan ------------------------------------------------


def test_contribution_plan_explanation_uses_the_policy_that_was_asked_for(client):
    headers, portfolio_id = _seeded_portfolio(client, "ai-plan@example.com")
    provider = _use(RecordingProvider())

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/explain/contribution-plan",
        params={"amount": "1000", "max_asset_weight": "0.5", **_window()},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["topic"] == "CONTRIBUTION_PLAN"
    assert body["prompt_version"] == "system_v1+contribution_plan_v1"

    (request,) = provider.requests
    assert "R$ 1.000,00" in request.user
    # The overridden ceiling, not the 20% default: an explanation of a
    # plan the investor did not ask for would be worse than none.
    assert "Teto de peso por ativo: 50,0%" in request.user


# -- asset score ------------------------------------------------------


def test_asset_score_explanation_is_scoped_to_the_portfolio(client):
    headers, portfolio_id = _seeded_portfolio(client, "ai-score@example.com")
    _use(RecordingProvider())

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/explain/scores/PETR4",
        params=_window(),
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["topic"] == "ASSET_SCORE"
    assert body["subject"] == "PETR4"
    source = f"GET /api/v1/portfolios/{portfolio_id}/scores"
    assert {fact["source"] for fact in body["facts"]} == {source}


def test_a_ticker_the_portfolio_does_not_score_is_a_404(client):
    headers, portfolio_id = _seeded_portfolio(client, "ai-missing@example.com")
    provider = _use(RecordingProvider())

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/explain/scores/XXXX99",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ASSET_NOT_FOUND"
    assert provider.requests == []


def test_the_ticker_is_matched_case_insensitively(client):
    headers, portfolio_id = _seeded_portfolio(client, "ai-case@example.com")
    _use(RecordingProvider())

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/explain/scores/petr4",
        params=_window(),
        headers=headers,
    )
    assert response.status_code == 200


# -- provider failures ------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (AINotConfiguredError("no key"), 503, "AI_NOT_CONFIGURED"),
        (AIUnavailableError("down"), 503, "AI_UNAVAILABLE"),
        (AIResponseBlockedError("safety"), 502, "AI_RESPONSE_BLOCKED"),
        (InvalidAIResponseError("garbage"), 502, "INVALID_AI_RESPONSE"),
    ],
    ids=["not-configured", "unavailable", "blocked", "invalid"],
)
def test_each_provider_failure_keeps_its_own_code(
    client, error, expected_status, expected_code
):
    """The operator action differs, so the status and code must too."""
    headers, portfolio_id = _seeded_portfolio(client, f"ai-{expected_code}@x.com")
    _use(RecordingProvider(raises=error))

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/explain/performance",
        params={"benchmark": "CDI", **_window()},
        headers=headers,
    )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
