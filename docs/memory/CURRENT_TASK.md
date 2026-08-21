# Current Task

## Task

**Duas coisas, e a primeira continua curta.**

1. 🔴 **Fechar a verificação da W12-001** — os dois providers de IA são código **não
   verificado** até que uma chamada real aconteça. Ver *O que continua pendente* abaixo.
2. ⚪ **Wave 14 — Walk-Forward Validation** (roadmap §26, AGENTS.md §60–62).

## Status

🟢 **A Wave 13 fechou em 2026-08-21**, 6 de 6 tasks, e não há código pela metade em lugar
nenhum. `pytest -q` → **1.049 passed**.

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

## O que continua pendente, e é a primeira coisa a fazer

🔴 **Nenhuma chamada real a modelo nenhum aconteceu** (herdado da W12).

- A `GEMINI_API_KEY` no `.env` é **válida**, mas a Gemini API está **desabilitada no
  projeto Google Cloud dela**. Toda chamada responde HTTP 403 `SERVICE_DISABLED`, com a
  URL de ativação do projeto `980912867288` no corpo.
- Não há Ollama instalado, então o `OllamaProvider` está igualmente sem verificação.

**Consequência deliberada**: nenhum teste de regressão de parser foi escrito. Um mock
construído sobre suposição não verifica a suposição — reproduz ela.

**Procedimento quando houver acesso** (`docs/planning/IMPLEMENTATION_GUIDE.md`): habilitar a
API → **uma** chamada real → conferir nome por nome (`candidates[0].content.parts[]`,
`finishReason`, `usageMetadata`, `modelVersion`) → corrigir `gemini.py` no que divergir → e
**só então** o teste de regressão.

---

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

## Estado do ambiente (verificado 2026-08-21)

- ✅ `pytest -q` → **1.049 passed** (era 944). `ruff` e `black` limpos no repositório inteiro.
- ✅ **Nenhuma migration nova**: nada da W13 é gravado (regra 16). Schema segue
  `012_corporate_actions`.
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
