from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.data.models.portfolio import TransactionTypeEnum

_ASSET_LINKED_TYPES = (
    TransactionTypeEnum.BUY,
    TransactionTypeEnum.SELL,
    TransactionTypeEnum.DIVIDEND,
)


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PortfolioUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PortfolioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    created_at: datetime
    updated_at: datetime


class TransactionCreate(BaseModel):
    """Payload to record a new transaction on a portfolio.

    Convention: the monetary amount of a transaction is always
    ``quantity * price`` (``fees`` is tracked separately and is not part
    of that amount). For BUY/SELL this is the trade value; for DIVIDEND
    it is the total dividend received; for DEPOSIT/WITHDRAWAL it is the
    cash amount moved (by convention record it as quantity=amount,
    price=1).

    ``asset_id`` is required for BUY/SELL/DIVIDEND and must be omitted
    for DEPOSIT/WITHDRAWAL, which are portfolio-level cash flows not
    tied to a specific asset.
    """

    asset_id: int | None = None
    type: TransactionTypeEnum
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(ge=0)
    fees: Decimal = Field(ge=0, default=Decimal(0))
    transaction_date: datetime

    @model_validator(mode="after")
    def _validate_asset_id_matches_type(self) -> "TransactionCreate":
        requires_asset = self.type in _ASSET_LINKED_TYPES
        if requires_asset and self.asset_id is None:
            raise ValueError(
                f"asset_id is required for {self.type.value} transactions."
            )
        if not requires_asset and self.asset_id is not None:
            raise ValueError(
                f"asset_id must not be set for {self.type.value} transactions."
            )
        return self


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    portfolio_id: int
    asset_id: int | None
    type: TransactionTypeEnum
    quantity: Decimal
    price: Decimal
    fees: Decimal
    transaction_date: datetime
    created_at: datetime


class AssetPositionResponse(BaseModel):
    """Consolidated, cost-basis position for a single asset.

    Derived entirely from the transaction ledger (AGENTS.md rule 16 — no
    independently stored quantity/average_price). Does not include
    current market value: that requires price data from the Market Data
    integration (Wave 05), not yet implemented.
    """

    asset_id: int
    ticker: str
    quantity: Decimal
    average_price: Decimal
    invested_amount: Decimal
    realized_pnl: Decimal
    dividends_received: Decimal
    #: Last stored **close** — what the market printed — and the session
    #: it belongs to. Never the adjusted close, which is a total-return
    #: price and would value a long-held position at a fraction of what
    #: the shares would fetch.
    last_price: Decimal | None
    price_date: date | None
    #: `quantity × last_price`, and `null` when no price is stored for
    #: this asset — never a stand-in zero and never the cost basis
    #: wearing a different label (ADR-014).
    market_value: Decimal | None
    unrealised_pnl: Decimal | None


class PortfolioPositionsResponse(BaseModel):
    """Consolidated positions, at cost and at market.

    ⚠️ **`valued_market_value` is not necessarily the whole portfolio.**
    It sums only the positions a stored price could be found for, and it
    is named that way so it cannot be read as a patrimônio. Check
    `unvalued_positions`: while it is above zero, `unvalued_invested`
    says how much cost basis the total leaves out.

    `unrealised_pnl` is `valued_market_value - valued_invested`, both
    over the **same** rows. Comparing the valued total against
    `total_invested` would report a loss made entirely of the positions
    nobody could price.

    `oldest_price_date` and `newest_price_date` bound the prices the
    totals were built from (rules 103/104). Equal dates mean one
    session; far apart means the total mixes a fresh close with a stale
    one, and the difference is the label that says so.
    """

    portfolio_id: int
    positions: list[AssetPositionResponse]
    total_invested: Decimal
    total_realized_pnl: Decimal
    total_dividends_received: Decimal
    net_contributions: Decimal
    valued_market_value: Decimal
    valued_invested: Decimal
    unrealised_pnl: Decimal
    unvalued_positions: int
    unvalued_invested: Decimal
    oldest_price_date: date | None
    newest_price_date: date | None
