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

Códigos em uso: `INVALID_CREDENTIALS`, `ASSET_NOT_FOUND`, `ASSET_ALREADY_EXISTS`, `PORTFOLIO_NOT_FOUND`, `INSUFFICIENT_POSITION`, `MARKET_DATA_TICKER_NOT_FOUND`, `MARKET_DATA_UNAVAILABLE`, `MARKET_DATA_INVALID_RESPONSE`, `MARKET_DATA_WINDOW_TOO_LARGE`, `FUNDAMENTALS_NOT_FOUND`, `FUNDAMENTALS_UNAVAILABLE`, `FUNDAMENTALS_INVALID_RESPONSE`, `BENCHMARK_NOT_FOUND`, `AI_NOT_CONFIGURED`, `AI_UNAVAILABLE`, `AI_RESPONSE_BLOCKED`, `INVALID_AI_RESPONSE`.

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
| POST | `/{ticker}/prices/backfill` | histórico **profundo** pela série COTAHIST aberta da B3; body `{start?, end?}`, `start` default `B3_COTAHIST_FIRST_YEAR`. **Sem teto de janela** — a fonte é um arquivo por ano civil, sem cota. Bars vêm **sem `adjusted_close`** e a ausência é gravada ([ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md)). Convive com `/prices/sync`: ambos escrevem em `asset_prices` e **nenhum sobrescreve data já gravada**, então compõem em qualquer ordem. Pode levar minutos com cache frio |
| GET | `/{ticker}/prices` | lê **só** do banco; query `start`/`end` opcionais. `adjusted_close` pode ser `null` — ver `source` para saber qual fonte forneceu a linha |
| POST | `/{ticker}/corporate-actions/sync` | ingere as ações societárias **dimensionadas** e reconstrói `adjusted_close` a partir do preço bruto **já gravado** — nada de preço é rebuscado. Body `{start?, end?}`, que filtra pela **data-com** da B3, não pela ex-date que ela resolve. Resposta: `fetched/inserted/skipped_existing/unplaced`, mais `adjusted_written`, `first_adjustable`/`last_adjustable` e — o que importa — `unaccounted` e `unusable`. `unaccounted` lista as sessões que o **contador da própria B3** marcou ex e que nenhuma ação publicada dimensiona; a mais recente delas é exatamente por que `first_adjustable` está onde está, porque ajustar através de um evento desconhecido daria número errado em vez de série curta ([ADR-026](../decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md)). Linha que **já** tem `adjusted_close` nunca é reescrita (ADR-020/ADR-024). Rode `/prices/backfill` antes |
| GET | `/{ticker}/corporate-actions` | lê **só** do banco; `start`/`end` filtram `ex_date`. Exatamente um de `cash_amount` (reais por ação) e `share_ratio` (ações depois por ação antes) vem preenchido, e qual deles é implicado por `kind`; o outro é `null`, nunca zero ou um |
| GET | `/{ticker}/quote` | cotação atual, **ao vivo** no provedor; nada é gravado (cotação é um momento, `asset_prices` guarda pregão fechado). Exige o ativo cadastrado, para que um typo não gaste requisição de cota mensal |
| POST | `/{ticker}/fundamentals/sync` | chama a API externa; sem body; ingere demonstrativos **anuais**; mesma resposta de contagens, mais `refilled`. `?refill=true` preenche colunas que estão **`NULL`** em períodos já gravados, e só elas — valor já presente nunca é tocado, então reexpressão continua não entrando por aqui ([ADR-024](../decisions/ADR-024-refill-fills-null-columns.md)). É como um banco alcança uma coluna de demonstrativo que o código aprendeu a ler depois da ingestão |
| GET | `/{ticker}/fundamentals` | lê **só** do banco; query `start`/`end` filtram `reference_date`; itens de linha não reportados vêm `null` |
| POST | `/{ticker}/indicators/compute` | **não** chama API externa — só transforma dado armazenado; devolve `periods/computed/skipped_existing/recomputed`. `?recompute=true` descarta e reconstrói os indicadores do ativo ([ADR-015](../decisions/ADR-015-indicator-recomputation.md)) |
| GET | `/{ticker}/indicators` | lê **só** do banco; `start`/`end` filtram `reference_date`; `null` = não computável, nunca zero |
| GET | `/{ticker}/benchmarks/{code}` | compara o histórico do ativo com um benchmark; lê **só** do banco; query `start`/`end` |

