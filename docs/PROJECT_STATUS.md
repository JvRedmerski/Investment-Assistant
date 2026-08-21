# Project Status — Investment Assistant

> **Este é o ledger detalhado task-a-task** (exigido pelo AGENTS.md §94): notas de implementação, validações executadas e decisões datadas. Continue atualizando-o ao concluir cada task.
>
> Para **retomar o trabalho**, comece por [../CLAUDE.md](../CLAUDE.md) → [memory/PROJECT_STATUS.md](memory/PROJECT_STATUS.md) (estado atual em uma página) → [memory/CURRENT_TASK.md](memory/CURRENT_TASK.md).

## Project Overview
Plataforma pessoal de análise e acompanhamento de investimentos com foco no mercado brasileiro (B3), acompanhamento patrimonial, recomendações quantitativas de aportes, análise de risco e módulo de Day Trade com Paper Trading.

---

## Current Phase
- **Phase**: wave **EVENTS** (eventos societários e proventos) em andamento — segunda wave **inserida fora da ordem do roadmap**, entre a W09 e a W10
- **Status**: 🟡 **WAVE 10 IN_PROGRESS** (2026-08-21) — 1 de 3 tasks: W10-001 entregou o peso-alvo, derivado do **mérito** e não do `final_score` ([ADR-027](decisions/ADR-027-target-weight-comes-from-merit.md)). Antes dela: 🟢 EVENTS COMPLETED (2026-08-20) — **3 de 3 tasks**: EVENTS-001 (distribuições por exercício, da DMPL da CVM — fechou o `dy`), EVENTS-002 (data e natureza do evento societário, pelo arquivo de fim de dia da B3) e EVENTS-003 (a **magnitude**, pelo serviço aberto de eventos da B3, e o `adjusted_close` derivado dela — **destravou o pilar de Risco**). A wave **PRICE** (3 tasks) fechou antes, em 2026-08-19. A **Wave 10 — Rebalanceamento** está em curso, de volta à ordem do roadmap

---

## Overall Progress
- **Total Waves**: 33 (W00 a W32)
- **Completed Waves**: 10 do roadmap (W00 a W09) + 1 inserida (PRICE)
- **In Progress Waves**: 1 inserida (EVENTS, 2/3 tasks)
- **Pending Waves**: 23

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
- **`frontend/`**: 🟡 SCAFFOLD (React + TS + Vite + Tailwind CSS — uma página estática de status; **não é dashboard de produto**)

---

## Architecture Status

> `🟢 COMPLETED` aqui significa **entregue na wave correspondente**, não "produto acabado".
> O frontend é o caso que mais confunde e por isso está marcado à parte.

- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS (`frontend/`) 🟡 SCAFFOLD — landing page única, sem rotas, sem estado, nenhuma capacidade do backend exposta em tela. Primeira wave de frontend real: **W11**
- **Backend**: FastAPI + Python 3.11/3.14 + Pydantic v2 + Uvicorn (`backend/`) 🟢 COMPLETED
- **Quant Engine**: retorno e risco em `decimal.Decimal` puro, sem I/O (`backend/app/quant`) 🟢 COMPLETED (Wave 07) — **NumPy/Pandas/SciPy não foram adotados**, decisão revogada no adendo ao [ADR-017](decisions/ADR-017-annualisation-and-numeric-type.md)
- **Portfolio Engine**: CRUD de carteiras/ativos, ledger de transações, motor de posições (custo médio/saldo) determinístico (`backend/app/domain/portfolio`) 🟢 COMPLETED (Wave 04)
- **Market Data Integration**: duas fontes atrás de interfaces separadas — `MarketDataProvider`/`BrapiProvider` (cota ao vivo e ajusta, ~63 pregões no plano gratuito) e `DailyHistoryProvider`/`B3CotahistProvider` (série COTAHIST aberta da B3, sem cota, décadas de histórico). Ingestão diária idempotente com caching e Data Quality Validator (`backend/app/integrations/market_data`, `backend/app/domain/market_data`) 🟢 COMPLETED (Wave 05 e wave PRICE). Uma terceira interface, `CorporateEventProvider`, responde **em que pregão o papel foi ex** e sob qual **ISIN/classe** — data e natureza, nunca magnitude (EVENTS-002, [ADR-025](decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md)); é lida do arquivo a cada sync, de propósito, porque serve de **verificação de completude**. Uma quarta, `CorporateActionProvider`/`B3CorporateActionProvider`, carrega a **magnitude** e é o que permite derivar `adjusted_close` (EVENTS-003, [ADR-026](decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md))
- **Fundamentals Integration**: CVM (fonte primária) + Brapi (ponte ticker→CNPJ), fontes compostas (`backend/app/integrations/fundamentals`) 🟢 COMPLETED (Waves 06 e 09; `dividends_paid` da DMPL na EVENTS-001, que fechou o último indicador sem insumo)
- **Benchmark Engine**: CDI/Selic/IPCA pelo BCB-SGS e IBOV pelo provedor de market data; comparativo time-weighted (`backend/app/domain/benchmarks`) 🟢 COMPLETED (Wave 08)
- **Recommendation Engine**: sub-scores decomponíveis e alocação do aporte mensal (`backend/app/domain/recommendations`) 🟢 COMPLETED (Wave 09)
- **Database**: PostgreSQL 16 + SQLAlchemy 2.0 Models + Alembic (`001` … `011_dividends_paid`) (`backend/app/data/models`) 🟢 COMPLETED
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
Status: 🟢 COMPLETED — parsers validados contra a API real, dois bugs de mapeamento corrigidos, ROIC destravado. 5 dos 10 indicadores produzem valor; os 5 restantes têm limitação documentada e evidenciada, não suposta.

- [x] **W06-001**: Ingestão de Demonstrativos Financeiros 🟢 COMPLETED
- [x] **W06-002**: Cálculo e Normalização de Indicadores Fundamentalistas 🟢 COMPLETED
- [x] **W06-003**: Validação contra a API real, correção do mapeamento e captação de insumos 🟢 COMPLETED

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

Detalhes W06-003:
- **Havia acesso de rede nesta sessão** (não havia nas anteriores). Gasta **1 requisição** à Brapi (`GET /quote/PETR4` com `range`, `interval` e três módulos de uma vez), suficiente para validar tudo. Resposta salva no scratchpad e usada offline no restante do trabalho.
- **Parsers de market data (W05-001) confirmados corretos.** `regularMarketPrice`, `regularMarketTime`, `currency` e as chaves de `historicalDataPrice` (`date` epoch, OHLC, `volume`, `adjustedClose`) conferem exatamente. Lacuna aberta desde a Wave 05 — fechada, sem necessidade de correção.
- **Dois bugs encontrados no parser de fundamentals (W06-001)**, ambos silenciosos:
  - `equity` lia `totalStockholderEquity` → **null em 16/16 períodos**. Campo correto: `shareholdersEquity`. Como `roe` e o capital investido dependem de `equity`, **`roe` era `None` em dados reais** — a task anterior reportou "4 indicadores funcionando", quando na prática eram 3.
  - `debt` lia `totalDebt` (inexistente) com fallback para `shortLongTermDebt` + `longTermDebt` → **null em 16/16**. Agora soma as seis linhas efetivamente reportadas (empréstimos, debêntures e arrendamentos, curto e longo prazo), todas 16/16.
- **`cleanEbitda` é idêntico a `ebit` nos 16 períodos** — não é EBITDA. Mapeá-lo teria colocado número errado atrás de `debt_ebitda` e `ebitda_margin`. `ebitda` permanece `NULL`, agora por evidência. Corrige a justificativa do ADR-013.
- **ROIC destravado**: `ebit`, `incomeBeforeTax` e `incomeTaxExpense` são reportados 16/16. Alíquota efetiva derivada por período. O campo `cleanNopat` da Brapi foi **descartado** porque aplica 34% fixos, enquanto as alíquotas reais vão de 26,6% a 32,4%.
- **Bug encontrado só ao rodar contra dados reais**: em 2020 a Petrobras teve imposto **positivo** (crédito de R$ 6,2 bi) contra R$ 37 mi de lucro antes de impostos. O `abs()` original transformava crédito em ônus e gerava alíquota de 16.780%, produzindo **ROIC de −1096%**. Corrigido: sinal tratado corretamente e alíquota fora de [0, 1] retorna `None` (ADR-014, item 4).
- **Filtro `type == "yearly"`**: as linhas trazem discriminador de período; o parser agora filtra explicitamente em vez de assumir.
- **Política de recomputação (ADR-015)**: `POST /assets/{ticker}/indicators/compute?recompute=true` reconstrói os indicadores do ativo. Necessário porque os valores gravados pela W06-002 estavam errados (equity nula). Fatos reportados nunca são tocados; só valores derivados.
- `backend/migrations/versions/004_fundamentals_income_detail.py`: `ebit`, `income_before_tax`, `income_tax_expense` em `NUMERIC(24,4)`, nullable.
- **`pe`, `pb`, `dy` permanecem `None`**: `sharesOutstanding` e `dividendYield` existem, mas só como snapshots atuais sem data-fim de período. Aplicar a contagem de ações de hoje a um balanço de 2010 seria atribuir fato presente a período passado (regras 108/109).
- Testes (+21, total 205), incluindo `test_regression_against_the_real_petr4_response`, que trava o mapeamento verificado com os números reais de 2025.
- Verificação de ponta a ponta sobre a resposta real: 16 períodos parseados, 0 rejeitados; ROE 26,5%, ROIC 10,7%, margem líquida 22,2% em 2025 — valores plausíveis; 2020 corretamente `None`.
- Validação: `pytest` 205/205; `ruff check` e `black --check` limpos. `alembic heads` → `004`.

---

### Wave 07 — Quant Engine — Returns & Risk
Status: ⚪ NOT_STARTED

- [ ] **W07-001**: Módulo `returns.py` (Daily, Monthly, CAGR) ⚪ NOT_STARTED
- [ ] **W07-002**: Módulo `risk.py` (Volatilidade, Beta, Drawdown, Sharpe, Sortino) ⚪ NOT_STARTED
- [ ] **W07-003**: Testes Unitários dos Cálculos Financeiros ⚪ NOT_STARTED

---

### Wave 08 — Benchmark Engine
Status: 🟢 COMPLETED

- [x] **W08-001**: Ingestão das Séries Históricas de CDI, IBOV e IPCA 🟢 COMPLETED
- [x] **W08-002**: Comparativo de Rentabilidade Carteira vs Benchmarks 🟢 COMPLETED

---

### Wave 09 — Portfolio Recommendation Engine
Status: 🟢 COMPLETED

- [x] **W09-001**: Sub-scores Quantitativos (Quality, Valuation, Growth, Risk, Diversification) 🟢 COMPLETED
- [x] **W09-002**: Fonte CVM para demonstrativos, com a Brapi fazendo a ponte ticker→CNPJ 🟢 COMPLETED
- [x] **W09-003**: Ações em circulação por exercício (CVM `composicao_capital`) — destrava `pe`/`pb` 🟢 COMPLETED
- [x] **W09-004**: Algoritmo de Alocação de Aporte Mensal (~R$ 1.000) 🟢 COMPLETED

> **Renumeração deliberada, duas vezes.** O plano original tinha só duas tasks, com a alocação
> em W09-002. A ingestão da CVM entrou como W09-002 porque é o que destrava três dos cinco
> sub-scores da W09-001 — sem ela, metade do pipeline ficaria permanentemente ausente. A
> contagem de ações entrou como W09-003 pelo mesmo critério: era o único insumo que faltava
> para o quinto pilar (Valuation), e alocar sem ele significaria distribuir dinheiro com um
> quinto da fórmula desligado. A alocação passou a W09-004.

---

### Waves inseridas fora da ordem — PRICE e EVENTS
Status: PRICE 🟢 COMPLETED (3 tasks) · EVENTS 🟡 IN_PROGRESS (2 de 3 tasks)

