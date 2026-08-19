# Session Handoff

## Last Updated

2026-08-19

## Last Completed Work

### Wave PRICE — Histórico de preços de fonte aberta (B3 COTAHIST)

Wave **inserida fora da ordem do roadmap**, escolhida pelo usuário entre as duas opções que a
sessão anterior deixou registradas. Três tasks, três commits.

O movimento é o mesmo que a W09-002 fez com os demonstrativos: trocar um fornecedor com cota por
um arquivo público do próprio mercado. O plano gratuito da Brapi serve um `range` de `3mo`
ancorado em hoje — cerca de 63 pregões, sem parâmetro de data inicial. A B3 publica a série
COTAHIST aberta, sem token, sem cota, e décadas atrás.

---

### PRICE-001 — O provider, o parser e o cache (`8491ea0`)

`B3CotahistProvider` + `CotahistArchive`. Um ZIP por ano civil (~79 MB), texto de posição fixa,
245 bytes por registro, latin-1.

**A separação de interface que a task obrigou**: o COTAHIST serve histórico mas **não cota** —
é arquivo de fim de dia. Implementá-lo como `MarketDataProvider` significaria escrever um
`get_quote` que devolve o fechamento de ontem vestido de cotação. Então `MarketDataProvider` foi
partido: `DailyHistoryProvider` (só histórico) e `MarketDataProvider` (histórico **+** cotação),
o segundo herdando do primeiro. A ingestão passou a pedir o estreito, porque é só disso que ela
precisa.

**Validado contra o arquivo real de 2024 antes de escrever qualquer fixture**, e duas coisas
mudaram o código:

1. **`FATCOT` é fator de cotação de verdade, não formalidade.** FNOR11 é cotado por **1.000**
   ações e SMLL11 por **10** (504 registros em 2024). Os preços são divididos por ele, e a
   normalização foi **reconciliada contra o volume financeiro do próprio registro**:
   `VOLTOT/QUATOT` dá R$ 0,00070125 por ação no FNOR11, que só o valor normalizado alcança —
   o cru (0,71) erra por mil. É a mesma técnica que a W09-003 usou com o LPA, e pela mesma razão:
   um arquivo que não declara escala precisa ser conferido contra ele mesmo.
2. **`adjusted_close` é `None`, jamais copiado do `close`.**

Distilação no download: só mercado à vista (`TPMERC=010`), gzip, **14,9 MB de 79 MB**. O resto
são opções — 89% do arquivo — que nada neste projeto lê. Ano fechado fica em cache para sempre;
o ano corrente grava no **nome do arquivo** até onde alcança e é rebaixado quando pedem mais
adiante, porque congelá-lo como um ano fechado pararia a série de avançar.

### PRICE-002 — A ausência de ajuste virou dado ([ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md), `d44d183`)

Esta é a task de desenho da wave, e ela colidiu de frente com uma decisão anterior.

O **ADR-016** estabeleceu que barra sem `adjusted_close` **não é armazenada**, e estava certo:
o fornecedor publica o ajuste um pregão depois, então rejeitar adia um dia e o sync seguinte
insere completa. Ele até considerou tornar a coluna nula e **rejeitou**, com o argumento certo
*para aquele caso*: espalharia tratamento de nulo por todo consumidor "em troca de guardar uma
barra que estará completa amanhã".

**O COTAHIST quebra a última oração.** Ele não vai publicar ajuste amanhã nem nunca — é o
registro de negociação da bolsa. Sob a regra antiga, **100% das suas barras seriam rejeitadas**,
e o projeto descartaria décadas de histórico aberto para se proteger de um atraso que esta fonte
não tem.

A saída foi mover a semântica da ausência para a **fonte**, não para a barra:
`reports_adjusted_close` distingue os dois casos, e o validador bifurca. ADR-016 continua valendo
onde foi escrito, testado, com autocorreção intacta.

E a objeção dele foi **respondida, não ignorada**: `app/domain/market_data/series.py` é o **ponto
único** que constrói série de retorno, e linha sem ajuste não entra. Os três lugares que faziam
isso à mão (comparativo de ativo, comparativo de carteira, pilar de Risco) passam por ele.
Nenhum consumidor lê a coluna direto.

**O tamanho do erro que isso evita, medido em dado real**: MGLU3 fez grupamento 1:10 em
2024-05-27. Na série crua, R$ 1,32 → R$ 13,15 = **+896% num pregão**. Tratada como ajustada,
essa sessão entra em `volatility`, `max_drawdown`, `beta` e `sharpe` — os quatro insumos do
pilar de Risco. O arquivo **marca** que houve evento (`ESPECI` vira `ON  EG  NM`) e **não diz o
tamanho**: marcador não é magnitude.

Migration `010` aplicada em PostgreSQL 16 real, `alembic check` limpo, downgrade testado.

### PRICE-003 — O backfill, e a validação que a wave existia para produzir (`7f86cf8`)

`POST /assets/{ticker}/prices/backfill`, ao lado do `/prices/sync` que vai ao fornecedor. Ambos
escrevem em `asset_prices`, nenhum sobrescreve data gravada, então compõem em qualquer ordem. A
tradução de erro que os dois compartilham foi **extraída, não copiada**.

Contra o banco real, que tinha PETR4 com 6 exercícios da CVM e `asset_prices` **vazia**:

```
backfill 2020–2025 → 1.495 pregões inseridos, 0 rejeitados (383 s a frio)
```

`pe` e `pb` eram `None` nos seis exercícios:

| exercício | P/L | P/VP | LPA |
|---|---|---|---|
| 2020-12-31 | 52,01 | 1,20 | R$ 0,54 |
| 2021-12-31 | 3,48 | 0,96 | R$ 8,18 |
| **2022-12-31** | **1,70** | 0,88 | R$ 14,44 |
| 2023-12-31 | 3,87 | 1,27 | R$ 9,63 |
| **2024-12-31** | **12,74** | **1,27** | R$ 2,84 |
| 2025-12-31 | 3,61 | 0,96 | R$ 8,54 |

