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

## Wave 09 — Portfolio Recommendation Engine (2026-08-18 / 2026-08-19)

Quatro tasks em vez das duas planejadas. As duas inseridas não foram escopo extra: cada uma
destravava pilares do score que, sem elas, ficariam permanentemente ausentes — e alocar
dinheiro com parte da fórmula desligada é pior do que adiar a alocação.

### W09-001 — Sub-scores decomponíveis
- Cinco pilares em `app/domain/recommendations/scoring.py`, puro e determinístico
- **Ausência é resposta de primeira classe**: pilar sem dado é `None`, nunca zero nem 50
  "neutro", e fica de fora da média. Um Quality Score fabricado não parece errado — parece
  uma empresa ruim, e depois some dentro do score final
- `compose` renormaliza sobre o que existe e **reporta `coverage`**
- Fórmula versionada, todo limiar é constante nomeada ao lado do motivo (§30)
- `GET /portfolios/{id}/scores`. +50 testes (total 499)

### W09-002 — CVM como fonte primária, Brapi fazendo a ponte
- `CvmFundamentalsProvider` lê os DFP de dados.cvm.gov.br; `CompositeFundamentalsProvider`
  põe a CVM na frente e o fornecedor atrás; `assets.cnpj` (migration `006`) guarda a ponte
- **Período inteiro vem de uma fonte só** — campos nunca são misturados, porque emendar
  produziria uma linha que nenhum arquivo jamais reportou
- `net_income` é `3.11.01` e não `3.11`; EBITDA é derivado (`EBIT + |D&A|`) e diz que é
- Mapeamento conferido contra número público: ROE da PETR4 dá os 10,0% publicados
- +43 testes (total 542)

### W09-003 — Ações em circulação por exercício
- `fundamentals.shares_outstanding` (`NUMERIC(20,0)`) + migration `007`; parse do
  `composicao_capital`: integralizadas menos tesouraria
- Destravou `pe` e `pb` — o último pilar sem dado nenhum
- **O arquivo não declara escala**, e ~1/3 dos declarantes escreve a contagem em milhares,
  alternando entre anos (a própria Petrobras). Sem tratar, o P/L sairia mil vezes menor e
  **clamparia em 100** na escala invertida, mandando as leituras mais quebradas para o topo
- A unidade é **reconciliada contra o LPA do próprio arquivo**, e fica ausente quando
  nenhuma unidade fecha. O LPA é lido **cru**: `ESCALA_MOEDA` não se aplica a valor por ação
- LPA derivado bate com o publicado: PETR4 R$ 2,84, VALE3 7,40 contra 7,39, MGLU3 0,61
- +13 testes (total 555)

### W09-004 — Alocação do aporte mensal
- `app/domain/recommendations/allocation.py`, puro, e `GET /portfolios/{id}/contribution-plan`
- **Ordena por faixa de cobertura antes do score.** Ordenar por `final_score` erra numa
  direção só: o pilar que sobrevive a toda lacuna é Diversification (~100 para o que a
  carteira não tem), então quem tem menos dado ganharia sistematicamente
- Tetos de 20%/40% lidos das **próprias escalas do score**, não redeclarados
- Todo limite configurável (§32); a política volta na resposta
- **Nada é gravado** — o plano é derivado como as posições (§16)
- Toda exclusão tem motivo nomeado; toda alocação diz qual regra a limitou
- +41 testes (total 596)

**Resultado da wave: 🟢 concluída.** Decisões em
[ADR-020](../decisions/ADR-020-cvm-primary-fundamentals-source.md) (fonte CVM) e
[ADR-021](../decisions/ADR-021-allocation-ranks-by-coverage-tier.md) (faixas de cobertura,
plano derivado).

A prova de que o desenho da W09-001 estava certo veio duas vezes, medida no banco real:
ingerir a CVM levou Quality e Growth de ausentes para 97,8 e 76,7, e a contagem de ações
destravou Valuation — **as duas vezes sem uma linha alterada em `scoring.py`**.

Achado registrado, **não** resolvido na wave: `pe`/`pb` estão destravados no código e continuam
ausentes no banco real por falta de **preço histórico**, não de contagem de ações. É a mesma
restrição do teto de 3 meses da Brapi, que também deixa o pilar de Risco ausente.
→ **Resolvido na wave PRICE**, abaixo.

---

## Wave PRICE — Histórico de preços de fonte aberta (B3 COTAHIST) 🟢

> **Inserida fora da ordem do roadmap**, entre a W09 e a W10, por decisão do usuário entre as
> duas opções que a sessão anterior deixou registradas. Mesmo movimento da W09-002 aplicado a
> preços: trocar um fornecedor com cota por um arquivo público do próprio mercado.

**PRICE-001 — o provider, o parser e o cache**

- `B3CotahistProvider` + `CotahistArchive` sobre a série COTAHIST (um ZIP por ano civil, ~79 MB,
  posição fixa, 245 bytes por registro, latin-1)
- **`MarketDataProvider` foi partido**: `DailyHistoryProvider` (só histórico) e
  `MarketDataProvider` (histórico **+** cotação). Arquivo de fim de dia não cota, e fingir que
  cota seria devolver o fechamento de ontem com carimbo de agora
