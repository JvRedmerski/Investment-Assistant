# Session Handoff

## Last Updated

2026-08-17

## Last Completed Work

**W06-003 — Validação contra a API real, correção do mapeamento e captação de insumos. Wave 06 concluída.**

Havia acesso de rede nesta sessão (não havia nas anteriores). Uma **única requisição** à Brapi validou tudo de uma vez, e o resultado justificou o gasto:

- **Market data (W05-001): parser correto.** Lacuna aberta desde a Wave 05, fechada sem correções.
- **Fundamentals (W06-001): dois bugs silenciosos.** `equity` lia `totalStockholderEquity` e `debt` lia `totalDebt` — **ambos null em 16/16 períodos reais**. Como `roe` depende de `equity`, ele era `None` em dados reais. Corrigido para `shareholdersEquity` e para a soma das seis linhas de dívida efetivamente reportadas.
- **`cleanEbitda` é cópia literal de `ebit`** nos 16 períodos — não é EBITDA. `ebitda` segue `NULL`, agora por evidência. Corrige a justificativa do ADR-013.
- **ROIC destravado** com alíquota efetiva derivada por período. O campo `cleanNopat` da Brapi foi descartado: aplica 34% fixos, enquanto as reais vão de 26,6% a 32,4%.
- **Bug pego só ao rodar contra dados reais**: PETR4 2020 teve crédito tributário (imposto positivo) contra lucro pré-imposto de R$ 37 mi; o `abs()` original gerava alíquota de 16.780% e **ROIC de −1096%**. Corrigido o sinal e adicionada guarda para alíquota fora de [0, 1].
- Migration `004` (`ebit`, `income_before_tax`, `income_tax_expense`), filtro `type == "yearly"`, e política de recomputação ([ADR-015](../decisions/ADR-015-indicator-recomputation.md)).

Commits anteriores da sessão: memória (`f5dc954`), W06-001 (`a60fae9`), W06-002 (`552efe8`).

## Current State

- `pytest` → **205 passed**. `ruff` e `black` limpos. `alembic heads` → `004`.
- **Wave 06 🟢 concluída.** 7 de 33 waves.
- Indicadores que produzem valor: `roe`, `roic`, `net_margin`, `revenue_growth`, `profit_growth`.
- Verificação de ponta a ponta sobre a resposta real: 16 períodos, 0 rejeitados, ROE 26,5% / ROIC 10,7% / margem 22,2% em 2025.

## Important Details

- **Um mock construído sobre uma suposição não verifica a suposição.** Foi assim que dois campos errados passaram por 45 testes verdes. Para intraday (W15) e IA (W12): **validar contra uma resposta real antes** de escrever a bateria de mocks. Existe agora `test_regression_against_the_real_petr4_response` como padrão a copiar.
- **Cota da Brapi**: toda a validação custou **1 requisição** — `range`, `interval` e três módulos cabem no mesmo `GET /quote`. Os throttles (`MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS`, `FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS`) continuam `0.0` por padrão; definir no `.env` antes de ingestão em lote.
- **Só a PETR4 foi validada.** Bancos, FIIs, ETFs e BDRs têm linhas de balanço diferentes — validar um de cada tipo antes de ingerir em lote.
- **Pendência operacional**: indicadores gravados antes da W06-003 estão errados. Rodar `POST /assets/{ticker}/indicators/compute?recompute=true` por ativo já processado.
- `pe`/`pb`/`dy` continuam `None` por decisão: os insumos existem só como snapshots atuais, e aplicá-los a períodos históricos seria look-ahead.
- Executar Python pelo virtualenv: `backend\.venv\Scripts\python.exe -m pytest -q`.
- Patch de `time.sleep`/`time.monotonic` em teste: `app.integrations.http.time` (ADR-012).
- Migrations `002`, `003` e `004` seguem sem aplicação contra PostgreSQL real.

## Pending Work

**Wave 07 — Quant Engine** (`app/quant/returns.py` e `risk.py`). Sem bloqueio; zero requisições externas. Ver [CURRENT_TASK.md](CURRENT_TASK.md).

Pendências de fundo: `alembic upgrade head` contra Postgres real; validar o parser com tickers de outros tipos; recomputar indicadores antigos.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md), `docs/roadmap.md` §19 e `AGENTS.md` §24–§27, e usar `app/domain/fundamentals/indicators.py` como molde de cálculo puro.

Duas decisões esperam na W07: a **convenção de anualização** (252 pregões vs. 365 dias) e a **fronteira `Decimal` → `float`** ao entrar em numpy/pandas — a regra 17 permite float para estatística desde que registrado, então provavelmente cabe um ADR.

## Relevant Files

- `backend/app/domain/fundamentals/indicators.py` — molde de cálculo puro com política de dado faltante
- `backend/app/data/models/assets.py` — `AssetPrice`; usar `adjusted_close` para retornos, não `close`
- `backend/tests/test_fundamental_indicators.py` — molde de teste com valores conhecidos
- `backend/tests/test_brapi_fundamentals_provider.py` — molde do teste de regressão com resposta real
- `docs/roadmap.md` §19 — especificação da Wave 7
