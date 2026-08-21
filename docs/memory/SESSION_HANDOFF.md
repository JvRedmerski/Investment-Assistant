# Session Handoff

## Last Updated

2026-08-21

## Last Completed Work

### Wave 13 — Backtesting de carteira, 6/6 (`02cd288`, `a42a91f`, `6409568`, `67b6cf7`, `9c55cab`, `6142a97`, `0f5bb0b`)

O roadmap previa duas tasks. Foram seis, e as quatro a mais não são subdivisão — são coisas
que só apareceram ao construir.

| task | entrega |
|---|---|
| **W13-001** | Ação societária aplicada no replay do ledger — defeito de wave anterior |
| **W13-002** | O motor de simulação, puro e sem I/O |
| **W13-003** | A própria estratégia do projeto replayada, com o lag da CVM ([ADR-031](../decisions/ADR-031-a-statement-is-readable-only-after-the-filing-deadline.md)) |
| **W13-004** | `alpha` no quant, *slippage* **medido**, trade fechado ausente por desenho |
| **W13-005** | O serviço, com a janela parando onde a série de retorno total para ([ADR-032](../decisions/ADR-032-the-backtest-stops-where-the-total-return-series-stops.md)) |
| **W13-006** | `GET /api/v1/backtests` |

### Por que a wave não tem uma segunda contabilidade

**O backtest fala ledger.** A saída da simulação são linhas de `Transaction`, então
`compute_positions`, `value_series` e `performance_index` medem um backtest com exatamente o
código que mede a carteira do investidor. Um segundo caminho de valorização seria um segundo
conjunto de bugs, e a primeira divergência apareceria como um backtest discordando do
dashboard por motivo que ninguém saberia nomear.

Pela mesma razão a estratégia **não é reimplementada**: `universe.py` monta os candidatos como
estariam numa data passada e entrega a `allocate_contribution` — a mesma função pura que
`/contribution-plan` chama hoje.

### As três formas de olhar o futuro, e como cada uma foi fechada

1. **Preço.** A decisão recebe os fechamentos **daquela sessão** e nada mais, e a ordem
   preenche na **seguinte** — um fechamento só pode ser lido depois de impresso. O intervalo
   entre decidir e preencher é onde mora o *slippage*, que por isso é **medido** e não
   assumido a alguma taxa em pontos-base.
2. **Balanço.** A regra 108 bastava para um score de hoje e não para um backtest: exercício
   que fecha em 31 de dezembro não é público em 1º de janeiro. Três meses, o prazo do DFP —
   a data **legal mais tardia**, porque errar para tarde custa informação e errar para cedo
   dá informação que ninguém tinha.
3. **Provento.** A janela começa onde **todo** ativo tem série de retorno total completa.
   Sessão marcada ex sem ação dimensionada é distribuição que a simulação não paga: a
   execução ficaria **errada**, não apenas não-mensurável.

### Os dois defeitos que rodar contra o banco real encontrou

Nenhum era alcançável por fixture, e os dois saíram de **ler** uma execução de seis anos —
o mesmo passo que achou os dois erros de janela da W11.

1. **Um feriado estava sendo reportado como problema de dado.** Ninguém negocia em 1º de
   janeiro, então uma execução pedida a partir do dia 1º começa no dia 2, e
   `window.bounded_by` nomeava um ativo por isso. Passou a comparar contra a primeira sessão
   que o universo de fato tem.
2. **Alpha estava sendo calculado contra o CDI.** O `compare` deliberadamente não reporta
   beta para benchmark de **taxa**, e alpha é a aritmética do beta. O portão passou a ser o
   beta que o `compare` alcançou — segunda leitura do tipo do benchmark é como as duas
   passariam a discordar.

Um terceiro achado, este de convenção e não de correção: `schemas.py` é a camada Pydantic em
**13 de 13** módulos, e a W13-002 tinha feito o de backtesting guardar as dataclasses do
motor. Elas foram para `simulation.py`, ao lado do replay que as produz.

## Current State

- `pytest` → **1.049 passed** (944 → 1.049), verificado em 2026-08-21. `ruff` e `black`
  limpos no repositório inteiro.
