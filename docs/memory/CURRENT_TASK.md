# Current Task

## Task

**Uma coisa: a Wave 14.** A pendência que vinha na frente fechou.

1. ✅ **Verificação da W12-001 (Gemini)** — feita em 2026-08-22. Ver *O que a verificação
   encontrou* abaixo.
2. 🔵 **Wave 14 — Walk-Forward Validation** (roadmap §26, AGENTS.md §60–62) — **é a próxima**.

## Status

🟢 **A Wave 13 fechou em 2026-08-21**, 6 de 6 tasks, e não há código pela metade em lugar
nenhum. Em 2026-08-22, fora de wave, a **verificação da Gemini** fechou e corrigiu o defeito
que ela encontrou. `pytest -q` → **1.063 passed**.

---

## O que a Wave 13 entregou

O roadmap previa duas tasks. A execução precisou de seis, e as quatro a mais não são
subdivisão — são coisas que só apareceram ao construir.

| task | entrega |
|---|---|
| **W13-001** | Ação societária aplicada no replay do ledger — **defeito de wave anterior**, e pré-requisito honesto |
| **W13-002** | O motor de simulação, puro e sem I/O, onde o look-ahead fica *fora de alcance* |
| **W13-003** | A **própria estratégia do projeto** replayada, com o lag de publicação da CVM ([ADR-031](../decisions/ADR-031-a-statement-is-readable-only-after-the-filing-deadline.md)) |
| **W13-004** | Métricas de execução: `alpha` no quant, *slippage* **medido**, trade fechado ausente por desenho |
| **W13-005** | O serviço, com a janela parando onde a série de retorno total para ([ADR-032](../decisions/ADR-032-the-backtest-stops-where-the-total-return-series-stops.md)) |
| **W13-006** | `GET /api/v1/backtests` |

### O ponto inteiro da wave, em uma frase

**O backtest fala ledger.** A saída da simulação são linhas de `Transaction` — o mesmo
formato de uma carteira real — então `compute_positions`, `value_series` e
`performance_index` medem um backtest com **exatamente** o código que mede a carteira do
investidor. E a estratégia sob teste não é *uma* estratégia: é `allocate_contribution`, a
mesma função pura que `/contribution-plan` chama hoje. Backtest de reimplementação mede a
reimplementação.

### As três coisas que ficam fora de alcance em vez de desencorajadas

1. **Preço futuro.** A decisão recebe um `SimulationState` com o dia, o caixa, as posições e
   os fechamentos **daquela sessão** — não o mapa de preços, não o calendário, nada que ela
   possa indexar para frente. E a ordem decidida numa sessão preenche na **seguinte**, porque
   um fechamento só pode ser lido depois de impresso.
2. **Balanço futuro.** Exercício que fecha em 31 de dezembro não é público em 1º de janeiro.
   Três meses — o prazo do DFP na CVM, a data legal mais tardia — e o teste percorre uma
   década de datas provando que a regra só consegue **segurar** um demonstrativo, nunca
   soltá-lo cedo.
3. **Provento que o projeto não sabe dimensionar.** A janela começa onde **todo** ativo tem
   série de retorno total completa. Não é só medição: sessão marcada ex sem ação dimensionada
   é distribuição que a simulação não paga, e a execução ficaria **errada**, não apenas
   não-mensurável.

### Os dois defeitos que rodar contra o banco real encontrou

Nenhum era alcançável por fixture, e os dois saíram de **ler** uma execução de seis anos:

1. **Um feriado estava sendo reportado como problema de dado.** Ninguém negocia em 1º de
   janeiro, então uma execução pedida a partir do dia 1º começa no dia 2 — e
   `window.bounded_by` nomeava um ativo por isso. O campo existe para o caso honesto;
   dispará-lo por um dia de calendário torna o caso honesto ilegível.
