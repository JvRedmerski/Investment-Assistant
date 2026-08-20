# Roadmap — Waves

> Camada 4. Índice consolidado das 33 waves com status real (2026-08-20).
> A **especificação funcional completa** (fórmulas, setups, schema, critérios detalhados) está em [../roadmap.md](../roadmap.md) — vá lá só quando for implementar a wave, na seção indicada.

Legenda: 🟢 concluída · 🟡 em progresso · ⚪ não iniciada

## Estado geral

**10 / 33 concluídas** (W00–W09), **mais duas waves inseridas fora da ordem** — ver abaixo.
Fronteira atual: a **Wave 10 — Rebalanceamento**, de volta à ordem do roadmap depois de duas
waves inseridas fora dela. A **Wave 10 —
Rebalanceamento** é a próxima do roadmap, depois dela (ver [CURRENT_TASK.md](../memory/CURRENT_TASK.md)).

## Waves inseridas fora da ordem

Não estão entre as 33 do roadmap. Cada uma existe porque destravava mais coisa do que a wave
seguinte da fila, e ambas trocam **fornecedor com cota** por **arquivo público do mercado** — o
mesmo movimento que a W09-002 fez com os demonstrativos.

| Wave | Objetivo | Status | Entre |
|---|---|---|---|
| PRICE | Histórico de preços de fonte aberta (COTAHIST da B3): provider/parser/cache, ausência de ajuste como dado ([ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md)), endpoint de backfill | 🟢 3/3 | W09 e W10 |
| EVENTS | Eventos societários e proventos: distribuições por exercício da DMPL da CVM ([ADR-024](../decisions/ADR-024-refill-fills-null-columns.md)), data e natureza do evento pelo arquivo da B3 ([ADR-025](../decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md)), e a **magnitude** pelo serviço aberto de eventos da B3, com o `adjusted_close` derivado dela ([ADR-026](../decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md)) | 🟢 3/3 | idem |

**O que a EVENTS existe para destravar**: o pilar de **Risco** — e com ele `volatility`,
`max_drawdown`, `beta`, `sharpe`, a cobertura do score (0,75 → 1,00) e o backtesting da **W13**,
que precisa de retorno total e não de preço bruto. As duas primeiras tasks já fecharam o `dy`,
o último dos 10 indicadores sem insumo.

## MVP → V1

- **MVP** = Auth + Portfolio + Asset tracking + Market data + Returns + Risk + Benchmark + Recommendation básica + Dashboard → waves **00–11**.
- **V1** = MVP + Fundamentals + Recomendação avançada + Backtesting + AI + Day Trade + Paper Trading + CI/CD + Deploy → waves **00–32**.
- Day Trade **não** precede o MVP (AGENTS.md §97).

## Fundação — concluída

| Wave | Objetivo | Status | Spec |
|---|---|---|---|
| W00 | Produto, repositório, `.env`, docker-compose, docs | 🟢 | §12 |
| W01 | Scaffold backend FastAPI + frontend React/Vite + Dockerfiles + pytest | 🟢 | §13 |
| W02 | 13 models SQLAlchemy + migration inicial | 🟢 | §14 |
| W03 | Auth: bcrypt, JWT, register/login/refresh/me, rotas protegidas | 🟢 | §15 |
| W04 | Carteiras, ativos, ledger de transações, motor de posições | 🟢 | §16 |
| W05 | `MarketDataProvider` + Brapi, ingestão diária, caching, data quality | 🟢 | §17 |

## Núcleo quantitativo — próximo

| Wave | Objetivo | Status | Depende de | Spec |
|---|---|---|---|---|
| W06 | Fundamental Data — ingestão 🟢 · indicadores 🟢 · validação real 🟢 | 🟢 | W05 | §18 |
| W07 | Quant Engine — `returns.py`, `risk.py` (CAGR, vol, beta, drawdown, Sharpe, Sortino) | 🟢 | W05 | §19 |
| W08 | Benchmark Engine — séries de CDI/IBOV/IPCA e comparativo | 🟢 | W07 | §20 |
| W09 | Recommendation Engine — sub-scores e alocação do aporte mensal | 🟢 — 4 tasks: sub-scores, fonte CVM, ações em circulação, alocação | W06 (**incl. W06-003**), W07 | §21 |
| **W10** | **Rebalanceamento** — target weights, weight gaps, restrições conservadoras | ⚪ **próxima**, e agora consome um score completo | W09 | §22 |
| W11 | Dashboard — patrimônio, rentabilidade, benchmarks, tela de ativo | ⚪ | W07, W08 | §23 |

⚠️ **W11 é a primeira wave com trabalho de frontend real.** O frontend hoje é só scaffold.

## Explicabilidade e validação

