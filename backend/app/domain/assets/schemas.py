from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssetCreate(BaseModel):
    """Payload to register a new asset for tracking.

    Registration here is watch-only bookkeeping (AGENTS.md 1.2): no
    brokerage integration is required or implied. Price history ingestion
    is handled separately by the Market Data integration (Wave 05).
    """

    ticker: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    asset_type: str = Field(min_length=1, max_length=50)
    sector: str | None = Field(default=None, max_length=100)
    currency: str = Field(default="BRL", max_length=10)

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: str
    asset_type: str
    sector: str | None
    currency: str
    is_active: bool
    created_at: datetime
