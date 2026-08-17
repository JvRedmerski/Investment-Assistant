# Session Handoff

## Last Updated

2026-08-17

## Last Completed Work

**Sessão de 2026-08-17 (esta):** construção da memória persistente do projeto. Nenhum código de aplicação foi alterado.
Criados `CLAUDE.md` (raiz) e a árvore `docs/memory/`, `docs/architecture/`, `docs/decisions/`, `docs/planning/`, `docs/history/`.

**Última sessão de implementação:** W05-003 (Data Quality Validator) — commit `97eb29b`, fechando a **Wave 05 — Market Data Integration**.

## Current State

- Árvore de trabalho limpa, `main` em `97eb29b` + os arquivos de memória desta sessão.
- `pytest` verificado nesta sessão: **95 passed**.
- Nenhuma task em andamento, nenhum bloqueio ativo.
- Backend cobre: auth, assets, portfolios, transações, posições, ingestão e leitura de preços diários.
- Frontend é uma landing page estática de status — nenhuma funcionalidade de produto está exposta na UI.

## Important Details

- Executar Python **sempre** pelo virtualenv: `backend\.venv\Scripts\python.exe -m pytest -q` (o `python` do PATH no Windows cai no stub da Microsoft Store).
- `ruff check` no repositório inteiro **não** fica limpo — há findings pré-existentes da Wave 02. Rode lint apenas nos arquivos que você alterou.
- Nada foi jamais executado contra PostgreSQL real; toda validação é SQLite in-memory. A migration `002_numeric_money_columns` continua não verificada em Postgres.
- Nenhum teste faz I/O de rede: o provider externo é sempre injetado via `app.dependency_overrides[get_market_data_provider]`.
- Divergências entre `AGENTS.md`/README e o código estão catalogadas em [PROJECT_STATUS.md](PROJECT_STATUS.md) → *Inconsistências*. Elas foram documentadas de propósito, **não** corrija sem pedir.

## Pending Work

1. Iniciar **W06-001** (ver [CURRENT_TASK.md](CURRENT_TASK.md)).
2. Pendências carregadas das waves anteriores, a resolver quando o ambiente permitir (não bloqueiam W06):
   - aplicar `alembic upgrade head` contra Postgres real;
   - validar o parser da Brapi contra uma resposta real da API.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md), depois `docs/roadmap.md` §18 e os arquivos do padrão Wave 05 listados lá, e planejar W06-001.

## Relevant Files

Provavelmente abertos na próxima sessão:

- `backend/app/integrations/market_data/{base,brapi,factory,schemas,data_quality}.py` — padrão a replicar
- `backend/app/domain/market_data/service.py` — padrão de ingestão idempotente
- `backend/app/api/routes/assets.py` — onde entram os endpoints de fundamentals
- `backend/app/api/dependencies.py` — onde entra a dependency do novo provider
- `backend/app/data/models/fundamentals.py` — model alvo
- `backend/app/core/config.py` — settings do novo provider
- `backend/tests/test_market_data_{service,routes}.py`, `test_brapi_provider.py` — padrão de teste a replicar
