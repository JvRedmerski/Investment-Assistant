# Current Project Status

> Camada 1 da memória: **onde o projeto está**, em uma página.
> Ledger detalhado task-a-task (histórico completo, notas de implementação, decisões datadas): [../PROJECT_STATUS.md](../PROJECT_STATUS.md).
> Última verificação contra o código: **2026-08-18**.

## Current Phase

**Wave 09 em andamento**: W09-001 (sub-scores) e W09-002 (fonte CVM) concluídas; falta **W09-003 — algoritmo de alocação do aporte mensal**.
9 de 33 waves concluídas (W00–W08).

✅ **O bloqueio de fundamentals foi contornado em 2026-08-18** ([ADR-020](../decisions/ADR-020-cvm-primary-fundamentals-source.md)). A fonte primária passou a ser os **dados abertos da CVM** — o arquivo entregue ao regulador, aberto, sem token, sem cota e com mais histórico do que o fornecedor dava. A **Brapi continua no projeto** fazendo a ponte que a CVM não faz: seus arquivos não têm coluna de ticker, e o `summaryProfile` (ainda gratuito) traz o CNPJ.

⚠️ **Restrição externa que permanece**: o `range` da Brapi está limitado a `3mo` (HTTP 400, `INVALID_RANGE`) e é **relativo a hoje**, sem parâmetro de data inicial — não há como paginar histórico. Teto absoluto de ~63 pregões para preços de ações e para o IBOV. Já quebra `sync_daily_history` em janelas acima de 3 meses e limita a W13.

CDI e IPCA **não** são afetados: vêm do Banco Central (SGS), aberto e sem cota.

## Overall Status

| | |
|---|---|
| **Completed** | W00 Foundation · W01 Scaffold · W02 Database · W03 Auth · W04 Portfolio · W05 Market Data · W06 Fundamental Data · W07 Quant Engine · W08 Benchmark Engine |
| **In Progress** | W09 Recommendation Engine — W09-001 e W09-002 feitas, W09-003 (alocação) pendente |
| **Blocked** | — nenhuma |

Baseline atual: `pytest` → **542 passed** (backend/.venv).

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

Detalhe por task: [../history/COMPLETED_TASKS.md](../history/COMPLETED_TASKS.md).

## Current Work

**W09-003 — algoritmo de alocação do aporte mensal.** Os sub-scores estão prontos e a fonte de demonstrativos voltou a funcionar.

## Next Recommended Step

Antes da alocação, um passo curto e de alto retorno: **ações em circulação por período**. O mesmo arquivo DFP já traz `composicao_capital` (com ações em tesouraria), e é só isso que falta para `pe`/`pb`/`dy` — destravaria o pilar de **Valuation**, o último ainda ausente, levando a cobertura do score de 55% para 75%. Ver [CURRENT_TASK.md](CURRENT_TASK.md).

## Known Issues

Problemas reais, verificados no código (2026-08-18).

> 🔴 **O mais restritivo, descoberto na W08:** **Plano gratuito da Brapi limita o `range` a `3mo`** (verificado 2026-08-18, HTTP 400 `INVALID_RANGE`: *"Ranges permitidos: 1d, 5d, 1mo, 3mo"*). E o `range` é **relativo a hoje** — a API não aceita data inicial, então **não há como paginar histórico**: ~63 pregões é o teto absoluto. Três consequências: (a) `_brapi_range_for` mapeia janelas > 90 dias para `6mo`/`1y`/`2y`/`5y`/`max`, todos recusados — **`sync_daily_history` falha hoje para qualquer janela acima de 3 meses**, defeito pré-existente da W05 que só apareceu agora porque a validação da W06-004 usou `range=1mo`; (b) `beta` fica estatisticamente pobre; (c) atinge o backtesting da W13, que precisa de anos. Não afeta CDI/IPCA (fonte BCB).

