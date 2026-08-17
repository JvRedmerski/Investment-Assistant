# Backend Architecture

> Camada 2. Leia quando a task tocar o backend.
> Estado em 2026-08-17. Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0.

## Estrutura real

```
backend/
├── app/
│   ├── main.py                 App FastAPI, CORS, exception handler global, registro de routers
│   ├── api/
│   │   ├── dependencies.py     get_current_user · get_market_data_provider
│   │   └── routes/             health · auth · assets · portfolios
│   ├── core/
│   │   ├── config.py           Settings (pydantic-settings, lê .env) → singleton `settings`
│   │   ├── security.py         hash/verify de senha (bcrypt) · create/decode de JWT (PyJWT)
│   │   └── logging.py          setup_logging()
│   ├── domain/                 users · portfolio · assets · market_data · fundamentals
│   │   └── <área>/             schemas.py (Pydantic) + service.py (regra de negócio)
│   ├── integrations/
│   │   ├── http.py             RetryingJsonClient — transporte compartilhado (retry/throttle)
│   │   ├── market_data/        base · schemas · exceptions · brapi · factory · data_quality
│   │   └── fundamentals/       mesma estrutura de cinco peças
│   └── data/
│       ├── database.py         engine · SessionLocal · Base · get_db · utc_now
│       └── models/             users · assets · portfolio · fundamentals · recommendations · daytrade
├── migrations/versions/        001_initial_schema · 002_numeric_money_columns
├── tests/                      plano, sem subpastas
├── pyproject.toml              deps + config de pytest/ruff
└── alembic.ini
```

**Ainda não existem** (previstos no AGENTS.md §6, waves futuras): `app/quant/`, `app/workers/`, `app/domain/recommendations/`, `app/domain/daytrade/`, `app/integrations/{intraday,ai}/`, `app/data/repositories/`.

## Fluxo de uma requisição

```
HTTP → CORSMiddleware
     → rota (api/routes/*.py)
        ├─ Depends(get_current_user)   → 401 se JWT inválido/expirado/órfão
        ├─ Depends(get_db)             → Session por request, fechada no finally
        ├─ Depends(get_<x>_provider)   → integração externa, fechada no finally
        ├─ Pydantic valida o body      → 422 automático do FastAPI
        ├─ resolve ownership           → 404 se não pertencer ao usuário
        ├─ chama domain/<área>/service.py
        └─ retorna response_model
     → HTTPException?  → handler global em main.py → {"error":{"code","message"}}
```

## Padrões a seguir

### 1. Toda integração externa atrás de uma interface abstrata
`integrations/<área>/base.py` define a ABC; `factory.py` escolhe a implementação a partir de `settings.<X>_PROVIDER`; `dependencies.py` expõe como `Depends`. Domínio e rotas **só** conhecem o tipo abstrato. Testes substituem via `app.dependency_overrides` — nunca mockam `httpx`. (AGENTS.md §21, [ADR-004](../decisions/ADR-004-market-data-provider-abstraction.md))

A resiliência HTTP não é reescrita por provedor: `integrations/http.py` (`RetryingJsonClient`) concentra timeout, retry limitado, backoff e throttle, recebendo as classes de exceção de cada integração. Um provedor concreto escreve apenas URL e parsing. ([ADR-012](../decisions/ADR-012-shared-http-transport.md))

### 2. Dado externo validado duas vezes
DTO Pydantic na fronteira (tipos/obrigatoriedade) **e** validador de qualidade de domínio (regras de negócio: OHLC coerente, preço positivo, duplicidade). O validador é uma função pura, sem I/O, testada com valores conhecidos. (AGENTS.md §19/§20)

### 3. Falha de integração é explícita e tipada
`integrations/<área>/exceptions.py` define exceções próprias (`TickerNotFoundError`, `MarketDataUnavailableError`, `InvalidMarketDataResponseError`). A rota — e só ela — traduz para HTTP:

| Exceção | HTTP | code |
|---|---|---|
| `TickerNotFoundError` | 404 | `MARKET_DATA_TICKER_NOT_FOUND` |
| `MarketDataUnavailableError` | 503 | `MARKET_DATA_UNAVAILABLE` |
| `InvalidMarketDataResponseError` | 502 | `MARKET_DATA_INVALID_RESPONSE` |
| `FundamentalsNotFoundError` | 404 | `FUNDAMENTALS_NOT_FOUND` |
| `FundamentalsUnavailableError` | 503 | `FUNDAMENTALS_UNAVAILABLE` |
| `InvalidFundamentalsResponseError` | 502 | `FUNDAMENTALS_INVALID_RESPONSE` |

