# Project Status — Investment Assistant

> **Este é o ledger detalhado task-a-task** (exigido pelo AGENTS.md §94): notas de implementação, validações executadas e decisões datadas. Continue atualizando-o ao concluir cada task.
>
> Para **retomar o trabalho**, comece por [../CLAUDE.md](../CLAUDE.md) → [memory/PROJECT_STATUS.md](memory/PROJECT_STATUS.md) (estado atual em uma página) → [memory/CURRENT_TASK.md](memory/CURRENT_TASK.md).

## Project Overview
Plataforma pessoal de análise e acompanhamento de investimentos com foco no mercado brasileiro (B3), acompanhamento patrimonial, recomendações quantitativas de aportes, análise de risco e módulo de Day Trade com Paper Trading.

---

## Current Phase
- **Phase**: Wave 05 (Market Data Integration) -> Wave 06 (Fundamental Data)
- **Status**: 🟡 IN_PROGRESS

---

## Overall Progress
- **Total Waves**: 33 (W00 a W32)
- **Completed Waves**: 6 (W00, W01, W02, W03, W04, W05)
- **In Progress Waves**: 0
- **Pending Waves**: 27

---

## Environment Status
- **Operating System**: Windows (PowerShell)
- **Node.js**: Disponível (Scaffold Frontend React+TS+Vite concluído em `frontend/`)
- **Python**: 3.11+ / 3.14 (Virtualenv `.venv` configurado em `backend/`)
- **Docker / Docker Compose**: Configurado em `docker-compose.yml` (validado com `docker compose config`)
- **PostgreSQL**: Configurado em `docker-compose.yml` com Alembic Migrations

---

## Infrastructure Status
- **`git`**: Inicializado
- **`.gitignore`**: 🟢 COMPLETED
- **`.env.example`**: 🟢 COMPLETED
- **`.env`**: 🟢 COMPLETED
- **`docker-compose.yml`**: 🟢 COMPLETED
- **`README.md`**: 🟢 COMPLETED
- **`backend/`**: 🟢 COMPLETED (FastAPI + Pydantic v2 + SQLAlchemy 2.0 + Alembic + Health Endpoints)
- **`frontend/`**: 🟢 COMPLETED (React + TS + Vite + Tailwind CSS + App Dashboard)

---

## Architecture Status
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS (`frontend/`) 🟢 COMPLETED
- **Backend**: FastAPI + Python 3.11/3.14 + Pydantic v2 + Uvicorn (`backend/`) 🟢 COMPLETED
- **Quant Engine**: NumPy + Pandas + SciPy (Wave 07) ⚪ NOT_STARTED
- **Portfolio Engine**: CRUD de carteiras/ativos, ledger de transações, motor de posições (custo médio/saldo) determinístico (`backend/app/domain/portfolio`) 🟢 COMPLETED (Wave 04)
- **Market Data Integration**: `MarketDataProvider`/`BrapiProvider`, ingestão diária com caching e Data Quality Validator (`backend/app/integrations/market_data`, `backend/app/domain/market_data`) 🟢 COMPLETED (Wave 05)
- **Database**: PostgreSQL 16 + SQLAlchemy 2.0 Models + Alembic (001 + 002 `NUMERIC` money columns) (`backend/app/data/models`) 🟢 COMPLETED
- **AI Integration**: Abstração `AIProvider` (Gemini / Ollama) (Wave 12) ⚪ NOT_STARTED

---

## Waves & Task Breakdown

### Wave 00 — Produto & Especificação (Foundation)
Status: 🟢 COMPLETED

- [x] **W00-001**: Repositório Git & Estrutura Base 🟢 COMPLETED
- [x] **W00-002**: Configuração de Ambiente (`.gitignore`, `.env.example`, `.env`) 🟢 COMPLETED
- [x] **W00-003**: Containerização Base (`docker-compose.yml`) 🟢 COMPLETED
- [x] **W00-004**: Documentação Técnica (`README.md`, `AGENTS.md`) 🟢 COMPLETED
- [x] **W00-005**: Sistema de Tracking (`docs/PROJECT_STATUS.md`) 🟢 COMPLETED

Definition of Done Wave 00:
- Repositório clonável, configurado com arquivos de ambiente, docker-compose básico, README e plano operacional rastreável.

---

### Wave 01 — Foundation & Scaffold
Status: 🟢 COMPLETED

- [x] **W01-001**: Scaffold do Backend FastAPI (`backend/`, `pyproject.toml`, `main.py`, `/health`, `/ready`) 🟢 COMPLETED
- [x] **W01-002**: Scaffold do Frontend React+TS+Vite (`frontend/`, `package.json`, `index.html`, `App.tsx`, Tailwind) 🟢 COMPLETED
- [x] **W01-003**: Dockerfiles para Backend e Frontend e validação no Docker Compose (`docker compose config`) 🟢 COMPLETED
- [x] **W01-004**: Validação de inicialização completa de ambiente e testes automatizados Pytest 🟢 COMPLETED

---

### Wave 02 — Database Schema & Migrations
Status: 🟢 COMPLETED

- [x] **W02-001**: Configuração SQLAlchemy 2.0 e Alembic no Backend (`backend/app/data/database.py`, `alembic.ini`) 🟢 COMPLETED
- [x] **W02-002**: Implementação dos Models das 13 tabelas essenciais (`users`, `investor_profiles`, `portfolios`, `assets`, `asset_prices`, `intraday_prices`, `fundamentals`, `financial_indicators`, `transactions`, `portfolio_snapshots`, `recommendations`, `daytrade_setups`, `daytrade_results`) 🟢 COMPLETED
- [x] **W02-003**: Migration Inicial Alembic (`001_initial_schema.py`) e testes de schema SQLAlchemy (`3 passed`) 🟢 COMPLETED
- [x] **W02-004** (correção pós-conclusão, 2026-08-16): Migration `002_numeric_money_columns.py` convertendo `transactions.quantity/price/fees` e `asset_prices.open/high/low/close/adjusted_close` de `FLOAT` para `NUMERIC(18,6)`, e os models SQLAlchemy correspondentes para `Decimal`. Ver Technical Decisions — "Monetary precision" abaixo. 🟢 COMPLETED

---

### Wave 03 — Authentication & Users
Status: 🟢 COMPLETED

- [x] **W03-001**: Hashing de senha (bcrypt) e Tokens JWT (`backend/app/core/security.py`) 🟢 COMPLETED
- [x] **W03-002**: Endpoints de Cadastro, Login, Refresh Token e Me 🟢 COMPLETED
- [x] **W03-003**: Dependencies de Autenticação e Proteção de Rotas (`get_current_user`) 🟢 COMPLETED

