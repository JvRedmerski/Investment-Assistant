# Session Handoff

## Last Updated

2026-08-17

## Last Completed Work

**W06-002 — Cálculo e Normalização de Indicadores Fundamentalistas.**

`app/domain/fundamentals/indicators.py`: `compute_indicators`, função pura e determinística com as **10 fórmulas** implementadas e testadas. `compute_and_store_indicators` no service, idempotente por `(asset_id, reference_date)`. `_price_on_or_before` seleciona o fechamento na data de referência ou anterior mais próxima — nunca posterior. Endpoints `POST /assets/{ticker}/indicators/compute` (não toca provedor externo) e `GET /assets/{ticker}/indicators`.

Política de dado faltante registrada em [ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md).

Antes, na mesma sessão: memória do projeto (`f5dc954`) e W06-001 (`a60fae9`).

## Current State

- `pytest` → **184 passed** (140 + 44). Nenhuma regressão.
- `ruff check` / `black --check` limpos nos arquivos das tasks.
- Wave 06 ⚠️ **parcial**: as duas tasks planejadas estão feitas, mas **6 dos 10 indicadores são sempre `None`** por falta de insumo.
- `.obsidian/` adicionado ao `.gitignore`.

## Important Details

- **Só 4 indicadores produzem valor hoje**: `roe`, `net_margin`, `revenue_growth`, `profit_growth`. Os outros 6 retornam `None` — isso é **correto e testado**, não bug. Falta `shares_outstanding` (pe, pb), proventos (dy), EBIT + alíquota (roic), EBITDA (debt_ebitda, ebitda_margin).
- Cada fórmula bloqueada tem um teste provando que **passa a funcionar assim que o insumo chegar** — a W06-003 não precisa mexer no módulo de cálculo, só popular `IndicatorInputs`.
- **`None` nunca deve ser coalescido para zero** na Wave 09. Ler ADR-014 antes de escrever qualquer sub-score.
- Período já gravado em `financial_indicators` **não é recomputado**. Se a W06-003 adicionar insumos, recomputar exige decidir explicitamente uma política (apagar e refazer? versionar?), não contornar.
- **Cota da Brapi**: `MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS` e `FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS` são `0.0` por padrão — sem throttle. Definir no `.env` antes de ingestão em lote. W06-002 fez **zero** requisições.
- Executar Python pelo virtualenv: `backend\.venv\Scripts\python.exe -m pytest -q`.
- Patch de `time.sleep`/`time.monotonic` em teste: `app.integrations.http.time` (ADR-012).
- Nada foi jamais executado contra PostgreSQL real; migrations `002` e `003` continuam não verificadas lá.

## Pending Work

**Decisão do usuário** entre duas frentes — ver [CURRENT_TASK.md](CURRENT_TASK.md):

- **W06-003** — captar shares outstanding, EBIT e proventos. Custo zero em requisições (módulos extras no mesmo `GET /quote`), mas precisa de rede para confirmar o mapeamento de campos.
- **Wave 07 — Quant Engine** (`returns.py`, `risk.py`). Sem bloqueio; **recomendada**.

Pendências de fundo: aplicar `alembic upgrade head` contra Postgres real; validar os dois parsers da Brapi contra respostas reais.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md), escolher a frente, e — se for a Wave 07 — usar `app/domain/fundamentals/indicators.py` como molde de cálculo puro.

## Relevant Files

- `backend/app/domain/fundamentals/indicators.py` — molde mais recente de função pura com política de dado faltante
- `backend/app/domain/fundamentals/service.py` — `compute_and_store_indicators`, `_price_on_or_before`
- `backend/app/domain/portfolio/service.py` — molde de replay determinístico em `Decimal`
- `backend/app/data/models/assets.py` — `AssetPrice`, fonte das séries para a Wave 07
- `backend/tests/test_fundamental_indicators.py` — molde de teste com valores conhecidos
- `docs/roadmap.md` §19 — especificação da Wave 7
