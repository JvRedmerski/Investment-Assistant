# Completed Tasks

> Camada 4. Marcos entregues, por wave. Responde "o que já foi feito?".
> Notas de implementação task-a-task, validações e decisões datadas: [../PROJECT_STATUS.md](../PROJECT_STATUS.md).

## Wave 00 — Produto & Fundação 🟢

- Repositório Git e estrutura base
- `.gitignore`, `.env.example`, `.env`
- `docker-compose.yml` (postgres + backend + frontend)
- `README.md` e `AGENTS.md` (contrato técnico, 138 seções)
- `docs/PROJECT_STATUS.md` como sistema de tracking

## Wave 01 — Scaffold 🟢

- Backend FastAPI com `/health` e `/ready`
- Frontend React 18 + TypeScript + Vite + Tailwind
- Dockerfiles de backend e frontend; `docker compose config` validado
- pytest rodando

## Wave 02 — Database 🟢

- SQLAlchemy 2.0 + Alembic configurados
- 13 models: `users`, `investor_profiles`, `portfolios`, `assets`, `asset_prices`, `intraday_prices`, `fundamentals`, `financial_indicators`, `transactions`, `portfolio_snapshots`, `recommendations`, `daytrade_setups`, `daytrade_results`
- Migration `001_initial_schema`
- **Correção pós-wave** (2026-08-16): migration `002_numeric_money_columns` — `Float` → `NUMERIC(18,6)`/`Decimal` em `transactions` e `asset_prices` ([ADR-003](../decisions/ADR-003-decimal-money.md))

## Wave 03 — Autenticação 🟢

- Hash de senha com bcrypt e JWT com PyJWT ([ADR-006](../decisions/ADR-006-bcrypt-pyjwt.md))
- `POST /auth/register`, `/login`, `/refresh`, `GET /auth/me`
- `get_current_user` protegendo rotas
- Envelope de erro global `{"error":{"code","message"}}` ([ADR-007](../decisions/ADR-007-error-envelope.md))
- +18 testes

## Wave 04 — Carteira 🟢

- CRUD de assets (watch-only) e de portfolios, escopado por usuário com 404 ([ADR-010](../decisions/ADR-010-404-over-403.md))
- Ledger de transações (BUY/SELL/DIVIDEND/DEPOSIT/WITHDRAWAL) com guarda `INSUFFICIENT_POSITION`
- Motor de posições determinístico, custo médio móvel, derivado do ledger ([ADR-002](../decisions/ADR-002-positions-derived-from-ledger.md))
- `GET /portfolios/{id}/positions`
- +36 testes

## Wave 05 — Market Data 🟢

- `MarketDataProvider` abstrato + `BrapiProvider` + factory + DTOs + exceções tipadas ([ADR-004](../decisions/ADR-004-market-data-provider-abstraction.md))
- httpx com timeout, retry limitado com backoff só em falha transitória, throttle de rate limit
- `sync_daily_history` idempotente; read-path lê só do banco ([ADR-005](../decisions/ADR-005-market-data-caching.md))
- `validate_daily_bars`: rejeita preço não-positivo, volume negativo, OHLC inconsistente e data duplicada; avisa sobre fora de ordem e variação diária >50%
- +39 testes

**Entregues com ressalva**: parser da Brapi nunca validado contra a API real (sem rede no ambiente); `get_quote()` implementado mas não exposto; ingestão de proventos, listada no roadmap §17, não implementada.

## Wave 06 — Fundamental Data 🟢

