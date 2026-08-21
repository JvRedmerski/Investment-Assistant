# Current Project Status

> Camada 1 da memória: **onde o projeto está**, em uma página.
> Ledger detalhado task-a-task (histórico completo, notas de implementação, decisões datadas): [../PROJECT_STATUS.md](../PROJECT_STATUS.md).
> Última verificação contra o código: **2026-08-21**.

## Current Phase

**Wave 12 — AI Engine concluída** (2026-08-21), **3 de 3 tasks**. **13 de 33 waves do roadmap
concluídas** (W00–W12), mais as duas inseridas fora da ordem (PRICE e EVENTS). **A próxima é a
Wave 13 — Backtesting.**

✅ **"A IA não calcula" deixou de ser confiança e virou mecanismo.** O
[ADR-009](../decisions/ADR-009-quant-deterministic-ai-explains.md) decidiu isso em 2026-08-09 e
não disse *como* — não havia código de IA para dizer. Agora há, e são três mecanismos:

1. **Não há o que calcular.** O modelo recebe um **fact pack** — lista fechada e plana de valores
   já calculados, com rótulo, unidade, string renderizada e endpoint de origem. Sem série, sem
   componente, sem linha de banco. `facts.py` é a cintura estreita: tudo que o modelo verá passa
   por ali.
2. **Não há o que arredondar.** Arredondar é calcular, então quem arredonda é o backend, com o
   espelho exato de `frontend/src/lib/format.ts`. O texto e o painel citam a **mesma string**.
3. **O que sobrar é apontado.** Todo número do texto é confrontado com esse conjunto fechado, e o
   que não casar volta em `unverified_figures` — **reportado, nunca rejeitado**
   ([ADR-030](../decisions/ADR-030-fact-pack-and-the-hallucination-guard.md)).

Três perguntas têm explicação: *estou batendo o CDI?*, *por que o aporte vai para esses ativos?* e
*o que esse score está medindo?*.

🔴 **Nenhuma chamada real a modelo nenhum aconteceu, e por isso nenhum teste de regressão de parser
foi escrito.** A `GEMINI_API_KEY` é válida, mas a Gemini API está **desabilitada no projeto Google
Cloud dela** (HTTP 403 `SERVICE_DISABLED`, projeto `980912867288`); não há Ollama local. A omissão
é deliberada: um mock construído sobre suposição não verifica a suposição, reproduz ela — foi assim
que dois campos da Brapi passaram por 45 testes verdes na W06-003. **É a primeira coisa a fazer na
próxima sessão**; o procedimento está em [CURRENT_TASK.md](CURRENT_TASK.md).

⚠️ **`unverified_figures` ainda não tem quem o exiba.** A W12 é backend-only por decisão. Uma tela
que mostre a prosa e ignore a lista desfaz metade da garantia. Está em Future Work.

✅ **A W12 não adicionou nenhuma dependência — removeu uma.** `google-generativeai` estava
declarado desde a W00, nunca foi importado, nem estava instalado, e é o SDK que o Google
descontinuou. A IA fala REST pelo mesmo `RetryingJsonClient` de todas as outras integrações, que
ganhou `post_json` e `default_headers`
([ADR-029](../decisions/ADR-029-ai-provider-speaks-rest.md)).

✅ **O frontend deixou de ser scaffold.** Quatro telas — Dashboard, Carteira, Ativos e Ativo —
sobre rotas, react-query e um cliente tipado que **valida toda resposta com `zod`**. Nenhuma
aritmética no cliente (regra 73); ausência é desenhada como ausência e cobertura parcial vem
rotulada. Ver [../architecture/FRONTEND.md](../architecture/FRONTEND.md).

✅ **Existe valor de mercado** (W11-001) e existe a **série de evolução** (W11-002): patrimônio em
BRL com a linha de aporte por baixo, e o índice time-weighted recortado à janela que compartilha
com o benchmark.

🔴 **Duas correções que só a verificação contra o banco real encontraria**, ambas em código de
waves anteriores e ambas invisíveis para a suíte **porque os testes compartilhavam a premissa
errada**:

1. **O índice time-weighted misturava moedas.** Posições em `adjusted_close`, fluxos em preço
   negociado. Contra seis anos reais de PETR4 o índice deu **-3,88** — valor de cota não pode ser
   negativo. Todo fixture precificava o ativo ao preço negociado, que é o único caso em que as
   duas moedas coincidem.
2. **O comparativo media duas janelas.** Carteira de 4,7 anos contra CDI de quatro meses, com a
   subtração reportada como excesso: **+251,5 p.p.** contra os **+7,1 p.p.** reais.

⚠️ **O frontend não tem teste automatizado nenhum.** Os 14 schemas foram conferidos à mão contra
um backend real, e isso não se repete sozinho. Está em Future Work.

✅ **A carteira sabe para onde deveria ir, e o que fazer com o aporte para chegar lá.** A wave
inteira era uma pergunta que nem o roadmap §22 nem a regra 34 respondem: **de onde vem o
`target_weight`**.

⚠️ **A resposta óbvia foi medida e reprovada antes de virar código.** Alvo proporcional ao
`final_score` não converge, porque o score lê a carteira que o alvo deveria mirar: variando só
quanto a carteira detém de PETR4, de 0% a 20%, ele escorrega de **76,72 para 65,47** enquanto os
quatro pilares de mérito ficam constantes. O que cai é Diversificação. Um alvo feito desse número
**recua conforme a carteira se aproxima dele**. O alvo passou a sair do **mérito** — Quality,
Valuation, Growth, Risk — e a concentração virou **teto** em vez de termo
([ADR-027](../decisions/ADR-027-target-weight-comes-from-merit.md)).

