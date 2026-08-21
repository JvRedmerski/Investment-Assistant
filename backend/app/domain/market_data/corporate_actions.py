"""Ingesting sized corporate actions, and deriving the adjusted close.

Two steps that belong together because the second is the only reason the
first exists: store what B3's events service published about an asset,
then rebuild `asset_prices.adjusted_close` from the raw closes already in
the database. No price is re-fetched — the arithmetic runs against rows
that a backfill already stored (rule 23).

## Where the ex-date comes from

The service publishes the **last date prior**: the final session on which
buying the paper still earned the right. The action takes effect on the
next trading session, and "next trading session" is resolved against the
sessions actually stored for this asset rather than by adding a day and
skipping weekends. A holiday would otherwise move an adjustment onto a
date that never traded, where nothing would ever apply it.

An action whose last date prior falls outside the stored price range is
left unplaced instead of being pinned to the nearest edge: too recent and
there is no session yet to be ex on; older than the first stored session
and there is nothing before it to restate.

## Nothing already written is overwritten

`adjusted_close` is filled only where it is `NULL`. A row that came from
the vendor already carries the vendor's own adjustment, and replacing it
with one derived here would silently mix two different restatements into
one series — the field-by-field merge ADR-020 rejected. Filling only the
empty column is the same rule ADR-024 set for statement columns, applied
to the same problem.

Actions themselves are inserted, never updated, matching how
`sync_daily_history` treats a date it already holds.
"""

import logging
from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.data.models.assets import Asset, AssetPrice
from app.data.models.assets import CorporateAction as StoredAction
from app.domain.market_data.adjustment import adjusted_closes
from app.domain.portfolio.service import ShareAdjustment
from app.integrations.market_data.base import (
    CorporateActionProvider,
    CorporateEventProvider,
)

logger = logging.getLogger("investment_assistant.market_data.corporate_actions")


@dataclass
class CorporateActionSyncResult:
    """What a sync stored, and what it still cannot answer.

    The three absence counts are the point of the response, not a
    footnote: they are what turns "this asset has no risk metrics" from a
    mystery into a named, dated gap.
    """

    ticker: str
    start: date
    end: date
    fetched: int
    inserted: int
    skipped_existing: int
    #: Reported by the service but not placeable on a stored session.
    unplaced: int
    #: Sessions the archive counted ex that no action accounts for. The
    #: most recent one is what bounds the adjusted series.
    unaccounted: list[date] = field(default_factory=list)
    #: Sessions carrying an action that cannot be expressed as a factor.
    unusable: list[date] = field(default_factory=list)
    #: Rows whose `adjusted_close` this run filled in.
    adjusted_written: int = 0
    first_adjustable: date | None = None
    last_adjustable: date | None = None


def sync_corporate_actions(
    db: Session,
    event_provider: CorporateEventProvider,
    action_provider: CorporateActionProvider,
    asset: Asset,
    start: date,
    end: date,
) -> CorporateActionSyncResult:
    """Store `asset`'s sized actions for [start, end] and rebuild its
    adjusted closes.

    Takes both providers because neither answers the whole question: the
    archive says which security this is and which sessions went ex, the
    events service says how large each action was, and the completeness
    check needs both to disagree out loud rather than quietly (ADR-026).
    """
    identity = event_provider.get_security_identity(asset.ticker, start, end)
    fetched = action_provider.get_corporate_actions(identity, start, end)

    bars = (
        db.query(AssetPrice)
        .filter(AssetPrice.asset_id == asset.id)
        .order_by(AssetPrice.date)
        .all()
    )
    sessions = [bar.date for bar in bars]

    existing = {
        (row.ex_date, row.kind, row.cash_amount, row.share_ratio, row.label)
        for row in db.query(StoredAction).filter(StoredAction.asset_id == asset.id)
    }

    inserted = skipped = unplaced = 0
    for action in fetched:
        ex_date = _first_session_after(sessions, action.last_date_prior)
        if ex_date is None:
            unplaced += 1
            logger.info(
                "%s: %s on %s has no stored session to go ex on; left unplaced.",
                asset.ticker,
                action.label,
                action.last_date_prior,
            )
            continue

        key = (
            ex_date,
            action.kind.value,
            action.cash_amount,
            action.share_ratio,
            action.label,
        )
        if key in existing:
            skipped += 1
            continue
        existing.add(key)

        db.add(
            StoredAction(
                asset_id=asset.id,
                ex_date=ex_date,
                last_date_prior=action.last_date_prior,
                kind=action.kind.value,
                cash_amount=action.cash_amount,
                share_ratio=action.share_ratio,
                label=action.label,
                source=action_provider.source_name,
            )
        )
        inserted += 1

    db.flush()

    result = CorporateActionSyncResult(
        ticker=asset.ticker,
        start=start,
        end=end,
        fetched=len(fetched),
        inserted=inserted,
        skipped_existing=skipped,
        unplaced=unplaced,
    )

    _rebuild_adjusted_closes(db, event_provider, asset, bars, result)
    db.commit()
    return result


