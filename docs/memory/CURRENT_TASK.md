# Current Task

## Task

**W09-003 — Algoritmo de Alocação de Aporte Mensal** (Wave 09)

> ⚠️ **Renumeração deliberada.** O plano original tinha duas tasks na W09, com a alocação em
> W09-002. A ingestão da CVM foi inserida como W09-002 porque era o que destravava três dos
> cinco sub-scores; a alocação virou W09-003.

## Status

⚪ Not Started

## Objective

Transformar score em decisão: *onde colocar o próximo R$ 1.000?*
(`docs/roadmap.md` §21, AGENTS.md §31/§32/§33).

A pergunta do sistema é **"qual novo aporte melhora minha carteira atual?"** — explicitamente
**não** "qual ativo tem maior score" (§31). O score já é relativo à carteira; a alocação precisa
respeitar restrições.

## O que já está pronto — não reimplemente

- `app/domain/recommendations/scoring.py` — cinco pilares decomponíveis, fórmula versionada,
  ausência de primeira classe. **Combine, não recalcule.**
- `app/domain/recommendations/service.py` — `score_universe(db, portfolio)` já devolve todo o
  universo pontuado contra a carteira, ordenado, com os não-pontuáveis por último.
- `app/quant/{returns,risk}.py` — retorno, volatilidade, drawdown, beta, Sharpe, Sortino.
- `app/domain/benchmarks/` e `app/domain/portfolio/performance.py`.
- `app/integrations/fundamentals/{cvm,identity,composite}.py` — demonstrativos da CVM funcionando.

## ⚠️ Duas coisas que a alocação precisa respeitar

### 1. `coverage` não é decoração — e a alocação é onde isso morde

Dois ativos com coberturas diferentes **não são comparáveis**, mesmo ambos voltando número entre
0 e 100. Um ativo pontuado só em Risco e Diversificação (40%) contra outro pontuado nos cinco
pilares não estão medindo a mesma coisa.

Ordenar o universo por `final_score` e distribuir o aporte de cima para baixo **ignora isso** e
favorece sistematicamente quem tem menos dado. A alocação tem que, no mínimo, exigir cobertura
mínima ou agrupar por cobertura — e dizer qual escolheu.

### 2. "Conservador" é restrição quantitativa, não adjetivo (§32)

Limite por ativo, por setor, de renda variável, de volatilidade; preferência por liquidez;
menor concentração. **Os pesos devem ser configuráveis** — §32 diz explicitamente para não assumir
que todo conservador tem a mesma alocação.

Os tetos já usados pelo pilar de Diversification são 20% por ativo e 40% por setor
(`ASSET_WEIGHT_SCALE` / `SECTOR_WEIGHT_SCALE`). A alocação deve usar **os mesmos números**, não
uma segunda cópia que possa divergir.

## Relevant Files

- `docs/roadmap.md` §21, `AGENTS.md` §31 (recomendação), §32 (perfil conservador), §33 (aporte mensal)
- `backend/app/domain/recommendations/` — scoring, service, schemas
- `backend/app/data/models/recommendations.py` — model `Recommendation`, ainda sem uso
- `backend/app/data/models/users.py` — `InvestorProfile` (`monthly_contribution` ainda em `Float`, ver Known Issues)
- [ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md) — `None` é "não computável", nunca zero

## Definition of Done

- [ ] Alocação determinística (§113): mesma carteira e mesmo universo, mesma resposta
- [ ] Respeita limites por ativo e por setor, reutilizando as constantes do scoring
- [ ] Trata `coverage` explicitamente — nunca compara scores de coberturas diferentes em silêncio
- [ ] Pesos e limites configuráveis (§32)
- [ ] Explica a decisão: qual ativo, quanto, e **por quê** — decomponível como o score
- [ ] Testes com valores conhecidos + carteira vazia + universo sem ativo pontuável
- [ ] `pytest` verde (baseline 542 + novos)
- [ ] `ruff check` e `black --check` limpos nos arquivos alterados
- [ ] `docs/PROJECT_STATUS.md` e a memória atualizados

---

## 🎯 Antes da alocação: um passo curto de alto retorno

**Ações em circulação por período.** É o único item que falta para `pe`, `pb` e `dy`, e
destravaria o pilar de **Valuation** inteiro — o último ainda ausente. Levaria a cobertura do
score de **55% para 75%**.

O dado já está no arquivo que o projeto **já baixa**: `dfp_cia_aberta_composicao_capital_{ano}.csv`
traz `QT_ACAO_TOTAL_CAP_INTEGR` e `QT_ACAO_TOTAL_TESOURO` por `DT_REFER`. Ações em circulação =
integralizadas − tesouraria.

O que falta: coluna `shares_outstanding` em `fundamentals` (migration), o campo no
`FinancialStatement`, o parse no `CvmFundamentalsProvider`, e passar adiante em
`IndicatorInputs` — que **já tem o campo** e cujo `compute_indicators` **já sabe** usá-lo para
`pe`/`pb`. O preço point-in-time já é resolvido por `_price_on_or_before`.

Estimativa: bem menor que a ingestão da CVM, porque toda a infraestrutura já existe.

---

## Estado do ambiente (verificado 2026-08-18)

- **PostgreSQL 16 no ar**, schema em `006`, com dado real: CDI (252 pregões), IPCA (31 meses),
  IBOV (63 pregões), e **PETR4 com 6 exercícios de demonstrativos e indicadores da CVM**.
  `docker compose up -d postgres` se estiver parado.
- Alembic do host precisa da URL sobrescrita (o `.env` aponta para o host `postgres` da rede Docker):
  `DATABASE_URL="postgresql://investment_user:investment_pass_dev@localhost:5432/investment_assistant" .venv/Scripts/python.exe -m alembic upgrade head`
- Rodar Python de `backend/` **não** carrega o `.env` da raiz e `BRAPI_TOKEN` fica vazio em silêncio.
- **Cache da CVM em `var/cvm/`** (gitignored), ~13 MB por exercício. Já tem 2020–2025.
- **`alembic check` falha** por drift pré-existente em `assets.ticker` e `users.email` — não é regressão.
- 🔴 **A Brapi limita o `range` a 3 meses** no plano gratuito, e o `range` é relativo a hoje.
  Não há histórico de preços além de ~63 pregões. Já quebra `sync_daily_history` acima de 3 meses.
  **Não afeta fundamentals** — esses vêm da CVM agora.