Nenhuma das duas está entre as 33 do roadmap. Ambas existem pelo mesmo critério: destravavam
mais coisa do que a wave seguinte da fila, e trocam **fornecedor com cota** por **arquivo
público do mercado** — o movimento que a W09-002 já tinha feito com os demonstrativos.

**PRICE — Histórico de preços de fonte aberta (B3 COTAHIST), 2026-08-19**

- [x] **PRICE-001**: `B3CotahistProvider` + `CotahistArchive`; `MarketDataProvider` partido em `DailyHistoryProvider` (só histórico) e `MarketDataProvider` (histórico + cotação) 🟢 COMPLETED
- [x] **PRICE-002**: `asset_prices.adjusted_close` anulável (migration `010`); a semântica da ausência passa a pertencer à fonte; `market_data/series.py` vira o ponto único da série de retorno ([ADR-023](decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md)) 🟢 COMPLETED
- [x] **PRICE-003**: `POST /assets/{ticker}/prices/backfill` — 1.495 pregões da PETR4, e `pe`/`pb` reais no banco 🟢 COMPLETED

**EVENTS — Eventos societários e proventos, iniciada em 2026-08-19**

- [x] **EVENTS-001**: Distribuições por exercício, da DMPL da CVM (`5.04.06` + `5.04.07`); coluna `fundamentals.dividends_paid` (migration `011`); `?refill=true` ([ADR-024](decisions/ADR-024-refill-fills-null-columns.md)) — **fechou o `dy`** 🟢 COMPLETED
- [x] **EVENTS-002**: `CorporateEventProvider` + `get_corporate_events` no `B3CotahistProvider`: data e natureza do evento pelo contador de distribuição, sem magnitude ([ADR-025](decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md)) 🟢 COMPLETED
- [x] **EVENTS-003**: Série de retorno total — `CorporateActionProvider` + `B3CorporateActionProvider`, tabela `corporate_actions` (migration `012`), `adjustment.py` com a regra de completude, endpoints de sync e leitura ([ADR-026](decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md)) — **destravou o pilar de Risco** 🟢 COMPLETED

Detalhes EVENTS-001:
- `backend/app/integrations/fundamentals/cvm.py`: lê a **DMPL** (`DMPL_con`), a única peça que diz o que foi distribuído **por exercício** e datado nele. Três detalhes decidem se o número está certo, e os três foram conferidos contra os arquivos reais: (a) **a coluna** — toda conta da DMPL se repete uma vez por coluna de patrimônio, então `CD_CONTA` sozinho seleciona oito linhas; só `Patrimônio Líquido` é lida, porque a irmã `Patrimônio Líquido Consolidado` inclui o pago a não-controladores (R$ 302 mi na PETR4 em 2024), sobre o qual o acionista não tem direito — mesma distinção que faz `net_income` ser `3.11.01` e não `3.11`; (b) **o sinal** — distribuição é débito, a peça escreve negativo, e a grandeza é o módulo; (c) **o que fica de fora** — `5.04.11` (*dividendos prescritos*) é dinheiro não reclamado voltando à companhia, estorno de período anterior e não distribuição negativa deste (R$ 316 mi na PETR4 em 2024). Dividendos e JCP são **somados**: declarantes dividem diferentemente e vários reportam tudo sob um código só.
- `backend/migrations/versions/011_dividends_paid.py` + `backend/app/data/models/fundamentals.py`: `dividends_paid` em `NUMERIC(24,4)`, nullable. Guardado como **agregado**, não por ação, pelo mesmo motivo de `net_income` e `equity` — o valor por ação é derivado no indicador, com a contagem do mesmo período.
- `backend/app/domain/fundamentals/indicators.py`: `dy = (dividends_paid / shares_outstanding) / price`. Era a última fórmula sem fonte; **os 10 indicadores passaram a ter insumo real** (foram 5 `None` → 1 → nenhum).
- **A armadilha operacional que a task expôs**: período gravado é congelado com os campos que o código conhecia no dia da ingestão (ADR-013), então os seis exercícios da PETR4 já no banco ficariam com a coluna vazia para sempre. `ebit` (W06-003) e `shares_outstanding` (W09-003) escaparam por acidente — chegaram a banco vazio. Daí `sync_annual_statements(..., refill=True)` e `?refill=true`, que preenchem coluna **`NULL`** e só ela ([ADR-024](decisions/ADR-024-refill-fills-null-columns.md)).
- Medido no banco real, após preencher seis períodos: 2020 R$ 4,41 bi (DPS 0,34, `dy` 0,01); **2022 R$ 224,06 bi** (DPS 17,18 sobre preço de 24,50 → `dy` **0,70**); 2024 R$ 100,90 bi (DPS 7,83, `dy` 0,22). Os 70% de 2022 não são erro de parsing — é o *payout* que a Petrobras de fato fez no ano recorde.
- Testes (+14, total **686**): `test_cvm_fundamentals_provider.py` (coluna, sinal, exclusão de prescritos), `test_fundamentals_service.py` (o `refill` que **não** sobrescreve valor presente), `test_fundamental_indicators.py` (`dy` a partir do agregado).

Detalhes EVENTS-002:
- `backend/app/integrations/market_data/base.py`: **`CorporateEventProvider`**, terceira ABC, ortogonal às duas de preço. Não é método em `DailyHistoryProvider` pela mesma razão que partiu aquela na PRICE-001 — um fornecedor de cotação não sabe em que pregão o papel foi ex, e obrigá-lo a implementar isso o obrigaria a responder mal.
- `backend/app/integrations/market_data/cotahist.py`: `get_corporate_events` lê o **mesmo arquivo já baixado**, sem requisição nova. `_read_bars` virou `_read_records`, então os dois leitores compartilham uma varredura em vez de crescerem uma paralela.
- **O sinal é o `DISMES`, não o marcador do `ESPECI`**, e isso foi medido, não suposto. O marcador **persiste** (~8 pregões de exibição: um dividendo seria reportado oito vezes) e **decai** (`EDJ` → `EJ`, que lido como texto parece marcador novo: 132 sessões em 2024). Detectar por início de sequência também não fecha: a BBAS3 exibe `ON  EDJ NM` em 12, 13 e 14/06/2024 enquanto o contador vai **323, 323, 324** — duas distribuições sob marcador imóvel. Esse caso virou teste, com os três registros verbatim.
- **Conferência no sentido inverso, no arquivo inteiro de 2024** (2.230 papéis, 7.312 incrementos): o contador nunca decresceu, atravessa a virada do ano (ITUB4 345 → 346 em 2025-01-02), e só **13 letras de ex- apareceram sem incremento** — nenhuma movendo preço em 25% ou mais, ou seja, nada capaz de corromper série de retorno se perde ao confiar no contador.
- **Duas letras mudaram de nome por evidência**: `EB` não é "bonificação" (carrega o desdobramento 1:2 da BBAS3, 56,46 → 27,91, o 10:1 da NVDC34 **e** a bonificação de 4,5% da MGLU3 em 2025) → `BONUS_OR_SPLIT`; `R` não é "rendimento" (é rendimento de fundo em 3.544 eventos de 2024, mas também cai em ação ao lado de outro provento — PETR4 com `EDR`, VIVT3 com `ERJ`) → `OTHER_DISTRIBUTION`, que afirma só o que todos os casos compartilham: dinheiro saiu, contagem de ações não mudou.
- Letra sem evidência (`X`, `C`) e incremento sem marcador (7,5% de 2024) viram **`UNCLASSIFIED`**, nunca palpite (regra 44). O `ESPECI` cru é guardado **verbatim** em cada evento, para revisar classificação sem reler dezenas de GB.
- **Não há fator e não há valor, de propósito**: o arquivo registra que houve distribuição e jamais quanto — derivar do degrau de preço é a heurística que o ADR-023 rejeitou.
- Validado contra os arquivos reais de 2020–2025: PETR4 com 47 eventos e **nenhum de contagem de ações em seis anos** (correto); MGLU3 com 15, entre eles o desdobramento 1:4 de 2020 (104,00 → 25,59), o grupamento 1:10 de 2024 e a bonificação de 2025.
- Testes (+15, total **701**), com **20 fixtures conferidas byte a byte** contra o arquivo real.

Detalhes EVENTS-003:
- **A fonte da magnitude não estava entre as três candidatas registradas.** O `CURRENT_TASK` listava contagem de ações da CVM, provento por pagamento de fonte a decidir, e fornecedor pago. A quarta é o **serviço aberto de eventos corporativos da própria B3** (`sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/`): publica reais por ação num provento e fator num desdobramento, sem token e sem cota — mesmo critério do [ADR-020](decisions/ADR-020-cvm-primary-fundamentals-source.md) e do [ADR-023](decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md).
- **Duas verificações contra dado real, antes de qualquer código.** (a) As datas do serviço, resolvidas para o pregão seguinte à data-com, caem em sessões que o contador `DISMES` — sinal **independente**, da EVENTS-002 — marcou ex: **157 de 157** em janela (PETR3, PETR4, VALE3, ITUB4, BBAS3). (b) Os fatores reproduzem o degrau de preço em cache em **49 de 50** casos; o único fora é o grupamento 1:30 da IRBR3 a R$ 0,93, onde um preço de poucos ticks não mede fator nenhum.
- **A junção é o ISIN, e o padrão do erro foi o que apontou isso.** A B3 repete um evento de contagem **uma vez por ISIN que o emissor já teve** — o 1:2 da BBAS3 chega sob `BRBBASA04OR8`, `BRBBASA05OR5` e `BRBBASACNOR3`. Compondo todos, o acordo caía para 32/50, e **todo** desacordo era uma **potência exata** da resposta certa: 2³ na BBAS3, 4³ na BPAC11, 10³ na CPLE3, 1,1³ na UNIP3. Foi isso que mostrou duplicação em vez de fórmula errada. Daí `SecurityIdentity` (ticker → ISIN + classe) lida do `CODISI`/`ESPECI` do próprio papel, em vez de inferida do dígito final do ticker — que funcionaria para PETR4 e falharia para TAEE11 (`UNT`).
- **`factor` significa duas coisas sob um nome só**, medido contra degrau real: porcentagem em `DESDOBRAMENTO` (BBAS3 `100` → 2,00 vs 2,0229) e `BONIFICACAO` (ITUB4 `3` → 1,03 vs 1,0297), e **razão crua** em `GRUPAMENTO` (MGLU3 `0,10` → 0,10 vs 0,1004). Os demais rótulos ficam **sem dimensionar de propósito**: a cisão da ITUB4 traz `factor` 100 contra um degrau medido de **1,2190**, que não é 2,0 nem 1,0 — seja o que for, não é razão de ação (regra 44).
- **A armadilha de unidade, pela terceira vez no projeto**: `valueCash` é cotado por `quotedPerShares`, que é `1000` em **332 de 2.305** linhas medidas. Mesmo modo de falha do `FATCOT` no arquivo e do `ESCALA_MOEDA` na CVM, e o erro seria de mil vezes.
- **A parte difícil não foi a aritmética, foi decidir quando ela pode rodar.** Um ajuste feito com *parte* das ações não é uma série mais curta — é uma **errada e plausível**. `backend/app/domain/market_data/adjustment.py` (puro, sem I/O) só deriva `adjusted_close` onde **toda sessão que o contador da B3 marcou ex** tem ação dimensionada; a mais recente que não tiver é um piso.
- **E a completude não pode ser julgada pelo serviço de eventos, porque ele omite.** A **ITUB4 foi ex em 2025-03-18** com o marcador `EB` do arquivo e degrau de **-8,60%**, e o serviço não reporta ação nenhuma ali. Confiar nele teria ajustado através de um evento real de contagem.
- **A exceção do `ATZ` foi decisão do dono do projeto, não do implementador.** Quase todo incremento não dimensionado carrega `ATZ` (*atualização*), em que nada sai do titular: **151 incrementos nos arquivos de 2020–2025, degrau mediano 1,0028**, e nenhum provento correspondente na B3. Seis moveram preço mais de 15% e ficam **nomeados** (BDRs A2MC34 e L1RC34, cota SNLG11, e RRRP3/AMBP3/AZUL4 em quedas de 15–20%). Sob a regra estrita, PETR4 teria **28 de 1.495** pregões ajustáveis, VALE3 47 e MGLU3 7 — a wave não destravaria nada. A pergunta foi apresentada com esses números e a decisão foi abrir a exceção (`CorporateEventKind.NOMINAL_UPDATE`), registrada no [ADR-026](decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md) §6 como o único ponto em que uma leitura foi preferida por conveniência de cobertura.
- `backend/app/domain/market_data/corporate_actions.py`: a **ex-date** é o primeiro pregão **realmente gravado** depois da data-com, não "mais um dia pulando fim de semana" — um feriado poria o ajuste numa data que nunca negociou (testado com a Sexta-feira Santa de 2025). O preenchimento só toca coluna **`NULL`**, pela mesma regra do [ADR-024](decisions/ADR-024-refill-fills-null-columns.md): linha que já tem ajuste do fornecedor nunca é reescrita.
- `backend/migrations/versions/012_corporate_actions.py`: **duas colunas de magnitude anuláveis**, não uma cujo sentido dependesse de `kind`. **Sem unique constraint, de propósito** — a identidade é a tupla de tudo que foi reportado, duas colunas dela anuláveis, e constraint sobre coluna anulável não dispara no PostgreSQL; a supressão de duplicata mora no service, como já mora para `asset_prices`.
- **Medido no PostgreSQL real, depois do sync**: PETR4 **1.495 de 1.495** pregões ajustados (62 proventos), volatilidade **41,8%**, drawdown **-63,4%** com fundo em **2020-03-18** (a COVID), e a **pior sessão ajustada idêntica à crua** (-29,7% em 2020-03-09) — a prova de que nenhum evento vazou. Fator de retorno total 3,43× em seis anos, consistente com ~R$ 39/ação de provento sobre um papel de ~R$ 30. BBAS3 1.495/1.495. **ITUB4 198/1.495**, truncada corretamente em `[2021-10-04, 2025-03-18]`; **MGLU3 478/1.495**, truncada na subscrição de 2024-02-01, com o **grupamento 1:10 desfeito** (13,5%, não os +896% do ADR-023).
- Testes (+49, total **750**): `test_b3_corporate_actions.py` (payloads verbatim do serviço real, incluindo a tripla duplicação por ISIN e o `CIS RED CAP` não dimensionado), `test_price_adjustment.py` (degraus reais de BBAS3, MGLU3, VIVT3 e ITUB4), `test_corporate_action_routes.py`, e o `ATZ`/identidade no `test_cotahist_provider.py`. Migration `012` aplicada em PostgreSQL 16 real, `alembic check` sem drift, downgrade testado.
- **Pendência deixada explícita**: **subscrição** não é dimensionada. A B3 a publica numa lista própria (`subscriptions`), com percentual e preço de exercício, e transformar isso em fator exige um **modelo do valor do direito**, não uma medição — por ora ela trunca a série (foi o que cortou a MGLU3).

