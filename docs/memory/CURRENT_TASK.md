# Current Task

## Task

**EVENTS-003 — série de retorno total.** Terceira e última task da wave **EVENTS** (eventos
societários e proventos), inserida fora da ordem do roadmap entre a W09 e a W10.

## Status

🟡 Wave em andamento, **2 de 3 tasks entregues**. A EVENTS-003 ⚪ **não começou**, e há uma
decisão de fonte a tomar antes de escrever código.

---

## O que a wave já entregou

| task | entrega | efeito medido |
|---|---|---|
| **EVENTS-001** | Distribuições por exercício, da DMPL da CVM (`5.04.06` + `5.04.07`) | `dy` deixou de ser `None`: 0,22 em 2024 e **0,70 em 2022** (PETR4). Os 10 indicadores passaram a ter insumo |
| **EVENTS-002** | **Data e natureza** de todo evento societário, pelo contador de distribuição da B3 | PETR4 com 47 eventos em 6 anos; MGLU3 com 15, incluindo o 1:4 de 2020, o 1:10 de 2024 e a bonificação de 2025 |

Duas decisões novas ficaram registradas:
[ADR-024](../decisions/ADR-024-refill-fills-null-columns.md) (preenchimento de coluna nula em
período já gravado) e
[ADR-025](../decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md) (evento
lido do contador, com data e natureza e **sem magnitude**).

## O que falta, em uma palavra: **magnitude**

O arquivo da B3 registra **que** houve distribuição e **jamais quanto**. Sem o fator de
desdobramento/grupamento e sem o valor do provento por pagamento não existe série de retorno
total, e sem ela continuam `None`: `volatility`, `max_drawdown`, `beta`, `sharpe` — os quatro
insumos do pilar de **Risco**. A cobertura do score continua em **0,75**, e o backtesting da
**W13** continua sem o que consumir.

⚠️ **O remendo proibido não mudou.** `adjusted_close = close` põe o grupamento 1:10 da MGLU3
como **+896% num pregão** dentro dessas quatro métricas
([ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md)). Derivar o fator
do degrau de preço é a mesma heurística com outro nome — a §44 proíbe inventar número.

---

## A decisão a tomar antes de escrever código: de onde vem a magnitude

O que mudou desde o ADR-023 é que **a data do evento agora existe**. Vale reavaliar as
alternativas com esse dado a mais — uma delas foi rejeitada exatamente por não tê-lo.

1. **Fator de desdobramento/grupamento pela contagem de ações da CVM + a data da B3.**
   O ADR-023 rejeitou a contagem de ações **por granularidade**: ela é anual e "um desdobramento
   precisa da **data** do evento". Essa objeção caiu com a EVENTS-002. A razão entre a contagem
   de dois exercícios, ancorada na data do evento que a B3 carimba, é candidata a fator —
   **mas precisa ser verificada contra caso real conhecido** (MGLU3 1:10 em 2024-05-27, BBAS3
   1:2 em 2024-04-16) antes de virar código, e não fecha quando há mais de um evento de contagem
   no mesmo exercício ou emissão/recompra no meio.
2. **Provento por pagamento (data + valor).** É o que falta para a parte em dinheiro; o agregado
   anual da DMPL **não** serve, porque distribuir um total anual entre as ex-dates seria
   atribuir valores que ninguém reportou. Fonte a decidir.
3. **Fornecedor pago.** Resolve os dois de uma vez e custa cota/assinatura. É a mesma decisão de
   produto já enfrentada nos fundamentals — e lá a resposta foi o dado aberto
   ([ADR-020](../decisions/ADR-020-cvm-primary-fundamentals-source.md)).

Seja qual for a fonte: **um período/valor vem inteiro de uma fonte só**, nunca campo a campo
(ADR-020), e ausência é gravada como ausência (ADR-014/ADR-023).

Depois disso, a task tem uma segunda metade previsível: **persistir os eventos** (model,
migration, endpoint de sync — hoje `get_corporate_events` varre o arquivo em cache a cada
chamada) e derivar `adjusted_close` a partir do preço bruto que **já está no banco**, sem
rebaixar nada.

---

## O que já está pronto — não reimplemente

- `app/integrations/market_data/cotahist.py` — `B3CotahistProvider` (preço **e** eventos),
  `CotahistArchive` (download em streaming, destilação, cache por ano). Os dois leitores
  compartilham uma varredura (`_read_records`).
- `app/integrations/market_data/base.py` — três ABCs: `DailyHistoryProvider`,
  `MarketDataProvider` e `CorporateEventProvider`.
- `app/integrations/market_data/schemas.py` — `CorporateEvent` / `CorporateEventKind`, com a
  evidência de cada letra no docstring.
- `app/domain/market_data/series.py` — **ponto único** da série de retorno. É aqui que o
  `adjusted_close` derivado passa a entrar; linha sem ajuste não entra.
- `app/integrations/fundamentals/cvm.py` — leitura de DFP/DMPL/`composicao_capital`, com cache
  anual em `backend/var/cvm/`.
- `app/domain/fundamentals/service.py` — `sync_annual_statements(..., refill=True)`.
- `app/domain/recommendations/{scoring,allocation,service}.py`, `app/quant/{returns,risk}.py`,
  `app/domain/benchmarks/`.

## Endpoints relevantes

- `POST /assets/{ticker}/prices/backfill` — histórico profundo pelo arquivo aberto da B3.
- `POST /assets/{ticker}/prices/sync` — fornecedor; nenhum dos dois sobrescreve data gravada.
- `POST /assets/{ticker}/fundamentals/sync?refill=true` — preenche coluna nula de período já
  gravado, e só ela.
- **Não existe** endpoint de evento societário. É parte da EVENTS-003.

---

## Estado do ambiente (verificado 2026-08-20)

- ✅ `pytest -q` → **701 passed**. `ruff check .` e `black --check .` limpos no repositório
  inteiro.
- 🔴 **Docker desligado nesta sessão** — `docker compose up -d postgres` antes de qualquer coisa
  que toque o banco. Com ele no ar, o schema é **`011`** (`001`…`011_dividends_paid`).
- No banco (registrado pelas tasks, **não** reconsultado com o Docker desligado): 1.495 pregões
  da PETR4 em `asset_prices` (2020-01-02 a 2025-12-30, `source='b3_cotahist'`, `adjusted_close`
  **NULL** — que é o desenho), 6 exercícios da CVM com `pe`, `pb` e agora `dy`.
- **Cache do COTAHIST em `backend/var/b3/`** (gitignored), ~15 MB por ano destilado, 2020–2025
  baixados. Ano frio: ~90 s e ~79 MB.
- Alembic do host precisa da URL sobrescrita:
  `DATABASE_URL="postgresql://investment_user:investment_pass_dev@localhost:5432/investment_assistant" .venv/Scripts/python.exe -m alembic upgrade head`
- 🔴 O teto de `3mo` da Brapi continua existindo. Não trava mais o histórico de **ações** (vem
  da B3), mas ainda limita o **IBOV**, o que mantém `beta` com janela pobre.
