from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def utc_now() -> datetime:
    return datetime.now(UTC)


# SQLAlchemy 2.0 Engine
engine = create_engine(
    settings.DATABASE_URL, pool_pre_ping=True, echo=settings.APP_ENV == "development"
)

# SessionFactory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Base Model Class
class Base(DeclarativeBase):
    pass


# Dependency for FastAPI Endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
