# Project Status — Investment Assistant

## Project Overview
Plataforma pessoal de análise e acompanhamento de investimentos com foco no mercado brasileiro (B3), acompanhamento patrimonial, recomendações quantitativas de aportes, análise de risco e módulo de Day Trade com Paper Trading.

---

## Current Phase
- **Phase**: Wave 04 (Portfolio Management) -> Wave 05 (Market Data Integration)
- **Status**: 🟡 IN_PROGRESS

---

## Overall Progress
- **Total Waves**: 33 (W00 a W32)
- **Completed Waves**: 5 (W00, W01, W02, W03, W04)
- **In Progress Waves**: 0
- **Pending Waves**: 28

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
Status: ⚪ NOT_STARTED

- [ ] **W05-001**: Abstração `MarketDataProvider` e integração Brapi ⚪ NOT_STARTED
- [ ] **W05-002**: Ingestão de Cotizações Diárias e Caching ⚪ NOT_STARTED
- [ ] **W05-003**: Data Quality Validator (validação de outliers/nulos) ⚪ NOT_STARTED

---

### Wave 06 — Fundamental Data
Status: ⚪ NOT_STARTED

- [ ] **W06-001**: Ingestão de Demonstrativos Financeiros ⚪ NOT_STARTED
- [ ] **W06-002**: Cálculo e Normalização de Indicadores Fundamentalistas ⚪ NOT_STARTED

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

Wave: 04
Task ID: W04-001
Task Name: Endpoints CRUD de Carteiras e Ativos
Status: ⚪ NOT_STARTED

Completed:
- Wave 00 (Foundation) concluída.
- Wave 01 (Scaffold Backend & Frontend + Pytest + Docker Config) concluída.
- Wave 02 (Database Schema & Migrations) concluída (13 tabelas criadas no SQLAlchemy 2.0 + Migration Alembic `001_initial_schema.py` + 3 testes passando).
- Wave 03 (Authentication & Users) concluída (hashing bcrypt + JWT, endpoints register/login/refresh/me, `get_current_user`, 18 testes novos passando).
- Correção de precisão monetária pós-Wave 02 (`Float` -> `NUMERIC(18,6)`/`Decimal` em `transactions` e `asset_prices`, migration `002_numeric_money_columns.py`), decidida com o usuário.
- W04-001 (CRUD de carteiras e ativos) concluída — 12 testes novos passando.
- W04-002 (registro de transações + guarda de venda insuficiente) concluída — 9 testes novos passando.
- W04-003 (endpoint de posições consolidadas + testes unitários do motor) concluída — 15 testes novos passando. **Wave 04 completa.**

Remaining (Wave 05 — Market Data Integration):
- W05-001: Abstração `MarketDataProvider` e integração Brapi.
- W05-002: Ingestão de cotações diárias e caching.
- W05-003: Data Quality Validator (outliers/nulos/OHLC inválido).

Next Action:
Ler `docs/roadmap.md` (Wave 5) e planejar W05-001 (`MarketDataProvider` + `BrapiProvider`) em `backend/app/integrations/market_data/`.

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

---

## In Progress
Nenhuma tarefa em progresso no momento. Wave 04 concluída. Próxima: W05-001 (Wave 05 — Market Data Integration).

---

## Blocked Tasks
Nenhuma tarefa bloqueada no momento.

---

## Known Issues
Nenhum problema conhecido no momento.

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

---

## Future Work
- Cache com Redis para cotações em tempo real.
- Suporte a WebSocket para streamings intraday.
- Modelos avançados de otimização de portfólio (Markowitz / Black-Litterman).
- Verificar/aplicar `alembic upgrade head` (migration `002_numeric_money_columns`) contra um PostgreSQL real assim que o Docker/`docker compose up` estiver disponível — não foi possível validar neste ambiente (Docker Desktop parado).
- Converter `intraday_prices` OHLC para `NUMERIC` na Wave 15; `portfolio_snapshots.total_value/cash_value` na Wave 11; `investor_profiles.monthly_contribution` na Wave 09 (mesma motivação da regra 17 do AGENTS.md, deliberadamente fora do escopo da correção de 2026-08-16).
- Lint: `ruff check` aponta ~30 findings pré-existentes (anteriores a esta sessão) em arquivos não tocados nas Waves 03/04 (`app/data/models/fundamentals.py`, `users.py`, `daytrade.py`, `recommendations.py`, `app/core/config.py`, `app/core/logging.py`, `app/data/database.py`, `app/api/routes/health.py`, `tests/test_health.py`, `app/domain/__init__.py`, `app/domain/users/__init__.py`) — majoritariamente import-sorting e `Optional`/`List` → `X | None`/`list`. Não corrigido agora por estar fora do escopo das tasks em andamento (regra 134 do AGENTS.md); considerar uma task dedicada de lint cleanup.

---

## Last Execution
- **Timestamp**: 2026-08-16T00:00:00-03:00
- **Action**: W04-003 (Wave 04) — `GET /api/v1/portfolios/{id}/positions`, expondo o motor de posições (`compute_positions`/`compute_net_contributions`) com testes unitários dedicados (casos conhecidos: preço médio ponderado, venda parcial/total, dividendos, aportes/retiradas, ordem cronológica). **Wave 04 concluída.**
- **Result**: Sucesso. 56/56 testes automatizados passando (`pytest`), `ruff check` e `black --check` limpos nos arquivos alterados. Nenhuma regressão nas waves anteriores.

---

## Next Action
Ler `docs/roadmap.md` (Wave 5 — Market Data) e `AGENTS.md` (seções 19, 21, 22, 23) e planejar W05-001 (`MarketDataProvider` + `BrapiProvider`) em `backend/app/integrations/market_data/`, seguido de W05-002 (ingestão/caching) e W05-003 (data quality validator).