def _rebuild_adjusted_closes(
    db: Session,
    event_provider: CorporateEventProvider,
    asset: Asset,
    bars: list[AssetPrice],
    result: CorporateActionSyncResult,
) -> None:
    """Derive and store the adjusted closes the stored actions support."""
    if not bars:
        return

    # The whole stored range, not the sync window: an event in 2021 bounds
    # a series that reaches 2020 whether or not this call asked about
    # 2021.
    events = event_provider.get_corporate_events(
        asset.ticker, bars[0].date, bars[-1].date
    )
    actions = (
        db.query(StoredAction)
        .filter(StoredAction.asset_id == asset.id)
        .order_by(StoredAction.ex_date)
        .all()
    )

    outcome = adjusted_closes(bars, actions, events)
    result.unaccounted = outcome.unaccounted
    result.unusable = outcome.unusable
    result.first_adjustable = outcome.first_adjustable
    result.last_adjustable = outcome.last_adjustable

    written = 0
    for bar in bars:
        value = outcome.adjusted.get(bar.date)
        # Only ever fills the empty column; see the module docstring.
        if value is None or bar.adjusted_close is not None:
            continue
        bar.adjusted_close = value
        written += 1
    result.adjusted_written = written

    if outcome.unaccounted:
        logger.info(
            "%s: %s counted session(s) have no sized action; the adjusted series "
            "starts at %s. Most recent gap: %s.",
            asset.ticker,
            len(outcome.unaccounted),
            outcome.first_adjustable,
            outcome.unaccounted[-1],
        )


def _first_session_after(sessions: list[date], when: date) -> date | None:
    """The first stored session strictly after `when`.

    `None` when the action cannot be placed: either every stored session
    is at or before `when` (the ex-date has not been stored yet), or
    `when` precedes the first stored session entirely (the event is older
    than the price history, so nothing here needs restating).
    """
    if not sessions or when < sessions[0]:
        return None
    index = bisect_right(sessions, when)
    return sessions[index] if index < len(sessions) else None


def share_adjustments(
    db: Session,
    asset_ids: Iterable[int],
    as_of: date | None = None,
) -> list[ShareAdjustment]:
    """Every stored share action for `asset_ids`, oldest first.

    Only rows that carry a `share_ratio`: a cash payout leaves the share
    count alone, and it reaches the investor through the DIVIDEND side of
    the ledger rather than by changing a holding.

    Feeds `portfolio.service.compute_positions` and the two curves in
    `portfolio.performance`, which cannot know a holding moved unless
    somebody tells them (W13-001). Nothing after `as_of` is read, so a
    position asked for as of a past date is not restated by an event that
    had not happened yet (rule 108).
    """
    ids = list(asset_ids)
    if not ids:
        return []

    query = db.query(StoredAction).filter(
        StoredAction.asset_id.in_(ids),
        StoredAction.share_ratio.is_not(None),
    )
    if as_of is not None:
        query = query.filter(StoredAction.ex_date <= as_of)

    return [
        ShareAdjustment(
            asset_id=action.asset_id,
            ex_date=action.ex_date,
            ratio=action.share_ratio,
            label=action.label,
        )
        for action in query.order_by(StoredAction.ex_date, StoredAction.id)
    ]
