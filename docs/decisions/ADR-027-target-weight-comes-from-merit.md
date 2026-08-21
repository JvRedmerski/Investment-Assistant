# ADR-027 — O peso-alvo sai do mérito, e a concentração vira teto em vez de termo

## Status

Accepted (2026-08-21, W10-001). Consome o [ADR-021](ADR-021-allocation-ranks-by-coverage-tier.md), que estabeleceu as faixas de cobertura e os tetos de concentração lidos das escalas do pilar de Diversificação, e segue a política de ausência do [ADR-014](ADR-014-indicator-missing-data-policy.md).

## Context

O roadmap §22 e a regra 34 do AGENTS.md pedem três números por ativo: `current_weight`, `target_weight` e `weight_gap`. Dois deles são triviais — o peso atual sai do ledger e o gap é uma subtração. **A wave inteira é o terceiro**, e nenhum dos dois documentos diz de onde ele vem.

A construção óbvia é fazer o alvo proporcional ao `final_score`, que é o número pelo qual o universo já é ordenado e o único que a W09 deixou pronto. Ela não sobrevive ao contato com o dado.

### Medido contra o banco real antes de escrever código

PETR4, variando **só** quanto dela a carteira detém:

| peso detido | `final_score` | quality | valuation | growth | risk | diversification |
|---|---|---|---|---|---|---|
| 0% | **76,72** | 97,8 | 93,5 | 76,7 | 28,3 | 100,0 |
| 5% | 73,91 | 97,8 | 93,5 | 76,7 | 28,3 | 81,2 |
| 10% | 71,10 | 97,8 | 93,5 | 76,7 | 28,3 | 62,5 |
| 15% | 68,28 | 97,8 | 93,5 | 76,7 | 28,3 | 43,8 |
| 20% | **65,47** | 97,8 | 93,5 | 76,7 | 28,3 | 25,0 |

**Nada mudou na empresa.** Os quatro pilares que descrevem o negócio são constantes em toda a tabela. O que caiu 11,25 pontos foi Diversificação, o único pilar que mede o **detentor** e não o ativo.

Isso é exatamente o que se quer para ordenar um aporte — a regra 31 diz que a pergunta é *"qual novo aporte melhora minha carteira atual?"*, e não *"qual ativo tem maior score?"*. É exatamente o que **não** se quer num alvo: um alvo proporcional a esse número **recua conforme a carteira se aproxima dele**. O investidor é informado de um gap de 4 p.p., fecha 2, e descobre que o gap agora é de 1 p.p. porque o ato de comprar baixou o alvo. O número entregue como distância não é distância até coisa nenhuma.

Existe um ponto fixo, mas não é ele que estaria sendo reportado.

## Decision

### 1. O alvo é proporcional ao **mérito**, que é o score sem Diversificação

`scoring.merit` recompõe Quality, Valuation, Growth e Risk sozinhos, renormalizando sobre os pilares que existirem — a mesma regra que `compose` aplica um nível acima, sobre um conjunto menor. Diversificação fica de fora **do alvo**, e continua inteira no score que ordena o aporte.

Medido no banco real: PETR4 tem mérito **72,61** com cobertura de mérito 1,00, contra um `final_score` de 76,72 inflado pelos 100 pontos que Diversificação dá a uma carteira vazia.

### 2. Concentração não sai do cálculo — ela muda de lugar

Tirar o pilar não é tirar o limite. Concentração volta como os **tetos** que aparam os alvos: os mesmos `max_asset_weight` (20%) e `max_sector_weight` (40%) contra os quais o pilar de Diversificação pontua, lidos do mesmo `AllocationPolicy` para que os dois não possam divergir.

A diferença é que como restrição ela é estável e como termo não é. Um teto diz "não mais que 20% aqui" independentemente do que a carteira tenha hoje; um termo de score diz "você está em 15%, logo quero menos disto", que é a recursão.

### 3. A distribuição é *water-filling*, e o teto setorial é testado **antes** do teto por ativo

Distribuir o que resta da carteira proporcionalmente ao mérito, congelar o primeiro teto que estourar, redistribuir sobre quem sobrou. Congelar em vez de aparar no lugar é o que mantém a soma certa: aparar deixaria o peso cortado sem dono mesmo quando outro ativo tinha espaço.

A ordem dos dois testes não é cosmética, e o caso foi encontrado traçando o algoritmo à mão. Com o teto por ativo primeiro, três papéis de um mesmo setor congelam a 20% cada e põem o setor em **60%**, contra um limite de 40% que nunca foi consultado. Na ordem inversa não há problema simétrico, porque o teto por ativo ganha uma segunda passagem **dentro** do espaço do setor.

### 4. A cobertura do alvo é medida sobre o mérito, e isso é mais estrito de propósito