⚠️ **`/rebalance` e `/rebalance-plan` podem discordar sobre o mesmo ativo, e os dois estão
certos.** A tabela mede a carteira de hoje; o plano mede a carteira que o aporte cria. Um papel
exatamente no alvo hoje **é comprado mesmo assim**, porque o aporte vai diluí-lo. Essa base foi
uma correção, não um desenho de primeira: o portão de elegibilidade lia o peso pré-aporte
enquanto todo o dimensionamento já rodava sobre a base pós-aporte, e **o teste contra o banco
real** pegou — PETR4 saiu de R$ 0 recusados para **R$ 140** alocados
([ADR-028](../decisions/ADR-028-rebalancing-is-cash-flow-only.md)).

**Nada do rebalanceamento vende**, e isso é decisão registrada, não omissão: todos os itens que a
regra 34 manda priorizar são de compra, e venda realiza IR numa carteira cuja tese é capitalizar.

✅ **A série de retorno total existe** (EVENTS-003). Era a trava de maior retorno do projeto e
estava reduzida a uma palavra: **magnitude**. Ela veio do **serviço aberto de eventos corporativos
da própria B3** — reais por ação num provento, fator num desdobramento, sem token e sem cota
([ADR-026](../decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md)).

Medido no banco real: **PETR4 com 1.495 de 1.495 pregões ajustados**, volatilidade 41,8% e
drawdown -63,4% com fundo em 2020-03-18 (a COVID). A pior sessão ajustada é **idêntica** à crua
(-29,7% em 2020-03-09), que é a prova de que nenhum evento vazou para a série. BBAS3 idem.
**ITUB4 fica corretamente truncada** em 2025-03-19 e a **MGLU3** em 2024-02-02 — por eventos que
ninguém dimensionou, que é o desenho funcionando, não uma falha.

✅ **Os 10 indicadores têm insumo real** (EVENTS-001). O `dy` era o último com fórmula e sem
fonte desde a W06-002; passou a vir da **DMPL da CVM** — 0,22 em 2024 e **0,70 em 2022** para a
PETR4, o *payout* do ano recorde e não erro de parsing.

✅ **A data e a natureza de todo evento societário são legíveis** (EVENTS-002), décadas atrás,
pelo **contador de distribuição** do papel e nunca pelo marcador de ex-
([ADR-025](../decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md)).

⚠️ **A regra que decide se `adjusted_close` pode existir vale ser sabida antes de mexer aqui**:
toda sessão que o contador da B3 marcou ex precisa de uma ação dimensionada. Não é o serviço de
eventos que julga isso, porque ele **omite** — a ITUB4 foi ex em 2025-03-18 com degrau de -8,60%
e o serviço não reporta nada ali. A única exceção é o marcador `ATZ`, medido em 151 incrementos
com degrau mediano de 1,0028; sem essa exceção a PETR4 teria **28** pregões ajustáveis em vez de
1.495, e a decisão de abri-la foi tomada pelo dono do projeto, com os números à vista.

✅ **O bloqueio de fundamentals foi contornado em 2026-08-18** ([ADR-020](../decisions/ADR-020-cvm-primary-fundamentals-source.md)). A fonte primária passou a ser os **dados abertos da CVM** — o arquivo entregue ao regulador, aberto, sem token, sem cota e com mais histórico do que o fornecedor dava. A **Brapi continua no projeto** fazendo a ponte que a CVM não faz: seus arquivos não têm coluna de ticker, e o `summaryProfile` (ainda gratuito) traz o CNPJ.

⚠️ **Restrição externa que permanece, mas deixou de ser estruturante**: o `range` da Brapi
continua limitado a `3mo` e relativo a hoje. Desde a wave PRICE isso **não trava mais o
histórico**, que vem da B3 de graça e cobre décadas. A Brapi segue necessária para **cotação ao
vivo**; o `adjusted_close` deixou de depender dela para papel com eventos completos.

CDI e IPCA **não** são afetados: vêm do Banco Central (SGS), aberto e sem cota.

## Overall Status

| | |
|---|---|
| **Completed** | W00 Foundation · W01 Scaffold · W02 Database · W03 Auth · W04 Portfolio · W05 Market Data · W06 Fundamental Data · W07 Quant Engine · W08 Benchmark Engine · W09 Recommendation Engine · W10 Rebalancing · W11 Dashboard · **W12 AI Engine** · **PRICE Open Price History** (inserida) · **EVENTS Corporate Actions & Distributions** (inserida) |
| **In Progress** | — nenhuma. Próxima: **Wave 13 — Backtesting**; ver [CURRENT_TASK.md](CURRENT_TASK.md) |
| **Blocked** | — nenhuma. ⚠️ Mas os dois providers de IA da W12 são código **não verificado** até que uma chamada real aconteça |

Baseline atual: `pytest` → **944 passed** (backend/.venv), verificado em 2026-08-21. Frontend: `npm run build` e `npm run lint` limpos. `ruff check .` e `black --check .` limpos no repositório inteiro; `alembic check` sem drift na última execução (2026-08-19, com o banco no ar); `npm run lint` e `npm run build` funcionando.

## Completed Work (nível wave)

- **W00–W01** — Repositório, `.env.example`, `docker-compose.yml` (postgres+backend+frontend), scaffold FastAPI com `/health` e `/ready`, scaffold React+TS+Vite+Tailwind, Dockerfiles, pytest rodando.
- **W02** — 13 models SQLAlchemy 2.0 + migration `001_initial_schema`. Correção posterior: `002_numeric_money_columns` (`Float` → `NUMERIC(18,6)`/`Decimal` em `transactions` e `asset_prices`).
- **W03** — bcrypt + PyJWT em `core/security.py`; `register` / `login` / `refresh` / `me`; `get_current_user`; envelope de erro global `{"error":{"code","message"}}`.
- **W04** — CRUD de assets e portfolios; ledger de transações com guarda `INSUFFICIENT_POSITION`; motor de posições determinístico (custo médio móvel) derivado 100% do ledger; endpoint `/positions`.
- **W05** — `MarketDataProvider` (abstrato) + `BrapiProvider` (httpx, timeout/retry limitado/throttle) + factory; `sync_daily_history` idempotente (nunca sobrescreve data já armazenada); `validate_daily_bars` (rejeita preço não-positivo, volume negativo, OHLC inconsistente, data duplicada; avisa sobre fora de ordem e variação >50%); read-path lê só do banco.

