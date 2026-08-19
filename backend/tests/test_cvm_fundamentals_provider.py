"""Tests for the CVM fundamentals provider.

No network: the archives are built in memory from rows copied verbatim
out of the real 2024 DFP files, captured on 2026-08-18 before any of
these tests existed. The figures asserted below are PETR4's published
2024 results, so a mapping error shows up as a number that does not match
the company's own annual report — which is the only check that would have
caught the Wave 06 field mix-up.
"""

import csv
import io
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.integrations.fundamentals.composite import CompositeFundamentalsProvider
from app.integrations.fundamentals.cvm import (
    CvmArchive,
    CvmFundamentalsProvider,
    normalise_cnpj,
)
from app.integrations.fundamentals.exceptions import (
    FundamentalsNotFoundError,
    FundamentalsUnavailableError,
    InvalidFundamentalsResponseError,
)
from app.integrations.fundamentals.identity import StaticCnpjResolver
from app.integrations.fundamentals.schemas import FinancialStatement

PETR4 = "33.000.167/0001-01"

#: Verbatim column set of the real statement CSVs.
COLUMNS = [
    "CNPJ_CIA",
    "DT_REFER",
    "VERSAO",
    "DENOM_CIA",
    "CD_CVM",
    "GRUPO_DFP",
    "MOEDA",
    "ESCALA_MOEDA",
    "ORDEM_EXERC",
    "DT_INI_EXERC",
    "DT_FIM_EXERC",
    "CD_CONTA",
    "DS_CONTA",
    "VL_CONTA",
    "ST_CONTA_FIXA",
]

#: PETR4's real 2024 figures, in thousands, exactly as the files carry
#: them. Sources: DRE_con, BPP_con, BPA_con and DVA_con of
#: dfp_cia_aberta_2024.zip.
PETR4_INCOME = [
    ("3.01", "Receita de Venda de Bens e/ou Servicos", "490829000"),
    ("3.05", "Resultado Antes do Resultado Financeiro e dos Tributos", "137201000"),
    ("3.07", "Resultado Antes dos Tributos sobre o Lucro", "54730000"),
    ("3.08", "Imposto de Renda e Contribuicao Social sobre o Lucro", "-17721000"),
    ("3.09", "Resultado Liquido das Operacoes Continuadas", "37009000"),
    ("3.11", "Lucro/Prejuizo Consolidado do Periodo", "37009000"),
    ("3.11.01", "Atribuido a Socios da Empresa Controladora", "36606000"),
    ("3.11.02", "Atribuido a Socios Nao Controladores", "403000"),
    # Earnings per share, in reais per share — on rows the file marks
    # `MIL` like every other. R$ 2.84 is what PETR4 published; scaling it
    # would make the reconciliation below reject every filing.
    ("3.99.01", "Lucro Basico por Acao", "0"),
    ("3.99.01.01", "ON", "2.84"),
    ("3.99.01.02", "PN", "2.84"),
]

#: PETR4's real 2024 share composition, from
#: dfp_cia_aberta_composicao_capital_2024.csv. Written in units in that
#: file; the 2020 one writes the same company in thousands.
PETR4_CAPITAL = {
    "QT_ACAO_ORDIN_CAP_INTEGR": "7442454142",
    "QT_ACAO_PREF_CAP_INTEGR": "5602042788",
    "QT_ACAO_TOTAL_CAP_INTEGR": "13044496930",
    "QT_ACAO_ORDIN_TESOURO": "222760",
    "QT_ACAO_PREF_TESOURO": "155541409",
    "QT_ACAO_TOTAL_TESOURO": "155764169",
}

#: 13,044,496,930 issued less 155,764,169 in treasury.
PETR4_SHARES_OUTSTANDING = Decimal(12888732761)

