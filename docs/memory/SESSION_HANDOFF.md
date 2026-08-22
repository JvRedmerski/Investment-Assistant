# Session Handoff

## Last Updated

2026-08-22

## Last Completed Work

### Wave 14 — Walk-Forward Validation, 5/5 (`8e3d820`, `ca60909`, `f806ab0`, `df8cec3`, e o commit da W14-005)

O roadmap previa uma task. Foram cinco, e as quatro a mais não são subdivisão: a partição é
uma coisa, **o que se ajusta** é outra, medir out-of-sample é uma terceira, e rodar contra o
banco real é o passo que nas waves anteriores achou o que fixture nenhum acha.

| task | entrega |
|---|---|
| **W14-001** | A partição `Train → Validate → Test`, pura, com o corte movendo |
| **W14-002** | A grade de políticas candidatas e o objetivo de seleção |
| **W14-003** | O serviço: treino ordena, validação escolhe, **teste só reporta** |
| **W14-004** | `GET /api/v1/backtests/walk-forward` |
| **W14-005** | Rodar contra o banco real, e corrigir o que ele achou |

### O ponto da wave, em uma frase

**Nada medido no teste alcança uma seleção.** Treino pergunta à grade inteira, validação
pergunta só à shortlist sobre história que a ordenação não viu, e teste roda o vencedor e mais
ninguém. É a regra 61 inteira, e é a única razão de um número out-of-sample significar alguma
coisa.

E nada de novo é medido: cada segmento é um `run_backtest` sobre o mesmo universo, então um
fold é medido pelo mesmo código que mede a carteira do investidor — a mesma razão de a W13 não
ter uma segunda contabilidade. `testable_universe` saiu de dentro do `run_backtest` para que a
partição caia sobre **o mesmo intervalo** que uma execução única usaria.

### As duas decisões, e por que cada uma é a decisão

1. **A grade é conjunto de hipóteses, não espaço de busca**
   ([ADR-034](../decisions/ADR-034-the-grid-is-a-hypothesis-set-not-a-search-space.md)).
   Espaço de busca é varrido: mais pontos deixam o melhor ponto melhor **em descrever o ruído
   em que foi ajustado**. Conjunto de hipóteses é perguntado. Sete candidatos, um campo cada,
   com a pergunta escrita ao lado — o produto cartesiano dos mesmos três eixos seria dezoito.
   Empate vai para a política **já em produção**, e candidato sem valor de objetivo é **ausente
   da ordenação**, não último.
2. **Os três segmentos têm o mesmo tamanho e cada um parte de carteira vazia**
   ([ADR-035](../decisions/ADR-035-equal-segments-from-an-empty-portfolio.md)). A estratégia
   constrói carteira por aporte mensal, então o tamanho do segmento muda **o que ele mede**: um
   teste mais curto reportaria degradação que é em parte só carteira mais nova, e ninguém
   saberia dizer qual parte. Confundidor removido por construção.

### O defeito que rodar contra o banco real encontrou

Candidato que **não preencheu ordem nenhuma** era pontuado em **zero**. `performance_index`
sobre ledger de depósitos sem compra é achatado em 100 *por construção* — e zero ganha de todo
candidato que aplicou e perdeu dinheiro. Uma política que não financiou nada venceria **qualquer
ano de queda**. Agora é `NO_POSITION_TAKEN`: não-ranqueável, não pontuado em zero.

### O veredicto, que é o produto da wave

PETR4+BBAS3, três folds anuais, `total-return`: o vencedor **mudou a cada fold**
(`selection_rate` 0,50), o fold 2 escolheu por **0,2 ponto percentual** e perdeu **90 pontos**
de retorno fora da amostra, e a `default` — a política que o projeto entrega — não foi
selecionada em fold nenhum. **Os parâmetros não são estáveis** sobre a história que existe hoje.

Isso é o resultado da wave, não a falha dela. Uma wave de validação que só sabe dizer "passou"
não valida nada.

## Current State

- `pytest` → **1.129 passed** (1.063 → 1.129 na W14), verificado em 2026-08-22. `ruff` e
  `black` limpos.
