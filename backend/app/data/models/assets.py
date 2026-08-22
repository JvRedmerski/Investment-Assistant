from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.database import Base, utc_now

# See app.data.models.portfolio.MONEY for rationale (AGENTS.md rule 17).
MONEY = Numeric(18, 6)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticker: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # STOCK, FII, ETF, FIXED_INCOME, BDR
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # The CVM files statements by CNPJ and has no ticker column, while the
    # market data vendor knows tickers and exposes the CNPJ on its free
    # profile module. This is where the two are joined, resolved once and
    # kept so a sync does not spend a quota-limited request re-asking.
    # NULL means "not resolved yet" or "no filer" - a BDR or an ETF has
    # none, and never will.
    cnpj: Mapped[str | None] = mapped_column(String(20), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="BRL", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    prices: Mapped[list["AssetPrice"]] = relationship(
        "AssetPrice", back_populates="asset", cascade="all, delete-orphan"
    )
    intraday_prices: Mapped[list["IntradayPrice"]] = relationship(
        "IntradayPrice", back_populates="asset", cascade="all, delete-orphan"
    )
    corporate_actions: Mapped[list["CorporateAction"]] = relationship(
        "CorporateAction", back_populates="asset", cascade="all, delete-orphan"
    )


class CorporateAction(Base):
    """One sized corporate action, as B3's events service published it.

    Stored, unlike `CorporateEvent`, because this is what an adjusted
    price series is rebuilt from and because it comes from a paginated
    remote service rather than a file already on disk — re-fetching a
    decade of payouts on every read would be exactly what rule 23
    forbids.

    Two nullable magnitude columns rather than one, because they are
    different quantities in different units and a single column would
    mean whatever `kind` said it meant — the same conflation that made
    `close` and `adjusted_close` worth separating (ADR-023). Exactly one
    is set on any row; `app.integrations.market_data.schemas.
    CorporateAction` is where that is enforced, before anything reaches
    here.
    """

    __tablename__ = "corporate_actions"
    __table_args__ = (Index("idx_corporate_action_ex_date", "asset_id", "ex_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    # The session the action takes effect on: the first trading session
    # after `last_date_prior`. Resolved against the sessions actually
    # stored for this asset, never from a weekday rule, so a holiday
    # cannot silently move an adjustment onto a day that never traded.
    ex_date: Mapped[date] = mapped_column(Date, nullable=False)
    # What B3 reported: the last session on which buying the paper still
    # earned the right. Kept alongside the resolved date so the source's
    # own statement survives, and so a re-resolution against a longer
    # price history can be checked rather than guessed at.
    last_date_prior: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Reais per share. NULL for an action that moves the share count.
    cash_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    # Shares held after per share held before: 2 for a 1:2 split, 0.1 for
    # a 1:10 reverse split. NULL for a cash payout. Wider scale than
    # MONEY because a ratio is not money and 1/3 bonuses are filed to
    # eleven decimal places.
    share_ratio: Mapped[Decimal | None] = mapped_column(Numeric(24, 12), nullable=True)
    # The source's own label, verbatim (`JRS CAP PROPRIO`, `GRUPAMENTO`).
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    asset: Mapped["Asset"] = relationship("Asset", back_populates="corporate_actions")


class AssetPrice(Base):
    __tablename__ = "asset_prices"
    __table_args__ = (
        UniqueConstraint("asset_id", "date", name="uq_asset_price_date"),
        Index("idx_asset_price_date", "asset_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    high: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    low: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    close: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # NULL means the source that supplied this bar does not publish an
    # adjusted close - B3's COTAHIST prints traded prices and has none.
    # It is never derived from `close`: the two are different quantities
    # (rule 44, ADR-016, ADR-023). Return series are built through
    # `app.domain.market_data.series`, which keeps only adjusted rows.
    adjusted_close: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    volume: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="brapi", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    asset: Mapped["Asset"] = relationship("Asset", back_populates="prices")


class IntradayPrice(Base):
    """One intraday OHLCV bar, keyed by the instant it opens on.

    ## The unique key has three parts, and the window is not one of them

    `(asset_id, timestamp, timeframe)` identifies a bar, so one instant
    at one bar size holds exactly one row. `source_window` records which
    request window produced it and is deliberately **outside** the key:
    admitting it would let the same instant hold two rows, which is
    precisely the mixture ADR-036 exists to prevent. Two windows
    partition a session differently, so a series assembled from both is
    one that never traded.
    """

    __tablename__ = "intraday_prices"
    __table_args__ = (
        UniqueConstraint(
            "asset_id", "timestamp", "timeframe", name="uq_intraday_timestamp_timeframe"
        ),
        Index("idx_intraday_asset_timestamp", "asset_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    # `timestamptz`, unlike every other timestamp in this schema, and the
    # only column where the distinction changes an answer: a daily bar is
    # a `Date` and carries no ambiguity, while a bar stamped 10:15 with
    # no zone could be three different instants (rule 18). Stored in UTC;
    # presentation converts (`intraday_quality.EXCHANGE_TIMEZONE`).
    #
    # SQLite - which the tests use - has no timestamptz and hands back a
    # naive value regardless. The domain layer therefore does not trust
    # the driver to preserve awareness; see `daytrade.service`.
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)  # 1m, 5m, 15m
    # NUMERIC, not FLOAT, per rule 17. Deferred here from migration 002,
    # which named this table explicitly as Wave 15's to convert.
    open: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    high: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    low: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    close: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # Stays FLOAT: a share count is not a monetary value, the same call
    # migration 002 made for `asset_prices.volume`.
    volume: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Which request window the source served this bar under (`5d`,
    # `3mo`, ...). Not provenance trivia: the same instant comes back
    # with different OHLCV depending on it, measured at 0 of 135 bars
    # agreeing between `5d` and `3mo` (ADR-036). Storing it is what lets
    # ingestion refuse to interleave two partitions.
    source_window: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(
        String(50), default="intraday_provider", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    asset: Mapped["Asset"] = relationship("Asset", back_populates="intraday_prices")