**W06-001 — Ingestão de Demonstrativos Financeiros** 🟢
- `FundamentalsProvider` abstrato + `BrapiFundamentalsProvider` + factory + DTOs + exceções tipadas
- `sync_annual_statements` idempotente; leitura servida só do banco
- `validate_financial_statements`: rejeita data de referência duplicada, data futura, demonstrativo vazio e valor negativo em receita/dívida/caixa; avisa sobre demonstrativo incompleto
- Migration `003_numeric_fundamentals_columns` — `fundamentals` em `NUMERIC(24,4)` ([ADR-003](../decisions/ADR-003-decimal-money.md))
- Transporte HTTP compartilhado extraído para `app/integrations/http.py`, reaproveitado pelo market data ([ADR-012](../decisions/ADR-012-shared-http-transport.md))
- Política point-in-time definida: só anual, restatement não sobrescreve, nada de TTM ([ADR-013](../decisions/ADR-013-fundamentals-point-in-time.md))
- +45 testes (total 140)

**W06-002 — Indicadores Fundamentalistas** 🟢
- `compute_indicators`: função pura e determinística com as 10 fórmulas (pe, pb, roe, roic, dy, debt_ebitda, net_margin, ebitda_margin, revenue_growth, profit_growth)
- Seleção de preço sem look-ahead: fechamento na data de referência ou anterior mais próxima
- Persistência idempotente; período pulado ainda serve de base para o crescimento seguinte
- `POST /assets/{ticker}/indicators/compute` (sem chamada externa) e `GET /assets/{ticker}/indicators`
- Política de dado faltante: `None` = não computável, nunca zero ([ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md))
- +44 testes (total 184)

**W06-003 — Validação contra a API real e correção do mapeamento** 🟢 (criada nesta wave, não prevista no roadmap original)
- **Parsers validados contra uma resposta real da Brapi** (1 requisição), fechando lacuna aberta desde a Wave 05
- Market data: correto. Fundamentals: **dois bugs silenciosos** — `equity` e `debt` liam campos null em 16/16 períodos, deixando `roe` sempre `None` em dados reais
- `cleanEbitda` identificado como cópia de `ebit`: `ebitda` segue `NULL`, agora por evidência (corrige o ADR-013)
- ROIC destravado com alíquota efetiva derivada por período; `cleanNopat` da Brapi descartado por aplicar 34% fixos
- Guarda para alíquota absurda (PETR4 2020 produzia ROIC de −1096%)
- Migration `004` (`ebit`, `income_before_tax`, `income_tax_expense`); filtro `type == "yearly"`
- Política de recomputação de derivados ([ADR-015](../decisions/ADR-015-indicator-recomputation.md))
- +21 testes (total 205), incl. regressão com a resposta real

**Resultado da wave: 🟢 concluída.** Cinco indicadores produzem valor (`roe`, `roic`, `net_margin`, `revenue_growth`, `profit_growth`); os cinco restantes têm limitação **evidenciada** contra a API, não suposta.

## Wave 06.5 — Manutenção pré-Wave 07 🟢 (não prevista no roadmap)

**W06-004 — Ambiente Postgres real e validação multi-tipo do parser** 🟢
- **A pendência de recomputar indicadores não existia**: não havia banco algum (sem container, sem volume, sem SQLite). Ao subir o Postgres o volume foi criado do zero e todas as tabelas vieram com 0 linhas. A pendência vinha de uma hipótese nunca conferida contra o estado real.
- **O Alembic nunca havia executado**: `migrations/env.py` chamava `context.is_offline()` (inexistente; correto é `is_offline_mode()`) e abortava. `alembic heads`/`history` — a "validação estrutural" da W06-003 — não carregam o `env.py`, e por isso não pegaram. Corrigido; `001`→`004` aplicadas em PostgreSQL 16 real.
- **Market data validado para FII (HGLG11), ETF (BOVA11) e banco (ITUB4)**: mesma forma de resposta da PETR4, 22 barras cada, 0 rejeitadas, 0 avisos. Fixado em teste de regressão.
- **Fundamentals bloqueado por mudança de plano**: os módulos de demonstrativos saíram do plano gratuito da Brapi (403), um dia depois de funcionarem. Bloqueava a Wave 09 — **contornado depois, na W09-002**, adotando os dados abertos da CVM como fonte primária ([ADR-020](../decisions/ADR-020-cvm-primary-fundamentals-source.md)).
- Descoberto que o plano gratuito aceita **1 ativo por requisição** — não há batching. Custo total: 5 requisições.
- +6 testes (total 211)

