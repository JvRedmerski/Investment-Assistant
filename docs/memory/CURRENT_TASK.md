# Current Task

## Task

**Wave 11 — Dashboard.** A primeira wave do projeto com **trabalho de frontend real** — o
frontend hoje é só scaffold. Ver [../planning/ROADMAP.md](../planning/ROADMAP.md) e roadmap §23.

## Status

⚪ **Não começou.** A Wave 10 fechou em 2026-08-21 com as três tasks entregues, e não há código
pela metade em lugar nenhum.

---

## O que a Wave 10 entregou

| task | entrega | ADR |
|---|---|---|
| **W10-001** | `targets.py` — peso-alvo derivado do **mérito** e o *drift* (`current`/`target`/`gap`) | [ADR-027](../decisions/ADR-027-target-weight-comes-from-merit.md) |
| **W10-002** | `GET /portfolios/{id}/rebalance` — a tabela de desvio | — |
| **W10-003** | `rebalancing.py` + `GET /portfolios/{id}/rebalance-plan` — o aporte que fecha os gaps | [ADR-028](../decisions/ADR-028-rebalancing-is-cash-flow-only.md) |

### As duas coisas que a wave descobriu, e que valem mais que o código

**1. O alvo não pode sair do `final_score`.** Medido antes de escrever código: variando só quanto
a carteira detém de PETR4, de 0% a 20%, o score escorrega de **76,72 para 65,47** enquanto os
quatro pilares de mérito ficam constantes. O que cai é Diversificação, o pilar que lê o detentor.
Um alvo construído sobre isso é uma trave que anda. O alvo passou a sair do **mérito** (Quality,
Valuation, Growth, Risk) e a concentração virou **teto** em vez de termo.

**2. O plano tem que raciocinar sobre a carteira que o aporte cria, não sobre a de hoje.** Isso
o **teste contra o banco real** pegou, e teste unitário nenhum pegaria — os unitários tinham sido
escritos sob a mesma premissa errada. PETR4 a 25% contra alvo de 20% era recusada por estar
*acima*; com os R$ 1.000 parados em caixa a base virava R$ 2.200 e ela caía para **13,6%**, mais
abaixo do alvo do que estava acima. Corrigido: R$ 0 → **R$ 140** alocados, distância 0,0636 → 0.

---

## O que já está pronto — não reimplemente

Todo o backend das waves 00–10. Em particular, para a W11:

- `GET /portfolios/{id}/positions` — posições consolidadas. ⚠️ **sem valor de mercado**: o
  `PortfolioPositionsResponse` é custo médio, derivado do ledger.
- `GET /portfolios/{id}/benchmarks/{code}` — carteira × CDI/IBOV/IPCA/Selic, com a carteira como
  índice **time-weighted**.
- `GET /portfolios/{id}/scores` — os cinco pilares por ativo, decomponíveis. **Ler `coverage`.**
- `GET /portfolios/{id}/contribution-plan` — onde vai o próximo aporte (ordena por score).
- `GET /portfolios/{id}/rebalance` e `/rebalance-plan` — desvio e o aporte que o fecha (ordena
  por gap). ⚠️ Os dois **podem discordar** sobre o mesmo ativo, de propósito (ADR-028 §2).
- `GET /assets/{ticker}/...` — cotações, histórico, fundamentos, indicadores, eventos societários.

Contrato completo dos endpoints: [../architecture/API.md](../architecture/API.md).

## O que a W11 vai esbarrar, e é bom saber antes

- **Não existe valor de mercado em lugar nenhum.** Tudo hoje é custo basis. Um dashboard de
  patrimônio precisa de `quantity × preço mais recente`, e essa multiplicação não existe no
  backend — decidir onde ela mora é trabalho da wave, e o `service.py` de recommendations
  registra por que a escolha do custo foi deliberada lá.
- **`portfolio_snapshots.total_value`/`cash_value` ainda são `Float`** e sem consumidor. Se a W11
  passar a usá-los, converter para `NUMERIC` primeiro ([ADR-003](../decisions/ADR-003-decimal-money.md)).
- **A cobertura de alvo do banco real é de um papel só.** Só PETR4 tem fundamentos; ITUB4/BBAS3/
  MGLU3 não têm setor nem demonstrativos, então a tela vai mostrar `unassigned` de 0,80. Isso é o
  desenho, não um bug de tela — aumentar a cobertura é cadastrar setor e sincronizar CVM.
- **O frontend é scaffold**: React 18 + TS + Vite 5 + Tailwind. `react-router-dom`,
  `@tanstack/react-query`, `recharts`, `zod`, `clsx` e `tailwind-merge` estão declarados no
  `package.json` e **ainda não são importados por nenhum código** — a W11 é onde entram.

---

## Estado do ambiente (verificado 2026-08-21)

- ✅ `pytest -q` → **815 passed** (era 750 na entrada da wave). `ruff check` e `black --check`
  limpos no repositório inteiro.
- ✅ Docker no ar, schema **`012_corporate_actions`** (head). **A Wave 10 não criou migration** —
  nada dela é gravado (regra 16).
- Banco real: uma carteira (`Local`, id 1) **sem transação nenhuma**; quatro ativos, dos quais só
  PETR4 tem setor (`Energia`) e fundamentos (6 exercícios, 2020–2025). Preço ajustado: PETR4
  1.495/1.495, BBAS3 1.495, ITUB4 198, MGLU3 478.
- Alembic do host precisa da URL sobrescrita:
  `DATABASE_URL="postgresql://investment_user:investment_pass_dev@localhost:5432/investment_assistant" .venv/Scripts/python.exe -m alembic upgrade head`
- 🔴 O teto de `3mo` da Brapi continua limitando o **IBOV**, o que mantém `beta` com janela pobre.
