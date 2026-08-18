"""Ticker-to-CNPJ resolution backed by what is already stored.

`app.integrations.fundamentals.identity` knows how to *ask* the market
data vendor for a company's CNPJ. This decides whether the question needs
asking at all.

A CNPJ does not change, and asking costs a request against a
quota-limited plan, so the first successful answer is written to
`assets.cnpj` and every later sync reads it from there. Twenty tracked
assets cost twenty lookups once, not twenty per sync.

Writing during resolution is a side effect, and it is confined to the
ingestion path — the only path already permitted to call an external
source (rule 23). Nothing on a read path resolves.
"""

import logging

from sqlalchemy.orm import Session

from app.data.models.assets import Asset
from app.integrations.fundamentals.cvm import CnpjResolver

logger = logging.getLogger("investment_assistant.fundamentals.identity")


class StoredCnpjResolver:
    """`assets.cnpj` first, the vendor second, and remember the answer."""

    def __init__(self, db: Session, fallback: CnpjResolver) -> None:
        self._db = db
        self._fallback = fallback

    def __call__(self, ticker: str) -> str | None:
        asset = (
            self._db.query(Asset).filter(Asset.ticker == ticker.strip().upper()).first()
        )
        if asset is not None and asset.cnpj:
            return asset.cnpj

        cnpj = self._fallback(ticker)
        if cnpj is None:
            # Not persisted as a negative result: an asset can be
            # registered before the vendor knows it, and caching "no"
            # would make that permanent with nothing to show why.
            return None

        if asset is not None:
            asset.cnpj = cnpj
            self._db.commit()
            logger.info("Resolved %s to CNPJ %s and stored it.", ticker, cnpj)
        return cnpj
