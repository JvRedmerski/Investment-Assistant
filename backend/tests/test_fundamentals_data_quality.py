"""Unit tests for validate_financial_statements, with known input and
known expected output (AGENTS.md rule 68)."""

from datetime import date
from decimal import Decimal

from app.integrations.fundamentals.data_quality import validate_financial_statements
from app.integrations.fundamentals.schemas import FinancialStatement

TODAY = date(2026, 8, 17)


def _statement(year=2024, **overrides) -> FinancialStatement:
    values = {
        "reference_date": date(year, 12, 31),
        "revenue": Decimal(511000000000),
        "ebitda": Decimal(200000000000),
        "net_income": Decimal(36000000000),
        "equity": Decimal(350000000000),
        "debt": Decimal(300000000000),
        "cash": Decimal(60000000000),
        "free_cash_flow": Decimal(80000000000),
        "ebit": Decimal(145000000000),
        "income_before_tax": Decimal(150000000000),
        "income_tax_expense": Decimal(-39000000000),
        "shares_outstanding": Decimal(12888732761),
    }
    values.update(overrides)
    return FinancialStatement(**values)


def test_fully_reported_statement_is_accepted_without_issues():
    report = validate_financial_statements([_statement()], today=TODAY)

    assert report.is_valid
    assert len(report.valid_statements) == 1
    assert report.errors == []
    assert report.warnings == []


def test_duplicate_reference_date_rejects_both_occurrences():
    report = validate_financial_statements(
        [_statement(), _statement(revenue=Decimal(1))], today=TODAY
    )

    assert report.valid_statements == []
    assert report.rejected_count == 2
    assert {issue.code for issue in report.errors} == {"DUPLICATE_REFERENCE_DATE"}


def test_future_reference_date_is_rejected():
    report = validate_financial_statements([_statement(year=2027)], today=TODAY)

    assert report.valid_statements == []
    assert [issue.code for issue in report.errors] == ["FUTURE_REFERENCE_DATE"]


def test_reference_date_of_today_is_accepted():
    report = validate_financial_statements(
        [_statement(reference_date=TODAY)], today=TODAY
    )

    assert report.is_valid
    assert len(report.valid_statements) == 1


def test_statement_with_no_figures_at_all_is_rejected():
    empty = FinancialStatement(reference_date=date(2024, 12, 31))

    report = validate_financial_statements([empty], today=TODAY)

    assert report.valid_statements == []
    assert [issue.code for issue in report.errors] == ["EMPTY_STATEMENT"]


def test_negative_revenue_is_rejected():
    report = validate_financial_statements(
        [_statement(revenue=Decimal(-1))], today=TODAY
    )

    assert report.valid_statements == []
    assert [issue.code for issue in report.errors] == ["NEGATIVE_VALUE"]


def test_negative_net_income_and_equity_are_accepted():
    # A loss-making year and negative shareholders' equity are real,
    # meaningful outcomes — rejecting them would discard valid data.
    report = validate_financial_statements(
        [_statement(net_income=Decimal(-5), equity=Decimal(-10))], today=TODAY
    )

    assert report.is_valid
    assert len(report.valid_statements) == 1


def test_negative_shares_outstanding_is_rejected():
    # Not a distressed company but a broken filing: the archives hold a
    # treasury count recorded as negative, and one whose treasury exceeds
    # the issued capital. Either way the row cannot be trusted.
    report = validate_financial_statements(
        [_statement(shares_outstanding=Decimal(-1))], today=TODAY
    )

    assert report.valid_statements == []
    assert [issue.code for issue in report.errors] == ["NEGATIVE_VALUE"]


def test_negative_free_cash_flow_is_accepted():
    report = validate_financial_statements(
        [_statement(free_cash_flow=Decimal(-42))], today=TODAY
    )

    assert report.is_valid
    assert len(report.valid_statements) == 1


def test_partially_reported_statement_is_stored_but_warned_about():
    partial = FinancialStatement(
        reference_date=date(2024, 12, 31), revenue=Decimal(100)
    )

    report = validate_financial_statements([partial], today=TODAY)

    assert report.is_valid
    assert report.valid_statements == [partial]
    assert [issue.code for issue in report.warnings] == ["INCOMPLETE_STATEMENT"]
    assert "10 of 11" in report.warnings[0].message


def test_valid_and_invalid_statements_are_separated():
    good = _statement(year=2024)
    bad = _statement(year=2023, revenue=Decimal(-1))

    report = validate_financial_statements([good, bad], today=TODAY)

    assert report.valid_statements == [good]
    assert report.rejected_count == 1
    assert report.errors[0].reference_date == date(2023, 12, 31)


def test_empty_batch_produces_an_empty_valid_report():
    report = validate_financial_statements([], today=TODAY)

    assert report.is_valid
    assert report.valid_statements == []
    assert report.rejected_count == 0
