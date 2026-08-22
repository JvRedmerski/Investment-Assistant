# Session Handoff

## Last Updated

2026-08-22

## Last Completed Work

### Wave 15 — Day Trade Data, 6/6 (`65236dd`, `469d053`, `a76897e`, `7029906`, `15edc26`, e a W15-006 em **dois** commits: `2fbee4c` e o seguinte)

O roadmap previa uma task. Foram seis, e as cinco a mais não são subdivisão: o contrato da
barra é uma coisa, buscá-la é outra, dizer que a série está furada é uma terceira, o esquema é
uma quarta, e rodar contra o banco real é o passo que nas waves anteriores achou o que fixture
nenhum acha.

| task | entrega |
|---|---|
| **W15-001** | O contrato: `Timeframe`, `IntradayBar`, `HistoryWindow`, `IntradayHistoryProvider` |
| **W15-002** | `BrapiProvider.get_intraday_history`, contra uma resposta que foi de fato lida |
| **W15-003** | Qualidade e gaps: `intraday_quality`, puro e sem I/O |
| **W15-004** | `intraday_prices` em `NUMERIC`/`TIMESTAMPTZ` com `source_window` (migration `013`) |
| **W15-005** | Ingestão idempotente que **recusa misturar janelas**, e as duas rotas |
| **W15-006** | Rodar contra o banco real, e corrigir o que ele achou |

### O ponto da wave, em uma frase

**Uma barra intraday não é um fato estável nesta fonte.** A mesma barra — mesmo ticker, mesmo
timestamp, mesmo timeframe — volta com OHLCV diferente conforme o `range` pedido. Então a
janela faz parte da identidade da barra, e é gravada com ela.

### Foi a chamada real que achou isso, e ela veio antes de qualquer parser

O procedimento do [IMPLEMENTATION_GUIDE](../planning/IMPLEMENTATION_GUIDE.md) — a lição cara da
W06-003 — foi seguido inteiro. Seis achados, três mudaram o desenho:

| medição | resultado | consequência |
|---|---|---|
| Mesmo balde, duas vezes | 135/135 e 1.194/1.194 idênticas | A fonte é determinística |
| `5d` contra `1mo` | 135/135 | Mesma partição |
| **`5d` contra `3mo`** | **0 de 135** | `source_window` na linha (ADR-036) |
| **`1mo` contra `3mo`** | **0 de 567** | idem |
| `adjustedClose` intraday | **nulo em 1.389 de 1.389** | O campo **não existe** em `IntradayBar` |
| Intraday liberado **por ticker** | PETR4/ITUB4/MGLU3/VALE3 sim; BBAS3/BOVA11 não | `IntradayNotAvailableError`, 400 e não 503 |
| `1m` + `3mo` | **5 sessões** contra 22 em `1m` + `1mo` | `1m` nunca escala para `3mo` |
| Sessão de 2026-07-31 | 16 barras em grade `:01/:16/:31/:46` | **Sem checagem de grade** (ADR-037) |

### As duas decisões, e por que cada uma é a decisão

1. **A janela do pedido faz parte da identidade da barra**
   ([ADR-036](../decisions/ADR-036-the-request-window-is-part-of-a-bars-identity.md)). A regra
   diária — nunca sobrescrever data gravada — não basta aqui: aplicada barra a barra, montaria
   uma sessão a partir de **duas partições dela**, conforme o que estivesse no banco no momento
   de cada sync. A **sessão** é a unidade que vem de uma janela só, como o período dos
   fundamentos no ADR-020. Conflito é **reportado, nunca resolvido em silêncio** — as duas
   respostas são auto-consistentes e nada no dado diz qual é a certa.
2. **Buraco se mede, borda de sessão se compara**
   ([ADR-037](../decisions/ADR-037-a-gap-is-measured-a-session-edge-is-compared.md)). Um buraco
   entre barras entregues é aritmética. Uma sessão que começou tarde não é mensurável sem o
   calendário de pregões da B3, que o projeto não tem — então `SHORT_SESSION` compara com as
   vizinhas do lote e **não pretende saber** se foi abertura tardia, leilão ou perda de linhas.

### O que rodar contra o banco real encontrou

✅ Funcionou: 76 barras por ticker no sync de 3 dias, segundo sync inserindo 0 e pulando 76,
BBAS3 recusado nos três timeframes, e o conflito disparando de verdade ao ampliar para 60 dias
(1.109 sessões novas, 3 recusadas). **Nenhuma sessão no banco tem mais de uma janela.**

🔴 Achou: a garantia é **por sessão**, e uma série não é uma sessão. Três dias sincronizados e
depois sessenta deixam 3 sessões em `5d` e 40 em `3mo` — cada uma íntegra, a série inteira com
uma **costura**, e a leitura devolvia lista pura sem dizer. `GET /assets/{ticker}/intraday`
passou a devolver envelope com `windows`.