Definition of Done da wave EVENTS: **atendida**. `dy` tem fonte, a data e a natureza de todo evento são legíveis, a **magnitude** existe e o `adjusted_close` é derivado dela. O pilar de **Risco** deixou de ser ausente e a cobertura do score saiu de 0,75.

---

### Wave 10 — Portfolio Rebalancing Engine
Status: 🟡 IN_PROGRESS (2 de 3 tasks)

- [x] **W10-001**: Peso-alvo e *drift* — `targets.py`, `scoring.merit` ([ADR-027](decisions/ADR-027-target-weight-comes-from-merit.md)) 🟢 COMPLETED
- [x] **W10-002**: Carregamento e endpoint da tabela de desvio (`GET /portfolios/{id}/rebalance`) 🟢 COMPLETED
- [ ] **W10-003**: O aporte que fecha os gaps — plano de rebalanceamento por fluxo de caixa ⚪ NOT_STARTED

> **Renumeração deliberada.** O plano original tinha duas tasks: "target weights e weight gaps"
> e "restrições quantitativas para perfil conservador". A segunda **já estava entregue** quando a
> wave começou — os tetos por ativo e por setor, o piso de cobertura, o piso de score e o
> `min_ticket` são a `AllocationPolicy` da W09-004, toda ela configurável por requisição
> ([ADR-021](decisions/ADR-021-allocation-ranks-by-coverage-tier.md)), e a W10-001 as reusa em
> vez de escrever uma segunda cópia. O que sobrava sem dono era o **plano**: calcular o gap não
> diz onde pôr o dinheiro. Daí a W10-003.

Detalhes W10-001 (2026-08-21):

- **A wave inteira era uma pergunta só: de onde vem o `target_weight`.** O roadmap §22 e a regra
  34 pedem `current_weight`, `target_weight` e `weight_gap`; o primeiro sai do ledger e o
  terceiro é uma subtração.
- **A resposta óbvia foi medida e reprovada, antes de qualquer código.** Alvo proporcional ao
  `final_score` não converge: variando só quanto a carteira detém de PETR4, de 0% a 20%, o score
  escorrega de **76,72 para 65,47** enquanto os quatro pilares de mérito ficam constantes em
  97,8 / 93,5 / 76,7 / 28,3. O que cai é Diversificação, o pilar que lê o detentor. Um alvo
  construído sobre isso **recua conforme a carteira se aproxima dele**.
- **O alvo passa a sair do mérito** — Quality, Valuation, Growth e Risk recompostos sozinhos por
  `scoring.merit` — e a concentração vira **teto** em vez de termo, lida do mesmo
  `AllocationPolicy` da W09 para que as duas não possam divergir.
- **Um erro de ordem foi encontrado traçando o algoritmo à mão**, não pelos testes: com o teto
  por ativo checado antes do setorial, três papéis de um mesmo setor congelam a 20% cada e põem
  o setor em **60%**, contra um limite de 40% nunca consultado. O teste
  `test_the_sector_ceiling_is_tested_before_the_asset_ceiling` fixa a ordem.
- **Verificado contra o banco real**: PETR4 com mérito **72,61** e cobertura de mérito 1,00
  (contra `final_score` 76,72, inflado pela Diversificação de uma carteira vazia); alvo de
  **0,200000** aparado pelo teto por ativo; **0,800000 `unassigned`**. ITUB4, que marca **92,47
  com cobertura 0,40** — o maior número do universo, feito só dos dois pilares que nunca faltam
  —, **não recebe alvo nenhum**: sob a regra do mérito ela tem um pilar só.
- 25 testes novos, todos com valores calculados à mão. `pytest` 750 → **775**.

Detalhes W10-002 (2026-08-21):

- `portfolio_targets` em `service.py` (carrega e delega, nada é calculado ali) e
  `GET /portfolios/{id}/rebalance`, com os mesmos overrides de política por query da W09 mais
  `rebalance_band`.
- **A construção de candidatos foi extraída** (`_candidates`) e passou a ser compartilhada com
  `plan_contribution`: os dois precisam ver o mesmo universo com os mesmos valores detidos, e
  discordarem disso faria o plano e os gaps que ele deveria fechar descreverem duas carteiras.
- **Um fato que só o teste ponta a ponta mostra**: sem demonstrativos, *nenhum* ativo recebe alvo,
  e **baixar `min_coverage` não resolve** — o que falta não é o piso, é um segundo pilar de
  mérito. O plano de aporte podia ser aberto por esse parâmetro; a tabela de desvio não pode, e
  o teste `test_lowering_the_coverage_floor_does_not_conjure_a_target` fixa isso.
- 12 testes novos de rota. `pytest` 775 → **787**.

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

Wave: **EVENTS** (inserida fora da ordem, entre a W09 e a W10)
Task ID: **EVENTS-003** — série de retorno total
Status: ⚪ NOT_STARTED (a wave está 🟡 em andamento: 2 de 3 tasks entregues)

> O detalhe task-a-task fica na seção *Waves inseridas fora da ordem* acima, em *Last Execution*
> e em [history/COMPLETED_TASKS.md](history/COMPLETED_TASKS.md) (esta última só recebe a wave
> quando ela fecha).

Completed:
- Waves 00 a 09 do roadmap, concluídas — Foundation, Scaffold, Database, Auth, Portfolio,
  Market Data, Fundamental Data, Quant Engine, Benchmark Engine, Recommendation Engine.
- **Wave PRICE** (inserida fora da ordem, entre a W09 e a W10) — histórico de preços de fonte
  aberta pela série COTAHIST da B3. Três tasks: provider/parser/cache, armazenamento da ausência
  de ajuste ([ADR-023](decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md)), e o
  endpoint de backfill validado contra o banco real. **672 testes.**
- **Wave EVENTS**, duas de três tasks: **EVENTS-001** (distribuições por exercício da DMPL da
  CVM, coluna `dividends_paid`, migration `011`, `?refill=true` —
  [ADR-024](decisions/ADR-024-refill-fills-null-columns.md); fechou o `dy`, e os 10 indicadores
  passaram a ter insumo) e **EVENTS-002** (data e natureza do evento societário pelo contador de
  distribuição da B3 —
  [ADR-025](decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md); sem
  magnitude, de propósito). **701 testes.**
- Manutenções fora de wave: DOC-001 (documentação × código) e FIX-001 (Known Issues acionáveis),
  ambas em 2026-08-19.

Next Action:
**EVENTS-003 — série de retorno total.** É a task que a wave existe para chegar: com a data e a
natureza do evento já legíveis, falta a **magnitude** (fator de desdobramento/grupamento e valor
do provento por pagamento) e o `adjusted_close` derivado dela. É o que destrava o pilar de Risco,
a cobertura do score (0,75 → 1,00) e o backtesting da W13. Ver `docs/memory/CURRENT_TASK.md`.

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
- **W06-003**: Validação contra a API real, correção do mapeamento e captação de insumos (🟢 COMPLETED)
- **W06-004**: Manutenção pré-Wave 07 — ambiente Postgres real, migrations aplicadas, validação multi-tipo do parser (🟢 COMPLETED)
- **W06-005**: Correção do `adjusted_close` fabricado a partir do `close` (ADR-016) (🟢 COMPLETED)
- **W07-001**: Quant Engine — módulo `returns.py` (diário, semanal, mensal, trimestral, YTD, anual, CAGR) (🟢 COMPLETED)
- **W07-002**: Quant Engine — módulo `risk.py` (volatilidade, beta, max drawdown, Sharpe, Sortino) (🟢 COMPLETED) — **Wave 07 concluída**
- **W08-001**: Benchmark Engine — ingestão de CDI, IBOV, IPCA e Selic (🟢 COMPLETED)
- **W08-002**: Comparativo carteira/ativo × benchmark, com índice de performance time-weighted (🟢 COMPLETED) — **Wave 08 concluída**
- **W09-001**: Sub-scores decomponíveis (Quality, Valuation, Growth, Risk, Diversification) com ausência de primeira classe (🟢 COMPLETED)
- **W09-002**: CVM como fonte primária de demonstrativos, com a Brapi fazendo a ponte ticker→CNPJ (🟢 COMPLETED)
- **W09-003**: Ações em circulação por exercício, com a unidade reconciliada contra o LPA do próprio arquivo (🟢 COMPLETED)
- **W09-004**: Alocação do aporte mensal — faixas de cobertura, tetos reusados do score, plano derivado (🟢 COMPLETED) — **Wave 09 concluída**
- **PRICE-001**: `B3CotahistProvider` + `CotahistArchive`; `DailyHistoryProvider` separado de `MarketDataProvider` (🟢 COMPLETED, 2026-08-19)
- **PRICE-002**: `adjusted_close` anulável — a ausência de ajuste virou dado, não erro (ADR-023) (🟢 COMPLETED, 2026-08-19)
- **PRICE-003**: `POST /assets/{ticker}/prices/backfill` — 1.495 pregões reais, `pe`/`pb` no banco (🟢 COMPLETED, 2026-08-19) — **wave PRICE concluída**
- **EVENTS-001**: Distribuições por exercício da DMPL da CVM; `fundamentals.dividends_paid` (migration `011`) e `?refill=true` (ADR-024) — **fechou o `dy`, o último indicador sem insumo** (🟢 COMPLETED, 2026-08-19)
- **EVENTS-002**: Data e natureza do evento societário pelo arquivo de fim de dia da B3, via contador de distribuição (ADR-025) — sem magnitude, de propósito (🟢 COMPLETED, 2026-08-19)
- **DOC-001**: Manutenção de documentação — zerar a lista *Inconsistências documentação × código* (🟢 COMPLETED, 2026-08-19)
- **FIX-001**: Manutenção de código — corrigir todos os Known Issues que tinham correção possível; migrations `008` e `009` (🟢 COMPLETED, 2026-08-19)

