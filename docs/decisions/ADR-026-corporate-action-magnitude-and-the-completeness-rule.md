# ADR-026 — A magnitude vem do serviço aberto de eventos da B3, e o ajuste só existe onde é completo

## Status

Accepted (2026-08-20, EVENTS-003). Completa o [ADR-023](ADR-023-unadjusted-history-is-stored-as-unadjusted.md) (preço não ajustado é armazenado como não ajustado) e o [ADR-025](ADR-025-corporate-events-come-from-the-distribution-counter.md) (evento vem do contador, **sem magnitude**).

## Context

O pilar de Risco estava ausente desde sempre por uma palavra: **magnitude**. A EVENTS-002 entregou a **data** de todo evento societário pelo contador de distribuição da B3, e o ADR-025 fechou dizendo que o arquivo registra *que* houve distribuição e jamais *quanto*. Sem fator de desdobramento e sem valor de provento não há série de retorno total, e sem ela `volatility`, `max_drawdown`, `beta` e `sharpe` seguem `None` — a cobertura do score presa em 0,75 e a W13 (backtesting) sem o que consumir.

O `CURRENT_TASK.md` listava três candidatas. Uma quarta apareceu ao medir, e mediu melhor que as três.

## Decision

### 1. A magnitude vem do serviço de eventos corporativos da própria B3

`https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/` — aberto, sem token e sem cota, o mesmo critério que escolheu a CVM para demonstrativos ([ADR-020](ADR-020-cvm-primary-fundamentals-source.md)) e o COTAHIST para preços (ADR-023). Ele publica **reais por ação** para provento e **fator** para evento de contagem.

**As datas foram conferidas contra um sinal independente antes de qualquer código.** O contador `DISMES` do arquivo de fim de dia e este serviço são dois sistemas separados da bolsa, e concordaram em **157 de 157** datas de provento em janela (PETR3, PETR4, VALE3, ITUB4, BBAS3). A data-com do serviço mais o pregão seguinte cai exatamente na sessão que o contador marcou ex. Isso é **evidência, não construção**: as duas fontes continuam separadas, cada uma inteira, e o acordo entre elas é medido em vez de imposto.

### 2. A chave de junção é o ISIN, e errar isso eleva o fator ao cubo

A B3 repete um evento de contagem **uma vez por ISIN que o emissor já teve**. O desdobramento 1:2 da BBAS3 chega três vezes (`BRBBASA04OR8`, `BRBBASA05OR5`, `BRBBASACNOR3`), e só o último é o papel que negocia.

Isso não foi sutil: enquanto a leitura era validada, **todo** desacordo com um degrau de preço real era uma potência exata da resposta certa — 2³ na BBAS3, 4³ na BPAC11, 10³ na CPLE3, 1,1³ na UNIP3. Filtrar pelo ISIN impresso no registro do próprio papel (`CODISI`) levou o acordo de 32/50 para **49/50**, e o único que sobra é o grupamento 1:30 da IRBR3 a R$ 0,93, onde um preço de poucos ticks não mede fator nenhum.

Daí `SecurityIdentity` (ticker → ISIN + classe), lida do arquivo em vez de inferida do dígito final do ticker — que funcionaria para PETR4 e falharia para TAEE11 (`UNT`).

### 3. `factor` significa duas coisas, e só o rótulo diz qual

Medido contra degrau real, não suposto:

| rótulo | leitura | conferência |
|---|---|---|
| `DESDOBRAMENTO` | `1 + factor/100` | BBAS3 `100` → 2,00 vs 2,0229 medido |
| `BONIFICACAO` | `1 + factor/100` | ITUB4 `3` → 1,03 vs 1,0297 |
| `GRUPAMENTO` | o `factor` já é a razão | MGLU3 `0,10` → 0,10 vs 0,1004 |

Uma porcentagem em dois rótulos e uma razão crua no terceiro, sob um nome de campo só.

Os demais rótulos (`CIS RED CAP`, `INCORPORACAO`, `RESG TOTAL RV`, `REST CAP ACOES`) ficam **sem dimensionar de propósito**: a cisão da ITUB4 em 2021-10-04 traz `factor` 100, que sob qualquer das duas leituras seria 2,0 ou 1,0 contra um degrau medido de **1,2190**. Seja o que for esse número, não é razão de ação, e nomeá-lo assim seria a §44.

