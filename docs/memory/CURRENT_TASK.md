# Current Task

## Task

**Wave 15 — Day Trade Data** (roadmap §27, AGENTS.md §45, §47–49). É a próxima, e abre o
módulo intraday.

## Status

🟢 **A Wave 14 fechou em 2026-08-22**, 5 de 5 tasks, e não há código pela metade em lugar
nenhum. `pytest -q` → **1.129 passed**.

---

## O que a Wave 14 entregou

O roadmap previa uma task. A execução precisou de cinco, e as quatro a mais não são
subdivisão: a partição é uma coisa, **o que se ajusta** é outra, medir out-of-sample é uma
terceira, e rodar contra o banco real é o passo que nas waves anteriores achou o que fixture
nenhum acha.

| task | entrega |
|---|---|
| **W14-001** | A partição `Train → Validate → Test`, pura, com o corte movendo |
| **W14-002** | A grade de políticas candidatas e o objetivo de seleção |
| **W14-003** | O serviço: treino ordena, validação escolhe, **teste só reporta** |
| **W14-004** | `GET /api/v1/backtests/walk-forward` |
| **W14-005** | Rodar contra o banco real, e corrigir o que ele achou |

### O ponto inteiro da wave, em uma frase

**Nada medido no teste alcança uma seleção.** É a regra 61 inteira, e é a única razão de um
número out-of-sample significar alguma coisa.

### As duas decisões que sustentam isso

1. **A grade é conjunto de hipóteses, não espaço de busca**
   ([ADR-034](../decisions/ADR-034-the-grid-is-a-hypothesis-set-not-a-search-space.md)). Sete
   candidatos, cada um diferindo da política do chamador em **um** campo, cada um com a
   pergunta que responde escrita ao lado. Produto cartesiano dos mesmos eixos seria dezoito —
   varredura vestida de walk-forward. Empate vai para a política **já em produção**.
2. **Os três segmentos têm o mesmo tamanho e cada um parte de carteira vazia**
   ([ADR-035](../decisions/ADR-035-equal-segments-from-an-empty-portfolio.md)). Confundidor
   removido por construção: a idade da carteira contaminaria a própria comparação que a wave faz.

### O defeito que rodar contra o banco real encontrou

Candidato que **não preencheu ordem nenhuma** era pontuado em **zero** — e zero ganha de todo
candidato que aplicou e perdeu. Índice achatado em 100 por construção, então uma política que
não financiou nada venceria qualquer ano de queda. Agora é `NO_POSITION_TAKEN`, não-ranqueável.

### O veredicto, que é o produto da wave

PETR4+BBAS3, três folds anuais, objetivo `total-return`:

| fold | vencedor | in-sample | out-of-sample | degradação |
|---|---|---|---|---|
| 0 | — (`NO_POSITION_TAKEN`) | — | — | — |
| 1 | `min-score-30` | 46,20% | 101,38% | −0,5518 |
| 2 | `min-score-70` | 101,58% | **11,34%** | **+0,9024** |

`selection_rate` **0,50**. O fold 2 escolheu por **0,2 p.p.** e perdeu **90 pontos** fora da
amostra, e a `default` não foi selecionada em fold nenhum. **Os parâmetros não são estáveis**
sobre a história que existe hoje — e isso é o resultado, não a falha.

---

## O que a W15 tem que respeitar

- **Day trade é módulo separado** (AGENTS.md §45): não compartilha score nem estratégia com o
  motor de longo prazo. Nada aqui entra no `recommendations`.
- ⚠️ **É a primeira integração externa nova desde a IA.** O procedimento do
  [IMPLEMENTATION_GUIDE](../planning/IMPLEMENTATION_GUIDE.md) vale inteiro: **uma chamada real
  → conferir nome por nome → só então parser e mocks → teste de regressão com valores reais**.
  A W06-003 e a verificação da W12-001 são as duas provas de por que ele existe.