1. ~~Parsers da Brapi nunca validados~~ — **RESOLVIDO** (W06-003 + W06-004). Market data validado contra resposta real de ação, **FII, ETF e banco**: mesma forma de resposta nas quatro classes, 0 barras rejeitadas. Fundamentals validado só com PETR4 e agora **impossível de reexaminar** no plano gratuito (item 14).
2. ~~Migrations `002`, `003` e `004` nunca aplicadas em PostgreSQL real~~ — **RESOLVIDO em 2026-08-18.** `001`→`004` aplicadas em PostgreSQL 16 real. Para isso foi preciso corrigir `migrations/env.py`, que chamava `context.is_offline()` (inexistente; o correto é `is_offline_mode()`) e abortava com `AttributeError` — ou seja, **o Alembic nunca havia executado**. `alembic heads`/`history` não carregam `env.py`, e por isso a "validação estrutural" anterior não pegou o erro.
3. **`get_quote()` implementado mas não exposto.** Existe no provider e é testado, mas nenhum endpoint o consome — cotação atual não chega ao usuário.
4. **Ingestão de dividendos (proventos) não implementada**, embora o roadmap a liste como entregável da Wave 5 (`docs/roadmap.md` §17). A Wave 05 foi marcada como concluída sem ela.
5. **`npm run lint` quebrado no frontend.** O script chama `eslint` mas não há `eslint` nas `devDependencies` nem arquivo de config.
6. **Lint pré-existente sujo no backend.** `ruff check` acusa findings em arquivos não tocados desde a Wave 02 (`data/models/users.py`, `daytrade.py`, `recommendations.py`, `core/logging.py`, `data/database.py`, `api/routes/health.py`, `tests/test_health.py`) — import-sorting e `Optional[X]`/`List[X]` → `X | None`/`list[X]`. Deliberadamente fora de escopo até uma task dedicada de cleanup. (`data/models/fundamentals.py` saiu da lista: foi reescrito e está limpo.)
7. **Colunas monetárias ainda em `Float`** (dívida conhecida, conversão adiada para a wave que as usar): `intraday_prices` OHLC (W15), `portfolio_snapshots.total_value/cash_value` (W11), `investor_profiles.monthly_contribution` (W09).
8. **`PriceSyncRequest` documenta que `end` não pode ser futura, mas o validador não verifica isso** — apenas `start <= end`.
9. **3 dos 10 indicadores permanecem `None`** (eram 5) — `pe`/`pb`/`dy`. **`ebitda_margin` e `debt_ebitda` foram destravados em 2026-08-18** pela fonte da CVM: o fornecedor copiava `ebit` em `cleanEbitda`, enquanto a CVM permite derivar EBITDA de verdade (`EBIT + |D&A|`, com D&A em `7.04.01` da DVA). Os três restantes precisam de **ações em circulação por período** — que o próprio DFP traz em `composicao_capital`, ainda não ingerido.
   - *Registro do estado anterior:* ~~5 dos 10 indicadores permanecem `None`~~, cada um por motivo **evidenciado** contra a API real: `pe`/`pb`/`dy` — a Brapi só expõe `sharesOutstanding` e `dividendYield` como snapshots atuais, sem data-fim de período; aplicá-los a um balanço de 2010 seria look-ahead (§108/§109). `debt_ebitda`/`ebitda_margin` — `cleanEbitda` é cópia literal de `ebit` em 16/16 períodos, não é EBITDA. **Limita os sub-scores de Valuation na Wave 09.**
10. ~~Indicadores gravados antes da W06-003 estão errados~~ — **PENDÊNCIA ANULADA em 2026-08-18.** Nunca existiu banco: sem container, sem volume Docker, sem arquivo SQLite. Ao subir o Postgres o volume foi criado do zero e todas as tabelas vieram com **0 linhas** (`assets`, `asset_prices`, `fundamentals`, `financial_indicators`, `users`, `transactions`). Não há nada gravado para recomputar. A pendência havia sido registrada por hipótese, não por observação do estado real.
11. **Reexpressões (restatements) de demonstrativos são invisíveis**: o primeiro valor gravado para um `reference_date` nunca é substituído. Corrigir exige schema versionado por período. (Indicadores derivados, ao contrário, podem ser recomputados — [ADR-015](../decisions/ADR-015-indicator-recomputation.md).)
12. **Demonstrativos trimestrais não são ingeridos** — o parser filtra `type == "yearly"`, porque `fundamentals` não tem coluna de período para distingui-los de um exercício anual com a mesma data-fim ([ADR-013](../decisions/ADR-013-fundamentals-point-in-time.md)).
13. **Throttle de requisições desligado por padrão.** `MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS` e `FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS` têm default `0.0` — nenhum espaçamento entre chamadas. A Brapi tem **cota mensal limitada** no plano gratuito. Definir um intervalo no `.env` antes de qualquer ingestão em lote.
14. 🔴 **Módulos de demonstrativos saíram do plano gratuito da Brapi** (verificado 2026-08-18, HTTP 403: *"Módulos disponíveis hoje: summaryProfile"*). Em 2026-08-17 a mesma chamada trouxe 16 períodos. **A ingestão de fundamentals está inoperante — por plano, não por código**; o parser segue correto e testado. Não afeta a W07 (que só usa `asset_prices`); **bloqueia a W09**. Decidir entre assinar o plano Startup, migrar para dados abertos da CVM, ou adiar a W09.
15. **Plano gratuito aceita no máximo 1 ativo por requisição.** Não há batching — ingestão em lote custa 1 requisição por ticker. Dimensionar a cota mensal por aí.
16. ~~`adjusted_close` pode ser congelado errado~~ — **CORRIGIDO em 2026-08-18** ([ADR-016](../decisions/ADR-016-unadjusted-bars-are-not-stored.md)). O parser não fabrica mais o ajuste a partir do `close`; `adjusted_close` é `Decimal | None` refletindo o que a fonte reportou, e `validate_daily_bars` rejeita a barra sem ajuste (`MISSING_ADJUSTED_CLOSE`). Autocorretivo: a data não é gravada, então o sync seguinte a insere quando a fonte publicar. Corrigido **antes** de qualquer ingestão — o banco estava vazio, então não há linha contaminada. Efeito colateral esperado: a sessão fechada mais recente pode faltar por ~1 dia, e `rejected: 1` no sync diário é rotina.
17. **`alembic check` falha por drift**: unique constraint + unique index duplicados em `assets.ticker` e `users.email` (a migration `001` declara a constraint, o model declara `unique=True, index=True`). Redundante, não incorreto — mas impede usar `alembic check` como guarda de drift no CI.
18. **`env_file=".env"` é relativo ao cwd.** Rodando de `backend/`, o `.env` da raiz não é lido e `BRAPI_TOKEN` fica vazio **silenciosamente**. Sob `docker compose` não afeta.
19. **Aproximação conhecida no `performance_index`**: um fluxo (compra/venda) que cai numa data sem preço armazenado é neutralizado na próxima data valorável, o que credita ao capital pré-existente o que as ações novas ganharam no intervalo. Só ocorre quando a data da operação não pode ser valorada; quando pode — o caso normal — não há distorção alguma. As alternativas seriam fabricar um fechamento (regra 44), esconder movimento real, ou descartar o histórico inteiro após uma lacuna. Correção verdadeira é a montante: ingerir os preços faltantes.
20. **`app/data/models/__init__.py` entrou na lista de lint pré-existente** — `ruff` (I001, RUF022) e `black` já falhavam nele antes da W08 (confirmado rodando as ferramentas na versão do `HEAD`). Não corrigido por estar fora de escopo (regra 134).
21. **Bancos e seguradoras usam plano de contas diferente no DFP.** `3.01` do Banco do Brasil é "Receitas de Intermediação Financeira", não receita de vendas, e `2.01.04` (empréstimos) pode não existir. O mapeamento aceita o que houver e deixa `None` no resto, mas os números de uma instituição financeira merecem conferência antes de virarem score. Validação feita contra PETR4 e VALE3 (industriais).
22. **Cobertura da CVM é só companhia aberta brasileira.** FII, ETF e BDR não arquivam DFP e nunca arquivarão — para eles os pilares fundamentalistas ficam permanentemente ausentes, o que o motor de score já trata como estado normal (não como falha).
23. **Um exercício já em cache nunca é rebaixado.** A CVM republica um ano conforme empresas corrigem; pegar a correção exige apagar o ZIP em `var/cvm/`. Deliberado — nenhum caminho de leitura dispara isso sozinho.

