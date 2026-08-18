# ADR-018 — Benchmark de taxa é armazenado como taxa publicada, não como índice acumulado

## Status

Accepted (2026-08-18, Wave 08 / W08-001)

## Context

A Wave 07 entregou `beta`, `sharpe` e `sortino` prontos e testados, retornando `None` por um único motivo: ninguém tinha série de referência para passar. A W08 ingere essas séries. Ao fazê-lo, uma pergunta que o `CURRENT_TASK.md` já havia levantado precisou de resposta:

**O CDI é uma taxa acumulada, não um preço.** `beta` recebe `list[PricePoint]` — uma série de níveis — porque alinha ativo e benchmark pelas datas em comum *antes* de calcular retornos. O IBOV se encaixa nisso naturalmente: é um nível em pontos. O CDI, não. O número publicado para 2024-01-02 (`0.043739`) **é** o retorno daquele dia, não um preço de que se extrai retorno.

Representá-lo como se fosse preço é o erro mais fácil de cometer aqui e o mais difícil de perceber: entre 2026-08-13 (0,051660%) e 2026-08-17 (0,051660%) uma série de "preços" acusaria retorno **zero**, quando o CDI de fato rendeu ~0,155% nos três dias. E se a taxa oscilasse de 0,0520% para 0,0517%, a leitura como preço reportaria uma **perda de 0,9%** onde houve ganho. Não é imprecisão — é outra grandeza, com outro sinal.

Havia ainda duas perguntas acopladas:

1. **O que gravar**: a taxa como publicada, ou já o índice acumulado (base 100) que `PricePoint` consome?
2. **Qual convenção de anualização**: o CDI é cotado em base 252, mas o ADR-017 fixou 365 dias corridos para retorno e 252 pregões para dispersão. Qual se aplica a uma taxa livre de risco?

E uma terceira, sobre a fonte: a Brapi não serve CDI nem IPCA.

## Decision

### 1. A tabela guarda a taxa **como publicada**, normalizada só de percentual para fração. O índice acumulado é derivado na leitura.

`benchmark_values.value` guarda `0.00043739` para o CDI de 2024-01-02 — o que o Banco Central publicou (`0.043739`), dividido por 100. Nada de índice, nada de base, nada acumulado.

O motivo é que **acumular é uma operação com parâmetro**: o índice depende da data-base a partir da qual se acumula. Um índice gravado congela uma data-base escolhida hoje e responde a uma pergunta que ninguém fez. A comparação que o produto precisa fazer — "minha carteira contra o CDI desde o meu primeiro aporte" — tem data-base diferente para cada carteira, e para cada janela que o usuário selecionar na tela.

A conversão taxa → índice não perde nada e é determinística; a inversa perde a granularidade diária. Derivar na leitura é portanto estritamente mais informativo, e o custo é uma multiplicação por observação.

Um `INDEX` (IBOV) é gravado como o nível publicado, sem transformação. `BenchmarkKind` viaja junto do dado e é o que impede que uma taxa seja lida como nível.

### 2. A unidade canônica é **fração, nunca percentual**, e a conversão acontece no provider.

`app.quant.returns` já estabelece que "retornos são frações, não percentagens". Uma taxa armazenada em percentual encontraria um retorno calculado em fração em algum ponto do pipeline, e o fator 100 sobreviveria silenciosamente: `0.05` é ao mesmo tempo um 5% plausível e um erro de cem vezes se o dado significava 0,05%.

A divisão por 100 fica no `BcbSgsProvider`, o único ponto do sistema que lê a fonte e portanto o único que sabe a unidade dela.

### 3. Taxa livre de risco anualiza em **252**, e isso fecha exatamente com o `_periodic_rate` da W07.

O CDI é cotado no Brasil em base 252 — não por convenção estatística, mas porque é assim que o mercado o negocia. `PERIODS_PER_YEAR[DAILY]` em `risk.py` já é 252, e `sharpe` de-anualiza a taxa recebida com `(1 + anual) ** (1/252) - 1`. Anualizar com 252 e de-anualizar com 252 **fecha o círculo sem resíduo**.