2. **Alpha estava sendo calculado contra o CDI.** O `compare` deliberadamente não reporta
   beta para benchmark de **taxa**, e alpha é a aritmética do beta. Estava reportando 0,30
   p.p. de habilidade contra um número que não mede nada. O portão passou a ser o beta que o
   `compare` alcançou — segunda leitura do tipo do benchmark é como as duas passariam a
   discordar.

### O que a execução real mostrou, e não é defeito

Com PETR4 e BBAS3 (1.495 de 1.495 pregões ajustados cada), seis anos: **R$ 72.000 aportados,
28 compras, R$ 58.471 em caixa**. Cada recusa é nomeada. Três dos quatro ativos não têm
demonstrativo e nunca passam do piso de cobertura, e a **PETR4 cai de 62,28 para 35,83** no
instante em que é detida — 15 pontos são o pilar de concentração
([ADR-027](../decisions/ADR-027-target-weight-comes-from-merit.md)) e 11,45 são a regra 109
entregando o exercício de 2024 no vencimento do prazo da CVM.

Com os quatro ativos, a janela cai de 2020-01-01 para **2025-03-19**, `bounded_by: ITUB4`,
cuja série ajustada tem 198 de 1.495 pregões.

---

## O que a verificação encontrou (2026-08-22)

✅ **A Gemini API está habilitada e respondendo.** HTTP 200, chamada real feita, e o contrato
`v1beta` publicado bateu **nome por nome**: `candidates[0].content.parts[]`, `finishReason`,
`usageMetadata.promptTokenCount`, `usageMetadata.candidatesTokenCount`, `modelVersion`. Nada
com nome errado — diferente da Brapi na W06-003, que é a razão de o procedimento existir.

✅ **O teste de regressão existe**: `tests/test_gemini_provider.py`, 11 testes, todos
construídos a partir de payloads capturados **depois** da chamada real.

🔴 **E a chamada real achou um defeito que nenhum fixture acharia.** `gemini-flash-latest`
resolve para **`gemini-3.7-flash`, um modelo de raciocínio**, e o raciocínio é cobrado contra o
mesmo `maxOutputTokens` da prosa. Medido com um fact pack realista de plano de aporte:

| orçamento | `finishReason` | pensamento | prosa | resultado |
|---|---|---|---|---|
| **1.024** (o padrão) | `MAX_TOKENS` | 981 | 39 | frase cortada em `"...entre três ativos:"` |
| 2.048 | `STOP` | 1.383 | 295 | explicação completa |

Como `MAX_TOKENS` estava em `_COMPLETE` e o texto não estava vazio, **o fragmento chegava ao
leitor como explicação pronta** — no valor padrão, com um pack comum, não numa borda.

Corrigido em [ADR-033](../decisions/ADR-033-a-truncated-explanation-is-reported-not-discarded.md):
`MAX_TOKENS` é truncagem, o provider normaliza para `Completion.truncated`, `Explanation.truncated`
leva isso à API, e o texto é entregue **exatamente como gerado** — aparar até a última frase
inteira produziria algo que *parece* completo. `thinking_tokens` passou a ser contado ao lado da
prosa (nunca somado), e `AI_MAX_OUTPUT_TOKENS` subiu para 4.096.

### O que continua pendente

⚠️ **O `OllamaProvider` segue não verificado** — não há servidor Ollama nesta máquina. Por isso
**nenhum teste de regressão foi escrito para ele**, pela mesma disciplina que produziu o achado
acima. Ele carrega uma suposição a mais, agora nomeada no docstring: `done_reason == "length"`
lido como truncagem. Se estiver errada, uma explicação local truncada será reportada como
completa — exatamente o defeito que a Gemini acabou de mostrar.

⚠️ **A chave é free tier: 20 requisições/dia** para `gemini-3.7-flash`, e o modelo devolve 503
`"high demand"` com frequência. Dimensione qualquer validação ao vivo por isso.

## O que a W14 tem que respeitar