Os dois endpoints `*/sync` são as únicas rotas que chamam provedores externos. `indicators/compute` escreve no banco mas não faz I/O de rede.

Unidades dos indicadores: margens, crescimento, ROE, ROIC e DY são **frações** (0.15 = 15%); `pe`, `pb` e `debt_ebitda` são múltiplos adimensionais.

**Os 10 indicadores têm insumo desde a EVENTS-001** — `dy` era o último sem fonte, e passou a vir da DMPL da CVM (`dividends_paid / shares_outstanding / price`, tudo do mesmo exercício). Um `null` na resposta continua significando *não computável para este período*, nunca zero ([ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md)).

### Portfolios — `/api/v1/portfolios` (todos autenticados, escopados ao dono)
| Método | Rota | Nota |
|---|---|---|
| POST · GET · GET `/{id}` · PATCH `/{id}` · DELETE `/{id}` | | CRUD; PATCH só altera `name` |
| POST | `/{id}/transactions` | `asset_id` obrigatório para BUY/SELL/DIVIDEND, proibido para DEPOSIT/WITHDRAWAL; SELL acima da posição → 422 `INSUFFICIENT_POSITION` |
| GET | `/{id}/transactions` | ordenado por `transaction_date`, `id` |
| GET | `/{id}/positions` | posições consolidadas, **a custo e a mercado**. `market_value` é `quantity × close` (nunca `adjusted_close`, que é preço de retorno total). ⚠️ Ler `unvalued_positions` antes de `valued_market_value`: ativo sem preço armazenado deixa a **linha** ausente, não o total, e o nome do campo diz o que ele cobre. `unrealised_pnl` compara `valued_market_value` com `valued_invested` — as mesmas linhas. `oldest_price_date`/`newest_price_date` delimitam os preços usados (regras 103/104). `as_of` trunca **o ledger e os preços** |
| GET | `/{id}/benchmarks/{code}` | compara a carteira com um benchmark; a carteira entra como índice **time-weighted**, então aporte não conta como rentabilidade. ⚠️ **Os dois lados são medidos na janela que compartilham** — `subject.start_date` e `benchmark.start_date` voltam iguais e podem ser mais estreitos que o pedido. Sem isso `excess_return` subtrai dois períodos diferentes: medido, +251,5 p.p. contra os +7,1 p.p. reais. Lê **só** do banco |
| GET | `/{id}/series` | as duas curvas de um gráfico de evolução. `wealth` é **patrimônio em BRL** (fechamento cru, aporte incluído) com `invested` ao lado; `index` é o nível **time-weighted**, que neutraliza aporte e é o único comparável a um benchmark ([ADR-019](../decisions/ADR-019-portfolio-return-is-time-weighted.md)). ⚠️ Rotular os dois diferente — curva de patrimônio lida como desempenho é o engano que o `invested` existe para impedir. Com `benchmark=`, ambos são recortados para a janela **compartilhada** e rebaseados em `base_date`. Traz `currency`, `sources`, `generated_at` (regra 74). Nada é gravado |
| GET | `/{id}/scores` | pontua todo ativo acompanhado **contra esta carteira**; lê **só** do banco. Ler `coverage` antes de comparar dois scores |
| GET | `/{id}/contribution-plan` | onde vai o próximo aporte, e por quê. `amount` default = `monthly_contribution` do perfil (senão R$ 1.000). Todo limite é sobrescrevível por query param (`max_asset_weight`, `max_sector_weight`, `max_share_per_position`, `max_positions`, `min_ticket`, `min_coverage`, `min_score`, `require_sector`) e a política volta na resposta. Nada é gravado |
| GET | `/{id}/rebalance` | `current_weight`, `target_weight` e `weight_gap` por ativo, mais underweight primeiro. ⚠️ O alvo sai do **mérito** (score sem o pilar de Diversificação) e não do `final_score` — um alvo feito do score recua conforme a carteira se aproxima ([ADR-027](../decisions/ADR-027-target-weight-comes-from-merit.md)). Ler `unassigned` junto com as linhas: é a fatia que os tetos não deram a ninguém. Alvo 0 em posição detida **não é ordem de venda**. Limites sobrescrevíveis: `max_asset_weight`, `max_sector_weight`, `min_coverage`, `min_score`, `rebalance_band`, `require_sector`. Nada é gravado |
| GET | `/{id}/rebalance-plan` | o aporte que fecha os gaps: maior gap primeiro, cada alocação para no alvo. ⚠️ **Nada aqui vende** — ativo acima do alvo volta em `skipped` com `ABOVE_TARGET`, e fecha por diluição ([ADR-028](../decisions/ADR-028-rebalancing-is-cash-flow-only.md)). O gap que o plano usa é medido na carteira **depois** do aporte, então ele pode comprar um papel que o `/rebalance` chama de no-alvo. Distinto do `/contribution-plan`: aquele ordena por score, este por gap. Nada é gravado |
| POST | `/{id}/explain/performance` | explicação em português do desempenho contra um benchmark (`?benchmark=CDI`). Os números são **os mesmos** de `/{id}/benchmarks/{code}` — mesma chamada, mesma janela — e chegam ao modelo já arredondados na string que a tela mostra. Nada é gravado |
| POST | `/{id}/explain/contribution-plan` | explicação do plano de aporte. Aceita **os mesmos** overrides de política de `/{id}/contribution-plan`: quem subiu um teto e pediu explicação tem que receber o plano que está vendo. O modelo recebe o valor **e** a regra nomeada que dimensionou cada linha, então nunca precisa inferir o motivo |
| POST | `/{id}/explain/scores/{ticker}` | explicação do score de um ativo nesta carteira. Ticker casado sem diferenciar maiúsculas; não pontuado → 404 `ASSET_NOT_FOUND` |

