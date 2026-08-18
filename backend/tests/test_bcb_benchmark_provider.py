"""Tests for BcbSgsProvider using httpx.MockTransport — no real network
access.

The order these were written in matters, and is the whole point of the
first section: the live API was called first, its answers recorded, and
only then were the mocks below built. Wave 06 shipped two wrong field
names past 45 green tests because every mock had been written from the
same assumption it was supposed to be checking, and three of the
behaviours pinned here — a 404 that means "empty window", an HTML page
returned with HTTP 200, and a 406 above ten years — are ones no mock
written from the documentation would ever have contained.
"""

from datetime import date
from decimal import Decimal
from itertools import pairwise

import httpx
import pytest

from app.domain.benchmarks.catalog import CDI, IPCA
from app.integrations.benchmarks.bcb import BcbSgsProvider, _windows
from app.integrations.benchmarks.exceptions import (
    BenchmarkUnavailableError,
    InvalidBenchmarkResponseError,
)
from app.integrations.benchmarks.schemas import BenchmarkKind


def _provider(handler, **kwargs) -> BcbSgsProvider:
    return BcbSgsProvider(
        base_url="https://api.bcb.gov.br/dados/serie",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        **kwargs,
    )


def _rows(*pairs):
    return [{"data": day, "valor": value} for day, value in pairs]


# -- regression against the live API ---------------------------------
#
# Verbatim from real responses captured on 2026-08-18:
#
#   GET /bcdata.sgs.12/dados?formato=json
#       &dataInicial=02/01/2024&dataFinal=31/01/2024
#   GET /bcdata.sgs.433/dados?formato=json
#       &dataInicial=01/01/2024&dataFinal=01/12/2024

_REAL_CDI_JANUARY_2024 = _rows(
    ("02/01/2024", "0.043739"),
    ("03/01/2024", "0.043739"),
    ("04/01/2024", "0.043739"),
    ("05/01/2024", "0.043739"),
    ("08/01/2024", "0.043739"),
    ("09/01/2024", "0.043739"),
    ("10/01/2024", "0.043739"),
    ("11/01/2024", "0.043739"),
    ("12/01/2024", "0.043739"),
    ("15/01/2024", "0.043739"),
    ("16/01/2024", "0.043739"),
    ("17/01/2024", "0.043739"),
    ("18/01/2024", "0.043739"),
    ("19/01/2024", "0.043739"),
    ("22/01/2024", "0.043739"),
    ("23/01/2024", "0.043739"),
    ("24/01/2024", "0.043739"),
    ("25/01/2024", "0.043739"),
    ("26/01/2024", "0.043739"),
    ("29/01/2024", "0.043739"),
    ("30/01/2024", "0.043739"),
    ("31/01/2024", "0.043739"),
)

_REAL_IPCA_2024 = _rows(
    ("01/01/2024", "0.42"),
    ("01/02/2024", "0.83"),
    ("01/03/2024", "0.16"),
    ("01/04/2024", "0.38"),
    ("01/05/2024", "0.46"),
    ("01/06/2024", "0.21"),
    ("01/07/2024", "0.38"),
    ("01/08/2024", "-0.02"),
    ("01/09/2024", "0.44"),
    ("01/10/2024", "0.56"),
    ("01/11/2024", "0.39"),
    ("01/12/2024", "0.52"),
)


def test_regression_against_the_real_cdi_response():
    """The live January 2024 CDI window, parsed field for field."""
    provider = _provider(lambda _: httpx.Response(200, json=_REAL_CDI_JANUARY_2024))

    observations = provider.get_series(
        CDI.series_id, date(2024, 1, 2), date(2024, 1, 31), CDI.kind
    )

    assert len(observations) == 22
    assert observations[0].date == date(2024, 1, 2)
    assert observations[-1].date == date(2024, 1, 31)
    # Only business days: the 6th and 7th are a weekend and are simply absent.
    assert date(2024, 1, 6) not in {observation.date for observation in observations}
    # Published as "0.043739" percent, stored as a fraction, exactly.
    assert observations[0].value == Decimal("0.00043739")


def test_the_real_cdi_compounds_to_the_annual_rate_the_bcb_itself_publishes():
    """Cross-validation of the base-252 convention against a second series.

    The SGS publishes the CDI twice: series 12 as the daily rate, series
    4389 as the annualised one. We ingest the daily series, so compounding
    it over 252 sessions must reproduce what 4389 says for the same day —
    otherwise the convention in ADR-018 is wrong and every Sharpe built on
    it would be wrong by a constant factor with nothing to reveal it.

    Live on 2024-01-02: series 12 said 0.043739, series 4389 said 11.65.
    """
    provider = _provider(lambda _: httpx.Response(200, json=_REAL_CDI_JANUARY_2024))

    observations = provider.get_series(
        CDI.series_id, date(2024, 1, 2), date(2024, 1, 31), CDI.kind
    )

    annualised = (1 + observations[0].value) ** 252 - 1
    assert round(annualised * 100, 2) == Decimal("11.65")


