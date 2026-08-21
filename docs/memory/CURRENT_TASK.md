# Current Task

## Task

**W10-001 — Pesos-alvo: de onde vem o `target_weight`.** Primeira das três tasks da
**Wave 10 — Rebalanceamento** (roadmap §22, AGENTS.md §34).

## Status

🟡 **Em andamento.** A wave EVENTS fechou em 2026-08-20 e não há código pela metade em lugar
nenhum.

---

## A wave em três tasks

| task | entrega | por que separada |
|---|---|---|
| **W10-001** | `targets.py` puro: `target_weight` por ativo e o *drift* (`current`/`target`/`gap`) | é a decisão da wave, e é aritmética pura — dá para fixar antes de tocar em banco |
| **W10-002** | `service.py` + `GET /portfolios/{id}/rebalance` — a tabela de desvio | carregamento, o mesmo corte que `benchmarks/service.py` faz contra `comparison.py` |
| **W10-003** | `rebalancing.py` + `GET /portfolios/{id}/rebalance-plan` — o aporte que fecha os gaps | é um plano diferente do da W09: ordena por gap, não por score |

---

## A pergunta que a wave tem que responder primeiro

O roadmap §22 pede `current_weight`, `target_weight`, `weight_gap` — e **não diz de onde sai o
alvo**. Peso atual é ledger; gap é subtração. **O alvo é a wave inteira.**

### Medido contra o banco real (2026-08-21), antes de escrever código

Alvo proporcional ao `final_score` **não converge**, porque o score lê a carteira que o alvo
deveria mirar:

| peso detido de PETR4 | `final_score` | quality | valuation | growth | risk | diversification |
|---|---|---|---|---|---|---|
| 0% | **76,72** | 97,8 | 93,5 | 76,7 | 28,3 | 100,0 |
| 5% | 73,91 | 97,8 | 93,5 | 76,7 | 28,3 | 81,2 |
| 10% | 71,10 | 97,8 | 93,5 | 76,7 | 28,3 | 62,5 |
| 15% | 68,28 | 97,8 | 93,5 | 76,7 | 28,3 | 43,8 |
| 20% | **65,47** | 97,8 | 93,5 | 76,7 | 28,3 | 25,0 |

**Nada mudou no negócio** — os quatro pilares de mérito são constantes. O que caiu foi
Diversificação, que é justamente o pilar que lê o peso atual. Um alvo construído sobre esse
número é uma **trave que anda**: recua conforme a carteira se aproxima, e o `weight_gap`
reportado ao investidor não é a distância até lugar nenhum.

**Decisão**: o alvo sai do **mérito** — Quality, Valuation, Growth e Risk, renormalizados — e
**nunca** de Diversificação. Concentração não some do cálculo: ela vira **teto** (as mesmas
escalas da W09), que é onde ela não se auto-referencia. Vai virar ADR-027.

### A armadilha de cobertura está viva neste universo

ITUB4 marca **92,47 com cobertura 0,40** — o maior score do banco, montado sobre os dois pilares
que nunca faltam (Risco e Diversificação). É exatamente o que o piso de cobertura da W09 existe
para barrar, e o alvo herda o mesmo piso.

### O universo real é pequeno de propósito — e força o caso difícil

Só PETR4 tem fundamentos; ITUB4/BBAS3/MGLU3 estão em cobertura 0,40 e sem setor. Com um único
ativo alvo-elegível e teto de 20% por ativo, os alvos somam **0,20** e sobram **0,80 sem dono**.
Isso não pode ser redistribuído em silêncio — é o análogo do `unallocated` do plano de aporte, e
tem que voltar nomeado.

---

## O que já está pronto — não reimplemente

- `app/domain/recommendations/scoring.py` — pilares, `Scale`, `ASSET_WEIGHT_SCALE` /
  `SECTOR_WEIGHT_SCALE`, `PILLAR_WEIGHTS`, `compose`.
- `app/domain/recommendations/allocation.py` — `AllocationPolicy`, `Exclusion`, `Limit`, os tetos
  lidos das escalas do score, `_floor_to_centavo`.
- `app/domain/recommendations/service.py` — `build_exposure`, `score_universe`,
  `plan_contribution`, `monthly_contribution_for`.
- `app/api/routes/portfolios.py` — `GET /{id}/scores` e `GET /{id}/contribution-plan`, com o
  helper de posse e os overrides de política por query.

## Estado do ambiente (verificado 2026-08-21)

- ✅ Docker no ar, schema **`012_corporate_actions`** (head), sem drift.
- ✅ `pytest -q` → **750 passed** na entrada da wave.
- Banco real: uma carteira (`Local`, id 1) **sem transação nenhuma**; quatro ativos, dos quais só
  PETR4 tem setor (`Energia`) e fundamentos (6 exercícios, 2020–2025).
- Alembic do host precisa da URL sobrescrita:
  `DATABASE_URL="postgresql://investment_user:investment_pass_dev@localhost:5432/investment_assistant" .venv/Scripts/python.exe -m alembic upgrade head`
