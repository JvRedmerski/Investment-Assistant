"""Data quality checks for a batch of financial statements (AGENTS.md rule 20).

Pydantic (`schemas.FinancialStatement`) already guarantees each field is
absent or a well-formed `Decimal` (rule 19). What it cannot catch is
business-level invalidity across a *batch*: two rows claiming the same
reference period, a period ending in the future, a row carrying no
figures at all, or a figure whose sign is impossible for that line item.

Like `market_data.data_quality`, this is a small pure deterministic
function with no I/O, testable with known input and known expected
output (rule 68). `today` is injectable so the future-date check stays
deterministic in tests.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from app.integrations.fundamentals.schemas import (
    REPORTED_FIELD_NAMES,
    FinancialStatement,
)

# Line items that cannot legitimately be negative. Deliberately excluded:
# `net_income` (losses are normal), `equity` (patrimônio líquido can be
# negative for a distressed company), and `free_cash_flow` (routinely
# negative for companies in a heavy investment cycle). Rejecting those
# would discard real, meaningful data.
#
# `shares_outstanding` is here because a negative count is not a company
# in trouble, it is a broken filing: the 2022 archive holds one with
# treasury shares recorded as a negative number, and the 2021 one holds a
# company whose treasury count exceeds its issued capital.
#
# `dividends_paid` is here for a different reason: the DMPL writes a
# distribution as a *debit*, so the parser takes its magnitude. A
# negative value arriving anyway means the sign convention was misread
# somewhere, and a negative payout is not a thing a company can do.
_NON_NEGATIVE_FIELDS = (
    "revenue",
    "debt",
    "cash",
    "shares_outstanding",
    "dividends_paid",
)


@dataclass
class StatementIssue:
    reference_date: date
    code: str
    message: str


@dataclass
class FundamentalsQualityReport:
    valid_statements: list[FinancialStatement] = field(default_factory=list)
    errors: list[StatementIssue] = field(default_factory=list)
    warnings: list[StatementIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def rejected_count(self) -> int:
        # One error per rejected statement (see _validate_single), so this
        # matches how many input statements were dropped.
        return len(self.errors)


def validate_financial_statements(
    statements: list[FinancialStatement],
    today: date | None = None,
) -> FundamentalsQualityReport:
    """Validate a batch of statements for one asset.

    Separates rows safe to store (`valid_statements`) from rows rejected
    (`errors`) and rows stored but worth flagging (`warnings`).
    """
    reference_today = today or datetime.now(UTC).date()
    report = FundamentalsQualityReport()

    seen: dict[date, int] = {}
    for statement in statements:
        seen[statement.reference_date] = seen.get(statement.reference_date, 0) + 1
    duplicates = {ref for ref, count in seen.items() if count > 1}

    accepted: list[FinancialStatement] = []
    for statement in statements:
        error = _validate_single(statement, duplicates, reference_today)
        if error is not None:
            report.errors.append(error)
            continue

        reported = statement.reported_fields
        if len(reported) < _EXPECTED_FIELD_COUNT:
            missing = _EXPECTED_FIELD_COUNT - len(reported)
            report.warnings.append(
                StatementIssue(
                    reference_date=statement.reference_date,
                    code="INCOMPLETE_STATEMENT",
                    message=(
                        f"Statement for {statement.reference_date} is missing "
                        f"{missing} of {_EXPECTED_FIELD_COUNT} line items "
                        f"(reported: {', '.join(sorted(reported))})."
                    ),
                )
            )
        accepted.append(statement)

    report.valid_statements = accepted
    return report


_EXPECTED_FIELD_COUNT = len(REPORTED_FIELD_NAMES)


def _validate_single(
    statement: FinancialStatement,
    duplicates: set[date],
    today: date,
) -> StatementIssue | None:
    if statement.reference_date in duplicates:
        # Neither occurrence can be trusted as authoritative, so both are
        # rejected — same policy as duplicate dates in daily bars.
        return StatementIssue(
            reference_date=statement.reference_date,
            code="DUPLICATE_REFERENCE_DATE",
            message=(
                f"Reference date {statement.reference_date} appears more than "
                f"once in the batch."
            ),
        )

    if statement.reference_date > today:
        # A reporting period cannot have ended in the future. Storing one
        # would let a later backtest read a figure before it could exist
        # (AGENTS.md rules 108/109).
        return StatementIssue(
            reference_date=statement.reference_date,
            code="FUTURE_REFERENCE_DATE",
            message=(
                f"Reference date {statement.reference_date} is in the future "
                f"(today is {today})."
            ),
        )

    reported = statement.reported_fields
    if not reported:
        return StatementIssue(
            reference_date=statement.reference_date,
            code="EMPTY_STATEMENT",
            message=(
                f"Statement for {statement.reference_date} reports no figures "
                f"at all; there is nothing to store."
            ),
        )

    for name in _NON_NEGATIVE_FIELDS:
        value = reported.get(name)
        if value is not None and value < 0:
            return StatementIssue(
                reference_date=statement.reference_date,
                code="NEGATIVE_VALUE",
                message=(
                    f"Statement for {statement.reference_date} has a negative "
                    f"{name} ({value}), which is not a valid value for that "
                    f"line item."
                ),
            )

    return None