2024 fecha contra número público: LPA R$ 2,84 sobre fechamento de R$ 36,19 dá 12,74; patrimônio
por ação de R$ 28,40 dá 1,27. E o P/L de **1,70 em 2022** é o que o mercado de fato viu no ano
dos lucros recordes da Petrobras — difícil de acertar por acidente.

São fechamentos **não ajustados**, e é exatamente o certo aqui: múltiplo *point-in-time* casa o
preço cotado então com o lucro reportado então. `_price_on_or_before` sempre leu `close`.

**Efeito no score, sem uma linha alterada em `scoring.py`:**

```
PETR4  final 92,86  cobertura 0,75  (era 0,55)
  quality 97,8 | valuation 93,5 | growth 76,7 | risk None | diversification 100
```

O pilar de **Valuation** — o único dos cinco que nunca tinha tido dado — saiu de ausente para
93,5.

## Current State

- `pytest` → **672 passed** (617 → 646 → 660 → 672). `ruff check .` e `black --check .` limpos
  no repositório inteiro. `alembic check` sem drift.
- **PostgreSQL 16 no ar, schema `010`**, com **1.495 pregões da PETR4** em `asset_prices`, todos
  `source='b3_cotahist'` e `adjusted_close` **NULL**.
- **Cache do COTAHIST em `backend/var/b3/`** (gitignored) com 2020–2025, ~15 MB por ano.
- **Wave PRICE 🟢 concluída**, inserida entre a W09 e a W10.

## Important Details

### O que continua ausente, e por que é decisão e não esquecimento

**O pilar de Risco.** Não é falta de preço — são 1.495 pregões no banco. É falta de **série de
retorno total**. Métrica de risco exige que o retorno inclua provento e desconte desdobramento;
o COTAHIST não dá nem um nem outro. A cobertura do score para em **0,75** por isso.

Isso **não** é remendável na leitura. As alternativas foram enumeradas no ADR-023 e todas
rejeitadas por motivo nomeado — inclusive derivar o ajuste da contagem de ações da CVM, que o
projeto já ingere: ela é **anual**, e um desdobramento precisa da **data** do evento.

A correção é a montante, e é a mesma pendência do `dy`: **ingerir eventos societários e
proventos**. Uma ingestão fecha `dy`, o pilar de Risco, a cobertura e o backtesting da W13.

### O engano fácil de cometer aqui

`asset_prices` deixou de estar vazia, mas **a carteira ainda não é valorável**: o índice
time-weighted valoriza posição em `adjusted_close` ([ADR-019](../decisions/ADR-019-portfolio-return-is-time-weighted.md)),
e as 1.495 linhas têm `adjusted_close` nulo. O que destravou foi múltiplo *point-in-time*, que
lê `close`. São coisas diferentes e a distinção é o assunto inteiro do ADR-023.

### Lições de método desta sessão

- **Reconciliar o arquivo contra ele mesmo pagou de novo.** O `FATCOT` seria fácil de ignorar —
  502 registros em 320 mil, e todos os preços parecem válidos. Foi o `VOLTOT/QUATOT` do próprio
  registro que provou qual normalização está certa, sem depender de fonte externa nenhuma.
- **A fonte aberta ensinou de novo o que o mock não ensinaria**: o grupamento da MGLU3 não foi
  um caso inventado para o teste — apareceu sozinho, como um `range` de `[1,32; 14,42]` numa
  listagem de sanidade que eu estava fazendo por outro motivo.
- **Um ADR anterior estar certo não impede a premissa dele de expirar.** O ADR-016 não foi
  revogado nem contornado: a premissa ("estará completa amanhã") foi identificada, e a decisão
  passou a ser condicionada à fonte. Vale reler o ADR-023 antes de mexer em `adjusted_close`.
- **O teste do Windows pegou um defeito real**: o caminho de 404 apagava o arquivo temporário
  **enquanto ele estava aberto**, o que no Windows é `PermissionError` — um ano ausente virava
  erro fatal em vez de ser pulado. Só apareceu porque o teste exercitou o 404 de verdade.

## Pending Work

**Nenhuma task em andamento.** A decisão da próxima está em [CURRENT_TASK.md](CURRENT_TASK.md):
**eventos societários e proventos** (recomendado, pelo motivo acima) ou **Wave 10,
rebalanceamento**, na ordem do roadmap.

A lista de Known Issues em [PROJECT_STATUS.md](PROJECT_STATUS.md) foi atualizada: o item 2
(`pe`/`pb`) fechou, **nasceu o 2b** (pilar de Risco, com o motivo e o remendo proibido escritos),
e o item 8 ganhou o aviso de que a wave PRICE **não** o resolveu.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md) e escolher. Se for proventos/eventos societários, ler
antes o [ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md) — ele já
enumera as fontes candidatas e por que cada alternativa mais barata foi rejeitada.

## Relevant Files

- `backend/app/integrations/market_data/cotahist.py` — provider, arquivo, parser, cache
- `backend/app/integrations/market_data/base.py` — a separação `DailyHistoryProvider` / `MarketDataProvider`
- `backend/app/domain/market_data/series.py` — o ponto único da série de retorno
- `backend/migrations/versions/010_nullable_adj_close.py`
- `backend/tests/test_cotahist_provider.py` — 29 testes, registros reais verbatim
- `backend/tests/test_unadjusted_price_history.py` — 14 testes, as duas leituras da ausência
- `backend/tests/test_price_backfill_routes.py` — 12 testes ponta a ponta
- `docs/decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md`