- **Nenhuma migration**: nada da W14 é gravado (regra 16). Schema segue `012_corporate_actions`.
- **Nenhuma dependência nova.**
- **Wave 14 🟢 concluída**, 5/5. Nada iniciado da W15.

## Important Details

### Os enganos fáceis de cometer aqui

**A figura que responde a pergunta é `stability.degradation_mean`, não o retorno.** Estratégia
cujo out-of-sample acompanha o in-sample tem parâmetro que descreve alguma coisa; a que desaba
tem parâmetro que descrevia a amostra. `selection_rate` é a outra metade: vencedor diferente a
cada fold é **ruído**, não parâmetro.

**Com um fold só, todo agregado vem `null`** e `refusal` é `SINGLE_FOLD`. Média de uma
observação e dispersão zero leriam como *perfeitamente estável*.

⚠️ **O objetivo mede o dinheiro *aplicado*, não o dado.** Tudo sai do índice time-weighted, que
avalia posição e **não caixa** ([ADR-019](../decisions/ADR-019-portfolio-return-is-time-weighted.md)).
Medido: um segmento de 2023 sobre PETR4+BBAS3 terminou com **R$ 3.239,88 em posição e
R$ 9.892,81 em caixa** sobre R$ 12.000 aportados — índice **+101,38%**, dinheiro **+9,44%**. O
caixa não é ociosidade, é o teto funcionando: com dois ativos e `max_asset_weight` em 20%, no
máximo 40% da carteira pode estar aplicada. `contributed` e `final_value` vêm lado a lado; o
**ranking** não os enxerga. Em *Future Work*.

⚠️ **O objetivo padrão (`sharpe`) recusa contra o banco real.** O CDI ingerido começa em
2025-08-18 e nenhum segmento anual é coberto, então todos os folds voltam
`OBJECTIVE_UNAVAILABLE`. Use `objective=total-return` ou ingira mais CDI — e note que **não há
fallback silencioso** de propósito: ele tornaria duas execuções do mesmo comando incomparáveis
conforme o que estivesse no banco.

⚠️ **O esquema padrão (12/12/12) não cabe no universo dos quatro ativos.** Nove meses de janela
replayável contra 36 exigidos → `WINDOW_TOO_SHORT`, `bounded_by: ITUB4`. Com esquema trimestral
sai exatamente **um** fold. A correção é ingerir os eventos societários que faltam, **nunca**
encurtar os segmentos.

### E os da W13, que continuam valendo

**`wealth` não é desempenho.** É patrimônio em BRL com `contributed` por baixo. A resposta
comparável a um benchmark é `comparison`, que é time-weighted (ADR-019).

**As cinco figuras de trade fechado voltam `null` de propósito** — são definidas sobre trade
fechado, e nada que este projeto entrega vende (ADR-028).

**O lag de publicação é zero por padrão** no caminho vivo; só o backtest passa o valor real.

## Pending Work

1. **Wave 15 — Day Trade Data** (roadmap §27). Ver [CURRENT_TASK.md](CURRENT_TASK.md).
   ⚠️ Primeira integração externa nova desde a IA: **uma chamada real antes dos mocks**.
2. **Ingerir os eventos societários que faltam em ITUB4 e MGLU3.** Não é wave, é dado — e é o
   único caminho para uma afirmação de estabilidade que valha alguma coisa.
3. **Verificar o `OllamaProvider`** contra um servidor real, quando houver um.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md) e **começar a Wave 15**.

## Relevant Files

- `backend/app/domain/backtesting/folds.py` — a partição, e a recusa quando ela não cabe
- `backend/app/domain/backtesting/grid.py` — o que pode ser ajustado, e com que valores
- `backend/app/domain/backtesting/objectives.py` — quanto vale um segmento, e qual figura decide
- `backend/app/domain/backtesting/walkforward.py` — o serviço, a seleção e a estabilidade
- `backend/app/domain/backtesting/service.py` — `testable_universe`, agora público
- `backend/app/api/routes/backtests.py` — as duas rotas
- `docs/decisions/ADR-034-*.md`, `ADR-035-*.md`
- `backend/tests/test_walk_forward_{folds,grid,service,routes}.py`
