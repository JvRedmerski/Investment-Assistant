# ADR-021 — A alocação ordena por faixa de cobertura antes do score, e o plano é derivado, nunca gravado

## Status

Accepted (2026-08-19, Wave 09 / W09-004)

## Context

A roadmap §21 termina o pipeline em `Final Score → Allocation`, e a AGENTS.md §31 é explícita sobre qual pergunta está sendo respondida:

> "Qual novo aporte melhora minha carteira atual?" — **não** "Qual ativo possui maior score?"

O score da W09-001 já responde a primeira metade: o pilar de Diversification lê a concentração atual, então o mesmo ativo pontua diferente para quem já tem 15% dele. Faltava a segunda metade — **quanto dinheiro, em quais deles**, sem violar os limites do perfil (§32) e a partir de um aporte mensal configurável (§33).

Duas coisas tornam isso mais do que "ordene e distribua".

### 1. `coverage` deixa de ser diagnóstico e vira defeito

O `AssetScore` já reporta `coverage`, a fração da fórmula em que o score de fato se apoia, e o docstring do `scoring.py` já avisava que **dois scores com coberturas diferentes não são comparáveis**. Ordenar o universo por `final_score` e pagar de cima para baixo ignora isso — e não erra ao acaso, erra **numa direção só**.

Os pilares que faltam são sempre os fundamentalistas (Quality, Valuation, Growth), e o que sobrevive a toda lacuna é Diversification, que vale ~100 para qualquer coisa que a carteira ainda não tem. Um ativo sem demonstrativo chega, portanto, carregando um score alto construído exatamente com os dois pilares que nunca estiveram em dúvida. Rankear por esse número faz **os ativos menos conhecidos ganharem sistematicamente**.

### 2. "Conservador" precisa virar aritmética antes de virar dinheiro

A §32 lista limite por ativo, por setor, de volatilidade, preferência por liquidez e menor concentração, e fecha com "os pesos exatos devem ser configuráveis. Não assumir que todos os investidores conservadores possuem exatamente a mesma alocação".

O pilar de Diversification já usava tetos de 20% por ativo e 40% por setor (`ASSET_WEIGHT_SCALE` / `SECTOR_WEIGHT_SCALE`). Repetir esses números na alocação criaria duas fontes livres para divergir.

## Decision

### 1. Piso de cobertura, e faixas de comparabilidade acima dele

- Abaixo de `min_coverage` (padrão **0,50**) o ativo **não é candidato**. Um score apoiado em um terço da fórmula descreve mais o que falta do que o ativo.
- Acima do piso, os candidatos são agrupados em faixas de largura `coverage_tier_width` (padrão **0,25**), e **uma faixa melhor sempre vence uma pior**, independentemente do score. O score decide a ordem **dentro** da faixa, onde está comparando coisas equivalentes.
- Uma faixa inferior ainda recebe dinheiro, mas **só o que a faixa acima não conseguiu absorver**.

O resultado é deliberado e às vezes desconfortável: um ativo com cobertura 1,00 e score 60 é financiado antes de um com cobertura 0,55 e score 95. A diferença de 35 pontos é, em grande parte, artefato dos pilares ausentes — não é informação sobre o ativo.

A largura de 0,25 existe para não fabricar precisão: 0,80 e 0,85 são o mesmo score com pilares ligeiramente diferentes faltando, e ordená-los estritamente é fingir uma resolução que o número não tem.

### 2. Os tetos são as próprias escalas do score, não uma segunda cópia

```python
MAX_ASSET_WEIGHT = ASSET_WEIGHT_SCALE.at_zero    # 0,20
MAX_SECTOR_WEIGHT = SECTOR_WEIGHT_SCALE.at_zero  # 0,40
```

`at_zero` é o peso em que o pilar de Diversification zera — exatamente o ponto em que a carteira deveria parar de acrescentar. Ligar os dois por construção impede o estado em que um ativo pontua bem por diversificar para uma posição que o alocador se recusa a financiar.

### 3. Todo limite é configurável, e viaja junto com o plano

`AllocationPolicy` carrega os nove parâmetros, e o endpoint aceita override por requisição. A política usada volta dentro da resposta: um plano só é interpretável ao lado dos limites que o produziram.

### 4. Os pesos são medidos contra a carteira **depois** do aporte, caixa incluído

