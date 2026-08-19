# Current Task

## Task

**Nenhuma em andamento.** A **Wave 09 fechou** em 2026-08-19, com quatro tasks:
sub-scores, fonte CVM, ações em circulação e alocação do aporte.

## Status

⚪ Aguardando escolha da próxima wave.

---

## A decisão a tomar antes de começar

Duas opções, e a segunda está fora da ordem do roadmap de propósito.

### Opção 1 — Wave 10, Rebalanceamento (a ordem do roadmap)

`docs/roadmap.md` §22, AGENTS.md §34. Calcular `current_weight`, `target_weight`,
`weight_gap` e priorizar ativos abaixo do alvo, com score adequado, sem violar restrição.

Boa parte da infraestrutura existe: `PortfolioExposure` já dá peso por ativo e por setor,
`allocation.py` já tem tetos e política configurável, e o motor de score já é relativo à
carteira. O que falta de verdade é a definição de **peso-alvo**, que hoje não existe em
lugar nenhum — e é exatamente a pergunta que a wave tem que responder.

### Opção 2 — Histórico de preços de fonte aberta (COTAHIST da B3)

Fora da ordem, mas é o que **hoje trava mais coisa ao mesmo tempo**:

| trava hoje | por quê |
|---|---|
| `pe` / `pb` no banco real | `_price_on_or_before` exige preço na data de referência ou antes; não há nenhum |
| pilar de **Risk** | sem série, `volatility`, `max_drawdown`, `beta` e `sharpe` são todos `None` |
| cobertura do score | com Risk ausente, o teto prático é 0,75, e o piso da alocação é 0,50 |
| `beta` estatisticamente útil | ~63 pregões é uma janela pobre |
| **Wave 13 inteira** (backtesting) | precisa de anos |

É o mesmo movimento que a W09-002 fez com os demonstrativos: trocar um fornecedor com cota
por um arquivo público do próprio mercado. A B3 publica o COTAHIST por ano, em layout de
posição fixa — parecido em espírito com os ZIPs da CVM, e a infraestrutura de cache em disco
(`CvmArchive`) é um molde pronto.

**Recomendação**: a opção 2. Sem preço histórico, o rebalanceamento da W10 nasceria sobre a
mesma carteira sem valor de mercado e sobre scores com o pilar de Risco ausente.

---

## O que já está pronto — não reimplemente

- `app/domain/recommendations/scoring.py` — cinco pilares decomponíveis, ausência de
  primeira classe, fórmula versionada.
- `app/domain/recommendations/allocation.py` — política configurável, faixas de cobertura,
  tetos lidos das escalas do score, motivo nomeado para toda exclusão. **Puro.**
- `app/domain/recommendations/service.py` — `score_universe`, `plan_contribution`,
  `build_exposure` (peso **e** valor por ativo e por setor).
- `app/quant/{returns,risk}.py`, `app/domain/benchmarks/`, `app/domain/portfolio/performance.py`.
- `app/integrations/fundamentals/{cvm,identity,composite}.py` — demonstrativos da CVM,
  incluindo contagem de ações por exercício com a unidade reconciliada.

## Endpoints da Wave 09

- `GET /portfolios/{id}/scores`
- `GET /portfolios/{id}/contribution-plan` — aceita override de todo limite por query param.

---

## Estado do ambiente (verificado 2026-08-19)

- **PostgreSQL 16 no ar**, schema em `007`, com dado real: CDI (252 pregões), IPCA (31 meses),
  IBOV (63 pregões), e **PETR4 com 6 exercícios de demonstrativos da CVM, agora com
  `shares_outstanding`**. `docker compose up -d postgres` se estiver parado.
- **`asset_prices` está vazia** — é por isso que o pilar de Risk e os múltiplos `pe`/`pb`
  aparecem ausentes numa consulta ao banco real. Não é defeito do código.
- Alembic do host precisa da URL sobrescrita (o `.env` aponta para o host `postgres` da rede Docker):
  `DATABASE_URL="postgresql://investment_user:investment_pass_dev@localhost:5432/investment_assistant" .venv/Scripts/python.exe -m alembic upgrade head`
- ⚠️ **`alembic_version.version_num` é `varchar(32)`** — um `revision` mais longo que isso
  falha **depois** de aplicar o schema. Por isso a `007` chama-se `007_shares_outstanding`.
- Rodar Python de `backend/` **não** carrega o `.env` da raiz e `BRAPI_TOKEN` fica vazio em silêncio.
- **Cache da CVM em `backend/var/cvm/`** (gitignored), ~13 MB por exercício. Já tem 2020–2026.
- **`alembic check` falha** por drift pré-existente em `assets.ticker` e `users.email` — não é regressão.
- 🔴 **A Brapi limita o `range` a 3 meses** no plano gratuito, e o `range` é relativo a hoje.
  Não há histórico de preços além de ~63 pregões. Já quebra `sync_daily_history` acima de 3 meses.
