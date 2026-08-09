# Project Status — Investment Assistant

## Project Overview
Plataforma pessoal de análise e acompanhamento de investimentos com foco no mercado brasileiro (B3), acompanhamento patrimonial, recomendações quantitativas de aportes, análise de risco e módulo de Day Trade com Paper Trading.

---

## Current Phase
- **Phase**: Wave 02 (Database Schema & Migrations) -> Wave 03 (Authentication & Users)
- **Status**: 🟡 IN_PROGRESS

---

## Overall Progress
- **Total Waves**: 33 (W00 a W32)
- **Completed Waves**: 3 (W00, W01, W02)
- **In Progress Waves**: 1 (W03)
- **Pending Waves**: 29

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
- **Database**: PostgreSQL 16 + SQLAlchemy 2.0 Models + Alembic 001 Migration (`backend/app/data/models`) 🟢 COMPLETED
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

---

### Wave 03 — Authentication & Users
Status: 🟡 IN_PROGRESS

- [ ] **W03-001**: Hashing de senha (Passlib/Bcrypt) e Tokens JWT (`backend/app/core/security.py`) 🟡 IN_PROGRESS
- [ ] **W03-002**: Endpoints de Cadastro, Login, Refresh Token e Me ⚪ NOT_STARTED
- [ ] **W03-003**: Dependencies de Autenticação e Proteção de Rotas (`get_current_user`) ⚪ NOT_STARTED

---

### Wave 04 — Portfolio Management
Status: ⚪ NOT_STARTED

- [ ] **W04-001**: Endpoints CRUD de Carteiras e Ativos ⚪ NOT_STARTED
- [ ] **W04-002**: Registro de Transações (BUY, SELL, DIVIDEND, DEPOSIT, WITHDRAWAL) ⚪ NOT_STARTED
- [ ] **W04-003**: Motor de Posições Consolidadas (Preço Médio e Saldo) ⚪ NOT_STARTED

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

Wave: 03
Task ID: W03-001
Task Name: Hashing de senha e Tokens JWT
Status: 🟡 IN_PROGRESS

Completed:
- Wave 00 (Foundation) concluída.
- Wave 01 (Scaffold Backend & Frontend + Pytest + Docker Config) concluída.
- Wave 02 (Database Schema & Migrations) concluída (13 tabelas criadas no SQLAlchemy 2.0 + Migration Alembic `001_initial_schema.py` + 3 testes passando).

Remaining:
- Implementar `backend/app/core/security.py` (funções de hash com Passlib/Bcrypt, verificação e criação de Tokens JWT com `python-jose`).
- Implementar schemas Pydantic de autenticação (`Token`, `TokenPayload`, `UserCreate`, `UserLogin`, `UserResponse`) em `backend/app/domain/users/schemas.py`.
- Criar rotas `/api/v1/auth/register`, `/login`, `/me` em `backend/app/api/routes/auth.py`.
- Adicionar middleware/dependency `get_current_user` em `backend/app/api/dependencies.py`.
- Escrever testes unitários e de integração de autenticação (`backend/tests/test_auth.py`).

Next Action:
Implementar o módulo de segurança `backend/app/core/security.py` e schemas de usuário da Wave 03.

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

---

## In Progress
- **W03-001**: Hashing de Senha e Tokens JWT (Wave 03)

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

---

## Future Work
- Cache com Redis para cotações em tempo real.
- Suporte a WebSocket para streamings intraday.
- Modelos avançados de otimização de portfólio (Markowitz / Black-Litterman).

---

## Last Execution
- **Timestamp**: 2026-08-09T15:39:30-03:00
- **Action**: Conclusão da Wave 02 (Database Schema & Migrations) e Inicialização da Wave 03 (Authentication & Users).
- **Result**: Sucesso. Models SQLAlchemy 2.0 criados e validados, migration 001_initial_schema gerada, 3/3 testes automatizados passando.

---

## Next Action
Implementar o módulo de segurança `backend/app/core/security.py` e endpoints de autenticação JWT da Wave 03.