Retry é **limitado** e só para falhas transitórias (timeout, erro de conexão, HTTP 429/5xx) com backoff exponencial; 4xx falha imediatamente. Nunca retry infinito. (AGENTS.md §22)

### 4. Dinheiro é `Decimal`
Colunas monetárias são `NUMERIC(18,6)` (constante `MONEY` em `data/models/portfolio.py` e `assets.py`); schemas usam `Decimal`; cálculos somam `Decimal`, nunca `float`. (AGENTS.md §17, [ADR-003](../decisions/ADR-003-decimal-money.md))

### 5. Timezone explícito
`utc_now()` em `data/database.py` para defaults; `datetime.now(UTC).date()` quando a rota precisa de "hoje". Nunca `datetime.now()` sem tz. (AGENTS.md §18)

### 6. Erro nunca é silenciado
Rejeições de qualidade de dados são logadas (`logger.warning`) e contabilizadas na resposta (`rejected`), não descartadas em silêncio. (AGENTS.md §122)

## Autenticação

- `core/security.py`: `bcrypt` para hash de senha, `PyJWT` HS256 para tokens. Sem passlib, sem python-jose ([ADR-006](../decisions/ADR-006-bcrypt-pyjwt.md)).
- JWT carrega `sub` = user id (string). `decode_access_token` retorna `None` em token inválido/expirado.
- `get_current_user` (em `api/dependencies.py`): decodifica, converte `sub` para int, carrega o `User`; qualquer falha → 401 `INVALID_CREDENTIALS` com header `WWW-Authenticate: Bearer`.
- `POST /auth/refresh` reemite a partir de um access token **ainda válido**; não há refresh token dedicado ([ADR-008](../decisions/ADR-008-refresh-without-refresh-token.md)).
- `OAuth2PasswordBearer` é usado só para o botão *Authorize* do Swagger; a autenticação real é o header Bearer.

## Configuração

Tudo em `core/config.py` (`pydantic-settings`, `env_file=".env"`, `case_sensitive=True`, `extra="ignore"`), exposto como singleton `settings`. Nunca leia `os.environ` diretamente; nunca hardcode secret.

Grupos: app (`APP_NAME`, `APP_ENV`, `API_V1_STR`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`) · banco (`DATABASE_URL`, `POSTGRES_*`) · CORS · market data (`MARKET_DATA_PROVIDER`, `BRAPI_TOKEN`, `BRAPI_BASE_URL`, `MARKET_DATA_TIMEOUT_SECONDS`, `MARKET_DATA_MAX_RETRIES`, `MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS`) · fundamentals (`FUNDAMENTALS_PROVIDER`, `FUNDAMENTALS_TIMEOUT_SECONDS`, `FUNDAMENTALS_MAX_RETRIES`, `FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS` — knobs próprios porque a cadência é diferente, ainda que o fornecedor e o rate limit sejam os mesmos) · IA (`AI_PROVIDER`, `GEMINI_API_KEY`, ainda não usados).

## Testes

- `tests/conftest.py`: engine SQLite in-memory único (`StaticPool`), compartilhado pela sessão; `app.dependency_overrides[get_db]`; fixture autouse cria e derruba o schema a cada teste; fixture `client` = `TestClient`.
- Integração externa é substituída por fake via `dependency_overrides` — **nenhum teste toca a rede**. O teste de read-path chega a injetar um provider que lança `AssertionError` se chamado, provando que a leitura não consulta a API.
- Testes de cálculo financeiro usam valores conhecidos, não apenas "não explode" (AGENTS.md §68).
- Para interceptar `time.sleep`/`time.monotonic` do laço de retry, faça patch em `app.integrations.http.time` (não no módulo do provedor).
- Baseline: **140 passed**.

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check <arquivos alterados>
.venv\Scripts\python.exe -m black --check <arquivos alterados>
```

`ruff` está configurado com `line-length = 100`, `ignore = ["B008"]` (falso positivo do `Depends()`), `F821` ignorado em `data/models/*` (referências `Mapped["X"]` resolvidas em runtime) e `UP007/UP035` em `migrations/versions/*` (template do Alembic).

## Pontos de atenção para alterações futuras

- **Não** introduza um segundo padrão de acesso a dados sem antes ler [ADR-011](../decisions/ADR-011-no-repository-layer.md).
- **Não** chame provedor externo fora de um endpoint de sync explícito.
- Ao criar um novo domínio, replique exatamente o par `schemas.py` + `service.py`; o service recebe `Session` como parâmetro, não a cria.
- `main.py` registra o router de health **duas vezes** (em `/` e em `/api/v1`) — intencional: o frontend consome `/api/v1/health` e o Docker healthcheck usa `/health`.
