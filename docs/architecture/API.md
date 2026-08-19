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

Códigos em uso: `INVALID_CREDENTIALS`, `ASSET_NOT_FOUND`, `ASSET_ALREADY_EXISTS`, `PORTFOLIO_NOT_FOUND`, `INSUFFICIENT_POSITION`, `MARKET_DATA_TICKER_NOT_FOUND`, `MARKET_DATA_UNAVAILABLE`, `MARKET_DATA_INVALID_RESPONSE`, `MARKET_DATA_WINDOW_TOO_LARGE`, `FUNDAMENTALS_NOT_FOUND`, `FUNDAMENTALS_UNAVAILABLE`, `FUNDAMENTALS_INVALID_RESPONSE`.

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
| POST | `/{ticker}/prices/sync` | chama a API externa; body `{start?, end?}`, default últimos 30 dias até hoje (UTC); `end` não pode ser futura; resposta traz `fetched/inserted/skipped_existing/rejected`. Janela além do teto do plano → **400 `MARKET_DATA_WINDOW_TOO_LARGE`** ([ADR-022](../decisions/ADR-022-provider-plan-limits-are-refused-locally.md)) |
| GET | `/{ticker}/prices` | lê **só** do banco; query `start`/`end` opcionais |
| GET | `/{ticker}/quote` | cotação atual, **ao vivo** no provedor; nada é gravado (cotação é um momento, `asset_prices` guarda pregão fechado). Exige o ativo cadastrado, para que um typo não gaste requisição de cota mensal |
| POST | `/{ticker}/fundamentals/sync` | chama a API externa; sem body; ingere demonstrativos **anuais**; mesma resposta de contagens |
| GET | `/{ticker}/fundamentals` | lê **só** do banco; query `start`/`end` filtram `reference_date`; itens de linha não reportados vêm `null` |
| POST | `/{ticker}/indicators/compute` | **não** chama API externa — só transforma dado armazenado; devolve `periods/computed/skipped_existing/recomputed`. `?recompute=true` descarta e reconstrói os indicadores do ativo ([ADR-015](../decisions/ADR-015-indicator-recomputation.md)) |
| GET | `/{ticker}/indicators` | lê **só** do banco; `start`/`end` filtram `reference_date`; `null` = não computável, nunca zero |
| GET | `/{ticker}/benchmarks/{code}` | compara o histórico do ativo com um benchmark; lê **só** do banco; query `start`/`end` |

Os dois endpoints `*/sync` são as únicas rotas que chamam provedores externos. `indicators/compute` escreve no banco mas não faz I/O de rede.

Unidades dos indicadores: margens, crescimento, ROE, ROIC e DY são **frações** (0.15 = 15%); `pe`, `pb` e `debt_ebitda` são múltiplos adimensionais.

### Portfolios — `/api/v1/portfolios` (todos autenticados, escopados ao dono)
| Método | Rota | Nota |
|---|---|---|
| POST · GET · GET `/{id}` · PATCH `/{id}` · DELETE `/{id}` | | CRUD; PATCH só altera `name` |
| POST | `/{id}/transactions` | `asset_id` obrigatório para BUY/SELL/DIVIDEND, proibido para DEPOSIT/WITHDRAWAL; SELL acima da posição → 422 `INSUFFICIENT_POSITION` |
| GET | `/{id}/transactions` | ordenado por `transaction_date`, `id` |
| GET | `/{id}/positions` | posições consolidadas + totais; **sem valor de mercado** (depende de precificação, ainda não integrada) |
| GET | `/{id}/benchmarks/{code}` | compara a carteira com um benchmark; a carteira entra como índice **time-weighted**, então aporte não conta como rentabilidade; lê **só** do banco |
| GET | `/{id}/scores` | pontua todo ativo acompanhado **contra esta carteira**; lê **só** do banco. Ler `coverage` antes de comparar dois scores |
| GET | `/{id}/contribution-plan` | onde vai o próximo aporte, e por quê. `amount` default = `monthly_contribution` do perfil (senão R$ 1.000). Todo limite é sobrescrevível por query param (`max_asset_weight`, `max_sector_weight`, `max_share_per_position`, `max_positions`, `min_ticket`, `min_coverage`, `min_score`, `require_sector`) e a política volta na resposta. Nada é gravado |

