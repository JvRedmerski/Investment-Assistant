"""Tests for ticker-to-CNPJ resolution — the joint between the two sources.

The payload shape is verbatim from a live `GET /quote/PETR4?modules=
summaryProfile` on 2026-08-18, which returned `cnpj: 33000167000101`.
That module is the one the vendor still serves on the free plan, which
is what makes the merge possible at all while its statement modules are
behind a paid tier.
"""

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.database import Base
from app.data.models.assets import Asset
from app.domain.fundamentals.identity import StoredCnpjResolver
from app.integrations.fundamentals.identity import (
    BrapiCnpjResolver,
    StaticCnpjResolver,
)

REAL_CNPJ = "33000167000101"


def _profile_payload(cnpj=REAL_CNPJ, include_profile=True):
    result = {"symbol": "PETR4", "longName": "Petroleo Brasileiro SA Pfd"}
    if include_profile:
        profile = {"sector": "Energia", "industry": "Petroleo e Gas Integrado"}
        if cnpj is not None:
            profile["cnpj"] = cnpj
        result["summaryProfile"] = profile
    return {"results": [result]}


def _resolver(handler) -> BrapiCnpjResolver:
    return BrapiCnpjResolver(
        base_url="https://brapi.dev/api",
        token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# -- the vendor side --------------------------------------------------


def test_the_cnpj_is_read_out_of_the_profile_module():
    resolver = _resolver(lambda _: httpx.Response(200, json=_profile_payload()))

    assert resolver("PETR4") == REAL_CNPJ


def test_the_profile_module_is_the_one_requested():
    """It is the only module still on the free plan."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return httpx.Response(200, json=_profile_payload())

    _resolver(handler)("PETR4")

    assert seen["modules"] == "summaryProfile"


def test_a_ticker_the_vendor_does_not_know_resolves_to_nothing():
    resolver = _resolver(lambda _: httpx.Response(404))

    assert resolver("NOPE3") is None


def test_a_profile_without_a_cnpj_resolves_to_nothing():
    """Normal for an ETF or a BDR — neither is a filing company."""
    resolver = _resolver(
        lambda _: httpx.Response(200, json=_profile_payload(cnpj=None))
    )

    assert resolver("IVVB11") is None


def test_an_empty_result_set_resolves_to_nothing():
    resolver = _resolver(lambda _: httpx.Response(200, json={"results": []}))

    assert resolver("NOPE3") is None


def test_a_missing_profile_module_resolves_to_nothing():
    resolver = _resolver(
        lambda _: httpx.Response(200, json=_profile_payload(include_profile=False))
    )

    assert resolver("PETR4") is None


# -- the stored side --------------------------------------------------


def test_a_stored_cnpj_is_used_without_asking_the_vendor(db_session):
    """A CNPJ does not change, and asking costs a quota-limited request."""
    db_session.add(
        Asset(ticker="PETR4", name="Petrobras", asset_type="STOCK", cnpj=REAL_CNPJ)
    )
    db_session.commit()

    def exploding(ticker):  # pragma: no cover - must not be called
        raise AssertionError("a stored CNPJ must not be re-resolved")

    assert StoredCnpjResolver(db_session, exploding)("PETR4") == REAL_CNPJ


def test_an_unresolved_asset_falls_back_and_remembers_the_answer(db_session):
    db_session.add(Asset(ticker="PETR4", name="Petrobras", asset_type="STOCK"))
    db_session.commit()
    calls: list[str] = []

    def fallback(ticker):
        calls.append(ticker)
        return REAL_CNPJ

    resolver = StoredCnpjResolver(db_session, fallback)

    assert resolver("PETR4") == REAL_CNPJ
    assert resolver("PETR4") == REAL_CNPJ
    assert calls == ["PETR4"]
    assert db_session.query(Asset).one().cnpj == REAL_CNPJ


def test_a_negative_answer_is_not_remembered(db_session):
    """An asset can be registered before the vendor knows it.

    Caching "no filer" would make that permanent, with nothing on the row
    to show why it was never retried.
    """
    db_session.add(Asset(ticker="NEW3", name="New", asset_type="STOCK"))
    db_session.commit()
    calls: list[str] = []

    def fallback(ticker):
        calls.append(ticker)

    resolver = StoredCnpjResolver(db_session, fallback)
    assert resolver("NEW3") is None
    assert resolver("NEW3") is None

    assert calls == ["NEW3", "NEW3"]
    assert db_session.query(Asset).one().cnpj is None


def test_an_unregistered_ticker_still_resolves_without_being_stored(db_session):
    resolver = StoredCnpjResolver(db_session, lambda ticker: REAL_CNPJ)

    assert resolver("PETR4") == REAL_CNPJ
    assert db_session.query(Asset).count() == 0


def test_the_lookup_is_case_insensitive(db_session):
    db_session.add(
        Asset(ticker="PETR4", name="Petrobras", asset_type="STOCK", cnpj=REAL_CNPJ)
    )
    db_session.commit()

    resolver = StoredCnpjResolver(db_session, lambda ticker: None)

    assert resolver("petr4") == REAL_CNPJ


def test_a_static_mapping_resolves_case_insensitively():
    resolver = StaticCnpjResolver({"PETR4": REAL_CNPJ})

    assert resolver("petr4") == REAL_CNPJ
    assert resolver("VALE3") is None