def test_regression_against_the_real_ipca_response():
    """Every 2024 monthly print, including the negative one.

    August 2024 deflated by 0.02%. It is here because a validator that
    treated a negative rate as invalid would drop a real observation, and
    because it is the case a hand-built mock would not have thought of.
    """
    provider = _provider(lambda _: httpx.Response(200, json=_REAL_IPCA_2024))

    observations = provider.get_series(
        IPCA.series_id, date(2024, 1, 1), date(2024, 12, 1), IPCA.kind
    )

    assert len(observations) == 12
    # Dated on the first day of the month it measures, never the last.
    assert [observation.date.day for observation in observations] == [1] * 12
    assert observations[0].value == Decimal("0.0042")
    assert observations[7].value == Decimal("-0.0002")


def test_the_real_ipca_year_accumulates_to_the_figure_the_ibge_published():
    """4.83% for 2024 — an outside check on both parsing and units.

    Compounding the twelve monthly fractions has to land on the headline
    number the IBGE reported. A percent-versus-fraction slip, a dropped
    month or a mishandled negative would all miss it.
    """
    provider = _provider(lambda _: httpx.Response(200, json=_REAL_IPCA_2024))

    observations = provider.get_series(
        IPCA.series_id, date(2024, 1, 1), date(2024, 12, 1), IPCA.kind
    )

    accumulated = Decimal(1)
    for observation in observations:
        accumulated *= 1 + observation.value
    assert round((accumulated - 1) * 100, 2) == Decimal("4.83")


# -- behaviours only a live call revealed ----------------------------


def test_http_404_means_an_empty_window_rather_than_a_failure():
    """The SGS answers 404 for a window holding no observation.

    Verified live: asking series 12 for 15/08/2026 to 16/08/2026, a
    weekend, returns 404 with `SGSNegocioException: Value(s) not found`.
    Treating that as an error would fail every sync whose window happened
    to cover only non-business days.
    """
    body = {
        "erro": {
            "statusCode": 404,
            "detail": (
                "br.gov.bcb.pec.sgs.comum.excecoes.SGSNegocioException: "
                "Value(s) not found"
            ),
        }
    }
    provider = _provider(lambda _: httpx.Response(404, json=body))

    observations = provider.get_series(
        CDI.series_id, date(2026, 8, 15), date(2026, 8, 16), CDI.kind
    )

    assert observations == []


def test_an_html_page_returned_with_http_200_is_an_invalid_response():
    """An unknown series number does not 404 — it returns a web page.

    Verified live for series 999999: HTTP 200, `Content-Type: text/html`,
    an XHTML error document. It reaches the right exception, but by a
    route no one would have mocked, so it is pinned.
    """
    html = '<?xml version="1.0" encoding="pt-br"?>\r\n<html><body>erro</body></html>'
    provider = _provider(lambda _: httpx.Response(200, text=html))

    with pytest.raises(InvalidBenchmarkResponseError):
        provider.get_series("999999", date(2024, 1, 1), date(2024, 1, 31), CDI.kind)


def test_a_window_wider_than_ten_years_is_split_into_several_requests():
    """The SGS refuses windows above ten years on a daily series (HTTP 406).

    The boundary was probed live and is inclusive-exact: 18/08/2016 to
    18/08/2026 is accepted, 17/08/2016 to the same end is refused. The
    provider chunks rather than passing the caller's window through.
    """
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.url.params["dataInicial"],
                request.url.params["dataFinal"],
            )
        )
        return httpx.Response(200, json=[])

    provider = _provider(handler)
    provider.get_series(CDI.series_id, date(1990, 1, 1), date(2026, 8, 18), CDI.kind)

    assert seen == [
        ("01/01/1990", "31/12/1999"),
        ("01/01/2000", "31/12/2009"),
        ("01/01/2010", "31/12/2019"),
        ("01/01/2020", "18/08/2026"),
    ]


def test_windows_are_contiguous_so_no_observation_falls_through_a_seam():
    windows = _windows(date(1990, 1, 1), date(2026, 8, 18))

    assert windows[0][0] == date(1990, 1, 1)
    assert windows[-1][1] == date(2026, 8, 18)
    for (_, earlier_end), (later_start, _) in pairwise(windows):
        assert (later_start - earlier_end).days == 1


def test_a_window_inside_the_limit_stays_a_single_request():
    windows = _windows(date(2024, 1, 2), date(2024, 1, 31))

    assert windows == [(date(2024, 1, 2), date(2024, 1, 31))]


def test_chunking_survives_a_start_on_a_leap_day():
    """29 February plus ten years is not a date; it must not raise."""
    windows = _windows(date(2024, 2, 29), date(2036, 1, 1))

    assert windows[0] == (date(2024, 2, 29), date(2034, 2, 27))
    assert windows[-1][1] == date(2036, 1, 1)


