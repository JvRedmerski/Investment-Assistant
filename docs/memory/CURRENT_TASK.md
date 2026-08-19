# Current Task

## Task

**Nenhuma em andamento.** A wave **PRICE — Histórico de preços de fonte aberta (B3 COTAHIST)**
fechou em 2026-08-19, com três tasks: o provider, o armazenamento da ausência de ajuste, e o
endpoint de backfill validado contra o banco real.

Era a opção 2 da decisão registrada aqui na sessão anterior — fora da ordem do roadmap, de
propósito, porque era o que travava mais coisa ao mesmo tempo. Duas das quatro travas caíram.

## Status

⚪ Aguardando escolha da próxima wave.

---

## O que a wave PRICE entregou, e o que ela deliberadamente não entregou

| trava de antes | estado agora |
|---|---|
| `pe` / `pb` no banco real | ✅ **resolvido** — 6 exercícios da PETR4 com P/L e P/VP reais |
| cobertura do score | ✅ **0,55 → 0,75**; o pilar de Valuation saiu de ausente para 93,5 |
| pilar de **Risk** | ❌ **continua ausente**, e por decisão ([ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md)) |
| `beta` com janela decente | ❌ mesma causa |
| **Wave 13** (backtesting) | ⚠️ tem preço bruto de anos; falta série de retorno total |

**Por que Risk continua ausente, e por que isso está certo:** o COTAHIST imprime o preço
**negociado**, e não publica série ajustada — não é atraso, é a natureza do arquivo. Métrica de
risco exige retorno total. Preencher `adjusted_close` com o `close` produziria, em dado real, o
grupamento 1:10 da MGLU3 como uma sessão de **+896%** dentro de `volatility`, `max_drawdown`,
`beta` e `sharpe`. A ausência é gravada como ausência, e o score já trata isso como estado normal.

---

## A decisão a tomar antes de começar

### Opção 1 — Eventos societários e proventos (**recomendada**)

É agora a peça que destrava mais coisa, e a wave PRICE deixou isso explícito em vez de
implícito. Uma única ingestão fecha quatro pendências:

| destrava | como |
|---|---|
| `dy` | é o **último** dos 10 indicadores ainda `None` (Known Issue nº 1 e nº 2) |
| pilar de **Risk** | permite construir a série ajustada sobre o preço bruto que já está no banco |
| cobertura do score | 0,75 → **1,00** |
| **Wave 13** inteira | backtesting precisa de retorno total, não de preço bruto |

O caminho conhecido para proventos é a **DMPL da CVM** (`5.04.06`/`5.04.07`) — mesma
infraestrutura de arquivo anual que a W09-002 e a W09-003 já usam. Para desdobramento e
grupamento falta decidir a fonte: o COTAHIST **marca** o evento (`ESPECI` vira `EG`, `EDJ`, `EB`;
`DISMES` incrementa) mas **não dá o fator** — marcador não é magnitude.

⚠️ Note que o preço bruto **já está gravado e não precisa ser rebaixado**: a série ajustada é
derivável dele mais os eventos.

### Opção 2 — Wave 10, Rebalanceamento (a ordem do roadmap)

`docs/roadmap.md` §22, AGENTS.md §34. `current_weight`, `target_weight`, `weight_gap`.
Boa parte da infraestrutura existe (`PortfolioExposure`, `allocation.py`, score relativo à
carteira); o que falta de verdade é a definição de **peso-alvo**, que não existe em lugar nenhum
— e é a pergunta da wave.

Agora é uma opção mais defensável do que era: os ativos passam a ter valor de mercado e
Valuation deixou de ser ausente. Mas o score que o rebalanceamento consome ainda tem o pilar de
Risco vazio.

---

## O que já está pronto — não reimplemente

- `app/integrations/market_data/cotahist.py` — `B3CotahistProvider` + `CotahistArchive`
  (download em streaming, destilação para mercado à vista, cache por ano).
- `app/integrations/market_data/base.py` — `DailyHistoryProvider` (histórico) separado de
  `MarketDataProvider` (histórico **+** cotação), com `reports_adjusted_close` e `source_name`.
- `app/domain/market_data/series.py` — **ponto único** que transforma linha em `PricePoint`.
  Toda série de retorno passa por aqui, e linha sem ajuste não entra.
- `app/domain/recommendations/{scoring,allocation,service}.py`, `app/quant/{returns,risk}.py`,
  `app/domain/benchmarks/`, `app/integrations/fundamentals/`.

## Endpoints da wave PRICE

- `POST /assets/{ticker}/prices/backfill` — histórico profundo pelo arquivo aberto da B3.
  Sem teto de janela. Convive com `POST /assets/{ticker}/prices/sync` (fornecedor): ambos
  escrevem em `asset_prices` e **nenhum sobrescreve data já gravada**.

---

## Estado do ambiente (verificado 2026-08-19)

- **PostgreSQL 16 no ar**, schema em **`010`**. `docker compose up -d postgres` se estiver parado.
- **`asset_prices` deixou de estar vazia**: **1.495 pregões da PETR4, 2020-01-02 a 2025-12-30**,
  todos com `source='b3_cotahist'` e `adjusted_close` **NULL** — que é o desenho, não uma falha.
- PETR4 com 6 exercícios da CVM, `shares_outstanding`, e agora **`pe`/`pb` preenchidos**.
- **Cache do COTAHIST em `backend/var/b3/`** (gitignored), ~15 MB por ano destilado, com
  2020–2025 já baixados. Um ano frio custa ~90 s e ~79 MB de download.
- Alembic do host precisa da URL sobrescrita:
  `DATABASE_URL="postgresql://investment_user:investment_pass_dev@localhost:5432/investment_assistant" .venv/Scripts/python.exe -m alembic upgrade head`
- ✅ `alembic check` passa (sem drift). `pytest` → **672 passed**. `ruff`/`black` limpos no
  repositório inteiro.
- 🔴 O teto de `3mo` da Brapi **continua existindo**, mas deixou de ser a restrição
  estruturante: o histórico profundo agora vem da B3, de graça. A Brapi segue necessária para
  **cotação ao vivo** e para o `adjusted_close` das sessões recentes.
