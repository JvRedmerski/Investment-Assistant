"""Tests for the B3 corporate-events provider — the magnitude source.

No network: every payload below was captured **verbatim** from the live
service on 2026-08-20, before any of these tests existed, and trimmed
only by dropping rows the assertion does not reach.

Three of the fixtures exist because they are the failure modes a
hand-written mock would never have contained:

- `BBAS_SUPPLEMENT` carries the same 1:2 split **three times**, once per
  ISIN the issuer has had (`BRBBASA04OR8`, `BRBBASA05OR5`,
  `BRBBASACNOR3`). Composing all three yields 8.0 against a real price
  step of 2.02, and that cubing is exactly how the duplication was
  found.
- `MGLU_SUPPLEMENT` holds all three sizeable labels at once, and their
  factors do **not** share a convention: `GRUPAMENTO` is `0,10` meaning
  the ratio itself, while `DESDOBRAMENTO` is `300,00` meaning a
  percentage. One field, two readings, and only the label says which.
- `ITUB_SUPPLEMENT` carries `CIS RED CAP` at `factor` 100 — a number
  that is neither 2.0 nor 1.0 against the 1.2190 step ITUB4 actually
  printed on 2021-10-04. It is left unsized on purpose.

`PETR_CASH_PAGE` keeps the service's own duplicate rows, because
collapsing them is behaviour under test rather than tidying.
"""

import base64
import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.integrations.market_data.b3_corporate_actions import (
    B3CorporateActionProvider,
)
from app.integrations.market_data.base import CorporateActionProvider
from app.integrations.market_data.exceptions import (
    InvalidMarketDataResponseError,
    MarketDataUnavailableError,
    TickerNotFoundError,
)
from app.integrations.market_data.schemas import (
    CorporateActionKind,
    SecurityIdentity,
)

# -- real payloads, verbatim ------------------------------------------

MGLU_SUPPLEMENT = [
    {
        "stockDividends": [
            {
                "assetIssued": "BRMGLUACNOR2",
                "factor": "5,00000000000",
                "approvedOn": "22/12/2025",
                "isinCode": "BRMGLUACNOR2",
                "label": "BONIFICACAO",
                "lastDatePrior": "29/12/2025",
                "remarks": "",
            },
            {
                "assetIssued": "BRMGLUACNOR2",
                "factor": "0,10000000000",
                "approvedOn": "24/04/2024",
                "isinCode": "BRMGLUACNOR2",
                "label": "GRUPAMENTO",
                "lastDatePrior": "24/05/2024",
                "remarks": "",
            },
            {
                "assetIssued": "BRMGLUACNOR2",
                "factor": "300,00000000000",
                "approvedOn": "07/10/2020",
                "isinCode": "BRMGLUACNOR2",
                "label": "DESDOBRAMENTO",
                "lastDatePrior": "13/10/2020",
                "remarks": "",
            },
        ],
        "cashDividends": [],
    }
]

BBAS_SUPPLEMENT = [
    {
        "stockDividends": [
            {
                "assetIssued": "BRBBASA04OR8",
                "factor": "100,00000000000",
                "approvedOn": "02/02/2024",
                "isinCode": "BRBBASA04OR8",
                "label": "DESDOBRAMENTO",
                "lastDatePrior": "15/04/2024",
                "remarks": "",
            },
            {
                "assetIssued": "BRBBASA05OR5",
                "factor": "100,00000000000",
                "approvedOn": "02/02/2024",
                "isinCode": "BRBBASA05OR5",
                "label": "DESDOBRAMENTO",
                "lastDatePrior": "15/04/2024",
                "remarks": "",
            },
            {
                "assetIssued": "BRBBASACNOR3",
                "factor": "100,00000000000",
                "approvedOn": "02/02/2024",
                "isinCode": "BRBBASACNOR3",
                "label": "DESDOBRAMENTO",
                "lastDatePrior": "15/04/2024",
                "remarks": "",
            },
        ],
        "cashDividends": [],
    }
]