#: Verbatim column set of the real composicao_capital CSV. Note what is
#: **not** here: no `ESCALA_MOEDA`, no `ORDEM_EXERC`, no `CD_CONTA`.
CAPITAL_COLUMNS = [
    "CNPJ_CIA",
    "DT_REFER",
    "VERSAO",
    "DENOM_CIA",
    "QT_ACAO_ORDIN_CAP_INTEGR",
    "QT_ACAO_PREF_CAP_INTEGR",
    "QT_ACAO_TOTAL_CAP_INTEGR",
    "QT_ACAO_ORDIN_TESOURO",
    "QT_ACAO_PREF_TESOURO",
    "QT_ACAO_TOTAL_TESOURO",
]
PETR4_LIABILITIES = [
    ("2.01.04", "Emprestimos e Financiamentos", "68783000"),
    ("2.02.01", "Emprestimos e Financiamentos", "304684000"),
    ("2.03", "Patrimonio Liquido Consolidado", "367514000"),
    ("2.03.09", "Participacao dos Acionistas Nao Controladores", "1508000"),
]
PETR4_ASSETS = [
    ("1", "Ativo Total", "1124797000"),
    ("1.01.01", "Caixa e Equivalentes de Caixa", "20254000"),
]
PETR4_VALUE_ADDED = [
    ("7.04.01", "Depreciacao, Amortizacao e Exaustao", "-67033000"),
]

BILLION = Decimal(1_000_000_000)


def _csv(rows, cnpj=PETR4, year=2024, scale="MIL", order="ÚLTIMO", version="1"):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, delimiter=";")
    writer.writeheader()
    for code, description, value in rows:
        writer.writerow(
            {
                "CNPJ_CIA": cnpj,
                "DT_REFER": f"{year}-12-31",
                "VERSAO": version,
                "DENOM_CIA": "PETROLEO BRASILEIRO S.A. PETROBRAS",
                "CD_CVM": "009512",
                "GRUPO_DFP": "DF Consolidado",
                "MOEDA": "REAL",
                "ESCALA_MOEDA": scale,
                "ORDEM_EXERC": order,
                "DT_INI_EXERC": f"{year}-01-01",
                "DT_FIM_EXERC": f"{year}-12-31",
                "CD_CONTA": code,
                "DS_CONTA": description,
                "VL_CONTA": value,
                "ST_CONTA_FIXA": "S",
            }
        )
    return buffer.getvalue().encode("latin-1")


