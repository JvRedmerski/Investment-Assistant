# System Overview

> Camada 2 da memória. Leia quando precisar entender como as peças se encaixam.
> Estado em 2026-08-17 (fim da Wave 05).

## Componentes

| Componente | Onde | Estado |
|---|---|---|
| Frontend SPA | `frontend/` | Página estática única (status do backend). Sem rotas, sem estado, sem telas de produto. |
| Backend REST API | `backend/app/` | Auth, assets, portfolios, transações, posições, market data. |
| PostgreSQL 16 | `docker-compose.yml` (`postgres`) | Schema completo (13 tabelas) via Alembic. 6 tabelas ainda sem código que as use. |
| Provedor de market data | Brapi (`https://brapi.dev/api`) | Único serviço externo integrado. |
| Provedor de IA | Gemini / Ollama | **Não integrado.** Só existe a chave em `.env` e a dependência no `pyproject.toml`. |

## Comunicação Frontend ↔ Backend

- REST sobre `VITE_API_URL` (default `http://localhost:8000/api/v1`).
- Hoje o frontend faz exatamente **uma** chamada: `GET /api/v1/health` (`frontend/src/services/api.ts`).
- CORS liberado no backend para `localhost:5173`, `localhost:3000`, `127.0.0.1:5173` (`core/config.py: BACKEND_CORS_ORIGINS`).
- Autenticação prevista via header `Authorization: Bearer <jwt>` — **o frontend ainda não implementa login**.

## Fluxo de dados — preços de mercado

Este é o fluxo mais importante já implementado, e o modelo para todas as futuras integrações externas:

```
POST /api/v1/assets/{ticker}/prices/sync      ← única porta de saída para a API externa
    ↓
get_market_data_provider (dependency, por request)
    ↓
BrapiProvider.get_daily_history()   httpx · timeout · retry limitado · throttle
    ↓
list[DailyBar]  (DTO Pydantic — dado externo validado na fronteira)
    ↓
validate_daily_bars()  função pura → DataQualityReport(valid_bars, errors, warnings)
    ↓
sync_daily_history()   descarta datas já armazenadas · insere o resto · nunca sobrescreve
    ↓
tabela asset_prices (PostgreSQL)
    ↓
GET /api/v1/assets/{ticker}/prices   ← lê SÓ do banco, nunca chama o provedor
```

A separação entre write-path (sync, explícito, custoso) e read-path (banco, barato) é deliberada: abrir uma página nunca dispara chamada externa (AGENTS.md §23). Ver [ADR-005](../decisions/ADR-005-market-data-caching.md).

## Fluxo de dados — carteira

```
POST /portfolios/{id}/transactions   → append-only no ledger
                                       (única validação: SELL ≤ quantidade detida)
    ↓
tabela transactions
    ↓
GET /portfolios/{id}/positions
    ↓
compute_positions()   replay cronológico do ledger, custo médio móvel, Decimal
    ↓
posições consolidadas (calculadas na hora, nunca armazenadas)
```

Não existe tabela de posições e não deve existir. Ver [ADR-002](../decisions/ADR-002-positions-derived-from-ledger.md).

## Responsabilidades por camada

| Camada | Responsabilidade | Nunca faz |
|---|---|---|
| `api/routes/` | HTTP, autenticação, validação de ownership, tradução de exceção de domínio → status code | Regra de negócio, cálculo financeiro |
| `domain/<área>/schemas.py` | Contrato de request/response (Pydantic v2) | Acesso a banco |
| `domain/<área>/service.py` | Regra de negócio determinística | HTTP, conhecer o provedor concreto |
| `integrations/<área>/` | Falar com o mundo externo, atrás de interface abstrata | Conhecer models do banco |
| `data/models/` | Mapeamento SQLAlchemy 2.0 | Lógica |
| `core/` | Config, segurança, logging | Domínio |

Não há camada de repositório: as rotas usam `Session` diretamente. Ver [ADR-011](../decisions/ADR-011-no-repository-layer.md).

## Fronteira de confiança

- **Dado externo é não confiável** (AGENTS.md §19): tudo que vem de HTTP externo passa por DTO Pydantic **e** por validador de qualidade antes de tocar o banco.
- **Dado do usuário é escopado**: toda rota de carteira resolve o recurso por `(id, user_id)` e retorna 404 — nunca 403 — para recurso de outro usuário. Ver [ADR-010](../decisions/ADR-010-404-over-403.md).
- **Erro nunca vaza stack trace**: handler global em `main.py` normaliza tudo para `{"error":{"code","message"}}`. Ver [ADR-007](../decisions/ADR-007-error-envelope.md).

## Execução

```powershell
docker compose up --build     # postgres + backend + frontend
```
- Frontend: http://localhost:5173 · API docs: http://localhost:8000/docs · Postgres: `localhost:5432`
- Volumes montam o código-fonte (hot reload em dev). Não há Dockerfile de produção (Wave 25).
- Não há workers, scheduler nem reverse proxy — planejados para waves futuras.
- Não há CI (`.github/` não existe) — Wave 26.