ITUB_SUPPLEMENT = [
    {
        "stockDividends": [
            {
                "assetIssued": "BRITUBACNPR1",
                "factor": "100,00000000000",
                "approvedOn": "01/09/2021",
                "isinCode": "BRITUBACNPR1",
                "label": "CIS RED CAP",
                "lastDatePrior": "01/10/2021",
                "remarks": "",
            },
            {
                "assetIssued": "BRITUBACNPR1",
                "factor": "3,00000000000",
                "approvedOn": "22/12/2025",
                "isinCode": "BRITUBACNPR1",
                "label": "BONIFICACAO",
                "lastDatePrior": "23/12/2025",
                "remarks": "",
            },
        ],
        "cashDividends": [],
    }
]

#: Note the duplicated rows — the service really answers this way.
PETR_CASH_PAGE = {
    "page": {"pageNumber": 1, "pageSize": 99, "totalRecords": 4, "totalPages": 1},
    "results": [
        {
            "typeStock": "PN",
            "dateApproval": "11/05/2026",
            "valueCash": "0,35048636",
            "ratio": "1",
            "corporateAction": "JRS CAP PROPRIO",
            "lastDatePriorEx": "01/06/2026",
            "closingPricePriorExDate": "47,34",
            "quotedPerShares": "1",
        },
        {
            "typeStock": "PN",
            "dateApproval": "11/05/2026",
            "valueCash": "0,35048636",
            "ratio": "1",
            "corporateAction": "JRS CAP PROPRIO",
            "lastDatePriorEx": "01/06/2026",
            "closingPricePriorExDate": "47,34",
            "quotedPerShares": "1",
        },
        {
            "typeStock": "ON",
            "dateApproval": "16/04/2026",
            "valueCash": "0,31311454",
            "ratio": "1",
            "corporateAction": "JRS CAP PROPRIO",
            "lastDatePriorEx": "22/04/2026",
            "closingPricePriorExDate": "52,70",
            "quotedPerShares": "1",
        },
        {
            "typeStock": "PN",
            "dateApproval": "30/09/2004",
            "valueCash": "0,17",
            "ratio": "1000",
            "corporateAction": "DIVIDENDO",
            "lastDatePriorEx": "30/09/2004",
            "closingPricePriorExDate": "273,00",
            "quotedPerShares": "1000",
        },
    ],
}

PETR_COMPANIES = {
    "page": {"pageNumber": 1, "pageSize": 99, "totalRecords": 1, "totalPages": 1},
    "results": [
        {
            "issuingCompany": "PETR",
            "companyName": "PETROLEO BRASILEIRO S.A. PETROBRAS",
            "tradingName": "PETROBRAS",
        }
    ],
}

WINDOW = (date(2000, 1, 1), date(2030, 12, 31))

MGLU3 = SecurityIdentity(ticker="MGLU3", isin="BRMGLUACNOR2", share_class="ON")
BBAS3 = SecurityIdentity(ticker="BBAS3", isin="BRBBASACNOR3", share_class="ON")
ITUB4 = SecurityIdentity(ticker="ITUB4", isin="BRITUBACNPR1", share_class="PN")
PETR4 = SecurityIdentity(ticker="PETR4", isin="BRPETRACNPR6", share_class="PN")


def _decode(request: httpx.Request) -> tuple[str, dict]:
    """The endpoint and the parameters B3 was actually asked for."""
    _, endpoint, encoded = request.url.path.rsplit("/", 2)
    return endpoint, json.loads(base64.b64decode(encoded).decode())


def build_provider(routes: dict[str, object], **kwargs) -> B3CorporateActionProvider:
    """A provider wired to a mock transport keyed by endpoint name."""

    def handler(request: httpx.Request) -> httpx.Response:
        endpoint, _params = _decode(request)
        if endpoint not in routes:
            return httpx.Response(404)
        payload = routes[endpoint]
        if isinstance(payload, int):
            return httpx.Response(payload)
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return B3CorporateActionProvider(client=client, min_request_interval=0.0, **kwargs)


# -- the reading of `factor` -------------------------------------------


def test_split_and_bonus_factors_are_percentages_of_new_shares():
    provider = build_provider(
        {"GetListedSupplementCompany": MGLU_SUPPLEMENT, "GetInitialCompanies": {}}
    )
    actions = provider.get_corporate_actions(MGLU3, *WINDOW)

    by_label = {action.label: action for action in actions}
    # 300% more shares per hundred held: one share becomes four. The real
    # step was 104.00 -> 25.59.
    assert by_label["DESDOBRAMENTO"].share_ratio == Decimal(4)
    assert by_label["DESDOBRAMENTO"].kind is CorporateActionKind.SPLIT
    # 5% more shares: 9.35 -> 8.94 on 2025-12-30.
    assert by_label["BONIFICACAO"].share_ratio == Decimal("1.05")
    assert by_label["BONIFICACAO"].kind is CorporateActionKind.BONUS


