# Current Task

## Task

**Wave 16 — Day Trade Engine** (roadmap §28, AGENTS.md §48–51). Indicadores intraday e os três
setups iniciais.

## Status

🟢 **A Wave 15 fechou em 2026-08-22**, 6 de 6 tasks, e não há código pela metade em lugar
nenhum. `pytest -q` → **1.228 passed**.

---

## O que a Wave 15 entregou

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
| **W15-006** | Rodar contra o banco real e o provider real, e corrigir o que achou |

### O ponto inteiro da wave, em uma frase

**Uma barra intraday não é um fato estável nesta fonte** — a mesma barra vem diferente conforme
a janela pedida —, então a janela faz parte da identidade da barra.

### As duas decisões que sustentam isso

1. **A janela do pedido faz parte da identidade da barra**
   ([ADR-036](../decisions/ADR-036-the-request-window-is-part-of-a-bars-identity.md)). Medido:
   `5d` contra `3mo` → **0 de 135** barras idênticas; `1mo` contra `3mo` → **0 de 567**; o mesmo
   balde pedido duas vezes → **135 de 135**. A **sessão** é a unidade que vem de uma janela só, e
   o conflito é **reportado, nunca resolvido em silêncio**.
2. **Buraco se mede, borda de sessão se compara**
   ([ADR-037](../decisions/ADR-037-a-gap-is-measured-a-session-edge-is-compared.md)).
   `INTRA_SESSION_GAP` é aritmética entre barras entregues; `SHORT_SESSION` é comparação com as
   vizinhas do lote. **Sem checagem de alinhamento de grade** — ela teria rejeitado as 16 barras
   reais de 2026-07-31, que estão numa fase de minuto diferente de todas as outras sessões.

### O que a chamada real mediu, e que nenhuma suposição teria achado

| medição | resultado |
|---|---|
| `adjustedClose` em barra intraday | **nulo em 1.389 de 1.389** → o campo não existe em `IntradayBar` |
| Intraday liberado **por ticker** no plano free | PETR4/ITUB4/MGLU3/VALE3 sim; **BBAS3/BOVA11 não** |
| Ticker inexistente no caminho intraday | `INVALID_INTERVAL`, **nunca 404** |
| `1m` + `3mo` | **5 sessões**, contra 22 em `1m` + `1mo` |
| Sessão de 2026-07-31 | 16 barras fora de fase, reais |

### O que rodar contra o banco real achou

A garantia é **por sessão**, e uma série não é uma sessão. Três dias sincronizados e depois
sessenta deixam 3 sessões em `5d` e 40 em `3mo` — cada uma íntegra, a série inteira com uma
**costura**. `GET /assets/{ticker}/intraday` passou a devolver envelope com `windows`.

E um segundo defeito, invisível na primeira chamada: `resync=true` sobre sessão já gravada **na
mesma janela** pulava a exclusão e reinseria tudo — violação de unicidade, HTTP 500.

---

## O que a W16 tem que respeitar

- ⚠️ **Calcule por sessão.** A W15 garante que nenhuma sessão mistura partições e **não** que
  uma série de várias sessões seja homogênea. `windows` com mais de uma entrada é uma emenda, e
  um indicador que atravessa fronteira de sessão lê através dela
  ([ADR-036](../decisions/ADR-036-the-request-window-is-part-of-a-bars-identity.md)).
- ⚠️ **O universo intraday é de 3 ativos, não 4.** BBAS3 não é servido no plano gratuito, e
  nunca terá barra até o plano mudar.
- **Day trade é módulo separado** (AGENTS.md §45): não compartilha score nem estratégia com o
  motor de longo prazo. Nada aqui entra em `recommendations`.
- **Cada setup é uma função/regra independente** (roadmap §28, AGENTS.md §49–50):
  `evaluate_breakout(asset, candles)` e irmãs.
- **Nada de `adjusted_close` intraday.** Ele não existe na fonte e não foi fabricado; barras
  intraday são preço bruto negociado.