def _capital_csv(*rows, cnpj=PETR4, year=2024, refer=None):
    """The share composition file, one row per company as the CVM ships it.

    Takes any number of rows so the version rule can be exercised; the
    real files carry exactly one per company per year.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CAPITAL_COLUMNS, delimiter=";")
    writer.writeheader()
    for counts in rows:
        row = {
            "CNPJ_CIA": cnpj,
            "DT_REFER": refer or f"{year}-12-31",
            "VERSAO": "1",
            "DENOM_CIA": "PETROLEO BRASILEIRO S.A. PETROBRAS",
        }
        row.update(counts)
        writer.writerow({column: row.get(column, "") for column in CAPITAL_COLUMNS})
    return buffer.getvalue().encode("latin-1")


def _archive_bytes(year=2024, **overrides):
    parts = {
        "DRE_con": overrides.get("income", _csv(PETR4_INCOME, year=year)),
        "BPP_con": overrides.get("liabilities", _csv(PETR4_LIABILITIES, year=year)),
        "BPA_con": overrides.get("assets", _csv(PETR4_ASSETS, year=year)),
        "DVA_con": overrides.get("value_added", _csv(PETR4_VALUE_ADDED, year=year)),
        "composicao_capital": overrides.get(
            "capital", _capital_csv(PETR4_CAPITAL, year=year)
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for statement, payload in parts.items():
            archive.writestr(f"dfp_cia_aberta_{statement}_{year}.csv", payload)
    return buffer.getvalue()


@pytest.fixture
def cache_dir(tmp_path) -> Path:
    return tmp_path / "cvm"


def _provider(cache_dir, payloads: dict[int, bytes], **kwargs):
    """A provider whose downloads are served from `payloads`, by year."""

    def handler(request: httpx.Request) -> httpx.Response:
        for year, payload in payloads.items():
            if f"dfp_cia_aberta_{year}.zip" in str(request.url):
                return httpx.Response(200, content=payload)
        return httpx.Response(404)

    archive = CvmArchive(
        cache_dir=cache_dir,
        base_url="https://dados.cvm.gov.br/x",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return CvmFundamentalsProvider(
        StaticCnpjResolver({"PETR4": "33000167000101"}),
        archive=archive,
        first_year=kwargs.pop("first_year", 2024),
        last_year=kwargs.pop("last_year", 2024),
    )


# -- the regression against the real filing ---------------------------


def test_petr4_2024_parses_to_the_figures_the_company_published(cache_dir):
    """Every field against Petrobras' own 2024 annual report."""
    provider = _provider(cache_dir, {2024: _archive_bytes()})

    statements = provider.get_annual_statements("PETR4")

    assert len(statements) == 1
    statement = statements[0]
    assert statement.reference_date == date(2024, 12, 31)
    assert statement.revenue == Decimal(490829000) * 1000
    assert statement.ebit == Decimal(137201000) * 1000
    assert statement.income_before_tax == Decimal(54730000) * 1000
    assert statement.income_tax_expense == Decimal(-17721000) * 1000
    assert statement.cash == Decimal(20254000) * 1000
    # Round figures, for readability: R$ 490.8 bn of revenue.
    assert (statement.revenue / BILLION).quantize(Decimal("0.1")) == Decimal("490.8")


def test_net_income_is_the_share_attributable_to_the_parents_owners(cache_dir):
    """3.11.01 (R$ 36.6 bn), not 3.11 (R$ 37.0 bn).

    The difference is the minority's R$ 403 m. Using the consolidated
    line against parent-only equity would inflate ROE by the share of
    the business the shareholder does not own.
    """
    provider = _provider(cache_dir, {2024: _archive_bytes()})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.net_income == Decimal(36606000) * 1000
    assert statement.net_income != Decimal(37009000) * 1000


def test_equity_is_netted_of_non_controlling_interests(cache_dir):
    """2.03 less 2.03.09 — the same owners the profit is attributed to."""
    provider = _provider(cache_dir, {2024: _archive_bytes()})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.equity == (Decimal(367514000) - Decimal(1508000)) * 1000


def test_the_derived_roe_matches_the_published_ten_percent(cache_dir):
    """The end-to-end check: R$ 36.6 bn over R$ 366.0 bn is 10%.

    Any of the mapping decisions above being wrong moves this number
    visibly, which is what makes it worth asserting on top of the fields.
    """
    provider = _provider(cache_dir, {2024: _archive_bytes()})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.net_income is not None and statement.equity is not None
    roe = statement.net_income / statement.equity
    assert roe.quantize(Decimal("0.001")) == Decimal("0.100")


def test_debt_is_the_sum_of_current_and_non_current_borrowings(cache_dir):
    provider = _provider(cache_dir, {2024: _archive_bytes()})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.debt == (Decimal(68783000) + Decimal(304684000)) * 1000


def test_ebitda_is_derived_as_ebit_plus_depreciation(cache_dir):
    """R$ 137.2 bn + R$ 67.0 bn = R$ 204.2 bn, the figure PETR4 reports.

    The DVA carries D&A as a negative because it presents retentions as
    deductions, so the magnitude is what counts — 433 of 467 companies
    report it negative, three positive.
    """
    provider = _provider(cache_dir, {2024: _archive_bytes()})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.ebitda == (Decimal(137201000) + Decimal(67033000)) * 1000
    assert (statement.ebitda / BILLION).quantize(Decimal("0.1")) == Decimal("204.2")


