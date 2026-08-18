# ADR-019 — A rentabilidade da carteira é medida por TWR, entregue como índice de cota

## Status

Accepted (2026-08-18, Wave 08 / W08-002)

## Context

A roadmap §20 pede "Portfolio vs CDI / IBOV / benchmark escolhido". Para comparar, é preciso primeiro decidir **o que significa "a rentabilidade da carteira"** — e essa pergunta estava explicitamente em aberto desde a Wave 07.

O `app/quant/returns.py` recusou-se a respondê-la, e disse por quê no próprio módulo: ele calcula o retorno de uma **série de preços**, e uma carteira com aportes é outra grandeza (AGENTS.md §26). O perfil do usuário torna isso central, não acadêmico: **aportes mensais de ~R$ 1.000** significam que a carteira recebe dinheiro novo o tempo todo.

Com fluxo de caixa no meio, `(final - inicial) / inicial` mede **variação patrimonial**, não desempenho. Num ano em que o investidor aportou R$ 12.000 e o mercado caiu, o patrimônio pode terminar maior do que começou — e a conta ingênua reportaria lucro. Comparar esse número contra o CDI faria a carteira "ganhar" de qualquer benchmark, sempre, porque o benchmark não recebe aporte.

## Decision

### 1. A carteira entra na comparação como **índice time-weighted** (valor de cota), não como valor patrimonial

`app/domain/portfolio/performance.py` produz um índice que parte de uma base e se move **apenas** pelo retorno que as posições produziram. Aportes e retiradas são neutralizados sub-período a sub-período.

Duas carteiras que compraram os mesmos ativos nos mesmos dias recebem o mesmo índice, uma tendo investido R$ 1.000 e a outra R$ 100.000. É o mesmo mecanismo que um fundo usa para a cota, e é a única forma de a comparação contra um índice ser honesta.

### 2. O índice é entregue como `list[PricePoint]`, o tipo que o Quant Engine já lê

Não é detalhe de conveniência. Como a saída é uma série de níveis, **todo o `app/quant/` da W07 consome a carteira sem adaptador nenhum**: `total_return`, `cagr`, `volatility`, `max_drawdown`, `beta`, `sharpe`, `sortino`. Nenhuma fórmula foi reescrita para "a versão da carteira".

Consequência de desenho: `benchmarks/comparison.py` é um módulo de comparação que **não calcula nada** — só orquestra. Esse é o formato que módulos analíticos futuros devem seguir.

### 3. O que conta como fluxo externo decorre de a carteira não ter caixa modelado

O projeto não deriva saldo em caixa (só `compute_net_contributions` para DEPOSIT/WITHDRAWAL), então "valor da carteira" aqui significa **apenas as posições**. Sob essa definição:

- **BUY/SELL são fluxos externos** — a compra converte caixa não rastreado em posição rastreada, elevando o nível sem que nada tenha rendido. Neutralizá-los é o serviço inteiro.
- **DEPOSIT/WITHDRAWAL não são** — movimentam caixa que o índice nunca enxerga.
- **DIVIDEND não é** — as posições são valoradas a `adjusted_close`, que já embute o provento. Contá-lo aqui creditaria o mesmo dinheiro duas vezes.

Taxas entram no fluxo, de modo que aparecem onde devem: dinheiro que entrou sem virar valor, ou seja, retorno menor.

### 4. Isto **não** é o valor da carteira, e não deve ser apresentado como tal

Valorar a `adjusted_close` é o que torna o índice um retorno **total** (com proventos). Mas um nível dele não é "quanto eu tenho". O investidor que pergunta o patrimônio quer o fechamento bruto mais o caixa — outro número, que pertence ao dashboard da W11.

### 5. `beta` só é reportado contra benchmark do tipo `INDEX`

Beta mede sensibilidade a um **mercado**. O CDI não é um mercado: quase não varia, então `cov/var` divide por quase-zero e devolve um número enorme, instável e sem significado.

O ponto decisivo é que ele **não sairia `None` sozinho**: a variância do CDI não é *exatamente* zero, então a guarda dentro de `beta` (que existe e é testada) não dispara, e o número seria reportado com cara de fato. A recusa tem que estar na camada de comparação, porque é a única que sabe o *tipo* do benchmark.

### 6. `return_ratio` ("% do CDI") só com **ambos** os retornos estritamente positivos

Restrição imposta por **evidência de dado real**, não por precaução teórica. Rodando contra a base já ingerida:

| comparação | assunto | benchmark | razão produzida |
|---|---|---|---|
| IBOV × IPCA | −5,96% | +0,07% | **−85,16** |
| IBOV × CDI | −5,96% | +3,32% | **−1,80** |

A primeira é um denominador quase nulo explodindo; a segunda é "−180% do CDI", frase que não significa nada para quem lê. O terceiro caso — benchmark negativo — inverte o sentido: cair 5% enquanto o índice caiu 10% viraria "50% do benchmark", que soa como perder feio e é o oposto do ocorrido.

`excess_return` (uma **diferença** em pontos de fração) é correto nos três casos e é o número a mostrar.

## Evidence

- `backend/app/domain/portfolio/performance.py` — o índice e a justificativa de cada regra de fluxo.
- `backend/app/domain/benchmarks/comparison.py` — comparação pura; `_ratio` e a recusa do beta.
- `backend/tests/test_portfolio_performance.py` — `test_a_contribution_does_not_move_the_index`, `test_fees_show_up_as_a_loss_because_they_never_become_value`, `test_a_fully_sold_portfolio_earns_nothing_while_it_holds_nothing`.
- `backend/tests/test_benchmark_comparison_routes.py` — `test_a_contribution_does_not_make_the_portfolio_beat_the_benchmark`, ponta a ponta.
- `backend/tests/test_benchmark_comparison.py` — os três casos de recusa da razão, com os números reais nas docstrings.
- `AGENTS.md` §26 (rentabilidade de carteira), §28 (não comparar métricas incompatíveis sem normalização), §44 (não inventar dado); ADR-016 (não fabricar), ADR-018 (representação de benchmark).

## Alternatives

- **Variação patrimonial** (`(final − inicial)/inicial`) — rejeitada. Com aporte mensal de R$ 1.000 ela reporta ganho em ano de perda, e faz a carteira "bater" qualquer benchmark. É precisamente o que a §26 proíbe.
- **MWR / TIR (retorno ponderado por dinheiro)** — **não rejeitada, adiada, e é complementar.** Ela responde outra pergunta, igualmente legítima: *quanto o meu dinheiro rendeu, dado quando eu aportei*. É a métrica certa para julgar as decisões de aporte do investidor. Mas é a errada para comparar contra um índice, porque incorpora o efeito do *timing* dos aportes, que o índice não tem. Cabe uma task própria quando houver tela que a apresente ao lado da TWR, com os rótulos distinguindo as duas.
- **Reaproveitar `portfolio_snapshots`** — rejeitada por ora. A tabela existe desde a W02 e nada a escreve; derivar do ledger mantém a fonte única de verdade (§16 / ADR-002) e não introduz estado que possa divergir. Se a W11 precisar de snapshot por desempenho, que seja cache explícito de algo derivável.
- **Valorar pelo fechamento bruto em vez do ajustado** — rejeitada. O preço bruto cai na data ex-dividendo, então a série reportaria como perda um provento que o investidor recebeu. Exigiria tratar DIVIDEND como fluxo, e o resultado seria o mesmo número por um caminho mais frágil.
- **Preencher preço faltante para conseguir valorar todas as datas** — rejeitada (§44 / ADR-016). Data em que algum ativo detido não tem preço armazenado simplesmente não é valorada.

## Consequences

- ✅ A pergunta central do produto — *estou batendo o CDI?* — passa a ter resposta defensável, com aporte neutralizado.
- ✅ Nenhuma fórmula do Quant Engine foi duplicada: a carteira virou um tipo que a W07 já lia.
- ✅ A comparação é reutilizável tal como está para ativo isolado, e servirá o dashboard da W11 e o backtester da W13.
- ⚠️ **Aproximação conhecida**: um fluxo que cai numa data sem preço armazenado é neutralizado na próxima data valorável, o que credita ao capital pré-existente o que as ações novas ganharam no intervalo. Quando a data da operação **pode** ser valorada — o caso normal — não há distorção alguma. As alternativas eram piores (fabricar fechamento, esconder movimento real, ou descartar o histórico após uma lacuna). Correção verdadeira é a montante: ingerir os preços faltantes.
- ⚠️ O índice **não** é o valor da carteira. Apresentá-lo como patrimônio na W11 seria erro de leitura, não de cálculo.
- ⚠️ Falta a MWR/TIR para julgar o *timing* dos aportes. Registrado em Future Work.