### Backtests — `/api/v1/backtests` (autenticado)
| Método | Rota | Nota |
|---|---|---|
| GET | `""` | replaya **uma das estratégias do próprio projeto** sobre o histórico. `strategy=contribution-plan` (ordena por score) ou `rebalance-plan` (ordena por distância até o alvo); `start` obrigatório, `end` default hoje; `amount` default = `monthly_contribution` do perfil (senão R$ 1.000); `day_of_month` é alvo, não data — cai na primeira sessão **em ou depois** dele. `tickers` restringe o universo, `benchmark` mede contra o catálogo. Custos (`brokerage`, `brokerage_rate`, `exchange_rate`) e toda a política de alocação são sobrescrevíveis e voltam em `settings`. Lê **só** do banco; nada é gravado |
| GET | `/walk-forward` | valida os **parâmetros** fora da amostra (regras 61/62). A janela replayável é cortada em `Train → Validate → Test` — os três do **mesmo** tamanho (`segment_months`, default 12) — e o corte anda `step_months` por vez. Cada candidato é medido no treino, a shortlist é remedida na validação, e **só o vencedor** roda no teste: nada medido no teste alcança uma seleção. Os candidatos são uma **grade declarada** (`candidates[]`, com a pergunta que cada um responde e `grid_version`), um parâmetro por vez a partir da política que você passou — nunca produto cartesiano (regra 60). `objective=sharpe` (default) ou `total-return`. Aceita os mesmos overrides de custo e política de `""`. Lê **só** do banco; nada é gravado |

⚠️ **Três leituras obrigatórias antes de qualquer número dessa resposta.**

1. **`window.start` pode ser bem depois de `window.requested_start`.** A série de retorno total só
   existe onde o ajuste é completo, e sessão marcada ex sem ação dimensionada por trás é
   distribuição que o projeto não sabe pagar — rodar através dela credita menos caixa do que o
   investidor receberia ([ADR-032](../decisions/ADR-032-the-backtest-stops-where-the-total-return-series-stops.md)).
   `window.bounded_by` nomeia o ativo que decidiu isso. Ele vem `null` quando só o calendário
   moveu a data (ninguém negocia em 1º de janeiro).
2. **`excluded[]` é parte do que foi medido.** `NO_PRICES` (nada armazenado) e
   `NO_TOTAL_RETURN_SERIES` (preço sim, ajuste completo não). Comparar dois backtests exige
   comparar `universe` e `window` antes dos números.