- Filtros que decidem o que é uma barra: `TIPREG=01` e `TPMERC=010` (mercado à vista)
- **`FATCOT` normalizado para uma ação**, validado contra o `VOLTOT/QUATOT` do próprio registro:
  FNOR11 é cotado por 1.000 ações, SMLL11 por 10
- Arquivo **destilado** no download (só à vista, gzip: 14,9 MB de 79 MB); ano fechado em cache
  permanente, ano corrente rebaixado quando a série precisa avançar
- +29 testes, de registros reais copiados verbatim do arquivo de 2024

**PRICE-002 — a ausência de ajuste virou dado**
([ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md), emenda ao ADR-016)

- `asset_prices.adjusted_close` passou a aceitar `NULL` (migration `010`)
- A semântica da ausência pertence à **fonte** (`reports_adjusted_close`): "ainda não publicou"
  continua sendo rejeição (ADR-016 intacto); "nunca publica" é gravado
- `app/domain/market_data/series.py` — **ponto único** de construção de série de retorno; os três
  lugares que faziam isso à mão passam por ele. É o que responde a objeção do ADR-016 contra a
  coluna nula
- Cada linha grava de qual fonte veio
- +14 testes (total 660)

**PRICE-003 — o backfill, e a validação contra o banco real**

- `POST /assets/{ticker}/prices/backfill`, sem teto de janela, convivendo com `/prices/sync`
- Tradução de erro compartilhada pelas duas rotas, **extraída em vez de copiada**
- +12 testes (total 672)

**Resultado da wave: 🟢 concluída.** Medido no PostgreSQL real, que tinha `asset_prices` vazia:

```
backfill PETR4 2020–2025 → 1.495 pregões, 0 rejeitados
pe/pb: None nos 6 exercícios → P/L 12,74 e P/VP 1,27 em 2024, P/L 1,70 em 2022
score: cobertura 0,55 → 0,75; pilar de Valuation de ausente → 93,5
```

Terceira vez que o desenho da W09-001 se paga: **nenhuma linha de `scoring.py` foi alterada**.

Pendência deixada explícita, **não** resolvida: o pilar de **Risco** continua ausente, e por
decisão. Métrica de risco exige série de retorno total, e a bolsa publica preço negociado. O
remendo proibido está medido em dado real — o grupamento 1:10 da MGLU3 vale **+896% num pregão**
na série crua. A correção é a montante: ingerir eventos societários e proventos, que é a mesma
ingestão que destrava o `dy`.

---

---

## Wave EVENTS — Eventos societários e proventos (2026-08-19 → 2026-08-20) 🟢

Segunda wave **inserida fora da ordem do roadmap**, entre a W09 e a W10, pelo mesmo critério da
PRICE: destrava mais coisa do que a wave seguinte da fila.

**EVENTS-001 — proventos por exercício, da DMPL da CVM** ([ADR-024](../decisions/ADR-024-refill-fills-null-columns.md))

- `dy` era o último indicador com fórmula escrita (desde a W06-002) e nenhuma fonte
- Três detalhes decidem se o número está certo, e os três foram conferidos no arquivo real: a
  **coluna** (só `Patrimônio Líquido`, porque a irmã `Consolidado` soma o pago a
  não-controladores — R$ 302 mi na PETR4 em 2024), o **sinal** (distribuição é débito) e o que
  **fica de fora** (`5.04.11`, dividendos prescritos, é estorno de período anterior)
- **A armadilha que a task expôs vale mais que a coluna**: período gravado é congelado com os
  campos que o código conhecia no dia (ADR-013), então os seis exercícios já no banco ficariam
  vazios para sempre. Daí `?refill=true`, que preenche coluna `NULL` e **só** ela. As duas
  colunas anteriores (`ebit`, `shares_outstanding`) só funcionaram por terem chegado a um banco
  **vazio** — ninguém tinha percebido
- +14 testes (total 686); migration `011`

**EVENTS-002 — em que pregão o papel foi ex, dito pela bolsa** ([ADR-025](../decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md))

- O marcador do `ESPECI` é **janela de exibição, não evento**: persiste ~8 pregões e ainda decai
  (`EDJ` → `EJ`, 132 sessões em 2024). A BBAS3 exibe `ON  EDJ NM` em 12, 13 e 14/06 enquanto o
  contador vai **323, 323, 324** — duas distribuições sob marcador imóvel
- O sinal exato é o **`DISMES`**. Conferido no sentido inverso no arquivo inteiro de 2024:
  **2.230 papéis, 7.312 incrementos**, nunca decresceu, e só 13 letras de ex- apareceram sem
  incremento — **nenhuma movendo preço em 25% ou mais**
- Duas letras mudaram de nome por evidência: `EB` → `BONUS_OR_SPLIT` e `R` → `OTHER_DISTRIBUTION`
- +15 testes (total 701); 20 fixtures conferidas byte a byte

**EVENTS-003 — a série de retorno total** ([ADR-026](../decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md))

- **A fonte da magnitude não estava na lista de candidatas.** É o serviço aberto de eventos
  corporativos da própria B3 — reais por ação num provento, fator num desdobramento, sem token e
  sem cota
- **Conferido antes de virar código**: datas contra o contador `DISMES`, um sinal independente,
  **157/157** em janela; fatores contra o degrau de preço, **49/50**
