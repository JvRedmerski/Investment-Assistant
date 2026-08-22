# ADR-036 — A janela do pedido faz parte da identidade da barra intraday

## Status

Accepted (2026-08-22, W15-001 / W15-005). Mesma família do [ADR-020](ADR-020-composite-fundamentals-sources.md)
— *um período vem inteiro de uma fonte só, nunca campo a campo* — e do
[ADR-023](ADR-023-unadjusted-history-is-stored-as-unadjusted.md), que separa duas grandezas que
pareciam uma. Aqui a grandeza que se desdobra em duas é a própria barra.

## Context

A W15 abre o módulo intraday, e o procedimento do
[IMPLEMENTATION_GUIDE](../planning/IMPLEMENTATION_GUIDE.md) para integração nova foi seguido
inteiro: **uma chamada real antes de qualquer parser**. Foi essa chamada que achou o problema.

A Brapi serve intraday pelo mesmo `/quote/{ticker}` da série diária, mudando só `interval`, e
expõe o histórico em **baldes de range ancorados em agora** (`1d`, `5d`, `1mo`, `3mo`) — não
aceita data inicial. O suposto natural seria que o balde decide **quanto** volta, e nada mais.

Não é o que acontece.

### O que foi medido (PETR4, barras de 15 minutos, 2026-08-22)

| comparação | barras em comum | idênticas |
|---|---|---|
| `5d` contra `5d`, 1,5 s depois | 135 | **135** |
| `3mo` contra `3mo`, 1,5 s depois | 1.194 | **1.194** |
| `5d` contra `1mo` | 135 | **135** |
| **`5d` contra `3mo`** | 135 | **0** |
| **`1mo` contra `3mo`** | 567 | **0** |

A fonte é determinística: o mesmo balde pedido duas vezes devolve barra por barra o mesmo
valor. E `1d`/`5d`/`1mo` concordam entre si. Mas `3mo` é **outra partição da mesma sessão** —
nenhuma barra em comum sobrevive à comparação.

Não é revisão tardia nem ruído: são sessões fechadas de dias atrás. Olhando de perto o pregão
de 2026-08-18, o `3mo` carrega uma barra de **10:00 com volume real** que os baldes curtos nunca
devolvem, e a partir daí os rótulos andam um balde: o que `5d` chama de 10:15 (`42,91 → 42,89`)
não é o que `3mo` chama de 10:15 (`42,92 → 43,07`). Cada série é internamente encadeada — o
fechamento de uma barra é a abertura da seguinte —, então as duas são **respostas
auto-consistentes e incompatíveis** à mesma pergunta.

### Por que isso quebra a regra que basta para a série diária

A política diária é *nunca sobrescrever uma data já gravada* (`sync_daily_history`). Ela vale
porque uma barra diária é a mesma barra pergunte quem perguntar.

Aplicada aqui, "primeiro que grava vence, barra a barra" montaria uma sessão a partir de **duas
partições dessa sessão**, conforme o que estivesse no banco no momento de cada sync. O
resultado é uma série que nunca foi negociada, internamente inconsistente, indetectável depois
— e todo indicador da W16 (VWAP, EMA, ATR) calculado sobre ela estaria errado sem nada a
mostrar.

## Decision

### 1. A barra carrega a janela que a produziu, do provider até a linha do banco

`IntradayHistory` emparelha `bars` com `window`, para que a janela não possa ser perdida no
caminho, e `intraday_prices.source_window` é `NOT NULL`. Não há default honesto: barra de janela
desconhecida não pode ser mostrada como pertencente a nenhuma partição.

`source_window` fica **fora** da chave única `(asset_id, timestamp, timeframe)`. Admiti-la
deixaria o mesmo instante ter duas linhas, que é exatamente a mistura que isto existe para
impedir.

### 2. A **sessão** é a unidade que vem de uma janela só

Mesma postura do [ADR-020](ADR-020-composite-fundamentals-sources.md). Um sync que alcança uma
sessão já gravada sob outra janela **não toca nela** e reporta `WindowConflict` com as duas
janelas e quantas barras deixou de fora.

Escolher um vencedor em silêncio não está na mesa: as duas são auto-consistentes e **nada no
dado diz qual é a certa**. Escolher significaria sobrescrever o gravado ou descartar o buscado,
e as duas coisas são decisão do chamador.

⚠️ **Conflito não é falha.** Todas as outras sessões do lote entram normalmente. Uma resposta com
`conflicts` não vazio é um sync bem-sucedido que está dizendo o que não fez.

### 3. Substituir é operação explícita, e é sessão inteira

`resync=true` apaga a sessão gravada e insere a buscada no lugar. Sessão inteira **por
construção**: substituir parte de uma produziria justamente a mistura que o conflito evita.

### 4. A série lida declara suas próprias janelas

A garantia do item 2 é *dentro da sessão*. Ela não torna homogênea uma série de várias sessões
— e o run real mostrou isso: sincronizar três dias e depois sessenta deixou 3 sessões em `5d` e
40 em `3mo`. Cada sessão íntegra, a série inteira com uma costura.

Por isso `GET /assets/{ticker}/intraday` devolve envelope, não lista: `windows` diz de uma vez
quais partições estão ali. Mais de uma entrada significa que **qualquer cálculo que atravesse
fronteira de sessão está lendo através de uma emenda**. Re-sincronizar o intervalo inteiro com
`resync=true` é o que colapsa a série para uma janela.

## Consequences

**Positivas**

- A mistura silenciosa é impossível: ou a sessão vem de uma janela, ou o conflito é reportado.
- A escolha de janela deixa de ser detalhe de fetch e vira dado auditável na linha.
- `_intraday_window_for` escolhe o **menor** balde que alcança `start`, o que evita escalar para
  `3mo` sem necessidade e trocar de partição por acidente.

**Negativas, e assumidas**

- ⚠️ Ampliar a janela pedida gera conflito nas sessões já gravadas. É o comportamento correto e
  é ruidoso: o caminho para uma série longa e homogênea é `resync=true` no intervalo inteiro.
- ⚠️ Uma série pode legitimamente ter costura entre sessões. Está reportada, não impedida —
  impedir exigiria recusar dados que o chamador pediu e que estão corretos dentro de cada sessão.
- O balde é atributo do fornecedor. Outro provedor intraday precisará mapear seu próprio conceito
  para `HistoryWindow`, ou o enum precisará crescer.

## Alternatives considered

**Fixar um único balde por timeframe e nunca escalar.** Resolveria por construção: com
`1d`/`5d`/`1mo` concordando, bastaria nunca pedir `3mo`. Rejeitada porque a fronteira entre as
duas partições é comportamento não documentado do fornecedor — hoje cai entre `1mo` e `3mo`,
amanhã pode cair em outro lugar, e o desenho voltaria a depender de uma coincidência medida.
Gravar a janela funciona **mesmo que a fronteira se mova**, e ainda permite os 43 pregões que só
`3mo` alcança contra os 22 de `1mo`.

**Incluir `source_window` na chave única.** Deixaria as duas partições coexistirem e adiaria a
escolha para a leitura. Rejeitada: transformaria toda leitura numa desambiguação, e a primeira
leitura que esquecesse de filtrar teria a série duplicada e encadeada errado.

**Normalizar as duas partições para uma.** Exigiria reagregar barras de uma grade para outra a
partir de OHLCV já agregado, o que não é reversível — `high` e `low` de dois baldes de 15 minutos
não reconstroem os quatro de 7,5. Seria derivar dado de dado agregado e apresentá-lo como
medição, que é o que o [ADR-023](ADR-023-unadjusted-history-is-stored-as-unadjusted.md) recusou.
