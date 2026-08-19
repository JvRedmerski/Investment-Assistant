"""`DailyHistoryProvider` backed by B3's open COTAHIST series.

https://bvmf.bmfbovespa.com.br/InstDados/SerHist/

This is the **open** price history: the exchange's own end-of-day file,
free, with no token and no quota, reaching back decades. It exists for
the same reason the CVM provider does (ADR-020) — the vendor's free plan
caps history at a `3mo` range anchored at today, roughly 63 sessions,
which is not enough to price a past fiscal year end, to measure risk, or
to backtest anything.

Every detail below was verified against the real file for 2026-08-18
before a single fixture was written.

## What the source actually is

Not an API. One ZIP per calendar year (`COTAHIST_A2024.ZIP`, ~79 MB)
holding a single fixed-width text file, 245 bytes per record, latin-1,
`\\r\\n`-terminated, covering **every instrument B3 lists** — there is no
way to ask for one ticker. Monthly (`_M`) and daily (`_D`) files exist in
the same layout; only the annual one is used, because a per-ticker
backfill of years would otherwise need hundreds of requests.

Record types are `00` header, `01` detail, `99` trailer.

## The two filters that decide what a bar means

- **`TPMERC` must be `010`** (mercado à vista). The same `CODNEG` also
  appears under term, forward and options markets, whose prices are for
  a different contract entirely. In the 2026-08-18 file the spot market
  is 1,424 of 18,332 records — options are 89% of the archive, and this
  project has no consumer for them.
- **`TIPREG` must be `01`**. Header and trailer share the record width
  and would otherwise parse as garbage.

## Prices, and the two scales the file applies

The five price fields are 13 digits with two **implied** decimals, so
`0000000004260` is R$ 42.60. There is no decimal point in the file.

`FATCOT` is the **quotation factor**: `1` when the price quoted is for
one share, `1000` when it is for a lot of a thousand — which B3 uses for
papers that would otherwise trade at fractions of a cent. Prices here are
divided by it, so a bar always means *one share*. Getting this wrong
would misprice such a paper by exactly a thousand, the same failure mode
the CVM share counts had (ADR-020).

`QUATOT` is the number of shares traded and is what `volume` carries,
matching what the vendor provider reports there. `VOLTOT` (financial
volume, also two implied decimals) is not carried: `DailyBar` has one
volume field, and mixing two different quantities into it would make the
series mean different things depending on the source.

## No adjusted close, and why nothing is invented

COTAHIST prints **what was actually traded**. It carries no
corporate-action-adjusted series and never will — that is not what an
exchange's trade record is. So `adjusted_close` is reported as `None`,
and `reports_adjusted_close` is `False` so the validator knows this is
permanent rather than the vendor's one-session publication lag (ADR-016).

Filling it from `close` would be fabricating a number (rule 44), and the
error would not be small: an unadjusted series shows a 1:10 split as a
-90% day, which would land in volatility, drawdown and beta as if the
market had crashed.

The file does mark that an event *happened* — `ESPECI` carries suffixes
such as `EDJ` (ex-dividend and interest on capital; VALE3 carried it on
2026-08-18) and `DISMES` counts distributions. But a marker is not a
magnitude: neither field says how much was paid, and an adjustment
factor cannot be derived from the fact that something was paid. Building
the adjusted series needs the corporate actions themselves, which is a
separate ingestion (docs/memory/PROJECT_STATUS.md, Known Issue 1).

## The archive is distilled, not stored whole

The unit of retrieval is a year for every instrument, so caching is not
an optimisation — it is what makes per-ticker access possible at all.
Unlike the CVM archive, what is cached is the **spot-market records
only**, gzipped: the raw ZIP is 89% options that nothing here reads, and
scanning half a gigabyte of text per ticker per year is the difference
between a backfill that finishes and one that does not.

A finished calendar year is final and cached forever. The **current**
year is not: it grows every session, so its cache records how far it
reaches (`..._through_YYYYMMDD`) and is re-fetched when a caller asks for
a date beyond that. Freezing it the way a closed year is frozen would
silently stop the series from ever advancing.
"""

import gzip
import logging
import re
import tempfile
import time
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

from app.core.config import settings
from app.integrations.http import backoff_seconds
from app.integrations.market_data.base import DailyHistoryProvider
from app.integrations.market_data.exceptions import (
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)
from app.integrations.market_data.schemas import DailyBar

