# ADR-034 — A grade é um conjunto de hipóteses, não um espaço de busca; e o número que se reporta é o out-of-sample

## Status

Accepted (2026-08-22, W14-002 / W14-003). Implementa as regras **60**, **61** e **62** do [AGENTS.md](../../AGENTS.md). Consome o [ADR-032](ADR-032-the-backtest-stops-where-the-total-return-series-stops.md), que decide qual história pode ser replayada, e é irmão do [ADR-035](ADR-035-equal-segments-from-an-empty-portfolio.md), que decide como ela é cortada.

## Context

A regra 60 proíbe *"ajustar parâmetros até obter o melhor resultado histórico **sem
validação**"*, com `RSI = 31.7` como o anti-padrão nomeado, e pede *"parâmetros simples e
robustos"*. A 61 exige `Training / Validation / Test` e proíbe calibrar e validar sobre a mesma
história. A 62 pede que a janela **ande** e que a estratégia seja avaliada quanto à
**estabilidade**.

O que a W14 tinha em mãos: a estratégia deste projeto é `allocate_contribution`, e ela é
parametrizada por uma `AllocationPolicy` de dez campos. Qualquer um deles pode ser variado, e
variar todos é exatamente o que a regra 60 descreve.

O ponto difícil não é obedecer a regra 61 — é obedecer a 60 **enquanto** se obedece a 61.
Empilhar validação atrás de uma varredura não desfaz a varredura: dá a ela um selo.

## Decision

### 1. Um parâmetro por vez, com a pergunta escrita ao lado

A diferença entre conjunto de hipóteses e espaço de busca aparece quando ele cresce. Espaço de
busca é **varrido**: mais pontos deixam o melhor ponto melhor — melhor em descrever o ruído em
que foi ajustado. Conjunto de hipóteses é **perguntado**: cada entrada responde uma pergunta que
alguém formularia em palavras antes de ver qualquer número.

Então `policy_grid(base)` devolve a política do chamador mais **uma variante de campo único**
por hipótese. Sete candidatos:

| nome | muda | pergunta |
|---|---|---|
| `default` | — | a política como configurada é a de ficar? |
| `min-score-30` / `min-score-70` | `min_score` | financiar score fraco ajuda? e recusar tudo menos o mais forte? |
| `min-coverage-25` / `min-coverage-75` | `min_coverage` | um piso de evidência mais frouxo paga os ativos que deixa entrar? e um mais rígido paga os que corta? |
| `max-positions-3` / `max-positions-8` | `max_positions` | concentrar o aporte ajuda? e espalhar? |

O produto cartesiano dos mesmos três eixos seria **dezoito**, e dezoito resultados sobre três
folds são uma varredura vestida de walk-forward.

`question` é **parte do resultado**, não documentação dele: candidato que não se enuncia como
pergunta é parâmetro varrido.

### 2. A grade é relativa à política do chamador, e versionada

Quem já apertou `min_coverage` está perguntando se **os seus** limites são estáveis; variar os
defaults de outra pessoa responde pergunta que ninguém fez. Variante que aterrissa na própria
base é descartada — ela *é* a base, e duas linhas idênticas num ranking são ruído com segundo
nome.

`WALK_FORWARD_GRID_VERSION` fica ao lado de `SCORING_FORMULA_VERSION` e
`ALLOCATION_RULES_VERSION` (regra 113): uma figura de estabilidade é afirmação sobre **este**
conjunto de hipóteses, e o conjunto mudar sem a versão mudar torna dois resultados
silenciosamente incomparáveis.

### 3. Treino ordena, validação escolhe, teste só reporta

- **Treino** pergunta à grade inteira.
- **Validação** pergunta só à shortlist (três), sobre história que a ordenação não viu. Existe
  porque o melhor candidato de um período é muito frequentemente o melhor **ajuste àquele
  período**, e um passo à frente é o teste mais barato de se a resposta sobrevive.
- **Teste** roda o vencedor e mais ninguém.

**Nada medido no teste alcança uma seleção.** É a regra 61 inteira, e é a única razão de um
número out-of-sample significar alguma coisa.

Shortlist de três: o bastante para o vencedor do treino não se confirmar sozinho, pouco o
bastante para a validação não virar um segundo treino — que é justamente o que a regra 61
separa os dois para evitar.

### 4. A figura que responde a pergunta é a **degradação**, não o retorno

`in_sample - out_of_sample`: o que o vencedor marcou na validação menos o que marcou no teste.
Estratégia cujo out-of-sample acompanha o in-sample tem parâmetro que descreve alguma coisa; a
que desaba tem parâmetro que descrevia a amostra.

E `selection_rate` é a outra metade: walk-forward que escolhe vencedor diferente a cada fold
achou **ruído**, não parâmetro.

### 5. Empate vai para a política já em produção; e quem não pode ser pontuado não é ranqueado

`sorted` é estável e a grade põe o baseline primeiro, então variante nunca desloca o que está
rodando por empatar com ele. Verificado contra o banco real: no fold trimestral de 2025,
`default`, `min-coverage-25` e `min-coverage-75` empataram em 0,0037 na validação e o `default`
ficou.