- **W06-001** — `FundamentalsProvider` + `BrapiFundamentalsProvider` + factory; `sync_annual_statements` idempotente; `validate_financial_statements`; endpoints de sync/leitura; migration `003` (`fundamentals` em `NUMERIC(24,4)`). Extraiu também o transporte HTTP compartilhado (`RetryingJsonClient`), agora usado pelas duas integrações.

- **W06-002** — `compute_indicators`: função pura com as **10 fórmulas** implementadas e testadas; `compute_and_store_indicators` idempotente; seleção de preço sem look-ahead (`_price_on_or_before`); endpoints `POST /indicators/compute` (não chama provedor externo) e `GET /indicators`. Política de dado faltante em [ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md).

- **W06-003** — **parsers validados contra a API real da Brapi** (1 requisição). Market data estava correto; fundamentals tinha dois campos errados (`equity`, `debt`) que deixavam `roe` silenciosamente `None`. ROIC destravado com alíquota efetiva derivada por período; migration `004`; política de recomputação ([ADR-015](../decisions/ADR-015-indicator-recomputation.md)).

- **W07** (2026-08-18) — `app/quant/returns.py` (`simple_return`, `period_returns` diário/semanal ISO/mensal/trimestral/anual, `total_return`, `ytd_return`, `cagr`) e `app/quant/risk.py` (`standard_deviation`, `downside_deviation`, `volatility`, `max_drawdown`, `beta`, `sharpe`, `sortino`). Puras, sem I/O, **inteiramente em `Decimal` — `numpy` não foi importado**. 101 testes com valores calculados à mão. Anualização (365 p/ retorno, 252 p/ dispersão) e tipo numérico em [ADR-017](../decisions/ADR-017-annualisation-and-numeric-type.md).

- **W06-004** (manutenção, 2026-08-18) — PostgreSQL real no ar; migrations `001`→`004` aplicadas de fato, após corrigir um `AttributeError` que impedia o Alembic de rodar. Confirmado que **não havia banco nem dado algum** — a pendência de recomputar indicadores era hipotética. Parser de market data validado contra FII/ETF/banco reais. Fundamentals bloqueado por mudança de plano da Brapi. Custo: 5 requisições.

- **W08-001** (2026-08-18) — Ingestão de benchmarks. `BenchmarkProvider` abstrato + `BcbSgsProvider` (Banco Central/SGS: aberto, sem token, sem cota) + `BrapiIndexProvider` (delega ao `MarketDataProvider`, **sem parser próprio** — verificado ao vivo, a Brapi devolve `^BVSP` na mesma forma de uma ação) + factory. Catálogo em **código** (CDI, SELIC, IPCA, IBOV), não em tabela. `benchmark_values` `NUMERIC(24,12)` + migration `005` aplicada em Postgres real. `INCOMPLETE_PERIOD`: observação de período não terminado é rejeitada, não gravada. Ingestão idempotente.

- **W08-002** (2026-08-18) — Comparativo. `benchmarks/series.py` (taxa → índice acumulado; taxa anualizada da janela), `portfolio/performance.py` (índice **time-weighted** da carteira, em formato `PricePoint`), `benchmarks/comparison.py` (puro, só orquestra o `app.quant`). Endpoints `GET /assets/{ticker}/benchmarks/{code}` e `GET /portfolios/{id}/benchmarks/{code}`. **`beta`, `sharpe` e `sortino` deixaram de retornar `None`.** Decisões em [ADR-018](../decisions/ADR-018-benchmark-representation.md) e [ADR-019](../decisions/ADR-019-portfolio-return-is-time-weighted.md).

- **W09-001** (2026-08-18) — Motor de sub-scores. Cinco pilares (Quality, Valuation, Growth, Risk, Diversification) em `app/domain/recommendations/scoring.py`, puro e determinístico. **Ausência é resposta de primeira classe**: pilar sem dado é `None`, nunca zero nem 50 "neutro", e fica de fora da média. O score final renormaliza sobre o que existe e **reporta `coverage`** — dois scores com cobertura diferente não são comparáveis. Fórmula versionada, todo limiar é constante nomeada (§30). Score é **relativo à carteira** (§31). `GET /portfolios/{id}/scores`.

- **W09-002** (2026-08-18) — **Fonte CVM + ponte Brapi**. `CvmFundamentalsProvider` lê os DFP de dados.cvm.gov.br (ZIP por exercício, cache em disco); `BrapiCnpjResolver` + `StoredCnpjResolver` resolvem ticker→CNPJ e gravam em `assets.cnpj` (migration `006`); `CompositeFundamentalsProvider` põe a CVM na frente e a Brapi atrás. **Período inteiro vem de uma fonte só** — campos nunca são misturados. Validado ao vivo com 6 exercícios da PETR4. Decisões em [ADR-020](../decisions/ADR-020-cvm-primary-fundamentals-source.md).

- **W09-003** (2026-08-19) — **Ações em circulação por exercício**, do `composicao_capital` da CVM: integralizadas menos tesouraria. Destravou `pe` e `pb`, o último pilar ausente. O arquivo **não declara escala** e cerca de um terço dos declarantes escreve a contagem em milhares — a própria Petrobras alterna entre 2020 e 2021 — então a unidade é **reconciliada contra o LPA do próprio arquivo** antes de gravar, e fica ausente quando nenhuma unidade fecha. Sem isso o P/L sairia mil vezes menor e clamparia em **100** na escala invertida. LPA derivado bate com o publicado: PETR4 R$ 2,84, VALE3 7,40 contra 7,39, MGLU3 0,61.