Isso não contraria o ADR-017: aquele ADR usa 365 para *retorno de preço*, que compõe sobre tempo decorrido. Uma taxa CDI não é retorno de preço — ela só existe em dias de pregão, e o próprio Banco Central a anualiza em 252.

**Isto foi verificado contra a fonte, não deduzido.** O SGS publica o CDI duas vezes: série 12 (diária) e série 4389 (a mesma taxa já anualizada). Compor a série 12 em 252 tem que reproduzir a 4389 para o mesmo dia:

| dia | série 12 (diária) | composta 252× | série 4389 publicada |
|---|---|---|---|
| 2024-01-02 | 0,043739% | **11,6499%** | **11,65%** |
| 2026-08-17 | 0,051660% | **13,8998%** | **13,90%** |

Duas janelas independentes, casando na precisão que a fonte publica. Se a convenção fosse 365, daria 17,3% contra 11,65% — não é um erro sutil.

### 4. Fonte: **API SGS do Banco Central** para CDI/IPCA/Selic; provedor de market data para o IBOV.

A Brapi não serve CDI nem IPCA. O SGS é aberto, sem token e sem cota — e é a fonte **primária**: o CDI contra o qual um fundo se reporta é o que o Banco Central publica, sem intermediário interpretando.

O IBOV vem pelo provedor de market data já existente porque, verificado ao vivo, a Brapi devolve `^BVSP` **exatamente na mesma forma de uma ação** — `historicalDataPrice[]` com OHLCV e `adjustedClose`. `BrapiIndexProvider` portanto não escreve parser nenhum: delega ao `BrapiProvider` já validado em quatro classes de ativo e só traduz o vocabulário de erro.

### 5. Uma observação cujo **período ainda não terminou** é rejeitada, nunca gravada.

Extensão direta do ADR-016 para séries de benchmark. A Brapi inclui a **sessão em curso** dentro de `historicalDataPrice` como se fosse uma barra fechada — e, ao contrário de uma ação, o índice vem com `adjustedClose` preenchido, então a guarda `MISSING_ADJUSTED_CLOSE` do ADR-016 **não** dispara.

Medido: três requisições ao `^BVSP` em poucos minutos, em 2026-08-18, devolveram para *a mesma data* os fechamentos 166851,5156 → 166978,9375 → 166923,3438. Como a ingestão nunca reescreve data já gravada, o primeiro que chegasse ficaria congelado como "o fechamento do Ibovespa".

A regra é sobre o **período**, não sobre a data: a observação do IPCA datada de 2026-08-01 mede agosto inteiro, então em 18/08 ela não está dezessete dias liquidada — está com um terço de mês de vida. Daí `period_end_for(data, periodicidade) >= hoje` como critério, e não uma comparação de datas.

Autocorretivo, como no ADR-016: `rejected: 1` num sync diário é rotina, e a rodada seguinte grava o valor definitivo.

### 6. O catálogo de benchmarks vive em **código**, não em tabela.

`app/domain/benchmarks/catalog.py` define os quatro benchmarks. Não há tabela `benchmarks` nem migration de seed. `benchmark_values.benchmark_code` é string, não foreign key.

A definição de um benchmark não é dado do usuário — é fato revisável sobre uma fonte externa, e controle de versão é melhor lar para isso do que um seed que dois ambientes podem divergir. É também o que a roadmap §20 pede por "outros benchmarks configuráveis": adicionar um é uma linha em diff.

## Evidence

- `backend/app/data/models/benchmarks.py` — `NUMERIC(24,12)`, sem coluna de índice acumulado, com a justificativa da precisão ao lado.
- `backend/migrations/versions/005_benchmark_values.py` — aplicada em PostgreSQL 16 real, com round-trip `downgrade`/`upgrade` verificado.
- `backend/app/integrations/benchmarks/bcb.py` — conversão percentual→fração; docstring com as três surpresas da API real.
- `backend/app/integrations/benchmarks/brapi_index.py` — delegação ao `MarketDataProvider`, sem parser próprio.
- `backend/app/domain/benchmarks/catalog.py` — os quatro benchmarks e o porquê da série 12 em vez da 4389.
- `backend/app/domain/benchmarks/data_quality.py` — `INCOMPLETE_PERIOD` e `period_end_for`.
- `backend/tests/test_bcb_benchmark_provider.py` — `test_the_real_cdi_compounds_to_the_annual_rate_the_bcb_itself_publishes` e `test_the_real_ipca_year_accumulates_to_the_figure_the_ibge_published`.
- `AGENTS.md` §28 (benchmarks), §17 (precisão), §44 (não inventar dado), §113 (determinismo); ADR-016, ADR-017.