Detalhes:
- `backend/app/core/security.py`: hashing de senha com `bcrypt` (não Passlib — ver Technical Decisions) e criação/validação de JWT com `PyJWT`.
- `backend/app/domain/users/schemas.py`: `UserCreate`, `UserLogin`, `UserResponse`, `Token`, `TokenPayload` (Pydantic v2, `EmailStr` via `email-validator`).
- `backend/app/api/routes/auth.py`: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `GET /api/v1/auth/me`.
- `backend/app/api/dependencies.py`: `get_current_user` (valida Bearer JWT, carrega o usuário via SQLAlchemy) usado para proteger `/me` e `/refresh`.
- `backend/app/main.py`: exception handler global padronizando erros da API no formato `{"error": {"code", "message"}}` (regra 72 do AGENTS.md), e registro do router de auth.
- Testes: `backend/tests/test_security.py` (7 casos: hash/verify, criação/decodificação/expiração/tamper de JWT) e `backend/tests/test_auth.py` (11 casos de integração via `TestClient` + SQLite in-memory compartilhado em `backend/tests/conftest.py`).
- `pyproject.toml`: dependências corrigidas para refletir o que é realmente importado (`pyjwt`, `bcrypt`, `email-validator`), removendo `passlib`/`python-jose` que nunca chegaram a ser usados; adicionada configuração mínima de `[tool.ruff]` (ignora `B008`, falso positivo para o padrão `Depends(...)` do FastAPI).
- Validação: `pytest` 21/21 passed; `ruff check` limpo nos arquivos da wave; `black --check` limpo nos arquivos da wave.

Definition of Done Wave 03: atendida — hashing seguro, JWT determinístico, endpoints de auth cobertos por testes de integração, rotas protegidas via `get_current_user`, sem regressão nos testes pré-existentes (health, models).

---

### Wave 04 — Portfolio Management
Status: 🟢 COMPLETED

- [x] **W04-001**: Endpoints CRUD de Carteiras e Ativos 🟢 COMPLETED
- [x] **W04-002**: Registro de Transações (BUY, SELL, DIVIDEND, DEPOSIT, WITHDRAWAL) 🟢 COMPLETED
- [x] **W04-003**: Motor de Posições Consolidadas (Preço Médio e Saldo) 🟢 COMPLETED

Detalhes W04-001:
- `backend/app/domain/assets/schemas.py`: `AssetCreate` (normaliza ticker para maiúsculas), `AssetResponse`.
- `backend/app/domain/portfolio/schemas.py`: `PortfolioCreate`, `PortfolioUpdate`, `PortfolioResponse` (schemas de transação/posições já definidos aqui, mas usados só a partir de W04-002/003).
- `backend/app/api/routes/assets.py`: `POST/GET /api/v1/assets`, `GET /api/v1/assets/{ticker}` — cadastro de ativos apenas para acompanhamento (sem integração com corretora), protegido por `get_current_user`.
- `backend/app/api/routes/portfolios.py`: CRUD completo de `/api/v1/portfolios` (`POST`, `GET` lista, `GET` por id, `PATCH`, `DELETE`), todos escopados ao usuário autenticado — acessar/alterar carteira de outro usuário retorna 404 (não 403), para não vazar quais IDs existem.
- `backend/app/main.py`: registro dos routers `assets` e `portfolios`.
- Testes: `backend/tests/test_assets.py` (6 casos) e `backend/tests/test_portfolios.py` (6 casos), incluindo isolamento entre usuários.
- Validação: `pytest` 33/33 passed; `ruff check` e `black --check` limpos nos arquivos da task.

Detalhes W04-002:
- `backend/app/domain/portfolio/service.py`: `compute_positions`/`compute_asset_quantity`/`compute_net_contributions` — motor de posições determinístico (moving-average cost method), derivado 100% do ledger de transações (regra 16 do AGENTS.md), sem tabela própria de posições.
- `backend/app/api/routes/portfolios.py`: `POST/GET /api/v1/portfolios/{id}/transactions`. Valida existência do ativo, exige `asset_id` só para BUY/SELL/DIVIDEND (schema `TransactionCreate`), e bloqueia SELL que exceda a quantidade atualmente detida (`INSUFFICIENT_POSITION`, 422) — usa `compute_asset_quantity` sobre o histórico já registrado.
- Convenção documentada: valor monetário de qualquer transação = `quantity × price` (fees separado); DEPOSIT/WITHDRAWAL não têm `asset_id` (fluxo de caixa no nível da carteira).
- Testes: `backend/tests/test_transactions.py` (9 casos): auth obrigatória, criação de BUY/DEPOSIT, 404 em carteira/ativo alheios ou inexistentes, validação de `asset_id` por tipo, guarda de venda insuficiente, venda até o limite permitida, ordenação cronológica na listagem.
- Nota: `status.HTTP_422_UNPROCESSABLE_ENTITY` está depreciado nesta versão do Starlette; usado `HTTP_422_UNPROCESSABLE_CONTENT`.
- Validação: `pytest` 42/42 passed; `ruff check` e `black --check` limpos nos arquivos da task.

Detalhes W04-003:
- `backend/app/api/routes/portfolios.py`: `GET /api/v1/portfolios/{id}/positions`, expondo `compute_positions`/`compute_net_contributions` — retorna posição por ativo (quantidade, preço médio, valor investido, P&L realizado, dividendos recebidos) e totais da carteira. Não inclui valor de mercado atual (depende da Wave 05 — Market Data, ainda não implementada).
- Testes: `backend/tests/test_portfolio_service.py` (11 casos unitários do motor com valores conhecidos — regra 68 do AGENTS.md: preço médio ponderado em compras múltiplas, venda parcial mantém preço médio e realiza P&L, venda total zera a posição mas preserva P&L histórico, dividendos não afetam quantidade/preço médio, posições independentes por ativo, replay respeita ordem cronológica mesmo com input fora de ordem, posição zerada sem P&L/dividendos é omitida, `compute_net_contributions`) e `backend/tests/test_positions.py` (4 casos de integração via HTTP).
- Validação: `pytest` 56/56 passed; `ruff check` e `black --check` limpos nos arquivos da task.

Definition of Done Wave 04: atendida — CRUD de carteiras/ativos, ledger de transações com validação de integridade (venda não pode exceder posição), motor de posições determinístico e testável com casos conhecidos, sem cálculo financeiro no frontend (ainda não implementado), sem regressão nos testes das waves anteriores.

---