Eventos no mesmo pregão **compõem**: a VIVT3 em 2025-04-15 foi `DESDOBRAMENTO` 7.900 **e** `GRUPAMENTO` 0,025, que multiplicam a exatamente 2,0 contra 2,0031 medido.

### 4. A armadilha de unidade, pela terceira vez no projeto

`valueCash` é cotado por `quotedPerShares` ações, e esse campo **não é sempre 1**: 332 de 2.305 linhas medidas dizem `1000`. É o mesmo modo de falha do `FATCOT` no arquivo e do `ESCALA_MOEDA` na CVM, e o erro seria de mil vezes.

### 5. `adjusted_close` só é derivado onde o ajuste é **completo**, e a completude é julgada pelo contador

Esta é a metade que importa. Um ajuste feito com *parte* das ações não é uma série de retorno mais curta — é uma **errada, e plausível**.

A completude **não** pode ser julgada pelo serviço de eventos, porque ele demonstravelmente não enumera tudo: a **ITUB4 foi ex em 2025-03-18** com o marcador `EB` do arquivo e degrau de **-8,60%**, e o serviço da B3 não reporta ação nenhuma nessa data. Confiar nele teria ajustado através de um evento real de contagem.

Então a regra é: **toda sessão que o contador marcou ex precisa ter uma ação dimensionada contra ela.** A mais recente que não tiver é um piso, e nada antes dela é ajustável. A lacuna é reportada na resposta, não engolida — série curta é a saída honesta, e o `app.quant` já responde `None` com pontos de menos.

### 6. A exceção é o `ATZ`, e ela é uma decisão de julgamento registrada como tal

O marcador `ATZ` (*atualização*) é a única exceção: um incremento em que **nada sai do titular**, logo não há magnitude a faltar.

A evidência: nos arquivos de 2020–2025 há **151 incrementos** cuja especificação traz `ATZ` sem marcador de ex-, o **degrau mediano é 1,0028** — três décimos de por cento — e o serviço da B3 não reporta distribuição contra nenhum deles. A PETR4 sozinha tem cinco.

**Seis dos 151 moveram preço mais de 15%, e ficam nomeados em vez de arredondados**: dois BDRs (A2MC34, L1RC34), uma cota de fundo (SNLG11) e três ações em quedas de 15–20% (RRRP3, AMBP3, AZUL4).

Sem essa exceção a regra estrita mediria: **PETR4 com 28 de 1.495 pregões ajustáveis**, VALE3 com 47, MGLU3 com 7 — a wave não destravaria nada. Com ela, PETR4 e BBAS3 ficam inteiras e a ITUB4 continua corretamente truncada pelo `EB` que ninguém dimensionou.

**Esta foi uma escolha apresentada ao dono do projeto com os números acima e decidida por ele**, não uma inferência do implementador. É o único ponto desta task em que uma leitura da fonte foi preferida a outra por conveniência de cobertura, e ele fica marcado.

### 7. O serviço fica atrás de `CorporateActionProvider`, e nada fora do adaptador conhece sua forma

O endpoint é aberto e público, mas é o backend JSON das páginas da B3 — parâmetros em base64 no **path**, sem documentação e sem contrato. Se ele mudar, quebra um arquivo, os chamadores continuam compilando, e a degradação é para **magnitude ausente** — exatamente o estado anterior a esta task — e nunca para número errado.

## Evidence

- `backend/app/integrations/market_data/b3_corporate_actions.py` — o adaptador, com as medições no docstring de módulo.
- `backend/app/integrations/market_data/base.py` — `CorporateActionProvider`, a quarta interface; `get_security_identity` na terceira.
- `backend/app/integrations/market_data/schemas.py` — `CorporateAction`, `CorporateActionKind`, `SecurityIdentity`, e `CorporateEventKind.NOMINAL_UPDATE` com as 151 medições e as 6 exceções.
- `backend/app/domain/market_data/adjustment.py` — a aritmética e a regra de completude, sem I/O.
- `backend/app/domain/market_data/corporate_actions.py` — ingestão, resolução da ex-date contra o calendário real, e o preenchimento que só toca coluna nula.
- `backend/migrations/versions/012_corporate_actions.py` — aplicada em PostgreSQL 16 real, `alembic check` sem drift, downgrade testado.
- **49 testes novos** (750, era 701): `test_b3_corporate_actions.py` (payloads verbatim do serviço real, incluindo a tripla duplicação por ISIN), `test_price_adjustment.py` (degraus reais de BBAS3, MGLU3, VIVT3, ITUB4), `test_corporate_action_routes.py`, e o `ATZ`/identidade no `test_cotahist_provider.py`.