## Inconsistências documentação × código

Registradas, **não corrigidas** (corrigir exigiria alterar AGENTS.md ou criar código fora de escopo):

| Documentado em | Realidade |
|---|---|
| AGENTS.md §6: `PROJECT_STATUS.md` e `CHANGELOG.md` na raiz | Status está em `docs/PROJECT_STATUS.md`; `CHANGELOG.md` não existe |
| AGENTS.md §6: `backend/app/data/repositories/` | Não existe — rotas usam `Session` do SQLAlchemy diretamente (ver ADR-011) |
| AGENTS.md §6: `backend/tests/{unit,integration,regression}/` | `tests/` é plano, sem subpastas |
| AGENTS.md §6/§93: `docs/architecture.md`, `database.md`, `api.md`, etc. | Não existiam; substituídos por `docs/architecture/*.md` criados nesta sessão |
| AGENTS.md Wave Execution Protocol: `docs/waves/WAVE-XX-*.md` | Diretório `docs/waves/` não existe; as waves vivem em `docs/roadmap.md` e `docs/PROJECT_STATUS.md` |
| AGENTS.md §5.1 / README: React Router, TanStack Query, Zod, Recharts | Instalados no `package.json`, nenhum é importado — o frontend é uma página estática única |
| README: "Frontend 🟢 COMPLETED" | Só existe uma landing page de status; sem rotas, sem estado, sem telas de produto |
| `.env.example`: `ACCESS_TOKEN_EXPIRE_MINUTES=115200` (80 dias) | Default do código é 8 dias (`core/config.py`) |

## Important Context

- **Ambiente**: Windows + PowerShell. Virtualenv em `backend/.venv` — invoque como `.venv\Scripts\python.exe -m pytest`. **PostgreSQL 16 no ar via Docker**, schema `005`, com dado real de benchmark ingerido (CDI, IPCA, IBOV).
- **Há rede de saída** neste ambiente (a Wave 05 foi implementada sem ela — daí a lacuna nº 1, já resolvida). A W08 chamou BCB e Brapi ao vivo. O SGS do Banco Central é aberto e sem cota; a Brapi tem cota mensal e aceita 1 ativo por requisição.
- **Testes rodam contra SQLite in-memory compartilhado** (`tests/conftest.py`), com `app.dependency_overrides` para `get_db`, `get_market_data_provider` e `get_benchmark_provider`. **Nenhum teste toca rede ou Postgres** — as chamadas ao vivo da W08 foram feitas em scripts de validação avulsos, não na suíte.
- **A regra mais estruturante do projeto**: posições nunca são armazenadas — sempre derivadas do ledger de transações (AGENTS.md §16, ADR-002). Não crie tabela de posições.