### Wave 05 — Market Data Integration
Status: 🟢 COMPLETED

- [x] **W05-001**: Abstração `MarketDataProvider` e integração Brapi 🟢 COMPLETED
- [x] **W05-002**: Ingestão de Cotizações Diárias e Caching 🟢 COMPLETED
- [x] **W05-003**: Data Quality Validator (validação de outliers/nulos) 🟢 COMPLETED

Detalhes W05-001:
- `backend/app/integrations/market_data/base.py`: interface abstrata `MarketDataProvider` (`get_quote`, `get_daily_history`) — domínio depende só desta abstração, nunca de um SDK/HTTP client concreto (regra 21 do AGENTS.md).
- `backend/app/integrations/market_data/schemas.py`: DTOs `DailyBar`/`Quote` (Pydantic — validação automática de tipos/campos obrigatórios de dados externos não confiáveis, regra 19).
- `backend/app/integrations/market_data/exceptions.py`: `TickerNotFoundError`, `MarketDataUnavailableError`, `InvalidMarketDataResponseError`.
- `backend/app/integrations/market_data/brapi.py`: `BrapiProvider`, implementação concreta via `httpx`. Timeout configurável, retry limitado com backoff exponencial só para falhas transitórias (timeout/erro de conexão/HTTP 429/500/502/503/504 — nunca retry infinito), 404 falha imediatamente, throttle opcional entre requisições (`MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS`) para respeitar rate limit do provedor gratuito.
- `backend/app/core/config.py`: `BRAPI_BASE_URL`, `MARKET_DATA_TIMEOUT_SECONDS`, `MARKET_DATA_MAX_RETRIES`, `MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS`.
- **Caveat importante**: o parser foi escrito com base na documentação pública da Brapi (`results[0].regularMarketPrice`, `results[0].historicalDataPrice[]`), mas só foi exercitado contra respostas HTTP mockadas (`httpx.MockTransport`) — não há acesso de rede de saída neste ambiente. Precisa ser validado contra uma resposta real da Brapi antes de ser usado em ingestão de produção (mesma ressalva já registrada para a migration `002_numeric_money_columns`).
- Testes: `backend/tests/test_brapi_provider.py` (15 casos): parsing de quote/histórico com sucesso, 404 -> `TickerNotFoundError`, campo obrigatório ausente/nulo -> `InvalidMarketDataResponseError`, JSON inválido, filtro de datas, `adjustedClose` ausente cai para `close`, retry em erro 5xx/timeout transitório com sucesso subsequente, falha definitiva após esgotar tentativas, erro não-retryable (4xx) falha imediatamente sem retry, e throttle de intervalo mínimo entre requisições.
- Validação: `pytest` 71/71 passed; `ruff check` e `black --check` limpos nos arquivos da task (exceto os `__init__.py` vazios, que replicam um padrão de estilo pré-existente no repositório — já registrado em Future Work).

Detalhes W05-002:
- `backend/app/integrations/market_data/factory.py`: `build_market_data_provider()` — seleciona a implementação concreta a partir de `settings.MARKET_DATA_PROVIDER` (padrão análogo ao `AIProvider`, regras 21/40 do AGENTS.md).
- `backend/app/api/dependencies.py`: dependency `get_market_data_provider` (FastAPI `Depends`) que instancia e fecha o provider por request; testes sobrescrevem com um fake via `app.dependency_overrides`, sem tocar rede.
- `backend/app/domain/market_data/schemas.py`: `PriceSyncRequest`, `PriceSyncResponse`, `AssetPriceResponse`.
- `backend/app/domain/market_data/service.py`: `sync_daily_history` — busca o histórico via `MarketDataProvider`, insere apenas datas ainda não armazenadas (nunca sobrescreve histórico existente — regra 20 do AGENTS.md) e retorna contagem de buscados/inseridos/ignorados.
- `backend/app/api/routes/assets.py`: `POST /api/v1/assets/{ticker}/prices/sync` (único endpoint que chama o provedor externo; mapeia `TickerNotFoundError`->404, `MarketDataUnavailableError`->503, `InvalidMarketDataResponseError`->502) e `GET /api/v1/assets/{ticker}/prices` (lê exclusivamente do banco — nunca consulta a API externa, regra 23 do AGENTS.md; suporta filtro `start`/`end`). Data "hoje" default calculada em UTC explícito (regra 18).
- Testes: `backend/tests/test_market_data_service.py` (4 casos unitários com SQLite in-memory: insere tudo quando vazio, ignora datas já armazenadas sem sobrescrever, idempotência ao rodar duas vezes, respeita a janela solicitada) e `backend/tests/test_market_data_routes.py` (9 casos de integração via HTTP com provider fake: auth obrigatória, 404 para ativo não cadastrado, sync + leitura comprovando que o read-path nunca chama o provider — inclusive com um provider que lançaria `AssertionError` se fosse chamado —, idempotência via API, mapeamento de cada erro do provider para o código HTTP correto, filtro de datas na leitura).
- Validação: `pytest` 84/84 passed; `ruff check` e `black --check` limpos nos arquivos da task (mesma ressalva de estilo pré-existente nos `__init__.py` vazios).

Detalhes W05-003:
- `backend/app/integrations/market_data/data_quality.py`: `validate_daily_bars(bars) -> DataQualityReport` — função pura e determinística, sem I/O. Rejeita (`errors`): preço não-positivo (`NON_POSITIVE_PRICE`), volume negativo (`INVALID_VOLUME`, defesa em profundidade — o schema `DailyBar` já impede isso na construção normal), OHLC inconsistente (`INVALID_OHLC`, exatamente o exemplo da regra 20: `low<=open`, `low<=close`, `high>=open`, `high>=close`, `low<=high`) e datas duplicadas no lote (`DUPLICATE_DATE`, ambas as ocorrências rejeitadas). Sinaliza como aviso, sem rejeitar (`warnings`): lote fora de ordem cronológica (`OUT_OF_ORDER`) e variação diária absurda >50% (`ABSURD_MOVE`, heurística documentada — splits/eventos legítimos podem mover preço assim).
- `backend/app/domain/market_data/service.py`: `sync_daily_history` agora roda `validate_daily_bars` antes de inserir; barras rejeitadas nunca chegam ao banco e populam `PriceSyncResult.rejected`; erros/avisos são logados (nunca silenciados — regra 122 do AGENTS.md).
- Testes: `backend/tests/test_data_quality.py` (10 casos unitários com valores conhecidos) e um caso adicional em `backend/tests/test_market_data_service.py` comprovando que uma barra inválida misturada com uma válida é rejeitada e não é persistida.
- Validação: `pytest` 95/95 passed; `ruff check` e `black --check` limpos nos arquivos da task.