### Medido no banco real, após o sync

| papel | ajustado | janela | leitura |
|---|---|---|---|
| **PETR4** | 1.495/1.495 | 2020-01-02 → 2025-12-30 | 62 proventos; volatilidade 41,8%, drawdown -63,4% com fundo em 2020-03-18 (a COVID). Pior sessão ajustada **idêntica** à crua (-29,7% em 2020-03-09): nenhum evento vazou |
| **BBAS3** | 1.495/1.495 | 2020-01-02 → | desdobramento 1:2 desfeito; pior sessão 17,1% |
| **ITUB4** | 198/1.495 | 2025-03-19 → | **truncada**, corretamente, em `[2021-10-04, 2025-03-18]` — a cisão sem dimensão e o `EB` que a B3 não reporta |
| **MGLU3** | 478/1.495 | 2024-02-02 → | truncada na subscrição de 2024-02-01; o **grupamento 1:10 desfeito** — pior sessão 13,5%, não os +896% do ADR-023 |

## Alternatives

- **Fator pela contagem de ações da CVM + data da B3** (opção 1 do `CURRENT_TASK`) — rejeitada. O ADR-023 a tinha rejeitado por granularidade e essa objeção caiu com a EVENTS-002, mas as outras não: a contagem é anual e não fecha com dois eventos no mesmo exercício nem com emissão/recompra no meio, **não cobre provento em dinheiro** (que é a maior parte do retorno total de PETR4 — fator 3,43× em seis anos), e produziria um fator **derivado** onde a B3 publica um **reportado**.
- **Fornecedor pago** (opção 3) — rejeitada pelo mesmo critério do ADR-020: o dado aberto responde, e responde com mais profundidade.
- **Derivar o fator do degrau de preço** — rejeitada, é o núcleo do ADR-023. A validação aqui mostrou por quê no sentido inverso: o degrau é bom o bastante para *conferir* um fator publicado e péssimo para *produzir* um, porque falha em papel ilíquido (CPLE5 negociou três meses depois) e em penny stock (IRBR3 a R$ 0,93, 26% de erro).
- **Preencher `adjusted_close` só com os eventos de contagem, ignorando proventos** — rejeitada, e foi a tentação real. Daria décadas de série para todo papel, mas `adjusted_close` está documentado como **retorno total**; gravar ali uma série de retorno de preço seria exatamente o rótulo errado que o ADR-023 existe para impedir.
- **Julgar a completude pelo serviço de eventos** — rejeitada por medição: a ITUB4 em 2025-03-18 prova que ele omite.
- **Regra estrita, sem a exceção do `ATZ`** — rejeitada com o custo medido (PETR4: 28 de 1.495). Ver o item 6 e de quem foi a decisão.
- **Sobrescrever `adjusted_close` já gravado** — rejeitada (ADR-020/ADR-024): misturaria a reexpressão do fornecedor com a derivada aqui numa série só.

## Consequences

- ✅ **A série de retorno total existe.** `volatility`, `max_drawdown`, `beta` e `sharpe` passam a ter insumo real, e o **pilar de Risco deixa de ser ausente** para papel com histórico aberto e eventos completos.
- ✅ **A cobertura do score sai de 0,75.**
- ✅ A **W13 (backtesting)** passa a ter o que consumir.
- ✅ Toda lacuna é **nomeada e datada** na resposta do sync, em vez de virar "esse ativo não tem risco, não se sabe por quê".
- ⚠️ **Papel com evento não dimensionado tem série curta**, e isso é o desenho. ITUB4 e MGLU3 são os casos reais.
- ⚠️ **Subscrição não é dimensionada.** O serviço a publica numa lista própria (`subscriptions`), com percentual e preço de exercício — dimensioná-la corretamente exige um modelo do valor do direito, não uma medição. Fica como *Future Work*, e por ora ela trunca (foi o que cortou a MGLU3 em 2024-02-01).
- ⚠️ **Uma correção tardia da B3 sobre data já ajustada não é reaplicada**, porque o preenchimento só toca coluna nula (ADR-024). Recomputar exigiria limpar a coluna primeiro, e isso é operação manual deliberada.
- ⚠️ O adaptador depende de um endpoint **sem contrato publicado**. Mitigado pela interface e pela degradação para ausência; não eliminado.