- **W09-004** (2026-08-19) — **Alocação do aporte mensal**. `app/domain/recommendations/allocation.py`, puro e determinístico, e `GET /portfolios/{id}/contribution-plan`. Ordena por **faixa de cobertura antes do score**, porque ordenar por `final_score` erra numa direção só: o pilar que sobrevive a toda lacuna é Diversification (~100 para o que a carteira não tem), então quem tem menos dado ganharia sistematicamente. Os tetos de 20%/40% são **as próprias escalas do score**, não uma segunda cópia. Todo limite é configurável (§32) e a política volta na resposta. **Nada é gravado** — o plano é derivado como as posições. Decisões em [ADR-021](../decisions/ADR-021-allocation-ranks-by-coverage-tier.md).

- **PRICE-001** (2026-08-19) — **Histórico de preços aberto da B3**. `B3CotahistProvider` +
  `CotahistArchive` lêem a série COTAHIST (um ZIP por ano civil, ~79 MB, posição fixa, 245 bytes
  por registro). Implementa a nova interface estreita `DailyHistoryProvider`, **não**
  `MarketDataProvider`: arquivo de fim de dia não cota. Validado contra o arquivo real de 2024
  antes de qualquer fixture, e duas descobertas mudaram o código. (a) **`FATCOT` é fator de
  cotação de verdade** — FNOR11 é cotado por 1.000 ações e SMLL11 por 10; os preços são divididos
  por ele e o resultado **reconcilia contra o volume financeiro do próprio registro**
  (`VOLTOT/QUATOT`), técnica idêntica à do LPA na W09-003. (b) **`adjusted_close` é `None`,
  nunca copiado do `close`.** O arquivo é destilado no download (só mercado à vista, gzip:
  14,9 MB de 79 MB) porque 89% dele são opções que nada aqui lê.

- **PRICE-002** (2026-08-19) — **A ausência de ajuste virou dado, não erro**
  ([ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md), emenda ao
  ADR-016). `asset_prices.adjusted_close` passou a aceitar `NULL` (migration `010`), e a
  semântica da ausência pertence à **fonte**: `reports_adjusted_close` distingue "o fornecedor
  ainda não publicou" (rejeita, ADR-016 intacto) de "esta fonte nunca publica" (grava com
  `NULL`). A objeção que o ADR-016 levantou contra a coluna nula — espalhar tratamento de nulo
  por todo consumidor — foi **respondida, não ignorada**: `app/domain/market_data/series.py` é o
  **ponto único** que constrói série de retorno, e os três lugares que faziam isso à mão passam
  por ele. Cada linha agora também grava de qual fonte veio.

- **PRICE-003** (2026-08-19) — **`POST /assets/{ticker}/prices/backfill`**, e a validação que a
  wave existia para produzir. Backfill real de 2020–2025 da PETR4: **1.495 pregões, 0 rejeitados**.
  `pe` e `pb` eram `None` nos 6 exercícios e passaram a ser reais — P/L de **12,74** em 2024
  (LPA R$ 2,84 sobre fechamento de R$ 36,19) e **1,70** em 2022, que é o que o mercado de fato
  viu no ano dos lucros recordes. São fechamentos **não ajustados**, e é exatamente o certo aqui:
  múltiplo *point-in-time* casa o preço cotado então com o lucro reportado então.

- **EVENTS-001** (2026-08-19) — **Distribuições por exercício, da DMPL da CVM**. `5.04.06`
  (dividendos) + `5.04.07` (JCP), somados porque declarantes dividem diferentemente e vários
  reportam tudo sob um código só. Três detalhes decidem se o número está certo, e os três foram
  conferidos contra o arquivo real: **a coluna** (toda conta da DMPL se repete uma vez por coluna
  de patrimônio, e só `Patrimônio Líquido` é lida — a irmã `Consolidado` inclui o pago a
  não-controladores, R$ 302 mi na PETR4 em 2024), **o sinal** (distribuição é débito, a peça
  escreve negativo, a grandeza é o módulo) e **o que fica de fora** (`5.04.11`, *dividendos
  prescritos*, é estorno de período anterior, não distribuição negativa deste). Coluna
  `fundamentals.dividends_paid`, migration `011`. **Fechou o `dy`** — os 10 indicadores passaram
  a ter insumo real. A armadilha que a task expôs vale mais que a coluna: período gravado é
  congelado com os campos que o código conhecia então (ADR-013), então `?refill=true` preenche
  coluna **`NULL`** e só ela ([ADR-024](../decisions/ADR-024-refill-fills-null-columns.md)).

- **EVENTS-002** (2026-08-19) — **Data e natureza do evento societário, ditas pela própria
  bolsa**. `CorporateEventProvider` — terceira interface, ortogonal às duas de preço — e
  `get_corporate_events` no `B3CotahistProvider`, lendo o **mesmo arquivo já baixado**. O sinal é
  o **`DISMES`**, contador de distribuição do papel, e **não** o marcador do `ESPECI`: medido no
  arquivo de 2024, o marcador persiste ~8 pregões e decai (`EDJ` → `EJ`, 132 sessões parecendo
  evento novo), e a BBAS3 mostra **duas** distribuições sob marcador imóvel (contador 323, 323,
  324). Conferido no sentido inverso em 2024 inteiro — 2.230 papéis, 7.312 incrementos, nunca
  decrescendo, só 13 letras sem incremento e **nenhuma movendo preço em 25% ou mais**. Duas
  letras mudaram de nome por evidência: `EB` carrega desdobramento **e** bonificação
  (`BONUS_OR_SPLIT`), `R` cai em fundo e em ação ao lado de outro provento
  (`OTHER_DISTRIBUTION`). Sem evidência → `UNCLASSIFIED`, e o `ESPECI` cru fica verbatim.
  **Sem fator e sem valor, de propósito**
  ([ADR-025](../decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md)).