- **A junção é o ISIN.** A B3 repete um evento uma vez por ISIN que o emissor já teve; compondo
  tudo o acordo caía para 32/50, e **todo** desacordo era uma **potência exata** da resposta certa
  (2³ na BBAS3, 10³ na CPLE3) — foi esse padrão que apontou duplicação em vez de fórmula errada
- **A parte difícil foi decidir quando o ajuste pode rodar.** `adjusted_close` só é derivado onde
  toda sessão contada tem ação dimensionada, e quem julga isso é o **contador da B3**, não o
  serviço — que **omite**: ITUB4 foi ex em 2025-03-18 com degrau de -8,60% e ele não reporta nada
- A exceção do marcador `ATZ` (151 incrementos, degrau mediano 1,0028, 6 exceções nomeadas) foi
  **decisão do dono do projeto**, com o custo da alternativa medido: sem ela a PETR4 teria 28 de
  1.495 pregões ajustáveis
- +49 testes (total 750); migration `012`

**Resultado da wave: 🟢 concluída.** Medido no PostgreSQL real:

```
dy: None nos 6 exercícios → 0,22 em 2024 e 0,70 em 2022 (PETR4)
adjusted_close: 0 de 1.495 → 1.495 de 1.495 (PETR4 e BBAS3)
PETR4: volatilidade 41,8%, drawdown -63,4% com fundo em 2020-03-18 (a COVID)
       pior sessão ajustada = pior sessão crua (-29,7%) → nenhum evento vazou
MGLU3: grupamento 1:10 aparece como 13,5%, não como os +896% do ADR-023
ITUB4: truncada em 2025-03-19, corretamente, por um evento que a B3 não dimensiona
```

O pilar de **Risco** deixou de ser ausente, que é o que a wave existia para fazer.

Pendência deixada explícita, **não** resolvida: **subscrição** não é dimensionada — a B3 publica
percentual e preço de exercício, e transformar isso em fator exige um **modelo do valor do
direito**, não uma medição.

---

---

## Wave 10 — Rebalanceamento (2026-08-21) 🟢

De volta à ordem do roadmap. A wave inteira era **uma pergunta**: o roadmap §22 e a regra 34 pedem
`current_weight`, `target_weight` e `weight_gap`, e não dizem de onde sai o alvo. Peso atual é
ledger, gap é subtração.

### W10-001 — o alvo sai do mérito ([ADR-027](../decisions/ADR-027-target-weight-comes-from-merit.md))

`targets.py` (puro) e `scoring.merit`. **A resposta óbvia foi medida e reprovada antes de virar
código**: alvo proporcional ao `final_score` não converge, porque o score lê a carteira que o
alvo deveria mirar.

| peso detido de PETR4 | `final_score` | quality | valuation | growth | risk | diversification |
|---|---|---|---|---|---|---|
| 0% | **76,72** | 97,8 | 93,5 | 76,7 | 28,3 | 100,0 |
| 10% | 71,10 | 97,8 | 93,5 | 76,7 | 28,3 | 62,5 |
| 20% | **65,47** | 97,8 | 93,5 | 76,7 | 28,3 | 25,0 |

Nada mudou na empresa. Um alvo feito desse número **recua conforme a carteira se aproxima**, e a
distância reportada não é distância até coisa alguma. O alvo passou a sair do **mérito** e a
concentração virou **teto** — os mesmos limites da W09, lidos da mesma `AllocationPolicy`.

Distribuição por *water-filling*, e **o teto setorial é testado antes do teto por ativo**: um erro
de ordem encontrado traçando o algoritmo à mão punha três papéis de um setor a 20% cada, com o
setor em 60% contra um limite de 40% nunca consultado.

Medido no banco real: PETR4 com mérito **72,61** e alvo **0,20** aparado pelo teto, com **0,80
`unassigned`**; ITUB4, que marca **92,47 com cobertura 0,40**, **não recebe alvo** — sob a regra do
mérito ela tem um pilar só.

### W10-002 — a tabela de desvio sobre a API

`portfolio_targets` + `GET /portfolios/{id}/rebalance`, ordenada mais-underweight-primeiro. A
construção de candidatos virou `_candidates`, compartilhada com o plano de aporte.

**O que só o teste ponta a ponta mostra**: sem demonstrativos *nenhum* ativo recebe alvo, e baixar
`min_coverage` não resolve — o que falta não é o piso, é um segundo pilar de mérito.

### W10-003 — o aporte que fecha os gaps ([ADR-028](../decisions/ADR-028-rebalancing-is-cash-flow-only.md))

`rebalancing.py` + `GET /portfolios/{id}/rebalance-plan`. Ordena por **gap** (o plano de aporte
ordena por score) e cada alocação para em `target * base - held`. **Nada vende.**

🔴 **O teste contra o banco real pegou uma falha de desenho que teste unitário nenhum pegaria**,
porque os 18 unitários verdes tinham sido escritos sob a mesma premissa errada: o portão de
elegibilidade lia o peso **antes** do aporte enquanto o dimensionamento inteiro já rodava sobre
`invested + contribution`.

| | primeira versão | corrigida |
|---|---|---|
| PETR4 alocada | R$ 0 (`ABOVE_TARGET`) | **R$ 140** (`TARGET_WEIGHT`) |
| distância a percorrer | 0 → **0,0636** | 0 → **0** |