Definition of Done Wave 05: atendida — provider abstraído e testável sem rede real, ingestão idempotente com cache real (leitura nunca chama a API externa), validação de qualidade de dados determinística e testada com casos conhecidos, erros do provedor mapeados para códigos HTTP corretos, sem regressão nas waves anteriores. Pendência conhecida e documentada: parser da Brapi não verificado contra resposta real (sem rede neste ambiente).

---

### Wave 06 — Fundamental Data
Status: ⚠️ NEEDS_REVIEW — as duas tasks planejadas estão concluídas, mas o resultado é parcial: 6 dos 10 indicadores são estruturalmente `None` por falta de insumo. Ver W06-003.

- [x] **W06-001**: Ingestão de Demonstrativos Financeiros 🟢 COMPLETED
- [x] **W06-002**: Cálculo e Normalização de Indicadores Fundamentalistas 🟢 COMPLETED
- [ ] **W06-003**: Captação dos insumos faltantes (shares outstanding, EBIT, proventos) ⚪ NOT_STARTED — task criada nesta wave, não prevista no roadmap original

Detalhes W06-001:
- `backend/app/integrations/http.py` (novo): `RetryingJsonClient` — transporte HTTP compartilhado com timeout, retry limitado com backoff exponencial só em falha transitória (timeout/conexão/429/5xx), falha imediata em 4xx e throttle de rate limit. As classes de exceção são injetadas, então cada integração mantém seu próprio vocabulário de erro. Extraído do `BrapiProvider` (regra 8 do AGENTS.md — não reimplementar o que já existe) em vez de copiar o loop de retry para o segundo provedor; ver Technical Decisions.
- `backend/app/integrations/market_data/brapi.py`: migrado para o transporte compartilhado. Mudança puramente mecânica — nenhuma alteração de comportamento; os 15 testes pré-existentes do `BrapiProvider` continuam passando (4 deles tiveram apenas o alvo do `patch` de `time.sleep`/`time.monotonic` repontado de `...market_data.brapi.time` para `...integrations.http.time`, já que é lá que o `sleep` passou a morar; nenhuma asserção foi alterada ou enfraquecida).
- `backend/app/integrations/fundamentals/`: `base.py` (`FundamentalsProvider`, ABC), `schemas.py` (`FinancialStatement`, todos os itens de linha opcionais), `exceptions.py`, `brapi.py` (`BrapiFundamentalsProvider`), `factory.py`, `data_quality.py`.
- `backend/app/domain/fundamentals/`: `schemas.py` + `service.py` (`sync_annual_statements`) — mesma forma de `sync_daily_history`: busca → valida → insere só o que ainda não existe → retorna `fetched/inserted/skipped_existing/rejected`.
- `backend/app/api/dependencies.py`: `get_fundamentals_provider`.
- `backend/app/api/routes/assets.py`: `POST /api/v1/assets/{ticker}/fundamentals/sync` (único endpoint que chama o provedor; mapeia `FundamentalsNotFoundError`→404, `FundamentalsUnavailableError`→503, `InvalidFundamentalsResponseError`→502) e `GET /api/v1/assets/{ticker}/fundamentals` (lê só do banco, filtro `start`/`end` sobre `reference_date`).
- `backend/app/core/config.py`: `FUNDAMENTALS_PROVIDER`, `FUNDAMENTALS_TIMEOUT_SECONDS` (15s — demonstrativos são payloads maiores), `FUNDAMENTALS_MAX_RETRIES`, `FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS`.
- `backend/app/data/models/fundamentals.py` + `backend/migrations/versions/003_numeric_fundamentals_columns.py`: colunas monetárias de `fundamentals` convertidas de `Float` para `NUMERIC(24,4)`/`Decimal`. Ver Technical Decisions.
- Data quality (`validate_financial_statements`, função pura e determinística, `today` injetável): rejeita `DUPLICATE_REFERENCE_DATE` (ambas as ocorrências), `FUTURE_REFERENCE_DATE`, `EMPTY_STATEMENT` (nenhum valor reportado) e `NEGATIVE_VALUE` em `revenue`/`debt`/`cash`. **Não** rejeita lucro líquido, patrimônio líquido ou FCF negativos — são resultados reais e informativos. Avisa `INCOMPLETE_STATEMENT` sem bloquear.
- Testes (+45): `test_brapi_fundamentals_provider.py` (17), `test_fundamentals_data_quality.py` (12), `test_fundamentals_service.py` (8), `test_fundamentals_routes.py` (8, incluindo um `ExplodingProvider` que falha se o read-path chamar o provedor).
- Validação: `pytest` 140/140 passed; `ruff check` e `black --check` limpos em todos os arquivos da task. `alembic heads`/`history` resolvem `003` corretamente.
- **Caveat**: como no W05-001, o parser foi escrito a partir da documentação pública da Brapi e exercitado só contra `httpx.MockTransport` — sem rede neste ambiente. Nomes de módulo (`incomeStatementHistory`, `balanceSheetHistory`), aninhamento e nomes de campo **não** foram confirmados contra resposta real.

Detalhes W06-002:
- **Conferência de insumos antes de implementar** revelou que o escopo original da task era inviável como escrito: `pe`/`pb` precisam de `shares_outstanding` e `dy` precisa de histórico de proventos — nada disso existe no schema; `roic` precisa de EBIT e alíquota; `debt_ebitda`/`ebitda_margin` precisam de EBITDA (bloqueado pelo ADR-013). Levado ao usuário; escolhida a opção de manter o escopo original (zero requisições à Brapi) e abrir W06-003 para os insumos.
- `backend/app/domain/fundamentals/indicators.py`: `IndicatorInputs` / `IndicatorSet` / `compute_indicators` — função pura, determinística, sem I/O, cálculo em `Decimal` convertido para `float` só na fronteira (a coluna é `Float` por decisão, ADR-003). As **10 fórmulas estão implementadas e testadas**; as que dependem de insumo ausente retornam `None` e passam a produzir valor assim que o insumo chegar (há teste provando isso para cada uma).
- Política de dado faltante: `None` = não computável, nunca zero; denominador zero → `None`, nunca exceção nem infinito; crescimento sobre base negativa ou zero → `None`; ROIC não presume alíquota. Registrado como ADR-014.
- `backend/app/domain/fundamentals/service.py`: `compute_and_store_indicators` — idempotente por `(asset_id, reference_date)`, não recomputa período já gravado; um período pulado ainda serve de base para o crescimento do período seguinte. `_price_on_or_before` seleciona o fechamento **na data de referência ou anterior mais próxima**, nunca posterior (regra 108) — quatro testes cobrem essa invariante, inclusive escopo por ativo.
- `backend/app/api/routes/assets.py`: `POST /api/v1/assets/{ticker}/indicators/compute` (**não** chama provedor externo — só transforma dado armazenado) e `GET /api/v1/assets/{ticker}/indicators`.
- Testes (+44): `test_fundamental_indicators.py` (25 casos com valores conhecidos), `test_indicators_service.py` (12), `test_indicators_routes.py` (7).
- Validação: `pytest` 184/184 passed; `ruff check` e `black --check` limpos nos arquivos da task. **Zero requisições à API da Brapi nesta task.**

