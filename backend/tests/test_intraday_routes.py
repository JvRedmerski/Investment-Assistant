"""Integration tests for the intraday sync/read endpoints (W15-005).

`get_intraday_provider` is overridden with a fake, so nothing reaches the
network - which matters more on this path than on the daily one: the real
source serves intraday for only some tickers, and a test that depended on
which would be a test of the vendor's plan.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.api.dependencies import get_intraday_provider
from app.integrations.market_data.base import IntradayHistory, IntradayHistoryProvider
from app.integrations.market_data.exceptions import (
    IntradayNotAvailableError,
    MarketDataUnavailableError,
)
from app.integrations.market_data.schemas import (
    HistoryWindow,
    IntradayBar,
    Timeframe,
)
from app.main import app

ASSETS_URL = "/api/v1/assets"
_15M = Timeframe.FIFTEEN_MINUTES


class FakeIntradayProvider(IntradayHistoryProvider):
    source_name = "fake"

    def __init__(self, bars=None, window=HistoryWindow.FIVE_DAYS, error=None):
        self._bars = bars or []
        self._window = window
        self._error = error

    def get_intraday_history(self, ticker, timeframe, start, end):
        if self._error is not None:
            raise self._error
        return IntradayHistory(
            timeframe=timeframe,
            window=self._window,
            bars=[b for b in self._bars if start <= b.timestamp <= end],
        )


def _bar(minutes_ago: int, close: str = "42.00") -> IntradayBar:
    """A bar inside the last day, so the route's `days` window contains it."""
    price = Decimal(close)
    moment = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).replace(
        second=0, microsecond=0
    )
    return IntradayBar(
        timestamp=moment,
        timeframe=_15M,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal(1000),
    )


@pytest.fixture(autouse=True)
def _reset_provider_override():
    yield
    app.dependency_overrides.pop(get_intraday_provider, None)


def _override(provider: FakeIntradayProvider) -> None:
    app.dependency_overrides[get_intraday_provider] = lambda: provider


def _auth_headers(client, email="intraday-owner@example.com"):
    password = "SuperSecret123"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _create_asset(client, headers, ticker="PETR4"):
    client.post(
        ASSETS_URL,
        json={"ticker": ticker, "name": "Petrobras PN", "asset_type": "STOCK"},
        headers=headers,
    )