def test_a_positive_depreciation_gives_the_same_ebitda(cache_dir):
    """The sign is a presentation convention, not information."""
    positive = _csv([("7.04.01", "Depreciacao", "67033000")])
    provider = _provider(cache_dir, {2024: _archive_bytes(value_added=positive)})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.ebitda == (Decimal(137201000) + Decimal(67033000)) * 1000


def test_ebitda_is_absent_when_depreciation_was_not_filed(cache_dir):
    """17 of 467 companies file no 7.04.01. Absent, not EBIT."""
    provider = _provider(cache_dir, {2024: _archive_bytes(value_added=_csv([]))})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.ebitda is None
    assert statement.ebit is not None


def test_free_cash_flow_is_never_derived(cache_dir):
    """The statement gives net investing, not capex; the two differ."""
    provider = _provider(cache_dir, {2024: _archive_bytes()})

    assert provider.get_annual_statements("PETR4")[0].free_cash_flow is None


# -- shares outstanding, and the unit the file does not state ---------


def test_shares_outstanding_is_issued_capital_less_treasury(cache_dir):
    """13,044,496,930 issued less 155,764,169 held in treasury.

    Treasury shares receive no dividend and carry no claim on earnings.
    Counting them would spread the same profit over more shares and
    understate EPS — for PETR4 by 1.2%, small here and not always.
    """
    provider = _provider(cache_dir, {2024: _archive_bytes()})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.shares_outstanding == PETR4_SHARES_OUTSTANDING
    assert statement.shares_outstanding != Decimal(13044496930)


def test_the_derived_eps_matches_the_published_two_eighty_four(cache_dir):
    """The end-to-end check, the same shape as the ROE one above.

    R$ 36.6 bn over 12.889 bn shares is R$ 2.84, which is the figure on
    PETR4's own income statement. Getting the share count wrong by a
    factor of a thousand — the file's actual failure mode — moves this
    to R$ 2,840.
    """
    provider = _provider(cache_dir, {2024: _archive_bytes()})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.net_income is not None
    assert statement.shares_outstanding is not None
    eps = statement.net_income / statement.shares_outstanding
    assert eps.quantize(Decimal("0.01")) == Decimal("2.84")


def test_a_count_filed_in_thousands_is_reconciled_to_units(cache_dir):
    """PETR4's own 2020 file, which writes the same company 1000x smaller.

    `composicao_capital` has no scale column and filers disagree: about a
    third write thousands. The filing's own EPS is what settles it — and
    it must settle it, because an unnoticed thousandfold error makes P/L
    a thousand times too low, which scores as the cheapest share on the
    exchange.
    """
    thousands = dict(PETR4_CAPITAL)
    thousands["QT_ACAO_TOTAL_CAP_INTEGR"] = "13044497"
    thousands["QT_ACAO_TOTAL_TESOURO"] = "155764"
    provider = _provider(
        cache_dir, {2024: _archive_bytes(capital=_capital_csv(thousands))}
    )

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.shares_outstanding == Decimal(12888733) * 1000


def test_earnings_per_share_is_read_without_the_currency_scale(cache_dir):
    """The EPS rows say `MIL` and mean reais per share.

    A regression guard on the one place the scale must not be applied: at
    `MIL` the reconciliation would look for a count a thousand times
    larger than any that was filed, and reject every company.
    """
    provider = _provider(
        cache_dir,
        {2024: _archive_bytes(income=_csv(PETR4_INCOME, scale="MIL"))},
    )

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.shares_outstanding == PETR4_SHARES_OUTSTANDING