PETR4 a 25% contra alvo de 20% era recusada por estar *acima*; com os R$ 1.000 parados em caixa a
base virava R$ 2.200 e ela caía para **13,6%** — mais abaixo do alvo do que estava acima, por ter
sido recusada por estar acima dele.

### Balanço

- `pytest` **750 → 815**. Nenhuma migration: nada da wave é gravado (regra 16).
- Dois ADRs: 027 (de onde vem o alvo) e 028 (rebalancear é dirigir aporte, e em que base).
- **A wave não precisou de nenhuma fonte externa nova.** Foi a primeira desde a W07 assim, e é
  consequência de as três anteriores terem fechado os insumos.

---

## Wave 11 — Dashboard (2026-08-21) 🟢

A wave que tirou o frontend do estado de scaffold. **Duas tasks de backend vieram antes das
telas**, porque o roadmap §23 pede números que o backend não produzia — "patrimônio"
(`quantity × preço`) e a **série** de evolução — e a regra 73 proíbe calcular isso no cliente.

### W11-001 — valor de mercado, com ausência por linha

`quantity × close`, **nunca** `adjusted_close`: ajuste é retroativo, e uma posição de 2020
valorizada ao preço ajustado vale uma fração do que as ações renderiam.

A política de ausência é a **terceira** do projeto, e de propósito. `performance_index` apaga o
**dia inteiro** se um ativo não tem preço (série time-weighted com constituintes diferentes é
outra carteira); `recommendations/service.py` usa **custo basis** para não deixar o pilar ausente.
Uma tabela de posições lê linha a linha, então só a **linha** fica ausente — e o nome do campo é o
que impede a leitura errada: `valued_market_value`, com `unvalued_positions` e `unvalued_invested`
dimensionando o buraco.

Dois achados na verificação real: o `as_of` filtrava os preços mas **não o ledger** (corrigido), e
o ledger **não conhece evento societário**, então posição carregada através de desdobramento tem
quantidade errada — lacuna pré-existente que só o valor de mercado tornou visível, registrada em
Future Work.

### W11-002 — a série de evolução, e o índice que ela consertou

`GET /portfolios/{id}/series` devolve **duas** curvas: `wealth` (patrimônio em BRL, com a linha
`invested` ao lado) e `index` (time-weighted). `align` recorta as duas séries para a janela
**compartilhada** com o benchmark e rebaseia ambas ali; nada é interpolado.

🔴 **Rodando contra seis anos reais de PETR4, o índice deu -3,88.** Valor de cota não pode ser
negativo. Causa: **erro de unidade** — posições valorizadas em `adjusted_close`, fluxos entrando
em preço **negociado**. Caso mínimo, mesmas operações e mesmo +10% de retorno:

| fator de ajuste | níveis |
|---|---|
| 1 (o único caso que a suíte exercitava) | 100 → 100 → 110 ✅ |
| 3 | 100 → **-100** → **-110** 🔴 |

`_external_share_flows` expressa o fluxo em **ações**, valorizadas no mesmo `adjusted_close` das
posições. **Efeito colateral bom**: a aproximação que o módulo documentava como seu ponto fraco
sumiu para o caso comum — comprar mais de algo já detido durante um vão de preço passou a ser
**exato**, porque o preço desconhecido aparece nos dois sub-períodos e cancela.

Depois da correção: aportes ao longo de 2020 em PETR4 dão **100 → 358,23** em seis anos,
consistente com o fator de retorno total de 3,43× medido na EVENTS-003.

### W11-003 — a primeira aplicação real de frontend

`src/lib/api.ts` é a **única** porta para o backend: base URL, bearer token, desembrulho do
envelope de erro num `ApiError` **com o código**, e **validação `zod` de toda resposta**. Cast é
promessa que o compilador acredita e ninguém confere. `ContractError` é distinto de `ApiError` de
propósito.

Dinheiro continua `string` até a formatação — o backend serializa `Decimal` como string para não
passar por float binário, e converter no cliente desfaria isso no único salto em que estava
protegido.

Tela de **Carteira** entregue como prova da corrente inteira. 🔴 O `.gitignore` estava
**engolindo o cliente de API**: `lib/`, do template Python, casa em qualquer profundidade.
Ancorado em `backend/lib/`.

### W11-004 — o Dashboard, e o comparativo que ele consertou

Responde: quanto eu tenho, estou batendo o CDI, quanto risco carrego, do que é feita a carteira,
onde vai o próximo R$ 1.000. Gráficos sob a regra 74: nada interpolado, duas linhas só dividem
eixo se dividem unidade, e todo gráfico carrega legenda com as seis coisas que a regra nomeia.

🔴 **O painel de excesso sobre o CDI mostrou +251,5 p.p.** `compare` media o sujeito na janela
dele e o benchmark na dele, e subtraía: 4,7 anos de ação contra quatro meses de juros.

| | antes | depois |
|---|---|---|
| excesso sobre o CDI | **+251,5 p.p.** | **+7,1 p.p.** |
| retorno da carteira | 266,1% | 12,4% |
| volatilidade | 58,7% | 22,5% |
| drawdown | -34,3% | -13,4% |

E o número do painel passou a **bater com o gráfico ao lado**.

