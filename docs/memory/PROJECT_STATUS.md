# Current Project Status

> Camada 1 da memória: **onde o projeto está**, em uma página.
> Ledger detalhado task-a-task (histórico completo, notas de implementação, decisões datadas): [../PROJECT_STATUS.md](../PROJECT_STATUS.md).
> Última verificação contra o código: **2026-08-18**.

## Current Phase

**Wave 06 concluída** + manutenção W06-004. Próxima: **Wave 07 — Quant Engine**.
7 de 33 waves concluídas (W00–W06).

⚠️ **Mudança externa relevante**: os módulos de demonstrativos da Brapi saíram do plano gratuito (403 em 2026-08-18). A ingestão de fundamentals está inoperante por plano. Não bloqueia a W07, que só consome `asset_prices`; bloqueia a W09.

## Overall Status

| | |
|---|---|
| **Completed** | W00 Foundation · W01 Scaffold · W02 Database · W03 Auth · W04 Portfolio · W05 Market Data · W06 Fundamental Data |
| **In Progress** | — nenhuma |
| **Blocked** | — nenhuma |

Baseline atual: `pytest` → **215 passed** (backend/.venv).

## Completed Work (nível wave)

- **W00–W01** — Repositório, `.env.example`, `docker-compose.yml` (postgres+backend+frontend), scaffold FastAPI com `/health` e `/ready`, scaffold React+TS+Vite+Tailwind, Dockerfiles, pytest rodando.
- **W02** — 13 models SQLAlchemy 2.0 + migration `001_initial_schema`. Correção posterior: `002_numeric_money_columns` (`Float` → `NUMERIC(18,6)`/`Decimal` em `transactions` e `asset_prices`).
- **W03** — bcrypt + PyJWT em `core/security.py`; `register` / `login` / `refresh` / `me`; `get_current_user`; envelope de erro global `{"error":{"code","message"}}`.
- **W04** — CRUD de assets e portfolios; ledger de transações com guarda `INSUFFICIENT_POSITION`; motor de posições determinístico (custo médio móvel) derivado 100% do ledger; endpoint `/positions`.
- **W05** — `MarketDataProvider` (abstrato) + `BrapiProvider` (httpx, timeout/retry limitado/throttle) + factory; `sync_daily_history` idempotente (nunca sobrescreve data já armazenada); `validate_daily_bars` (rejeita preço não-positivo, volume negativo, OHLC inconsistente, data duplicada; avisa sobre fora de ordem e variação >50%); read-path lê só do banco.

- **W06-001** — `FundamentalsProvider` + `BrapiFundamentalsProvider` + factory; `sync_annual_statements` idempotente; `validate_financial_statements`; endpoints de sync/leitura; migration `003` (`fundamentals` em `NUMERIC(24,4)`). Extraiu também o transporte HTTP compartilhado (`RetryingJsonClient`), agora usado pelas duas integrações.

- **W06-002** — `compute_indicators`: função pura com as **10 fórmulas** implementadas e testadas; `compute_and_store_indicators` idempotente; seleção de preço sem look-ahead (`_price_on_or_before`); endpoints `POST /indicators/compute` (não chama provedor externo) e `GET /indicators`. Política de dado faltante em [ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md).

- **W06-003** — **parsers validados contra a API real da Brapi** (1 requisição). Market data estava correto; fundamentals tinha dois campos errados (`equity`, `debt`) que deixavam `roe` silenciosamente `None`. ROIC destravado com alíquota efetiva derivada por período; migration `004`; política de recomputação ([ADR-015](../decisions/ADR-015-indicator-recomputation.md)).

- **W06-004** (manutenção, 2026-08-18) — PostgreSQL real no ar; migrations `001`→`004` aplicadas de fato, após corrigir um `AttributeError` que impedia o Alembic de rodar. Confirmado que **não havia banco nem dado algum** — a pendência de recomputar indicadores era hipotética. Parser de market data validado contra FII/ETF/banco reais. Fundamentals bloqueado por mudança de plano da Brapi. Custo: 5 requisições.

Detalhe por task: [../history/COMPLETED_TASKS.md](../history/COMPLETED_TASKS.md).

## Current Work

Nada em execução. Wave 06 fechada; pendências operacionais herdadas resolvidas na W06-004 (2026-08-18).

## Next Recommended Step

**Wave 07 — Quant Engine**: `app/quant/returns.py` e `risk.py` sobre `asset_prices`. Ver [CURRENT_TASK.md](CURRENT_TASK.md).

## Known Issues

Problemas reais, verificados no código (2026-08-18):

