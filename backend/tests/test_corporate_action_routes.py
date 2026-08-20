"""Integration tests for the corporate action sync and its read path.

Both providers are overridden with fakes, so nothing opens an archive or
reaches B3. What is asserted is the contract the route owes a caller:
that ex-dates land on sessions that actually traded, that an adjusted
close already present is never rewritten, and that the reason a series
stops where it does comes back in the response rather than only in a log.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.api.dependencies import (
    get_corporate_action_provider,
    get_corporate_event_provider,
)
from app.data.models.assets import Asset, AssetPrice
from app.integrations.market_data.base import (
    CorporateActionProvider,
    CorporateEventProvider,
)
from app.integrations.market_data.exceptions import (
    MarketDataUnavailableError,
    TickerNotFoundError,
)
from app.integrations.market_data.schemas import (
    CorporateAction,
    CorporateActionKind,
    CorporateEvent,
    CorporateEventKind,
    SecurityIdentity,
)
from app.main import app
from tests.conftest import _TestingSessionLocal

ASSETS_URL = "/api/v1/assets"


class FakeArchive(CorporateEventProvider):
    """Stands in for COTAHIST: it dates events and identifies the paper."""

    def __init__(self, events=None, identity=None, error=None):
        self._events = events or []
        self._identity = identity or SecurityIdentity(
            ticker="BBAS3", isin="BRBBASACNOR3", share_class="ON"
        )
        self._error = error

    def get_corporate_events(self, ticker, start, end):
        if self._error is not None:
            raise self._error
        return [e for e in self._events if start <= e.date <= end]

    def get_security_identity(self, ticker, start, end):
        if self._error is not None:
            raise self._error
        return self._identity


class FakeEvents(CorporateActionProvider):
    """Stands in for B3's corporate-events service: magnitudes only."""

    source_name = "b3_corporate_events"

    def __init__(self, actions=None, error=None):
        self._actions = actions or []
        self._error = error
        self.asked_for: list[SecurityIdentity] = []

    def get_corporate_actions(self, security, start, end):
        if self._error is not None:
            raise self._error
        self.asked_for.append(security)
        return [a for a in self._actions if start <= a.last_date_prior <= end]


def auth_headers(client, email="actions-owner@example.com"):
    password = "SecurePass123"
    client.post("/api/v1/auth/register", json={"email": email, "password": password})
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def seed(ticker: str, closes: dict[date, str], adjusted: dict[date, str] | None = None):
    """An asset with raw closes already stored, as a backfill would leave it."""
    adjusted = adjusted or {}
    db = _TestingSessionLocal()
    try:
        asset = Asset(ticker=ticker, name=ticker, asset_type="STOCK")
        db.add(asset)
        db.flush()
        for day, close in closes.items():
            value = Decimal(close)
            db.add(
                AssetPrice(
                    asset_id=asset.id,
                    date=day,
                    open=value,
                    high=value,
                    low=value,
                    close=value,
                    adjusted_close=(
                        Decimal(adjusted[day]) if day in adjusted else None
                    ),
                    volume=1000.0,
                    source="brapi" if day in adjusted else "b3_cotahist",
                )
            )
        db.commit()
        return asset.id
    finally:
        db.close()


def use(archive: FakeArchive, events: FakeEvents):
    app.dependency_overrides[get_corporate_event_provider] = lambda: archive
    app.dependency_overrides[get_corporate_action_provider] = lambda: events


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_corporate_event_provider, None)
    app.dependency_overrides.pop(get_corporate_action_provider, None)


# -- the real BBAS3 split, end to end ----------------------------------

BBAS_CLOSES = {
    date(2024, 4, 12): "55.90",
    date(2024, 4, 15): "56.46",
    date(2024, 4, 16): "27.91",
    date(2024, 4, 17): "28.10",
}

BBAS_SPLIT = CorporateAction(
    last_date_prior=date(2024, 4, 15),
    kind=CorporateActionKind.SPLIT,
    share_ratio=Decimal(2),
    label="DESDOBRAMENTO",
)