def test_dates_are_sent_in_the_day_first_format_the_sgs_requires():
    """An ISO date is silently unusable here — the API wants dd/MM/yyyy."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, json=[])

    provider = _provider(handler)
    provider.get_series(CDI.series_id, date(2024, 3, 4), date(2024, 3, 5), CDI.kind)

    assert seen["dataInicial"] == "04/03/2024"
    assert seen["dataFinal"] == "05/03/2024"
    assert seen["formato"] == "json"


# -- units, missing data and malformed payloads ----------------------


def test_a_rate_is_converted_from_percent_to_a_fraction():
    provider = _provider(
        lambda _: httpx.Response(200, json=_rows(("02/01/2024", "13.65")))
    )

    observations = provider.get_series(
        "12", date(2024, 1, 2), date(2024, 1, 2), BenchmarkKind.RATE
    )

    assert observations[0].value == Decimal("0.1365")


def test_an_index_level_is_kept_exactly_as_published():
    """No division by 100: a level is not a percentage of anything."""
    provider = _provider(
        lambda _: httpx.Response(200, json=_rows(("30/09/2019", "104745")))
    )

    observations = provider.get_series(
        "7", date(2019, 9, 30), date(2019, 9, 30), BenchmarkKind.INDEX
    )

    assert observations[0].value == Decimal(104745)


def test_an_empty_value_is_reported_as_none_and_never_as_zero():
    """The SGS lists some dates with an empty `valor`.

    Zero is a measurement — a day the CDI paid nothing — and absence is
    not. Conflating them would quietly drag an accumulated index down
    (ADR-016, AGENTS.md rule 44).
    """
    provider = _provider(
        lambda _: httpx.Response(
            200, json=_rows(("02/01/2024", "0.043739"), ("03/01/2024", ""))
        )
    )

    observations = provider.get_series(
        CDI.series_id, date(2024, 1, 2), date(2024, 1, 3), CDI.kind
    )

    assert observations[0].value == Decimal("0.00043739")
    assert observations[1].value is None


def test_observations_come_back_oldest_first_even_if_the_source_reverses_them():
    """The `ultimos/N` form of this API returns newest first."""
    provider = _provider(
        lambda _: httpx.Response(
            200,
            json=_rows(
                ("17/08/2026", "0.051660"),
                ("14/08/2026", "0.051661"),
                ("13/08/2026", "0.051662"),
            ),
        )
    )

    observations = provider.get_series(
        CDI.series_id, date(2026, 8, 13), date(2026, 8, 17), CDI.kind
    )

    assert [observation.date for observation in observations] == [
        date(2026, 8, 13),
        date(2026, 8, 14),
        date(2026, 8, 17),
    ]


def test_an_unparseable_value_raises_rather_than_being_skipped():
    provider = _provider(
        lambda _: httpx.Response(200, json=_rows(("02/01/2024", "n/d")))
    )

    with pytest.raises(InvalidBenchmarkResponseError):
        provider.get_series(CDI.series_id, date(2024, 1, 2), date(2024, 1, 2), CDI.kind)


def test_an_unrecognized_date_raises():
    provider = _provider(
        lambda _: httpx.Response(200, json=_rows(("2024-01-02", "0.043739")))
    )

    with pytest.raises(InvalidBenchmarkResponseError):
        provider.get_series(CDI.series_id, date(2024, 1, 2), date(2024, 1, 2), CDI.kind)


def test_an_entry_without_a_date_raises():
    provider = _provider(lambda _: httpx.Response(200, json=[{"valor": "0.043739"}]))

    with pytest.raises(InvalidBenchmarkResponseError):
        provider.get_series(CDI.series_id, date(2024, 1, 2), date(2024, 1, 2), CDI.kind)


def test_a_json_object_where_an_array_was_expected_raises():
    provider = _provider(lambda _: httpx.Response(200, json={"data": "02/01/2024"}))

    with pytest.raises(InvalidBenchmarkResponseError):
        provider.get_series(CDI.series_id, date(2024, 1, 2), date(2024, 1, 2), CDI.kind)


def test_start_after_end_is_rejected_before_any_request_is_made():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request should be made")

    provider = _provider(handler)

    with pytest.raises(ValueError):
        provider.get_series(CDI.series_id, date(2024, 2, 1), date(2024, 1, 1), CDI.kind)


def test_a_persistent_server_error_surfaces_as_unavailable():
    """Resilience comes from the shared client; this pins the wiring."""
    provider = _provider(lambda _: httpx.Response(503), max_retries=2)

    with pytest.raises(BenchmarkUnavailableError):
        provider.get_series(CDI.series_id, date(2024, 1, 2), date(2024, 1, 3), CDI.kind)


def test_the_406_above_ten_years_would_surface_as_unavailable():
    """Belt and braces: chunking should mean this is never reached.

    Pinned anyway so that if the SGS ever tightens the limit, the failure
    is a clear `BenchmarkUnavailableError` rather than a parse error on
    the JSON error body.
    """
    body = {
        "error": (
            "O sistema aceita uma janela de consulta de, no maximo, "
            "10 anos em series de periodicidade diaria"
        )
    }
    provider = _provider(lambda _: httpx.Response(406, json=body))

    with pytest.raises(BenchmarkUnavailableError):
        provider.get_series(CDI.series_id, date(2024, 1, 2), date(2024, 1, 3), CDI.kind)