logger = logging.getLogger("investment_assistant.market_data.cotahist")

#: Every record, header and trailer included, is exactly this wide.
RECORD_LENGTH = 245

#: `TIPREG` values. Only detail records carry a bar.
DETAIL_RECORD = "01"

#: `TPMERC` for the spot market. See the module docstring.
SPOT_MARKET = "010"

#: Field offsets, as half-open slices into a decoded 245-char record.
#: Taken from B3's published layout and confirmed field by field against
#: the real 2026-08-18 file.
TIPREG = slice(0, 2)
DATA_PREGAO = slice(2, 10)
CODNEG = slice(12, 24)
TPMERC = slice(24, 27)
ESPECI = slice(39, 49)
PREABE = slice(56, 69)
PREMAX = slice(69, 82)
PREMIN = slice(82, 95)
PREULT = slice(108, 121)
QUATOT = slice(152, 170)
FATCOT = slice(210, 217)

#: Price fields carry two implied decimals: `0000000004260` is 42.60.
PRICE_DECIMALS = Decimal(100)

#: Ticker as it may be written by a caller. Anything outside this cannot
#: appear in `CODNEG`, so it is rejected before an archive is opened
#: rather than scanned for fruitlessly.
TICKER_PATTERN = re.compile(r"^[A-Z0-9]{4,12}$")


