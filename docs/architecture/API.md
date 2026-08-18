# API

> Camada 2. Leia quando a task tocar endpoints ou contratos HTTP.
> Estado em 2026-08-17.

## Organização

- Prefixo de versão: `settings.API_V1_STR` = `/api/v1`. Routers registrados em `app/main.py`.
- Um arquivo por recurso em `app/api/routes/`, cada um com `APIRouter(prefix=..., tags=[...])`.
- OpenAPI em `/docs` (Swagger) e `/redoc`; schema em `/api/v1/openapi.json`.
- Health é registrado **duas vezes**: sem prefixo (para healthcheck/infra) e sob `/api/v1` (o frontend consome este).

## Convenções

- REST por recurso; sub-recursos aninhados (`/portfolios/{id}/transactions`).
- Request e response sempre com modelo Pydantic explícito (`response_model=`), definidos em `app/domain/<área>/schemas.py`. Responses que espelham models usam `ConfigDict(from_attributes=True)`.
- Criação retorna **201**; `DELETE` retorna **204** sem corpo.
- Todo endpoint de negócio exige `Depends(get_current_user)`. Apenas `/`, `/health`, `/ready` e os de auth são públicos.
- Recurso de outro usuário retorna **404**, nunca 403 ([ADR-010](../decisions/ADR-010-404-over-403.md)).
- Ticker é normalizado para maiúsculas (no schema, em `AssetCreate`, e novamente na busca por path param).
- Datas "hoje" são calculadas em UTC explícito.

## Autenticação

`Authorization: Bearer <access_token>` (JWT HS256, `sub` = user id).
Falha de validação → **401** `INVALID_CREDENTIALS` com header `WWW-Authenticate: Bearer`.

## Formato de erro

Handler global em `main.py` normaliza **todo** `HTTPException` para:

```json
{ "error": { "code": "ASSET_NOT_FOUND", "message": "Asset PETR4 was not found." } }
```

Ao lançar de dentro de uma rota, passe o envelope já pronto em `detail` para controlar o `code`:

```python
raise HTTPException(status_code=404, detail={"error": {"code": "...", "message": "..."}})
```

Sem `detail` estruturado, o handler emite `code: "HTTP_ERROR"`. Erros de validação do Pydantic (422) seguem o formato padrão do FastAPI — **não** passam pelo handler.

Códigos em uso: `INVALID_CREDENTIALS`, `ASSET_NOT_FOUND`, `ASSET_ALREADY_EXISTS`, `PORTFOLIO_NOT_FOUND`, `INSUFFICIENT_POSITION`, `MARKET_DATA_TICKER_NOT_FOUND`, `MARKET_DATA_UNAVAILABLE`, `MARKET_DATA_INVALID_RESPONSE`, `FUNDAMENTALS_NOT_FOUND`, `FUNDAMENTALS_UNAVAILABLE`, `FUNDAMENTALS_INVALID_RESPONSE`.

## Endpoints implementados

### Health (público)
| Método | Rota | Nota |
|---|---|---|
| GET | `/` | banner |
| GET | `/health` e `/api/v1/health` | `status`, `app_name`, `environment`, `version` |
| GET | `/ready` e `/api/v1/ready` | ⚠️ retorna `"database": "connected"` **fixo** — não verifica o banco de verdade |

### Auth — `/api/v1/auth`
| Método | Rota | Auth | Nota |
|---|---|---|---|
| POST | `/register` | — | 201; e-mail duplicado → 409 |
| POST | `/login` | — | retorna `Token` |
| POST | `/refresh` | ✅ | reemite a partir de access token válido ([ADR-008](../decisions/ADR-008-refresh-without-refresh-token.md)) |
| GET | `/me` | ✅ | usuário autenticado |

### Assets — `/api/v1/assets` (todos autenticados)
| Método | Rota | Nota |
|---|---|---|
| POST | `""` | cadastro watch-only; ticker duplicado → 409 |
| GET | `""` | lista global, ordenada por ticker (assets não são escopados por usuário) |
| GET | `/{ticker}` | 404 se não cadastrado |
| POST | `/{ticker}/prices/sync` | chama a API externa; body `{start?, end?}`, default últimos 30 dias até hoje (UTC); resposta traz `fetched/inserted/skipped_existing/rejected` |
| GET | `/{ticker}/prices` | lê **só** do banco; query `start`/`end` opcionais |
| POST | `/{ticker}/fundamentals/sync` | chama a API externa; sem body; ingere demonstrativos **anuais**; mesma resposta de contagens |
| GET | `/{ticker}/fundamentals` | lê **só** do banco; query `start`/`end` filtram `reference_date`; itens de linha não reportados vêm `null` |
| POST | `/{ticker}/indicators/compute` | **não** chama API externa — só transforma dado armazenado; devolve `periods/computed/skipped_existing/recomputed`. `?recompute=true` descarta e reconstrói os indicadores do ativo ([ADR-015](../decisions/ADR-015-indicator-recomputation.md)) |
| GET | `/{ticker}/indicators` | lê **só** do banco; `start`/`end` filtram `reference_date`; `null` = não computável, nunca zero |

Os dois endpoints `*/sync` são as únicas rotas que chamam provedores externos. `indicators/compute` escreve no banco mas não faz I/O de rede.

Unidades dos indicadores: margens, crescimento, ROE, ROIC e DY são **frações** (0.15 = 15%); `pe`, `pb` e `debt_ebitda` são múltiplos adimensionais.

### Portfolios — `/api/v1/portfolios` (todos autenticados, escopados ao dono)
| Método | Rota | Nota |
|---|---|---|
| POST · GET · GET `/{id}` · PATCH `/{id}` · DELETE `/{id}` | | CRUD; PATCH só altera `name` |
| POST | `/{id}/transactions` | `asset_id` obrigatório para BUY/SELL/DIVIDEND, proibido para DEPOSIT/WITHDRAWAL; SELL acima da posição → 422 `INSUFFICIENT_POSITION` |
| GET | `/{id}/transactions` | ordenado por `transaction_date`, `id` |
| GET | `/{id}/positions` | posições consolidadas + totais; **sem valor de mercado** (depende de precificação, ainda não integrada) |

### Convenção de transação
Valor monetário = `quantity × price`; `fees` é separado e não entra nesse produto.
DEPOSIT/WITHDRAWAL: registrar `quantity = valor`, `price = 1`, sem `asset_id`.

## Contratos de resposta principais

- `PortfolioPositionsResponse`: `positions[]` (`asset_id`, `ticker`, `quantity`, `average_price`, `invested_amount`, `realized_pnl`, `dividends_received`) + `total_invested`, `total_realized_pnl`, `total_dividends_received`, `net_contributions`. Todos `Decimal`, serializados como string no JSON.
- `PriceSyncResponse`: `ticker`, `start`, `end`, `fetched`, `inserted`, `skipped_existing`, `rejected`.
- `AssetPriceResponse`: barra diária OHLCV armazenada (`Decimal`) + `source`.

## Ao adicionar endpoints

1. Schema em `app/domain/<área>/schemas.py`; **nunca** exponha um model SQLAlchemy diretamente.
2. Lógica em `service.py`; a rota só orquestra e traduz erro.
3. `Depends(get_current_user)` salvo justificativa explícita.
4. Erro com envelope `{"error":{"code","message"}}` e `code` novo em SCREAMING_SNAKE.
5. Mudança breaking deve atualizar frontend, testes e esta página (AGENTS.md §71).
6. Teste de integração via `TestClient` cobrindo: sem auth, caminho feliz, recurso inexistente, recurso de outro usuário.
