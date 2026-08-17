# Session Handoff

## Last Updated

2026-08-17

## Last Completed Work

**W06-001 — Ingestão de Demonstrativos Financeiros.** Primeira task da Wave 06.

Entregue: `FundamentalsProvider` (ABC) + `BrapiFundamentalsProvider` + factory + DTOs + exceções; `validate_financial_statements` (função pura); `sync_annual_statements` idempotente; endpoints `POST /assets/{ticker}/fundamentals/sync` e `GET /assets/{ticker}/fundamentals`; migration `003` convertendo as colunas monetárias de `fundamentals` para `NUMERIC(24,4)`.

Junto veio uma extração estrutural: o laço de timeout/retry/backoff/throttle saiu de `BrapiProvider` para `app/integrations/http.py` (`RetryingJsonClient`), agora compartilhado pelas duas integrações ([ADR-012](../decisions/ADR-012-shared-http-transport.md)). Mudança mecânica, sem alteração de comportamento.

Antes disso, na mesma sessão: criação de toda a estrutura de memória (commit `f5dc954`).

## Current State

- `pytest` → **140 passed** (95 anteriores + 45 novos). Nenhuma regressão.
- `ruff check` e `black --check` limpos em todos os arquivos da task.
- `alembic heads` → `003_numeric_fundamentals_columns`.
- Wave 06 aberta: W06-001 ✅, W06-002 pendente.

## Important Details

- Executar Python **sempre** pelo virtualenv: `backend\.venv\Scripts\python.exe -m pytest -q`.
- **Patch de `time.sleep`/`time.monotonic` em teste agora é em `app.integrations.http.time`**, não no módulo do provedor — o laço de retry mudou de lugar (ADR-012).
- Ao adicionar um provedor externo novo (intraday W15, IA W12), use `RetryingJsonClient`: só escreva URL e parsing.
- Os `__init__.py` novos dos pacotes de fundamentals são **vazios de fato** (0 bytes), não `""` como os antigos — o conteúdo `""` dispara `D419` no ruff e reformatação no black, e a DoD exige lint limpo. Divergência consciente do padrão antigo; os antigos seguem como estão.
- `ebitda` e `free_cash_flow` sempre `NULL` é **decisão**, não bug — leia [ADR-013](../decisions/ADR-013-fundamentals-point-in-time.md) antes de tocar em fundamentos.
- Nada foi jamais executado contra PostgreSQL real; as migrations `002` e `003` continuam não verificadas lá.
- Nenhum teste faz I/O de rede.

## Pending Work

1. Iniciar **W06-002** (ver [CURRENT_TASK.md](CURRENT_TASK.md)) — fecha a Wave 06.
2. Pendências que atravessam waves, não bloqueantes: aplicar `alembic upgrade head` contra Postgres real; validar os **dois** parsers da Brapi contra respostas reais.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md) e [ADR-013](../decisions/ADR-013-fundamentals-point-in-time.md), depois `app/domain/portfolio/service.py` como molde de cálculo puro, e planejar W06-002.

## Relevant Files

- `backend/app/domain/fundamentals/service.py` — onde a persistência de indicadores se encaixa
- `backend/app/data/models/fundamentals.py` — `Fundamental` (insumo) e `FinancialIndicator` (destino)
- `backend/app/data/models/assets.py` — `AssetPrice`, para P/L, P/VP e DY
- `backend/app/domain/portfolio/service.py` — molde de função pura determinística em `Decimal`
- `backend/app/api/routes/assets.py` — onde entra o endpoint de leitura
- `backend/tests/test_portfolio_service.py` — molde de teste com valores conhecidos
