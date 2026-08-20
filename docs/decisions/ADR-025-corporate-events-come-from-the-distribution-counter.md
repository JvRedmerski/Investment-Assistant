# ADR-025 — Evento societário é lido do contador de distribuição da B3, com data e natureza e sem magnitude

## Status

Accepted (2026-08-19, EVENTS-002). Complementa o [ADR-023](ADR-023-unadjusted-history-is-stored-as-unadjusted.md), que estabeleceu que **marcador não é magnitude**.

## Context

O pilar de Risco está ausente porque não existe série de retorno total, e não existe porque o COTAHIST imprime preço **negociado** (ADR-023). Construir a série exige os eventos societários, e a primeira metade disso é saber **em que pregões o papel negociou ex** algum direito.

O arquivo de fim de dia da própria bolsa diz isso, num campo que o parser de preço já lia e descartava. Só que ele **não diz onde parece dizer**.

### O marcador é janela de exibição, não evento

O `ESPECI` traz o marcador de ex- (`ON  EDJ NM`). Lê-lo como evento falha de duas maneiras, ambas medidas no arquivo real de 2024:

- **Ele persiste.** A B3 mantém o marcador no ar por cerca de **oito pregões**. Um único dividendo seria reportado oito vezes.
- **Ele decai.** À medida que direitos saem da janela, `EDJ` vira `EJ` — o que, lido como texto, parece um marcador *aparecendo*. **132 sessões de 2024** têm essa forma.

Detectar por "início de sequência do marcador" também não fecha. A BBAS3 exibe `ON  EDJ NM` em 12, 13 e 14/06/2024 enquanto o contador de distribuição vai **323, 323, 324**: são **duas** distribuições sob um marcador imóvel. A detecção por sequência encontraria uma e perderia a do dia 14.

## Decision

### 1. O sinal é o `DISMES`, o contador de distribuição do próprio papel

É o número que a B3 mantém para o papel, ele **incrementa no ex-date**, e incrementa **uma vez por distribuição** mesmo quando o texto do marcador não se move. Um evento é um incremento em relação ao pregão anterior do mesmo papel.

Conferido no sentido inverso, no arquivo inteiro de 2024 (**2.230 papéis, 7.312 incrementos**): o contador **nunca decresceu**, atravessa a virada do ano (ITUB4 345 → 346 em 2025-01-02), e apenas **13 letras de ex- apareceram no ano sem incremento** — **nenhuma delas moveu preço em 25% ou mais**, ou seja, nada capaz de corromper uma série de retorno se perde ao confiar no contador.

### 2. A natureza é decomposta letra a letra, e cada letra foi confirmada contra um degrau de preço real

`CorporateEventKind` nomeia **o que o titular deixou de ter direito**, não como a empresa chamou o ato — é a única leitura que a fonte sustenta. Duas descobertas mudaram nomes:

- **`EB` não é "bonificação".** O mesmo marcador carrega o desdobramento 1:2 da BBAS3 (56,46 → 27,91), o 10:1 da NVDC34 e a bonificação de 4,5% da MGLU3 em 2025 (9,35 → 8,94). Nomear pelo ato jurídico afirmaria uma distinção que **o arquivo não faz** — daí `BONUS_OR_SPLIT`.
- **`R` não é "rendimento".** É o rendimento mensal de fundo em 3.544 dos eventos de 2024, mas também cai em ação ao lado de outro provento (PETR4 com `EDR` em quatro sessões de dividendo, VIVT3 com `ERJ`), onde o arquivo não diz o que ele cobre. O que todos os casos observados compartilham é dinheiro saindo com a contagem de ações intacta — e é só isso que o nome afirma: `OTHER_DISTRIBUTION`.

Letra sem evidência (`X`, `C`) e incremento sem marcador algum (7,5% de 2024) viram **`UNCLASSIFIED`**, nunca um palpite (AGENTS.md §44). O `ESPECI` cru é guardado **verbatim** em cada evento, para que uma classificação errada possa ser revista sem reler dezenas de GB de arquivo.

