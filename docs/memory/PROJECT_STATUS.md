# Current Project Status

> Camada 1 da memória: **onde o projeto está**, em uma página.
> Ledger detalhado task-a-task (histórico completo, notas de implementação, decisões datadas): [../PROJECT_STATUS.md](../PROJECT_STATUS.md).
> Última verificação contra o código: **2026-08-17**.

## Current Phase

**Wave 05 concluída → Wave 06 (Fundamental Data) não iniciada.**
6 de 33 waves concluídas (W00–W05). Nenhuma wave em progresso.

## Overall Status

| | |
|---|---|
| **Completed** | W00 Foundation · W01 Scaffold · W02 Database · W03 Auth · W04 Portfolio · W05 Market Data |
| **In Progress** | — nenhuma |
| **Blocked** | — nenhuma |

Baseline verificado nesta análise: `pytest` → **95 passed** (backend/.venv).

## Completed Work (nível wave)

- **W00–W01** — Repositório, `.env.example`, `docker-compose.yml` (postgres+backend+frontend), scaffold FastAPI com `/health` e `/ready`, scaffold React+TS+Vite+Tailwind, Dockerfiles, pytest rodando.
- **W02** — 13 models SQLAlchemy 2.0 + migration `001_initial_schema`. Correção posterior: `002_numeric_money_columns` (`Float` → `NUMERIC(18,6)`/`Decimal` em `transactions` e `asset_prices`).
- **W03** — bcrypt + PyJWT em `core/security.py`; `register` / `login` / `refresh` / `me`; `get_current_user`; envelope de erro global `{"error":{"code","message"}}`.
- **W04** — CRUD de assets e portfolios; ledger de transações com guarda `INSUFFICIENT_POSITION`; motor de posições determinístico (custo médio móvel) derivado 100% do ledger; endpoint `/positions`.
- **W05** — `MarketDataProvider` (abstrato) + `BrapiProvider` (httpx, timeout/retry limitado/throttle) + factory; `sync_daily_history` idempotente (nunca sobrescreve data já armazenada); `validate_daily_bars` (rejeita preço não-positivo, volume negativo, OHLC inconsistente, data duplicada; avisa sobre fora de ordem e variação >50%); read-path lê só do banco.

Detalhe por task: [../history/COMPLETED_TASKS.md](../history/COMPLETED_TASKS.md).

## Current Work

Nenhum trabalho em andamento. O último commit (`97eb29b`) fecha a Wave 05 com árvore limpa.

## Next Recommended Step

**W06-001 — Ingestão de demonstrativos financeiros** (tabela `fundamentals`). Ver [CURRENT_TASK.md](CURRENT_TASK.md).

## Known Issues

Problemas reais, verificados no código (2026-08-17):

1. **Parser da Brapi nunca validado contra resposta real.** `BrapiProvider` foi escrito a partir da documentação pública e testado só com `httpx.MockTransport` (sem rede no ambiente). Os nomes de campo (`regularMarketPrice`, `historicalDataPrice`) podem estar errados. **Bloqueia uso em ingestão real.**
2. **Migration `002_numeric_money_columns` nunca aplicada em PostgreSQL real.** Validada apenas estruturalmente e contra SQLite in-memory (Docker Desktop parado no ambiente). `alembic upgrade head` contra Postgres é obrigatório antes de confiar nela.
3. **`get_quote()` implementado mas não exposto.** Existe no provider e é testado, mas nenhum endpoint o consome — cotação atual não chega ao usuário.
4. **Ingestão de dividendos (proventos) não implementada**, embora o roadmap a liste como entregável da Wave 5 (`docs/roadmap.md` §17). A Wave 05 foi marcada como concluída sem ela.
5. **`npm run lint` quebrado no frontend.** O script chama `eslint` mas não há `eslint` nas `devDependencies` nem arquivo de config.
6. **Lint pré-existente sujo no backend.** `ruff check` acusa findings em arquivos não tocados desde a Wave 02 (`data/models/fundamentals.py`, `users.py`, `daytrade.py`, `recommendations.py`, `core/logging.py`, `data/database.py`, `api/routes/health.py`, `tests/test_health.py`) — import-sorting e `Optional[X]`/`List[X]` → `X | None`/`list[X]`. Deliberadamente fora de escopo até uma task dedicada de cleanup.
7. **Colunas monetárias ainda em `Float`** (dívida conhecida, conversão adiada para a wave que as usar): `intraday_prices` OHLC (W15), `portfolio_snapshots.total_value/cash_value` (W11), `investor_profiles.monthly_contribution` (W09).
8. **`PriceSyncRequest` documenta que `end` não pode ser futura, mas o validador não verifica isso** — apenas `start <= end`.

## Inconsistências documentação × código

Registradas, **não corrigidas** (corrigir exigiria alterar AGENTS.md ou criar código fora de escopo):

| Documentado em | Realidade |
|---|---|
| AGENTS.md §6: `PROJECT_STATUS.md` e `CHANGELOG.md` na raiz | Status está em `docs/PROJECT_STATUS.md`; `CHANGELOG.md` não existe |
| AGENTS.md §6: `backend/app/data/repositories/` | Não existe — rotas usam `Session` do SQLAlchemy diretamente (ver ADR-011) |
| AGENTS.md §6: `backend/tests/{unit,integration,regression}/` | `tests/` é plano, sem subpastas |
| AGENTS.md §6/§93: `docs/architecture.md`, `database.md`, `api.md`, etc. | Não existiam; substituídos por `docs/architecture/*.md` criados nesta sessão |
| AGENTS.md Wave Execution Protocol: `docs/waves/WAVE-XX-*.md` | Diretório `docs/waves/` não existe; as waves vivem em `docs/roadmap.md` e `docs/PROJECT_STATUS.md` |
| AGENTS.md §5.1 / README: React Router, TanStack Query, Zod, Recharts | Instalados no `package.json`, nenhum é importado — o frontend é uma página estática única |
| README: "Frontend 🟢 COMPLETED" | Só existe uma landing page de status; sem rotas, sem estado, sem telas de produto |
| `.env.example`: `ACCESS_TOKEN_EXPIRE_MINUTES=115200` (80 dias) | Default do código é 8 dias (`core/config.py`) |

## Important Context

- **Ambiente**: Windows + PowerShell. Virtualenv em `backend/.venv` — invoque como `.venv\Scripts\python.exe -m pytest`. Docker Desktop estava parado; nada foi validado contra Postgres real.
- **Sem rede de saída** no ambiente onde a Wave 05 foi implementada — daí a lacuna nº 1.
- **Testes rodam contra SQLite in-memory compartilhado** (`tests/conftest.py`), com `app.dependency_overrides` para `get_db` e `get_market_data_provider`. Nenhum teste toca rede ou Postgres.
- **A regra mais estruturante do projeto**: posições nunca são armazenadas — sempre derivadas do ledger de transações (AGENTS.md §16, ADR-002). Não crie tabela de posições.
