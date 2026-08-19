"""Tests for the B3 COTAHIST historical price provider.

No network: every archive here is built in memory from records copied
**verbatim** out of the real `COTAHIST_A2024.ZIP`, captured on 2026-08-19
before any of these tests existed. Each is 245 characters wide, exactly
as B3 writes them.

Two of the fixtures were chosen because they are the failure modes that a
hand-written mock would never have contained:

- `MGLU3` on 2024-05-24 and 2024-05-27 straddle a real 1:10 reverse split
  (`ESPECI` turns from `ON      NM` into `ON  EG  NM` — *ex-grupamento*),
  which moves the raw close from R$ 1.32 to R$ 13.15. That is the series
  the quant engine must never be handed as if it were adjusted.
- `FNOR11` and `SMLL11` are quoted per 1,000 and per 10 shares
  respectively (`FATCOT`), which is the only reason their prices mean
  anything once divided.
"""

import gzip
import io
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.integrations.market_data.cotahist import (
    B3CotahistProvider,
    CotahistArchive,
)
from app.integrations.market_data.exceptions import (
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)

# -- real records, verbatim -------------------------------------------

PETR4_20240102 = (
    "012024010202PETR4       010PETROBRAS   PN      N2   R$  "
    "000000000374400000000037890000000003740000000000376600000000037"
    "780000000003775000000000377839280000000000024043800000000090551"
    "383800000000000000009999123100000010000000000000BRPETRACNPR6209"
)

#: The session before Magazine Luiza's 1:10 reverse split.
MGLU3_20240524 = (
    "012024052402MGLU3       010MAGAZ LUIZA ON      NM   R$  "
    "000000000014000000000001410000000000132000000000013400000000001"
    "320000000000131000000000013230093000000000255521100000000034447"
    "106600000000000000009999123100000010000000000000BRMGLUACNOR2123"
)

#: The session after it. `ESPECI` carries `EG` — ex-grupamento.
MGLU3_20240527 = (
    "012024052702MGLU3       010MAGAZ LUIZA ON  EG  NM   R$  "
    "000000000128300000000013190000000001233000000000127400000000013"
    "150000000001313000000000131536759000000000027976500000000035662"
    "659200000000000000009999123100000010000000000000BRMGLUACNOR2124"
)

#: Quoted per 1,000 shares (`FATCOT` = 1000).
FNOR11_20240102 = (
    "012024010214FNOR11      010FINOR       CI *         R$  "
    "000000000007000000000000710000000000070000000000007000000000000"
    "710000000000070000000000007100002000000000000008000000000000000"
    "000561000000000000009999123100010000000000000000BRFNORCTF013002"
)

#: Quoted per 10 shares (`FATCOT` = 10).
SMLL11_20241016 = (
    "012024101602SMLL11      010SMALL CAP   SML)         R$  "
    "000000020330000000002033000000000203300000000020330000000002033"
    "000000000000000000000000000000006000000000000004890000000000099"
    "413700000000000000009999123100000100000000000000BRSMLLINDM18100"
)

#: A header and a trailer are the same width as a bar and would parse as
#: garbage if the record type were not checked.
HEADER = "00COTAHIST.2024BOVESPA 20240102".ljust(245)
TRAILER = "99COTAHIST.2024BOVESPA 2024123000000251000".ljust(245)

#: PETR4's 2024-01-02 record rewritten as an option (`TPMERC` 070). The
#: negotiation code is deliberately kept: the point is that the same
#: ticker trades in other markets at prices for a different contract.
PETR4_OPTION = PETR4_20240102[:24] + "070" + PETR4_20240102[27:]


