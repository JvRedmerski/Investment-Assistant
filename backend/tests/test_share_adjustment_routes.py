"""The share-action fix from the database to the endpoint (W13-001).

The unit tests next door pin the arithmetic. These pin the wiring: that
a `corporate_actions` row with a `share_ratio` actually reaches
`/positions`, and that a cash payout — which changes no share count —
does not.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.data.models.assets import CorporateAction
from app.domain.market_data.corporate_actions import share_adjustments
from tests.conftest import _TestingSessionLocal
from tests.test_scoring_routes import (
    PORTFOLIOS_URL,
    STEADY,
    _auth_headers,
    _buy,
    _portfolio,
    _seed_asset,
)

ASSETS_URL = "/api/v1/assets"


def _today() -> date:
    """Today in UTC, the way the rest of the project reads a clock."""
    return datetime.now(UTC).date()


def _store_action(asset_id: int, ex_day: date, **fields) -> None:
    session = _TestingSessionLocal()
    try:
        session.add(
            CorporateAction(
                asset_id=asset_id,
                ex_date=ex_day,
                last_date_prior=ex_day,
                kind=fields.pop("kind", "SPLIT"),
                label=fields.pop("label", "DESDOBRAMENTO"),
                source="test",
                **fields,
            )
        )
        session.commit()
    finally:
        session.close()


def _positions(client, headers, portfolio_id):
    response = client.get(f"{PORTFOLIOS_URL}/{portfolio_id}/positions", headers=headers)
    assert response.status_code == 200
    return {row["ticker"]: row for row in response.json()["positions"]}


def test_a_stored_split_reaches_the_positions_endpoint(client):
    headers = _auth_headers(client, "sa-split@example.com")
    asset_id = _seed_asset(client, headers, "PETR4", STEADY)
    portfolio_id = _portfolio(client, headers)
    _buy(client, headers, portfolio_id, asset_id, 100, "100")

    before = _positions(client, headers, portfolio_id)["PETR4"]
    assert Decimal(before["quantity"]) == Decimal(100)

    _store_action(asset_id, _today(), share_ratio=Decimal(2))

    after = _positions(client, headers, portfolio_id)["PETR4"]
    assert Decimal(after["quantity"]) == Decimal(200)
    # The money did not move: only the per-share view did.
    assert Decimal(after["invested_amount"]) == Decimal(before["invested_amount"])
    assert Decimal(after["average_price"]) == Decimal(before["average_price"]) / 2


def test_a_cash_payout_leaves_the_share_count_alone(client):
    """It reaches the investor as a DIVIDEND, never as more shares."""
    headers = _auth_headers(client, "sa-cash@example.com")
    asset_id = _seed_asset(client, headers, "PETR4", STEADY)
    portfolio_id = _portfolio(client, headers)
    _buy(client, headers, portfolio_id, asset_id, 100, "100")

    _store_action(
        asset_id,
        _today(),
        kind="DIVIDEND",
        label="DIVIDENDO",
        cash_amount=Decimal("1.50"),
    )

    after = _positions(client, headers, portfolio_id)["PETR4"]
    assert Decimal(after["quantity"]) == Decimal(100)


def test_the_loader_reads_only_ratios_and_respects_as_of(client):
    headers = _auth_headers(client, "sa-loader@example.com")
    asset_id = _seed_asset(client, headers, "PETR4", STEADY)

    _store_action(asset_id, date(2024, 5, 27), share_ratio=Decimal("0.1"))
    _store_action(asset_id, date(2025, 4, 15), share_ratio=Decimal(2))
    _store_action(
        asset_id, date(2025, 6, 1), kind="DIVIDEND", cash_amount=Decimal("1.00")
    )

    session = _TestingSessionLocal()
    try:
        every = share_adjustments(session, [asset_id])
        assert [adjustment.ratio for adjustment in every] == [
            Decimal("0.1"),
            Decimal(2),
        ]

        # Nothing after `as_of`: a position asked for as of a past date is
        # not restated by an event that had not happened yet (rule 108).
        earlier = share_adjustments(session, [asset_id], date(2024, 12, 31))
        assert [adjustment.ex_date for adjustment in earlier] == [date(2024, 5, 27)]

        assert share_adjustments(session, []) == []
    finally:
        session.close()


def test_a_split_lets_the_whole_holding_be_sold(client):
    """The SELL guard has to count the shares actually in custody."""
    headers = _auth_headers(client, "sa-sell@example.com")
    asset_id = _seed_asset(client, headers, "PETR4", STEADY)
    portfolio_id = _portfolio(client, headers)
    _buy(client, headers, portfolio_id, asset_id, 100, "100")
    _store_action(asset_id, _today(), share_ratio=Decimal(2))

    response = client.post(
        f"{PORTFOLIOS_URL}/{portfolio_id}/transactions",
        json={
            "asset_id": asset_id,
            "type": "SELL",
            "quantity": "200",
            "price": "50",
            "transaction_date": datetime.now(UTC).isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 201