### W11-005 — a tela de Ativo

Cotação, histórico, indicadores, eventos societários e o **score decomposto**, mais o peso atual e
o peso-alvo na carteira selecionada. **A cobertura vem antes do score, não numa nota de rodapé**:
o banco real tem ITUB4 em 92,5 com cobertura 0,40, e mostrar 92,5 grande reproduziria a armadilha
que o backend gastou uma wave desarmando. Pilar ausente é desenhado como ausente.

O mapa de rótulos de evento estava **escrito por suposição** e errado — pego conferindo contra as
respostas reais dos quatro papéis.

### Balanço

- `pytest` **832 → 859**. Nenhuma migration: nada da wave é gravado (regra 16).
- **Duas correções de waves anteriores**, ambas encontradas rodando contra o banco real, ambas
  invisíveis para a suíte porque **os testes compartilhavam a premissa errada** — a mesma lição
  da W10-003.
- Nenhum ADR novo: as duas correções são consertos de unidade e de janela, não decisões entre
  alternativas.
- ⚠️ O frontend segue **sem teste automatizado**; os 14 schemas foram conferidos à mão contra um
  backend real. Em Future Work.

---

## Wave 12 — AI Engine (2026-08-21) 🟢

A wave que transformou a regra mais repetida do contrato em mecanismo. O
[ADR-009](../decisions/ADR-009-quant-deterministic-ai-explains.md) decidiu em 2026-08-09 que a IA
não calcula e não decide, e não disse **como** — não havia código de IA para dizer. Chegando aqui,
"garantir" precisou virar estrutura, porque um prompt *pede* e não *garante*.

### W12-001 — `AIProvider`, e uma dependência a menos

`AIProvider` abstrato + `GeminiProvider` + `OllamaProvider` + `DisabledAIProvider`. Os três
concretos falam **REST pelo `RetryingJsonClient`**, que ganhou `post_json` e `default_headers` —
as primeiras capacidades novas desde o [ADR-012](../decisions/ADR-012-shared-http-transport.md),
que já nomeava "IA (W12)" como um dos quatro provedores que compartilhariam o transporte.

`google-generativeai` foi **removido** do `pyproject.toml`, não usado: declarado desde a W00,
nunca importado, nem instalado no venv, e é o SDK que o Google descontinuou em favor de
`google-genai`. Adotá-lo seria adotar uma migração, e traria transporte, retry e exceções
paralelos aos do resto do projeto para uma requisição que é **um POST com três campos**
([ADR-029](../decisions/ADR-029-ai-provider-speaks-rest.md)).

`AI_PROVIDER=none` é deployment suportado, não defeito: explicação é a única feature que pode ser
desligada sem mudar um número em lugar nenhum.

### W12-002 — o fact pack, e o guard

`app/domain/ai/`. O modelo nunca vê o banco, uma série ou os componentes de um score. Vê um
**fact pack**: lista fechada e plana de valores já calculados, cada um com rótulo, unidade, a
string **já renderizada** e o endpoint de origem. `facts.py` é a cintura estreita — tudo que o
modelo verá passa por ali, então a regra vive num lugar legível em vez de depender de disciplina
espalhada.

Arredondar também é calcular, então `formatting.py` é o **espelho exato** de
`frontend/src/lib/format.ts`, `ROUND_HALF_UP` incluído porque é o gêmeo Python do half-expand do
ECMA-402. A frase e o painel citam a **mesma string** — a mesma classe de defeito que a W11-004
corrigiu, desarmada antes de aparecer.

E `guard.py` confronta todo número do texto com o conjunto fechado de figuras que o backend
escreveu. O que não casar volta em `unverified_figures`: **reportado, nunca rejeitado**. Rejeitar
faria a confiabilidade do recurso depender de como o modelo redigiu uma frase, e filtro com falso
positivo é filtro que alguém desliga
([ADR-030](../decisions/ADR-030-fact-pack-and-the-hallucination-guard.md)).

Prompts versionados em `prompts/*_v1.txt` (regra 43), contendo **só** papel, guardrails e a ordem
do argumento — nenhum limiar, peso ou versão, que chegam como fatos com valor e origem.

### W12-003 — as três rotas

`POST /portfolios/{id}/explain/{performance,contribution-plan,scores/{ticker}}`. São POST embora
não gravem nada: um GET promete ser seguro e repetível, e estas gastam uma chamada externa metrada
e respondem diferente a cada vez.

`_contribution_plan_response`, `_asset_score_response` e `_resolve_benchmark` foram **extraídos**
das rotas existentes em vez de duplicados — a explicação descreve o objeto que o endpoint devolve,
não uma segunda montagem dele.

### Os dois defeitos que a wave achou em si mesma

Os dois eram de **desenho**, e os dois apareceram rodando o teste que proíbe o prompt de
introduzir número que não seja fato:

1. **`key` e `source` estavam sendo renderizados dentro do prompt.** Servem ao leitor, não ao
   modelo, e mandá-los punha os dígitos de `/api/v1/portfolios/1` na frente de um modelo instruído
   a citar só o que recebeu. Hoje viajam só na `Explanation` (§91, §112).
