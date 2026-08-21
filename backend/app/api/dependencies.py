from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.data.database import get_db
from app.data.models.users import User
from app.domain.benchmarks.catalog import UnknownBenchmarkError, get_benchmark
from app.domain.fundamentals.identity import StoredCnpjResolver
from app.integrations.ai.base import AIProvider
from app.integrations.ai.factory import build_ai_provider
from app.integrations.benchmarks.base import BenchmarkProvider
from app.integrations.benchmarks.factory import build_benchmark_provider
from app.integrations.fundamentals.base import FundamentalsProvider
from app.integrations.fundamentals.factory import build_fundamentals_provider
from app.integrations.fundamentals.identity import BrapiCnpjResolver
from app.integrations.market_data.base import (
    CorporateActionProvider,
    CorporateEventProvider,
    DailyHistoryProvider,
    MarketDataProvider,
)
from app.integrations.market_data.factory import (
    build_corporate_action_provider,
    build_corporate_event_provider,
    build_historical_price_provider,
    build_market_data_provider,
)

# tokenUrl is used only for OpenAPI documentation (Swagger "Authorize" button).
# Actual authentication is performed via the "Authorization: Bearer <token>" header.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": {
                "code": "INVALID_CREDENTIALS",
                "message": "Could not validate credentials.",
            }
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve and return the authenticated user from a JWT bearer token.

    Raises 401 if the token is missing, invalid, expired, or no longer
    references an existing user.
    """
    payload = decode_access_token(token)
    if payload is None:
        raise _credentials_exception()

    subject = payload.get("sub")
    if subject is None:
        raise _credentials_exception()

    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise _credentials_exception()

    user = db.get(User, user_id)
    if user is None:
        raise _credentials_exception()

    return user


def get_market_data_provider() -> Generator[MarketDataProvider, None, None]:
    """Provide a `MarketDataProvider` instance for a single request.

    Routes depend only on the abstract type, never on `BrapiProvider`
    directly (AGENTS.md rule 21). Tests override this dependency with a
    fake provider instead of hitting the network.
    """
    provider = build_market_data_provider()
    try:
        yield provider
    finally:
        provider.close()


def get_historical_price_provider() -> Generator[DailyHistoryProvider, None, None]:
    """Provide the deep-history price source for a single request.

    Separate from `get_market_data_provider` because the two are not
    interchangeable. The vendor quotes and serves a short recent window
    with adjusted closes; B3's open archive serves decades of traded
    prices and cannot quote at all (ADR-023). A route asks for whichever
    of the two answers its question.
    """
    provider = build_historical_price_provider()
    try:
        yield provider
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()


def get_corporate_event_provider() -> Generator[CorporateEventProvider, None, None]:
    """Provide the source that dates events and identifies the security.

    Distinct from the price dependency even though B3's archive backs
    both today: a route that needs ex-dates and an ISIN is asking a
    different question from one that needs bars, and separating them
    keeps a future price source from having to answer this one.
    """
    provider = build_corporate_event_provider()
    try:
        yield provider
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()


def get_corporate_action_provider() -> Generator[CorporateActionProvider, None, None]:
    """Provide the source that sizes corporate events.

    The seam that keeps B3's undocumented events endpoint replaceable
    (ADR-026): routes and services see only `CorporateActionProvider`,
    and a test overrides this with a fake rather than reaching the
    network.
    """
    provider = build_corporate_action_provider()
    try:
        yield provider
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()


def get_fundamentals_provider(
    db: Session = Depends(get_db),
) -> Generator[FundamentalsProvider, None, None]:
    """Provide a `FundamentalsProvider` instance for a single request.

    Same contract as `get_market_data_provider`: routes depend only on
    the abstract type, and tests override this dependency with a fake
    instead of hitting the network.

    Unlike the other two, this one takes a session, because the default
    provider reads CVM files keyed by CNPJ and the mapping from a ticker
    lives on `assets.cnpj`. Resolving through the database first is what
    keeps a sync from spending a quota-limited request per asset on a
    value that never changes.
    """
    provider = build_fundamentals_provider(
        resolve_cnpj=StoredCnpjResolver(db, BrapiCnpjResolver())
    )
    try:
        yield provider
    finally:
        provider.close()


def get_benchmark_provider(code: str) -> Generator[BenchmarkProvider, None, None]:
    """Provide the `BenchmarkProvider` that serves the benchmark in the path.

    Unlike the other two provider dependencies this one reads a path
    parameter, because which source backs a benchmark is a property of
    the benchmark rather than of the deployment: the CDI only exists at
    the Banco Central, the Ibovespa only at a market data vendor. Routes
    still depend solely on the abstract type (AGENTS.md rule 21), and
    tests override this dependency with a fake.
    """
    try:
        definition = get_benchmark(code)
    except UnknownBenchmarkError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "BENCHMARK_NOT_FOUND",
                    "message": f"Unknown benchmark {code}.",
                }
            },
        ) from exc

    provider = build_benchmark_provider(definition.source)
    try:
        yield provider
    finally:
        provider.close()


def get_ai_provider() -> Generator[AIProvider, None, None]:
    """Provide the `AIProvider` for a single request.

    Same contract as the other provider dependencies: routes depend only
    on the abstract type (AGENTS.md rules 21/40), and tests override
    this with a fake instead of reaching a model.

    Unlike the others, the provider behind this one produces no data —
    only prose about data the backend already computed (ADR-009). That
    is why `AI_PROVIDER=none` yields a provider that refuses politely
    rather than raising here: switching explanations off is a supported
    deployment, not a misconfiguration.
    """
    provider = build_ai_provider()
    try:
        yield provider
    finally:
        provider.close()