def test_a_count_that_reconciles_at_neither_unit_is_absent(cache_dir):
    """Six to seventeen filings a year contradict their own EPS.

    Absent, not approximated and not "closest guess" (rule 44). The
    Valuation pillar treats a missing multiple as a first-class state.
    """
    wrong = dict(PETR4_CAPITAL)
    wrong["QT_ACAO_TOTAL_CAP_INTEGR"] = "500000"
    wrong["QT_ACAO_TOTAL_TESOURO"] = "0"
    provider = _provider(cache_dir, {2024: _archive_bytes(capital=_capital_csv(wrong))})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.shares_outstanding is None
    assert statement.net_income is not None  # the rest of the row survives


def test_shares_are_absent_when_the_filing_reports_no_eps(cache_dir):
    """No EPS, no way to tell thousands from units — so no count.

    A real gap: roughly a third of filers report no per-share figure at
    all. Accepting their counts unchecked would be right about two times
    in three, which is not a standard this project applies to a number
    that feeds a score.
    """
    no_eps = [row for row in PETR4_INCOME if not row[0].startswith("3.99")]
    provider = _provider(cache_dir, {2024: _archive_bytes(income=_csv(no_eps))})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.shares_outstanding is None


def test_treasury_exceeding_issued_capital_is_absent(cache_dir):
    """The 2021 archive holds one. A company cannot hold more than it issued."""
    impossible = dict(PETR4_CAPITAL)
    impossible["QT_ACAO_TOTAL_CAP_INTEGR"] = "0"
    impossible["QT_ACAO_TOTAL_TESOURO"] = "53096770180"
    provider = _provider(
        cache_dir, {2024: _archive_bytes(capital=_capital_csv(impossible))}
    )

    assert provider.get_annual_statements("PETR4")[0].shares_outstanding is None


def test_shares_are_absent_when_the_company_filed_no_composition_row(cache_dir):
    provider = _provider(cache_dir, {2024: _archive_bytes(capital=_capital_csv())})

    assert provider.get_annual_statements("PETR4")[0].shares_outstanding is None


def test_a_count_dated_to_another_period_is_not_attached(cache_dir):
    """The count must describe the period it is stored under (rule 109)."""
    provider = _provider(
        cache_dir,
        {2024: _archive_bytes(capital=_capital_csv(PETR4_CAPITAL, refer="2023-12-31"))},
    )

    assert provider.get_annual_statements("PETR4")[0].shares_outstanding is None


def test_the_highest_version_of_the_composition_row_wins(cache_dir):
    """Same rule as the statements: a re-delivered filing supersedes."""
    combined = _capital_csv(
        {**PETR4_CAPITAL, "QT_ACAO_TOTAL_CAP_INTEGR": "1"},
        {**PETR4_CAPITAL, "VERSAO": "3"},
    )
    provider = _provider(cache_dir, {2024: _archive_bytes(capital=combined)})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.shares_outstanding == PETR4_SHARES_OUTSTANDING


# -- the four columns that change the answer --------------------------


def test_the_currency_scale_is_applied(cache_dir):
    """`UNIDADE` filings are already in reais; `MIL` are in thousands.

    550 of the 32,776 rows in the real 2024 income statements are
    `UNIDADE`. Reading them as thousands would inflate those companies a
    thousandfold.
    """
    unidade = _csv([("3.01", "Receita", "490829000000")], scale="UNIDADE")
    provider = _provider(cache_dir, {2024: _archive_bytes(income=unidade)})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.revenue == Decimal(490829000000)


def test_an_unrecognised_currency_scale_is_refused(cache_dir):
    weird = _csv([("3.01", "Receita", "1")], scale="MILHAO")
    provider = _provider(cache_dir, {2024: _archive_bytes(income=weird)})

    with pytest.raises(InvalidFundamentalsResponseError):
        provider.get_annual_statements("PETR4")


def test_the_comparative_prior_year_is_ignored(cache_dir):
    """Every file carries the previous year as PENÚLTIMO.

    Reading it would produce a second statement for a year that has its
    own file, holding the restated view rather than what was filed.
    """
    both = (
        _csv(PETR4_INCOME)
        + _csv([("3.01", "Receita", "512000000")], order="PENÚLTIMO").split(b"\n", 1)[1]
    )
    provider = _provider(cache_dir, {2024: _archive_bytes(income=both)})

    statements = provider.get_annual_statements("PETR4")

    assert len(statements) == 1
    assert statements[0].revenue == Decimal(490829000) * 1000