`allocation.py` compara `min_coverage` com `AssetScore.coverage`, a fração dos **cinco** pilares. Diversificação praticamente nunca falta — carteira vazia ainda tem peso zero —, então aquele denominador carrega 0,15 constantes que não dizem nada sobre o quanto se sabe do ativo.

A cobertura de mérito divide só pelos pesos de mérito. Sob o mesmo `min_coverage` de 0,50, isso exige 0,425 de mérito onde o alocador exige 0,35. A severidade extra é deliberada: o alocador tem as **faixas de cobertura** como segunda linha de defesa contra comparar dois números incomparáveis, e um peso-alvo não tem nenhuma — é um número só, entregue ao investidor como destino.

A armadilha é viva neste banco, não hipotética: **ITUB4 marca 92,47 com cobertura 0,40**, o maior número do universo, montado exclusivamente sobre os dois pilares que nunca faltam. Sob a regra do alvo ela **não tem mérito nenhum** (só Risco disponível) e não recebe alvo.

### 5. A elegibilidade também testa mérito, e não o `final_score`

Reaproveitar `allocation.ineligibility` seria mais curto e traria Diversificação de volta pela porta dos fundos: um ativo poderia **perder o alvo justamente por ter sido comprado**, que é a circularidade que este ADR existe para remover. Os quatro veredictos são os mesmos e o vocabulário (`Exclusion`) é compartilhado; o que muda é o número testado.

### 6. Os alvos não precisam somar 1, e o resto volta nomeado

Com um único ativo pontuável e teto de 20%, os alvos somam 0,20 e **0,80 não têm dono**. Nada é redistribuído para o total parecer inteiro: isso entregaria o resto a quem por acaso fosse pontuável, que é justamente o canto menos conhecido do universo. Ele volta como `unassigned`, do mesmo jeito que o plano de aporte reporta `unallocated`.

Essa não é uma hipótese de laboratório — é a forma exata do banco de hoje, com PETR4 sozinha em 0,20 e 0,80 sem dono.

### 7. Ativo detido que o modelo não sabe pontuar tem alvo zero, e isso não é ordem de venda

O gap fica negativo pelo tamanho da posição. É a aritmética honesta de uma posição que o modelo se recusa a endossar, e não uma recomendação de vender: nenhum plano deste projeto vende, e uma carteira que recebe aportes mensais fecha esse gap por diluição. A linha aparece na tabela com o motivo nomeado — sumir com ela esconderia justamente a parte da carteira que a tabela existe para explicar.

## Alternatives considered

| alternativa | por que não |
|---|---|
| **Alvo ∝ `final_score`** | a tabela acima: a trave anda. É a alternativa que parecia óbvia e a razão de existir deste ADR |
| **Alvo ∝ ponto fixo de `final_score`** | existe e é caro de calcular; e resolveria a convergência sem resolver o problema de comunicação — o alvo ainda seria diferente para dois investidores por causa do que já têm, o que não é o que a palavra "alvo" promete |
| **Alvo igualitário (1/N sobre os elegíveis)** | não usa a informação que quatro pilares custaram três waves para produzir, e faz o alvo de um ativo depender de quantos outros existem no cadastro |
| **Alvo definido pelo investidor, gravado numa tabela** | é o modelo das ferramentas comerciais e é legítimo, mas responde a uma pergunta diferente ("estou seguindo meu plano?") e não a do projeto ("onde o próximo aporte melhora a carteira?"). Fica registrado como extensão possível, não como o padrão |
| **Alvo ∝ (mérito − piso)** | espalha demais: mérito 51 contra 100 viraria 2% contra 98%. Proporcional ao mérito cru limita o espalhamento a 2:1 acima do piso de 50, o que é uma propriedade conservadora que vale manter |

## Consequences

- `target_weight`, `current_weight` e `weight_gap` existem e são decomponíveis: cada linha nomeia o teto que a aparou ou o motivo pelo qual não tem alvo.
- O modelo tem versão própria (`TARGET_MODEL_VERSION`), separada de `SCORING_FORMULA_VERSION` e de `ALLOCATION_RULES_VERSION`, porque os três mudam por motivos diferentes (regra 30).
- **O alvo é estável sob compra.** Comprar um ativo muda `current_weight` e fecha o gap; não mexe no alvo. Essa é a propriedade que a wave inteira comprou.
- **Um universo pequeno deixa a maior parte da carteira sem alvo**, e o sistema diz isso em vez de escondê-lo. Aumentar a cobertura de alvo é aumentar a cobertura de **fundamentos** — cadastrar setor e sincronizar demonstrativos —, não afrouxar o modelo.
- Nada é gravado: um alvo é derivado do ledger, dos scores e da política, como as posições e os planos (regra 16, [ADR-002](ADR-002-positions-derived-from-ledger.md)).
- `AllocationPolicy` ganhou `rebalance_band` (2 p.p.) e `Exclusion` ganhou `NO_MERIT_SCORE`. Os dois são aditivos e nenhum comportamento da W09 mudou.