### 3. Não há fator e não há valor, deliberadamente

O arquivo registra **que** houve distribuição e jamais **quanto**. Derivar o tamanho do degrau de preço é a heurística que o ADR-023 rejeitou. Dimensionar os eventos é problema separado, com fonte separada.

### 4. `CorporateEventProvider` é interface própria

Não é método em `DailyHistoryProvider`, pela mesma razão que partiu aquela interface na PRICE-001: um fornecedor de cotação não sabe em que pregão um papel foi ex, e obrigá-lo a implementar isso o obrigaria a **responder mal**. Só o `B3CotahistProvider` a implementa, lendo o **mesmo arquivo já baixado** — nenhuma requisição nova.

## Evidence

- `backend/app/integrations/market_data/base.py` — `CorporateEventProvider`, ortogonal às duas interfaces de preço.
- `backend/app/integrations/market_data/schemas.py` — `CorporateEvent` e `CorporateEventKind`, com a evidência de cada letra no docstring.
- `backend/app/integrations/market_data/cotahist.py` — `get_corporate_events`, `_distributions_for`, `_kinds_in`, e o docstring de módulo com as medições. `_read_bars` virou `_read_records`, então os dois leitores compartilham uma varredura em vez de crescerem uma paralela.
- `backend/tests/test_cotahist_provider.py` — inclui o caso BBAS3 (323/323/324) com os três registros verbatim. **20 fixtures conferidas byte a byte contra o arquivo real.**
- Validação contra os arquivos reais de 2020–2025: PETR4 com **47 eventos e nenhum de contagem de ações em seis anos**, o que é correto; MGLU3 com 15, entre eles o desdobramento 1:4 de 2020 (104,00 → 25,59), o grupamento 1:10 de 2024 e a bonificação de 2025.

## Alternatives

- **Detectar pelo marcador `ESPECI`** — rejeitado por medição: oito pregões de exibição por evento, e o decaimento `EDJ` → `EJ` produz 132 falsos "novos marcadores" em 2024.
- **Detectar pelo início de sequência do marcador** — rejeitado: o caso BBAS3 mostra duas distribuições sob marcador imóvel; encontraria uma e perderia a outra.
- **Derivar evento e fator do degrau de preço** — rejeitado, é o núcleo do ADR-023: não distingue grupamento de queda real e inventa número (§44).
- **Adivinhar a natureza das letras sem evidência** — rejeitado. `UNCLASSIFIED` reporta que o evento existiu e que a natureza é desconhecida, que é o fato.
- **Chamar um fornecedor de proventos** — rejeitado por agora: custa cota e o arquivo da própria bolsa já responde a **data**, que é a metade que ninguém mais dá de graça com esta profundidade.
- **`get_corporate_events` como método de `DailyHistoryProvider`** — rejeitado: obrigaria o fornecedor de cotação a responder algo que ele não sabe.

## Consequences

- ✅ **A data e a natureza de todo evento societário passam a ser conhecidas**, décadas atrás, sem cota e sem requisição nova.
- ✅ A metade que falta para a série de retorno total ficou nomeada e isolada: **magnitude**.
- ✅ O `ESPECI` cru guardado verbatim torna toda classificação revisável sem custo de reprocessamento.
- ⚠️ **Um evento na primeiríssima sessão que os arquivos guardam para o papel não é visível**, porque a comparação precisa de um predecessor. Na prática é o primeiro pregão do ano civil de `start` — o ano inteiro é varrido independentemente de onde `start` cai — ou a primeira sessão do papel.
- ⚠️ Quando dois eventos caem dentro de uma mesma janela de exibição, ambos recebem a **união** das letras do marcador. As duas datas estão certas; a atribuição de qual letra pertence a qual evento **o arquivo não permite fazer**, e a união é a afirmação da própria fonte em vez de um palpite sobre a metade nova.
- ⚠️ O evento **ainda não é persistido**: `get_corporate_events` é leitura de arquivo, não ingestão. Model, migration e endpoint são a próxima task.