| Wave | Objetivo | Status | Depende de | Spec |
|---|---|---|---|---|
| W12 | AI Engine — `AIProvider` (Gemini/Ollama), explicações em linguagem natural | ⚪ | W09 | §24 |
| W13 | Backtesting de carteira — simulação histórica de aportes + métricas | ⚪ | W07, W09 | §25 |
| W14 | Walk-forward — janelas móveis, validação out-of-sample | ⚪ | W13 | §26 |

## Day Trade — módulo separado

Não compartilha scores nem estratégias com o motor de longo prazo (AGENTS.md §45).

| Wave | Objetivo | Status | Depende de | Spec |
|---|---|---|---|---|
| W15 | Ingestão intraday (1m/5m/15m) | ⚪ | W05 | §27 |
| W16 | Indicadores (VWAP, EMA 9/21, RSI, ATR, RVOL) e setups (Breakout, Pullback, VWAP) | ⚪ | W15 | §28 |
| W17 | Risk Engine — sizing, stop, R/R, circuit breaker diário | ⚪ | W16 | §29 |
| W18 | Dashboard de Day Trade | ⚪ | W16, W17 | §30 |
| W19 | Backtesting de setups intraday | ⚪ | W16 | §31 |
| W20 | Paper Trading — execução simulada, nenhuma ordem real | ⚪ | W17, W19 | §32 |

## Produção

| Wave | Objetivo | Status | Spec |
|---|---|---|---|
| W21 | Suíte de testes unit/integration/e2e/regression | ⚪ | §33 |
| W22 | Frontend avançado — gráficos interativos, comparadores, filtros | ⚪ | §34 |
| W23 | Observabilidade — logging estruturado, healthchecks reais | ⚪ | §35 |
| W24 | Security hardening — CORS, rate limit, secrets, TTL de token | ⚪ | §36 |
| W25 | Docker de produção — multi-stage, non-root, nginx | ⚪ | §37 |
| W26 | CI/CD — GitHub Actions (lint → test → build) | ⚪ | §38 |
| W27 | Deploy | ⚪ | §39 |
| W28 | Migrations em produção com backup | ⚪ | §40 |
| W29 | Backup e disaster recovery | ⚪ | §41 |
| W30 | Paper trading estendido / validação de longo prazo | ⚪ | §42 |
| W31 | Auditoria de métricas quantitativas e segurança | ⚪ | §43 |
| W32 | Release V1.0 | ⚪ | — |

## Ordem obrigatória

```
Foundation → Database → Portfolio → Market Data → Quant → Benchmark
→ Recommendation → Backtesting → AI → Intraday → Day Trade
→ Paper Trading → Production
```

Não pule para IA ou Day Trade (AGENTS.md §96). Uma wave por vez (§133) — exceto dependência técnica mínima para desbloquear a wave atual.

## Pendências que atravessam waves

Não bloqueiam a wave em andamento, mas precisam ser resolvidas antes de produção (revisado em 2026-08-20):

- ✅ ~~Aplicar `alembic upgrade head` contra PostgreSQL real~~ — feito na W06-004 (2026-08-18); desde então toda migration nova é aplicada em Postgres 16 real, até a `011`.
- Validar o parser da CVM com tickers de outros tipos — bancos e seguradoras têm plano de contas próprio no DFP (`3.01` do BB é receita de intermediação financeira), e FII/ETF/BDR não arquivam DFP e nunca arquivarão. Validado até aqui contra PETR4 e VALE3.
- ✅ ~~Recomputar indicadores gravados antes da W06-003~~ — resolvido por `?recompute=true` ([ADR-015](../decisions/ADR-015-indicator-recomputation.md)).
- Suportar demonstrativos trimestrais e reexpressões: exige coluna de período / versionamento em `fundamentals` ([ADR-013](../decisions/ADR-013-fundamentals-point-in-time.md)). O `refill` da EVENTS-001 **não** resolve isso — ele só preenche coluna nula ([ADR-024](../decisions/ADR-024-refill-fills-null-columns.md)).
- ✅ ~~Task dedicada de lint cleanup no backend~~ e ~~consertar `npm run lint`~~ — ambas fechadas em FIX-001 (2026-08-19). `ruff`/`black` limpos no repositório inteiro, ESLint 10 rodando.
- ✅ ~~**Ingestão de proventos, entregável da W05 (roadmap §17)**~~ — **fechada em 2026-08-20** (EVENTS-003). O provento por pagamento, com data e valor, vem do serviço aberto de eventos da B3 e é persistido em `corporate_actions` ([ADR-026](../decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md)). Continua de fora a **subscrição**, que exige um modelo do valor do direito e não uma medição — por ora ela trunca a série ajustada.
- Converter para `NUMERIC` as colunas monetárias ainda em `Float` (ver [ADR-003](../decisions/ADR-003-decimal-money.md)) — sobraram `intraday_prices` OHLC (W15) e `portfolio_snapshots.total_value`/`cash_value` (W11), as duas **sem consumidor** hoje.