Detalhes W06-003 (a fazer):
- Captar `shares_outstanding` (módulo `defaultKeyStatistics`), `ebit` (já vem em `incomeStatementHistory`, apenas não mapeado) e histórico de proventos. Módulos extras entram no **mesmo** `GET /quote`, então não aumentam a contagem de requisições — só o tamanho do payload.
- Exige migration `004` (colunas novas em `fundamentals`) e alteração do `BrapiFundamentalsProvider`.
- Deliberadamente adiada até haver como validar contra a API real: hoje nenhum mapeamento de campo da Brapi foi confirmado, e empilhar mais campos especulativos aumenta a superfície não verificada.

---

### Wave 07 — Quant Engine — Returns & Risk
Status: ⚪ NOT_STARTED

- [ ] **W07-001**: Módulo `returns.py` (Daily, Monthly, CAGR) ⚪ NOT_STARTED
- [ ] **W07-002**: Módulo `risk.py` (Volatilidade, Beta, Drawdown, Sharpe, Sortino) ⚪ NOT_STARTED
- [ ] **W07-003**: Testes Unitários dos Cálculos Financeiros ⚪ NOT_STARTED

---

### Wave 08 — Benchmark Engine
Status: ⚪ NOT_STARTED

- [ ] **W08-001**: Ingestão das Séries Históricas de CDI, IBOV e IPCA ⚪ NOT_STARTED
- [ ] **W08-002**: Comparativo de Rentabilidade Carteira vs Benchmarks ⚪ NOT_STARTED

---

### Wave 09 — Portfolio Recommendation Engine
Status: ⚪ NOT_STARTED

- [ ] **W09-001**: Sub-scores Quantitativos (Quality, Valuation, Growth, Risk, Diversification) ⚪ NOT_STARTED
- [ ] **W09-002**: Algoritmo de Alocação de Aporte Mensal (~R$ 1.000) ⚪ NOT_STARTED

---

### Wave 10 — Portfolio Rebalancing Engine
Status: ⚪ NOT_STARTED

- [ ] **W10-001**: Cálculo de Target Weights e Weight Gaps ⚪ NOT_STARTED
- [ ] **W10-002**: Restrições Quantitativas para Perfil Conservador ⚪ NOT_STARTED

---

### Wave 11 — Dashboard & Main Interface
Status: ⚪ NOT_STARTED

- [ ] **W11-001**: Dashboard Principal (Patrimônio, Rentabilidade, Benchmarks) ⚪ NOT_STARTED
- [ ] **W11-002**: Interface de Gestão de Carteira e Histórico ⚪ NOT_STARTED
- [ ] **W11-003**: Página Detalhada do Ativo com Indicadores ⚪ NOT_STARTED

---

### Wave 12 — AI Engine Integration
Status: ⚪ NOT_STARTED

- [ ] **W12-001**: Abstração `AIProvider` (`GeminiProvider`, `OllamaProvider`) ⚪ NOT_STARTED
- [ ] **W12-002**: Geração de Explicações em Linguagem Natural ⚪ NOT_STARTED

---

### Wave 13 — Portfolio Backtesting Engine
Status: ⚪ NOT_STARTED

- [ ] **W13-001**: Motor de Simulação Histórica de Aportes ⚪ NOT_STARTED
- [ ] **W13-002**: Geração de Métricas de Performance do Backtest ⚪ NOT_STARTED

---

### Wave 14 — Walk-Forward Validation
Status: ⚪ NOT_STARTED

- [ ] **W14-001**: Implementação de Janelas Móveis e Validação Out-of-Sample ⚪ NOT_STARTED

---

### Wave 15 — Day Trade — Intraday Data
Status: ⚪ NOT_STARTED

- [ ] **W15-001**: Ingestão e Armazenamento de Velas Intraday (1m, 5m, 15m) ⚪ NOT_STARTED

---

### Wave 16 — Day Trade Engine — Setups
Status: ⚪ NOT_STARTED

- [ ] **W16-001**: Indicadores Intraday (VWAP, EMA 9/21, RSI, ATR, Relative Volume) ⚪ NOT_STARTED
- [ ] **W16-002**: Avaliadores de Setups (Breakout, Pullback, VWAP) ⚪ NOT_STARTED

---

### Wave 17 — Day Trade Risk Engine
Status: ⚪ NOT_STARTED

- [ ] **W17-001**: Sizing de Posição, Stop Loss e Alvo R/R ⚪ NOT_STARTED
- [ ] **W17-002**: Circuit Breaker Diário (Bloqueio de Perda Diária) ⚪ NOT_STARTED

---

### Wave 18 — Day Trade Dashboard
Status: ⚪ NOT_STARTED

- [ ] **W18-001**: Interface de Sinais Day Trade e Candidatos ⚪ NOT_STARTED

---

### Wave 19 — Day Trade Backtesting
Status: ⚪ NOT_STARTED

- [ ] **W19-001**: Backtesting Histórico de Setups Intraday ⚪ NOT_STARTED

---

### Wave 20 — Paper Trading
Status: ⚪ NOT_STARTED

- [ ] **W20-001**: Módulo de Execução Simulada e Rastreamento de Sinais ⚪ NOT_STARTED

---

### Wave 21 — Automated Testing Suite
Status: ⚪ NOT_STARTED

- [ ] **W21-001**: Suíte Integrada de Testes Unitários e E2E ⚪ NOT_STARTED

---

### Wave 22 — Advanced Frontend
Status: ⚪ NOT_STARTED

- [ ] **W22-001**: Gráficos Interativos, Comparadores e Filtros ⚪ NOT_STARTED

---

### Wave 23 — Observability & Logging
Status: ⚪ NOT_STARTED

- [ ] **W23-001**: Logging Estruturado e Healthchecks Avançados ⚪ NOT_STARTED

