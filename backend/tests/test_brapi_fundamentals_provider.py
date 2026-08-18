"""Tests for BrapiFundamentalsProvider using httpx.MockTransport — no
real network access.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from app.integrations.fundamentals.brapi import BrapiFundamentalsProvider
from app.integrations.fundamentals.exceptions import (
    FundamentalsNotFoundError,
    FundamentalsUnavailableError,
    InvalidFundamentalsResponseError,
)


def _epoch(year, month, day) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp())


def _payload(income_rows=None, balance_rows=None):
    result = {"symbol": "PETR4"}
    if income_rows is not None:
        result["incomeStatementHistory"] = {"incomeStatementHistory": income_rows}
    if balance_rows is not None:
        result["balanceSheetHistory"] = {"balanceSheetStatements": balance_rows}
    return {"results": [result]}


def _full_payload():
    """Mirrors the shape and field names of a real Brapi response.

    Verified against a live `GET /quote/PETR4` on 2026-08-17: modules are
    bare lists, rows carry `type: "yearly"`, equity is reported as
    `shareholdersEquity`, and debt only as individual lines.
    """
    return _payload(
        income_rows=[
            {
                "type": "yearly",
                "endDate": "2024-12-31",
                "totalRevenue": 511_000_000_000,
                "netIncome": 36_000_000_000,
                "ebit": 145_000_000_000,
                "incomeBeforeTax": 150_000_000_000,
                "incomeTaxExpense": -39_000_000_000,
            },
            {
                "type": "yearly",
                "endDate": "2023-12-31",
                "totalRevenue": 490_000_000_000,
                "netIncome": 124_000_000_000,
            },
        ],
        balance_rows=[
            {
                "type": "yearly",
                "endDate": "2024-12-31",
                "shareholdersEquity": 350_000_000_000,
                "cash": 60_000_000_000,
                "loansAndFinancing": 60_000_000_000,
                "longTermLoansAndFinancing": 240_000_000_000,
            },
            {
                "type": "yearly",
                "endDate": "2023-12-31",
                "shareholdersEquity": 340_000_000_000,
                "cash": 70_000_000_000,
                "loansAndFinancing": 40_000_000_000,
                "longTermLoansAndFinancing": 250_000_000_000,
            },
        ],
    )


def _provider(handler, **kwargs) -> BrapiFundamentalsProvider:
    transport = httpx.MockTransport(handler)
    return BrapiFundamentalsProvider(
        base_url="https://brapi.test/api",
        token="test-token",
        client=httpx.Client(transport=transport),
        **kwargs,
    )


def _static(payload, status_code=200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return handler


def test_parses_annual_statements_joined_by_reference_date():
    provider = _provider(_static(_full_payload()))

    statements = provider.get_annual_statements("PETR4")

    assert [s.reference_date for s in statements] == [
        date(2023, 12, 31),
        date(2024, 12, 31),
    ]
    latest = statements[1]
    assert latest.revenue == Decimal(511000000000)
    assert latest.net_income == Decimal(36000000000)
    assert latest.equity == Decimal(350000000000)
    assert latest.cash == Decimal(60000000000)
    assert latest.debt == Decimal(300000000000)


def test_debt_is_the_sum_of_the_reported_debt_lines():
    # The live response never populates totalDebt / shortLongTermDebt /
    # longTermDebt; only the individual lines carry values.
    provider = _provider(_static(_full_payload()))

    statements = provider.get_annual_statements("PETR4")

    older = statements[0]
    assert older.reference_date == date(2023, 12, 31)
    assert older.debt == Decimal(290000000000)


def test_debt_sums_loans_debentures_and_leases():
    payload = _payload(
        balance_rows=[
            {
                "type": "yearly",
                "endDate": "2024-12-31",
                "loansAndFinancing": 1,
                "longTermLoansAndFinancing": 10,
                "debentures": 100,
                "longTermDebentures": 1000,
                "leaseFinancing": 10_000,
                "longTermLeaseFinancing": 100_000,
            }
        ]
    )
    provider = _provider(_static(payload))

    (statement,) = provider.get_annual_statements("PETR4")

    assert statement.debt == Decimal(111_111)


def test_debt_prefers_an_aggregate_field_when_the_source_provides_one():
    payload = _payload(
        balance_rows=[
            {
                "type": "yearly",
                "endDate": "2024-12-31",
                "totalDebt": 900,
                "loansAndFinancing": 1,
            }
        ]
    )
    provider = _provider(_static(payload))

    (statement,) = provider.get_annual_statements("PETR4")

    assert statement.debt == Decimal(900)


def test_equity_reads_shareholders_equity():
    # totalStockholderEquity is null in every period of the live response;
    # shareholdersEquity is the populated field.
    payload = _payload(
        balance_rows=[
            {
                "type": "yearly",
                "endDate": "2024-12-31",
                "totalStockholderEquity": None,
                "shareholdersEquity": 417_587_000_000,
            }
        ]
    )
    provider = _provider(_static(payload))

    (statement,) = provider.get_annual_statements("PETR4")

    assert statement.equity == Decimal(417_587_000_000)


def test_equity_falls_back_to_the_documented_field_names():
    payload = _payload(
        balance_rows=[
            {"type": "yearly", "endDate": "2024-12-31", "totalStockholderEquity": 123}
        ]
    )
    provider = _provider(_static(payload))

    (statement,) = provider.get_annual_statements("PETR4")

    assert statement.equity == Decimal(123)


def test_income_detail_fields_are_mapped():
    provider = _provider(_static(_full_payload()))

    latest = provider.get_annual_statements("PETR4")[1]

    assert latest.ebit == Decimal(145_000_000_000)
    assert latest.income_before_tax == Decimal(150_000_000_000)
    assert latest.income_tax_expense == Decimal(-39_000_000_000)


def test_quarterly_rows_are_dropped():
    # A fiscal year and its Q4 share an end date; storing both would make
    # them indistinguishable (ADR-013).
    payload = _payload(
        income_rows=[
            {"type": "yearly", "endDate": "2024-12-31", "totalRevenue": 1000},
            {"type": "quarterly", "endDate": "2024-12-31", "totalRevenue": 250},
            {"type": "quarterly", "endDate": "2024-09-30", "totalRevenue": 240},
        ]
    )
    provider = _provider(_static(payload))

    statements = provider.get_annual_statements("PETR4")

    assert [s.reference_date for s in statements] == [date(2024, 12, 31)]
    assert statements[0].revenue == Decimal(1000)


def test_rows_without_a_type_discriminator_are_kept():
    # Older responses may omit `type`; dropping those rows would lose data.
    payload = _payload(income_rows=[{"endDate": "2024-12-31", "totalRevenue": 1000}])
    provider = _provider(_static(payload))

    assert len(provider.get_annual_statements("PETR4")) == 1


def test_regression_against_the_real_petr4_response():
    """Locks in the mapping verified against a live response on 2026-08-17.

    Values are PETR4's reported 2025 figures, with the modules as bare
    lists exactly as the API returns them. If Brapi renames a field, this
    fails loudly instead of silently producing nulls — which is precisely
    how the pre-verification `totalStockholderEquity` / `totalDebt`
    mapping went unnoticed.
    """
    payload = {
        "results": [
            {
                "symbol": "PETR4",
                "incomeStatementHistory": [
                    {
                        "type": "yearly",
                        "endDate": "2025-12-31",
                        "totalRevenue": 497549000000,
                        "ebit": 145628000000,
                        "cleanEbitda": 145628000000,  # identical to ebit: not EBITDA
                        "cleanNopat": 96114480000,  # flat 34%: not used
                        "netIncome": 110605000000,
                        "incomeBeforeTax": 150599000000,
                        "incomeTaxExpense": -39994000000,
                    }
                ],
                "balanceSheetHistory": [
                    {
                        "type": "yearly",
                        "endDate": "2025-12-31",
                        "cash": 35608000000,
                        "totalStockholderEquity": None,
                        "shareholdersEquity": 417587000000,
                        "shortLongTermDebt": None,
                        "longTermDebt": None,
                        "loansAndFinancing": 67253000000,
                        "longTermLoansAndFinancing": 316772000000,
                        "debentures": 0,
                        "longTermDebentures": 0,
                        "leaseFinancing": 55226000000,
                        "longTermLeaseFinancing": 183310000000,
                    }
                ],
            }
        ]
    }
    provider = _provider(_static(payload))

    (statement,) = provider.get_annual_statements("PETR4")

    assert statement.reference_date == date(2025, 12, 31)
    assert statement.revenue == Decimal(497549000000)
    assert statement.net_income == Decimal(110605000000)
    assert statement.equity == Decimal(417587000000)
    assert statement.cash == Decimal(35608000000)
    assert statement.debt == Decimal(622561000000)
    assert statement.ebit == Decimal(145628000000)
    assert statement.income_before_tax == Decimal(150599000000)
    assert statement.income_tax_expense == Decimal(-39994000000)
    # Never taken from cleanEbitda, which is a copy of ebit.
    assert statement.ebitda is None


def test_ebitda_and_free_cash_flow_are_none_not_fabricated():
    # These are not reported per reference period by the modules used;
    # they must stay null rather than be filled from a TTM snapshot.
    provider = _provider(_static(_full_payload()))

    for statement in provider.get_annual_statements("PETR4"):
        assert statement.ebitda is None
        assert statement.free_cash_flow is None


def test_missing_line_items_become_none_without_failing():
    provider = _provider(
        _static(_payload(income_rows=[{"endDate": "2024-12-31", "netIncome": 10}]))
    )

    (statement,) = provider.get_annual_statements("PETR4")

    assert statement.net_income == Decimal(10)
    assert statement.revenue is None
    assert statement.equity is None
    assert statement.cash is None
    assert statement.debt is None


def test_accepts_module_given_as_a_bare_list():
    # The exact nesting could not be verified against a live response, so
    # the parser accepts both documented shapes.
    payload = {
        "results": [
            {
                "symbol": "PETR4",
                "incomeStatementHistory": [
                    {"endDate": "2024-12-31", "totalRevenue": 100}
                ],
            }
        ]
    }
    provider = _provider(_static(payload))

    (statement,) = provider.get_annual_statements("PETR4")

    assert statement.reference_date == date(2024, 12, 31)
    assert statement.revenue == Decimal(100)


def test_parses_epoch_end_date():
    payload = _payload(
        income_rows=[{"endDate": _epoch(2024, 12, 31), "totalRevenue": 100}]
    )
    provider = _provider(_static(payload))

    (statement,) = provider.get_annual_statements("PETR4")

    assert statement.reference_date == date(2024, 12, 31)


def test_row_without_end_date_is_skipped_not_guessed():
    payload = _payload(
        income_rows=[
            {"totalRevenue": 999},
            {"endDate": "2024-12-31", "totalRevenue": 100},
        ]
    )
    provider = _provider(_static(payload))

    statements = provider.get_annual_statements("PETR4")

    assert len(statements) == 1
    assert statements[0].revenue == Decimal(100)


def test_unparseable_end_date_raises_invalid_response():
    payload = _payload(income_rows=[{"endDate": "not-a-date", "totalRevenue": 100}])
    provider = _provider(_static(payload))

    with pytest.raises(InvalidFundamentalsResponseError):
        provider.get_annual_statements("PETR4")


def test_unrecognised_module_shape_raises_invalid_response():
    payload = {"results": [{"symbol": "PETR4", "incomeStatementHistory": "nope"}]}
    provider = _provider(_static(payload))

    with pytest.raises(InvalidFundamentalsResponseError):
        provider.get_annual_statements("PETR4")


def test_response_without_any_statement_module_raises_invalid_response():
    provider = _provider(_static({"results": [{"symbol": "PETR4"}]}))

    with pytest.raises(InvalidFundamentalsResponseError):
        provider.get_annual_statements("PETR4")


def test_empty_results_raises_not_found():
    provider = _provider(_static({"results": []}))

    with pytest.raises(FundamentalsNotFoundError):
        provider.get_annual_statements("PETR4")


def test_http_404_raises_not_found():
    provider = _provider(_static({"error": "not found"}, status_code=404))

    with pytest.raises(FundamentalsNotFoundError):
        provider.get_annual_statements("UNKNOWN")


def test_invalid_json_raises_invalid_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    provider = _provider(handler)

    with pytest.raises(InvalidFundamentalsResponseError):
        provider.get_annual_statements("PETR4")


def test_retries_on_transient_server_error_then_succeeds():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, text="service unavailable")
        return httpx.Response(200, json=_full_payload())

    provider = _provider(handler, max_retries=3)
    with patch("app.integrations.http.time.sleep"):
        statements = provider.get_annual_statements("PETR4")

    assert calls["count"] == 2
    assert len(statements) == 2


def test_raises_unavailable_after_exhausting_retries():
    provider = _provider(_static({"error": "boom"}, status_code=500), max_retries=3)

    with (
        patch("app.integrations.http.time.sleep"),
        pytest.raises(FundamentalsUnavailableError),
    ):
        provider.get_annual_statements("PETR4")


def test_non_retryable_http_error_fails_immediately_without_retrying():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(400, text="bad request")

    provider = _provider(handler, max_retries=3)
    with pytest.raises(FundamentalsUnavailableError):
        provider.get_annual_statements("PETR4")

    assert calls["count"] == 1