def test_the_latest_version_of_a_restated_filing_wins(cache_dir):
    """A re-delivered year keeps its old rows in the file.

    Reading both would double every figure, and reading the first would
    report the numbers the company has since corrected.
    """
    restated = (
        _csv([("3.01", "Receita", "1000")], version="1")
        + _csv([("3.01", "Receita", "490829000")], version="3").split(b"\n", 1)[1]
    )
    provider = _provider(cache_dir, {2024: _archive_bytes(income=restated)})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.revenue == Decimal(490829000) * 1000


def test_a_line_the_company_did_not_file_is_absent_not_zero(cache_dir):
    """A bank files no 2.01.04; zero would be a different claim."""
    provider = _provider(cache_dir, {2024: _archive_bytes(liabilities=_csv([]))})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.debt is None
    assert statement.equity is None


def test_only_one_borrowing_line_still_yields_a_debt_figure(cache_dir):
    """A company with no current borrowings genuinely has only the one."""
    only_long = _csv([("2.02.01", "Emprestimos", "304684000")])
    provider = _provider(cache_dir, {2024: _archive_bytes(liabilities=only_long)})

    statement = provider.get_annual_statements("PETR4")[0]

    assert statement.debt == Decimal(304684000) * 1000


# -- identity ---------------------------------------------------------


def test_the_cnpj_is_punctuated_the_way_the_cvm_writes_it():
    """The vendor returns bare digits; the files are keyed on punctuation.

    Comparing the two unnormalised matches nothing, silently.
    """
    assert normalise_cnpj("33000167000101") == "33.000.167/0001-01"
    assert normalise_cnpj("33.000.167/0001-01") == "33.000.167/0001-01"


def test_a_malformed_cnpj_is_refused():
    with pytest.raises(InvalidFundamentalsResponseError):
        normalise_cnpj("330001670001")


def test_an_asset_with_no_filer_is_not_found(cache_dir):
    """A BDR or an ETF files no DFP, and never will."""
    provider = _provider(cache_dir, {2024: _archive_bytes()})

    with pytest.raises(FundamentalsNotFoundError, match="BDR"):
        provider.get_annual_statements("IVVB11")


def test_a_company_absent_from_the_archive_is_not_found(cache_dir):
    other = _csv(PETR4_INCOME, cnpj="00.000.000/0001-91")
    provider = _provider(cache_dir, {2024: _archive_bytes(income=other)})

    with pytest.raises(FundamentalsNotFoundError):
        provider.get_annual_statements("PETR4")


# -- the archive ------------------------------------------------------


