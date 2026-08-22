"""End-to-end tests for the walk-forward endpoint (W14-004).

The whole chain — register, track an asset, sync its prices, walk the
strategy forward — with a fake provider so nothing touches the network.

Like `test_backtest_routes`, this universe carries no financial
statements, so every score rests on Risk and Diversification alone: 0,40
of the formula, under the default floor. `min_coverage` is lowered for
the same reason it is there — rule 32 means the limits are the
investor's to set.

The scheme is quarterly throughout. The default is a year per segment,
which needs three years of history; the fake provider serves 400 days,
and a fixture pretending otherwise would be testing a window nobody has.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.api.dependencies import get_market_data_provider
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.schemas import DailyBar
from app.main import app

ASSETS_URL = "/api/v1/assets"
WALK_FORWARD_URL = "/api/v1/backtests/walk-forward"

DAYS = [date(2024, 1, 1) + timedelta(days=offset) for offset in range(400)]

#: Coverage without a single financial statement is 0,40.
THIN_COVERAGE = "0.4"

#: Nine months from the first session: exactly one quarterly fold.
ONE_FOLD_END = date(2024, 9, 30)
#: Twelve months: two.
TWO_FOLD_END = date(2024, 12, 31)


class FakeMarketData(MarketDataProvider):
    """A gently rising series, so a segment has a return to measure."""

    def __init__(self, close: str = "10", drift: str = "0.01"):
        price = Decimal(close)
        step = Decimal(drift)
        self._bars = [
            DailyBar(
                date=day,
                open=price + step * offset,
                high=price + step * offset,
                low=price + step * offset,
                close=price + step * offset,
                adjusted_close=price + step * offset,
                volume=Decimal(1000),
            )
            for offset, day in enumerate(DAYS)
        ]

    def get_quote(self, ticker):  # pragma: no cover - unused here
        raise NotImplementedError

    def get_daily_history(self, ticker, start, end):
        return [bar for bar in self._bars if start <= bar.date <= end]


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.pop(get_market_data_provider, None)


def _auth_headers(client, email="walkforward@example.com"):
    client.post(
        "/api/v1/auth/register", json={"email": email, "password": "SuperSecret123"}
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _seed_asset(client, headers, ticker="AAA3", sector="Energia", drift="0.01"):
    client.post(
        ASSETS_URL,
        json={
            "ticker": ticker,
            "name": ticker,
            "asset_type": "STOCK",
            "sector": sector,
        },
        headers=headers,
    )
    app.dependency_overrides[get_market_data_provider] = lambda: FakeMarketData(
        drift=drift
    )
    client.post(
        f"{ASSETS_URL}/{ticker}/prices/sync",
        json={"start": DAYS[0].isoformat(), "end": DAYS[-1].isoformat()},
        headers=headers,
    )


def _walk(client, headers, **params):
    return client.get(
        WALK_FORWARD_URL,
        params={
            "start": DAYS[0].isoformat(),
            "end": ONE_FOLD_END.isoformat(),
            "segment_months": 3,
            "step_months": 3,
            "objective": "total-return",
            "min_coverage": THIN_COVERAGE,
            **params,
        },
        headers=headers,
    )


# -- the happy path ---------------------------------------------------


def test_a_walk_forward_reports_its_folds_and_what_each_one_chose(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    response = _walk(client, headers, day_of_month=5)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["universe"] == ["AAA3"]
    assert body["partition"]["folds"] == 1
    assert body["partition"]["refusal"] is None

    fold = body["folds"][0]
    assert fold["selected"] is not None
    assert fold["tested"] is not None
    assert fold["train"]["end"] < fold["validation"]["start"]
    assert fold["validation"]["end"] < fold["test"]["start"]


def test_the_declared_grid_travels_with_the_result(client):
    """Rule 60: the hypotheses have to be readable, and versioned."""
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    body = _walk(client, headers).json()

    assert body["grid_version"] == "1.0.0"
    assert body["candidates"][0]["name"] == "default"
    assert len(body["candidates"]) == 7
    for candidate in body["candidates"]:
        assert candidate["question"].endswith("?")
        assert candidate["policy"]["min_coverage"] is not None


def test_the_settings_come_back_with_the_result(client):
    """Rule 113: a figure that cannot say what produced it is not
    reproducible."""
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    body = _walk(client, headers, amount="500").json()

    assert body["settings"]["contribution"] == "500"
    assert body["settings"]["objective"] == "total-return"
    assert body["settings"]["scheme"] == {"segment_months": 3, "step_months": 3}
    assert body["settings"]["shortlist"] == 3
    assert body["settings"]["publication_lag_months"] == 3
    assert body["settings"]["policy"]["min_coverage"] == "0.4"


def test_only_the_shortlist_reaches_validation(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    fold = _walk(client, headers).json()["folds"][0]

    assert len(fold["trained"]) == 7
    assert len(fold["shortlist"]) <= 3
    assert [run["name"] for run in fold["validated"]] == fold["shortlist"]
    assert fold["selected"] in fold["shortlist"]


def test_degradation_is_reported_next_to_the_two_figures_it_compares(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    fold = _walk(client, headers).json()["folds"][0]

    assert Decimal(fold["degradation"]) == Decimal(fold["in_sample"]) - Decimal(
        fold["out_of_sample"]
    )
    assert fold["out_of_sample"] == fold["tested"]["objective"]


def test_two_folds_are_aggregated_into_a_stability_claim(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    body = _walk(client, headers, end=TWO_FOLD_END.isoformat()).json()

    assert body["partition"]["folds"] == 2
    stability = body["stability"]
    assert stability["refusal"] is None
    assert stability["measured_folds"] == 2
    assert stability["out_of_sample_mean"] is not None
    assert stability["out_of_sample_stdev"] is not None
    assert sum(stability["selections"].values()) == 2


# -- what it refuses to claim -----------------------------------------


def test_one_fold_withholds_the_aggregate_and_says_why(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    stability = _walk(client, headers).json()["stability"]

    assert stability["folds"] == 1
    assert stability["refusal"] == "SINGLE_FOLD"
    assert stability["out_of_sample_mean"] is None
    assert stability["selection_rate"] is None


def test_a_window_too_short_names_the_months_it_needed(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    body = _walk(client, headers, end=DAYS[120].isoformat()).json()

    assert body["folds"] == []
    assert body["partition"]["refusal"] == "WINDOW_TOO_SHORT"
    assert body["partition"]["required_months"] == 9
    assert body["partition"]["available_months"] < 9


def test_the_default_scheme_refuses_on_a_year_of_history(client):
    """A year each needs three years — and this universe has 400 days."""
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    body = client.get(
        WALK_FORWARD_URL,
        params={
            "start": DAYS[0].isoformat(),
            "end": DAYS[-1].isoformat(),
            "min_coverage": THIN_COVERAGE,
        },
        headers=headers,
    ).json()

    assert body["settings"]["scheme"] == {"segment_months": 12, "step_months": 12}
    assert body["partition"]["required_months"] == 36
    assert body["partition"]["refusal"] == "WINDOW_TOO_SHORT"


def test_sharpe_without_an_ingested_cdi_leaves_the_fold_unselected(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    body = _walk(client, headers, objective="sharpe").json()

    assert body["settings"]["objective"] == "sharpe"
    fold = body["folds"][0]
    assert fold["selected"] is None
    assert fold["refusal"] == "OBJECTIVE_UNAVAILABLE"
    assert len(fold["trained"]) == 7
    assert body["stability"]["refusal"] == "OBJECTIVE_UNAVAILABLE"


# -- rejections -------------------------------------------------------


def test_an_unknown_strategy_is_refused_by_name(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    response = _walk(client, headers, strategy="momentum")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNKNOWN_STRATEGY"


def test_an_unknown_objective_is_rejected_by_the_schema(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    assert _walk(client, headers, objective="calmar").status_code == 422


def test_an_end_before_its_start_is_refused(client):
    headers = _auth_headers(client)
    _seed_asset(client, headers)

    response = _walk(
        client, headers, end=DAYS[0].isoformat(), start=DAYS[5].isoformat()
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_WINDOW"


def test_an_empty_universe_is_a_404(client):
    headers = _auth_headers(client)

    response = _walk(client, headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EMPTY_UNIVERSE"


def test_the_endpoint_requires_authentication(client):
    response = client.get(WALK_FORWARD_URL, params={"start": DAYS[0].isoformat()})

    assert response.status_code == 401