**W06-005 — Correção do `adjusted_close` fabricado** 🟢 ([ADR-016](../decisions/ADR-016-unadjusted-bars-are-not-stored.md))
- A Brapi deixa `adjustedClose: null` na sessão fechada mais recente; o parser preenchia com o `close`. Combinado com a idempotência de `sync_daily_history` (nunca sobrescreve data gravada), isso **congelaria um ajuste inventado para sempre** — e a Wave 07 calcula todo retorno dessa coluna.
- Corrigido **antes de qualquer ingestão**, com o banco vazio. Depois exigiria identificar linhas suspeitas, o que é impossível com segurança: `adjustedClose == close` é comum e legítimo em dia sem provento.
- Agora o parser reporta `None` e `validate_daily_bars` rejeita a barra (`MISSING_ADJUSTED_CLOSE`). Autocorretivo: a data entra no sync seguinte.
- +4 testes (total 215)

## Wave 07 — Quant Engine 🟢

**W07-001 — `app/quant/returns.py`** 🟢
- `simple_return` (primitiva), `period_returns` (diário, semanal **ISO**, mensal, trimestral, anual), `total_return`, `ytd_return`, `cagr`
- `PeriodReturn` carrega o intervalo que realmente mediu — necessário porque lacunas são normais ([ADR-016](../decisions/ADR-016-unadjusted-bars-are-not-stored.md)) e um retorno "mensal" pode legitimamente cobrir dois meses
- Buckets fechados pela **última observação que de fato contêm**, o que torna feriados e sessões ausentes inofensivos em vez de casos especiais
- YTD ancora no **último fechamento do ano anterior**, não no primeiro de janeiro (que descartaria a virada do ano)
- CAGR retorna `None` abaixo de 30 dias corridos: anualizar dois dias de +3% dá ~+25.000%
- +47 testes (total 262)

**W07-002 — `app/quant/risk.py`** 🟢
- `standard_deviation` e `downside_deviation` (primitivas), `volatility`, `max_drawdown`, `beta`, `sharpe`, `sortino`
- `PERIODS_PER_YEAR` local (252 diário), **não** importado de `returns.py` — com teste que falha se alguém trocar
- **`beta` alinha as duas séries por data antes de medir retornos.** Sem isso, um retorno do ativo que cobre 2 dias (por lacuna) seria regredido contra um intervalo diferente do benchmark
- `beta`/`sharpe`/`sortino` recebem a referência externa como parâmetro e retornam `None` sem ela — a série de CDI/IBOV é da Wave 08, e não foi antecipada
- Taxa livre de risco de-anualizada **geometricamente**, não dividida por 252
- Volatilidade de carteira **não** implementada: exige matriz de covariâncias e pesos. Em Future Work, com a instrução de não aproximar por média
- +54 testes (total 316)

**Resultado da wave: 🟢 concluída.** Duas decisões estruturais em [ADR-017](../decisions/ADR-017-annualisation-and-numeric-type.md): anualização em **365 dias corridos para retorno** e **252 pregões para dispersão** (misturá-las corromperia todo Sharpe por ~1,20 sem sintoma visível), e o Quant Engine **inteiramente em `Decimal`** — `numpy`/`scipy` seguem sem nenhum import no projeto, porque nenhuma das métricas exige uma operação que `Decimal` não cubra.

## Wave 08 — Benchmark Engine (2026-08-18) 🟢

A wave que faz o Quant Engine da W07 produzir número em vez de `None`: `beta`, `sharpe` e
`sortino` estavam escritos e testados desde a wave anterior, esperando apenas a série de
referência.