---

### Wave 24 — Security Hardening
Status: ⚪ NOT_STARTED

- [ ] **W24-001**: CORS, Rate Limit, Secrets Management ⚪ NOT_STARTED

---

### Wave 25 — Docker Production Setup
Status: ⚪ NOT_STARTED

- [ ] **W25-001**: Dockerfiles de Produção e Reverse Proxy Nginx ⚪ NOT_STARTED

---

### Wave 26 — CI/CD Pipeline
Status: ⚪ NOT_STARTED

- [ ] **W26-001**: Workflows do GitHub Actions para Lint, Test e Build ⚪ NOT_STARTED

---

### Wave 27 — Production Deploy
Status: ⚪ NOT_STARTED

- [ ] **W27-001**: Provisionamento e Deploy (Vercel / Render / Cloud) ⚪ NOT_STARTED

---

### Wave 28 — Production Migrations Strategy
Status: ⚪ NOT_STARTED

- [ ] **W28-001**: Pipeline de Aplicação de Migrations com Backup ⚪ NOT_STARTED

---

### Wave 29 — Backup & Disaster Recovery
Status: ⚪ NOT_STARTED

- [ ] **W29-001**: Automação de Backup do Banco PostgreSQL ⚪ NOT_STARTED

---

### Wave 30 — Extended Paper Trading
Status: ⚪ NOT_STARTED

- [ ] **W30-001**: Validação de Longo Prazo em Paper Trading ⚪ NOT_STARTED

---

### Wave 31 — System Validation & Audit
Status: ⚪ NOT_STARTED

- [ ] **W31-001**: Auditoria de Métricas Quantitativas e Segurança ⚪ NOT_STARTED

---

### Wave 32 — Release V1.0
Status: ⚪ NOT_STARTED

- [ ] **W32-001**: Documentação Final e Lançamento Oficial V1.0 ⚪ NOT_STARTED

---

## Current Task

Wave: 06
Task ID: W06-003
Task Name: Captação dos insumos faltantes para indicadores (shares outstanding, EBIT, proventos)
Status: ⚪ NOT_STARTED — bloqueada por falta de acesso de rede para validar o mapeamento de campos

Completed:
- Wave 00 (Foundation) concluída.
- Wave 01 (Scaffold Backend & Frontend + Pytest + Docker Config) concluída.
- Wave 02 (Database Schema & Migrations) concluída (13 tabelas criadas no SQLAlchemy 2.0 + Migration Alembic `001_initial_schema.py` + 3 testes passando).
- Wave 03 (Authentication & Users) concluída (hashing bcrypt + JWT, endpoints register/login/refresh/me, `get_current_user`, 18 testes novos passando).
- Correção de precisão monetária pós-Wave 02 (`Float` -> `NUMERIC(18,6)`/`Decimal` em `transactions` e `asset_prices`, migration `002_numeric_money_columns.py`), decidida com o usuário.
- Wave 04 (Portfolio Management) concluída — CRUD de carteiras/ativos, transações, motor de posições. 36 testes novos passando.
- Wave 05 (Market Data Integration) concluída — `MarketDataProvider`/`BrapiProvider`, ingestão diária com caching, Data Quality Validator. 39 testes novos passando.
- W06-001 (Ingestão de Demonstrativos Financeiros) concluída — `FundamentalsProvider`/`BrapiFundamentalsProvider`, transporte HTTP compartilhado, ingestão anual idempotente, data quality de demonstrativos, migration `003`. 45 testes novos passando.
- W06-002 (Indicadores Fundamentalistas) concluída — `compute_indicators` puro com as 10 fórmulas, seleção de preço sem look-ahead, persistência idempotente, endpoints de compute/leitura. 44 testes novos passando.

Remaining (Wave 06 — Fundamental Data):
- W06-003: captar `shares_outstanding`, `ebit` e histórico de proventos, para destravar `pe`, `pb`, `dy` e `roic`. Bloqueada por falta de acesso de rede para confirmar o mapeamento de campos.

Next Action:
Duas opções, a critério do usuário:
1. **W06-003**, se houver como validar o mapeamento de campos contra a API real da Brapi (o custo em requisições é zero — módulos extras vão no mesmo `GET /quote`).
2. **Wave 07 (Quant Engine)**, que não depende dos indicadores faltantes: `returns.py` e `risk.py` consomem `asset_prices`, já ingerido e disponível.

A Wave 09 (Recommendation Engine) é que depende de verdade dos 6 indicadores inertes — até lá há caminho livre.

---

## Completed Tasks
- **W00-001**: Repositório Git & Estrutura Base (🟢 COMPLETED)
- **W00-002**: Configuração de Ambiente (`.gitignore`, `.env.example`, `.env`) (🟢 COMPLETED)
- **W00-003**: Containerização Base (`docker-compose.yml`) (🟢 COMPLETED)
- **W00-004**: Documentação Técnica (`README.md`, `AGENTS.md`) (🟢 COMPLETED)
- **W00-005**: Sistema de Tracking (`docs/PROJECT_STATUS.md`) (🟢 COMPLETED)
- **W01-001**: Scaffold do Backend FastAPI (🟢 COMPLETED)
- **W01-002**: Scaffold do Frontend React+TS+Vite (🟢 COMPLETED)
- **W01-003**: Dockerfiles & Docker Compose Config (🟢 COMPLETED)
- **W01-004**: Pytest Healthcheck Execution (🟢 COMPLETED)
- **W02-001**: Configuração SQLAlchemy 2.0 e Alembic (🟢 COMPLETED)
- **W02-002**: Implementação dos Models das 13 tabelas (🟢 COMPLETED)
- **W02-003**: Migration Inicial Alembic (`001_initial_schema.py`) (🟢 COMPLETED)
- **W03-001**: Hashing de Senha (bcrypt) e Tokens JWT (🟢 COMPLETED)
- **W03-002**: Endpoints de Cadastro, Login, Refresh Token e Me (🟢 COMPLETED)
- **W03-003**: Dependencies de Autenticação e Proteção de Rotas (`get_current_user`) (🟢 COMPLETED)
- **W04-001**: Endpoints CRUD de Carteiras e Ativos (🟢 COMPLETED)
- **W04-002**: Registro de Transações (BUY, SELL, DIVIDEND, DEPOSIT, WITHDRAWAL) (🟢 COMPLETED)
- **W04-003**: Motor de Posições Consolidadas (Preço Médio e Saldo) (🟢 COMPLETED)
- **W05-001**: Abstração `MarketDataProvider` e integração Brapi (🟢 COMPLETED)
- **W05-002**: Ingestão de Cotações Diárias e Caching (🟢 COMPLETED)
- **W05-003**: Data Quality Validator (validação de outliers/nulos) (🟢 COMPLETED)
- **W06-001**: Ingestão de Demonstrativos Financeiros (🟢 COMPLETED)
- **W06-002**: Cálculo e Normalização de Indicadores Fundamentalistas (🟢 COMPLETED)