2. **O prompt de sistema trazia `"12,4%"` como exemplo** de como citar um valor — um número
   plausível em toda requisição, pronto para vazar para uma explicação onde não significa nada.
   Virou `"X,Y%"`, e um teste agora proíbe qualquer coisa com a forma `\d,\d` ali.

Um terceiro achado, sobre o contrato: os testes de rota assumiam envelope de erro sob `detail`,
quando a regra 72 o põe no topo. **O teste é que estava errado.**

### Balanço

- `pytest` **859 → 944**. Nenhuma migration: nada da wave é gravado (regra 16).
- **Nenhuma dependência adicionada** — uma removida.
- Dois ADRs novos ([029](../decisions/ADR-029-ai-provider-speaks-rest.md),
  [030](../decisions/ADR-030-fact-pack-and-the-hallucination-guard.md)).
- 🔴 **Nenhuma chamada real a modelo nenhum aconteceu** — a chave do Gemini é válida mas a API
  está desabilitada no projeto Google Cloud dela, e não há Ollama local. Por isso **nenhum teste
  de regressão de parser foi escrito**: um mock construído sobre suposição não verifica a
  suposição, reproduz ela (a lição da W06-003). Os dois providers são código não verificado.
  - ✅ **Fechado para a Gemini em 2026-08-22**, fora de wave. A API foi habilitada, a chamada
    real aconteceu, e a espera se pagou: o contrato bateu nome por nome, mas a chamada revelou
    que o modelo **raciocina** e que o raciocínio come o mesmo orçamento da prosa — no valor
    padrão, uma frase cortada era servida como explicação pronta
    ([ADR-033](../decisions/ADR-033-a-truncated-explanation-is-reported-not-discarded.md)).
    `tests/test_gemini_provider.py` existe agora, sobre payload capturado.
    ⚠️ **O `OllamaProvider` continua não verificado e sem teste** — não há servidor local.
- ⚠️ Duas das cinco capacidades do roadmap §24 ficaram fora **por falta de fonte**: resumir
  notícia e resumir documento exigem ingestão que o projeto não tem.
- ⚠️ `unverified_figures` **não tem quem o exiba** — a wave é backend-only por decisão.

---

## Wave 13 — Backtesting de carteira (2026-08-21)

**6 tasks** — o roadmap previa 2, e as quatro a mais não são subdivisão: são coisas que só
apareceram ao construir. `02cd288` · `a42a91f` · `6409568` · `67b6cf7` · `9c55cab` · `6142a97` ·
`0f5bb0b`

| task | entrega |
|---|---|
| **W13-001** | Ação societária aplicada no replay do ledger |
| **W13-002** | O motor de simulação, puro e sem I/O |
| **W13-003** | A própria estratégia do projeto replayada, com o lag de publicação da CVM |
| **W13-004** | `alpha` no quant, *slippage* medido, trade fechado |
| **W13-005** | O serviço, com a janela limitada pela série de retorno total |
| **W13-006** | `GET /api/v1/backtests` |

### O ponto da wave, em uma frase

**O backtest fala ledger.** A saída da simulação são linhas de `Transaction` — o mesmo formato de
uma carteira real — então `compute_positions`, `value_series` e `performance_index` medem um
backtest com **exatamente** o código que mede a carteira do investidor. Um segundo caminho de
valorização seria um segundo conjunto de bugs, e a primeira divergência apareceria como um
backtest discordando do dashboard por motivo que ninguém saberia nomear. Pela mesma razão a
estratégia sob teste não é reimplementada: é `allocate_contribution`, a mesma função pura que
`/contribution-plan` chama hoje.

### As três formas de olhar o futuro, e como cada uma foi fechada

1. **Preço.** A decisão recebe os fechamentos **daquela sessão** e nada mais, e a ordem preenche
   na **seguinte** — um fechamento só pode ser lido depois de impresso. O intervalo entre decidir
   e preencher é onde mora o *slippage*, e por isso ele é **medido** e não assumido a uma taxa em
   pontos-base.
2. **Balanço.** A regra 108 bastava para um score de hoje e não para um backtest: exercício que
   fecha em 31 de dezembro não é público em 1º de janeiro. Três meses, o prazo do DFP — a data
   **legal mais tardia**, porque errar para tarde custa informação e errar para cedo dá informação
   que ninguém tinha ([ADR-031](../decisions/ADR-031-a-statement-is-readable-only-after-the-filing-deadline.md)).
3. **Provento.** A janela começa onde **todo** ativo tem série de retorno total completa: sessão
   marcada ex sem ação dimensionada é distribuição que a simulação não paga, e a execução ficaria
   **errada**, não apenas não-mensurável ([ADR-032](../decisions/ADR-032-the-backtest-stops-where-the-total-return-series-stops.md)).

### O defeito de wave anterior que a W13-001 corrigiu

Desdobramento, grupamento e bonificação mudam o que está em custódia e **não geram transação**.
Inofensivo enquanto posição era só custo; erro de fator inteiro assim que valor de mercado chegou
na W11-001. Medido no banco real, três dos quatro ativos acompanhados têm um — a MGLU3 tem os três,
que compostos dão **0,42**: uma posição de 2019 reportaria 100 ações contra as 42 em custódia.
A metade sutil é que as **duas curvas precisam de restatements opostos do mesmo evento**, porque
precificam a posição de formas diferentes; inverter isso desenha uma linha suave errada pelo fator
ao quadrado.