1. ~~Parsers da Brapi nunca validados~~ — **RESOLVIDO** (W06-003 + W06-004). Market data validado contra resposta real de ação, **FII, ETF e banco**: mesma forma de resposta nas quatro classes, 0 barras rejeitadas. Fundamentals validado só com PETR4 e agora **impossível de reexaminar** no plano gratuito (item 14).
2. ~~Migrations `002`, `003` e `004` nunca aplicadas em PostgreSQL real~~ — **RESOLVIDO em 2026-08-18.** `001`→`004` aplicadas em PostgreSQL 16 real. Para isso foi preciso corrigir `migrations/env.py`, que chamava `context.is_offline()` (inexistente; o correto é `is_offline_mode()`) e abortava com `AttributeError` — ou seja, **o Alembic nunca havia executado**. `alembic heads`/`history` não carregam `env.py`, e por isso a "validação estrutural" anterior não pegou o erro.
3. **`get_quote()` implementado mas não exposto.** Existe no provider e é testado, mas nenhum endpoint o consome — cotação atual não chega ao usuário.
4. **Ingestão de dividendos (proventos) não implementada**, embora o roadmap a liste como entregável da Wave 5 (`docs/roadmap.md` §17). A Wave 05 foi marcada como concluída sem ela.
5. **`npm run lint` quebrado no frontend.** O script chama `eslint` mas não há `eslint` nas `devDependencies` nem arquivo de config.
6. **Lint pré-existente sujo no backend.** `ruff check` acusa findings em arquivos não tocados desde a Wave 02 (`data/models/users.py`, `daytrade.py`, `recommendations.py`, `core/logging.py`, `data/database.py`, `api/routes/health.py`, `tests/test_health.py`) — import-sorting e `Optional[X]`/`List[X]` → `X | None`/`list[X]`. Deliberadamente fora de escopo até uma task dedicada de cleanup. (`data/models/fundamentals.py` saiu da lista: foi reescrito e está limpo.)
7. **Colunas monetárias ainda em `Float`** (dívida conhecida, conversão adiada para a wave que as usar): `intraday_prices` OHLC (W15), `portfolio_snapshots.total_value/cash_value` (W11), `investor_profiles.monthly_contribution` (W09).
8. **`PriceSyncRequest` documenta que `end` não pode ser futura, mas o validador não verifica isso** — apenas `start <= end`.
9. **5 dos 10 indicadores permanecem `None`**, cada um por motivo **evidenciado** contra a API real: `pe`/`pb`/`dy` — a Brapi só expõe `sharesOutstanding` e `dividendYield` como snapshots atuais, sem data-fim de período; aplicá-los a um balanço de 2010 seria look-ahead (§108/§109). `debt_ebitda`/`ebitda_margin` — `cleanEbitda` é cópia literal de `ebit` em 16/16 períodos, não é EBITDA. **Limita os sub-scores de Valuation na Wave 09.**
10. ~~Indicadores gravados antes da W06-003 estão errados~~ — **PENDÊNCIA ANULADA em 2026-08-18.** Nunca existiu banco: sem container, sem volume Docker, sem arquivo SQLite. Ao subir o Postgres o volume foi criado do zero e todas as tabelas vieram com **0 linhas** (`assets`, `asset_prices`, `fundamentals`, `financial_indicators`, `users`, `transactions`). Não há nada gravado para recomputar. A pendência havia sido registrada por hipótese, não por observação do estado real.
11. **Reexpressões (restatements) de demonstrativos são invisíveis**: o primeiro valor gravado para um `reference_date` nunca é substituído. Corrigir exige schema versionado por período. (Indicadores derivados, ao contrário, podem ser recomputados — [ADR-015](../decisions/ADR-015-indicator-recomputation.md).)
12. **Demonstrativos trimestrais não são ingeridos** — o parser filtra `type == "yearly"`, porque `fundamentals` não tem coluna de período para distingui-los de um exercício anual com a mesma data-fim ([ADR-013](../decisions/ADR-013-fundamentals-point-in-time.md)).
13. **Throttle de requisições desligado por padrão.** `MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS` e `FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS` têm default `0.0` — nenhum espaçamento entre chamadas. A Brapi tem **cota mensal limitada** no plano gratuito. Definir um intervalo no `.env` antes de qualquer ingestão em lote.
14. 🔴 **Módulos de demonstrativos saíram do plano gratuito da Brapi** (verificado 2026-08-18, HTTP 403: *"Módulos disponíveis hoje: summaryProfile"*). Em 2026-08-17 a mesma chamada trouxe 16 períodos. **A ingestão de fundamentals está inoperante — por plano, não por código**; o parser segue correto e testado. Não afeta a W07 (que só usa `asset_prices`); **bloqueia a W09**. Decidir entre assinar o plano Startup, migrar para dados abertos da CVM, ou adiar a W09.
15. **Plano gratuito aceita no máximo 1 ativo por requisição.** Não há batching — ingestão em lote custa 1 requisição por ticker. Dimensionar a cota mensal por aí.
16. ~~`adjusted_close` pode ser congelado errado~~ — **CORRIGIDO em 2026-08-18** ([ADR-016](../decisions/ADR-016-unadjusted-bars-are-not-stored.md)). O parser não fabrica mais o ajuste a partir do `close`; `adjusted_close` é `Decimal | None` refletindo o que a fonte reportou, e `validate_daily_bars` rejeita a barra sem ajuste (`MISSING_ADJUSTED_CLOSE`). Autocorretivo: a data não é gravada, então o sync seguinte a insere quando a fonte publicar. Corrigido **antes** de qualquer ingestão — o banco estava vazio, então não há linha contaminada. Efeito colateral esperado: a sessão fechada mais recente pode faltar por ~1 dia, e `rejected: 1` no sync diário é rotina.
17. **`alembic check` falha por drift**: unique constraint + unique index duplicados em `assets.ticker` e `users.email` (a migration `001` declara a constraint, o model declara `unique=True, index=True`). Redundante, não incorreto — mas impede usar `alembic check` como guarda de drift no CI.
18. **`env_file=".env"` é relativo ao cwd.** Rodando de `backend/`, o `.env` da raiz não é lido e `BRAPI_TOKEN` fica vazio **silenciosamente**. Sob `docker compose` não afeta.

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