def test_a_regroup_factor_is_the_ratio_itself_not_a_percentage():
    """The convention flips on this one label, and only the label says so.

    Read as a percentage, `0,10` would be a ratio of 1.001 — a tenth of a
    percent — against MGLU3's measured 1:10 regroup of 2024-05-27, where
    R$ 1.32 became R$ 13.15.
    """
    provider = build_provider(
        {"GetListedSupplementCompany": MGLU_SUPPLEMENT, "GetInitialCompanies": {}}
    )
    actions = provider.get_corporate_actions(MGLU3, *WINDOW)

    regroup = next(a for a in actions if a.label == "GRUPAMENTO")
    assert regroup.share_ratio == Decimal("0.10")
    assert regroup.kind is CorporateActionKind.REVERSE_SPLIT
    assert regroup.last_date_prior == date(2024, 5, 24)
    assert regroup.cash_amount is None


def test_the_same_split_filed_under_three_isins_is_read_once():
    """BBAS3's 1:2, which the service reports once per ISIN.

    Taking all three would compose to 2^3 = 8.0 against a price step of
    56.46 -> 27.91. The ISIN filter is what makes the answer 2.0.
    """
    provider = build_provider(
        {"GetListedSupplementCompany": BBAS_SUPPLEMENT, "GetInitialCompanies": {}}
    )
    actions = provider.get_corporate_actions(BBAS3, *WINDOW)

    assert len(actions) == 1
    assert actions[0].share_ratio == Decimal(2)
    assert actions[0].last_date_prior == date(2024, 4, 15)


def test_a_label_without_evidence_is_left_unsized_rather_than_guessed():
    """`CIS RED CAP` carries a factor and not a share ratio.

    ITUB4 stepped 29.67 -> 24.34 on 2021-10-04, a ratio of 1.2190, while
    the field says 100 — which under the split reading would be 2.0.
    Whatever that number means, sizing it would be rule 44.
    """
    provider = build_provider(
        {"GetListedSupplementCompany": ITUB_SUPPLEMENT, "GetInitialCompanies": {}}
    )
    actions = provider.get_corporate_actions(ITUB4, *WINDOW)

    assert [a.label for a in actions] == ["BONIFICACAO"]


# -- cash payouts ------------------------------------------------------


def test_cash_payouts_are_filtered_by_share_class():
    """PETR3 and PETR4 do not always receive the same thing."""
    provider = build_provider(
        {
            "GetInitialCompanies": PETR_COMPANIES,
            "GetListedCashDividends": PETR_CASH_PAGE,
            "GetListedSupplementCompany": [{"stockDividends": [], "cashDividends": []}],
        }
    )
    actions = provider.get_corporate_actions(PETR4, *WINDOW)

    assert all(a.kind.name in {"INTEREST_ON_CAPITAL", "CASH_DIVIDEND"} for a in actions)
    # The `ON` row of 2026-04-22 belongs to PETR3 and must not be here.
    assert date(2026, 4, 22) not in {a.last_date_prior for a in actions}


def test_identical_duplicate_rows_collapse_to_one_payout():
    provider = build_provider(
        {
            "GetInitialCompanies": PETR_COMPANIES,
            "GetListedCashDividends": PETR_CASH_PAGE,
            "GetListedSupplementCompany": [{"stockDividends": [], "cashDividends": []}],
        }
    )
    actions = provider.get_corporate_actions(PETR4, *WINDOW)

    on_that_day = [a for a in actions if a.last_date_prior == date(2026, 6, 1)]
    assert len(on_that_day) == 1
    assert on_that_day[0].cash_amount == Decimal("0.35048636")


