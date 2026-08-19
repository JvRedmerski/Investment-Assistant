# ADR-023 — Histórico não ajustado é armazenado como não ajustado, e nunca entra numa série de retorno

## Status

Accepted (2026-08-19, PRICE-002). **Emenda o [ADR-016](ADR-016-unadjusted-bars-are-not-stored.md)**, que continua válido para a fonte que ele descreve.

## Context

A [PRICE-001](../../backend/app/integrations/market_data/cotahist.py) trouxe o COTAHIST da B3 como fonte aberta de preços — décadas de histórico, sem token e sem cota, contra os ~63 pregões que o plano gratuito do fornecedor serve. É o mesmo movimento que o [ADR-020](ADR-020-cvm-primary-fundamentals-source.md) fez com os demonstrativos.

Só que o COTAHIST **não publica preço ajustado**, e nunca vai publicar: ele é o registro de negociação da bolsa, imprime o que foi negociado. Não há campo de ajuste no layout.

Isso colidia de frente com o ADR-016, que estabeleceu que **uma barra sem `adjusted_close` reportado não é armazenada** — e o `validate_daily_bars` a rejeitava com `MISSING_ADJUSTED_CLOSE`. Sob essa regra, **100% das barras do COTAHIST seriam rejeitadas**, e o projeto descartaria décadas de histórico aberto.

Mas o ADR-016 não estava errado. Ele foi escrito sobre uma premissa específica e verificada: o fornecedor devolve `adjustedClose: null` para a sessão fechada mais recente e **publica o valor depois**. A rejeição ali é autocorretiva — a data entra completa no sync seguinte, e o atraso é de um pregão. Ele até enumerou "relaxar a coluna para `NULL`" entre as alternativas e a **rejeitou**, com o argumento certo para aquele caso:

> Empurraria o tratamento de nulo para todo consumidor do preço, incluindo cada função de retorno da Wave 07, em troca de guardar uma barra que estará disponível completa no dia seguinte.

A premissa que muda é essa última oração. Para o COTAHIST, a barra **não** estará disponível completa no dia seguinte. Ausente não é atraso; é permanente.

### O erro que não pode ser cometido, medido em dado real

A saída preguiçosa seria `adjusted_close = close`. O tamanho do erro foi medido no arquivo real de 2024:

| ticker | data | fechamento anterior | fechamento | variação crua |
|---|---|---|---|---|
| MGLU3 | 2024-05-27 | R$ 1,32 | R$ 13,15 | **+896% num pregão** |

É o grupamento 1:10 da Magazine Luiza. Numa série tratada como ajustada, essa sessão entra em `volatility`, `max_drawdown`, `beta` e `sharpe` como se o mercado tivesse se movido 896% — e o pilar de Risco consome exatamente essas quatro. O arquivo **marca que o evento ocorreu** (`ESPECI` passa de `ON      NM` para `ON  EG  NM`, *ex-grupamento*, e `DISMES` incrementa), mas **não diz o tamanho**. Marcador não é magnitude: não há fator a derivar de "aconteceu alguma coisa".

## Decision

### 1. As duas colunas passam a significar coisas diferentes, explicitamente

- **`close`** é o que o mercado imprimiu. É o insumo correto para pergunta *point-in-time*: o P/L de um fim de exercício é o lucro reportado naquele exercício contra o preço efetivamente cotado então.
- **`adjusted_close`** é o preço de retorno total. `NULL` significa **"esta fonte não calcula ajuste"** — não "faltou", não "é igual ao close".

`asset_prices.adjusted_close` passa a aceitar `NULL` (migration `010`). Widening puro: toda linha existente veio do fornecedor e tem valor.

### 2. A semântica da ausência pertence à **fonte**, não à barra

`DailyHistoryProvider.reports_adjusted_close` declara se a fonte ajusta, e `validate_daily_bars` lê isso:

| fonte | `adjusted_close is None` significa | o que acontece |
|---|---|---|
| fornecedor (`reports_adjusted_close=True`) | ainda não publicado | **rejeita** — ADR-016 intacto, autocorreção intacta |
| COTAHIST (`False`) | nunca publicado | **armazena com `NULL`** |

Isso é o que permite emendar o ADR-016 sem revogá-lo: as duas regras coexistem porque descrevem fontes diferentes, e a distinção é declarada no lugar onde ela é verdade.

### 3. Um único ponto de passagem, e é ele que torna a coluna nula segura

A objeção do ADR-016 — "empurraria o tratamento de nulo para todo consumidor" — era real, e é respondida diretamente: **nenhum consumidor lê a coluna**. `app/domain/market_data/series.py` é o único lugar que transforma linhas em `PricePoint`, e ele **descarta linha sem ajuste**. Os três pontos que construíam a série à mão (comparativo de ativo, comparativo de carteira, pilar de Risco) passaram a chamá-lo.

### 4. Linha não ajustada é descartada, não preenchida

