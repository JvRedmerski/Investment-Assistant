# Current Task

## Task

**W09-001 — Portfolio Recommendation Engine** (Wave 09)

## Status

⚪ Not Started — **começa com uma decisão de produto, não com código**

## Objective

Pipeline determinístico de scores que responda *onde colocar o próximo R$ 1.000*
(`docs/roadmap.md` §21, AGENTS.md §30):

```
Dados → Quality → Valuation → Growth → Risk → Diversification → Portfolio Fit → Final Score → Allocation
```

O score deve ser **decomponível** (§30) e o resultado **determinístico** (§113).

## ⚠️ Leia isto antes de escrever qualquer código

### A wave está parcialmente bloqueada, e a decisão é de produto

O pipeline acima tem seis sub-scores. **Três dependem de demonstrativos financeiros**
(Quality, Valuation, Growth) — e a ingestão de fundamentals está **inoperante desde
2026-08-18**, não por bug, mas porque os módulos saíram do plano gratuito da Brapi
(HTTP 403). O parser continua correto e testado; ele não tem mais o que receber.

Some-se a isso que **5 dos 10 indicadores já retornavam `None`** por limitação
evidenciada da fonte (`pe`/`pb`/`dy` são snapshots atuais sem data-fim de período,
usá-los sobre um balanço antigo seria look-ahead; `cleanEbitda` é cópia literal de
`ebit`, não é EBITDA).

Os outros três sub-scores (**Risk, Diversification, Portfolio Fit**) **estão
desbloqueados**: a W07 entregou volatilidade/drawdown/beta/Sharpe/Sortino e a W08
entregou as séries de referência que faltavam.

**Escolha uma das três antes de começar** — e registre em ADR:

1. **Assinar o plano Startup da Brapi** (R$ 119,99/mês) — destrava tudo, custa dinheiro recorrente.
2. **Migrar para dados abertos da CVM** — sem custo e é a fonte primária, mas é uma
   integração nova inteira (formato DFP/ITR, CSV zipado, sem API REST). Provavelmente
   uma wave própria.
3. **Entregar a W09 com o que há** — Risk + Diversification + Portfolio Fit, com os
   sub-scores fundamentalistas explicitamente ausentes em vez de estimados.
   **Nunca preencher com valor default** (regra 44 / ADR-014): um Quality Score
   inventado contamina o Final Score e some dentro dele.

A opção 3 é a única que não depende de decisão externa e não viola a regra de uma
wave por vez. É a recomendação, se a decisão travar.

### O que já está pronto e não deve ser reimplementado

- `app/quant/returns.py` e `app/quant/risk.py` — retorno, volatilidade, drawdown, beta, Sharpe, Sortino. **Puros e testados.**
- `app/domain/benchmarks/` — catálogo, ingestão, série (taxa → índice), comparação.
- `app/domain/portfolio/performance.py` — índice time-weighted da carteira, já em formato `PricePoint`.
- `app/domain/portfolio/service.py` — posições consolidadas derivadas do ledger.
- `app/domain/fundamentals/indicators.py` — as 10 fórmulas, das quais 5 produzem valor.

O Score não calcula nada disso de novo. Ele **combina** o que já existe.

## Relevant Files

- `docs/roadmap.md` §21 (Wave 9), `AGENTS.md` §30 (score decomponível), §44 (não inventar dado)
- [ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md) — `None` significa "não computável", nunca zero. É a regra que decide o que fazer com um sub-score sem dado.
- [ADR-018](../decisions/ADR-018-benchmark-representation.md) — representação de benchmark, base 252, período incompleto
- `backend/app/domain/benchmarks/comparison.py` — molde de "módulo puro que só orquestra o `app.quant`"

## Definition of Done

- [ ] Decisão sobre fundamentals registrada em ADR
- [ ] Sub-scores implementados como funções puras e testáveis isoladamente
- [ ] Score final **decomponível** — o consumidor vê a contribuição de cada parte
- [ ] Sub-score sem dado é **ausente**, nunca estimado (ADR-014)
- [ ] Determinístico: mesma entrada, mesma saída (§113)
- [ ] Testes com valores conhecidos + casos de dado faltante
- [ ] `pytest` verde (baseline 449 + novos)
- [ ] `ruff check` e `black --check` limpos nos arquivos alterados
- [ ] `docs/PROJECT_STATUS.md` e a memória atualizados

---

## Estado do ambiente (verificado 2026-08-18)

- **PostgreSQL 16 no ar**, schema em `005`, e agora **com dado real**: CDI (252 pregões,
  2025-08-18 a 2026-08-17), IPCA (31 meses desde 2024-01) e IBOV (63 pregões desde
  2026-05-20). `docker compose up -d postgres` se estiver parado.
- Alembic a partir do host precisa da URL sobrescrita (o `.env` aponta para o host `postgres` da rede Docker):
  `DATABASE_URL="postgresql://investment_user:investment_pass_dev@localhost:5432/investment_assistant" .venv/Scripts/python.exe -m alembic upgrade head`
- Rodar Python de `backend/` **não** carrega o `.env` da raiz e `BRAPI_TOKEN` fica vazio em silêncio.
- **`alembic check` falha** por drift pré-existente em `assets.ticker` e `users.email` — não é regressão.
- 🔴 **A Brapi limita o `range` a 3 meses no plano gratuito**, e o `range` é relativo a hoje.
  Não há histórico de ações/IBOV além de ~63 pregões hoje. Isso já quebra
  `sync_daily_history` para janelas acima de 3 meses e vai limitar a W13.