def test_a_payout_quoted_per_thousand_shares_is_brought_to_one_share():
    """`quotedPerShares` is 1000 on 332 of the 2,305 rows measured.

    Reading it as per-share would overstate the payout a thousandfold —
    the same failure `FATCOT` has in the archive and `ESCALA_MOEDA` has
    in the CVM files.
    """
    provider = build_provider(
        {
            "GetInitialCompanies": PETR_COMPANIES,
            "GetListedCashDividends": PETR_CASH_PAGE,
            "GetListedSupplementCompany": [{"stockDividends": [], "cashDividends": []}],
        }
    )
    actions = provider.get_corporate_actions(PETR4, *WINDOW)

    old = next(a for a in actions if a.last_date_prior == date(2004, 9, 30))
    assert old.cash_amount == Decimal("0.00017")


def test_the_window_filters_on_the_date_b3_reports():
    provider = build_provider(
        {"GetListedSupplementCompany": MGLU_SUPPLEMENT, "GetInitialCompanies": {}}
    )
    actions = provider.get_corporate_actions(
        MGLU3, date(2024, 1, 1), date(2024, 12, 31)
    )

    assert [a.label for a in actions] == ["GRUPAMENTO"]


def test_an_inverted_window_asks_the_service_nothing():
    provider = build_provider({})
    assert (
        provider.get_corporate_actions(MGLU3, date(2025, 1, 1), date(2024, 1, 1)) == []
    )


# -- the fallback and the failure modes --------------------------------


def test_an_issuer_whose_trading_name_will_not_resolve_falls_back():
    """`KLBN11`'s trading name is `KLABIN S/A` and the lookup returns none.

    The supplement's own short tail is read instead — the same service,
    used *instead of* the full endpoint rather than merged with it.
    """
    klbn = SecurityIdentity(ticker="KLBN11", isin="BRKLBNCDAM18", share_class="UNT")
    provider = build_provider(
        {
            # No `results` match for the issuer code.
            "GetInitialCompanies": {"page": {"totalPages": 1}, "results": []},
            "GetListedSupplementCompany": [
                {
                    "stockDividends": [],
                    "cashDividends": [
                        {
                            "isinCode": "BRKLBNCDAM18",
                            "rate": "0,25000000000",
                            "label": "DIVIDENDO",
                            "lastDatePrior": "18/12/2025",
                        },
                        {
                            "isinCode": "BRKLBNACNOR1",
                            "rate": "9,99000000000",
                            "label": "DIVIDENDO",
                            "lastDatePrior": "18/12/2025",
                        },
                    ],
                }
            ],
        }
    )
    actions = provider.get_corporate_actions(klbn, *WINDOW)

    assert len(actions) == 1
    assert actions[0].cash_amount == Decimal("0.25")


def test_a_company_the_service_does_not_know_is_not_found():
    provider = build_provider(
        {"GetListedSupplementCompany": [], "GetInitialCompanies": {}}
    )
    with pytest.raises(TickerNotFoundError):
        provider.get_corporate_actions(MGLU3, *WINDOW)


def test_a_service_outage_is_reported_as_unavailable():
    provider = build_provider(
        {"GetListedSupplementCompany": 503, "GetInitialCompanies": {}}, max_retries=1
    )
    with pytest.raises(MarketDataUnavailableError):
        provider.get_corporate_actions(MGLU3, *WINDOW)


def test_a_malformed_document_is_reported_as_invalid():
    provider = build_provider(
        {"GetListedSupplementCompany": "not a document", "GetInitialCompanies": {}}
    )
    with pytest.raises(InvalidMarketDataResponseError):
        provider.get_corporate_actions(MGLU3, *WINDOW)


def test_the_provider_satisfies_the_abstract_interface():
    """Callers depend on the seam, never on this class (rule 21)."""
    provider = build_provider({})
    assert isinstance(provider, CorporateActionProvider)
    assert provider.source_name == "b3_corporate_events"


def test_parameters_travel_base64_encoded_in_the_path():
    """Not a query string — the service reads one encoded path segment."""
    seen: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        endpoint, params = _decode(request)
        seen.append((endpoint, params))
        if endpoint == "GetListedSupplementCompany":
            return httpx.Response(200, json=MGLU_SUPPLEMENT)
        return httpx.Response(200, json={"page": {"totalPages": 1}, "results": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = B3CorporateActionProvider(client=client, min_request_interval=0.0)
    provider.get_corporate_actions(MGLU3, *WINDOW)

    endpoint, params = seen[0]
    assert endpoint == "GetListedSupplementCompany"
    assert params["issuingCompany"] == "MGLU"