---

## In Progress
**Wave EVENTS 🟡 em andamento**, 2 de 3 tasks entregues. Nenhuma task com código pela metade — a
próxima, **EVENTS-003** (série de retorno total), ainda não começou. Ver
[memory/CURRENT_TASK.md](memory/CURRENT_TASK.md).

---

## Blocked Tasks
Nenhuma tarefa bloqueada no momento.

---

## Known Issues
- ✅ ~~**1 dos 10 indicadores permanece `None`**~~ — **os 10 têm insumo desde 2026-08-19** (EVENTS-001). O último era o `dy`, e ele passou a vir da **DMPL da CVM** (`5.04.06` + `5.04.07`, coluna `Patrimônio Líquido`), que reporta a distribuição **por exercício e datada nele** — exatamente o que a Brapi nunca deu, porque `dividendYield` lá é snapshot atual sem data-fim, e aplicá-lo a um balanço passado é o look-ahead que as regras 108/109 proíbem. Medido no banco real: `dy` de 0,22 em 2024 e 0,70 em 2022 para a PETR4. O caminho até aqui foi de **5 `None` → 1 → nenhum**; os outros quatro foram destravados pela fonte da CVM: `debt_ebitda`/`ebitda_margin` em 2026-08-18 (W09-002, EBITDA derivado de verdade em vez da cópia de `ebit` que o fornecedor entregava) e `pe`/`pb` em 2026-08-19 (W09-003, contagem de ações por exercício).
  - ✅ **`pe`/`pb` existem no banco real desde 2026-08-19** (wave PRICE): faltava **preço histórico**, e ele passou a vir do COTAHIST da B3. Seis exercícios da PETR4, P/L de 12,74 e P/VP de 1,27 em 2024. São fechamentos **não ajustados**, e é o correto: múltiplo *point-in-time* casa o preço cotado então com o lucro reportado então.
- 🔴 **O pilar de Risco continua ausente, e é a pendência de maior retorno do projeto** (registrado em 2026-08-19, wave PRICE). Não é falta de preço — são **1.495 pregões** no banco. É falta de **série de retorno total**: o COTAHIST publica o preço negociado e nenhum ajuste, então `volatility`, `max_drawdown`, `beta` e `sharpe` ficam `None` e a cobertura do score para em **0,75**. **Não remende com `adjusted_close = close`**: medido em dado real, o grupamento 1:10 da MGLU3 em 2024-05-27 aparece como **+896% num pregão** ([ADR-023](decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md), que enumera e rejeita, com motivo, todas as alternativas mais baratas — inclusive derivar o ajuste da contagem de ações da CVM, que é **anual** e não data o evento). A correção é a montante — **ingerir eventos societários e proventos** — e ela está **pela metade**: a EVENTS-002 trouxe **data e natureza** de todo evento, de graça e décadas atrás, e deliberadamente **não** a magnitude ([ADR-025](decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md)). O que falta é o **fator** (desdobramento/grupamento) e o **valor por pagamento** do provento, e é isso a EVENTS-003.
  - ⚠️ Pelo mesmo motivo, a **carteira ainda não é valorável**: o índice time-weighted valoriza posição em `adjusted_close` ([ADR-019](decisions/ADR-019-portfolio-return-is-time-weighted.md)), e as 1.495 linhas têm `adjusted_close` nulo. `asset_prices` deixou de estar vazia, mas o que destravou foi múltiplo *point-in-time*, que lê `close`. A distinção é o assunto inteiro do ADR-023.
  - ✅ **A parte do `dy` foi entregue em 2026-08-19** (EVENTS-001): dividendos e JCP debitados ao patrimônio no exercício, da DMPL. Não move o pilar de Risco — nenhum pilar de score consome `dy` —, mas era a metade barata da mesma ingestão e fecha o conjunto de indicadores.