- **`Decimal` para preço** — a migration `013` já converteu o OHLC; não reintroduza `float`.
- ⚠️ **Definition of Done adicional para Day Trade** (AGENTS.md §129): entry, stop, target e
  risk definidos; fees e slippage considerados; backtest disponível; look-ahead auditado.

## O que já está pronto — não reimplemente

Todo o backend das waves 00–15 e as quatro telas. Contrato completo em
[../architecture/API.md](../architecture/API.md); a ingestão intraday em
[../architecture/BACKEND.md](../architecture/BACKEND.md).

## Os arquivos que a W16 provavelmente vai tocar

| arquivo | por quê |
|---|---|
| `backend/app/domain/daytrade/` | onde o módulo já mora (`service.py`, `schemas.py`) |
| `backend/app/domain/daytrade/service.py` | `read_intraday_bars` é a entrada dos indicadores |
| `backend/app/integrations/market_data/intraday_quality.py` | `session_date`, `EXCHANGE_TIMEZONE` |
| `backend/app/data/models/daytrade.py` | `DayTradeSetup`/`DayTradeResult` existem e **ainda são `Float`** |
| `backend/app/quant/` | o molde de cálculo puro e determinístico |
| `docs/planning/ROADMAP.md` §28 · `docs/roadmap.md` §28 | o escopo da wave |
| `AGENTS.md` §48, §49, §50, §51, §129 | indicadores, setups, score de day trade, DoD |

⚠️ **`daytrade_setups` e `daytrade_results` ainda têm preço em `Float`** — mesma dívida da regra
17 que a `013` acabou de pagar para `intraday_prices`. Migration nova na W16 ou W17.

## Também na fila, e não é wave

🔴 **Redigir a credencial da Brapi do log.** `logging.basicConfig(level=INFO)` põe o logger raiz
em INFO e o `httpx` imprime a URL com `?token=...` em texto claro. Pré-existe desde a W05,
achado na W15-006 e registrado sem corrigir (§134). É de uma linha.

⚠️ **Ingerir os eventos societários que faltam em ITUB4 e MGLU3.** A janela replayável do
universo é de **nove meses** ([ADR-032](../decisions/ADR-032-the-backtest-stops-where-the-total-return-series-stops.md),
`bounded_by: ITUB4`), o que dá um fold trimestral e **nenhum anual**.

⚠️ **O `OllamaProvider` continua não verificado** — não há servidor local — e por isso segue sem
teste de regressão, de propósito.

## Estado do ambiente (verificado 2026-08-22)

- ✅ `pytest -q` → **1.228 passed** (1.129 → 1.228 na W15). `ruff` e `black` limpos.
- ✅ **Migration nova**: `013_intraday_precision`, aplicada contra o Postgres real **e revertida
  e reaplicada** para conferir as duas direções. Schema em `013_intraday_precision`.
- ✅ **Nenhuma dependência nova.** (`tzdata` foi considerada e recusada — ver ADR-037.)
- Banco real: quatro ativos, 1.495 pregões diários cada. **Intraday: 3.555 barras de 15m** em
  PETR4/ITUB4/MGLU3 (1.185 cada, 43 sessões, `windows=['5d','3mo']`); **BBAS3 sem nenhuma**,
  por limite de plano. Último pregão diário armazenado: **2025-12-30**.
- Benchmarks: IBOV a partir de 2026-05-20, CDI de 2025-08-18. ⚠️ **Nenhum segmento anual do
  walk-forward é coberto pelo CDI** — use `objective=total-return` ou ingira mais CDI.
- ✅ **IA funcional**: `AI_PROVIDER=gemini`, `AI_MAX_OUTPUT_TOKENS=4096`. Free tier,
  **20 requisições/dia**.
- Rodar a app: `docker compose up -d postgres`, depois
  `cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000` e
  `cd frontend && npm run dev`.
  ⚠️ Rodando da máquina (fora do Docker), sobrescreva `DATABASE_URL` para `localhost` — o
  `.env` aponta para o hostname `postgres` da rede do Compose.
