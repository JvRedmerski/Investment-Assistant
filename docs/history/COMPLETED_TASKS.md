# Completed Tasks

> Camada 4. Marcos entregues, por wave. Responde "o que já foi feito?".
> Notas de implementação task-a-task, validações e decisões datadas: [../PROJECT_STATUS.md](../PROJECT_STATUS.md).

## Wave 00 — Produto & Fundação 🟢

- Repositório Git e estrutura base
- `.gitignore`, `.env.example`, `.env`
- `docker-compose.yml` (postgres + backend + frontend)
- `README.md` e `AGENTS.md` (contrato técnico, 138 seções)
- `docs/PROJECT_STATUS.md` como sistema de tracking

## Wave 01 — Scaffold 🟢

- Backend FastAPI com `/health` e `/ready`
- Frontend React 18 + TypeScript + Vite + Tailwind
- Dockerfiles de backend e frontend; `docker compose config` validado
- pytest rodando

## Wave 02 — Database 🟢

- SQLAlchemy 2.0 + Alembic configurados
- 13 models: `users`, `investor_profiles`, `portfolios`, `assets`, `asset_prices`, `intraday_prices`, `fundamentals`, `financial_indicators`, `transactions`, `portfolio_snapshots`, `recommendations`, `daytrade_setups`, `daytrade_results`
- Migration `001_initial_schema`
- **Correção pós-wave** (2026-08-16): migration `002_numeric_money_columns` — `Float` → `NUMERIC(18,6)`/`Decimal` em `transactions` e `asset_prices` ([ADR-003](../decisions/ADR-003-decimal-money.md))

## Wave 03 — Autenticação 🟢

- Hash de senha com bcrypt e JWT com PyJWT ([ADR-006](../decisions/ADR-006-bcrypt-pyjwt.md))
- `POST /auth/register`, `/login`, `/refresh`, `GET /auth/me`
- `get_current_user` protegendo rotas
- Envelope de erro global `{"error":{"code","message"}}` ([ADR-007](../decisions/ADR-007-error-envelope.md))
- +18 testes

## Wave 04 — Carteira 🟢

- CRUD de assets (watch-only) e de portfolios, escopado por usuário com 404 ([ADR-010](../decisions/ADR-010-404-over-403.md))
- Ledger de transações (BUY/SELL/DIVIDEND/DEPOSIT/WITHDRAWAL) com guarda `INSUFFICIENT_POSITION`
- Motor de posições determinístico, custo médio móvel, derivado do ledger ([ADR-002](../decisions/ADR-002-positions-derived-from-ledger.md))
- `GET /portfolios/{id}/positions`
- +36 testes

## Wave 05 — Market Data 🟢

- `MarketDataProvider` abstrato + `BrapiProvider` + factory + DTOs + exceções tipadas ([ADR-004](../decisions/ADR-004-market-data-provider-abstraction.md))
- httpx com timeout, retry limitado com backoff só em falha transitória, throttle de rate limit
- `sync_daily_history` idempotente; read-path lê só do banco ([ADR-005](../decisions/ADR-005-market-data-caching.md))
- `validate_daily_bars`: rejeita preço não-positivo, volume negativo, OHLC inconsistente e data duplicada; avisa sobre fora de ordem e variação diária >50%
- +39 testes

**Entregues com ressalva**: parser da Brapi nunca validado contra a API real (sem rede no ambiente); `get_quote()` implementado mas não exposto; ingestão de proventos, listada no roadmap §17, não implementada.

## Wave 06 — Fundamental Data 🟢

**W06-001 — Ingestão de Demonstrativos Financeiros** 🟢
- `FundamentalsProvider` abstrato + `BrapiFundamentalsProvider` + factory + DTOs + exceções tipadas
- `sync_annual_statements` idempotente; leitura servida só do banco
- `validate_financial_statements`: rejeita data de referência duplicada, data futura, demonstrativo vazio e valor negativo em receita/dívida/caixa; avisa sobre demonstrativo incompleto
- Migration `003_numeric_fundamentals_columns` — `fundamentals` em `NUMERIC(24,4)` ([ADR-003](../decisions/ADR-003-decimal-money.md))
- Transporte HTTP compartilhado extraído para `app/integrations/http.py`, reaproveitado pelo market data ([ADR-012](../decisions/ADR-012-shared-http-transport.md))
- Política point-in-time definida: só anual, restatement não sobrescreve, nada de TTM ([ADR-013](../decisions/ADR-013-fundamentals-point-in-time.md))
- +45 testes (total 140)

**W06-002 — Indicadores Fundamentalistas** 🟢
- `compute_indicators`: função pura e determinística com as 10 fórmulas (pe, pb, roe, roic, dy, debt_ebitda, net_margin, ebitda_margin, revenue_growth, profit_growth)
- Seleção de preço sem look-ahead: fechamento na data de referência ou anterior mais próxima
- Persistência idempotente; período pulado ainda serve de base para o crescimento seguinte
- `POST /assets/{ticker}/indicators/compute` (sem chamada externa) e `GET /assets/{ticker}/indicators`
- Política de dado faltante: `None` = não computável, nunca zero ([ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md))
- +44 testes (total 184)

**W06-003 — Validação contra a API real e correção do mapeamento** 🟢 (criada nesta wave, não prevista no roadmap original)
- **Parsers validados contra uma resposta real da Brapi** (1 requisição), fechando lacuna aberta desde a Wave 05
- Market data: correto. Fundamentals: **dois bugs silenciosos** — `equity` e `debt` liam campos null em 16/16 períodos, deixando `roe` sempre `None` em dados reais
- `cleanEbitda` identificado como cópia de `ebit`: `ebitda` segue `NULL`, agora por evidência (corrige o ADR-013)
- ROIC destravado com alíquota efetiva derivada por período; `cleanNopat` da Brapi descartado por aplicar 34% fixos
- Guarda para alíquota absurda (PETR4 2020 produzia ROIC de −1096%)
- Migration `004` (`ebit`, `income_before_tax`, `income_tax_expense`); filtro `type == "yearly"`
- Política de recomputação de derivados ([ADR-015](../decisions/ADR-015-indicator-recomputation.md))
- +21 testes (total 205), incl. regressão com a resposta real

**Resultado da wave: 🟢 concluída.** Cinco indicadores produzem valor (`roe`, `roic`, `net_margin`, `revenue_growth`, `profit_growth`); os cinco restantes têm limitação **evidenciada** contra a API, não suposta.

## Wave 07 — Quant Engine ⚪

Próxima. Ver [../memory/CURRENT_TASK.md](../memory/CURRENT_TASK.md).

---

## Marcos de infraestrutura de conhecimento

- **2026-08-17** — Sistema de memória persistente criado: `CLAUDE.md` na raiz + `docs/{memory,architecture,decisions,planning,history}/`, com 11 ADRs extraídos do código e do histórico de decisões.