Detalhe por task: [../history/COMPLETED_TASKS.md](../history/COMPLETED_TASKS.md).

- **W12** — **AI Engine**. `AIProvider` + `GeminiProvider` + `OllamaProvider` + `DisabledAIProvider`
  sobre o transporte compartilhado, que ganhou `post_json` e `default_headers`
  ([ADR-029](../decisions/ADR-029-ai-provider-speaks-rest.md)); `app/domain/ai/` com fact pack,
  formatador espelhado no frontend, prompts versionados em `prompts/*_v1.txt` (regra 43) e o guard
  que confronta cada número do texto contra o conjunto fechado de fatos
  ([ADR-030](../decisions/ADR-030-fact-pack-and-the-hallucination-guard.md)); três rotas
  `POST /portfolios/{id}/explain/*`. `google-generativeai` **removido**. Nada é gravado, logo
  nenhuma migration. ⚠️ Providers **não verificados** contra resposta real.

## Current Work

**Nenhuma.** A Wave 12 fechou em 2026-08-21 com as três tasks entregues e nada de código pela
metade. Ver [CURRENT_TASK.md](CURRENT_TASK.md).

## Next Recommended Step

1. **Fechar a verificação da W12-001, e é curto.** Habilitar a Gemini API no projeto Google
   Cloud da chave, fazer **uma** chamada real, conferir o formato campo a campo e escrever o
   teste de regressão. Enquanto isso não acontece, `gemini.py` e `ollama.py` são código não
   verificado — e a W06-003 já mostrou o que isso custa quando passa despercebido.
2. **Wave 13 — Backtesting**, de volta à ordem do roadmap. Ela precisa de **retorno total**, e
   a série ajustada existe desde a EVENTS-003 — onde o ajuste é completo, e truncada onde não é
   ([ADR-026](../decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md)).
3. **Antes de confiar no Risco de um ativo novo, rode o sync de ações societárias.** Um papel só
   com preço bruto continua sem `adjusted_close`, e portanto sem risco — o que é o estado normal
   que o motor de score já trata, não um defeito. O comando é
   `POST /assets/{ticker}/corporate-actions/sync` **depois** do `prices/backfill`.

Ver [CURRENT_TASK.md](CURRENT_TASK.md).

## Known Issues

Problemas reais, verificados no código. **Última varredura: 2026-08-19**, quando tudo que tinha
correção possível foi corrigido — o que sobrou está abaixo, cada um com o motivo de continuar
aberto.

> 🔴 **A restrição mais dura, e ela é externa:** o **plano gratuito da Brapi limita o `range` a
> `3mo`** (HTTP 400 `INVALID_RANGE`) e o `range` é **relativo a hoje**, sem parâmetro de data
> inicial — **não há como paginar histórico**. ~63 pregões é o teto absoluto. Continua atingindo
> `beta` (janela estatisticamente pobre), `pe`/`pb` no banco real e o backtesting da W13.
> Não afeta CDI/IPCA/Selic (fonte BCB, aberta e sem cota).
>
> ✅ **Os defeitos de código que essa restrição escondia foram corrigidos em 2026-08-19**, e eram
> dois. (a) `_brapi_range_for` mapeava janelas > 90 dias para `6mo`/`1y`/`max`, todos recusados —
> a requisição era gasta para ouvir não, e o erro chegava como falha genérica de provedor. Agora o
> teto é configurável (`BRAPI_MAX_RANGE`, default `3mo`) e a recusa é local, com
> `HistoryWindowTooLargeError` → **HTTP 400 `MARKET_DATA_WINDOW_TOO_LARGE`** dizendo quanto faltou.
> (b) Mais silencioso e pior: o bucket era escolhido pelo **tamanho da janela** (`end - start`),
> mas todo range da Brapi **termina em hoje** — pedir duas semanas do trimestre passado mandava
> `range=5d`, que não contém um único pregão do intervalo pedido, e a resposta vinha **vazia, sem
> erro nenhum**. O bucket agora é medido de `start` até hoje.

### Abertos

1. ✅ ~~**Ingestão de proventos: metade feita**~~ — **fechado em 2026-08-20** (EVENTS-003).
   O provento **por pagamento, com data e valor**, passou a vir do serviço aberto de eventos da
   B3, persistido em `corporate_actions` (migration `012`) com endpoint de sync e de leitura
   ([ADR-026](../decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md)).
   O agregado por exercício da DMPL (EVENTS-001) continua onde estava, servindo o `dy` — são
   perguntas diferentes e nenhuma substitui a outra.
   - ⚠️ **Subscrição continua sem dimensionar.** O serviço a publica numa lista própria
     (`subscriptions`), com percentual e preço de exercício, e dimensioná-la exige um **modelo do
     valor do direito**, não uma medição. Por ora ela trunca a série — foi o que cortou a MGLU3
     em 2024-02-01. É task de wave, não remendo.
   - ⚠️ **O `CorporateEvent` (data + natureza) segue lido e não persistido**, e agora é de
     propósito: ele é varrido do arquivo já em cache a cada sync para servir de **verificação de
     completude**, e gravá-lo criaria uma segunda cópia do que o arquivo já é.
2. ✅ ~~**1 dos 10 indicadores permanece `None`**~~ — **fechado em 2026-08-19** (EVENTS-001).
   O `dy` era o último e passou a ter fonte: distribuições da DMPL sobre a contagem de ações do
   mesmo exercício, sobre o preço da data de referência. **Nenhum pilar de score consome `dy`**
   hoje, então isso não mexeu na cobertura — o valor está no conjunto de indicadores ficar
   completo, não no score.
   - ✅ **`pe`/`pb` deixaram de ser hipotéticos e existem no banco real** desde a wave PRICE
     (2026-08-19): 6 exercícios da PETR4, P/L de 12,74 e P/VP de 1,27 em 2024. Faltava **preço
     histórico**, e ele agora vem do COTAHIST.
   - *Registro:* `ebitda_margin`/`debt_ebitda` destravados em 2026-08-18 (W09-002, EBITDA
     derivado de verdade em vez da cópia de `ebit`); `pe`/`pb` no código em 2026-08-19 (W09-003)
     e **no banco** no mesmo dia (PRICE-003); `dy` em 2026-08-19 (EVENTS-001). O caminho foi de
     **5 `None` → 1 → nenhum**.