- **Nenhuma migration**: nada da W13 é gravado (regra 16). Schema segue `012_corporate_actions`.
- **Nenhuma dependência nova.** `alpha` entrou em `app/quant/risk.py`, em `Decimal`, como
  todo o resto do motor.
- **Wave 13 🟢 concluída**, 6/6. Nada iniciado da W14.

## Important Details

### 🔴 O que NÃO foi verificado, e é a primeira coisa a fazer

**Nenhuma chamada real a modelo nenhum aconteceu** (herdado da W12). A `GEMINI_API_KEY` é
válida, mas a Gemini API está **desabilitada no projeto Google Cloud dela** — HTTP 403
`SERVICE_DISABLED`, projeto `980912867288`. Não há Ollama local. Por isso **nenhum teste de
regressão de parser foi escrito**, de propósito. Procedimento completo em
[CURRENT_TASK.md](CURRENT_TASK.md).

### Os enganos fáceis de cometer aqui

**`wealth` não é desempenho.** É patrimônio em BRL com `contributed` por baixo. A resposta
comparável a um benchmark é `comparison`, que é time-weighted. Exibir a primeira sozinha é a
leitura que o [ADR-019](../decisions/ADR-019-portfolio-return-is-time-weighted.md) existe para
impedir.

**`comparison` descreve um período mais curto que `index`** sempre que o benchmark tem menos
histórico — os dois lados são recortados à janela compartilhada. Medido: uma execução de seis
anos comparada com o CDI reporta **quatro meses**, porque 2025-08-18 é o começo do CDI
ingerido. `subject.start_date` é o que diz isso.

**As cinco figuras de trade fechado voltam `null` de propósito.** `win_rate`, `average_win`,
`average_loss`, `profit_factor` e `expectancy` são definidas sobre trade **fechado**, e nada
que este projeto entrega vende ([ADR-028](../decisions/ADR-028-rebalancing-is-cash-flow-only.md)).
`closed_trades: 0` é o que diz por quê — `0%` leria como *toda operação perdeu*.

**Uma janela curta não é bug do backtest.** ITUB4 reduz seis anos a nove meses porque sua
série ajustada tem 198 de 1.495 pregões. A correção é a montante — dimensionar os eventos que
faltam — e **nunca** relaxar a regra de completude.

**O lag de publicação é zero por padrão.** `score_asset(publication_lag_months=0)` deixa o
caminho vivo exatamente como estava (regra 134). Só o backtest passa o valor real. O
corolário é que `GET /portfolios/{id}/scores?as_of=` faz pergunta histórica sem lag — está em
Future Work.

**Não guarde a magnitude de um evento em `share_ratio` e `cash_amount` ao mesmo tempo.**
Exatamente uma das duas é preenchida por linha, e é isso que separa "quanto pagou" de
"quantas ações virou".

## Pending Work

1. **Verificar os providers de IA contra uma resposta real** (acima).
2. **Wave 14 — Walk-Forward Validation**. Ver [CURRENT_TASK.md](CURRENT_TASK.md) e o roadmap §26.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md). Se a Gemini API já estiver habilitada, comece pelo
item 1 — são vinte minutos e ele tira dois módulos do estado "não verificado".

## Relevant Files

- `backend/app/domain/backtesting/simulation.py` — o motor **e** os objetos que ele fala
- `backend/app/domain/backtesting/metrics.py` — trade fechado, taxas e o *slippage* medido
- `backend/app/domain/backtesting/availability.py` — quando um demonstrativo virou público
- `backend/app/domain/backtesting/universe.py` — a estratégia do projeto, numa data passada
- `backend/app/domain/backtesting/service.py` — o que pode ser replayado, e a partir de quando
- `backend/app/domain/backtesting/schemas.py` — os contratos da API (Pydantic, como nos outros)
- `backend/app/quant/risk.py` — `alpha`, ao lado do `beta` em que se apoia
- `backend/app/api/routes/backtests.py` — `GET /api/v1/backtests`
- `docs/decisions/ADR-031-*.md` e `ADR-032-*.md`
