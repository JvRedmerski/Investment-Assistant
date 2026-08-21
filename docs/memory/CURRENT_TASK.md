# Current Task

## Task

**Wave 10 — Rebalanceamento.** De volta à ordem do roadmap, depois de duas waves inseridas fora
dela (PRICE e EVENTS). Ver [../planning/ROADMAP.md](../planning/ROADMAP.md).

## Status

⚪ **Não começou.** A wave EVENTS fechou em 2026-08-20 com as três tasks entregues, e não há
código pela metade em lugar nenhum.

---

## O que a wave EVENTS entregou, e por que isso muda a Wave 10

| task | entrega | efeito medido |
|---|---|---|
| **EVENTS-001** | Distribuições por exercício, da DMPL da CVM | `dy` deixou de ser `None`: 0,22 em 2024 e 0,70 em 2022 (PETR4) |
| **EVENTS-002** | **Data e natureza** de todo evento, pelo contador de distribuição da B3 | PETR4 com 47 eventos em 6 anos; MGLU3 com 15 |
| **EVENTS-003** | **Magnitude**, do serviço aberto de eventos da B3, e o `adjusted_close` derivado dela | **PETR4 com 1.495 de 1.495 pregões ajustados**; volatilidade 41,8%, drawdown -63,4% |

**O score ficou completo.** O pilar de Risco tem insumo real pela primeira vez, e é exatamente o
score que o rebalanceamento consome — daí a Wave 10 vir agora e não antes.

Três ADRs saíram da wave: [ADR-024](../decisions/ADR-024-refill-fills-null-columns.md),
[ADR-025](../decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md) e
[ADR-026](../decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md).

---

## O que saber antes de mexer em preço ajustado

**`adjusted_close` só é derivado onde o ajuste é completo**, e a completude é julgada pelo
**contador da B3**, não pelo serviço de eventos — porque o serviço **omite**: a ITUB4 foi ex em
2025-03-18 com marcador `EB` e degrau de **-8,60%**, e ele não reporta nada ali. Toda sessão
contada precisa de ação dimensionada; a mais recente que não tiver é um piso.

A única exceção é o marcador **`ATZ`** (`CorporateEventKind.NOMINAL_UPDATE`), medido em 151
incrementos com degrau mediano de 1,0028. Sem ela a PETR4 teria **28** pregões ajustáveis em vez
de 1.495. Foi decisão do dono do projeto, com os números à vista — está registrada no ADR-026 §6.

**A junção com o serviço da B3 é o ISIN, nunca a classe adivinhada pelo ticker.** A B3 repete um
evento de contagem uma vez por ISIN que o emissor já teve; compor as três cópias do desdobramento
da BBAS3 dá 8,0 contra um degrau real de 2,02.

## O que já está pronto — não reimplemente

- `app/integrations/market_data/b3_corporate_actions.py` — `B3CorporateActionProvider`, o
  adaptador sobre o serviço aberto da B3. Fino de propósito: o endpoint não tem contrato
  publicado, e a interface é a costura.
- `app/integrations/market_data/base.py` — **quatro** ABCs agora: `DailyHistoryProvider`,
  `MarketDataProvider`, `CorporateEventProvider` (com `get_security_identity`) e
  `CorporateActionProvider`.
- `app/domain/market_data/adjustment.py` — a aritmética do ajuste retroativo **e** a regra de
  completude. Puro, sem I/O.
- `app/domain/market_data/corporate_actions.py` — ingestão, resolução da ex-date contra o
  calendário realmente gravado, e o preenchimento que só toca coluna nula.
- `app/domain/market_data/series.py` — ponto único da série de retorno; linha sem ajuste não entra.
- `app/domain/recommendations/{scoring,allocation,service}.py`, `app/quant/{returns,risk}.py`,
  `app/domain/benchmarks/`, `app/integrations/fundamentals/cvm.py`.

## Endpoints relevantes

- `POST /assets/{ticker}/prices/backfill` — histórico profundo pelo arquivo aberto da B3.
- `POST /assets/{ticker}/corporate-actions/sync` — **rode depois do backfill**: ingere as ações
  dimensionadas e reconstrói `adjusted_close` a partir do preço já gravado. A resposta traz
  `unaccounted` — as sessões contadas que ninguém dimensionou, que é por que a série começa onde
  começa.
- `GET /assets/{ticker}/corporate-actions` — lê só do banco.
- `POST /assets/{ticker}/fundamentals/sync?refill=true` — preenche coluna nula de período já
  gravado, e só ela.

---

## Estado do ambiente (verificado 2026-08-20)

- ✅ `pytest -q` → **750 passed** (era 701). `ruff check` e `black --check` limpos.
- ✅ Tudo commitado **e enviado** (`31ba72a`); árvore limpa, `main` em dia com `origin/main`.
- 🔴 **Docker desligado** ao encerrar a sessão de 2026-08-20 — `docker compose up -d postgres`
  antes de qualquer coisa que toque o banco. Com ele no ar, o schema é **`012`**
  (`001`…`012_corporate_actions`), com `alembic check` sem drift e downgrade testado.
- No banco real, **conferido em 2026-08-20** — quatro papéis com 1.495 pregões cada:

  | papel | `adjusted_close` | `corporate_actions` |
  |---|---|---|
  | PETR4 | 1.495 | 62 |
  | BBAS3 | 1.495 | 76 |
  | ITUB4 | 198 | 102 |
  | MGLU3 | 478 | 7 |

  As truncagens de ITUB4 e MGLU3 são **corretas** e explicadas por `unaccounted` — não são
  ingestão pela metade.
- **Cache do COTAHIST em `backend/var/b3/`** (gitignored), 2020–2025 baixados. Ano frio: ~90 s.
- Alembic do host precisa da URL sobrescrita:
  `DATABASE_URL="postgresql://investment_user:investment_pass_dev@localhost:5432/investment_assistant" .venv/Scripts/python.exe -m alembic upgrade head`
- 🔴 O teto de `3mo` da Brapi continua existindo. Não trava mais o histórico nem o
  `adjusted_close` de ação, mas ainda limita o **IBOV**, o que mantém `beta` com janela pobre.