---

## In Progress
Nenhuma tarefa em progresso no momento. Wave 05 concluída. Próxima: W06-001 (Wave 06 — Fundamental Data).

---

## Blocked Tasks
Nenhuma tarefa bloqueada no momento.

---

## Known Issues
- **6 dos 10 indicadores fundamentalistas são estruturalmente `None`** (`pe`, `pb`, `dy`, `roic`, `debt_ebitda`, `ebitda_margin`) por falta de insumo. Comportamento correto e testado, mas limita a Wave 09. Endereçado pela W06-003.
- **Throttle de requisições desligado por padrão**: `MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS` e `FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS` têm default `0.0`, ou seja, sem espaçamento entre chamadas. A Brapi tem cota mensal limitada no plano gratuito. Definir um intervalo no `.env` antes de qualquer ingestão em lote.

---

## Technical Decisions

### Decision — 2026-08-09
- **Decision**: Adotar PostgreSQL como banco principal e FastAPI para o backend.
- **Reason**: Consistência relacional para transações financeiras e alta performance com Python para computação quantitativa.
- **Status**: 🟢 APPROVED

### Decision — 2026-08-09
- **Decision**: Separar estritamente Quant Engine (cálculos determinísticos no backend) de AI Engine (apenas explicações/contextualizações).
- **Reason**: Cumprimento do Princípio Fundamental de `AGENTS.md` (evitar alucinações da IA em métricas quantitativas).
- **Status**: 🟢 APPROVED

### Decision — 2026-08-16
- **Decision**: Usar `bcrypt` (hashing) e `PyJWT` (tokens) diretamente em `backend/app/core/security.py`, em vez de `passlib[bcrypt]`/`python-jose[cryptography]` originalmente declarados em `pyproject.toml`.
- **Reason**: `passlib` está sem manutenção ativa e `python-jose` nunca chegou a ser importado pelo código; `bcrypt` e `PyJWT` são as libs mantidas e efetivamente usadas, evitando dependências fantasma (regra 92 do AGENTS.md).
- **Status**: 🟢 APPROVED

### Decision — 2026-08-16
- **Decision**: Adotar um exception handler global em `backend/app/main.py` para todo `HTTPException`, padronizando o corpo de erro da API como `{"error": {"code", "message"}}`.
- **Reason**: Regra 72 do AGENTS.md exige respostas de erro consistentes; sem o handler, FastAPI aninha `detail` e cada rota poderia divergir no formato.
- **Status**: 🟢 APPROVED

### Decision — 2026-08-16
- **Decision**: Endpoint `/api/v1/auth/refresh` reemite um novo access token a partir de um token de acesso ainda válido (via `get_current_user`), sem refresh token dedicado/rotacionado.
- **Reason**: Roadmap trata refresh token como "se necessário"; um fluxo simples de reemissão atende a Wave 03 sem introduzir complexidade de armazenamento/rotação de refresh tokens antes de haver necessidade real (regra 101 do AGENTS.md). Pode evoluir para refresh token dedicado em wave futura de segurança (W24) se necessário.
- **Status**: 🟢 APPROVED

### Decision — 2026-08-16 — Monetary precision
- **Decision**: Ao iniciar a Wave 04, identificado que `transactions.quantity/price/fees` e `asset_prices.open/high/low/close/adjusted_close` usavam `Float` no SQLAlchemy, violando a regra 17 do AGENTS.md. Consultado o usuário (decisão arquitetural sobre schema já commitado da Wave 02, não inferida automaticamente); optou-se por migrar agora para `NUMERIC(18,6)`/`Decimal` em vez de aceitar como débito técnico.
- **Implementation**: `backend/migrations/versions/002_numeric_money_columns.py` (Alembic, revises `001_initial_schema`) + models atualizados (`app/data/models/portfolio.py`, `app/data/models/assets.py`, constante `MONEY = Numeric(18, 6)`). `volume` permanece `Float` (não é valor monetário). Teste de regressão em `backend/tests/test_models.py` garante que os valores retornam como `Decimal`, não `float`.
- **Escopo explicitamente fora desta correção (Future Work)**: `intraday_prices` OHLC (pertence à Wave 15), `portfolio_snapshots.total_value/cash_value` e `investor_profiles.monthly_contribution` continuam `Float` — serão convertidos quando as waves que os utilizam (11 e 09) forem implementadas.
- **Caveat de validação**: a migration foi escrita manualmente (mesmo padrão de `001_initial_schema.py`) e validada apenas estruturalmente (`alembic heads`/`history` resolvem corretamente; suíte de testes passa contra SQLite in-memory). **Não foi aplicada contra um PostgreSQL real** — o Docker Desktop não estava em execução neste ambiente. É obrigatório rodar `alembic upgrade head` contra Postgres (via `docker compose up`) antes de considerar esta migration definitivamente validada em produção/dev real, conforme regra 14 do AGENTS.md ("autogenerate/migration não é infalível, deve ser revisada").
- **Status**: 🟢 APPROVED (implementação); ⚠️ aplicação em Postgres real ainda pendente de verificação.

### Decision — 2026-08-17 — Fundamentals monetary precision: `NUMERIC(24,4)`
- **Decision**: Converter as colunas monetárias de `fundamentals` (`revenue`, `ebitda`, `net_income`, `equity`, `debt`, `cash`, `free_cash_flow`) de `Float` para `NUMERIC(24,4)`/`Decimal` (migration `003_numeric_fundamentals_columns`). `financial_indicators` permanece `Float`.
- **Reason**: Mesma motivação da regra 17 do AGENTS.md que originou a migration `002`. Consultado o usuário (mesma classe de decisão arquitetural que foi escalada em 2026-08-16, não inferida automaticamente); optou-se por converter agora, com a tabela ainda vazia, em vez de acumular dívida. Precisão diferente da constante `MONEY` (18,6) porque os valores são agregados de companhia inteira na casa das centenas de bilhões de BRL, o que consumiria quase todos os 12 dígitos inteiros de `NUMERIC(18,6)`; `NUMERIC(24,4)` deixa folga ampla e 4 casas decimais excedem o que qualquer demonstrativo reporta. `financial_indicators` guarda razões e taxas de crescimento (P/L, ROE, margens), não moeda — a regra 17 permite float onde adequado desde que a decisão seja registrada, e está registrada aqui e em `app/data/models/fundamentals.py`.
- **Caveat de validação**: mesma ressalva da `002` — migration escrita manualmente, validada estruturalmente (`alembic heads`/`history`) e contra SQLite in-memory. **Não aplicada contra PostgreSQL real.**
- **Status**: 🟢 APPROVED (implementação); ⚠️ aplicação em Postgres real ainda pendente.