Candidato sem valor de objetivo é **ausente da ordenação**, não último — tratá-lo como pior nota
deixaria um candidato ser batido por uma falha de medição. Mesma leitura que `profit_factor`
faz de amostra sem perdas.

### 6. Objetivo é enum fechado, e sem fallback silencioso

Dois, ambos maximizados: `sharpe` (padrão) e `total-return`. Padrão risk-adjusted porque a regra
32 põe o perfil conservador como restrição quantitativa, e porque ordenar por retorno cru é o
que a regra 60 vigia mesmo com validação atrás.

Sharpe precisa da taxa livre de risco, que este projeto lê do CDI e é `None` até ele ser
ingerido. Nesse caso o fold **recusa** (`OBJECTIVE_UNAVAILABLE`) em vez de cair para
`total-return`: fallback silencioso tornaria duas execuções do mesmo comando incomparáveis
conforme o que estivesse no banco.

Objetivo definido pelo chamador como expressão livre foi recusado pela mesma razão da regra 60 —
objetivo que pode ser qualquer coisa é objetivo que pode ser escolhido **depois** de ver os
resultados.

## Evidence

- `backend/app/domain/backtesting/grid.py` — `policy_grid`, `PolicyCandidate`, `BASELINE`, `WALK_FORWARD_GRID_VERSION`.
- `backend/app/domain/backtesting/objectives.py` — `SelectionObjective`, `SegmentMetrics`, `OBJECTIVE_UNAVAILABLE`.
- `backend/app/domain/backtesting/walkforward.py` — `_run_fold`, `_ranked`, `SHORTLIST`, `Stability`.
- `backend/app/api/routes/backtests.py` — `GET /api/v1/backtests/walk-forward`.
- `backend/tests/test_walk_forward_grid.py`, `test_walk_forward_service.py`, `test_walk_forward_routes.py`.
- **Verificado no banco real (2026-08-22)**, PETR4+BBAS3, três folds anuais, objetivo `total-return`:

  | fold | vencedor | in-sample | out-of-sample | degradação |
  |---|---|---|---|---|
  | 0 | — (`NO_POSITION_TAKEN`) | — | — | — |
  | 1 | `min-score-30` | 46,20% | **101,38%** | −0,5518 |
  | 2 | `min-score-70` | 101,58% | **11,34%** | **+0,9024** |

  `selection_rate` **0,50**, `stdev` 0,6367, `degradation_mean` 0,1753. O fold 2 é o caso de
  livro: o vencedor foi escolhido por **0,2 ponto percentual** sobre o segundo e perdeu **90
  pontos** de retorno fora da amostra. E a `default` — a política que o projeto entrega — não
  foi selecionada em fold nenhum. **A leitura honesta desse resultado é que os parâmetros não
  são estáveis**, que é exatamente o que a wave existe para conseguir dizer.

## Alternatives

| Alternativa | Por que não |
|---|---|
| **Produto cartesiano dos mesmos eixos** | Dezoito candidatos sobre três folds é varredura, e a regra 60 é sobre não entregar varredura. Um-a-um mantém cada resultado atribuível a uma pergunta. |
| **Otimizador contínuo** (grid fino, ou busca) | `RSI = 31.7` é o exemplo literal da regra 60. Valor redondo que ninguém escolheu olhando resultado é a única propriedade que o leitor não consegue conferir sozinho. |
| **Só treino e teste**, sem validação | Metade barata da regra 61. Sem o passo intermediário, o vencedor do treino vai direto ao teste e a primeira evidência de que ele não generaliza aparece justamente onde ela já não pode ser usada. |
| **Fallback de `sharpe` para `total-return`** quando falta CDI | Duas execuções do mesmo comando passariam a medir coisas diferentes conforme o banco. Recusa nomeada diz ao chamador o que fazer; fallback esconde. |
| **Reportar o melhor fold** | É o resultado histórico escolhido a posteriori, com três chances em vez de uma. A wave existe contra isso. |
| **Ranquear por retorno do dinheiro** (patrimônio sobre aportado) | Contaminado pelo timing do aporte, que é precisamente o que o [ADR-019](ADR-019-portfolio-return-is-time-weighted.md) neutraliza. A defasagem entre índice e dinheiro fica **nomeada** em vez de corrigida com uma segunda definição de retorno — ver *Future Work*. |

## Consequences

- Uma resposta do `/walk-forward` é grande: 7 candidatos × (1 treino + 3 validação) + 1 teste por fold. A política **não** é repetida por linha — aparece uma vez em `candidates[]`, e `name` é o que junta.
- A rota roda muitos backtests. Correção antes de performance (regra 136); medido, três folds anuais sobre dois ativos levam ~5,6 s contra o Postgres real.
- Acrescentar candidato à grade **exige** subir `WALK_FORWARD_GRID_VERSION`, e resultados de versões diferentes não devem ser comparados.
- O objetivo mede o dinheiro **aplicado**, não o dado — ver [ADR-035](ADR-035-equal-segments-from-an-empty-portfolio.md) e *Future Work* no [PROJECT_STATUS](../PROJECT_STATUS.md).
