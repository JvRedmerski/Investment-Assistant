"""Integration tests for `POST /assets/{ticker}/prices/backfill`.

The historical provider dependency is overridden with a fake, so nothing
downloads a year archive. What is asserted is the contract the route owes
a caller: the same error envelope as `/prices/sync`, unadjusted bars
stored rather than rejected, and the two ingestion paths coexisting on
one table without either clobbering the other (ADR-023).
"""

from datetime import date
from decimal import Decimal

import pytest

from app.api.dependencies import (
    get_historical_price_provider,
    get_market_data_provider,
)
from app.integrations.market_data.base import (
    DailyHistoryProvider,
    MarketDataProvider,
)
from app.integrations.market_data.exceptions import (
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)
from app.integrations.market_data.schemas import DailyBar
from app.main import app

ASSETS_URL = "/api/v1/assets"


class FakeArchive(DailyHistoryProvider):
    """Stands in for COTAHIST: traded prices, no adjustment, deep history."""

    source_name = "b3_cotahist"
    reports_adjusted_close = False

    def __init__(self, bars=None, error=None):
        self._bars = bars or []
        self._error = error

    def get_daily_history(self, ticker, start, end):
        if self._error is not None:
            raise self._error
        return [bar for bar in self._bars if start <= bar.date <= end]


class FakeVendor(MarketDataProvider):
    """Stands in for the vendor: adjusted bars, short window."""

    source_name = "brapi"

    def __init__(self, bars=None):
        self._bars = bars or []

    def get_quote(self, ticker):  # pragma: no cover - unused here
        raise NotImplementedError

    def get_daily_history(self, ticker, start, end):
        return [bar for bar in self._bars if start <= bar.date <= end]


def traded_bar(day: int, close: str) -> DailyBar:
    """A COTAHIST-shaped bar: priced, but with nothing adjusted."""
    return DailyBar(
        date=date(2020, 3, day),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        adjusted_close=None,
        volume=Decimal(1_000_000),
    )


def adjusted_bar(day: int, close: str, adjusted: str) -> DailyBar:
    return DailyBar(
        date=date(2020, 3, day),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        adjusted_close=Decimal(adjusted),
        volume=Decimal(1_000_000),
    )


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.pop(get_historical_price_provider, None)
    app.dependency_overrides.pop(get_market_data_provider, None)


def use_archive(provider: FakeArchive) -> None:
    app.dependency_overrides[get_historical_price_provider] = lambda: provider


def use_vendor(provider: FakeVendor) -> None:
    app.dependency_overrides[get_market_data_provider] = lambda: provider


def auth_headers(client, email="backfill-owner@example.com"):
    password = "SuperSecret123"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def create_asset(client, headers, ticker="PETR4"):
    return client.post(
        ASSETS_URL,
        json={"ticker": ticker, "name": "Petrobras PN", "asset_type": "STOCK"},
        headers=headers,
    ).json()


# -- the contract ------------------------------------------------------


def test_backfill_requires_authentication(client):
    response = client.post(f"{ASSETS_URL}/PETR4/prices/backfill", json={})
    assert response.status_code == 401