@pytest.fixture(autouse=True)
def _fixed_first_year(monkeypatch):
    """Keep the provider from walking back to the configured first year."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "B3_COTAHIST_FIRST_YEAR", 2000)


def build_zip(records: list[str], year: int = 2024) -> bytes:
    buffer = io.BytesIO()
    body = "\r\n".join(records).encode("latin-1")
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"COTAHIST_A{year}.TXT", body)
    return buffer.getvalue()


def build_archive(
    tmp_path: Path,
    records: list[str],
    *,
    year: int = 2024,
    calls: list[str] | None = None,
    status: int = 200,
) -> CotahistArchive:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(str(request.url))
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, content=build_zip(records, year))

    return CotahistArchive(
        cache_dir=tmp_path,
        base_url="https://b3.test/SerHist",
        max_retries=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def read_cached(path: Path) -> list[str]:
    with gzip.open(path, "rb") as handle:
        return [line.rstrip(b"\n").decode("latin-1") for line in handle]


# -- parsing a real record --------------------------------------------


def test_parses_a_real_petr4_record_field_by_field(tmp_path):
    archive = build_archive(tmp_path, [HEADER, PETR4_20240102, TRAILER])
    provider = B3CotahistProvider(archive)

    (bar,) = provider.get_daily_history("PETR4", date(2024, 1, 1), date(2024, 12, 31))

    assert bar.date == date(2024, 1, 2)
    # Thirteen digits with two implied decimals: 0000000003744 is 37.44.
    assert bar.open == Decimal("37.44")
    assert bar.high == Decimal("37.89")
    assert bar.low == Decimal("37.40")
    assert bar.close == Decimal("37.78")
    # QUATOT, the number of shares traded — the same quantity the vendor
    # provider reports, not the financial volume.
    assert bar.volume == Decimal(24043800)


def test_the_source_reports_no_adjusted_close_and_none_is_invented(tmp_path):
    archive = build_archive(tmp_path, [PETR4_20240102])
    provider = B3CotahistProvider(archive)

    (bar,) = provider.get_daily_history("PETR4", date(2024, 1, 1), date(2024, 12, 31))

    # Not `close`. COTAHIST prints what traded; it holds no adjusted
    # series, and filling one from the raw close would fabricate a
    # number (rule 44 / ADR-016).
    assert bar.adjusted_close is None


def test_provider_declares_that_it_does_not_adjust(tmp_path):
    # The validator needs to tell "not published yet" (the vendor, one
    # session later) from "never published" (an exchange trade record).
    assert B3CotahistProvider.reports_adjusted_close is False


def test_ticker_is_matched_case_insensitively_and_trimmed(tmp_path):
    archive = build_archive(tmp_path, [PETR4_20240102])
    provider = B3CotahistProvider(archive)

    bars = provider.get_daily_history(" petr4 ", date(2024, 1, 1), date(2024, 12, 31))

    assert [bar.close for bar in bars] == [Decimal("37.78")]


# -- the quotation factor ---------------------------------------------


def test_a_paper_quoted_per_thousand_shares_is_normalised_to_one(tmp_path):
    archive = build_archive(tmp_path, [FNOR11_20240102])
    provider = B3CotahistProvider(archive)

    (bar,) = provider.get_daily_history("FNOR11", date(2024, 1, 1), date(2024, 12, 31))

    # The file writes a close of 0.71 with FATCOT=1000, meaning the price
    # quoted is for a thousand shares. Reconciled against the same
    # record's own financial volume: VOLTOT/QUATOT = 5.61 / 8000 =
    # 0.00070125 per share, which only the normalised figure is anywhere
    # near — the raw 0.71 is off by a factor of a thousand.
    assert bar.close == Decimal("0.00071")
    assert bar.volume == Decimal(8000)


def test_a_paper_quoted_per_ten_shares_is_normalised_to_one(tmp_path):
    archive = build_archive(tmp_path, [SMLL11_20241016])
    provider = B3CotahistProvider(archive)

    (bar,) = provider.get_daily_history("SMLL11", date(2024, 1, 1), date(2024, 12, 31))

    # Raw 2033.00 with FATCOT=10. The record's own VOLTOT/QUATOT is
    # 994137.00 / 4890 = 203.30 exactly, matching the normalised value.
    assert bar.close == Decimal("203.3")


def test_normalisation_is_a_no_op_when_the_factor_is_one(tmp_path):
    archive = build_archive(tmp_path, [PETR4_20240102])
    provider = B3CotahistProvider(archive)

    (bar,) = provider.get_daily_history("PETR4", date(2024, 1, 1), date(2024, 12, 31))

    assert bar.close == Decimal("37.78")


# -- the corporate action the source marks but does not quantify -------


def test_the_raw_series_carries_a_reverse_split_untouched(tmp_path):
    archive = build_archive(tmp_path, [MGLU3_20240524, MGLU3_20240527])
    provider = B3CotahistProvider(archive)

    before, after = provider.get_daily_history(
        "MGLU3", date(2024, 5, 1), date(2024, 5, 31)
    )

    # A real 1:10 reverse split. The provider reports both closes as
    # traded and does not smooth the discontinuity away — it has no
    # factor to smooth it with. `ESPECI` turns to `EG` (ex-grupamento),
    # so the file says an event happened, but never how large it was.
    assert before.close == Decimal("1.32")
    assert after.close == Decimal("13.15")
    jump = after.close / before.close - 1
    assert jump > Decimal(8)  # ~+896% in a single session
    # And neither bar claims to be adjusted, which is what keeps this
    # out of the return series.
    assert before.adjusted_close is None
    assert after.adjusted_close is None


# -- what the distilled archive keeps ----------------------------------


def test_header_trailer_and_other_markets_are_dropped_on_distil(tmp_path):
    archive = build_archive(tmp_path, [HEADER, PETR4_20240102, PETR4_OPTION, TRAILER])
    archive.fetch(2024)

    kept = read_cached(archive.final_path_for(2024))

    # Only the spot-market detail record survives. The option carries the
    # same CODNEG but a price for a different contract entirely.
    assert len(kept) == 1
    assert kept[0][24:27] == "010"


def test_an_option_on_the_same_ticker_is_never_returned_as_a_bar(tmp_path):
    # The archive holds a spot record too, so "not found" here can only
    # mean the option was filtered out — not that the year was empty.
    archive = build_archive(tmp_path, [PETR4_OPTION, MGLU3_20240527])
    provider = B3CotahistProvider(archive)

    with pytest.raises(TickerNotFoundError):
        provider.get_daily_history("PETR4", date(2024, 1, 1), date(2024, 12, 31))


def test_a_record_of_the_wrong_width_is_skipped(tmp_path):
    archive = build_archive(tmp_path, ["01truncated", PETR4_20240102])

    kept = read_cached(archive.fetch(2024))

    assert len(kept) == 1


def test_an_archive_without_a_text_member_is_rejected(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("readme.pdf", b"not the series")
        return httpx.Response(200, content=buffer.getvalue())

    archive = CotahistArchive(
        cache_dir=tmp_path,
        base_url="https://b3.test/SerHist",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(InvalidMarketDataResponseError):
        archive.fetch(2024)


def test_a_payload_that_is_not_a_zip_is_rejected(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>maintenance</html>")

    archive = CotahistArchive(
        cache_dir=tmp_path,
        base_url="https://b3.test/SerHist",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(InvalidMarketDataResponseError):
        archive.fetch(2024)


# -- caching -----------------------------------------------------------


def test_a_finished_year_is_downloaded_once_and_then_read_from_disk(tmp_path):
    calls: list[str] = []
    archive = build_archive(tmp_path, [PETR4_20240102], calls=calls)

    first = archive.fetch(2024)
    second = archive.fetch(2024)

    assert first == second == archive.final_path_for(2024)
    assert len(calls) == 1
    assert calls[0].endswith("/COTAHIST_A2024.ZIP")


def test_a_year_still_running_records_how_far_it_reaches(tmp_path, monkeypatch):
    current = _pretend_year_is_current(monkeypatch, 2024)
    archive = build_archive(tmp_path, [PETR4_20240102])

    path = archive.fetch(current)

    # Named by its last session, so staleness is a directory listing
    # rather than a decompression.
    assert path == archive.partial_path_for(current, date(2024, 1, 2))
    assert not archive.final_path_for(current).exists()


def test_a_running_year_is_reused_when_it_already_reaches_far_enough(
    tmp_path, monkeypatch
):
    current = _pretend_year_is_current(monkeypatch, 2024)
    calls: list[str] = []
    archive = build_archive(tmp_path, [PETR4_20240102], calls=calls)

    archive.fetch(current, needed_through=date(2024, 1, 2))
    archive.fetch(current, needed_through=date(2024, 1, 2))

    assert len(calls) == 1


def test_a_running_year_is_refetched_when_a_later_session_is_wanted(
    tmp_path, monkeypatch
):
    current = _pretend_year_is_current(monkeypatch, 2024)
    calls: list[str] = []
    archive = build_archive(tmp_path, [PETR4_20240102], calls=calls)

    archive.fetch(current, needed_through=date(2024, 1, 2))
    # Freezing the running year the way a closed one is frozen would stop
    # the series advancing for the rest of the year.
    archive.fetch(current, needed_through=date(2024, 6, 30))

    assert len(calls) == 2


def test_a_superseded_partial_is_removed_once_its_replacement_is_in_place(
    tmp_path, monkeypatch
):
    current = _pretend_year_is_current(monkeypatch, 2024)
    archive = build_archive(tmp_path, [PETR4_20240102])
    archive.fetch(current, needed_through=date(2024, 1, 2))

    archive_later = build_archive(tmp_path, [PETR4_20240102, MGLU3_20240527])
    archive_later.fetch(current, needed_through=date(2024, 12, 31))

    remaining = sorted(p.name for p in tmp_path.glob("cotahist_2024*"))
    assert remaining == ["cotahist_2024_through_20240527.txt.gz"]


def test_no_partial_file_is_left_behind_by_a_failed_download(tmp_path):
    archive = build_archive(tmp_path, [PETR4_20240102], status=500)

    with pytest.raises(MarketDataUnavailableError):
        archive.fetch(2024)

    assert list(tmp_path.glob("*.partial")) == []
    assert list(tmp_path.glob("*.txt.gz")) == []


def _pretend_year_is_current(monkeypatch, year: int) -> int:
    """Make `year` look like the calendar year in progress."""
    import app.integrations.market_data.cotahist as module

    real_datetime = module.datetime

    class FrozenDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(year, 6, 30, 12, 0, tzinfo=tz)

    monkeypatch.setattr(module, "datetime", FrozenDatetime)
    return year


# -- failure modes -----------------------------------------------------


def test_a_ticker_that_cannot_be_a_negotiation_code_is_refused_upfront(tmp_path):
    calls: list[str] = []
    archive = build_archive(tmp_path, [PETR4_20240102], calls=calls)
    provider = B3CotahistProvider(archive)

    with pytest.raises(TickerNotFoundError):
        provider.get_daily_history("../etc", date(2024, 1, 1), date(2024, 12, 31))

    # Refused before an archive was opened: no 79 MB download to learn
    # what the pattern already rules out.
    assert calls == []


def test_a_ticker_absent_from_the_archive_is_not_found(tmp_path):
    archive = build_archive(tmp_path, [PETR4_20240102])
    provider = B3CotahistProvider(archive)

    with pytest.raises(TickerNotFoundError):
        provider.get_daily_history("VALE3", date(2024, 1, 1), date(2024, 12, 31))


def test_a_year_b3_has_no_archive_for_is_skipped_not_fatal(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "2023" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, content=build_zip([PETR4_20240102]))

    archive = CotahistArchive(
        cache_dir=tmp_path,
        base_url="https://b3.test/SerHist",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider = B3CotahistProvider(archive)

    bars = provider.get_daily_history("PETR4", date(2023, 1, 1), date(2024, 12, 31))

    assert [bar.date for bar in bars] == [date(2024, 1, 2)]


def test_no_archive_at_all_is_an_unavailable_source_not_an_empty_series(tmp_path):
    archive = build_archive(tmp_path, [], status=404)
    provider = B3CotahistProvider(archive)

    # An empty list here would read as "this asset never traded", which
    # is a different and much worse answer than "the source is down".
    with pytest.raises(MarketDataUnavailableError):
        provider.get_daily_history("PETR4", date(2024, 1, 1), date(2024, 12, 31))


def test_a_failing_download_is_retried_before_giving_up(tmp_path):
    calls: list[str] = []
    archive = build_archive(tmp_path, [PETR4_20240102], calls=calls, status=503)

    with pytest.raises(MarketDataUnavailableError):
        archive.fetch(2024)

    assert len(calls) == 2  # max_retries


# -- windowing ---------------------------------------------------------


def test_a_ticker_that_traded_outside_the_window_yields_an_empty_series(tmp_path):
    archive = build_archive(tmp_path, [PETR4_20240102, MGLU3_20240527])
    provider = B3CotahistProvider(archive)

    bars = provider.get_daily_history("PETR4", date(2024, 6, 1), date(2024, 12, 31))

    # PETR4 is in the archive, just not in this window — a listing that
    # had not started or had already ended. That is an empty series, not
    # a "no such ticker", which is reserved for never appearing at all.
    assert bars == []


def test_an_inverted_window_yields_nothing_without_touching_the_source(tmp_path):
    calls: list[str] = []
    archive = build_archive(tmp_path, [PETR4_20240102], calls=calls)
    provider = B3CotahistProvider(archive)

    assert (
        provider.get_daily_history("PETR4", date(2024, 12, 31), date(2024, 1, 1)) == []
    )
    assert calls == []


def test_bars_from_several_years_come_back_in_chronological_order(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        year = 2023 if "2023" in str(request.url) else 2024
        record = (
            PETR4_20240102.replace("20240102", "20230103")
            if year == 2023
            else PETR4_20240102
        )
        return httpx.Response(200, content=build_zip([record], year))

    archive = CotahistArchive(
        cache_dir=tmp_path,
        base_url="https://b3.test/SerHist",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider = B3CotahistProvider(archive)

    bars = provider.get_daily_history("PETR4", date(2023, 1, 1), date(2024, 12, 31))

    assert [bar.date for bar in bars] == [date(2023, 1, 3), date(2024, 1, 2)]


# -- factory -----------------------------------------------------------


def test_factory_builds_the_configured_historical_source(monkeypatch):
    from app.core.config import settings
    from app.integrations.market_data.brapi import BrapiProvider
    from app.integrations.market_data.factory import build_historical_price_provider

    monkeypatch.setattr(settings, "HISTORICAL_PRICE_PROVIDER", "b3_cotahist")
    assert isinstance(build_historical_price_provider(), B3CotahistProvider)

    monkeypatch.setattr(settings, "HISTORICAL_PRICE_PROVIDER", "brapi")
    assert isinstance(build_historical_price_provider(), BrapiProvider)


def test_factory_refuses_an_unknown_historical_source(monkeypatch):
    from app.core.config import settings
    from app.integrations.market_data.factory import build_historical_price_provider

    monkeypatch.setattr(settings, "HISTORICAL_PRICE_PROVIDER", "nasdaq")
    with pytest.raises(ValueError, match="nasdaq"):
        build_historical_price_provider()
