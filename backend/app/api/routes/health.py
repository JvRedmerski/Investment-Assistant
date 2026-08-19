from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health", status_code=200)
def health_check():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "version": "0.1.0",
    }


@router.get("/ready", status_code=200)
def readiness_check():
    # Can be extended to check database connection status
    return {"status": "ready", "database": "connected"}