### Os dois defeitos que rodar contra o banco real encontrou

Nenhum era alcançável por fixture:

1. **Um feriado estava sendo reportado como problema de dado.** `window.bounded_by` nomeava um
   ativo porque ninguém negocia em 1º de janeiro. O campo existe para o caso honesto.
2. **Alpha estava sendo calculado contra o CDI.** O `compare` não reporta beta para benchmark de
   taxa, e alpha é a aritmética do beta.

### Balanço

- `pytest` **944 → 1.049**. Nenhuma migration: nada da wave é gravado (regra 16).
- **Nenhuma dependência adicionada** — `alpha` entrou em `Decimal`, como todo o resto do quant.
- Dois ADRs novos ([031](../decisions/ADR-031-a-statement-is-readable-only-after-the-filing-deadline.md),
  [032](../decisions/ADR-032-the-backtest-stops-where-the-total-return-series-stops.md)).
- **Um padrão paralelo removido**: `schemas.py` é a camada Pydantic em 13 de 13 módulos, e o de
  backtesting guardava dataclasses do motor. Elas foram para `simulation.py`.
- ⚠️ **Nenhuma tela lê um backtest** — a wave é backend-only por decisão; o roadmap põe
  `/backtests` na W22.
- ⚠️ **As cinco figuras de trade fechado voltam `null`** em toda estratégia que o projeto entrega,
  porque nada aqui vende (ADR-028). É a resposta honesta, não uma lacuna.

---

## Wave 14 — Walk-Forward Validation 🟢

> A wave que consegue dizer que a estratégia **não** passou. 5 tasks (o roadmap previa 1).

- **W14-001** — a partição `Train → Validate → Test`, pura e determinística, com o corte movendo
- **W14-002** — a grade de políticas candidatas e o objetivo de seleção
- **W14-003** — o serviço: treino ordena, validação escolhe, teste só reporta
- **W14-004** — `GET /api/v1/backtests/walk-forward`
- **W14-005** — rodar contra o banco real, e corrigir o que ele achou

### O ponto da wave, em uma frase

**Nada medido no teste alcança uma seleção.** Treino pergunta à grade inteira, validação pergunta
só à shortlist sobre história que a ordenação não viu, e teste roda o vencedor e mais ninguém.
É a regra 61 inteira, e é a única razão de um número out-of-sample significar alguma coisa.

### As duas decisões que sustentam isso

1. **A grade é um conjunto de hipóteses, não um espaço de busca**
   ([ADR-034](../decisions/ADR-034-the-grid-is-a-hypothesis-set-not-a-search-space.md)). Sete
   candidatos, cada um diferindo da política do chamador em **exatamente um campo**, cada um com
   a pergunta que responde escrita ao lado. O produto cartesiano dos mesmos três eixos seria
   dezoito — varredura vestida de walk-forward. Empate vai para a política **já em produção**.
2. **Os três segmentos têm o mesmo tamanho e cada um parte de carteira vazia**
   ([ADR-035](../decisions/ADR-035-equal-segments-from-an-empty-portfolio.md)). A estratégia
   constrói carteira por aporte mensal, então o tamanho do segmento muda o que ele mede: um teste
   mais curto reportaria degradação que é em parte só carteira mais nova. Confundidor removido
   **por construção**, não corrigido depois.

### O defeito que só rodar contra o banco real achou

Candidato que **não preencheu ordem nenhuma** era pontuado em **zero** — e zero ganha de todo
candidato que aplicou e perdeu dinheiro. Uma política que não financiou nada venceria qualquer ano
de queda, na força de um índice achatado em 100 por construção. Agora é `NO_POSITION_TAKEN`:
não-ranqueável, não pontuado em zero.

### O veredicto, que é o produto da wave

PETR4+BBAS3, três folds anuais: o vencedor **mudou a cada fold** (`selection_rate` 0,50), o fold 2
escolheu por **0,2 ponto percentual** e perdeu **90 pontos** de retorno fora da amostra, e a
`default` — a política que o projeto entrega — não foi selecionada em fold nenhum. **Os parâmetros
não são estáveis** sobre a história que existe hoje.

### Balanço

- `pytest` **1.063 → 1.129**. Nenhuma migration: nada da wave é gravado (regra 16).
- **Nenhuma dependência adicionada.**
- Dois ADRs novos ([034](../decisions/ADR-034-the-grid-is-a-hypothesis-set-not-a-search-space.md),
  [035](../decisions/ADR-035-equal-segments-from-an-empty-portfolio.md)).
- ⚠️ **O universo acompanhado não suporta o esquema padrão**: nove meses de janela replayável
  contra 36 exigidos, `bounded_by: ITUB4`. A resposta é `WINDOW_TOO_SHORT`, e a correção é a
  montante — ingerir os eventos societários que faltam.
- ⚠️ **O objetivo mede o dinheiro aplicado, não o dado** (índice time-weighted não vê caixa).
  Nomeado no código, na API e em *Future Work*; corrigi-lo com uma segunda definição de retorno
  seria pior do que nomear a lacuna.
- ⚠️ **Nenhuma tela lê um walk-forward** — backend-only, como a W13.

---

## Wave 15 — Day Trade Data 🟢