class TestAuthAndLookup:
    def test_sync_requires_authentication(self, client):
        assert client.post(f"{ASSETS_URL}/PETR4/intraday/sync").status_code == 401

    def test_read_requires_authentication(self, client):
        assert client.get(f"{ASSETS_URL}/PETR4/intraday").status_code == 401

    def test_an_unregistered_asset_is_a_404(self, client):
        headers = _auth_headers(client, "intraday-a@example.com")
        _override(FakeIntradayProvider(bars=[_bar(30)]))

        response = client.post(f"{ASSETS_URL}/NOPE/intraday/sync", headers=headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ASSET_NOT_FOUND"


class TestSyncAndRead:
    def test_bars_are_ingested_and_read_back_without_a_second_call(self, client):
        headers = _auth_headers(client, "intraday-b@example.com")
        _create_asset(client, headers, "PETR4")
        _override(FakeIntradayProvider(bars=[_bar(30), _bar(45)]))

        response = client.post(
            f"{ASSETS_URL}/PETR4/intraday/sync?timeframe=15m&days=1", headers=headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["fetched"] == 2
        assert body["inserted"] == 2
        assert body["window"] == "5d"
        assert body["timeframe"] == "15m"
        assert body["conflicts"] == []

        # A provider that would blow up if the read path called it.
        _override(
            FakeIntradayProvider(error=MarketDataUnavailableError("must not be called"))
        )
        read = client.get(
            f"{ASSETS_URL}/PETR4/intraday?timeframe=15m&days=1", headers=headers
        )
        assert read.status_code == 200
        assert len(read.json()) == 2
        assert read.json()[0]["source_window"] == "5d"

    def test_the_response_reports_session_coverage(self, client):
        headers = _auth_headers(client, "intraday-c@example.com")
        _create_asset(client, headers, "VALE3")
        _override(FakeIntradayProvider(bars=[_bar(30), _bar(45)]))

        body = client.post(
            f"{ASSETS_URL}/VALE3/intraday/sync?days=1", headers=headers
        ).json()
        assert len(body["sessions"]) >= 1
        assert body["sessions"][0]["bar_count"] >= 1

    def test_a_second_sync_stores_nothing_new(self, client):
        headers = _auth_headers(client, "intraday-d@example.com")
        _create_asset(client, headers, "ITUB4")
        _override(FakeIntradayProvider(bars=[_bar(30)]))

        client.post(f"{ASSETS_URL}/ITUB4/intraday/sync?days=1", headers=headers)
        body = client.post(
            f"{ASSETS_URL}/ITUB4/intraday/sync?days=1", headers=headers
        ).json()

        assert body["inserted"] == 0
        assert body["skipped_existing"] == 1

    def test_an_unknown_timeframe_is_rejected_by_the_contract(self, client):
        headers = _auth_headers(client, "intraday-e@example.com")
        _create_asset(client, headers, "MGLU3")
        _override(FakeIntradayProvider(bars=[_bar(30)]))

        response = client.post(
            f"{ASSETS_URL}/MGLU3/intraday/sync?timeframe=30m", headers=headers
        )
        assert response.status_code == 422


class TestTheWindowConflictReachesTheCaller:
    def test_a_conflict_is_reported_on_an_otherwise_successful_sync(self, client):
        headers = _auth_headers(client, "intraday-f@example.com")
        _create_asset(client, headers, "BBDC4")

        _override(FakeIntradayProvider(bars=[_bar(30)], window=HistoryWindow.FIVE_DAYS))
        client.post(f"{ASSETS_URL}/BBDC4/intraday/sync?days=1", headers=headers)

        _override(
            FakeIntradayProvider(
                bars=[_bar(30, close="43.07")], window=HistoryWindow.THREE_MONTHS
            )
        )
        response = client.post(
            f"{ASSETS_URL}/BBDC4/intraday/sync?days=1", headers=headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["inserted"] == 0
        assert len(body["conflicts"]) == 1
        assert body["conflicts"][0]["stored_window"] == "5d"
        assert body["conflicts"][0]["incoming_window"] == "3mo"

    def test_resync_replaces_it(self, client):
        headers = _auth_headers(client, "intraday-g@example.com")
        _create_asset(client, headers, "WEGE3")

        _override(FakeIntradayProvider(bars=[_bar(30)]))
        client.post(f"{ASSETS_URL}/WEGE3/intraday/sync?days=1", headers=headers)

        _override(
            FakeIntradayProvider(
                bars=[_bar(30, close="43.07")], window=HistoryWindow.THREE_MONTHS
            )
        )
        body = client.post(
            f"{ASSETS_URL}/WEGE3/intraday/sync?days=1&resync=true", headers=headers
        ).json()

        assert body["conflicts"] == []
        assert body["replaced"] == 1
        assert body["inserted"] == 1

        read = client.get(f"{ASSETS_URL}/WEGE3/intraday?days=1", headers=headers)
        assert read.json()[0]["source_window"] == "3mo"


class TestErrorTranslation:
    def test_the_plan_refusal_is_a_400_that_names_itself(self, client):
        """Not a 503: "currently unavailable" would send a caller back to
        retry forever against a per-ticker limit that will not lift."""
        headers = _auth_headers(client, "intraday-h@example.com")
        _create_asset(client, headers, "BBAS3")
        _override(
            FakeIntradayProvider(
                error=IntradayNotAvailableError("plan does not cover this ticker")
            )
        )

        response = client.post(f"{ASSETS_URL}/BBAS3/intraday/sync", headers=headers)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INTRADAY_NOT_AVAILABLE"
        assert "BBAS3" in response.json()["error"]["message"]

    def test_a_genuine_outage_is_still_a_503(self, client):
        headers = _auth_headers(client, "intraday-i@example.com")
        _create_asset(client, headers, "PRIO3")
        _override(FakeIntradayProvider(error=MarketDataUnavailableError("down")))

        response = client.post(f"{ASSETS_URL}/PRIO3/intraday/sync", headers=headers)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "MARKET_DATA_UNAVAILABLE"