- ✅ ~~**Módulos de demonstrativos saíram do plano gratuito da Brapi**~~ — **CONTORNADO em 2026-08-18** (W09-002, [ADR-020](decisions/ADR-020-cvm-primary-fundamentals-source.md)). A fonte primária passou a ser os **dados abertos da CVM**, que são o arquivo entregue ao regulador: aberto, sem token, sem cota e com mais histórico do que o fornecedor dava. A Brapi continua no projeto fazendo a ponte que a CVM não faz — o `summaryProfile`, ainda gratuito, traz o CNPJ, e os arquivos da CVM não têm coluna de ticker. Validado ao vivo com 6 exercícios da PETR4 batendo com o publicado. O texto original fica abaixo para registro.
- 🔴 **Módulos de demonstrativos saíram do plano gratuito da Brapi.** `GET /quote/{ticker}?modules=incomeStatementHistory,balanceSheetHistory` retorna **HTTP 403**: *"Os módulos ... não estão no plano Gratuito. O plano Startup (R$ 119,99/mês) libera esses módulos. Módulos disponíveis hoje: summaryProfile."* Em 2026-08-17 (W06-003) a mesma chamada funcionou e trouxe 16 períodos. **A ingestão de fundamentals está inoperante — por plano, não por código.** O parser continua correto e testado; ele apenas não tem mais o que receber. Bloqueia reingestão de fundamentals e, por consequência, os sub-scores fundamentalistas da Wave 09. Decidir: assinar o plano, trocar de fonte (CVM/dados abertos) ou adiar a Wave 09.
- 🟡 **O plano gratuito da Brapi só aceita `range` de até `3mo`** — deixou de ser a restrição estruturante em 2026-08-19 (wave PRICE): o histórico profundo passou a vir da B3, aberto e sem cota. A Brapi segue necessária para **cotação ao vivo** e para o `adjusted_close` das sessões recentes, que o arquivo de fim de dia da bolsa não dá. Registro original: (verificado 2026-08-18, W08-001, HTTP 400: *"O range \"1y\" não está disponível no seu plano. Ranges permitidos: 1d, 5d, 1mo, 3mo"*, `code: INVALID_RANGE`). E o `range` da Brapi é **relativo a hoje** — não existe parâmetro de data inicial, então **não há como paginar histórico**: o teto de ~63 pregões é absoluto no plano gratuito. Consequências: (a) `_brapi_range_for` em `market_data/brapi.py` mapeia janelas > 90 dias para `6mo`/`1y`/`2y`/`5y`/`max`, todos recusados — ou seja, **`sync_daily_history` falha hoje para qualquer janela acima de 3 meses**, defeito pré-existente da W05 que só apareceu agora porque a validação da W06-004 usou `range=1mo`; (b) o IBOV fica limitado a ~3 meses, o que torna `beta` estatisticamente pobre; (c) impacta diretamente o backtesting da W13, que precisa de anos. Não é regressão da W08. O CDI/IPCA **não** são afetados: o SGS é aberto e aceita janela de 10 anos por requisição.
- **Plano gratuito aceita no máximo 1 ativo por requisição** (`"Seu plano permite no máximo 1 ativo(s) por requisição. Você enviou 3."`). Não há batching: ingestão em lote custa **1 requisição por ticker**. Relevante para dimensionar a cota mensal.
- ~~**`adjusted_close` pode ser congelado errado**~~ — **CORRIGIDO em 2026-08-18**, ver [ADR-016](decisions/ADR-016-unadjusted-bars-are-not-stored.md) e a decisão datada abaixo. O problema, para registro: a Brapi devolve `adjustedClose: null` para a sessão fechada mais recente (verificado em 2026-08-18: nulo em 2026-08-17 nos três ativos testados) e preenche depois. O parser cai para `close` ([`brapi.py:157-159`](../backend/app/integrations/market_data/brapi.py#L157-L159)) e `sync_daily_history` **nunca sobrescreve uma data já gravada** ([`service.py`](../backend/app/domain/market_data/service.py)). Uma barra ingerida enquanto o ajuste ainda é nulo guarda `close` como `adjusted_close` **permanentemente**. Se houve provento/desdobramento naquela data, todo retorno calculado sobre ela na W07 fica errado, em silêncio. Corrigir antes de ingestão em lote: ou não gravar a última sessão, ou permitir sobrescrita quando o valor gravado veio do fallback.
- ✅ ~~**`alembic check` acusa drift**~~ — **RESOLVIDO em 2026-08-19** pela migration `009_drop_dup_uniques`, que removeu as `UniqueConstraint` redundantes. `alembic check` responde "No new upgrade operations detected" e serve de guarda de drift em CI. A unicidade continua garantida pelos índices únicos `ix_assets_ticker`/`ix_users_email` — verificado com `INSERT` duplicado real contra o Postgres. Registro do problema:  `assets` tem `assets_ticker_key` (UNIQUE CONSTRAINT) **e** `ix_assets_ticker` (UNIQUE INDEX) para a mesma coluna; idem `users.email`. Vem de a migration `001` declarar a constraint e o model declarar `unique=True, index=True`. Redundante, não incorreto — mas faz `alembic check` falhar, o que impede usá-lo como guarda de drift no CI.
- ✅ ~~**`env_file=".env"` é relativo ao cwd**~~ — **RESOLVIDO em 2026-08-19**: o caminho passou a ser ancorado ao próprio arquivo de configuração (`Path(__file__).parents[3] / ".env"`), com o `.env` do diretório atual mantido como override de maior precedência. Verificado rodando de `backend/`: `BRAPI_TOKEN` carrega. Registro do problema:  (`app/core/config.py`). Rodando de `backend/`, o `.env` da raiz não é lido e `BRAPI_TOKEN` fica vazio **silenciosamente** — as chamadas saem sem token. Sob `docker compose` não afeta (as env vars são injetadas explicitamente).
- **Throttle de requisições desligado por padrão** (mantido de propósito; o que era defeito — as chaves não constarem do `.env.example` — foi corrigido em 2026-08-19): `MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS` e `FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS` têm default `0.0`, ou seja, sem espaçamento entre chamadas. A Brapi tem cota mensal limitada no plano gratuito. Definir um intervalo no `.env` antes de qualquer ingestão em lote.
- ~~**Só a PETR4 foi usada na validação.**~~ **RESOLVIDO em 2026-08-18 para market data** (FII/ETF/banco validados, ver W06-004). **Continua aberto para fundamentals**: BDRs e o balanço específico de bancos/seguradoras seguem sem validação, agora bloqueados pelo plano gratuito (ver primeiro item).

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
- **Status**: 🟢 RESOLVIDO em 2026-08-17 (W06-003). Validado contra resposta real: o parser de market data estava **correto**; o de fundamentals tinha **dois campos errados**, corrigidos. Ver "Validação contra a API real" abaixo.

### Decision — 2026-08-17 — Validação contra a API real e o que ela ensinou (W06-003)
- **Decision**: Gastar 1 requisição à Brapi para validar todos os mapeamentos de uma vez, em vez de continuar acumulando código não verificado.
- **Resultado**: market data ✅ correto; fundamentals ❌ `totalStockholderEquity` e `totalDebt` nulos em 16/16 períodos, deixando `equity`, `debt` e `roe` silenciosamente `None`.
- **Lição registrada**: todos os testes anteriores usavam payloads que eu mesmo escrevi com os nomes de campo que eu supunha corretos. **Um mock construído sobre uma suposição não verifica a suposição** — ele a reproduz. Existe agora um teste de regressão com a resposta real (`test_regression_against_the_real_petr4_response`). Aplicar o mesmo padrão a intraday (W15) e IA (W12): validar contra uma resposta real **antes** de escrever a bateria de mocks.
- **Custo em cota**: 1 requisição no total. Módulos e `range` cabem todos no mesmo `GET /quote`.
- **Status**: 🟢 APPROVED

### Decision — 2026-08-17 — Recomputação de indicadores derivados
- **Decision**: `financial_indicators` pode ser reconstruído sob demanda (`?recompute=true`); `fundamentals` nunca é sobrescrito.
- **Reason**: Um indicador é `f(insumos, versão do código)`, não um fato reportado. Quando a fórmula é corrigida, o valor antigo é simplesmente um bug preservado. Os demonstrativos crus continuam imutáveis, então nada do que a fonte publicou se perde.
- **Status**: 🟢 APPROVED. Registrado como `docs/decisions/ADR-015`.

### Decision — 2026-08-18 — Manutenção pré-Wave 07 (W06-004)
- **Contexto**: duas pendências herdadas da Wave 06 — recomputar indicadores desatualizados e validar o parser com FII/ETF/banco.
- **A recomputação era um não-problema.** Não existia banco algum: sem container, sem volume, sem arquivo SQLite. Ao subir o Postgres, o volume foi **criado do zero** e todas as tabelas vieram com 0 linhas. Não havia indicador gravado para recomputar — a pendência tinha sido registrada por hipótese, não por observação. Lição: pendência operacional deve ser verificada contra o estado real antes de ser propagada de handoff em handoff.
- **`alembic upgrade head` nunca havia rodado.** `migrations/env.py` chamava `context.is_offline()`, que não existe na API do Alembic (o correto é `is_offline_mode()`), e o comando abortava com `AttributeError`. Passou despercebido porque `alembic heads`/`history` — a "validação estrutural" registrada na W06-003 — leem o diretório de scripts e **não carregam `env.py`**. Corrigido; as migrations `001`→`004` foram aplicadas em PostgreSQL 16 real, com sucesso.
- **Custo em cota: 5 requisições.** Tentei batelar os 3 tickers numa só (1 req) — o plano gratuito recusa mais de 1 ativo por requisição. A segunda descobriu o 403 dos módulos de demonstrativos. As 3 restantes validaram as séries de preço.
- **Resultado da validação**: o parser de market data está **correto para FII, ETF e banco** — 22 barras cada, 0 rejeitadas, 0 avisos, `get_quote` correto. A forma da resposta é a mesma da PETR4, não varia por classe de ativo. Fixado em `test_regression_against_real_responses_per_asset_type`.
- **O parser de fundamentals não pôde ser validado**: os módulos saíram do plano gratuito (ver Known Issues).
- **Status**: 🟢 APPROVED

### Decision — 2026-08-18 — Barra sem `adjusted_close` não é armazenada (ADR-016)
- **Decision**: o parser deixa de fabricar `adjusted_close` a partir do `close`; o campo passa a ser `Decimal | None` refletindo o que a fonte reportou, e `validate_daily_bars` rejeita a barra sem ajuste (`MISSING_ADJUSTED_CLOSE`).
- **Reason**: o fallback parecia inofensivo isolado, mas combinado com a idempotência de `sync_daily_history` (que nunca sobrescreve data gravada) congelava um ajuste inventado **permanentemente** — e a Wave 07 calcula todo retorno a partir dessa coluna. Falha do pior tipo: sem exceção, sem log, coluna preenchida com número plausível. Igualdade não distingue os casos: em dia sem provento, `adjustedClose == close` legitimamente (BOVA11 em 2026-07-20, ambos 170.3), então não há como auditar depois quais valores vieram da fonte e quais do fallback.
- **Por que agora, e não como Future Work**: o banco estava vazio. A correção custou uma tarde e zero linhas contaminadas; depois de qualquer ingestão exigiria identificar linhas suspeitas — o que não é possível com segurança — e reingerir.
- **O que torna a rejeição segura**: autocorreção. A data não gravada não entra em `existing_dates`, então o sync seguinte a insere quando a fonte publicar o ajuste. Provado ponta a ponta em `test_unadjusted_bar_is_not_stored_and_lands_on_a_later_sync`.
- **Custo aceito**: a sessão fechada mais recente pode faltar por ~1 dia; `rejected: 1` no sync diário passa a ser rotina, não sinal de problema de qualidade.
- **Status**: 🟢 APPROVED. Registrado como `docs/decisions/ADR-016`.

### Decision — 2026-08-18 — Anualização e tipo numérico no Quant Engine (ADR-017)
- **Decision**: retornos anualizam em **dias corridos (ACT/365 fixo)**; volatilidade anualizará em **252 pregões** na W07-002. `returns.py` fica inteiramente em `Decimal` — **sem** fronteira `float` e sem `numpy`.
- **Reason**: as duas convenções de anualização não são alternativas para a mesma pergunta. Retorno composto escala com **tempo decorrido** (feriado não suspende juro); volatilidade escala com **número de observações** (~252/ano). Misturá-las corrompe o Sharpe por um fator constante (`sqrt(365/252) ~ 1,20`) sem que nada no resultado denuncie. Quanto ao tipo: retorno só exige subtração, divisão e exponenciação fracionária — todas operações determinísticas de `Decimal` — então `float` custaria precisão sem comprar nada, e os valores são encadeados pela W08/W13.
- **A fronteira `float` não foi antecipada de propósito**: ela é real em `risk.py` (desvio-padrão, covariância) e deve ser decidida lá, com o cálculo concreto em mãos, em vez de importar `numpy` para cumprir uma expectativa documentada (regras 92 e 134).
- **Nota de validação**: o caso conhecido de CAGR foi escrito assumindo 730 dias entre 2024-01-01 e 2026-01-01. Sao 731 — 2024 e bissexto. O teste falhou e o intervalo foi corrigido. Evidencia de que os valores sao calculados a mao e conferidos, nao ajustados ao que o codigo devolveu.
- **Status**: APPROVED. Registrado como `docs/decisions/ADR-017`.

### Decision — 2026-08-18 — A fronteira `Decimal -> float` nao existe; `numpy` nao entra no Quant Engine (adendo ao ADR-017)
- **Decision**: `risk.py` fica inteiramente em `Decimal`, como `returns.py`. `numpy`/`scipy` seguem sem nenhum import no projeto.
- **Contexto**: o ADR-017 previu que esta task precisaria de `float`, porque desvio-padrao, covariancia e raiz quadrada sao "estatistica" e a regra 17 abre essa porta. Levantando operacao por operacao, nenhuma das cinco metricas exige: `Decimal.sqrt()` existe, potencia fracionaria ja havia sido verificada, e nao ha matriz, inversao nem funcao transcendental.
- **O argumento decisivo e determinismo (regra 113)**, nao magnitude: soma em `float` depende da ordem dos termos, e essa divergencia atravessa uma raiz e uma divisao ate virar um Sharpe que nao reproduz. Quando o determinismo e gratis, nao se abre mao dele.
- **A expectativa de "usar numpy no quant" fica revogada, nao pendente.** Se uma wave futura precisar de algebra matricial de verdade (matriz de covariancia para volatilidade de carteira, Markowitz), a pergunta volta e deve ser decidida ali, com o mesmo criterio: qual operacao concreta `Decimal` nao cobre.
- **Nao implementado, de proposito**: volatilidade de carteira. Nao e a media das volatilidades dos ativos — precisa da matriz de covariancias e dos pesos das posicoes. Esta em Future Work; **nao aproximar por media** (regra 44).
- **Status**: APPROVED. Registrado como adendo datado em `docs/decisions/ADR-017`.

### Decision — 2026-08-19 (EVENTS-002)
- **Decision**: Evento societário é detectado pelo **`DISMES`** — o contador de distribuição do próprio papel no arquivo de fim de dia da B3 — e **não** pelo marcador de ex- do `ESPECI`. O que se reporta é **data e natureza**, jamais magnitude, e a natureza vem decomposta letra a letra, com `UNCLASSIFIED` para o que não tem evidência. `CorporateEventProvider` é interface própria, ortogonal às duas de preço.
- **Reason**: O marcador é **janela de exibição, não evento**, e isso foi medido no arquivo real de 2024, não suposto: ele persiste ~8 pregões (um dividendo seria contado oito vezes) e decai (`EDJ` → `EJ`, que lido como texto parece marcador novo — 132 sessões no ano). Detectar por início de sequência também falha: a BBAS3 mostra `ON  EDJ NM` em 12, 13 e 14/06 enquanto o contador vai **323, 323, 324** — duas distribuições sob marcador imóvel. No sentido inverso, varrendo os 2.230 papéis e 7.312 incrementos de 2024, o contador nunca decresceu e só 13 letras de ex- apareceram sem incremento, **nenhuma movendo preço em 25% ou mais**. Duas letras mudaram de nome por evidência (`EB` carrega desdobramento *e* bonificação → `BONUS_OR_SPLIT`; `R` aparece em fundo e em ação ao lado de outro provento → `OTHER_DISTRIBUTION`), porque nomear pelo ato jurídico afirmaria uma distinção que o arquivo não faz. Magnitude fica de fora porque derivá-la do degrau de preço é a heurística que o ADR-023 já rejeitou (regra 44).
- **Status**: 🟢 APPROVED. Registrado em [ADR-025](decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md).

### Decision — 2026-08-19 (EVENTS-001)
- **Decision**: `sync_annual_statements(..., refill=True)` e `?refill=true` preenchem colunas que estão **`NULL`** em períodos já gravados, e **somente** elas. Valor já presente nunca é tocado.
- **Reason**: O ADR-013 congela o período gravado, o que protege contra reexpressão silenciosa e, como efeito colateral, faz **toda coluna nova nascer permanentemente vazia** para o dado já no banco. `ebit` (W06-003) e `shares_outstanding` (W09-003) escaparam disso por acidente de cronologia — chegaram a um banco vazio. `dividends_paid` chegou a um banco com seis exercícios da PETR4, e sem saída o `dy` **nunca** produziria valor, com a fonte reportando o número o tempo todo. Não é porta dos fundos para o ADR-013: como valor presente jamais é sobrescrito, reexpressão continua sem entrada, e continua sendo o problema em aberto que era.
- **Status**: 🟢 APPROVED. Registrado em [ADR-024](decisions/ADR-024-refill-fills-null-columns.md).

### Decision — 2026-08-19 (PRICE-002)
- **Decision**: Histórico sem ajuste é **gravado com `adjusted_close` NULL** em vez de rejeitado ou preenchido com o `close`; a semântica da ausência pertence à **fonte** (`reports_adjusted_close`), e `app/domain/market_data/series.py` é o ponto único que constrói série de retorno, descartando linha sem ajuste.
- **Reason**: O ADR-016 estava certo para a fonte que descreveu — o fornecedor publica o ajuste um pregão depois, então rejeitar é autocorretivo. O COTAHIST quebra essa premissa: ele **nunca** publicará ajuste, e sob a regra antiga 100% das suas barras seriam descartadas, junto com décadas de histórico aberto. Preencher com o `close` é pior: medido em dado real, o grupamento 1:10 da MGLU3 vira uma sessão de **+896%** dentro de `volatility`, `max_drawdown`, `beta` e `sharpe`.
- **Status**: 🟢 APPROVED. Registrado em [ADR-023](decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md), emenda ao [ADR-016](decisions/ADR-016-unadjusted-bars-are-not-stored.md).

### Decision — 2026-08-19 (W09-004)
- **Decision**: A alocação ordena por **faixa de cobertura antes do score** (piso de 0,50, faixas de 0,25 de largura), reusa `ASSET_WEIGHT_SCALE.at_zero` / `SECTOR_WEIGHT_SCALE.at_zero` como tetos em vez de redeclarar 20%/40%, mede os pesos contra a carteira **depois** do aporte (caixa incluído) e **não grava nada** — o plano é derivado a cada leitura, como as posições.
- **Reason**: Ordenar por `final_score` é o desenho óbvio e erra **numa direção só**. Os pilares que somem são os fundamentalistas; o que sobrevive a toda lacuna é Diversification, que vale ~100 para o que a carteira ainda não tem. Um ativo sem demonstrativo chega com score alto feito dos dois pilares que nunca estiveram em dúvida — e o ranking passa a premiar quem tem menos dado. As faixas cortam isso sem fingir precisão que a escala não tem (0,80 e 0,85 são a mesma coisa com pilares diferentes faltando). Reusar as escalas do score por construção impede o estado em que um ativo pontua bem por diversificar para uma posição que o alocador se recusa a financiar. `MAX_POSITIONS = 5` é `1 / 0,20` e não é coincidência: na carteira vazia a base **é** o aporte, o teto de 20% vale R$ 200, e com menos posições o primeiro aporte ficaria estruturalmente inexecutável — descoberto por um teste escrito à mão, não em produção.
- **Status**: 🟢 APPROVED. Registrado em [ADR-021](decisions/ADR-021-allocation-ranks-by-coverage-tier.md).

### Decision — 2026-08-19 (W09-003)
- **Decision**: A contagem de ações vem do `composicao_capital` da CVM como **integralizadas menos tesouraria**, e a **unidade em que ela foi escrita é reconciliada contra o LPA do próprio arquivo** (`3.99.*`), nunca assumida. Onde nenhuma unidade reconcilia, ou onde a empresa não publica LPA, `shares_outstanding` fica **ausente** — não é corrigida por palpite nem gravada como veio.
- **Reason**: O arquivo **não tem coluna de escala** e os declarantes não concordam: medido nos exercícios de 2020 a 2025, cerca de um terço escreve a contagem em milhares e o resto em unidades, sem marcador nenhum, e a mesma empresa troca de convenção entre um ano e outro — a Petrobras escreve `13.044.497` em 2020 e `13.044.496.930` em 2021. Engolir isso não dá um erro pequeno: contagem mil vezes menor → LPA mil vezes maior → P/L mil vezes menor, e numa escala **invertida** o P/L absurdamente baixo **clampa em 100**. As leituras mais quebradas iriam para o **topo** de qualquer ranking, que é exatamente onde a alocação da W09-004 vai buscar. A reconciliação usa `lucro / LPA` como contagem independente, com tolerância larga de propósito (fator de 5 para cada lado), porque as duas grandezas não são a mesma — o LPA é média ponderada do ano e por classe de ação, a contagem é o total na data de fechamento. Basta separar unidades, e um fator de 5 fica duas ordens de grandeza longe de um fator de 1.000.
- **Validação contra número público, não contra schema**: PETR4 2024 dá LPA de **R$ 2,84**, que é o publicado; VALE3 dá 7,40 contra 7,39; MGLU3 dá 0,61 contra 0,61. As séries também reproduzem eventos societários reais — o desdobramento da WEGE3 em 2021 (2,1 bi → 4,2 bi ações), a bonificação da PSSA3 (320 mi → 638 mi) e o grupamento da MGLU3 em 2024 (6,7 bi → 736 mi).
- **Status**: 🟢 APPROVED. Documentada no docstring de `app/integrations/fundamentals/cvm.py`, junto do código e das constantes que ela governa — sem ADR próprio porque não há alternativa arquitetural em disputa, só a aplicação da regra 44 e do ADR-014 a uma coluna nova.

### Decision — 2026-08-18 (W09-002)
- **Decision**: Dados abertos da **CVM** como fonte primária de demonstrativos; a **Brapi** permanece fazendo a ponte ticker→CNPJ (`summaryProfile`, ainda gratuito) e cobrindo BDR/ETF. Composição por **período inteiro** — campos nunca são misturados entre fontes. Falha de infraestrutura **não** cai para a outra fonte.
- **Reason**: A CVM é a peça entregue ao regulador, aberta e sem cota, mas seus arquivos não têm coluna de ticker — só CNPJ. A Brapi conhece ticker e expõe o CNPJ no módulo que continuou gratuito. Nenhuma das duas responde sozinha. Mesclar campo a campo foi rejeitado porque duas fontes discordam sobre consolidado versus controladora, sobre o que é dívida e sobre qual linha é "receita" num banco: emendar produziria uma linha que **nenhum arquivo reportou**, e nada a jusante perceberia. Cair para a outra fonte em timeout transformaria indisponibilidade em **troca silenciosa de fonte**. Mapeamento conferido contra números públicos da PETR4 antes de qualquer mock: `net_income` é `3.11.01` (R$ 36,6 bi) e não `3.11` (R$ 37,0 bi, com minoritários), com o patrimônio líquido dos minoritários pela mesma razão — numerador e denominador precisam descrever os mesmos donos, e o ROE resultante dá os 10,0% publicados.
- **Status**: 🟢 APPROVED. Registrado em [ADR-020](decisions/ADR-020-cvm-primary-fundamentals-source.md).

### Decision — 2026-08-18 (W09-001)
- **Decision**: Sub-score sem dado é **ausente**, nunca zero nem 50 "neutro", e fica de fora da média em vez de puxá-la para baixo. O score final renormaliza sobre os pilares existentes e **reporta `coverage`**; exige no mínimo dois pilares. A fórmula é versionada (`SCORING_FORMULA_VERSION`) e todo limiar é constante nomeada.
- **Reason**: Um Quality Score fabricado **não parece errado — parece uma empresa ruim**, e depois desaparece dentro do score final. A cobertura é leitura obrigatória e não diagnóstico: um ativo pontuado só em Risco e outro pontuado nos cinco pilares voltam ambos como número entre 0 e 100 e **não são comparáveis**. Mínimo de dois pilares porque um composto de um só é esse um com outro nome. Ausência não é estado temporário do projeto: um FII ou ETF nunca terá demonstrativo para pontuar Quality.
- **Status**: 🟢 APPROVED. Documentada no docstring de `app/domain/recommendations/scoring.py`, onde vive junto dos pesos e limiares que ela governa — sem ADR próprio porque não há alternativa arquitetural em disputa, só a aplicação do ADR-014 um nível acima.

### Decision — 2026-08-18 (W08-002)
- **Decision**: A carteira entra na comparação como **índice de performance time-weighted** (valor de cota, base 100), não como valor patrimonial. `beta` é reportado **apenas** contra benchmark do tipo `INDEX`. `return_ratio` ("% do CDI") só é reportada quando **ambos** os retornos são estritamente positivos.
- **Reason**: (a) Sem time-weighting, uma carteira que recebe aporte mensal apareceria batendo qualquer benchmark num ano em que o investidor perdeu dinheiro — o aporte entra como se fosse rentabilidade (regra 26). Entregar o resultado como `PricePoint` faz todo o `app.quant` da W07 ler a carteira sem adaptador. (b) Beta contra o CDI não é uma grandeza: o CDI quase não varia, então `cov/var` divide por quase-zero. Pior, **não** sairia `None` sozinho — a variância não é exatamente zero, então a guarda dentro de `beta` não dispara e um número enorme e instável seria reportado com cara de fato. (c) A razão foi restringida **por evidência de dado real**: o IBOV caindo 5,96% contra um IPCA de +0,07% na janela produziu razão **-85,16**, e contra um CDI de +3,32% produziu **-1,80** ("-180% do CDI" não significa nada para quem lê). `excess_return` é correto nos três casos e é o número a mostrar.
- **Status**: 🟢 APPROVED. Registrado em [ADR-019](decisions/ADR-019-portfolio-return-is-time-weighted.md).

### Decision — 2026-08-18 (W08-001)
- **Decision**: Benchmark de taxa (CDI, IPCA, Selic) é gravado **como a taxa publicada**, convertida de percentual para fração, e **nunca** como índice acumulado. O índice é derivado na leitura. Benchmark de nível (IBOV) é gravado como o nível publicado. Taxa livre de risco anualiza em **base 252**. Observação cujo **período ainda não terminou** é rejeitada, não gravada. Catálogo de benchmarks vive em código, não em tabela.
- **Reason**: Acumular é operação com parâmetro — o índice depende da data-base, que é diferente para cada carteira e cada janela de tela; gravar um índice congela uma data-base que ninguém pediu e perde a taxa diária, que não é recuperável. A base 252 **foi verificada contra a própria fonte**, não deduzida: compor a série 12 do SGS (CDI diário) em 252 reproduz a série 4389 (CDI anualizado) na precisão publicada — 0,043739% → 11,6499% contra 11,65% em 2024-01-02, e 0,051660% → 13,8998% contra 13,90% em 2026-08-17. Isso também fecha sem resíduo com o `_periodic_rate` da W07, que de-anualiza com `PERIODS_PER_YEAR[DAILY] = 252`. A rejeição de período incompleto estende o ADR-016: a Brapi devolve a **sessão em curso** dentro de `historicalDataPrice` com `adjustedClose` preenchido (a guarda do ADR-016 não dispara), e três requisições ao `^BVSP` em poucos minutos devolveram 166851,5156 → 166978,9375 → 166923,3438 **para a mesma data** — como a ingestão nunca reescreve data gravada, o primeiro a chegar ficaria congelado como "o fechamento do Ibovespa".
- **Status**: 🟢 APPROVED. Registrado em [ADR-018](decisions/ADR-018-benchmark-representation.md).

---

## Future Work
- ✅ ~~**`dy` a partir da DMVL/DMPL da CVM**~~ — **FEITO em 2026-08-19** (EVENTS-001): `5.04.06` + `5.04.07` na coluna `Patrimônio Líquido`, com `5.04.11` (prescritos) excluído e o sinal tratado como apresentação. Os 10 indicadores passaram a ter insumo real.
- **Magnitude do evento societário** — o que a EVENTS-002 deliberadamente não entregou. A data e a natureza vêm de graça do arquivo da B3; o **fator** de desdobramento/grupamento e o **valor por pagamento** do provento exigem outra fonte, e são o que a série de retorno total consome. É a EVENTS-003, a task corrente.
- **Persistir os eventos societários.** Hoje `get_corporate_events` varre o arquivo em cache a cada chamada — não há tabela, migration nem endpoint. Dimensionar isso é parte da EVENTS-003, e vale medir antes: são ~15 MB destilados por ano e uma varredura por ano civil.
- ✅ ~~**Histórico de preços é o que ainda trava `pe`/`pb` no banco real**~~ — **FEITO em 2026-08-19** (wave PRICE): o COTAHIST da B3 entrou como fonte aberta e o backfill da PETR4 gravou 1.495 pregões, com `pe`/`pb` reais nos seis exercícios. ⚠️ **A W13 continua travada pelo mesmo motivo de antes**: backtesting precisa de retorno **total**, e o que existe é preço bruto.
- **Valor de mercado como base da concentração**: hoje o pilar de Diversification e o alocador leem custo de aquisição, deliberadamente ([ADR-021](decisions/ADR-021-allocation-ranks-by-coverage-tier.md)). Quando a W11 trouxer valor de mercado, os dois devem migrar **juntos** — são a mesma exposição por desenho.
- **Modelar caixa da carteira.** A base da alocação é `custo das posições + aporte`, e o que sobra fica implicitamente como caixa sem estar registrado em lugar nenhum. `portfolio_snapshots.cash_value` existe e não é usado.
- **Teto de 3 meses de histórico da Brapi no plano gratuito** (ver Known Issues): resolvido para **ações** pela wave PRICE, que troca a fonte pela B3. Continua aberto para o **IBOV**, cuja série ainda vem do fornecedor — o que mantém `beta` com janela estatisticamente pobre. Decidir: assinar plano pago, achar fonte aberta para o índice, ou aceitar o teto.
- **`app/data/models/__init__.py` entra na lista de lint pré-existente**: `ruff` (I001, RUF022) e `black` já falhavam nele **antes** da W08-001 — confirmado rodando as ferramentas na versão do `HEAD`. A task tocou o arquivo apenas para registrar o novo model, mantendo o estilo existente; reformatá-lo é a task dedicada de lint cleanup (regra 134).
- **MWR / TIR (retorno ponderado por dinheiro)** para a carteira. A W08-002 entregou a **TWR**, que neutraliza aportes e é a métrica certa para comparar contra um índice ([ADR-019](decisions/ADR-019-portfolio-return-is-time-weighted.md)). A MWR responde outra pergunta legítima — *quanto o meu dinheiro rendeu, dado quando eu aportei* — e é a que julga as decisões de aporte do investidor. Não é substituta: as duas devem aparecer lado a lado, com rótulos que as distingam. Provável W11, junto da tela que as apresente.
- **Volatilidade de carteira** (nao a media das volatilidades dos ativos): exige matriz de covariancias entre os ativos e os pesos das posicoes, porque ativos pouco correlacionados cancelam risco. Depende dos pesos, que vem do motor de posicoes. **Nao aproximar por media.** Provavel W09/W11, e o primeiro lugar onde `numpy` pode voltar a ser uma pergunta legitima.
- Cache com Redis para cotações em tempo real.
- Suporte a WebSocket para streamings intraday.
- Modelos avançados de otimização de portfólio (Markowitz / Black-Litterman).
- ~~Verificar/aplicar `alembic upgrade head` contra um PostgreSQL real~~ — **FEITO em 2026-08-18** (W06-004): `001`→`004` aplicadas em PostgreSQL 16, após corrigir `context.is_offline()` → `is_offline_mode()` em `migrations/env.py`.
- ✅ ~~Resolver o drift que faz `alembic check` falhar~~ — **FEITO em 2026-08-19** (FIX-001, migration `009`). Falta só **ligá-lo no CI**, que é a Wave 26.
- ✅ ~~Decidir o destino da ingestão de fundamentals agora que os módulos saíram do plano gratuito da Brapi~~ — **DECIDIDO em 2026-08-18** ([ADR-020](decisions/ADR-020-cvm-primary-fundamentals-source.md)): dados abertos da CVM como fonte primária, Brapi só na ponte ticker→CNPJ.
- Converter `intraday_prices` OHLC para `NUMERIC` na Wave 15 e `portfolio_snapshots.total_value/cash_value` na Wave 11 (mesma motivação da regra 17 do AGENTS.md, deliberadamente fora do escopo da correção de 2026-08-16). **`investor_profiles.monthly_contribution` perdeu o prazo**: a Wave 09 passou e não o converteu, embora agora seja o único consumidor dele — `monthly_contribution_for` lê o `float` e converte via `str` para não pegar a expansão binária. Continua `Float` no banco; a conversão não tem mais wave associada.
- Validar `BrapiProvider` (`backend/app/integrations/market_data/brapi.py`) contra uma resposta real da API assim que houver acesso de rede — os nomes de campo (`regularMarketPrice`, `historicalDataPrice`, etc.) foram inferidos da documentação pública, não de uma chamada real.
- Lint: `ruff check` aponta findings pré-existentes (anteriores a esta sessão) em arquivos não tocados nas Waves 03/04/05 (`app/data/models/fundamentals.py`, `users.py`, `daytrade.py`, `recommendations.py`, `app/core/logging.py`, `app/data/database.py`, `app/api/routes/health.py`, `tests/test_health.py`) — majoritariamente import-sorting e `Optional`/`List` → `X | None`/`list`. Além disso, os `__init__.py` vazios do projeto (`app/domain/__init__.py`, `app/domain/users/__init__.py`, e agora `app/integrations/__init__.py`, `app/integrations/market_data/__init__.py`) usam `""` como conteúdo, o que dispara `D419`/reformatação do `black` — padrão pré-existente replicado por consistência. Não corrigido agora por estar fora do escopo das tasks em andamento (regra 134 do AGENTS.md); considerar uma task dedicada de lint cleanup.

---

## Last Execution
- **Timestamp**: 2026-08-20T00:00:00-03:00
- **Action**: **DOC-002** — sincronização da documentação com o código depois das duas primeiras tasks da wave EVENTS. As tasks tinham sido entregues e commitadas (`f330a4c`, `a4700d2`) com `PROJECT_CONTEXT.md` e `BACKEND.md` já atualizados, mas as camadas de memória e o ledger ainda descreviam o projeto como "entre waves, wave PRICE concluída". Escritos os **[ADR-024](decisions/ADR-024-refill-fills-null-columns.md)** (preenchimento de coluna nula) e **[ADR-025](decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md)** (evento pelo contador de distribuição), que as duas tasks produziram e que não existiam; atualizados o índice de ADRs, `DATABASE.md` (migration `011`), `API.md` (`?refill=true`/`refilled`), `BACKEND.md` (o padrão de coluna nova), `ROADMAP.md` (as duas waves inseridas passaram a constar, e as pendências transversais foram reconciliadas), este ledger e as quatro camadas de memória.
- **Result**: Sucesso, **sem alteração de código** — direção do CLAUDE.md §3, o código é a fonte de verdade. Verificado antes de escrever: `pytest -q` → **701 passed**, `ruff check .` e `black --check .` limpos no repositório inteiro. **A afirmação corrigida que mais importava**: o ledger dava a wave EVENTS como inexistente e o `dy` como pendente, quando os 10 indicadores já têm insumo desde a EVENTS-001. Achados de documentação estagnada, corrigidos junto: o `ROADMAP.md` nunca registrou a wave PRICE (que fechou no dia anterior) e listava como pendentes seis itens já fechados em W06-004/FIX-001 (`alembic upgrade head` em Postgres real, recomputação de indicadores, lint do backend, `npm run lint`, drift do `alembic check`, destino da ingestão de fundamentals). ⚠️ **Não verificado nesta sessão**: o estado do banco real — o Docker está desligado, então as contagens do PostgreSQL vêm dos registros das tasks, não de consulta nova.
- **Action anterior**: **Wave EVENTS**, tasks 1 e 2. **EVENTS-001** (`f330a4c`): distribuições por exercício da DMPL da CVM (`5.04.06` + `5.04.07`, coluna `Patrimônio Líquido`, prescritos `5.04.11` excluídos, sinal tratado como apresentação), coluna `fundamentals.dividends_paid` (migration `011`), e `?refill=true` para que períodos já gravados alcancem uma coluna que o código aprendeu a ler depois ([ADR-024](decisions/ADR-024-refill-fills-null-columns.md)). **EVENTS-002** (`a4700d2`): `CorporateEventProvider` e `get_corporate_events` no `B3CotahistProvider` — data e natureza do evento pelo **contador de distribuição** (`DISMES`), nunca pelo marcador do `ESPECI`, e sem magnitude ([ADR-025](decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md)).
- **Result**: Sucesso. **686 testes** após a EVENTS-001 e **701** após a EVENTS-002 (era 672); migration `011` aplicada em PostgreSQL 16 real com `alembic check` limpo. **O resultado que a EVENTS-001 existia para produzir**: `dy` era o último dos 10 indicadores com fórmula e sem fonte, e passou a valer 0,22 em 2024 e **0,70 em 2022** para a PETR4 — os 70% não são erro de parsing, é o *payout* do ano recorde contra uma ação a R$ 24,50. A armadilha que a task expôs valia mais que a coluna: período gravado é congelado com os campos conhecidos no dia da ingestão, então as duas colunas anteriores (`ebit`, `shares_outstanding`) só funcionaram por terem chegado a um banco vazio. Na EVENTS-002, **o marcador de ex- foi medido e reprovado como sinal**: persiste ~8 pregões e decai (`EDJ` → `EJ`, 132 sessões em 2024 parecendo evento novo), e a BBAS3 mostra duas distribuições sob marcador imóvel (contador 323, 323, 324). O contador foi conferido no sentido inverso em 2024 inteiro — 2.230 papéis, 7.312 incrementos, nunca decrescendo, e só 13 letras sem incremento, **nenhuma movendo preço em 25% ou mais**. Duas letras mudaram de nome por evidência (`EB` → `BONUS_OR_SPLIT`, `R` → `OTHER_DISTRIBUTION`). Registrado e **não** resolvido: sem magnitude não há série de retorno total, então o pilar de Risco segue ausente e a cobertura do score segue em 0,75.
- **Action anterior**: Wave **PRICE** (inserida) — histórico de preços de fonte aberta, B3 COTAHIST. Três tasks. **PRICE-001**: `B3CotahistProvider` + `CotahistArchive` sobre a série COTAHIST (um ZIP por ano civil, ~79 MB, posição fixa de 245 bytes, latin-1); `MarketDataProvider` partido em `DailyHistoryProvider` (só histórico) e `MarketDataProvider` (histórico + cotação); destilação para mercado à vista no download; factory e configuração. **PRICE-002** ([ADR-023](decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md), emenda ao ADR-016): `asset_prices.adjusted_close` passa a aceitar `NULL` (migration `010`), a semântica da ausência passa a pertencer à fonte (`reports_adjusted_close`), e `app/domain/market_data/series.py` vira o ponto único de construção de série de retorno. **PRICE-003**: `POST /assets/{ticker}/prices/backfill`, com a tradução de erro compartilhada com `/prices/sync` extraída em vez de copiada.
- **Result**: Sucesso. **672/672 testes** (617 + 55 novos), `ruff check .` e `black --check .` limpos no repositório inteiro, migration `010` aplicada em PostgreSQL 16 real com round-trip `downgrade`/`upgrade` e `alembic check` sem drift. **O resultado que a wave existia para produzir**, medido no banco real que tinha `asset_prices` vazia: backfill da PETR4 2020–2025 inseriu **1.495 pregões, 0 rejeitados**, e `pe`/`pb` — `None` nos seis exercícios — passaram a ser reais: P/L **12,74** em 2024 (LPA R$ 2,84 sobre fechamento de R$ 36,19, ambos conferidos contra número público) e **1,70** em 2022, que é o que o mercado de fato viu no ano dos lucros recordes da Petrobras. O pilar de **Valuation** saiu de ausente para **93,5** e a cobertura do score de **0,55 para 0,75**, pela terceira vez **sem uma linha alterada em `scoring.py`**. **Duas descobertas na validação contra o arquivo real mudaram o código**: (a) `FATCOT` é fator de cotação de verdade — FNOR11 é cotado por 1.000 ações e SMLL11 por 10, e a normalização foi reconciliada contra o `VOLTOT/QUATOT` do próprio registro (0,00070125 por ação no FNOR11, que só o valor normalizado alcança), mesma técnica que a W09-003 usou com o LPA; (b) `adjusted_close` **não pode** ser copiado do `close` — medido em dado real, o grupamento 1:10 da MGLU3 em 2024-05-27 vale **+896% num pregão**, e tratado como ajustado entraria em `volatility`, `max_drawdown`, `beta` e `sharpe`. O arquivo **marca** o evento (`ESPECI` vira `ON  EG  NM`) e **não dá o fator**. Um defeito real apareceu porque o teste exercitou o caminho de 404 de verdade: o arquivo temporário era apagado **enquanto ainda estava aberto**, o que no Windows é `PermissionError` — um ano ausente virava erro fatal em vez de ser pulado. Registrado e **não** resolvido: o pilar de **Risco** continua ausente, por decisão — métrica de risco exige série de retorno total e a bolsa publica preço negociado; a correção é a montante, ingerindo eventos societários e proventos, que é a mesma ingestão que destrava o `dy`.
- **Action anterior**: FIX-001 — varredura dos Known Issues, corrigindo **tudo que tinha correção possível**. Oito itens fechados: `get_quote()` sem endpoint (`GET /assets/{ticker}/quote`), `PriceSyncRequest` sem validação de `end` futura, `env_file` relativo ao cwd, drift do `alembic check` (migration `009_drop_dup_uniques`), `investor_profiles.monthly_contribution` em `Float` (migration `008_numeric_contribution`), lint pré-existente do backend, `npm run lint` quebrado, e os dois defeitos de código que a limitação de `range` da Brapi escondia. Migrations `008` e `009` aplicadas em PostgreSQL 16 real, com round-trip `downgrade`/`upgrade`.
- **Result**: Sucesso. **617/617 testes** (596 + 21 novos), `ruff check .` e `black --check .` limpos **no repositório inteiro** pela primeira vez desde a Wave 02, `alembic check` sem drift, `npm run lint` e `npm run build` passando. O achado que mais importa não estava na lista: `_brapi_range_for` escolhia o bucket de `range` pelo **tamanho da janela** (`end - start`), mas todo range da Brapi **termina em hoje** — pedir duas semanas do trimestre passado mandava `range=5d`, que não contém um único pregão do intervalo pedido, e a resposta voltava **vazia, sem erro nenhum**. O sintoma documentado (falhar acima de 3 meses) era o barulhento; este era o silencioso, e é o que corromperia um backfill sem ninguém perceber. Ambos corrigidos: o bucket agora é medido de `start` até hoje, e o teto virou configuração (`BRAPI_MAX_RANGE`) com recusa local e nomeada (`MARKET_DATA_WINDOW_TOO_LARGE`, HTTP 400) em vez de gastar uma requisição de cota mensal para ouvir não. Dois outros defeitos apareceram só porque a ferramenta foi ligada: o ESLint achou um import morto no primeiro uso, e ao validar `npm run lint` descobriu-se que **`npm run build` também estava quebrado** e não constava de lista nenhuma (`tsc` reprovava `React` não usado e `import.meta.env` sem os tipos do `vite/client`). Quatro testes existentes passaram a falhar corretamente ao adotar o range ancorado em hoje — usavam datas fixas de janeiro, fora do que o plano serve — e foram reancorados em datas relativas. Por fim, versionar o `package-lock.json` levou a construir e **executar** as imagens Docker, o que expôs um defeito que `docker compose config` jamais pegaria: **nenhum dos dois contextos tinha `.dockerignore`**, então o `COPY . .` copiava o build do host para dentro da imagem. No frontend isso a **quebrava** — o `node_modules` do Windows sobrescrevia o que o `npm ci` instalara, e o `eslint` do container tentava executar `node.exe`; era latente desde a W01 e só ficou ativo porque esta sessão rodou `npm install`. No backend era peso morto (`.venv` de outra plataforma e `var/cvm/`, ~13 MB por exercício). Corrigidos com `.dockerignore` nos dois, `node:20-alpine` no frontend (o Node 18 está fora de suporte e não satisfaz o `engines` do ESLint 10) e `npm ci` em lugar de `npm install`. Ambas as imagens reconstruídas e executadas: `npm run lint` roda dentro do container e `import app.main` funciona no backend.
- **Action anterior**: DOC-001 — varredura e correção de **todas** as inconsistências documentação × código registradas em `docs/memory/PROJECT_STATUS.md`. Oito estavam catalogadas e nove outras apareceram durante a verificação. Arquivos alterados: `AGENTS.md` (§5.1, §6, §7.1, §11, §67, §93, §94, §127, §131 e o Wave Execution Protocol), `README.md`, `CLAUDE.md`, `.env.example`, `docs/PROJECT_STATUS.md`, `docs/memory/PROJECT_STATUS.md`, `docs/architecture/BACKEND.md`, `docs/architecture/FRONTEND.md`.
- **Result**: Sucesso, **sem alteração de código** — a direção da correção seguiu o CLAUDE.md §3 (o código é a fonte de verdade), então quem mudou foi o documento em todos os 17 casos. `pytest -q` → **596 passed**, idêntico ao baseline anterior, o que é o que se espera de uma task que não tocou em `.py`. As três divergências estruturais mais antigas (`data/repositories/`, `docs/waves/`, `CHANGELOG.md`) deixaram de ser "pendências" e passaram a **ausências declaradas**, com o motivo escrito e link para o ADR quando havia um — o objetivo é que a próxima sessão que ler o AGENTS.md e depois o código não tente "consertar" o código. Achados novos que mais importam: o baseline de testes no CLAUDE.md estava em 205 contra 596 reais; o `.env.example` documentava só até a Wave 05, omitindo justamente os `*_MIN_REQUEST_INTERVAL_SECONDS` que a Known Issue nº 13 manda ajustar antes de qualquer ingestão em lote; e o *Architecture Status* deste ledger ainda dava o Quant Engine como `NOT_STARTED` com NumPy/Pandas/SciPy, duas coisas que a W07 e o adendo ao ADR-017 já haviam desmentido.
- **Action anterior**: W09-004 — alocação do aporte mensal. `app/domain/recommendations/allocation.py` (puro: política, ranking por faixa de cobertura, tetos, motivo de cada exclusão), `plan_contribution` no service, `GET /portfolios/{id}/contribution-plan` com override de todo limite. **Wave 09 concluída.**
- **Result**: Sucesso. 596/596 testes (555 + 41 novos), `ruff`/`black` limpos nos arquivos alterados. Validado contra o banco real: PETR4 pontua **92,63 com cobertura 0,55**, passa o piso e recebe **R$ 200 limitado pelo teto de 20%** — com R$ 800 reportados como `unallocated` porque só há um ativo acompanhado. Dois defeitos apareceram nos testes escritos à mão, ambos de desenho e não de digitação: (a) `MAX_POSITIONS = 3` tornava o **primeiro** aporte estruturalmente inexecutável, porque na carteira vazia a base é o próprio aporte e o teto de 20% vale R$ 200 — 3 fatias deixariam R$ 400 parados por meses; corrigido para 5, que é `1 / MAX_ASSET_WEIGHT`; (b) com teto de setor e cota por posição empatados, o motivo relatado é o primeiro da ordem fixa, o que o teste documenta em vez de mascarar.
- **Action anterior**: W09-003 — ações em circulação por exercício. `fundamentals.shares_outstanding` (`NUMERIC(20,0)`) + migration `007`; parse de `dfp_cia_aberta_composicao_capital_{ano}.csv` em `CvmFundamentalsProvider`, com a **unidade reconciliada contra o LPA do próprio arquivo** antes de gravar; contagem negativa rejeitada no data quality; insumo propagado até `IndicatorInputs`.
- **Result**: Sucesso. 555/555 testes (542 + 13 novos), `ruff`/`black` limpos nos arquivos alterados, migration `007` aplicada em PostgreSQL 16 real. Validado contra números públicos: LPA da PETR4 2024 dá **R$ 2,84**, o publicado; VALE3 7,40 contra 7,39; MGLU3 0,61 contra 0,61. As séries reproduzem eventos societários reais (desdobramento da WEGE3, bonificação da PSSA3, grupamento da MGLU3). **A descoberta que mudou o desenho**: o arquivo não tem coluna de escala e ~1/3 dos declarantes escreve a contagem em milhares, alternando de ano para ano — a própria Petrobras. Sem a reconciliação, o P/L sairia mil vezes menor e **clamparia em 100** numa escala invertida, mandando as leituras mais quebradas para o topo do ranking que a alocação vai consumir. Registrado também: no banco real `pe`/`pb` seguem ausentes por **falta de preço histórico**, não por falta de contagem.
- **Action anterior**: W09-001 (motor de sub-scores) + W09-002 (fonte CVM). `app/domain/recommendations/{scoring,service,schemas}.py` com cinco pilares decomponíveis e ausência de primeira classe; `GET /portfolios/{id}/scores`. `app/integrations/fundamentals/{cvm,identity,composite}.py` + `app/domain/fundamentals/identity.py` + migration `006` (`assets.cnpj`).
- **Result**: Sucesso. 542/542 testes (449 → 499 → 542), `ruff`/`black` limpos nos arquivos alterados, migration `006` aplicada em PostgreSQL 16 real. Validado ao vivo: 6 exercícios da PETR4 pela CVM batendo com o publicado (lucro R$ 188,3 bi em 2022, R$ 36,6 bi em 2024; ROE 10,0%). **Medido no banco real, Quality e Growth foram de ausentes para 97,8 e 76,7 e a cobertura do score de 40% para 55%, sem uma linha alterada em `scoring.py`.** Os testes escritos à mão pegaram de novo um defeito meu: numa escala invertida, um P/L negativo clampava no extremo *bom* e marcaria 100.
- **Action anterior**: W08-002 — Comparativo carteira/ativo × benchmark. `benchmarks/series.py` (taxa → índice acumulado, taxa anualizada da janela), `portfolio/performance.py` (índice time-weighted a partir do ledger + `asset_prices`), `benchmarks/comparison.py` (puro, só orquestra o `app.quant`), assembly em `benchmarks/service.py`, endpoints `GET /assets/{ticker}/benchmarks/{code}` e `GET /portfolios/{id}/benchmarks/{code}`. **`beta`, `sharpe` e `sortino` deixaram de retornar `None` — o objetivo da wave.**
- **Result**: Sucesso. 449/449 testes (391 + 58 novos), `ruff`/`black` limpos nos arquivos alterados. Validado contra o dado real já ingerido: IBOV × CDI na janela 2026-05-20..2026-08-17 dá -5,96% contra +3,32% (excesso -9,28 p.p., Sharpe -2,34, CDI anualizado 14,20% a.a.), e IBOV × IBOV dá excesso 0,00% com **beta exatamente 1,0000** — a sanidade mais forte possível para o alinhamento por data. Um teste escrito à mão pegou um defeito real no `performance_index`: eventos do ledger em datas sem preço eram ignorados por completo (quantidades **e** fluxos), corrigido com varredura por ponteiro.
- **Action anterior**: W08-001 — Benchmark Engine, ingestão. `BenchmarkProvider` abstrato + `BcbSgsProvider` (BCB/SGS, aberto e sem cota) + `BrapiIndexProvider` (delega ao `MarketDataProvider`, sem parser próprio) + factory; catálogo em código (CDI, SELIC, IPCA, IBOV); `benchmark_values` (`NUMERIC(24,12)`) + migration `005`; `validate_benchmark_series` com `INCOMPLETE_PERIOD`; `sync_benchmark_series` idempotente; endpoints de catálogo/sync/leitura. **Parsers validados contra as APIs reais antes de qualquer mock** (ADR-018).
- **Result**: Sucesso. 391/391 testes (316 + 75 novos), `ruff`/`black` limpos nos arquivos alterados, migration `005` aplicada em PostgreSQL 16 real com round-trip `downgrade`/`upgrade`. Ingestão real executada: CDI 252 pregões (acumulado 14,67% no ano), IPCA 31 meses (2024 fecha em 4,83%, igual ao IBGE), IBOV 63 pregões com a sessão em curso corretamente rejeitada; segunda passada inseriu 0 e pulou 63 (idempotência). 3 requisições à Brapi.
- **Action anterior**: W07-002 — `app/quant/risk.py`: `standard_deviation`, `downside_deviation`, `volatility`, `max_drawdown`, `beta`, `sharpe`, `sortino`. `PERIODS_PER_YEAR` local (252 diario), alinhamento por data antes de medir retornos no beta, taxa livre de risco de-anualizada geometricamente. Fronteira `Decimal -> float` resolvida como inexistente (adendo ao ADR-017). **Wave 07 concluida.**
- **Result**: Sucesso. 316/316 testes passando (262 + 54 novos), `ruff` e `black` limpos nos arquivos alterados. Nenhuma regressao. Zero requisicoes externas.

---

## Next Action
**EVENTS-003 — série de retorno total.** A wave EVENTS está 2/3. O que já existe: o **preço bruto** no banco (1.495 pregões), a **data e a natureza** de todo evento societário (de graça, décadas atrás) e o **provento agregado por exercício**. O que falta é a **magnitude** — fator de desdobramento/grupamento e valor do provento por pagamento — e o `adjusted_close` derivado dela, que é o que destrava o pilar de Risco, a cobertura do score (0,75 → 1,00) e o backtesting da W13. A fonte da magnitude é a decisão a tomar antes de começar; ver `docs/memory/CURRENT_TASK.md`. Depois da wave, a **Wave 10 — Rebalanceamento** (roadmap §22, AGENTS.md §34) volta a ser a próxima do roadmap.