> A wave em que a chamada real antes dos mocks se pagou de novo, e caro. 6 tasks (o roadmap
> previa 1).

- **W15-001** — o contrato: `Timeframe`, `IntradayBar`, `HistoryWindow`, `IntradayHistoryProvider`
- **W15-002** — `BrapiProvider.get_intraday_history`, contra uma resposta que foi de fato lida
- **W15-003** — qualidade e detecção de gaps: `intraday_quality`, puro e sem I/O
- **W15-004** — `intraday_prices` em `NUMERIC`/`TIMESTAMPTZ` com `source_window` (migration `013`)
- **W15-005** — ingestão idempotente que recusa misturar janelas, e as duas rotas
- **W15-006** — rodar contra o banco real e o provider real, e corrigir o que achou

### O ponto da wave, em uma frase

**Uma barra intraday não é um fato estável nesta fonte.** A mesma barra — mesmo ticker, mesmo
timestamp, mesmo timeframe — volta com OHLCV diferente conforme o `range` pedido, então a janela
faz parte da identidade da barra e é gravada com ela.

### O que a chamada real mediu, antes de qualquer parser

| medição | resultado |
|---|---|
| Mesmo balde, duas vezes | 135/135 e 1.194/1.194 idênticas — a fonte é determinística |
| `5d` contra `1mo` | 135/135 — mesma partição |
| **`5d` contra `3mo`** | **0 de 135** |
| **`1mo` contra `3mo`** | **0 de 567** |
| `adjustedClose` intraday | **nulo em 1.389 de 1.389** — o campo não existe em `IntradayBar` |
| Intraday liberado **por ticker** | PETR4/ITUB4/MGLU3/VALE3 sim; BBAS3/BOVA11 não |
| Ticker inexistente no caminho intraday | `INVALID_INTERVAL`, **nunca 404** |
| `1m` + `3mo` | **5 sessões** contra 22 em `1m` + `1mo` |
| Sessão de 2026-07-31 | 16 barras numa fase `:01/:16/:31/:46`, reais |

### As duas decisões que sustentam isso

1. **A janela do pedido faz parte da identidade da barra**
   ([ADR-036](../decisions/ADR-036-the-request-window-is-part-of-a-bars-identity.md)). A regra
   diária — nunca sobrescrever data gravada — não basta: aplicada barra a barra, montaria uma
   sessão a partir de **duas partições dela**. A **sessão** é a unidade que vem de uma janela só,
   como o período dos fundamentos no ADR-020, e o conflito é **reportado, nunca resolvido em
   silêncio** — as duas respostas são auto-consistentes e nada no dado diz qual é a certa.
2. **Buraco se mede, borda de sessão se compara**
   ([ADR-037](../decisions/ADR-037-a-gap-is-measured-a-session-edge-is-compared.md)). Um buraco
   entre barras entregues é aritmética. Uma sessão que começou tarde não é mensurável sem o
   calendário de pregões da B3, que o projeto não tem — então `SHORT_SESSION` compara com as
   vizinhas do lote e não pretende saber se foi abertura tardia, leilão ou perda de linhas.
   **Sem checagem de alinhamento de grade**: ela teria rejeitado 16 preços reais.

### O que só rodar contra o banco real achou

A garantia é **por sessão**, e uma série não é uma sessão. Três dias sincronizados e depois
sessenta deixam 3 sessões em `5d` e 40 em `3mo` — cada uma íntegra, a série inteira com uma
**costura** que a leitura devolvia sem declarar. `GET /assets/{ticker}/intraday` passou a
devolver envelope com `windows`.

E um segundo defeito, alcançável direto pela API: a substituição estava condicionada a
**divergência de janela**, então re-sincronizar sessão já gravada sob a **mesma** janela pulava
o delete e reinseria todas as barras — violação de unicidade na segunda chamada, HTTP 500.

### Balanço

- `pytest` **1.129 → 1.228**. Migration `013_intraday_precision`, aplicada contra o Postgres
  real **e revertida e reaplicada** para conferir as duas direções.
- **Nenhuma dependência adicionada.** `tzdata` foi considerada para `ZoneInfo` e **recusada**:
  quebra no Windows e funciona no contêiner, o que faria o mesmo código agrupar sessões de
  formas diferentes conforme onde rodasse.
- Dois ADRs novos ([036](../decisions/ADR-036-the-request-window-is-part-of-a-bars-identity.md),
  [037](../decisions/ADR-037-a-gap-is-measured-a-session-edge-is-compared.md)).
- ⚠️ **O universo intraday é de 3 ativos, não 4** — BBAS3 não é servido no plano gratuito.
- ⚠️ **Uma série pode ter costura entre sessões.** Reportada em `windows`, não impedida.
- 🔴 **Achado fora do escopo e registrado sem corrigir** (§134): o token da Brapi vaza para o log
  da aplicação, porque o logger raiz está em INFO e o `httpx` imprime a URL completa. Pré-existe
  desde a W05.
- ⚠️ **Nenhuma tela lê intraday** — backend-only, como a W13 e a W14.

---

## Marcos de infraestrutura de conhecimento

- **2026-08-17** — Sistema de memória persistente criado: `CLAUDE.md` na raiz + `docs/{memory,architecture,decisions,planning,history}/`, com 11 ADRs extraídos do código e do histórico de decisões.
