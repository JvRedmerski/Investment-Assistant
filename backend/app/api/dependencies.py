from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.data.database import get_db
from app.data.models.users import User
from app.integrations.market_data.base import MarketDataProvider
from app.integrations.market_data.factory import build_market_data_provider

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
