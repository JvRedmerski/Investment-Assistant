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

    # Fundamentals ingestion is far lower-frequency than price ingestion
    # (statements change quarterly, not daily), but it shares the same
    # provider and therefore the same rate limit — hence its own knobs.
    # "cvm_then_brapi" merges both: the CVM leads, the vendor backs it
    # up for assets the CVM has no filer for. "cvm" and "brapi" select
    # a single source.
    FUNDAMENTALS_PROVIDER: str = "cvm_then_brapi"
    FUNDAMENTALS_TIMEOUT_SECONDS: float = 15.0
    FUNDAMENTALS_MAX_RETRIES: int = 3
    FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS: float = 0.0

    # Fundamentals from the CVM open data portal (Wave 09). Free, no
    # token, no quota - but delivered as one ~13 MB ZIP per fiscal year
    # covering every listed company, so the archive is cached on disk and
    # a year is downloaded at most once.
    CVM_DFP_BASE_URL: str = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS"
    CVM_CACHE_DIR: str = "var/cvm"
    CVM_TIMEOUT_SECONDS: float = 180.0
    CVM_MAX_RETRIES: int = 3
    # Earliest fiscal year to read. Each additional year is another
    # download and another ~13 MB on disk; five years is enough for the
    # growth indicators, which compare consecutive periods.
    CVM_FIRST_YEAR: int = 2020

    # Benchmarks (Wave 08). The CDI/IPCA/Selic come from the Banco
    # Central's SGS API, which is open, needs no token and enforces no
    # quota - but it is noticeably slower than Brapi, and a multi-decade
    # backfill is split into one request per decade, so the timeout is
    # more generous and throttling stays available.
    BCB_SGS_BASE_URL: str = "https://api.bcb.gov.br/dados/serie"
    BENCHMARK_TIMEOUT_SECONDS: float = 30.0
    BENCHMARK_MAX_RETRIES: int = 3
    BENCHMARK_MIN_REQUEST_INTERVAL_SECONDS: float = 0.0

    AI_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""

    model_config = SettingsConfigDict(
        case_sensitive=True, env_file=".env", extra="ignore"
    )


settings = Settings()