## Alternatives

- **Gravar o índice acumulado base 100** — rejeitado. Congela uma data-base arbitrária, e a comparação carteira × CDI precisa da data-base de cada carteira. Perde a taxa diária, que não é recuperável do índice sem supor que a taxa foi constante nas lacunas.
- **Gravar as duas coisas (taxa e índice)** — rejeitado. Duas representações do mesmo fato que podem divergir, exatamente o que a regra 16 proíbe para posições. O índice sai de uma multiplicação; não precisa de coluna.
- **Ingerir a série 4389 (CDI já anualizado)** — rejeitado. É a direção que perde informação. Além disso, ela serviu de **verificação independente** da convenção — e um dado usado para conferir não deve ser o mesmo que se grava.
- **Anualizar a taxa livre de risco em 365, por consistência com o ADR-017** — rejeitado por evidência: a fonte anualiza em 252, e compor em 365 erra o Sharpe por um fator constante sem sintoma na saída.
- **Um `PricePoint` sintético com preço 1,0 e a taxa embutida** — rejeitado. Faria a taxa passar por `usable_series`, que exige preço positivo e não sabe que aquilo não é preço. O tipo deixaria de significar o que diz.
- **Tabela `benchmarks` com seed via migration** — rejeitada. Definição de benchmark é configuração revisável, não dado de usuário; um seed permite que ambientes discordem sobre o que "CDI" significa.
- **Escrever um parser próprio para o `^BVSP`** — rejeitado. A resposta é idêntica à de uma ação; um segundo parser para o mesmo payload é a implementação paralela que a regra 8 proíbe, e seria a cópia que apodrece.
- **Aceitar a barra da sessão em curso e sobrescrevê-la depois** — rejeitado. Exigiria abrir mão da idempotência da ingestão, que é o que garante que uma comparação relatada continue reproduzindo.

## Consequences

- ✅ `sharpe`, `sortino` (CDI) e `beta` (IBOV) deixam de retornar `None` por falta de referência — o objetivo da wave.
- ✅ A base-252 fecha sem resíduo com o `_periodic_rate` já escrito na W07: anualizar e de-anualizar usam o mesmo 252.
- ✅ Nenhum valor gravado é derivado, suposto ou preenchido — cada linha é o que a fonte publicou, na unidade canônica.
- ✅ Nenhum valor gravado é um retrato de algo ainda em movimento.
- ✅ CDI e IPCA não consomem cota: o SGS é aberto. Só o IBOV custa requisição.
- ⚠️ Toda leitura de uma série `RATE` **tem que** consultar o `kind` do catálogo. Ler `benchmark_values` sem isso acabará tratando taxa como preço. Por isso o caminho de leitura passa por `app.domain.benchmarks`.
- ⚠️ O SGS recusa janela maior que 10 anos em série diária (HTTP 406, limite inclusivo-exato verificado). O provider fatia sozinho; um backfill de três décadas são quatro requisições.
- ⚠️ **HTTP 404 do SGS significa "janela sem observação"**, não "série inexistente" — um fim de semana devolve 404. Tratado como resultado vazio. Série inexistente, por sua vez, devolve **HTTP 200 com uma página HTML**.
- 🔴 **O plano gratuito da Brapi só aceita `range` de até `3mo`**, e o `range` é relativo a hoje — não há como paginar histórico. O IBOV fica limitado a ~63 pregões, e o mesmo teto atinge o sync de preços da Wave 05. Registrado como Known Issue; não é regressão desta wave, mas limita `beta` e, mais adiante, o backtesting da W13.