class CotahistArchive:
    """Downloads one COTAHIST year and caches its spot-market records.

    What lands on disk is the distilled subset, gzipped — see the module
    docstring on why the raw archive is not kept.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._cache_dir = Path(cache_dir or settings.B3_COTAHIST_CACHE_DIR)
        self._base_url = (base_url or settings.B3_COTAHIST_BASE_URL).rstrip("/")
        self._timeout = (
            timeout if timeout is not None else settings.B3_COTAHIST_TIMEOUT_SECONDS
        )
        self._max_retries = (
            max_retries if max_retries is not None else settings.B3_COTAHIST_MAX_RETRIES
        )
        self._client = client or httpx.Client(timeout=self._timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # -- cache layout -------------------------------------------------

    def final_path_for(self, year: int) -> Path:
        """Cache entry for a year that has ended, and is therefore final."""
        return self._cache_dir / f"cotahist_{year}.txt.gz"

    def partial_path_for(self, year: int, through: date) -> Path:
        """Cache entry for a year still in progress, naming its last session.

        The reach is in the filename rather than inside the file so that
        deciding whether the cache is stale costs a directory listing
        instead of decompressing megabytes.
        """
        return self._cache_dir / f"cotahist_{year}_through_{through:%Y%m%d}.txt.gz"

    def _cached_partial(self, year: int) -> tuple[Path, date] | None:
        candidates: list[tuple[Path, date]] = []
        pattern = f"cotahist_{year}_through_*.txt.gz"
        for path in self._cache_dir.glob(pattern):
            stamp = path.name.removeprefix(f"cotahist_{year}_through_").removesuffix(
                ".txt.gz"
            )
            try:
                reach = date(int(stamp[0:4]), int(stamp[4:6]), int(stamp[6:8]))
            except ValueError:
                continue
            candidates.append((path, reach))
        if not candidates:
            return None
        return max(candidates, key=lambda pair: pair[1])

    # -- retrieval ----------------------------------------------------

    def fetch(self, year: int, needed_through: date | None = None) -> Path | None:
        """The distilled archive for `year`, downloading it if needed.

        `needed_through` is the latest session the caller cares about. It
        only matters for a year that has not ended: a cached partial that
        does not reach that far is refreshed. Returns `None` when B3 has
        no archive for the year, which is the normal answer for a year
        that has not started, not an error.
        """
        final = self.final_path_for(year)
        if final.exists():
            return final

        year_is_over = year < datetime.now(UTC).year
        cached = self._cached_partial(year)
        if cached is not None and not year_is_over:
            path, reach = cached
            if needed_through is None or reach >= needed_through:
                return path

        payload = self._download(year)
        if payload is None:
            # Nothing published for this year. A partial already on disk
            # is still the best available answer.
            return cached[0] if cached is not None else None

        return self._store(year, payload, year_is_over, previous=cached)

    def _store(
        self,
        year: int,
        raw_zip: Path,
        year_is_over: bool,
        previous: tuple[Path, date] | None,
    ) -> Path | None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        staging = self._cache_dir / f"cotahist_{year}.partial"

        try:
            last_session = _distil(raw_zip, staging)
        finally:
            raw_zip.unlink(missing_ok=True)

        if last_session is None:
            logger.warning("COTAHIST archive for %s held no spot-market rows.", year)
            if not year_is_over:
                # No session to name the cache entry after, and a year
                # that has only just begun will have one shortly. Left
                # uncached so the next call looks again.
                staging.unlink(missing_ok=True)
                return None
            # A finished year with nothing in it is a final answer, and
            # caching it stops a fruitless re-download on every call.
            staging.replace(self.final_path_for(year))
            return self.final_path_for(year)

        target = (
            self.final_path_for(year)
            if year_is_over
            else self.partial_path_for(year, last_session)
        )
        staging.replace(target)

        # A superseded partial is removed only once its replacement is in
        # place, so an interrupted run never leaves the year uncached.
        if previous is not None and previous[0] != target:
            previous[0].unlink(missing_ok=True)

        return target

    def _download(self, year: int) -> Path | None:
        """Stream the year ZIP to a temporary file, or `None` on 404."""
        url = f"{self._base_url}/COTAHIST_A{year}.ZIP"
        last_error: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            handle, name = tempfile.mkstemp(suffix=".zip", prefix=f"cotahist_{year}_")
            tmp_path = Path(name)
            absent = False
            failed = False

            # The temporary file is closed before it is ever unlinked:
            # Windows refuses to delete an open file, which turned a
            # missing year into a PermissionError instead of a skip.
            try:
                with open(handle, "wb") as sink, self._client.stream(
                    "GET", url, follow_redirects=True
                ) as response:
                    if response.status_code == 404:
                        absent = True
                    elif response.status_code >= 400:
                        raise MarketDataUnavailableError(
                            f"B3 returned HTTP {response.status_code} for {year}."
                        )
                    else:
                        # Streamed to disk rather than held in memory:
                        # a year is tens of megabytes compressed and
                        # about half a gigabyte once expanded.
                        sink.writelines(response.iter_bytes(chunk_size=1 << 20))
            except (httpx.HTTPError, MarketDataUnavailableError) as exc:
                last_error = exc
                failed = True
                logger.warning(
                    "COTAHIST download failed (attempt %s/%s) for %s: %s",
                    attempt,
                    self._max_retries,
                    year,
                    exc,
                )

            if not (absent or failed):
                return tmp_path

            tmp_path.unlink(missing_ok=True)
            if absent:
                logger.info("B3 has no COTAHIST archive for %s.", year)
                return None
            if attempt < self._max_retries:
                time.sleep(backoff_seconds(attempt))

        raise MarketDataUnavailableError(
            f"B3 COTAHIST for {year} could not be downloaded after "
            f"{self._max_retries} attempts: {last_error}"
        )


def _distil(raw_zip: Path, destination: Path) -> date | None:
    """Copy the spot-market records out of `raw_zip` into a gzip file.

    Returns the last session date seen, or `None` if the archive held no
    usable record. Both files are streamed, so peak memory is one record
    regardless of the year's size.
    """
    last_session: date | None = None
    try:
        with zipfile.ZipFile(raw_zip) as archive:
            members = [n for n in archive.namelist() if n.upper().endswith(".TXT")]
            if not members:
                raise InvalidMarketDataResponseError(
                    f"COTAHIST archive {raw_zip.name} holds no .TXT member."
                )
            with archive.open(members[0]) as source, gzip.open(
                destination, "wb"
            ) as sink:
                for raw_line in source:
                    line = raw_line.rstrip(b"\r\n")
                    if len(line) != RECORD_LENGTH:
                        continue
                    if line[TIPREG] != DETAIL_RECORD.encode("ascii"):
                        continue
                    if line[TPMERC] != SPOT_MARKET.encode("ascii"):
                        continue
                    sink.write(line + b"\n")
                    session = _parse_date(line[DATA_PREGAO].decode("latin-1"))
                    if session is not None and (
                        last_session is None or session > last_session
                    ):
                        last_session = session
    except zipfile.BadZipFile as exc:
        raise InvalidMarketDataResponseError(
            f"COTAHIST archive {raw_zip.name} is not a readable ZIP: {exc}"
        ) from exc
    return last_session


class B3CotahistProvider(DailyHistoryProvider):
    """Daily bars read out of B3's open COTAHIST year archives.

    History only. There is no `get_quote` here and that is deliberate:
    an end-of-day archive cannot answer what a share is worth right now,
    and implementing it would mean returning yesterday's close dressed as
    a quote. `MarketDataProvider` stays the interface for that.
    """

    #: COTAHIST prints traded prices; nothing in it is adjusted.
    reports_adjusted_close = False

    def __init__(self, archive: CotahistArchive | None = None) -> None:
        self._archive = archive or CotahistArchive()

    def close(self) -> None:
        self._archive.close()

    def get_daily_history(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        normalised = ticker.strip().upper()
        if not TICKER_PATTERN.match(normalised):
            raise TickerNotFoundError(
                f"{ticker!r} is not a B3 negotiation code, so no COTAHIST "
                f"record can carry it."
            )
        if start > end:
            return []

        earliest = settings.B3_COTAHIST_FIRST_YEAR
        today = datetime.now(UTC).date()
        bars: list[DailyBar] = []
        found_any_archive = False
        traded_at_all = False

        for year in range(max(start.year, earliest), end.year + 1):
            path = self._archive.fetch(year, needed_through=min(end, today))
            if path is None:
                continue
            found_any_archive = True
            for bar in _read_bars(path, normalised):
                traded_at_all = True
                if start <= bar.date <= end:
                    bars.append(bar)

        if not found_any_archive:
            # Distinct from an empty series: the caller asked about years
            # nobody could answer for, which is a source failure, not the
            # statement that this asset never traded.
            raise MarketDataUnavailableError(
                f"No COTAHIST archive is available for {start.year}-{end.year}."
            )
        if not traded_at_all:
            raise TickerNotFoundError(
                f"COTAHIST has no spot-market record for {normalised} in "
                f"{start.year}-{end.year}."
            )

        # A ticker that exists but did not trade inside the window — not
        # yet listed, or already delisted — returns an empty series, the
        # way the vendor provider does. Only never appearing at all is a
        # "not found".
        bars.sort(key=lambda bar: bar.date)
        return bars


def _read_bars(path: Path, ticker: str) -> list[DailyBar]:
    """Every bar one distilled year holds for `ticker`."""
    wanted = ticker.ljust(12).encode("latin-1")
    bars: list[DailyBar] = []
    try:
        with gzip.open(path, "rb") as source:
            for raw_line in source:
                line = raw_line.rstrip(b"\n")
                if len(line) != RECORD_LENGTH or line[CODNEG] != wanted:
                    continue
                bar = _parse_bar(line.decode("latin-1"), ticker)
                if bar is not None:
                    bars.append(bar)
    except (OSError, EOFError) as exc:
        raise InvalidMarketDataResponseError(
            f"Cached COTAHIST archive {path.name} could not be read: {exc}"
        ) from exc
    return bars


def _parse_bar(record: str, ticker: str) -> DailyBar | None:
    session = _parse_date(record[DATA_PREGAO])
    if session is None:
        return None

    try:
        factor = _quotation_factor(record[FATCOT])
        bar = DailyBar(
            date=session,
            open=_price(record[PREABE], factor),
            high=_price(record[PREMAX], factor),
            low=_price(record[PREMIN], factor),
            close=_price(record[PREULT], factor),
            # Nothing in COTAHIST is adjusted; see the module docstring.
            adjusted_close=None,
            volume=Decimal(record[QUATOT].strip() or "0"),
        )
    except (InvalidOperation, ValueError) as exc:
        raise InvalidMarketDataResponseError(
            f"COTAHIST record for {ticker} on {record[DATA_PREGAO]} could not "
            f"be parsed: {exc}"
        ) from exc
    return bar


def _price(field: str, factor: Decimal) -> Decimal:
    """A 13-digit price field as reais per **one** share."""
    return Decimal(field.strip() or "0") / PRICE_DECIMALS / factor


def _quotation_factor(field: str) -> Decimal:
    factor = Decimal(field.strip() or "1")
    # A zero factor would divide every price by nothing meaningful. It
    # has not been observed, but the file is external input (rule 19).
    return factor if factor > 0 else Decimal(1)


def _parse_date(field: str) -> date | None:
    text = field.strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None
