# Current Task

## Task

**W07-001 / W07-002 — Quant Engine: Returns & Risk** (Wave 07)

## Status

⚪ Not Started

## Objective

Criar `app/quant/`, o módulo que o AGENTS.md §24 define como o lugar de **todo** cálculo financeiro do projeto:

- **`returns.py`** — retorno diário, semanal, mensal, trimestral, YTD, anual e CAGR.
- **`risk.py`** — volatilidade, beta, maximum drawdown, Sharpe, Sortino.

Sobre as séries de `asset_prices`, já ingeridas e disponíveis.

## Context

Este é o coração quantitativo do produto. Tudo que vem depois se apoia nele: benchmarks (W08), scores de recomendação (W09), backtesting (W13). Uma fórmula errada aqui contamina todas as waves seguintes de forma invisível.

A Wave 06 fechou com 5 dos 10 indicadores fundamentalistas produzindo valor; os outros 5 têm limitação evidenciada e documentada. A W07 **não depende deles**.

## Relevant Areas

- Backend — novo pacote `app/quant/`
- Backend — Domain (persistência/exposição, se a task chegar até lá)

## Relevant Files

**Moldes de cálculo puro a seguir:**
- `backend/app/domain/fundamentals/indicators.py` — o mais recente: função pura, `Decimal`, política de dado faltante, cada fórmula documentada na docstring
- `backend/app/domain/portfolio/service.py` — replay determinístico ordenado

**Fonte de dados:**
- `backend/app/data/models/assets.py` — `AssetPrice` (`date`, OHLC `Decimal`, `adjusted_close`, `volume`)

**Testes-molde:**
- `backend/tests/test_fundamental_indicators.py` — valores conhecidos + edge cases

**Leitura obrigatória antes de começar:**
- `docs/roadmap.md` §19 (Wave 7)
- `AGENTS.md` §24 (quant engine), §25 (retornos), §26 (retorno de carteira ≠ variação patrimonial), §27 (risco), §128 (DoD quant)
- [ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md) — política de dado faltante, vale aqui também

## Requirements

1. Funções **puras**, sem I/O, em `app/quant/`. Persistência separada.
2. Cada métrica com **fórmula, periodicidade e metodologia documentadas** (§128) — incluindo a convenção de anualização escolhida (252 pregões vs. 365 dias) e o porquê.
3. **Usar `adjusted_close`, não `close`**, para retornos: proventos e desdobramentos distorcem a série de preço bruto.
4. Distinguir claramente retorno do **ativo**, retorno da **carteira** e **variação patrimonial** (§26). Com aportes intermediários, `(atual − inicial)/inicial` **não** é rentabilidade — usar TWR ou MWR/IRR quando aplicável.
5. Dado faltante, série curta demais e divisão por zero → `None`, nunca zero nem exceção ([ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md)).
6. Sem look-ahead: toda janela usa apenas dados até a data de referência (§108).
7. Beta e Sharpe exigem referência externa (índice, taxa livre de risco) que **ainda não existe** no sistema — a série de CDI/IBOV é da Wave 08. Projetar a assinatura recebendo a série de referência como parâmetro e deixá-la `None` até a W08, em vez de antecipar a wave.
8. Testes com **casos conhecidos**: entrada conhecida → resultado esperado conhecido, calculado à mão (§68). Não apenas "não quebra".

## Constraints

- **Não** implementar benchmarks (W08), scoring (W09) nem backtesting (W13).
- **Nenhuma chamada externa.** Esta wave só consome o que está no banco — zero requisições à Brapi.
- **Decidir e documentar** onde `float` passa a ser aceitável na fronteira com numpy/pandas. Preços são `Decimal`; estatística em `Decimal` é inviável. A regra 17 permite float para cálculo estatístico **desde que a decisão seja registrada** — provavelmente merece um ADR.
- Não adicionar dependências: numpy, pandas, scipy já estão no `pyproject.toml` (nunca importados até agora).

## Definition of Done

- [ ] `app/quant/returns.py` e `app/quant/risk.py`, funções puras e determinísticas
- [ ] Cada fórmula documentada com periodicidade e tratamento de dado faltante
- [ ] Convenção de anualização escolhida e justificada
- [ ] Fronteira `Decimal` → `float` decidida e registrada
- [ ] Testes com valores conhecidos calculados à mão + edge cases (série vazia, um ponto, gaps)
- [ ] `pytest` verde (baseline 205 + novos), sem regressão
- [ ] `ruff check` e `black --check` limpos nos arquivos alterados
- [ ] `docs/PROJECT_STATUS.md` e a memória atualizados
- [ ] Commit: `feat: add quant engine returns module (W07-001)`

---

## Pendência operacional herdada da Wave 06

Indicadores gravados **antes** da W06-003 estão errados (`roe`/`roic` nulos por causa do bug de `equity`). Para cada ativo já processado:

```
POST /api/v1/assets/{ticker}/indicators/compute?recompute=true
```

Não custa requisição externa.