- **`intraday_prices` já existe como model** desde a W02 — leia antes de criar coluna. ⚠️ O OHLC
  dela ainda é `Float`, o que a regra 17 não permite; a conversão foi explicitamente adiada para
  esta wave (ver *Monetary precision* em [../PROJECT_STATUS.md](../PROJECT_STATUS.md)). Migration
  nova, portanto.
- **Timezone explícito** (regra 18). Vela intraday sem timezone é vela sem hora, e
  `IntradayPrice.timestamp` é `DateTime` **naive** hoje — nenhum model do projeto usa
  `DateTime(timezone=True)`, então isto é decisão a tomar na wave e não padrão a copiar.
- **Detecção de gap** é parte do escopo, não polimento: pregão com buraco de dez minutos é dado
  que precisa dizer que está furado, não série mais curta.

## O que já está pronto — não reimplemente

Todo o backend das waves 00–14 e as quatro telas. Contrato completo em
[../architecture/API.md](../architecture/API.md); backtesting e walk-forward em
[../architecture/BACKEND.md](../architecture/BACKEND.md).

## Os arquivos que a W15 provavelmente vai tocar

| arquivo | por quê |
|---|---|
| `backend/app/data/models/assets.py` | onde `IntradayPrice` mora hoje |
| `backend/migrations/versions/` | migration nova (OHLC intraday → `NUMERIC`) |
| `backend/app/integrations/market_data/` | o padrão de provider a replicar |
| `backend/app/integrations/http.py` | o transporte compartilhado (retry/backoff/throttle) |
| `backend/app/domain/market_data/service.py` | o molde de serviço de ingestão idempotente |
| `backend/app/integrations/market_data/data_quality.py` | o molde de validador puro |
| `docs/planning/ROADMAP.md` §27 · `docs/roadmap.md` §27 | o escopo da wave |
| `AGENTS.md` §18, §19, §20, §45, §47 | timezone, market data, data quality, day trade |

## Também na fila, e não é wave

⚠️ **Ingerir os eventos societários que faltam em ITUB4 e MGLU3.** A janela replayável do
universo dos quatro é de **nove meses** ([ADR-032](../decisions/ADR-032-the-backtest-stops-where-the-total-return-series-stops.md),
`bounded_by: ITUB4`), o que dá um fold trimestral e **nenhum anual**. É o único caminho para uma
afirmação de estabilidade que valha alguma coisa. Relaxar o esquema não é alternativa.

⚠️ **O `OllamaProvider` continua não verificado** — não há servidor local — e por isso segue sem
teste de regressão, de propósito.

## Estado do ambiente (verificado 2026-08-22)

- ✅ `pytest -q` → **1.129 passed** (1.063 → 1.129 na W14). `ruff` e `black` limpos.
- ✅ **Nenhuma migration nova**: nada da W14 é gravado (regra 16). Schema segue
  `012_corporate_actions`.
- ✅ **Nenhuma dependência nova.**
- Banco real: quatro ativos, 1.495 pregões cada. Série ajustada **completa** em BBAS3 e PETR4;
  **198** pregões em ITUB4 e **478** em MGLU3. Só a PETR4 tem setor e demonstrativos. Último
  pregão armazenado: **2025-12-30**.
- Benchmarks: IBOV a partir de 2026-05-20, CDI de 2025-08-18. ⚠️ **Nenhum segmento anual do
  walk-forward é coberto pelo CDI**, então o objetivo padrão (`sharpe`) recusa com
  `OBJECTIVE_UNAVAILABLE` — use `objective=total-return` ou ingira mais CDI.
- ✅ **IA funcional**: `AI_PROVIDER=gemini`, `AI_MAX_OUTPUT_TOKENS=4096`. Free tier,
  **20 requisições/dia**.
- Rodar a app: `docker compose up -d postgres`, depois
  `cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000` e
  `cd frontend && npm run dev`.
  ⚠️ Rodando da máquina (fora do Docker), sobrescreva `DATABASE_URL` para `localhost` — o
  `.env` aponta para o hostname `postgres` da rede do Compose.