def test_backfill_returns_not_found_for_an_unregistered_asset(client):
    headers = auth_headers(client)
    use_archive(FakeArchive(bars=[traded_bar(2, "20.10")]))

    response = client.post(
        f"{ASSETS_URL}/NOPE/prices/backfill", json={}, headers=headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ASSET_NOT_FOUND"


def test_backfill_stores_unadjusted_bars_instead_of_rejecting_them(client):
    headers = auth_headers(client, "backfill-a@example.com")
    create_asset(client, headers, ticker="MGLU3")
    use_archive(FakeArchive(bars=[traded_bar(2, "20.10"), traded_bar(3, "21.40")]))

    response = client.post(
        f"{ASSETS_URL}/MGLU3/prices/backfill",
        json={"start": "2020-01-01", "end": "2020-12-31"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["inserted"] == 2
    assert response.json()["rejected"] == 0


def test_the_read_endpoint_reports_the_absence_rather_than_a_number(client):
    headers = auth_headers(client, "backfill-b@example.com")
    create_asset(client, headers, ticker="VALE3")
    use_archive(FakeArchive(bars=[traded_bar(2, "20.10")]))
    client.post(
        f"{ASSETS_URL}/VALE3/prices/backfill",
        json={"start": "2020-01-01", "end": "2020-12-31"},
        headers=headers,
    )

    prices = client.get(f"{ASSETS_URL}/VALE3/prices", headers=headers).json()

    (row,) = prices
    assert row["close"] == "20.100000"
    assert row["adjusted_close"] is None
    # Which source a row came from is what makes the null interpretable.
    assert row["source"] == "b3_cotahist"


def test_a_window_wider_than_any_vendor_plan_is_accepted(client):
    headers = auth_headers(client, "backfill-c@example.com")
    create_asset(client, headers, ticker="ITUB4")
    use_archive(FakeArchive(bars=[traded_bar(2, "20.10")]))

    response = client.post(
        f"{ASSETS_URL}/ITUB4/prices/backfill",
        json={"start": "2015-01-01", "end": "2020-12-31"},
        headers=headers,
    )

    # Six years. The vendor route would refuse this with
    # MARKET_DATA_WINDOW_TOO_LARGE; the open archive has no such ceiling,
    # which is the whole reason this endpoint exists.
    assert response.status_code == 200


def test_a_future_end_date_is_still_refused(client):
    headers = auth_headers(client, "backfill-d@example.com")
    create_asset(client, headers, ticker="BBAS3")
    use_archive(FakeArchive())

    response = client.post(
        f"{ASSETS_URL}/BBAS3/prices/backfill",
        json={"end": "2999-01-01"},
        headers=headers,
    )

    assert response.status_code == 422


def test_an_inverted_window_is_refused(client):
    headers = auth_headers(client, "backfill-e@example.com")
    create_asset(client, headers, ticker="WEGE3")
    use_archive(FakeArchive())

    response = client.post(
        f"{ASSETS_URL}/WEGE3/prices/backfill",
        json={"start": "2020-12-31", "end": "2020-01-01"},
        headers=headers,
    )

    assert response.status_code == 422


# -- failures translate the same way as the vendor route ---------------


def test_a_ticker_the_archive_never_carried_is_a_404(client):
    headers = auth_headers(client, "backfill-f@example.com")
    create_asset(client, headers, ticker="PETR3")
    use_archive(FakeArchive(error=TickerNotFoundError("no such code")))

    response = client.post(
        f"{ASSETS_URL}/PETR3/prices/backfill", json={}, headers=headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MARKET_DATA_TICKER_NOT_FOUND"


def test_an_unreachable_archive_is_a_503(client):
    headers = auth_headers(client, "backfill-g@example.com")
    create_asset(client, headers, ticker="ABEV3")
    use_archive(FakeArchive(error=MarketDataUnavailableError("b3 is down")))

    response = client.post(
        f"{ASSETS_URL}/ABEV3/prices/backfill", json={}, headers=headers
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MARKET_DATA_UNAVAILABLE"


def test_an_unreadable_archive_is_a_502(client):
    headers = auth_headers(client, "backfill-h@example.com")
    create_asset(client, headers, ticker="BBDC4")
    use_archive(FakeArchive(error=InvalidMarketDataResponseError("not a zip")))

    response = client.post(
        f"{ASSETS_URL}/BBDC4/prices/backfill", json={}, headers=headers
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MARKET_DATA_INVALID_RESPONSE"


# -- the two sources sharing one table ---------------------------------


def test_the_vendor_does_not_overwrite_a_date_the_archive_already_filled(client):
    headers = auth_headers(client, "backfill-i@example.com")
    create_asset(client, headers, ticker="EGIE3")
    use_archive(FakeArchive(bars=[traded_bar(2, "20.10")]))
    client.post(
        f"{ASSETS_URL}/EGIE3/prices/backfill",
        json={"start": "2020-01-01", "end": "2020-12-31"},
        headers=headers,
    )

    use_vendor(FakeVendor(bars=[adjusted_bar(2, "20.10", "19.80")]))
    second = client.post(
        f"{ASSETS_URL}/EGIE3/prices/sync",
        json={"start": "2020-01-01", "end": "2020-12-31"},
        headers=headers,
    )

    # A stored date is never rewritten, whichever source comes second.
    # The consequence is worth naming: a date first filled from the open
    # archive keeps its NULL adjusted close even when the vendor could
    # have supplied one.
    assert second.json()["inserted"] == 0
    assert second.json()["skipped_existing"] == 1
    (row,) = client.get(f"{ASSETS_URL}/EGIE3/prices", headers=headers).json()
    assert row["adjusted_close"] is None
    assert row["source"] == "b3_cotahist"


def test_the_archive_fills_only_the_dates_the_vendor_did_not_reach(client):
    headers = auth_headers(client, "backfill-j@example.com")
    create_asset(client, headers, ticker="TAEE11")
    use_vendor(FakeVendor(bars=[adjusted_bar(3, "21.40", "21.00")]))
    client.post(
        f"{ASSETS_URL}/TAEE11/prices/sync",
        json={"start": "2020-01-01", "end": "2020-12-31"},
        headers=headers,
    )

    use_archive(FakeArchive(bars=[traded_bar(2, "20.10"), traded_bar(3, "21.40")]))
    response = client.post(
        f"{ASSETS_URL}/TAEE11/prices/backfill",
        json={"start": "2020-01-01", "end": "2020-12-31"},
        headers=headers,
    )

    assert response.json()["inserted"] == 1
    assert response.json()["skipped_existing"] == 1
    rows = client.get(f"{ASSETS_URL}/TAEE11/prices", headers=headers).json()
    by_date = {row["date"]: row for row in rows}
    # The vendor's adjusted day survives untouched; the archive only adds
    # the day the vendor's window never covered.
    assert by_date["2020-03-03"]["adjusted_close"] == "21.000000"
    assert by_date["2020-03-02"]["adjusted_close"] is None