2b. ✅ ~~**O pilar de Risco continua ausente**~~ — **fechado em 2026-08-20** (EVENTS-003).
   A série de retorno total existe, e com ela `volatility`, `max_drawdown`, `beta` e `sharpe`
   têm insumo real. Medido no banco: **PETR4 com 1.495 de 1.495 pregões ajustados**,
   volatilidade 41,8%, drawdown -63,4% com fundo em 2020-03-18; **a pior sessão ajustada é a
   mesma da série crua**, o que prova que nenhum evento vazou. O grupamento 1:10 da MGLU3
   aparece como 13,5%, não como os +896% que o
   [ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md) descreve.
   - ⚠️ **Continua ausente para papel cujos eventos ninguém dimensionou**, e isso é o desenho:
     ITUB4 tem 198 de 1.495 pregões ajustáveis (a cisão de 2021 e um `EB` de 2025 que a B3 não
     reporta) e MGLU3 tem 478 (a subscrição de 2024). A lacuna volta **nomeada e datada** em
     `unaccounted` na resposta do sync, em vez de virar "esse ativo não tem risco, sabe-se lá
     por quê".
   - ⚠️ **Uma correção tardia da B3 sobre data já ajustada não é reaplicada**: o preenchimento
     só toca coluna nula (ADR-024). Recomputar exige limpar `adjusted_close` antes, e isso é
     operação manual deliberada.
3. **Reexpressões (restatements) de demonstrativos são invisíveis**: o primeiro valor gravado
   para um `reference_date` nunca é substituído. Corrigir exige schema versionado por período —
   mudança de desenho com ADR, não correção pontual. (Indicadores derivados, ao contrário, podem
   ser recomputados — [ADR-015](../decisions/ADR-015-indicator-recomputation.md).)
4. **Demonstrativos trimestrais não são ingeridos** — o parser filtra `type == "yearly"` porque
   `fundamentals` não tem coluna de período para distingui-los de um exercício anual com a mesma
   data-fim. É decisão registrada, não esquecimento
   ([ADR-013](../decisions/ADR-013-fundamentals-point-in-time.md)).
5. **Throttle de requisições desligado por padrão** (`*_MIN_REQUEST_INTERVAL_SECONDS = 0.0`).
   **Mantido de propósito**: o default serve uso local, onde espaçar chamadas só torna o
   desenvolvimento lento. O que era defeito de verdade — as chaves nem constarem do
   `.env.example`, apesar de a orientação ser "defina antes de ingestão em lote" — foi corrigido
   em 2026-08-19. A Brapi tem **cota mensal** no plano gratuito.
6. **Plano gratuito aceita no máximo 1 ativo por requisição.** Externo. Não há batching —
   ingestão em lote custa 1 requisição por ticker. Dimensionar a cota mensal por aí.
7. **Colunas monetárias ainda em `Float`**, e as duas que sobraram **não têm consumidor**:
   `intraday_prices` OHLC (a wave que as usa é a W15) e
   `portfolio_snapshots.total_value`/`cash_value` (W11). Converter agora seria migration sem uso.
   ✅ `investor_profiles.monthly_contribution` — a que **tinha** consumidor — virou
   `NUMERIC(18,6)` em 2026-08-19 (migration `008`), e `monthly_contribution_for` deixou de lavar
   o valor por `str`.
8. **Aproximação conhecida no `performance_index`**: um fluxo que cai numa data sem preço
   armazenado é neutralizado na próxima data valorável. Só ocorre quando a data não pode ser
   valorada; quando pode — o caso normal — não há distorção. As alternativas seriam fabricar um
   fechamento (regra 44), esconder movimento real, ou descartar o histórico após uma lacuna.
   **A correção verdadeira é a montante**: ingerir os preços faltantes.
   - ✅ **A EVENTS-003 resolveu a dependência que a PRICE não tinha resolvido.** O índice da
     carteira valoriza posição em `adjusted_close`
     ([ADR-019](../decisions/ADR-019-portfolio-return-is-time-weighted.md)), e as 1.495 linhas do
     COTAHIST estavam com a coluna nula; agora elas são preenchidas para papel com eventos
     completos. Onde os eventos **não** estão completos a data continua não valorável, e o
     `performance_index` segue neutralizando — a aproximação acima continua sendo a descrição
     correta desse caso.
9. **Bancos e seguradoras usam plano de contas diferente no DFP.** `3.01` do Banco do Brasil é
   "Receitas de Intermediação Financeira", não receita de vendas, e `2.01.04` pode não existir.
   O mapeamento aceita o que houver e deixa `None` no resto. Fechar isso exige **conferir contra
   demonstrativo real de instituição financeira** — trabalho de validação com dado ao vivo, não
   alteração de código. Validado até aqui contra PETR4 e VALE3 (industriais).
10. **Cobertura da CVM é só companhia aberta brasileira.** FII, ETF e BDR não arquivam DFP e
    nunca arquivarão — para eles os pilares fundamentalistas ficam permanentemente ausentes, o
    que o motor de score já trata como estado normal.
11. **Ativo sem setor cadastrado não recebe aporte** (`require_sector`, padrão ligado).
    **Deliberado**: um teto de setor que não pode ser avaliado não é um teto. O conserto é
    preencher o campo no ativo, e a recusa (`SECTOR_UNKNOWN`) diz isso. Configurável por
    requisição.
