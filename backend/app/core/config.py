from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# `.env` lives at the repository root, next to docker-compose.yml. Anchoring
# it to this file instead of to the process working directory is deliberate:
# a relative "env_file" is resolved against the cwd, so running anything from
# `backend/` (pytest, alembic, a validation script) silently loaded no file at
# all and left BRAPI_TOKEN empty - requests went out unauthenticated with no
# error to show for it. Under docker compose the variables are injected into
# the environment directly and no file is read either way.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ROOT_ENV_FILE = _PROJECT_ROOT / ".env"

# A `.env` in the current directory still wins when one exists: later entries
# take precedence in pydantic-settings, which keeps per-checkout overrides
# working without reintroducing the silent-empty failure as the default.
ENV_FILES: tuple[Path | str, ...] = (_ROOT_ENV_FILE, ".env")


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
    # Largest history range the account's Brapi plan actually serves. The
    # free plan stops at "3mo" and answers HTTP 400 INVALID_RANGE beyond it,
    # so asking for more only spends a request to be refused. Every range is
    # anchored at today (the API takes no start date), which makes this a
    # hard ceiling on how far back history can reach - not a page size.
    BRAPI_MAX_RANGE: str = "3mo"

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

    # Open historical prices from B3's COTAHIST series (PRICE-001).
    # Free, no token, no quota - and it reaches back decades, where the
    # market data vendor's free plan stops at ~63 sessions. Delivered as
    # one ZIP per calendar year holding every instrument B3 lists, ~79 MB
    # for 2024, of which the spot market is under a tenth; the archive is
    # distilled on download and cached, so a year is fetched at most once.
    HISTORICAL_PRICE_PROVIDER: str = "b3_cotahist"
    B3_COTAHIST_BASE_URL: str = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist"
    B3_COTAHIST_CACHE_DIR: str = "var/b3"
    # A year archive is tens of megabytes over a link that is not fast;
    # this is a whole-file download, not an API call, hence the minutes.
    B3_COTAHIST_TIMEOUT_SECONDS: float = 600.0
    B3_COTAHIST_MAX_RETRIES: int = 3
    # Earliest calendar year to pull. Each year is another download and
    # another few megabytes on disk once distilled.
    B3_COTAHIST_FIRST_YEAR: int = 2015

    # Corporate action magnitudes (EVENTS-003). The archive above counts
    # distributions and never sizes them; this is B3's own listed-company
    # service, which publishes reais per share and split factors, open and
    # without a token. It is the JSON backend of B3's public pages rather
    # than a published data product, so it sits behind
    # `CorporateActionProvider` and nothing outside that adapter knows its
    # shape (ADR-026).
    CORPORATE_ACTION_PROVIDER: str = "b3_events"
    B3_EVENTS_BASE_URL: str = (
        "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall"
    )
    B3_EVENTS_TIMEOUT_SECONDS: float = 30.0
    B3_EVENTS_MAX_RETRIES: int = 3
    # A full payout history is paginated, so one sync is a handful of
    # calls in a row against a service that publishes no rate limit.
    # Spacing them is politeness, and cheap: a sync is a manual operation.
    B3_EVENTS_MIN_REQUEST_INTERVAL_SECONDS: float = 0.2

    # Benchmarks (Wave 08). The CDI/IPCA/Selic come from the Banco
    # Central's SGS API, which is open, needs no token and enforces no
    # quota - but it is noticeably slower than Brapi, and a multi-decade
    # backfill is split into one request per decade, so the timeout is
    # more generous and throttling stays available.
    BCB_SGS_BASE_URL: str = "https://api.bcb.gov.br/dados/serie"
    BENCHMARK_TIMEOUT_SECONDS: float = 30.0
    BENCHMARK_MAX_RETRIES: int = 3
    BENCHMARK_MIN_REQUEST_INTERVAL_SECONDS: float = 0.0

    # AI Engine (Wave 12). The model explains numbers the backend already
    # computed and never produces one of its own (ADR-009), so none of
    # these settings can change a figure anywhere in the system - the
    # worst a bad value here does is leave the explanation unavailable.
    #
    # "gemini" is the hosted default; "ollama" points at a local server
    # and needs no key, which is what keeps the architecture from
    # depending on one proprietary API (AGENTS.md rule 42). "none"
    # disables explanations outright, and is the honest setting for a
    # deployment that has no credential - better than a provider that
    # fails on every call.
    AI_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    #: Alias rather than a pinned build, so the vendor's current fast
    #: model is used without an edit here. The model that actually
    #: answered is echoed back on every `Completion` and recorded on the
    #: `Explanation`, which is what keeps the audit trail exact even
    #: though the request is not.
    GEMINI_MODEL: str = "gemini-flash-latest"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"

    AI_TIMEOUT_SECONDS: float = 60.0
    AI_MAX_RETRIES: int = 3
    AI_MIN_REQUEST_INTERVAL_SECONDS: float = 0.0
    #: Low, not zero. Text is exempt from the determinism rule (113)
    #: because it feeds no calculation, but an explanation that rewords
    #: itself on every refresh reads as unreliable.
    AI_TEMPERATURE: float = 0.2
    #: Three short paragraphs, which is what the prompts ask for, with
    #: room to spare. A truncated explanation comes back with a
    #: finish_reason saying so rather than silently ending mid-sentence.
    AI_MAX_OUTPUT_TOKENS: int = 1024

    model_config = SettingsConfigDict(
        case_sensitive=True, env_file=ENV_FILES, extra="ignore"
    )


settings = Settings()