Série mais curta é lacuna **visível e honesta**. As funções do `app.quant` já respondem `None` com pontos de menos, então um ativo com só histórico não ajustado reporta risco **ausente** — que é o estado que o motor de score foi desenhado para tratar como normal (W09-001), e que a alocação já sabe ordenar por faixa de cobertura (ADR-021).

O que **não** se faz é reportar um número que não é o que ele diz ser.

## Evidence

- `backend/app/integrations/market_data/cotahist.py` — a fonte, e por que ela não ajusta.
- `backend/app/integrations/market_data/base.py` — `reports_adjusted_close`, `source_name`.
- `backend/app/integrations/market_data/data_quality.py` — a bifurcação por fonte.
- `backend/app/domain/market_data/series.py` — o ponto único de passagem.
- `backend/migrations/versions/010_nullable_adj_close.py` — aplicada em PostgreSQL 16 real, `alembic check` sem drift, downgrade testado.
- `backend/tests/test_unadjusted_price_history.py` — 14 testes: as duas leituras da ausência, o `source` gravado, e o grupamento da MGLU3 barrado da série de retorno.
- `backend/tests/test_cotahist_provider.py::test_the_raw_series_carries_a_reverse_split_untouched` — o +896% com registros reais.
- `AGENTS.md` §44 (nunca inventar um número), §19, §20; [ADR-014](ADR-014-indicator-missing-data-policy.md) (ausente → `None`, nunca um default).

## Alternatives

- **`adjusted_close = close` para o COTAHIST** — rejeitado, e é o núcleo do ADR. Viola a §44 e produz o +896% da MGLU3 dentro da volatilidade. Pior: depois de gravado, **é indistinguível de um ajuste real** — em dia sem provento os dois são legitimamente iguais, argumento que o próprio ADR-016 já usou.
- **Manter a coluna `NOT NULL` e rejeitar tudo do COTAHIST** — rejeitado. Descartaria décadas de histórico aberto para proteger contra um atraso de publicação que esta fonte não tem. Deixaria `pe`/`pb` permanentemente ausentes no banco real, que é o que a wave existe para destravar.
- **Tabela separada para preço não ajustado** — rejeitado. Duplicaria o conceito: `close` já é o preço negociado, em ambas as fontes. Duas tabelas obrigariam todo leitor a saber em qual procurar, o que é a mesma dispersão de responsabilidade que o ponto único de passagem elimina.
- **Derivar o ajuste da própria série de preços** (detectar o degrau e dividir) — rejeitado. É heurística vestida de medição, exatamente o que a §44 proíbe, e não distingue grupamento de queda real. O `ESPECI` diria *que* houve evento, nunca *quanto*.
- **Derivar o ajuste da contagem de ações da CVM** (`composicao_capital`, já ingerida na W09-003) — rejeitado por granularidade: a contagem é anual, e um desdobramento precisa da **data** do evento para ajustar a série. Também não cobre provento em dinheiro.
- **Preencher a lacuna com o fornecedor onde ele alcança** — rejeitado pelo mesmo motivo que o ADR-020 rejeitou mesclar campo a campo: emendaria ~63 pregões ajustados numa série crua de anos, produzindo uma série que **nenhuma fonte jamais reportou**, com uma descontinuidade artificial na junção.

## Consequences

- ✅ **Décadas de preço aberto passam a ser armazenáveis**, sem token e sem cota.
- ✅ **`pe`/`pb` destravam no banco real**: `_price_on_or_before` lê `close`, e o `close` bruto é justamente o insumo correto para múltiplo *point-in-time* (§108/109). Era a última dependência do pilar de Valuation, e a Known Issue nº 2 aponta para ela.
- ✅ **O ADR-016 continua valendo onde foi escrito**, e a autocorreção do fornecedor está preservada e testada.
- ✅ Toda linha diz de onde veio (`source`), o que antes era um default de configuração.
- ⚠️ **O pilar de Risco continua ausente para ativo que só tenha histórico do COTAHIST**, e isso é deliberado. Métrica de risco exige série de retorno total; a correção verdadeira é **a montante** — ingerir proventos e eventos societários (Known Issue nº 1, DMPL `5.04.06`/`5.04.07` da CVM é o caminho conhecido). Esta é agora a wave de maior retorno do projeto.
- ⚠️ O mesmo vale para o índice time-weighted da carteira, que valoriza posições em `adjusted_close` ([ADR-019](ADR-019-portfolio-return-is-time-weighted.md)): datas sem ajuste continuam não valoráveis, e o `performance_index` já as neutraliza (Known Issue nº 8).
- ⚠️ `adjusted_close` nulo é **permitido pelo schema em toda linha**, então o invariante deixou de ser estrutural e passou a ser mantido por um módulo. É uma troca consciente: um ponto de passagem testado, em vez de uma restrição de banco que impedia a fonte aberta de existir.
