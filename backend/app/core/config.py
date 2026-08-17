from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Investment Assistant API"
    APP_ENV: str = "development"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "dev_secret_key_change_in_production_12345"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days

    POSTGRES_DB: str = "investment_assistant"
    POSTGRES_USER: str = "investment_user"
    POSTGRES_PASSWORD: str = "investment_pass_dev"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = (
        "postgresql://investment_user:investment_pass_dev@localhost:5432/investment_assistant"
    )

    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    MARKET_DATA_PROVIDER: str = "brapi"
    BRAPI_TOKEN: str = ""
    BRAPI_BASE_URL: str = "https://brapi.dev/api"
    MARKET_DATA_TIMEOUT_SECONDS: float = 10.0
    MARKET_DATA_MAX_RETRIES: int = 3
    # Minimum delay enforced between outbound requests to the market data
    # provider, to respect free-tier rate limits (AGENTS.md rule 22/23).
    # 0 disables throttling (default: local/dev usage).
    MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS: float = 0.0

    AI_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""

    model_config = SettingsConfigDict(
        case_sensitive=True, env_file=".env", extra="ignore"
    )


settings = Settings()
