# Session Handoff

## Last Updated

2026-08-18

## Last Completed Work

**Wave 08 — Benchmark Engine — concluída.** Duas tasks, e é a wave que finalmente
faz o Quant Engine da W07 produzir número em vez de `None`.

### W08-001 — Ingestão de benchmarks (`b2ba595`)

`BenchmarkProvider` abstrato + factory, com duas implementações:

- **`BcbSgsProvider`** — CDI, IPCA e Selic pela API SGS do Banco Central. Aberta, sem
  token, sem cota, e é a fonte **primária**: o CDI contra o qual um fundo se reporta é
  o que o BC publica.
- **`BrapiIndexProvider`** — IBOV. **Não escreve parser nenhum**: verificado ao vivo, a
  Brapi devolve `^BVSP` exatamente na mesma forma de uma ação, então ele delega ao
  `MarketDataProvider` já validado na W06 e só traduz o vocabulário de erro.

Catálogo em **código** (`domain/benchmarks/catalog.py`), não em tabela — é o que a
roadmap §20 pede por "outros benchmarks configuráveis", e evita seed migration.
`benchmark_values` em `NUMERIC(24,12)` + migration `005`, aplicada em Postgres 16 real
com round-trip `downgrade`/`upgrade`.

### W08-002 — Comparativo carteira/ativo × benchmark

- `benchmarks/series.py` — taxa → índice acumulado; taxa anualizada da janela.
- `portfolio/performance.py` — índice **time-weighted** da carteira (valor de cota),
  derivado do ledger + `asset_prices`, entregue como `PricePoint`.
- `benchmarks/comparison.py` — puro; **não calcula nada**, só orquestra o `app.quant`.
- Endpoints `GET /assets/{ticker}/benchmarks/{code}` e `GET /portfolios/{id}/benchmarks/{code}`.

## Current State

- `pytest` → **449 passed** (316 → 391 → 449). `ruff`/`black` limpos nos arquivos alterados.
- **Wave 08 🟢 concluída.** 9 de 33 waves (W00–W08).
- **PostgreSQL 16 no ar, schema `005`, e agora com dado real**: CDI 252 pregões
  (2025-08-18 a 2026-08-17), IPCA 31 meses (desde 2024-01), IBOV 63 pregões
  (desde 2026-05-20).
- `beta`, `sharpe` e `sortino` **produzem número**. Era o objetivo da wave.

## Important Details

### As decisões estruturais da wave ([ADR-018](../decisions/ADR-018-benchmark-representation.md) e [ADR-019](../decisions/ADR-019-portfolio-return-is-time-weighted.md))

**Benchmark de taxa guarda a taxa publicada, não o índice acumulado.** Acumular é uma
operação **com parâmetro** — o índice depende da data-base, que é diferente para cada
carteira e muda a cada janela que o usuário escolhe na tela. Gravar um índice congela
uma data-base que ninguém pediu e joga fora a taxa diária, que não é recuperável do
índice. A conversão acontece na leitura, em `series.py`.

**Taxa livre de risco anualiza em base 252, e isso foi verificado, não deduzido.** O SGS
publica o CDI duas vezes: série 12 (diária) e série 4389 (já anualizada). Compor a 12 em
252 tem que reproduzir a 4389 — e reproduz, nas duas janelas testadas:

| dia | série 12 | composta 252× | série 4389 |
|---|---|---|---|
| 2024-01-02 | 0,043739% | 11,6499% | 11,65% |
| 2026-08-17 | 0,051660% | 13,8998% | 13,90% |

Isso também fecha sem resíduo com o `_periodic_rate` da W07, que de-anualiza com
`PERIODS_PER_YEAR[DAILY] = 252`. Se as duas pontas usassem bases diferentes, todo Sharpe
sairia errado por um fator constante, **sem nada na saída denunciando**.

**Observação de período não terminado é rejeitada, nunca gravada** (extensão do ADR-016).
A Brapi inclui a **sessão em curso** dentro de `historicalDataPrice` — e, ao contrário de
uma ação, o índice vem com `adjustedClose` preenchido, então a guarda
`MISSING_ADJUSTED_CLOSE` do ADR-016 **não** dispara. Três requisições ao `^BVSP` em
poucos minutos devolveram, para a mesma data, 166851,5156 → 166978,9375 → 166923,3438.
Como a ingestão nunca reescreve data gravada, o primeiro a chegar ficaria congelado como
"o fechamento do Ibovespa".

**A carteira entra como índice time-weighted, não como valor patrimonial.** Sem isso, uma
carteira com aporte mensal apareceria batendo qualquer benchmark num ano em que o
investidor perdeu dinheiro — o aporte entraria como rentabilidade (regra 26).

**`beta` só contra benchmark do tipo `INDEX`.** Não é limitação a remover depois: o CDI
quase não varia, então `cov/var` divide por quase-zero. E **não sairia `None` sozinho** —
a variância não é exatamente zero, então a guarda dentro de `beta` não dispara e um
número enorme e instável seria reportado com cara de fato.

