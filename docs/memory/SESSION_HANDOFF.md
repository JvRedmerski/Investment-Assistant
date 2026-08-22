# Session Handoff

## Last Updated

2026-08-22

## Last Completed Work

### Verificação da W12-001 — a Gemini, fora de wave (2026-08-22)

A pendência que abria as últimas duas sessões fechou pela metade que dependia de acesso. O
procedimento do [IMPLEMENTATION_GUIDE](../planning/IMPLEMENTATION_GUIDE.md) foi seguido na
ordem: **uma chamada real → conferir nome por nome → corrigir o que divergiu → e só então o
teste de regressão**.

| o que | resultado |
|---|---|
| contrato `v1beta` | bateu **nome por nome** — nenhum campo com nome errado |
| `modelVersion` | `gemini-3.7-flash` (o alias resolveu, e a trilha de auditoria captura isso) |
| **orçamento de saída** | 🔴 **defeito**: pensamento come `maxOutputTokens`, e `MAX_TOKENS` contava como término normal |
| `thoughtsTokenCount` | 🔴 não era contado: `output_tokens` reportava 153 numa requisição de 701 |
| `OllamaProvider` | ⚠️ continua sem verificação e sem teste (sem servidor local) |

**O defeito, em uma frase:** uma explicação cortada no meio da frase era servida ao leitor como
se estivesse pronta. Agora `MAX_TOKENS` é truncagem, o provider normaliza para
`Completion.truncated`, `Explanation.truncated` leva isso à API, e o texto vai **exatamente
como gerado** — aparar até a última frase inteira produziria algo que *parece* completo, que é
o defeito com uma camada a mais em cima
([ADR-033](../decisions/ADR-033-a-truncated-explanation-is-reported-not-discarded.md)).

**Rejeitada por medição, não por gosto:** limitar o raciocínio via `thinkingConfig`.
`thinkingBudget: 0` é aceito com HTTP 200 e **ignorado** (398 tokens de pensamento assim mesmo);
`thinkingLevel: "low"` idem, com 436. Um botão que o fornecedor aceita e não honra documenta uma
garantia que não existe.


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

- `pytest` → **1.063 passed** (944 → 1.049 na W13 → 1.063 com a verificação da Gemini),
  verificado em 2026-08-22. `ruff` e `black` limpos nos arquivos alterados.
- **Nenhuma migration**: nada da W13 é gravado (regra 16), e a verificação da Gemini também não
  grava nada. Schema segue `012_corporate_actions`.
- **IA funcional**: `AI_PROVIDER=gemini`, `AI_MAX_OUTPUT_TOKENS` subiu de 1.024 para **4.096**.
- **Nenhuma dependência nova.** `alpha` entrou em `app/quant/risk.py`, em `Decimal`, como
  todo o resto do motor.
- **Wave 13 🟢 concluída**, 6/6. Nada iniciado da W14.

## Important Details

### ✅ A verificação da IA fechou para a Gemini — e achou um defeito

A API respondeu, o contrato `v1beta` bateu **nome por nome**, e o teste de regressão existe
(`tests/test_gemini_provider.py`, 11 testes sobre payload capturado).

**O que ela achou não foi nome errado, foi orçamento.** `gemini-flash-latest` resolve para
`gemini-3.7-flash`, um **modelo de raciocínio**, e o pensamento é cobrado contra o mesmo
`maxOutputTokens` da prosa. No padrão de então (1.024), com um fact pack comum de plano de
aporte: 981 tokens pensando, 39 de texto, `finishReason: MAX_TOKENS` e uma frase cortada em
`"...entre três ativos:"`. E como `MAX_TOKENS` estava em `_COMPLETE` e o texto não estava
vazio, **o fragmento era entregue como explicação pronta** — no valor padrão, não numa borda.

Ver [ADR-033](../decisions/ADR-033-a-truncated-explanation-is-reported-not-discarded.md).

⚠️ **O `OllamaProvider` continua não verificado** — não há servidor local. Pela mesma
disciplina, **nenhum teste de regressão foi escrito para ele**, e ele carrega agora uma
suposição a mais e nomeada no docstring: `done_reason == "length"`.

⚠️ **A chave é free tier: 20 requisições/dia** para `gemini-3.7-flash`, e o modelo devolve 503
`"high demand"` com frequência. Uma sessão de validação ao vivo tem que caber nisso.

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

1. **Wave 14 — Walk-Forward Validation**. Ver [CURRENT_TASK.md](CURRENT_TASK.md) e o roadmap §26.
2. **Verificar o `OllamaProvider`** contra um servidor real, quando houver um. É o que resta da
   pendência da W12-001, e a Gemini acabou de mostrar que a espera se paga.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md) e **começar a Wave 14**. Não há mais nada na frente
dela: a pendência da IA que abria as duas últimas sessões fechou no que dependia de acesso, e
o que sobra (Ollama) depende de instalar um servidor, não de uma decisão do projeto.

## Relevant Files

- `backend/app/domain/backtesting/simulation.py` — o motor **e** os objetos que ele fala
- `backend/app/domain/backtesting/metrics.py` — trade fechado, taxas e o *slippage* medido
- `backend/app/domain/backtesting/availability.py` — quando um demonstrativo virou público
- `backend/app/domain/backtesting/universe.py` — a estratégia do projeto, numa data passada
- `backend/app/domain/backtesting/service.py` — o que pode ser replayado, e a partir de quando
- `backend/app/domain/backtesting/schemas.py` — os contratos da API (Pydantic, como nos outros)
- `backend/app/quant/risk.py` — `alpha`, ao lado do `beta` em que se apoia
- `backend/app/api/routes/backtests.py` — `GET /api/v1/backtests`
- `docs/decisions/ADR-031-*.md`, `ADR-032-*.md` e `ADR-033-*.md`
- `backend/app/integrations/ai/gemini.py` — o formato do fio, agora com a resposta real documentada
- `backend/app/integrations/ai/schemas.py` — `Completion.truncated` e `thinking_tokens`
- `backend/tests/test_gemini_provider.py` — os payloads capturados, e o defeito travado