### Decision — 2026-08-17 — Transporte HTTP compartilhado entre integrações
- **Decision**: Extrair o loop de timeout/retry/backoff/throttle do `BrapiProvider` para `app/integrations/http.py` (`RetryingJsonClient`), parametrizado pelas classes de exceção de cada integração, e usá-lo tanto no market data quanto no fundamentals.
- **Reason**: Regra 8 do AGENTS.md (não reimplementar o que já existe). A alternativa era copiar ~60 linhas de lógica de resiliência para o segundo provedor — e depois para intraday (W15) e IA (W12), chegando a quatro cópias. A extração é mecânica e os 15 testes pré-existentes do `BrapiProvider` funcionaram como rede de segurança (continuam passando sem alteração de asserção).
- **Escopo**: mudança de estrutura, não de comportamento. Nenhum parâmetro, código HTTP ou exceção mudou de semântica.
- **Status**: 🟢 APPROVED. Registrado como `docs/decisions/ADR-012`.

### Decision — 2026-08-17 — Fundamentals: só anual, e restatement não sobrescreve
- **Decision**: (a) Ingerir apenas demonstrativos **anuais**; (b) nunca sobrescrever um `reference_date` já armazenado, mesmo que o provedor passe a servir um valor reexpresso; (c) não preencher `ebitda`/`free_cash_flow` a partir do módulo `financialData` da Brapi.
- **Reason**: (a) `fundamentals` identifica a linha por `(asset_id, reference_date)` e não tem coluna de período — um exercício anual encerrado em 31/12 e o 4º trimestre reportam a mesma data-fim e virariam duas linhas indistinguíveis. (b) Substituir o valor armazenado reescreveria o que o sistema "sabia" à época e corromperia qualquer análise point-in-time (regras 108/109); tratar reexpressão corretamente exige schema que comporte múltiplas versões do mesmo período. (c) `financialData` é um snapshot TTM sem data-fim de período; atribuí-lo a um `reference_date` histórico seria exatamente o look-ahead que a regra 109 proíbe, e derivar EBITDA/FCF depende de convenções de sinal não verificáveis sem resposta real — um número silenciosamente errado é pior que um `NULL` honesto (regra 44).
- **Status**: 🟢 APPROVED. Registrado como `docs/decisions/ADR-013`.

### Decision — 2026-08-17 — Brapi parser not yet verified live
- **Decision**: Implementar `BrapiProvider` (W05-001) com base na documentação pública da Brapi, testado exclusivamente contra respostas HTTP mockadas (`httpx.MockTransport`), sem acesso de rede de saída neste ambiente.
- **Reason**: Regra 124 do AGENTS.md ("quando não souber, explicar a incerteza") — não há como validar contra a API real sem rede; a alternativa (não implementar) bloquearia toda a Wave 05. Preferi implementar de forma defensiva (nunca assumir campo presente, regra 19) e documentar claramente a lacuna, em vez de fingir que foi validado.
- **Status**: 🟢 APPROVED (implementação); ⚠️ verificação contra resposta real da Brapi ainda pendente antes de uso em ingestão de produção.

---

## Future Work
- Cache com Redis para cotações em tempo real.
- Suporte a WebSocket para streamings intraday.
- Modelos avançados de otimização de portfólio (Markowitz / Black-Litterman).
- Verificar/aplicar `alembic upgrade head` (migration `002_numeric_money_columns`) contra um PostgreSQL real assim que o Docker/`docker compose up` estiver disponível — não foi possível validar neste ambiente (Docker Desktop parado).
- Converter `intraday_prices` OHLC para `NUMERIC` na Wave 15; `portfolio_snapshots.total_value/cash_value` na Wave 11; `investor_profiles.monthly_contribution` na Wave 09 (mesma motivação da regra 17 do AGENTS.md, deliberadamente fora do escopo da correção de 2026-08-16).
- Validar `BrapiProvider` (`backend/app/integrations/market_data/brapi.py`) contra uma resposta real da API assim que houver acesso de rede — os nomes de campo (`regularMarketPrice`, `historicalDataPrice`, etc.) foram inferidos da documentação pública, não de uma chamada real.
- Lint: `ruff check` aponta findings pré-existentes (anteriores a esta sessão) em arquivos não tocados nas Waves 03/04/05 (`app/data/models/fundamentals.py`, `users.py`, `daytrade.py`, `recommendations.py`, `app/core/logging.py`, `app/data/database.py`, `app/api/routes/health.py`, `tests/test_health.py`) — majoritariamente import-sorting e `Optional`/`List` → `X | None`/`list`. Além disso, os `__init__.py` vazios do projeto (`app/domain/__init__.py`, `app/domain/users/__init__.py`, e agora `app/integrations/__init__.py`, `app/integrations/market_data/__init__.py`) usam `""` como conteúdo, o que dispara `D419`/reformatação do `black` — padrão pré-existente replicado por consistência. Não corrigido agora por estar fora do escopo das tasks em andamento (regra 134 do AGENTS.md); considerar uma task dedicada de lint cleanup.

---

## Last Execution
- **Timestamp**: 2026-08-17T00:00:00-03:00
- **Action**: W06-002 (Wave 06) — cálculo de indicadores fundamentalistas: `compute_indicators` (função pura com as 10 fórmulas), `compute_and_store_indicators` idempotente, `_price_on_or_before` sem look-ahead, endpoints `POST /indicators/compute` e `GET /indicators`. Escopo confirmado com o usuário após a descoberta de que 6 indicadores carecem de insumo; criada a task W06-003.
- **Result**: Sucesso. 184/184 testes passando (`pytest`), `ruff check` e `black --check` limpos nos arquivos da task. Nenhuma regressão. **Zero requisições à API da Brapi.**

---

## Next Action
Decidir entre W06-003 (destravar os 6 indicadores, requer validação do mapeamento de campos contra a API real) e Wave 07 — Quant Engine (`returns.py`/`risk.py`, sem dependência dos indicadores faltantes). Ver `docs/memory/CURRENT_TASK.md`.