### Benchmarks — `/api/v1/benchmarks` (todos autenticados)
| Método | Rota | Nota |
|---|---|---|
| GET | `""` | catálogo (CDI, SELIC, IPCA, IBOV); servido do código, não toca banco nem fonte externa |
| POST | `/{code}/sync` | única rota que chama a fonte externa; body `{start?, end?}`, default 1 ano; `rejected: 1` num sync diário é rotina — é o período em curso |
| GET | `/{code}/values` | lê **só** do banco; `value` é **fração** para benchmark `RATE` e **nível** para `INDEX` |

O `code` é casado sem diferenciar maiúsculas; desconhecido → 404 `BENCHMARK_NOT_FOUND`.

### Convenção de transação
Valor monetário = `quantity × price`; `fees` é separado e não entra nesse produto.
DEPOSIT/WITHDRAWAL: registrar `quantity = valor`, `price = 1`, sem `asset_id`.

## Contratos de resposta principais

- `PortfolioPositionsResponse`: `positions[]` (`asset_id`, `ticker`, `quantity`, `average_price`, `invested_amount`, `realized_pnl`, `dividends_received`) + `total_invested`, `total_realized_pnl`, `total_dividends_received`, `net_contributions`. Todos `Decimal`, serializados como string no JSON.
- `PriceSyncResponse`: `ticker`, `start`, `end`, `fetched`, `inserted`, `skipped_existing`, `rejected`.
- `AssetPriceResponse`: barra diária OHLCV armazenada (`Decimal`) + `source`.
- `BenchmarkComparisonResponse`: `subject` e `benchmark` (cada um com a **janela que de fato foi medida**, `observations`, `periodicity`, `total_return`, `annualised_return`, `volatility`, `max_drawdown`) + `excess_return`, `return_ratio`, `beta`, `sharpe`, `sortino`, `risk_free_rate`.
  `excess_return` é **diferença** em pontos de fração; `return_ratio` é **múltiplo** ("115% do CDI") e vem `null` a menos que ambos os retornos sejam positivos. `beta` é `null` contra benchmark de taxa, por desenho. `sharpe`/`sortino` são `null` enquanto não houver CDI ingerido para a janela — nunca calculados contra taxa zero.

- `ContributionPlanResponse`: `policy` (os limites usados), `contribution`, `allocated`, `unallocated`, `base_value`, `allocations[]` e `skipped[]`, mais `formula_version` e `rules_version`.
  `allocated + unallocated == contribution` sempre — dinheiro que os limites não deixam colocar volta como `unallocated`, nunca é forçado. Cada `allocation` traz `amount`, `rank`, `final_score`, `coverage`, `coverage_tier`, `headroom`, `limited_by` (`ASSET_WEIGHT` / `SECTOR_WEIGHT` / `POSITION_SHARE` / `CONTRIBUTION_REMAINING`), `weight_before`/`weight_after` e os `sub_scores` inteiros. Cada `skipped` traz `reason` (`NOT_SCORABLE`, `COVERAGE_BELOW_MINIMUM`, `SCORE_BELOW_MINIMUM`, `SECTOR_UNKNOWN`, `ASSET_LIMIT_REACHED`, `SECTOR_LIMIT_REACHED`, `BELOW_MINIMUM_TICKET`, `MAX_POSITIONS_REACHED`, `CONTRIBUTION_EXHAUSTED`) e um `detail` em texto.
  `coverage_tier` é a faixa de comparabilidade: scores são comparados **dentro** de uma faixa e nunca entre faixas ([ADR-021](../decisions/ADR-021-allocation-ranks-by-coverage-tier.md)).

## Ao adicionar endpoints

1. Schema em `app/domain/<área>/schemas.py`; **nunca** exponha um model SQLAlchemy diretamente.
2. Lógica em `service.py`; a rota só orquestra e traduz erro.
3. `Depends(get_current_user)` salvo justificativa explícita.
4. Erro com envelope `{"error":{"code","message"}}` e `code` novo em SCREAMING_SNAKE.
5. Mudança breaking deve atualizar frontend, testes e esta página (AGENTS.md §71).
6. Teste de integração via `TestClient` cobrindo: sem auth, caminho feliz, recurso inexistente, recurso de outro usuário.
