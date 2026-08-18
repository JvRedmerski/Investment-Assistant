# Roadmap — Waves

> Camada 4. Índice consolidado das 33 waves com status real (2026-08-17).
> A **especificação funcional completa** (fórmulas, setups, schema, critérios detalhados) está em [../roadmap.md](../roadmap.md) — vá lá só quando for implementar a wave, na seção indicada.

Legenda: 🟢 concluída · 🟡 em progresso · ⚪ não iniciada

## Estado geral

**7 / 33 concluídas.** Fronteira atual: **Wave 07 — Quant Engine**.

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
| **W07** | **Quant Engine** — `returns.py`, `risk.py` (CAGR, vol, beta, drawdown, Sharpe, Sortino) | ⚪ **atual** | W05 | §19 |
| W08 | Benchmark Engine — séries de CDI/IBOV/IPCA e comparativo | ⚪ | W07 | §20 |
| W09 | Recommendation Engine — sub-scores e alocação do aporte mensal | ⚪ | W06 (**incl. W06-003**), W07 | §21 |
| W10 | Rebalanceamento — target weights, weight gaps, restrições conservadoras | ⚪ | W09 | §22 |
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

Não bloqueiam a W06, mas precisam ser resolvidas antes de produção:

- Aplicar `alembic upgrade head` contra PostgreSQL real (`002`, `003` e `004` nunca rodaram lá).
- Validar o parser da Brapi com tickers de outros tipos (FII, ETF, BDR, banco) — só a PETR4 foi verificada; bancos e seguradoras têm linhas de balanço próprias.
- Recomputar indicadores gravados antes da W06-003 (`?recompute=true`).
- Suportar demonstrativos trimestrais e reexpressões: exige coluna de período / versionamento em `fundamentals` ([ADR-013](../decisions/ADR-013-fundamentals-point-in-time.md)).
- Task dedicada de lint cleanup no backend (findings pré-existentes da W02).
- Consertar `npm run lint` no frontend (falta `eslint`).
- Expor `get_quote()` e implementar ingestão de proventos — entregáveis da W05 (roadmap §17) que ficaram de fora.
- Converter para `NUMERIC` as colunas monetárias ainda em `Float` (ver [ADR-003](../decisions/ADR-003-decimal-money.md)).