12. **A carteira não tem caixa modelado, e a alocação depende disso.** A base dos pesos é
    `custo das posições + aporte`; o que os tetos não deixarem colocar volta como `unallocated`
    e fica implicitamente em caixa. `portfolio_snapshots.cash_value` existe e não é usado.
    Modelar caixa é desenho de carteira — território da **W11**, não remendo.
13. **A tabela `recommendations` continua sem uso, e por decisão**
    ([ADR-021](../decisions/ADR-021-allocation-ranks-by-coverage-tier.md)): o plano é derivado a
    cada leitura, como as posições. Ela declara `suggested_amount`/`target_weight` como `Float`,
    o que a regra 17 proíbe para dinheiro — a migration vem junto com a necessidade real de
    histórico, não antes.
14. **Um exercício já em cache nunca é rebaixado.** A CVM republica um ano conforme empresas
    corrigem; pegar a correção exige apagar o ZIP em `var/cvm/`. Deliberado — nenhum caminho de
    leitura dispara download sozinho.

### Corrigidos em 2026-08-19

Ficam registrados porque o motivo de terem existido ensina alguma coisa.

- ✅ **`get_quote()` implementado e não exposto** — existia no provider, testado, sem endpoint
  algum consumindo. Agora **`GET /assets/{ticker}/quote`**. Não grava nada: cotação é um momento
  e `asset_prices` guarda pregão fechado (mesmo raciocínio do
  [ADR-016](../decisions/ADR-016-unadjusted-bars-are-not-stored.md)). Exige o ativo cadastrado,
  para que um typo não gaste requisição de uma cota mensal.
- ✅ **`PriceSyncRequest` documentava que `end` não podia ser futura e não verificava.** Agora
  verifica, em UTC explícito (regra 18).
- ✅ **`env_file=".env"` era relativo ao cwd** — rodando de `backend/`, o `.env` da raiz não era
  lido e **`BRAPI_TOKEN` ficava vazio em silêncio**. Ancorado ao arquivo, não ao processo; um
  `.env` local ainda tem precedência.
- ✅ **`alembic check` falhava por drift** (a migration `001` criou `UniqueConstraint` *e* índice
  único para `assets.ticker`/`users.email`; o model declara só o índice). A migration `009`
  removeu a duplicata: **`alembic check` passa** e volta a servir de guarda de drift em CI.
  Unicidade intacta — verificada com `INSERT` duplicado real, rejeitado por `ix_assets_ticker`.
- ✅ **Lint pré-existente no backend** (22 findings desde a W02, incluindo
  `app/data/models/__init__.py`): zerado. `ruff check .` e `black --check .` limpos no
  repositório inteiro.
- ✅ **`npm run lint` quebrado** desde a W01 — o script chamava `eslint`, ausente das
  `devDependencies` e sem arquivo de configuração. Agora roda (flat config, ESLint 10 +
  typescript-eslint + react-hooks) e **achou um import morto no primeiro uso**.
- ✅ **`npm run build` também estava quebrado, e não constava desta lista** — `tsc` falhava em
  `React` não usado (o transform `react-jsx` não o exige) e em `import.meta.env` sem os tipos do
  `vite/client`. Descoberto ao validar o item anterior.
- ✅ **Nenhum dos dois Dockerfiles tinha `.dockerignore`, e o `COPY . .` copiava o build do
  host para dentro da imagem.** No frontend isso **quebrava a imagem**: o `node_modules` do
  Windows sobrescrevia o que o `npm ci` tinha instalado, e o `eslint` do container tentava
  executar `node.exe`. Era latente até esta sessão — antes do `npm install` a pasta não
  existia no host. No backend era peso morto: `.venv` (virtualenv de outra plataforma) e
  `var/cvm/` (~13 MB por exercício de cache da CVM) iam para dentro da camada. Ambos com
  `.dockerignore` agora, e as duas imagens reconstruídas e testadas.
- ✅ **`frontend/Dockerfile` em `node:18-alpine` com `npm install`.** O Node 18 saiu de
  suporte em abril de 2025 e não satisfaz o `engines` do ESLint 10 — a imagem instalaria o
  linter com aviso e não conseguiria rodá-lo. Agora `node:20-alpine` e **`npm ci`**, que
  instala a árvore exata do `package-lock.json` em vez de reresolver os `^` a cada build.
  Verificado: `npm run lint` roda **dentro** da imagem.

## Inconsistências documentação × código

✅ **Zeradas em 2026-08-19.** A regra é a do CLAUDE.md §3 — o código é a fonte de verdade —
então em todos os casos foi a **documentação** que mudou; nenhuma linha de código foi escrita
para satisfazer um documento.

