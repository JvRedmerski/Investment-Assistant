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
- `BBAS3` on 2024-06-12, -13 and -14 shows the same `ON  EDJ NM` on all
  three sessions while `DISMES` reads 323, 323, 324. Two distributions,
  one unchanging marker: no mock would have been written this way, and
  it is the case that decides how corporate events must be detected.
"""

import gzip
import io
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.integrations.market_data.base import CorporateEventProvider
from app.integrations.market_data.cotahist import (
    B3CotahistProvider,
    CotahistArchive,
)
from app.integrations.market_data.exceptions import (
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)
from app.integrations.market_data.schemas import CorporateEvent, CorporateEventKind

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

#: Ex-dividend: `DISMES` goes 209 -> 210 on the session the price steps
#: from 63.96 to 60.84.
VALE3_20240311 = (
    "012024031102VALE3       010VALE        ON      NM   R$  "
    "000000000647800000000064780000000006372000000000640900000000063"
    "960000000006396000000000639801862000000000058622400000000375723"
    "935600000000000000009999123100000010000000000000BRVALEACNOR0209"
)
VALE3_20240312 = (
    "012024031202VALE3       010VALE        ON  ED  NM   R$  "
    "000000000623600000000062570000000006066000000000614000000000060"
    "840000000006084000000000608583139000000000044680100000000274337"
    "396200000000000000009999123100000010000000000000BRVALEACNOR0210"
)

#: A dividend and interest on capital going ex on the same session.
PETR4_20240611 = (
    "012024061102PETR4       010PETROBRAS   PN      N2   R$  "
    "000000000378100000000038000000000003750000000000376900000000037"
    "660000000003766000000000376742479000000000031130300000000117340"
    "149900000000000000009999123100000010000000000000BRPETRACNPR6212"
)
PETR4_20240612 = (
    "012024061202PETR4       010PETROBRAS   PN  EDJ N2   R$  "
    "000000000369500000000037050000000003561000000000361300000000035"
    "820000000003582000000000358310928000000000052182400000000188573"
    "779400000000000000009999123100000010000000000000BRPETRACNPR6213"
)

#: Banco do Brasil's 1:2 *desdobramento*: 56.46 -> 27.91 on 2024-04-16,
#: under the very same `EB` a bonus share carries.
BBAS3_20240415 = (
    "012024041502BBAS3       010BRASIL      ON      NM   R$  "
    "000000000572600000000057340000000005621000000000565300000000056"
    "460000000005641000000000564624487000000000007205700000000040740"
    "757500000000000000009999123100000010000000000000BRBBASACNOR3321"
)
BBAS3_20240416 = (
    "012024041602BBAS3       010BRASIL      ON  EB  NM   R$  "
    "000000000282300000000028400000000002754000000000279300000000027"
    "910000000002790000000000279555445000000000022923700000000064045"
    "699000000000000000009999123100000010000000000000BRBBASACNOR3322"
)

#: The three sessions the module docstring is about: one marker, two
#: distributions, and only the counter tells them apart.
BBAS3_20240612 = (
    "012024061202BBAS3       010BRASIL      ON  EDJ NM   R$  "
    "000000000273000000000027300000000002646000000000266400000000026"
    "540000000002670000000000265551422000000000019141600000000051002"
    "844000000000000000009999123100000010000000000000BRBBASACNOR3323"
)
BBAS3_20240613 = (
    "012024061302BBAS3       010BRASIL      ON  EDJ NM   R$  "
    "000000000266200000000026800000000002651000000000267000000000026"
    "720000000002671000000000267327804000000000013566600000000036233"
    "817200000000000000009999123100000010000000000000BRBBASACNOR3323"
)
BBAS3_20240614 = (
    "012024061402BBAS3       010BRASIL      ON  EDJ NM   R$  "
    "000000000265500000000026660000000002631000000000264400000000026"
    "450000000002644000000000264526597000000000011146400000000029479"
    "083800000000000000009999123100000010000000000000BRBBASACNOR3324"
)

#: `EX` is a marker this project has no evidence for. The counter moves,
#: so something went ex; what it was is not readable here.
BBAS3_20240221 = (
    "012024022102BBAS3       010BRASIL      ON      NM   R$  "
    "000000000593200000000059590000000005906000000000594300000000059"
    "440000000005940000000000594525993000000000022806100000000135537"
    "428900000000000000009999123100000010000000000000BRBBASACNOR3319"
)
BBAS3_20240222 = (
    "012024022202BBAS3       010BRASIL      ON  EX  NM   R$  "
    "000000000586900000000058760000000005792000000000582700000000058"
    "100000000005809000000000581129350000000000009899200000000057689"
    "194700000000000000009999123100000010000000000000BRBBASACNOR3320"
)

#: A fund that traded on neither side of its own distribution: the
#: counter moves 105 -> 106 across eighteen calendar days, and the
#: specification carries no marker at all.
BTYU11_20241010 = (
    "012024101012BTYU11      010FII BTYU    CI           R$  "
    "000000000101300000000010130000000001013000000000101300000000010"
    "130000000001075000000000000000001000000000000000001000000000000"
    "001013000000000000009999123100000010000000000000BRBTYUCTF004105"
)
BTYU11_20241028 = (
    "012024102812BTYU11      010FII BTYU    CI           R$  "
    "000000000100800000000010080000000001008000000000100800000000010"
    "080000000001010000000000000000045000000000001308269000000001318"
    "735152000000000000009999123100000010000000000000BRBTYUCTF004106"
)

#: The turn of the year: 345 on the last session of 2024, 346 on the
#: first of 2025, which is an event on a session no single archive can
#: date on its own.
ITUB4_20241230 = (
    "012024123002ITUB4       010ITAUUNIBANCOPN      N1   R$  "
    "000000000308700000000031070000000003073000000000308600000000030"
    "730000000003072000000000307527599000000000028377300000000087572"
    "672900000000000000009999123100000010000000000000BRITUBACNPR1345"
)
ITUB4_20250102 = (
    "012025010202ITUB4       010ITAUUNIBANCOPN  EJ  N1   R$  "
    "000000000306500000000030850000000003024000000000305500000000030"
    "570000000003055000000000305757666000000000025643400000000078361"
    "892900000000000000009999123100000010000000000000BRITUBACNPR1346"
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


# -- corporate events --------------------------------------------------


def events_of(tmp_path, records: list[str], ticker: str = "BBAS3", **kwargs):
    provider = B3CotahistProvider(build_archive(tmp_path, records, **kwargs))
    return provider.get_corporate_events(ticker, date(2024, 1, 1), date(2025, 12, 31))


def test_the_provider_answers_the_corporate_event_interface():
    # Orthogonal to the price interfaces on purpose: the vendor quotes
    # and cannot say when a paper went ex, so folding this into
    # `DailyHistoryProvider` would force it to answer badly.
    assert issubclass(B3CotahistProvider, CorporateEventProvider)


def test_a_dividend_is_dated_to_the_session_the_counter_moved(tmp_path):
    (event,) = events_of(tmp_path, [VALE3_20240311, VALE3_20240312], "VALE3")

    # Not the session the marker was last seen, and not the announcement:
    # the first session the paper traded without the right.
    assert event.date == date(2024, 3, 12)
    assert event.kind is CorporateEventKind.DIVIDEND
    assert event.distribution_number == 210
    assert event.specification == "ON  ED  NM"


def test_a_composite_marker_yields_one_event_per_right(tmp_path):
    events = events_of(tmp_path, [PETR4_20240611, PETR4_20240612], "PETR4")

    # `EDJ` is two rights, so it is two events — but one distribution as
    # the exchange counted it, which the shared number keeps recoverable.
    assert [event.kind for event in events] == [
        CorporateEventKind.DIVIDEND,
        CorporateEventKind.INTEREST_ON_CAPITAL,
    ]
    assert {event.date for event in events} == {date(2024, 6, 12)}
    assert {event.distribution_number for event in events} == {213}


def test_two_distributions_under_one_unchanging_marker_are_both_found(tmp_path):
    events = events_of(
        tmp_path,
        [
            BBAS3_20240415,
            BBAS3_20240416,
            BBAS3_20240612,
            BBAS3_20240613,
            BBAS3_20240614,
        ],
    )

    # The whole reason detection reads the counter and not the marker.
    # `ON  EDJ NM` is displayed on all three June sessions; detecting
    # runs of it would report one event where B3 counted two, and would
    # miss the one on the 14th entirely.
    assert [(event.date, event.distribution_number) for event in events] == [
        (date(2024, 4, 16), 322),
        (date(2024, 6, 12), 323),
        (date(2024, 6, 12), 323),
        (date(2024, 6, 14), 324),
        (date(2024, 6, 14), 324),
    ]


def test_a_marker_still_on_display_is_not_a_second_event(tmp_path):
    events = events_of(tmp_path, [BBAS3_20240612, BBAS3_20240613])

    # B3 keeps the marker up for about eight sessions. The counter does
    # not move, so neither does anything here — and the 12th itself is
    # the first record scanned, which has nothing to be compared to.
    assert events == []


def test_a_reverse_split_is_reported_and_carries_no_factor(tmp_path):
    (event,) = events_of(tmp_path, [MGLU3_20240524, MGLU3_20240527], "MGLU3")

    assert event.date == date(2024, 5, 27)
    assert event.kind is CorporateEventKind.REVERSE_SPLIT

    # The same two records move the raw close from 1.32 to 13.15 — the
    # +896% of ADR-023 — and the event that explains it still says
    # nothing about its size. There is no field here that could: the
    # archive marks that a grouping happened and never in what ratio,
    # and inferring one from the step is the heuristic that ADR rejected.
    assert set(CorporateEvent.model_fields) == {
        "date",
        "kind",
        "specification",
        "distribution_number",
    }


def test_a_split_and_a_bonus_are_reported_under_one_kind(tmp_path):
    (event,) = events_of(tmp_path, [BBAS3_20240415, BBAS3_20240416])

    # Banco do Brasil split 1:2 here, and B3 wrote the marker it writes
    # for a bonus. Naming the kind after either act alone would claim a
    # distinction the file does not make.
    assert event.date == date(2024, 4, 16)
    assert event.kind is CorporateEventKind.BONUS_OR_SPLIT


def test_a_letter_with_no_evidence_behind_it_is_left_unclassified(tmp_path):
    (event,) = events_of(tmp_path, [BBAS3_20240221, BBAS3_20240222])

    # `EX` is real and undeciphered. The event is reported because the
    # exchange counted it; what went ex is not guessed at (rule 44).
    assert event.date == date(2024, 2, 22)
    assert event.kind is CorporateEventKind.UNCLASSIFIED
    # Kept verbatim, so the day this marker is understood the archives do
    # not have to be read again.
    assert event.specification == "ON  EX  NM"


def test_a_counted_distribution_with_no_marker_at_all_is_still_reported(tmp_path):
    (event,) = events_of(tmp_path, [BTYU11_20241010, BTYU11_20241028], "BTYU11")

    # 7.5% of 2024's events look like this. The fund did not trade on the
    # ex-date itself, so the date is the first session it traded after —
    # which is the honest answer, and no price step is misplaced by it
    # because there was no session in between to misplace.
    assert event.date == date(2024, 10, 28)
    assert event.kind is CorporateEventKind.UNCLASSIFIED
    assert event.distribution_number == 106


def test_an_event_on_the_first_session_scanned_cannot_be_seen(tmp_path):
    events = events_of(tmp_path, [MGLU3_20240527], "MGLU3")

    # The counter is only ever read against its own previous value, and
    # 124 on its own says nothing. Reporting the marker instead would be
    # reporting a display window as an event.
    assert events == []


def test_the_counter_carries_across_the_turn_of_the_year(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        year = 2024 if "2024" in str(request.url) else 2025
        record = ITUB4_20241230 if year == 2024 else ITUB4_20250102
        return httpx.Response(200, content=build_zip([record], year))

    archive = CotahistArchive(
        cache_dir=tmp_path,
        base_url="https://b3.test/SerHist",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider = B3CotahistProvider(archive)

    (event,) = provider.get_corporate_events(
        "ITUB4", date(2024, 1, 1), date(2025, 12, 31)
    )

    # 345 lives in one archive and 346 in the next. Neither year can date
    # this event alone, which is why the scan spans the window's years
    # before it compares anything.
    assert event.date == date(2025, 1, 2)
    assert event.kind is CorporateEventKind.INTEREST_ON_CAPITAL


def test_an_event_outside_the_window_is_not_reported(tmp_path):
    provider = B3CotahistProvider(
        build_archive(tmp_path, [VALE3_20240311, VALE3_20240312])
    )

    assert (
        provider.get_corporate_events("VALE3", date(2024, 4, 1), date(2024, 12, 31))
        == []
    )


def test_the_session_before_the_window_is_still_read(tmp_path):
    provider = B3CotahistProvider(
        build_archive(tmp_path, [VALE3_20240311, VALE3_20240312])
    )

    # The window opens on the ex-date itself, so the record that makes it
    # detectable is outside it. Clipping the scan to the window would
    # lose the event; scanning whole years costs nothing extra.
    (event,) = provider.get_corporate_events(
        "VALE3", date(2024, 3, 12), date(2024, 12, 31)
    )
    assert event.date == date(2024, 3, 12)


def test_events_are_not_looked_for_in_an_inverted_window(tmp_path):
    calls: list[str] = []
    provider = B3CotahistProvider(
        build_archive(tmp_path, [VALE3_20240312], calls=calls)
    )

    assert (
        provider.get_corporate_events("VALE3", date(2024, 12, 31), date(2024, 1, 1))
        == []
    )
    assert calls == []


def test_a_ticker_absent_from_the_archive_has_no_events_to_report(tmp_path):
    provider = B3CotahistProvider(build_archive(tmp_path, [VALE3_20240312]))

    with pytest.raises(TickerNotFoundError):
        provider.get_corporate_events("PETR4", date(2024, 1, 1), date(2024, 12, 31))


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