Base = `investido + aporte`. O que os limites deixarem sem destino volta como `unallocated` e permanece na base, como caixa — que é o que é. Assim os pesos relatados são os pesos que o investidor de fato terá, e não os de uma carteira que gastou tudo.

Isso tem uma consequência visível no primeiro aporte: numa carteira vazia a base **é** o próprio aporte, então o teto de 20% vale R$ 200 por ativo. `MAX_POSITIONS` é 5 justamente por isso — `1 / 0,20` — porque com menos posições o primeiro aporte ficaria estruturalmente inexecutável.

### 5. Nada é gravado

O plano é derivado a cada leitura, como as posições (§16, [ADR-002](ADR-002-positions-derived-from-ledger.md)). Ele é função do ledger, dos scores e da política, todos já persistidos; congelar uma cópia criaria uma segunda versão da verdade que envelhece sozinha. A tabela `recommendations` continua sem uso.

## Evidence

- `backend/app/domain/recommendations/allocation.py` — módulo puro: política, ranking, tetos, motivos.
- `backend/app/domain/recommendations/service.py` — `plan_contribution`, que só carrega e delega.
- `backend/app/api/routes/portfolios.py` — `GET /portfolios/{id}/contribution-plan`, com override de cada limite.
- `backend/tests/test_contribution_allocation.py` — 28 testes com valores calculados à mão.
- `backend/tests/test_contribution_plan_routes.py` — 13 testes ponta a ponta.

## Alternatives

**Ordenar direto por `final_score`.** É o desenho óbvio e foi recusado pelo viés acima: favorece sistematicamente quem tem menos dado. Não é uma imprecisão tolerável — é um ranking que se inverte conforme a ingestão melhora.

**Exigir cobertura idêntica entre os comparados.** Mais puro e inútil na prática: as coberturas alcançáveis são somas discretas dos pesos dos pilares, e exigir igualdade exata deixaria a maioria dos universos com um candidato só.

**Financiar apenas a faixa mais alta presente.** Nunca compara faixas diferentes, o que é correto, mas desperdiça o aporte inteiro quando o único ativo da faixa de cima está no teto. O transbordo para a faixa seguinte mantém o dinheiro trabalhando **sem** jamais colocar dois números incomparáveis lado a lado.

**Distribuir proporcionalmente ao score.** Tratar o score como cardinal (um 80 recebendo 4/3 do que um 60 recebe) atribui à escala uma propriedade que ela não tem — ela é calibrada por limiares nomeados, não é uma medida de razão. O preenchimento por ordem, limitado pelo teto, usa apenas a ordenação, que é o que o score realmente sustenta.

**Gravar o plano em `recommendations`.** Além do problema de verdade duplicada, a tabela declara `suggested_amount` e `target_weight` como `Float`, o que a regra 17 proíbe para dinheiro. Persistir exigiria migration antes de existir qualquer necessidade real de histórico de recomendações.

**Aplicar os tetos contra a carteira sem o aporte.** Deixaria o peso resultante acima do teto sempre que o aporte fosse grande em relação à carteira — que é precisamente o caso do investidor no começo.

## Consequences

- O ranking **muda** quando a ingestão de dados melhora, e muda para melhor: um ativo que sobe de 0,55 para 1,00 de cobertura passa a competir numa faixa acima. Isso é a intenção, não instabilidade — e `formula_version` + `rules_version` deixam rastreável qual conjunto produziu cada plano.
- Enquanto os demonstrativos não forem ingeridos para um ativo, ele fica **abaixo do piso de cobertura** e o plano não financia nada. É a resposta honesta e é visível: cada ativo volta com `COVERAGE_BELOW_MINIMUM` e a cobertura que tinha. Quem quiser operar com menos dado baixa o piso explicitamente.
- Parte do aporte pode ficar sem destino, e isso é reportado em vez de forçado. Nos primeiros meses é o caso normal: com poucos ativos acompanhados, o teto de 20% não deixa R$ 1.000 caber.
- Ativo sem setor cadastrado é recusado por padrão (`require_sector`). Um teto que não pode ser avaliado não é um teto, e liberá-lo faria a regra deixar de valer exatamente onde o dado é mais fraco. O conserto é um campo no ativo, e a recusa diz isso.
- A carteira ainda não tem caixa modelado, então "base" é custo das posições mais o aporte. Quando a W11 trouxer valor de mercado, a base deve migrar junto com o pilar de Diversification — as duas leem a mesma exposição de propósito.