3. **`wealth` não é desempenho.** É patrimônio em BRL — `holdings` a fechamento cru mais `cash`,
   o que a estratégia não gastou — com `contributed` por baixo. A resposta comparável a um
   benchmark é `comparison`, que é **time-weighted**
   ([ADR-019](../decisions/ADR-019-portfolio-return-is-time-weighted.md)). E `comparison`
   descreve um período **mais curto** que `index` sempre que o benchmark tem menos histórico:
   os dois lados são recortados à janela compartilhada, então `comparison.subject.start_date` é
   leitura obrigatória antes de citar um número dali ao lado da curva.

`GET`, e não `POST`, porque nada é gravado (regra 16): rodar duas vezes com os mesmos parâmetros
é a mesma requisição duas vezes, não dois recursos. Erros: 400 `UNKNOWN_STRATEGY`, 400
`INVALID_WINDOW`, 404 `EMPTY_UNIVERSE`, 404 `BENCHMARK_NOT_FOUND`.

⚠️ **E mais três antes de citar qualquer número do `/walk-forward`.**

1. **A figura que responde a pergunta é `stability.degradation_mean`**, não os retornos.
   Estratégia cujo out-of-sample acompanha o in-sample tem parâmetro que descreve alguma coisa;
   a que desaba tem parâmetro que descrevia a amostra em que foi escolhido.
   `stability.selection_rate` é a outra metade: walk-forward que escolhe vencedor diferente a
   cada fold achou ruído, não parâmetro.
2. **Com um fold só, todo agregado vem `null`** e `stability.refusal` é `SINGLE_FOLD`. Média de
   uma observação e dispersão zero leriam como *perfeitamente estável*. O out-of-sample daquele
   fold continua reportado — só o agregado é retido.
3. **Todo segmento parte de carteira vazia**, que é o que torna candidatos comparáveis entre si
   e o in-sample comparável ao out-of-sample. O custo: um segmento mede a estratégia
   **acumulando**, não rodando sobre carteira madura.
4. **O objetivo mede o dinheiro que foi aplicado, não o que foi dado.** Ele lê o índice
   time-weighted, que avalia posição e não caixa
   ([ADR-019](../decisions/ADR-019-portfolio-return-is-time-weighted.md)). Medido no banco real:
   um segmento de 2023 sobre PETR4+BBAS3 terminou com **R$ 3.239,88 em posição e R$ 9.892,81 em
   caixa** sobre R$ 12.000 aportados — índice **+101,38%**, dinheiro **+9,44%**. Os dois estão
   certos e respondem perguntas diferentes; `outcome.contributed` e `outcome.final_value` vêm
   lado a lado para a segunda leitura ficar a uma subtração.
5. **Candidato que não preencheu ordem nenhuma não é ranqueado.** Índice achatado em 100 dá
   retorno exatamente zero, e zero ganharia de todo candidato que aplicou e perdeu.
   `outcome.unrankable = NO_POSITION_TAKEN` é o que diz isso — achado sobre a política, não
   lacuna de dado.

`partition.refusal = WINDOW_TOO_SHORT` significa que a janela replayável não coube em três
segmentos, com `required_months` e `available_months` dizendo por quanto. A correção é a
montante — ingerir os eventos societários que truncam a série de retorno total
([ADR-032](../decisions/ADR-032-the-backtest-stops-where-the-total-return-series-stops.md)) —
**nunca** encurtar os segmentos até caberem. `fold.refusal = OBJECTIVE_UNAVAILABLE` significa
que nenhum candidato pôde ser pontuado: no objetivo padrão, que não há CDI cobrindo o segmento.
Objetivo fora do enum → 422. ⚠️ **A rota roda muitos backtests** (um por candidato no treino,
um por candidato da shortlist na validação, e um no teste, por fold).

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