def test_a_year_is_downloaded_once_and_then_read_from_disk(cache_dir):
    """Caching is what makes per-ticker access possible at all.

    The unit of retrieval is 13 MB covering every listed company, so
    without this, scoring twenty assets would fetch it twenty times.
    """
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=_archive_bytes())

    archive = CvmArchive(
        cache_dir=cache_dir,
        base_url="https://dados.cvm.gov.br/x",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider = CvmFundamentalsProvider(
        StaticCnpjResolver({"PETR4": "33000167000101"}),
        archive=archive,
        first_year=2024,
        last_year=2024,
    )

    provider.get_annual_statements("PETR4")
    provider.get_annual_statements("PETR4")

    assert len(calls) == 1


def test_a_year_the_cvm_has_no_file_for_is_skipped_not_failed(cache_dir):
    """Normal for a fiscal year whose filings are not out yet."""
    provider = _provider(
        cache_dir, {2024: _archive_bytes()}, first_year=2024, last_year=2026
    )

    statements = provider.get_annual_statements("PETR4")

    assert [statement.reference_date.year for statement in statements] == [2024]


def test_a_persistent_server_error_surfaces_as_unavailable(cache_dir):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    archive = CvmArchive(
        cache_dir=cache_dir,
        base_url="https://dados.cvm.gov.br/x",
        max_retries=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider = CvmFundamentalsProvider(
        StaticCnpjResolver({"PETR4": "33000167000101"}),
        archive=archive,
        first_year=2024,
        last_year=2024,
    )

    with pytest.raises(FundamentalsUnavailableError):
        provider.get_annual_statements("PETR4")


def test_a_corrupt_archive_is_reported_as_an_invalid_response(cache_dir):
    provider = _provider(cache_dir, {2024: b"this is not a zip"})

    with pytest.raises(InvalidFundamentalsResponseError):
        provider.get_annual_statements("PETR4")


def test_an_interrupted_download_does_not_leave_a_cached_stub(cache_dir):
    """Only whole files are moved into place, so a retry re-downloads."""
    provider = _provider(cache_dir, {2024: _archive_bytes()})
    provider.get_annual_statements("PETR4")

    assert not list(cache_dir.glob("*.partial"))
    assert (cache_dir / "dfp_cia_aberta_2024.zip").exists()


# -- the composite ----------------------------------------------------


class _Fake:
    def __init__(self, statements=None, error=None):
        self._statements = statements or []
        self._error = error
        self.closed = False

    def get_annual_statements(self, ticker):
        if self._error is not None:
            raise self._error
        return list(self._statements)

    def close(self):
        self.closed = True


def _statement(year: int) -> FinancialStatement:
    return FinancialStatement(reference_date=date(year, 12, 31), revenue=Decimal(year))


def test_the_first_source_with_data_wins():
    primary = _Fake([_statement(2024)])
    fallback = _Fake([_statement(2023)])

    result = CompositeFundamentalsProvider([primary, fallback]).get_annual_statements(
        "PETR4"
    )

    assert [item.reference_date.year for item in result] == [2024]


def test_a_source_that_does_not_have_the_asset_falls_through():
    primary = _Fake(error=FundamentalsNotFoundError("no filer"))
    fallback = _Fake([_statement(2023)])

    result = CompositeFundamentalsProvider([primary, fallback]).get_annual_statements(
        "IVVB11"
    )

    assert [item.reference_date.year for item in result] == [2023]


def test_an_empty_answer_is_treated_the_same_as_not_found():
    """A provider's choice of signal must not change which source is used."""
    primary = _Fake([])
    fallback = _Fake([_statement(2023)])

    result = CompositeFundamentalsProvider([primary, fallback]).get_annual_statements(
        "PETR4"
    )

    assert [item.reference_date.year for item in result] == [2023]


def test_a_broken_source_does_not_silently_hand_over_to_the_other():
    """An outage must not become an invisible change of source.

    Falling through here would mean the same figures arriving from
    somewhere else, with nothing in the result to say so.
    """
    primary = _Fake(error=FundamentalsUnavailableError("timeout"))
    fallback = _Fake([_statement(2023)])

    with pytest.raises(FundamentalsUnavailableError):
        CompositeFundamentalsProvider([primary, fallback]).get_annual_statements(
            "PETR4"
        )


def test_no_source_having_the_asset_is_not_found():
    composite = CompositeFundamentalsProvider(
        [_Fake(error=FundamentalsNotFoundError("a")), _Fake([])]
    )

    with pytest.raises(FundamentalsNotFoundError):
        composite.get_annual_statements("NOPE3")


def test_closing_the_composite_closes_every_source():
    first, second = _Fake(), _Fake()

    CompositeFundamentalsProvider([first, second]).close()

    assert first.closed and second.closed


def test_a_composite_needs_at_least_one_source():
    with pytest.raises(ValueError):
        CompositeFundamentalsProvider([])
