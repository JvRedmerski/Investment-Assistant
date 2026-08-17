# Current Task

## Task

**W06-002 — Cálculo e Normalização de Indicadores Fundamentalistas** (Wave 06 — Fundamental Data)

## Status

⚪ Not Started

## Objective

Derivar indicadores fundamentalistas a partir dos demonstrativos já ingeridos (`fundamentals`) e dos preços já armazenados (`asset_prices`), e persisti-los em `financial_indicators` por `reference_date`.

Indicadores previstos pela tabela: `pe` (P/L), `pb` (P/VP), `roe`, `roic`, `dy`, `debt_ebitda`, `net_margin`, `ebitda_margin`, `revenue_growth`, `profit_growth`.

## Context

W06-001 entregou a ingestão de demonstrativos anuais. Esses números crus não são utilizáveis por um motor de decisão: a Wave 09 (Recommendation Engine) consome **scores** de Quality/Valuation/Growth, que se apoiam nestes indicadores normalizados.

Esta é a primeira task do projeto que produz números derivados a partir de dados de duas fontes (demonstrativo + preço). Ela estabelece o precedente de como cálculo financeiro determinístico é escrito aqui, então vale seguir de perto `app/domain/portfolio/service.py` (função pura, `Decimal`, testada com valores conhecidos).

## Relevant Areas

- Backend — Domain (novo módulo de cálculo)
- Database (escrita em `financial_indicators`)
- Backend — API (endpoint de leitura)

## Relevant Files

**Insumos já existentes:**
- `backend/app/data/models/fundamentals.py` — `Fundamental` (fonte) e `FinancialIndicator` (destino)
- `backend/app/data/models/assets.py` — `AssetPrice`, para os indicadores que dependem de preço (P/L, P/VP, DY)
- `backend/app/domain/fundamentals/service.py` — padrão de idempotência a replicar

**Padrão de cálculo a seguir:**
- `backend/app/domain/portfolio/service.py` — função pura, sem I/O, `Decimal`, determinística
- `backend/tests/test_portfolio_service.py` — teste com valores conhecidos

**A criar/modificar:**
- `backend/app/domain/fundamentals/indicators.py` (cálculo puro) e extensão de `service.py` (persistência)
- `backend/app/api/routes/assets.py` (leitura de indicadores)
- `backend/tests/test_fundamental_indicators.py`

**Decisões que restringem esta task:**
- [ADR-013](../decisions/ADR-013-fundamentals-point-in-time.md) — **leia antes de começar**
- [ADR-003](../decisions/ADR-003-decimal-money.md) — `financial_indicators` é `Float` de propósito

## Requirements

1. Cálculo em função **pura**, sem I/O, determinística, separada da persistência.
2. Cada indicador com fórmula documentada (AGENTS.md §128) — definição, periodicidade e tratamento de dado faltante.
3. **Dado ausente propaga como `None`, nunca como zero.** `ebitda` e `free_cash_flow` chegam sempre `NULL` do provedor atual (ADR-013), portanto `debt_ebitda` e `ebitda_margin` serão `None` na prática — isso é correto e deve ser testado como tal.
4. Divisão por zero ou por `None` produz `None`, nunca exceção e nunca infinito.
5. Indicadores que dependem de preço (P/L, P/VP, DY) devem usar o preço **na data de referência ou anterior mais próxima** — nunca um preço posterior (AGENTS.md §108: sem look-ahead).
6. Persistência idempotente por `(asset_id, reference_date)`, sem sobrescrever o já gravado (mesma política do ADR-013).
7. Endpoint de leitura autenticado, lendo só do banco.
8. Crescimento (`revenue_growth`, `profit_growth`) exige o período anterior; se não houver, `None`.

## Constraints

- **Não** implementar scoring nem recomendação — isso é Wave 09.
- **Não** buscar dados novos no provedor externo; esta task só transforma o que já está armazenado.
- **Não** alterar o schema: `financial_indicators` já existe e permanece `Float`.
- **Não** inventar um indicador quando faltar insumo (AGENTS.md §44).
- Um indicador isolado nunca define recomendação (AGENTS.md §29) — este módulo só calcula, não julga.

## Definition of Done

- [ ] Função pura de cálculo, com cada fórmula documentada
- [ ] Dado faltante e divisão por zero tratados, retornando `None`
- [ ] Preço selecionado sem look-ahead
- [ ] Persistência idempotente
- [ ] Endpoint de leitura autenticado
- [ ] Testes unitários com valores conhecidos, incluindo edge cases (`None`, zero, período anterior ausente)
- [ ] Testes de integração HTTP
- [ ] `pytest` verde (baseline 140 + novos), sem regressão
- [ ] `ruff check` e `black --check` limpos nos arquivos alterados
- [ ] `docs/PROJECT_STATUS.md` e a memória atualizados
- [ ] Commit: `feat: add fundamental indicator calculation (W06-002)`