- `BacktestResponse`: `settings` (tudo que parametrizou a execução, inclusive `costs` e
  `publication_lag_months`), `window`, `universe[]`, `excluded[]`, `comparison`, `alpha`,
  `index[]`, `wealth[]`, `trades` e `sources[]`.
  `alpha` é o retorno que sobra **depois de pagar pela exposição ao mercado** — não é o
  `comparison.excess_return`, que é diferença simples. Excesso positivo com alpha negativo
  significa que a estratégia subiu porque o mercado subiu, e menos do que o próprio beta dela
  dava direito. Vem `null` contra benchmark de **taxa**, pelo mesmo motivo que `beta`:
  sensibilidade ao CDI não é quantidade que signifique algo.
  `trades` traz `trades`, `buys`, `sells`, `closed_trades`, `wins`, `losses`, `win_rate`,
  `average_win`, `average_loss`, `profit_factor`, `expectancy`, `realized_result`, `fees`,
  `slippage`/`slippage_paid`/`slippage_earned`, `dividends_received`, `contributed` e
  `unfilled{}`.
  ⚠️ **As cinco figuras de trade fechado vêm `null` em toda estratégia que este projeto
  entrega**, e é a resposta honesta e não uma lacuna: as cinco são definidas sobre trade
  **fechado**, e nada aqui vende ([ADR-028](../decisions/ADR-028-rebalancing-is-cash-flow-only.md)).
  `closed_trades: 0` é o que diz isso — `0%` leria como *toda operação perdeu*.
  **`slippage` é medido, não assumido**: a ordem é decidida contra o fechamento de uma sessão e
  preenchida contra o da seguinte, e a diferença é somada do que aconteceu. Positivo = custou
  dinheiro; as duas direções vêm à parte porque uma execução que pagou R$ 40 e ganhou R$ 38 não é
  uma que quase não se moveu. `unfilled{}` conta as ordens que terminaram em nada, por motivo
  (`NO_PRICE`, `BELOW_ONE_SHARE`, `INSUFFICIENT_CASH`, `NOTHING_HELD`).

- `Explanation` (as três rotas `explain/*`): `topic`, `subject`, `text`, `model`, `prompt_version`, `generated_at`, `facts[]`, `unverified_figures[]` e `truncated`.
  ⚠️ **`unverified_figures` é leitura obrigatória, não diagnóstico.** É a lista de números que aparecem no texto e **não** casam com nenhum fato enviado — ou seja, números que o modelo inventou ou derivou por conta própria. Vem reportada em vez de bloquear a resposta ([ADR-030](../decisions/ADR-030-fact-pack-and-the-hallucination-guard.md)); um cliente que a ignorar desfaz metade da garantia.
  ⚠️ **`truncated` diz que o texto parou no meio, e não que os fatos acabaram.** É `true` quando o modelo esgotou o orçamento de saída antes de terminar a frase. O texto vem **exatamente como gerado** — sem reticências, sem corte até o último ponto final —, porque aparar produziria uma explicação que *parece* completa ([ADR-033](../decisions/ADR-033-a-truncated-explanation-is-reported-not-discarded.md)). Um cliente que exibe a prosa deve rotular o caso; da leitura do texto sozinho os dois jeitos de acabar cedo são indistinguíveis. Aditivo e com default `false`.
  `facts[]` é a evidência: cada fato traz `key`, `label`, `value` (canônico), `formatted` (a string que a tela mostra), `unit` e `source` — **o endpoint que produziu aquele número** (regra 112). O `key` e o `source` não vão para o modelo, só para o leitor.
  `model` é o modelo que **de fato respondeu**, não o pedido: aliases são resolvidos no servidor do fornecedor. `prompt_version` é `system_vN+topico_vN` (regra 43).
  Quando o backend não conseguiu calcular **nenhum** fato, o provedor nem é chamado: volta uma frase fixa dizendo que os dados estão indisponíveis, com `model: "none"` (regra 44).

### Por que as rotas de explicação são POST

Elas não gravam nada — como `/positions` e `/contribution-plan`, tudo é derivado. Mas um GET promete ser seguro e repetível, e estas gastam uma chamada externa metrada e respondem diferente a cada vez. Rotular isso como leitura seria uma mentira que um cache acabaria acreditando.

## Ao adicionar endpoints

1. Schema em `app/domain/<área>/schemas.py`; **nunca** exponha um model SQLAlchemy diretamente.
2. Lógica em `service.py`; a rota só orquestra e traduz erro.
3. `Depends(get_current_user)` salvo justificativa explícita.
4. Erro com envelope `{"error":{"code","message"}}` e `code` novo em SCREAMING_SNAKE.
5. Mudança breaking deve atualizar frontend, testes e esta página (AGENTS.md §71).
6. Teste de integração via `TestClient` cobrindo: sem auth, caminho feliz, recurso inexistente, recurso de outro usuário.
