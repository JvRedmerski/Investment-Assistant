# Session Handoff

## Last Updated

2026-08-21

## Last Completed Work

### Wave 10 — Rebalanceamento, 3/3 (`461eca7`, `fd2b56e`, mais o commit da W10-003)

De volta à ordem do roadmap depois de duas waves inseridas fora dela. A wave inteira era uma
pergunta que nem o roadmap §22 nem a regra 34 respondem: **de onde vem o `target_weight`**. Peso
atual é ledger, gap é subtração; o alvo era tudo.

### W10-001 — o alvo sai do mérito ([ADR-027](../decisions/ADR-027-target-weight-comes-from-merit.md))

**A resposta óbvia foi medida e reprovada antes de qualquer código.** Alvo proporcional ao
`final_score` não converge, porque o score lê a carteira que o alvo deveria mirar:

| peso detido de PETR4 | `final_score` | quality | valuation | growth | risk | diversification |
|---|---|---|---|---|---|---|
| 0% | **76,72** | 97,8 | 93,5 | 76,7 | 28,3 | 100,0 |
| 20% | **65,47** | 97,8 | 93,5 | 76,7 | 28,3 | 25,0 |

Nada mudou na empresa — os quatro pilares de mérito são constantes. Um alvo feito desse número
**recua conforme a carteira se aproxima**, e o gap reportado não é distância até coisa alguma.

O alvo passou a sair do **mérito** (`scoring.merit`: Quality, Valuation, Growth, Risk
renormalizados) e a concentração virou **teto** em vez de termo — os mesmos `max_asset_weight` e
`max_sector_weight` da W09, lidos da mesma `AllocationPolicy`.

**Um erro de ordem apareceu traçando o algoritmo à mão, não nos testes**: com o teto por ativo
checado antes do setorial, três papéis de um setor congelam a 20% cada e põem o setor em **60%**,
contra um limite de 40% nunca consultado.

Medido no banco real: PETR4 com mérito **72,61** (contra `final_score` 76,72, inflado pela
Diversificação de carteira vazia), alvo **0,20** aparado pelo teto, **0,80 `unassigned`**. ITUB4,
que marca **92,47 com cobertura 0,40** — o maior número do universo, feito só dos dois pilares
que nunca faltam —, **não recebe alvo**: sob a regra do mérito ela tem um pilar só.

### W10-002 — a tabela de desvio sobre a API

`portfolio_targets` + `GET /portfolios/{id}/rebalance`. A construção de candidatos virou
`_candidates`, compartilhada com `plan_contribution`.

**Um fato que só o teste ponta a ponta mostra**: sem demonstrativos *nenhum* ativo recebe alvo, e
**baixar `min_coverage` não resolve** — o que falta não é o piso, é um segundo pilar de mérito.

### W10-003 — o aporte que fecha os gaps ([ADR-028](../decisions/ADR-028-rebalancing-is-cash-flow-only.md))

`rebalancing.py` + `plan_rebalance` + `GET /portfolios/{id}/rebalance-plan`. Ordena por **gap**
(o plano de aporte ordena por score) e cada alocação para em `target * base - held`.

**Nada vende.** Todos os itens que a regra 34 manda priorizar são de compra; venda realiza IR
numa carteira cuja tese é capitalizar e paga corretagem nas duas pontas para mover dinheiro que o
aporte seguinte move de graça. Ativo acima do alvo volta em `skipped` com `ABOVE_TARGET`.

🔴 **O teste contra o banco real pegou uma falha de desenho que teste unitário nenhum pegaria** —
porque os unitários tinham sido escritos sob a mesma premissa errada. O portão de elegibilidade
lia o peso **antes** do aporte, enquanto o dimensionamento inteiro já rodava sobre
`invested + contribution`:

| | primeira versão | corrigida |
|---|---|---|
| PETR4 alocada | R$ 0 (`ABOVE_TARGET`) | **R$ 140** (`TARGET_WEIGHT`) |
| distância a percorrer | 0 → **0,0636** | 0 → **0** |

PETR4 a 25% contra alvo de 20% era recusada por estar *acima*; com os R$ 1.000 parados em caixa a
base virava R$ 2.200 e ela caía para **13,6%** — mais abaixo do alvo do que estava acima, **por
ter sido recusada por estar acima dele**.

## Current State

- `pytest` → **815 passed** (750 → 815), verificado em 2026-08-21. `ruff check` e `black --check`
  limpos no repositório inteiro.
- ✅ Commitado; árvore limpa.
- 🔴 **Docker ligado** nesta sessão. Schema **`012_corporate_actions`**, e a Wave 10 **não criou
  migration** — nada dela é gravado (regra 16, ADR-002).
- **Wave 10 🟢 concluída**, 3/3. Nada iniciado da W11.

## Important Details

### O engano fácil de cometer aqui

**A tabela de desvio e o plano podem discordar sobre o mesmo ativo, e os dois estão certos.**
`/rebalance` mede a carteira de hoje; `/rebalance-plan` mede a carteira que o aporte cria. Um
papel exatamente no alvo hoje **é comprado mesmo assim**, porque o aporte vai diluí-lo. As duas
leituras vêm em cada linha do plano (`weight_gap` e `needed`), e o teste
`test_a_position_on_target_today_is_still_bought_when_the_money_dilutes_it` fixa isso.

O outro: **`merit_score` não é `final_score`**, e a diferença é o ponto da wave inteira.

### Lições de método desta wave

- **Medir a hipótese óbvia antes de codificá-la.** A tabela do `final_score` custou dez minutos e
  matou o desenho inteiro que teria sido escrito por padrão.
- **Traçar o algoritmo à mão pega o que o teste não pega**, porque o teste é escrito pela mesma
  cabeça que escreveu o código. O erro de ordem dos tetos veio daí.
- **Rodar contra o banco real e olhar os números** — o passo que o `IMPLEMENTATION_GUIDE` cobra
  para provedor externo — vale igual para lógica pura. A falha de base do portão passou por 18
  testes unitários verdes porque eles compartilhavam a premissa errada.
- **Quando os testes falham depois de uma correção, conferir de que lado está o erro.** Três
  falharam aqui e os três eram cenários escritos sob a premissa antiga, não regressões.

## Pending Work

**Wave 11 — Dashboard**, a primeira wave com trabalho de frontend real. Ver
[CURRENT_TASK.md](CURRENT_TASK.md), que lista o que a W11 vai esbarrar — a começar por **não
existir valor de mercado em lugar nenhum**: tudo hoje é custo basis.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md) e [../planning/ROADMAP.md](../planning/ROADMAP.md) para a
W11, e [../architecture/FRONTEND.md](../architecture/FRONTEND.md) antes de tocar em React.

## Relevant Files

- `backend/app/domain/recommendations/targets.py` — o modelo de alvo e a regra de *water-filling*
- `backend/app/domain/recommendations/rebalancing.py` — o plano, e a base pós-aporte
- `backend/app/domain/recommendations/scoring.py` — `merit` / `Merit` / `MERIT_PILLARS`
- `backend/app/domain/recommendations/allocation.py` — a política compartilhada e os helpers
  públicos (`floor_to_centavo`, `percent`, `round_score`)
- `backend/app/domain/recommendations/service.py` — `portfolio_targets`, `plan_rebalance`
- `backend/tests/test_target_weights.py`, `test_rebalance_plan.py`, `test_rebalance_routes.py`
- `docs/decisions/ADR-027-target-weight-comes-from-merit.md`,
  `docs/decisions/ADR-028-rebalancing-is-cash-flow-only.md`