🔴 Achou também um segundo defeito, alcançável direto pela API e invisível na primeira chamada:
a substituição estava condicionada a **divergência de janela**, e re-sincronizar sessão já
gravada sob a **mesma** janela pulava o delete e reinseria todas as barras, porque `resync`
também desligava a checagem de duplicata. Duas chamadas `?resync=true` idênticas davam violação
de unicidade — **HTTP 500**. Agora a condição é "a sessão tem algo gravado", e `resync` é
idempotente.

## Current State

- `pytest` → **1.228 passed** (1.129 → 1.228 na W15), verificado em 2026-08-22. `ruff` e
  `black` limpos.
- **Migration nova**: `013_intraday_precision` — OHLC para `NUMERIC(18,6)`, `timestamp` para
  `TIMESTAMPTZ`, `source_window` `NOT NULL`. Aplicada contra o Postgres real e **revertida e
  reaplicada** para conferir as duas direções.
- **Nenhuma dependência nova.** `tzdata` foi considerada para `ZoneInfo` e **recusada** — ela
  quebra no Windows e funciona no contêiner, o que faria o mesmo código agrupar sessões de
  formas diferentes conforme onde rodasse (ADR-037).
- **Wave 15 🟢 concluída**, 6/6. Nada iniciado da W16.

## Important Details

### Os enganos fáceis de cometer aqui

⚠️ **Não calcule indicador atravessando fronteira de sessão sem olhar `windows`.** A garantia é
por sessão. Uma série com `windows: ["5d", "3mo"]` tem uma emenda, e uma EMA que cruza o dia lê
através dela. É o aviso mais importante para a W16.

⚠️ **O universo intraday é de 3 ativos, não 4.** BBAS3 é recusado pelo plano gratuito e não tem
nenhuma barra. A mensagem do fornecedor culpa o *intervalo*, e o intervalo é o mesmo dos tickers
que funcionam — o discriminante é o ticker, e BBAS3 responde 200 em `interval=1d`.

⚠️ **`IntradayNotAvailableError` não significa "ticker não existe".** No caminho intraday o gate
de plano roda **antes** da resolução do ticker, então um ticker inventado devolve a mesma coisa.
Nunca leia inexistência dessa exceção.

⚠️ **Ampliar a janela pedida gera conflito nas sessões já gravadas.** É o comportamento correto.
O caminho para uma série longa e homogênea é `resync=true` sobre o intervalo inteiro.

### E os das waves anteriores, que continuam valendo

**A figura que responde a pergunta do walk-forward é `stability.degradation_mean`**, não o
retorno. Com um fold só, todo agregado vem `null` e `refusal` é `SINGLE_FOLD`.

**`wealth` não é desempenho.** É patrimônio em BRL com `contributed` por baixo. A resposta
comparável a um benchmark é `comparison`, que é time-weighted (ADR-019).

**As cinco figuras de trade fechado voltam `null` de propósito** — são definidas sobre trade
fechado, e nada que este projeto entrega vende (ADR-028).

## Pending Work

1. 🔴 **Redigir a credencial da Brapi do log.** `app/core/logging.py` chama
   `logging.basicConfig(level=INFO)`, que configura o logger **raiz**, e o `httpx` imprime
   `GET https://brapi.dev/api/quote/PETR4?token=<token>&...` em texto claro. Pré-existe desde a
   W05; achado na W15-006 e registrado sem corrigir por ser fora do escopo (§134). Correção
   candidata: `logging.getLogger("httpx").setLevel(logging.WARNING)`, e/ou mover a autenticação
   da Brapi para header — o `RetryingJsonClient` já suporta `default_headers`, e o docstring
   dele já diz por que header é o lugar certo.
2. **Wave 16 — Day Trade Engine** (roadmap §28). Ver [CURRENT_TASK.md](CURRENT_TASK.md).
3. **Ingerir os eventos societários que faltam em ITUB4 e MGLU3.** Não é wave, é dado.
4. **Verificar o `OllamaProvider`** contra um servidor real, quando houver um.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md). A correção do log (item 1) é de uma linha e vale antes
de **começar a Wave 16**.

## Relevant Files

- `backend/app/integrations/market_data/schemas.py` — `Timeframe`, `HistoryWindow`, `IntradayBar`
- `backend/app/integrations/market_data/base.py` — `IntradayHistoryProvider`, `IntradayHistory`
- `backend/app/integrations/market_data/brapi.py` — `get_intraday_history`, `_INTRADAY_WINDOWS`, `_map_brapi_error`
- `backend/app/integrations/market_data/intraday_quality.py` — sessões, buracos, `EXCHANGE_TIMEZONE`
- `backend/app/domain/daytrade/service.py` — a ingestão e a recusa de misturar janelas
- `backend/app/domain/daytrade/schemas.py` — os contratos, incluindo `IntradaySeriesResponse`
- `backend/migrations/versions/013_intraday_precision.py`
- `docs/decisions/ADR-036-*.md`, `ADR-037-*.md`
- `backend/tests/test_intraday_{schemas,quality,storage,service,routes}.py`, `test_brapi_intraday_provider.py`
