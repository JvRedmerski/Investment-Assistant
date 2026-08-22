# ADR-035 — Os três segmentos têm o mesmo tamanho, e cada um parte de carteira vazia

## Status

Accepted (2026-08-22, W14-001 / W14-003). Irmão do [ADR-034](ADR-034-the-grid-is-a-hypothesis-set-not-a-search-space.md), que decide **o que** é comparado; este decide **sobre o quê**. Consome o [ADR-032](ADR-032-the-backtest-stops-where-the-total-return-series-stops.md), que decide qual história pode ser replayada, e o [ADR-028](ADR-028-rebalancing-is-cash-flow-only.md), que é por que a carteira só cresce.

## Context

A regra 62 pede `Train → Validate → Test → Move window → Repeat`. Isso deixa duas perguntas em
aberto que nenhuma regra responde, e as duas mudam o que os números significam:

1. **Os três segmentos precisam ter o mesmo tamanho?** O uso comum é treino longo e teste curto.
2. **O segmento de teste continua a carteira que o treino construiu, ou recomeça?**

Elas parecem detalhe de implementação e não são. A estratégia sob teste constrói carteira a
partir de **aporte mensal**, e ela nunca vende ([ADR-028](ADR-028-rebalancing-is-cash-flow-only.md)).
Duas consequências:

- **O tamanho do segmento muda o que ele mede.** Três meses são três aportes numa carteira que
  estava vazia em janeiro. Doze são doze numa carteira que já tem pesos, setores e um pilar de
  Diversificação lendo isso de volta — o mesmo pilar que faz a PETR4 cair de 62,28 para 35,83 no
  instante em que passa a ser detida ([ADR-027](ADR-027-target-weight-comes-from-merit.md)).
- **A idade da carteira é um confundidor da própria coisa que a wave mede.** A afirmação da W14
  é uma comparação: in-sample contra out-of-sample. Se o teste for mais curto que a validação,
  parte da degradação é estratégia e parte é carteira mais nova — e ninguém consegue dizer qual
  parte.

## Decision

### 1. Um único `segment_months`: treino, validação e teste têm o mesmo tamanho

O confundidor é removido **por construção**, não corrigido depois. É a mesma postura do
`allocation`, que recusa ordenar dois scores de cobertura diferente em vez de ajustar um ao
outro: duas figuras não comparáveis não viram comparáveis por ajuste.

Padrão de **12 meses** cada — três anos por fold. Redondo e grosso de propósito (regra 60):
segmento longo o bastante para a carteira parar de ser uma primeira compra, e doze meses é o
menor intervalo que cobre um ciclo completo dos demonstrativos anuais que o score lê.

O passo padrão é igual ao segmento, que é o walk-forward rolante do livro: o treino de um fold é
a validação do anterior, e os segmentos de **teste** ladrilham a história sem se sobrepor. É o
que faz uma figura out-of-sample por fold somar uma afirmação sobre a estratégia, em vez do
mesmo período contado duas vezes.

### 2. Todo segmento parte de carteira vazia

A execução não herda nada: mesmo caixa inicial, mesmas posições ausentes, mesmo tamanho de
intervalo. Então a **única** coisa que difere entre dois candidatos — e entre in-sample e
out-of-sample — é a política e o período.

Isso é o que torna a comparação uma comparação.

⚠️ **O custo é real e está dito em todo lugar que reporta o número**: um segmento mede a
estratégia **acumulando**, não rodando sobre carteira madura. O pilar de Diversificação lê
carteira vazia no primeiro aporte de cada segmento, então o walk-forward avalia o comportamento
inicial do alocador.

### 3. Fold que não cabe é recusado por nome, nunca encolhido

Três segmentos precisam de `3 × segment_months`. História mais curta → `WINDOW_TOO_SHORT`, com
`required_months` e `available_months`. **Nunca** segmentos aparados até caberem: isso produziria
resultado com cara de validado a partir de janela que não validou nada.

E não é hipotético. Com os quatro ativos acompanhados, o
[ADR-032](ADR-032-the-backtest-stops-where-the-total-return-series-stops.md) trunca a janela
replayável em **nove meses** (`bounded_by: ITUB4`), então o esquema padrão recusa contra o banco
real. A correção é **a montante** — dimensionar os eventos societários que faltam — e nunca
relaxar a regra.

### 4. Candidato que não preencheu ordem nenhuma **não é ranqueado**

Achado ao rodar contra o banco real (W14-005), e não alcançável por fixture. `performance_index`
sobre um ledger de depósitos sem compra nenhuma é achatado em 100 **por construção**, então o
segmento reporta retorno total de exatamente **zero**.