**W08-001 — Ingestão de benchmarks** 🟢
- `BenchmarkProvider` abstrato + factory. `BcbSgsProvider` (CDI/IPCA/Selic pela API SGS do
  Banco Central — aberta, sem token, sem cota, e fonte **primária**) e `BrapiIndexProvider` (IBOV)
- `BrapiIndexProvider` **não escreve parser**: verificado ao vivo, a Brapi devolve `^BVSP`
  na mesma forma de uma ação, então ele delega ao `MarketDataProvider` já validado na W06
  e só traduz o vocabulário de erro
- Catálogo de benchmarks em **código**, não em tabela — é o que a roadmap §20 pede por
  "outros benchmarks configuráveis", sem seed migration que dois ambientes possam divergir
- `benchmark_values` em `NUMERIC(24,12)` (uma coluna que guarda tanto 166.978,9375 pontos
  quanto uma taxa de 0,00043739) + migration `005`, aplicada em Postgres 16 real
- `INCOMPLETE_PERIOD`: observação de período ainda não encerrado é **rejeitada**. A regra
  olha o fim do *período*, não a data — a linha do IPCA datada de 01/08 mede agosto inteiro
- **Parsers validados contra as APIs reais antes de qualquer mock.** Foi o que revelou:
  404 do SGS significa "janela sem observação" (fim de semana), série inexistente devolve
  HTTP 200 com página HTML, e janela diária acima de 10 anos é recusada com 406
- +75 testes (total 391)

**W08-002 — Comparativo carteira × benchmark** 🟢
- `benchmarks/series.py` — taxa → índice acumulado (na leitura, porque acumular depende da
  data-base, que muda por carteira e por janela); taxa anualizada da janela para o Sharpe
- `portfolio/performance.py` — índice **time-weighted** da carteira (valor de cota) derivado
  do ledger + `asset_prices`, entregue como `PricePoint` para que todo o `app.quant` o leia
  sem adaptador. Sem isso, uma carteira com aporte mensal apareceria batendo qualquer
  benchmark num ano em que o investidor perdeu dinheiro (regra 26)
- `benchmarks/comparison.py` — puro, **não calcula nada**: só orquestra o `app.quant`
- `beta` só contra benchmark do tipo `INDEX`. Contra o CDI não sairia `None` sozinho — a
  variância não é exatamente zero, então a guarda interna não dispara e um número enorme e
  instável seria reportado com cara de fato
- `return_ratio` ("% do CDI") só com **ambos** os retornos positivos — restrição imposta por
  evidência de dado real, que produziu razões de -85,16 e -1,80
- Endpoints `GET /assets/{ticker}/benchmarks/{code}` e `GET /portfolios/{id}/benchmarks/{code}`
- +58 testes (total 449)

**Resultado da wave: 🟢 concluída.** Decisões em [ADR-018](../decisions/ADR-018-benchmark-representation.md) (representação de benchmark) e [ADR-019](../decisions/ADR-019-portfolio-return-is-time-weighted.md) (rentabilidade de carteira).
A base 252 do CDI foi **verificada contra a própria fonte**, não deduzida: compor a série 12
(diária) em 252 reproduz a série 4389 (anualizada) na precisão publicada, em duas janelas
independentes. Validado ponta a ponta contra dado real ingerido — IBOV × IBOV dá excesso
0,00% e beta exatamente 1,0000.

Achado colateral, **não** regressão desta wave: o plano gratuito da Brapi passou a limitar o
`range` a `3mo`, e o `range` é relativo a hoje, sem parâmetro de data inicial — de modo que
`sync_daily_history` falha hoje para qualquer janela acima de 3 meses e não há como paginar
histórico.

---

---

## Marcos de infraestrutura de conhecimento

- **2026-08-17** — Sistema de memória persistente criado: `CLAUDE.md` na raiz + `docs/{memory,architecture,decisions,planning,history}/`, com 11 ADRs extraídos do código e do histórico de decisões.