### O que a API real ensinou, e nenhum mock ensinaria

A DoD exigia validar contra resposta real **antes** de escrever os mocks. Foi o que
produziu tudo abaixo — nada disso está na documentação das APIs:

- **HTTP 404 do SGS significa "janela sem observação"**, não "série inexistente": pedir o
  CDI num fim de semana devolve 404. Tratado como resultado vazio; tratar como erro faria
  todo sync falhar quando a janela pegasse só dias não úteis.
- **Série inexistente devolve HTTP 200 com uma página HTML**, não JSON.
- **O SGS recusa janela acima de 10 anos em série diária** (HTTP 406), com limite
  inclusivo-exato: 18/08/2016→18/08/2026 passa, um dia a mais não. O provider fatia sozinho.
- 🔴 **O plano gratuito da Brapi limita o `range` a `3mo`** (HTTP 400, `INVALID_RANGE`), e
  o `range` é **relativo a hoje** — não há parâmetro de data inicial, então **não dá para
  paginar histórico**. Isso **já quebra `sync_daily_history` da W05** para qualquer janela
  acima de 3 meses; só não havia aparecido porque a validação da W06-004 usou `range=1mo`.
  Não é regressão da W08, mas limita `beta` hoje e o backtesting da W13.

### Lições de método desta sessão

- **O teste escrito à mão pegou um defeito real de novo.** `performance_index` ignorava
  por completo eventos do ledger em datas sem preço — as quantidades **e** os fluxos —
  porque indexava o ledger pela data de valoração. Uma compra feita num dia sem preço
  simplesmente não existia. Corrigido com varredura por ponteiro. Um teste escrito a
  partir da saída do código teria passado.
- **Rodar contra dado real melhorou o código depois de tudo verde.** A comparação IBOV ×
  IPCA devolveu razão **-85,16** (denominador de +0,07%), e IBOV × CDI devolveu **-1,80**
  ("-180% do CDI" não significa nada). `return_ratio` passou a exigir que **ambos** os
  retornos sejam positivos — a única situação que o idioma "115% do CDI" descreve.
- **A melhor sanidade é comparar a série consigo mesma.** IBOV × IBOV com dado real deu
  excesso 0,00% e **beta exatamente 1,0000**, o que valida o alinhamento por data e a
  covariância de uma vez.

## Pending Work

**Wave 09 — Portfolio Recommendation Engine**, que **começa por uma decisão de produto**.
Ver [CURRENT_TASK.md](CURRENT_TASK.md).

Três dos seis sub-scores (Quality, Valuation, Growth) dependem de demonstrativos, e a
ingestão de fundamentals está inoperante desde 2026-08-18 porque os módulos saíram do
plano gratuito da Brapi. Os outros três (Risk, Diversification, Portfolio Fit) estão
**desbloqueados** pela W07+W08. Escolher entre: assinar o plano Startup (R$ 119,99/mês),
migrar para dados abertos da CVM, ou entregar a wave com os sub-scores disponíveis e os
demais **explicitamente ausentes** — nunca estimados (regra 44 / ADR-014), porque um
Quality Score inventado contamina o Final Score e desaparece dentro dele.

Pendências de fundo, sem mudança: `alembic check` falha por drift em `assets.ticker` e
`users.email`; lint pré-existente no backend (agora incluindo `data/models/__init__.py`);
`get_quote()` implementado mas não exposto; ingestão de proventos nunca feita;
`npm run lint` quebrado no frontend.

Aproximação conhecida e documentada: no `performance_index`, um fluxo que cai numa data
sem preço é neutralizado na próxima data valorável, creditando ao capital pré-existente o
que as ações novas ganharam no intervalo. Só ocorre nessa situação; a correção verdadeira
é a montante, ingerir os preços faltantes.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md), `docs/roadmap.md` §21 e `AGENTS.md` §30.
Decidir o destino dos fundamentals **antes** de escrever código. Usar
`app/domain/benchmarks/comparison.py` como molde de "módulo puro que só orquestra o
`app.quant`" — o Score deve combinar o que já existe, não recalcular nada.

## Relevant Files

- `backend/app/domain/benchmarks/` — catálogo, ingestão, série, comparação
- `backend/app/domain/portfolio/performance.py` — índice time-weighted da carteira
- `backend/app/quant/{returns,risk}.py` — tudo que o Score deve reutilizar
- `backend/app/domain/fundamentals/indicators.py` — as 10 fórmulas (5 produzem valor)
- `backend/tests/test_bcb_benchmark_provider.py` — molde de teste de regressão contra resposta real
- `docs/decisions/ADR-018-benchmark-representation.md` — representação de benchmark
- `docs/decisions/ADR-019-portfolio-return-is-time-weighted.md` — rentabilidade de carteira (TWR), e por que a MWR/TIR fica pendente
