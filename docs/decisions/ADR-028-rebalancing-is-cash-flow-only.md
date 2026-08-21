# ADR-028 — Rebalancear é dirigir aporte, nunca vender; e todo gap é medido na carteira depois do dinheiro

## Status

Accepted (2026-08-21, W10-003). Consome o [ADR-027](ADR-027-target-weight-comes-from-merit.md) (de onde vem o peso-alvo) e reusa a política do [ADR-021](ADR-021-allocation-ranks-by-coverage-tier.md).

## Context

A W10-001 entregou o alvo e a W10-002 a tabela de desvio. Faltava a pergunta que o desvio não responde: **o que fazer com ele**. Duas decisões precisavam ser tomadas, e a segunda só apareceu ao rodar o pipeline contra o banco real.

## Decision

### 1. O plano nunca vende

A regra 34 lista o que a recomendação deve priorizar e **todos os itens são de compra** — *"ativos que estejam abaixo do peso-alvo"*. Este módulo leva isso ao pé da letra: nenhuma linha do plano é uma venda, e posição acima do alvo é fechada por **diluição** ao longo dos aportes seguintes.

Não é escrúpulo, é a aritmética do investidor deste projeto. Uma venda realiza imposto sobre ganho de capital numa carteira cuja tese inteira é capitalizar, e paga corretagem nas duas pontas para mover dinheiro que o aporte do mês seguinte moveria de graça. Com ~R$ 1.000 entrando todo mês contra uma carteira de algumas dezenas de milhares, o fluxo de caixa é alavanca suficiente para corrigir desvio sozinho.

A consequência é dita e não escondida: uma carteira muito acima do alvo num papel **continua** muito acima por um tempo, e a tabela de desvio segue dizendo isso. Um ativo acima do alvo volta em `skipped` com `ABOVE_TARGET`, e vai continuar voltando.

### 2. Toda decisão é tomada sobre a carteira **depois** do aporte, não sobre a de hoje

Esta é a decisão que **o teste contra o banco real pegou, e que nenhum teste unitário pegaria** — porque os testes unitários também tinham sido escritos sob a premissa errada.

A primeira versão usava dois referenciais ao mesmo tempo: o portão de elegibilidade lia o peso que a tabela de desvio reporta (medido sobre o **investido hoje**), enquanto todo o dimensionamento — `needed`, espaço do setor, espaço do ativo — já rodava sobre `invested + contribution`.

Medido no banco real, com PETR4 a R$ 300 e MGLU3 a R$ 900:

| | primeira versão | corrigida |
|---|---|---|
| PETR4 alocada | **R$ 0** (`ABOVE_TARGET`) | **R$ 140** (`TARGET_WEIGHT`) |
| não alocado | R$ 1.000 | R$ 860 |
| distância a percorrer | 0 → **0,0636** | 0 → **0** |

PETR4 está em 25% contra alvo de 20%, logo *acima* — na leitura de hoje. Recusada por isso, os R$ 1.000 ficam em caixa, a base vira R$ 2.200 e a mesma posição fica em **13,6%**: mais abaixo do alvo do que estava acima, **por ter sido recusada por estar acima dele**. O plano deixava dinheiro parado e afastava a carteira do destino.

Então o portão, a banda e a ordenação passam a rodar sobre `held / (invested + contribution)`. Não é uma regra nova: é a mesma base que o resto do módulo já usava, e o peso pré-aporte no portão era a inconsistência.

**As duas leituras chegam ao investidor.** Cada linha carrega `weight_gap` como a tabela de desvio reportou e `needed` como o dinheiro que o plano de fato agiu sobre. Elas respondem perguntas diferentes, e o caso em que discordam é justamente o interessante: um papel pode estar *no* alvo hoje e ser comprado mesmo assim, porque o aporte vai diluí-lo.

### 3. A ordenação é por gap, e não é a do alocador

O `allocation.py` ordena por faixa de cobertura e depois por score, e precisa das faixas porque compara scores apoiados em quantidades diferentes de evidência. Aqui a ordem é o gap, e as faixas **já foram gastas**: um alvo só existe para ativo cujo **mérito** passou pelo piso de cobertura (ADR-027), então tudo que chega a esta ordenação passou pelo mesmo teste.

Dois planos, duas ordens, uma política. O plano de aporte responde *"onde dinheiro novo melhora mais a carteira"*; este responde *"o que está mais longe de onde deveria estar"*.

### 4. O alvo é o teto que aperta, e ele engole o teto por ativo

Uma alocação para em `target * base - held`. Como nenhum alvo pode exceder `max_asset_weight` (o ADR-027 apara ali), esse valor nunca é maior do que o teto por ativo permitiria — o teto por ativo continua sendo avaliado e **não consegue apertar primeiro**.

O teto **setorial** ainda aperta, e o caso é real: um setor carregado num papel que o modelo não sabe pontuar não tem alvo próprio para segurá-lo, e financiar um papel pontuado dentro dele empurraria o setor além do limite de qualquer jeito.

### 5. `max_share_per_position` deliberadamente **não** se aplica

O plano de aporte limita qualquer ativo a 40% de um aporte porque ordena por **score**, que é estimativa ruidosa, e o dinheiro de um mês inteiro caindo sem diluição sobre um ranking ruidoso é risco que vale proteger.

Este plano não emite julgamento novo sobre qual ativo é melhor: ele fecha uma distância **medida** até um destino que os tetos de concentração já aparam, e estouro é estruturalmente impossível porque o alvo aperta primeiro. A proteção não teria contra o que proteger, e em troca deixaria dinheiro ocioso exatamente no caso em que o investidor mais quer que ele seja gasto — um gap grande e todo o resto no alvo.

### 6. `underweight_after` pode ser **maior** que `underweight_before`, e isso é reportado

Dinheiro que os limites deixam sem colocar fica como caixa **dentro da base**, e diluiu todo mundo, inclusive quem já estava no alvo. Reportar um número só de "drift" esconderia isso. Os dois vêm, e a diferença entre eles é o que o plano de fato conseguiu.

## Consequences

- `GET /portfolios/{id}/rebalance-plan` existe e é decomponível: cada linha traz o que foi colocado, o que faltava (`needed`), o teto que decidiu, e o peso antes e depois; cada recusa traz o motivo nomeado.
- Quatro versões passam a ser registradas por plano (regra 30): fórmula do score, modelo de alvo, regras de rebalanceamento e a política ecoada inteira.
- **A tabela de desvio e o plano podem discordar sobre um mesmo ativo**, de propósito. Quem lê os dois precisa saber que a primeira mede a carteira de hoje e o segundo a carteira que o aporte cria.
- Nada é gravado (regra 16, [ADR-002](ADR-002-positions-derived-from-ledger.md)).
- Fica **de fora**, e nomeado: nenhuma venda, nem mesmo para o caso em que um papel passa de qualquer teto por evento societário. Se isso passar a ser necessário, é decisão de produto e pede ADR novo — não uma exceção enfiada aqui.