- **A W13 inteira já existe**: motor, estratégia e métricas. O que falta é o
  **particionamento** das janelas (treino / validação / teste) e o que se afirma a partir
  dele — estabilidade, e não um número melhor.
- ⚠️ **A janela herdada é apertada.** Uma série já truncada por
  [ADR-032](../decisions/ADR-032-the-backtest-stops-where-the-total-return-series-stops.md)
  tem menos espaço para ser dividida em três: o universo dos quatro ativos acompanhados dá
  **nove meses**. Ampliar isso é ingerir os eventos societários que faltam, **não** relaxar a
  regra.
- **Nada de ajustar parâmetro até o histórico ficar bonito** (regra 60). A wave existe para
  medir estabilidade, e um `min_score` escolhido por dar o melhor retorno passado é
  exatamente o que ela deve detectar.
- **Determinismo** (regra 113): mesma entrada, mesmo resultado, sempre. Já vale para o
  backtest e tem teste; a partição de janelas não pode quebrá-lo.

## O que já está pronto — não reimplemente

Todo o backend das waves 00–13 e as quatro telas. Contrato completo em
[../architecture/API.md](../architecture/API.md); o backtesting em
[../architecture/BACKEND.md](../architecture/BACKEND.md).

## Os arquivos que a W14 provavelmente vai tocar

A wave **consome** a W13 inteira, então quase tudo abaixo é leitura, não reescrita:

| arquivo | por quê |
|---|---|
| `backend/app/domain/backtesting/service.py` | é onde a janela é decidida hoje; o particionamento nasce ao lado |
| `backend/app/domain/backtesting/simulation.py` | o motor e seus objetos — **consumir, não alterar** |
| `backend/app/domain/backtesting/universe.py` | a estratégia numa data passada, já com o lag da CVM |
| `backend/app/domain/backtesting/metrics.py` | as métricas por janela que a W14 vai comparar entre partições |
| `backend/app/domain/backtesting/schemas.py` | os contratos Pydantic; a saída da W14 entra aqui |
| `backend/app/api/routes/backtests.py` | o endpoint existente, se a wave expuser o walk-forward |
| `docs/planning/ROADMAP.md` §26 | o escopo da wave |
| `AGENTS.md` §60–62 | as regras de overfitting/validação que a wave existe para respeitar |

## Estado do ambiente (verificado 2026-08-22)

- ✅ `pytest -q` → **1.063 passed** (944 → 1.049 na W13 → 1.063 com a verificação da Gemini).
  `ruff` e `black` limpos nos arquivos alterados.
- ✅ **Nenhuma migration nova**: nada da W13 é gravado (regra 16), e a verificação da Gemini
  também não grava nada. Schema segue `012_corporate_actions`.
- ✅ **IA funcional**: `AI_PROVIDER=gemini`, `GEMINI_MODEL=gemini-flash-latest` (resolve para
  `gemini-3.7-flash`), `AI_MAX_OUTPUT_TOKENS=4096`. Free tier, **20 requisições/dia**.
- Banco real: quatro ativos, 1.495 pregões cada. Série ajustada **completa** em BBAS3 e
  PETR4; **198** pregões em ITUB4 (último buraco em 2025-03-18) e **478** em MGLU3 (último em
  2024-02-01). Só a PETR4 tem setor e demonstrativos.
- Benchmarks ingeridos não cobrem a janela do backtest: IBOV a partir de 2026-05-20, CDI de
  2025-08-18. Um comparativo contra o CDI mede quatro meses de uma execução de seis anos — e
  `comparison.subject.start_date` é o que diz isso.
- Rodar a app: `docker compose up -d postgres`, depois
  `cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000` e
  `cd frontend && npm run dev`.
  ⚠️ Rodando da máquina (fora do Docker), sobrescreva `DATABASE_URL` para `localhost` — o
  `.env` aponta para o hostname `postgres` da rede do Compose.