E zero ganha de todo candidato que aplicou e perdeu dinheiro. Uma política que não financiou nada
venceria qualquer ano de queda, na força de uma figura que mediu carteira nenhuma.

Então o candidato é **não-ranqueável** (`NO_POSITION_TAKEN`) em vez de pontuado em zero — mesma
leitura que `profit_factor` faz de amostra sem perdas. O que ele fez continua reportado:
`trades` em zero é o fato, e é um achado sobre a política.

Quando **todos** os candidatos de um fold dizem isso, o fold recusa com esse nome e não com
`OBJECTIVE_UNAVAILABLE`: *"sua política não financiou nada aqui"* e *"não há CDI cobrindo este
segmento"* são mensagens diferentes, e juntá-las esconderia a primeira atrás de um problema de
dado.

## Evidence

- `backend/app/domain/backtesting/folds.py` — `WalkForwardScheme`, `_segments`, `WINDOW_TOO_SHORT`, `SEGMENT_MONTHS`.
- `backend/app/domain/backtesting/walkforward.py` — `_run_candidate`, `NO_POSITION_TAKEN`, `_no_ranking_reason`.
- `backend/tests/test_walk_forward_folds.py` — os três segmentos ladrilhando o fold, o passo, a recusa, a ancoragem de fim de mês.
- `backend/tests/test_walk_forward_service.py::test_a_candidate_that_never_bought_anything_does_not_rank_at_zero`.
- **Verificado no banco real (2026-08-22)**:
  - Universo dos quatro, esquema padrão: `required=36m`, `available=9m`, `refusal=WINDOW_TOO_SHORT`, `bounded_by=ITUB4`.
  - Universo dos quatro, esquema trimestral: **exatamente um fold**, `SINGLE_FOLD` na estabilidade, e o empate triplo em 0,0037 ficando com o `default`.
  - PETR4+BBAS3, três folds anuais: o fold 0 tem `NO_POSITION_TAKEN` — só `min-coverage-25` operou no treino, e na validação não operou.

## Alternatives

| Alternativa | Por que não |
|---|---|
| **Treino longo, teste curto** (o uso comum) | Torna in-sample e out-of-sample **não comparáveis** para esta estratégia: parte da degradação seria a idade da carteira. O uso comum pressupõe estratégia cujo desempenho não depende de há quanto tempo ela roda; esta depende, pelo pilar de Diversificação e pelos tetos de concentração. |
| **Replay contínuo**, o teste herdando a carteira do treino | Mais fiel à operação e destrói a comparação: o teste herdaria o que o **candidato vencedor** por acaso comprou, então in-sample e out-of-sample deixariam de ser o mesmo experimento. Exigiria ainda um estado de abertura no motor puro, que a wave consome e não altera. |
| **Aparar os segmentos até caberem** na janela curta | Produz três folds de dois meses e um relatório com cara de validado. A janela curta é sintoma do [ADR-032](ADR-032-the-backtest-stops-where-the-total-return-series-stops.md); a correção é ingerir evento societário, não afrouxar método. |
| **Pontuar em zero quem não operou** | Era o comportamento antes da W14-005, e é plausível-e-errado: zero venceria qualquer ano de queda. Exatamente a classe de defeito que o [ADR-026](ADR-026-corporate-action-magnitude-and-the-completeness-rule.md) nomeia — *"não é uma série mais curta, é uma errada e plausível"*. |
| **Data de entrada por ativo** (universo que cresce no meio da execução) | Ficou registrada no [ADR-032](ADR-032-the-backtest-stops-where-the-total-return-series-stops.md) como *"fica para a W14, que já move janelas por construção"*. Deliberadamente **não** feita: a W14 move janelas de **medição**, e universo que cresce no meio muda a **estratégia sob teste**, não a validação dela. Fica em *Future Work*. |

## Consequences

- Uma janela de `3n` meses produz um fold; `4n`, dois. Com um fold só, todo agregado de estabilidade vem ausente e `refusal = SINGLE_FOLD` — média de uma observação e dispersão zero leriam como *perfeitamente estável*.
- O universo acompanhado hoje **não suporta** o esquema padrão. Isso é a resposta correta e é também um item de trabalho: ampliar a janela é ingerir os eventos societários de ITUB4 e MGLU3.
- Como cada segmento recomeça, o walk-forward mede o alocador na fase de acumulação. Avaliar a estratégia sobre carteira madura precisaria do replay contínuo — que é a alternativa recusada acima e continua recusada pela mesma razão.