def test_a_sync_sizes_the_split_and_fills_the_adjusted_closes(client):
    seed("BBAS3", BBAS_CLOSES)
    use(
        FakeArchive(
            events=[
                CorporateEvent(
                    date=date(2024, 4, 16),
                    kind=CorporateEventKind.BONUS_OR_SPLIT,
                    specification="ON  EB  NM",
                    distribution_number=323,
                )
            ]
        ),
        FakeEvents(actions=[BBAS_SPLIT]),
    )
    headers = auth_headers(client)

    response = client.post(
        f"{ASSETS_URL}/BBAS3/corporate-actions/sync",
        json={"start": "2024-01-01", "end": "2024-12-31"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["inserted"] == 1
    assert body["unaccounted"] == []
    assert body["adjusted_written"] == 4
    assert body["first_adjustable"] == "2024-04-12"

    prices = client.get(f"{ASSETS_URL}/BBAS3/prices", headers=headers).json()
    by_date = {p["date"]: p["adjusted_close"] for p in prices}
    # 56.46 halved lands on the 27.91 that actually printed.
    assert Decimal(by_date["2024-04-15"]) == Decimal("28.230000")
    assert Decimal(by_date["2024-04-16"]) == Decimal("27.910000")


def test_the_ex_date_is_the_next_session_that_actually_traded(client):
    """The service publishes the last date *with* the right, and
    2024-04-15 was a Monday: the ex-date is the Tuesday that followed,
    resolved from the stored sessions rather than by adding a day."""
    seed("BBAS3", BBAS_CLOSES)
    use(FakeArchive(), FakeEvents(actions=[BBAS_SPLIT]))
    headers = auth_headers(client, "actions-exdate@example.com")

    client.post(f"{ASSETS_URL}/BBAS3/corporate-actions/sync", json={}, headers=headers)
    stored = client.get(f"{ASSETS_URL}/BBAS3/corporate-actions", headers=headers).json()

    assert len(stored) == 1
    assert stored[0]["last_date_prior"] == "2024-04-15"
    assert stored[0]["ex_date"] == "2024-04-16"
    assert stored[0]["source"] == "b3_corporate_events"


def test_an_action_over_a_market_holiday_lands_on_the_next_open_session(client):
    """2025-04-18 was Good Friday; the session after 2025-04-17 is the
    Monday. A weekday rule would have pinned the adjustment to a date
    with no bar, where nothing would ever apply it."""
    seed(
        "BBAS3",
        {
            date(2025, 4, 16): "20.00",
            date(2025, 4, 17): "20.00",
            date(2025, 4, 21): "19.50",
        },
    )
    use(
        FakeArchive(),
        FakeEvents(
            actions=[
                CorporateAction(
                    last_date_prior=date(2025, 4, 17),
                    kind=CorporateActionKind.CASH_DIVIDEND,
                    cash_amount=Decimal("0.50"),
                    label="DIVIDENDO",
                )
            ]
        ),
    )
    headers = auth_headers(client, "actions-holiday@example.com")

    client.post(f"{ASSETS_URL}/BBAS3/corporate-actions/sync", json={}, headers=headers)
    stored = client.get(f"{ASSETS_URL}/BBAS3/corporate-actions", headers=headers).json()

    assert stored[0]["ex_date"] == "2025-04-21"


def test_an_adjusted_close_already_stored_is_never_rewritten(client):
    """A vendor bar carries the vendor's own restatement. Replacing it
    here would blend two adjustments into one series (ADR-020/ADR-024)."""
    seed(
        "BBAS3",
        BBAS_CLOSES,
        adjusted={date(2024, 4, 17): "99.999999"},
    )
    use(FakeArchive(), FakeEvents(actions=[BBAS_SPLIT]))
    headers = auth_headers(client, "actions-nowrite@example.com")

    response = client.post(
        f"{ASSETS_URL}/BBAS3/corporate-actions/sync", json={}, headers=headers
    )

    assert response.json()["adjusted_written"] == 3
    prices = client.get(f"{ASSETS_URL}/BBAS3/prices", headers=headers).json()
    kept = {p["date"]: p["adjusted_close"] for p in prices}["2024-04-17"]
    assert Decimal(kept) == Decimal("99.999999")


def test_a_counted_session_nobody_sized_is_named_in_the_response(client):
    """ITUB4's 2025-03-18 — the case that makes the check necessary."""
    seed(
        "ITUB4",
        {
            date(2025, 3, 17): "35.34",
            date(2025, 3, 18): "32.30",
            date(2025, 3, 19): "32.38",
        },
    )
    use(
        FakeArchive(
            events=[
                CorporateEvent(
                    date=date(2025, 3, 18),
                    kind=CorporateEventKind.BONUS_OR_SPLIT,
                    specification="PN  EB  N1",
                    distribution_number=350,
                )
            ],
            identity=SecurityIdentity(
                ticker="ITUB4", isin="BRITUBACNPR1", share_class="PN"
            ),
        ),
        FakeEvents(actions=[]),
    )
    headers = auth_headers(client, "actions-gap@example.com")

    body = client.post(
        f"{ASSETS_URL}/ITUB4/corporate-actions/sync", json={}, headers=headers
    ).json()

    assert body["unaccounted"] == ["2025-03-18"]
    assert body["first_adjustable"] == "2025-03-19"
    assert body["adjusted_written"] == 1


def test_a_second_sync_inserts_nothing_and_stays_idempotent(client):
    seed("BBAS3", BBAS_CLOSES)
    use(FakeArchive(), FakeEvents(actions=[BBAS_SPLIT]))
    headers = auth_headers(client, "actions-idem@example.com")

    first = client.post(
        f"{ASSETS_URL}/BBAS3/corporate-actions/sync", json={}, headers=headers
    ).json()
    second = client.post(
        f"{ASSETS_URL}/BBAS3/corporate-actions/sync", json={}, headers=headers
    ).json()

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["skipped_existing"] == 1
    # The second run rewrites nothing, because the first already filled it.
    assert second["adjusted_written"] == 0


def test_an_action_newer_than_the_stored_prices_is_left_unplaced(client):
    seed("BBAS3", {date(2024, 4, 12): "55.90", date(2024, 4, 15): "56.46"})
    use(
        FakeArchive(),
        FakeEvents(
            actions=[
                CorporateAction(
                    last_date_prior=date(2026, 6, 1),
                    kind=CorporateActionKind.INTEREST_ON_CAPITAL,
                    cash_amount=Decimal("0.35048636"),
                    label="JRS CAP PROPRIO",
                )
            ]
        ),
    )
    headers = auth_headers(client, "actions-unplaced@example.com")

    body = client.post(
        f"{ASSETS_URL}/BBAS3/corporate-actions/sync", json={}, headers=headers
    ).json()

    assert body["unplaced"] == 1
    assert body["inserted"] == 0


def test_the_events_service_is_asked_about_the_isin_the_archive_printed(client):
    seed("BBAS3", BBAS_CLOSES)
    events = FakeEvents(actions=[BBAS_SPLIT])
    use(FakeArchive(), events)
    headers = auth_headers(client, "actions-isin@example.com")

    client.post(f"{ASSETS_URL}/BBAS3/corporate-actions/sync", json={}, headers=headers)

    assert events.asked_for[0].isin == "BRBBASACNOR3"
    assert events.asked_for[0].share_class == "ON"


# -- the error envelope ------------------------------------------------


def test_an_unregistered_asset_is_not_found(client):
    use(FakeArchive(), FakeEvents())
    headers = auth_headers(client, "actions-404@example.com")

    response = client.post(
        f"{ASSETS_URL}/NOPE3/corporate-actions/sync", json={}, headers=headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ASSET_NOT_FOUND"


def test_a_source_outage_uses_the_shared_error_envelope(client):
    seed("BBAS3", BBAS_CLOSES)
    use(FakeArchive(), FakeEvents(error=MarketDataUnavailableError("down")))
    headers = auth_headers(client, "actions-502@example.com")

    response = client.post(
        f"{ASSETS_URL}/BBAS3/corporate-actions/sync", json={}, headers=headers
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MARKET_DATA_UNAVAILABLE"


def test_a_ticker_the_archive_does_not_carry_is_reported(client):
    seed("BBAS3", BBAS_CLOSES)
    use(FakeArchive(error=TickerNotFoundError("no such paper")), FakeEvents())
    headers = auth_headers(client, "actions-notfound@example.com")

    response = client.post(
        f"{ASSETS_URL}/BBAS3/corporate-actions/sync", json={}, headers=headers
    )

    assert response.status_code == 404


def test_the_read_path_requires_authentication(client):
    seed("BBAS3", BBAS_CLOSES)

    assert client.get(f"{ASSETS_URL}/BBAS3/corporate-actions").status_code == 401


def test_the_read_path_never_calls_the_service(client):
    """Rule 23: opening a page must not spend a request."""
    seed("BBAS3", BBAS_CLOSES)
    events = FakeEvents(actions=[BBAS_SPLIT])
    use(FakeArchive(), events)
    headers = auth_headers(client, "actions-read@example.com")

    client.get(f"{ASSETS_URL}/BBAS3/corporate-actions", headers=headers)

    assert events.asked_for == []


def test_an_end_date_in_the_future_is_rejected(client):
    seed("BBAS3", BBAS_CLOSES)
    use(FakeArchive(), FakeEvents())
    headers = auth_headers(client, "actions-future@example.com")

    response = client.post(
        f"{ASSETS_URL}/BBAS3/corporate-actions/sync",
        json={"end": "2099-01-01"},
        headers=headers,
    )

    assert response.status_code == 422