| Documentado em | Realidade | O que foi feito |
|---|---|---|
| AGENTS.md §6: `PROJECT_STATUS.md` e `CHANGELOG.md` na raiz | Status está em `docs/PROJECT_STATUS.md` (ledger) e `docs/memory/PROJECT_STATUS.md` (uma página); `CHANGELOG.md` não existe | Árvore da §6 reescrita para a estrutura real; §94, §127, §131 e o Wave Execution Protocol passaram a citar os caminhos certos. `CHANGELOG.md` sai da árvore com nota: o histórico é `docs/history/COMPLETED_TASKS.md` + o ledger |
| AGENTS.md §6: `backend/app/data/repositories/` | Não existe e **não está previsto** — rotas recebem a `Session` e os services a consomem direto (ADR-011) | Removido da árvore, com a ausência declarada deliberada e link para o ADR-011. §11 deixou de listar `repository` entre as camadas preferidas. `docs/architecture/BACKEND.md` deixou de classificá-lo como "previsto, wave futura" |
| AGENTS.md §6: `backend/tests/{unit,integration,regression}/` | `tests/` é plano, um `test_<área>.py` por área | Árvore corrigida; §67 agora diz que as categorias são conceituais, não diretórios |
| AGENTS.md §6/§93: `docs/architecture.md`, `database.md`, `api.md`, `quant-engine.md`, … | Substituídos por `docs/architecture/*.md`, `docs/decisions/`, `docs/planning/`, `docs/history/` e `docs/memory/` | Lista da §93 reescrita com os arquivos que existem, e registrado que os documentos por engine nunca foram criados — o conteúdo equivalente está no `BACKEND.md` e nos ADRs |
| AGENTS.md Wave Execution Protocol: `docs/waves/WAVE-XX-*.md` | `docs/waves/` não existe; as waves vivem em `docs/roadmap.md` e no ledger | Passo 3 do protocolo reescrito; "atualizar o arquivo da wave" virou "atualizar `docs/history/COMPLETED_TASKS.md`" |
| AGENTS.md §5.1 / README: React Router, TanStack Query, Zod, Recharts como stack | Instalados no `package.json`, nenhum importado — o frontend é uma página estática única | §5.1 separa "em uso hoje" de "declarado e não importado, entra na W11"; README idem, incluindo `numpy`/`pandas`/`scipy`/`scikit-learn`/`google-generativeai` no backend |
| README: "Frontend 🟢 COMPLETED" | Só existe uma landing page de status; sem rotas, sem estado, sem telas de produto | O rótulo já não estava no README, mas havia migrado para `docs/PROJECT_STATUS.md` — lá o frontend virou **🟡 SCAFFOLD** com o motivo escrito. README ganhou uma seção **Estado atual** com as 10 waves concluídas e o que não existe |
| `.env.example`: `ACCESS_TOKEN_EXPIRE_MINUTES=115200` (80 dias) | Default do código é 8 dias (`core/config.py`, `60*24*8 = 11520`) | Corrigido para `11520`, com o cálculo no comentário |

Encontradas **durante** esta varredura e corrigidas junto:

| Documentado em | Realidade | O que foi feito |
|---|---|---|
| CLAUDE.md §4: "baseline atual: 205 passed" | `pytest -q` → **596 passed** | Baseline atualizado |
| README: "CI/CD: GitHub Actions" | `.github/` não existe; lint e testes rodam localmente | Registrado como não existente |
| README: diagrama com "Quant Engine (Pandas/NumPy/TA)" | O Quant Engine é `Decimal` puro; NumPy foi **revogado**, não adiado (adendo ao ADR-017) | Diagrama e stack corrigidos, com link para o ADR |
| `docs/PROJECT_STATUS.md`: "Quant Engine: NumPy + Pandas + SciPy (Wave 07) ⚪ NOT_STARTED" | W07 concluída em 2026-08-18, e sem NumPy | Architecture Status reescrito, incluindo Fundamentals, Benchmark e Recommendation Engine, que faltavam |
| `.env.example` cobre só até a Wave 05 | O `Settings` tem toda a configuração de fundamentals, CVM e benchmarks — inclusive os dois `*_MIN_REQUEST_INTERVAL_SECONDS` que a Known Issue nº 13 manda ajustar antes de ingestão em lote | Todas as chaves do `core/config.py` documentadas no `.env.example`, agrupadas por wave |
| README: links `file:///C:/Users/joao/…` | Absolutos para uma máquina só | Trocados por caminhos relativos |
| Esta própria página: "schema `005`" | `backend/migrations/versions/` vai até `007_shares_outstanding` | Corrigido em *Important Context*, junto com o dado que existe no banco |
| `docs/architecture/FRONTEND.md`: "o README marca o frontend como 🟢 COMPLETED" | O README já não marcava | Aviso reescrito para descrever o estado, não o rótulo de outro documento |
| AGENTS.md §5.1: GitHub Actions na *Infrastructure*, `AIProvider` na *AI* | `.github/` não existe (é a W26) e não há implementação de IA (é a W12) | Ambos movidos para "previsto e ainda inexistente", com a wave nomeada |

## Important Context

- **Ambiente**: Windows + PowerShell. Virtualenv em `backend/.venv` — invoque como `.venv\Scripts\python.exe -m pytest`. **Docker desligado em 2026-08-20** (`docker compose up -d postgres` para religar); quando no ar, o schema é `011` (migrations `001`…`011_dividends_paid`), com dado real: benchmarks (CDI, IPCA, IBOV), 6 exercícios de demonstrativos da PETR4 pela CVM **com `pe`/`pb` e `dy` calculados** (os seis preenchidos por `?refill=true`), e **`asset_prices` com 1.495 pregões da PETR4** (2020-01-02 a 2025-12-30, `source='b3_cotahist'`, `adjusted_close` NULL em todas). As contagens vêm dos registros das tasks — não foram reconsultadas com o banco desligado.
- **Há rede de saída** neste ambiente (a Wave 05 foi implementada sem ela — daí a lacuna nº 1, já resolvida). A W08 chamou BCB e Brapi ao vivo; a wave PRICE baixou arquivos reais da B3. **Três das quatro fontes são abertas e sem cota** (BCB/SGS, CVM, B3); só a Brapi tem cota mensal e aceita 1 ativo por requisição.
- **Cache do COTAHIST em `backend/var/b3/`** (gitignored), ~15 MB por ano já destilado, com 2020–2025 baixados. Um ano frio custa ~79 MB de download e ~90 s.
- **Testes rodam contra SQLite in-memory compartilhado** (`tests/conftest.py`), com `app.dependency_overrides` para `get_db`, `get_market_data_provider` e `get_benchmark_provider`. **Nenhum teste toca rede ou Postgres** — as chamadas ao vivo da W08 foram feitas em scripts de validação avulsos, não na suíte.
- **A regra mais estruturante do projeto**: posições nunca são armazenadas — sempre derivadas do ledger de transações (AGENTS.md §16, ADR-002). Não crie tabela de posições.
