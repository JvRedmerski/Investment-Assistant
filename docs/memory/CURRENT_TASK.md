# Current Task

## Task

**Decisão pendente do usuário** entre duas frentes. As duas tasks planejadas da Wave 06 estão concluídas.

| Opção | Task | Bloqueio |
|---|---|---|
| **A** | **W06-003** — captar `shares_outstanding`, `ebit` e proventos, destravando `pe`, `pb`, `dy`, `roic` | Precisa de acesso de rede para confirmar o mapeamento de campos da Brapi |
| **B** | **Wave 07 — Quant Engine** (`returns.py`, `risk.py`) | Nenhum — consome `asset_prices`, já disponível |

**Recomendação: B.** A Wave 07 não depende dos indicadores faltantes e é a próxima na ordem obrigatória do roadmap. Quem depende de verdade dos 6 indicadores inertes é a Wave 09 (Recommendation Engine) — há duas waves de folga para resolver a W06-003 quando houver como validá-la.

## Status

⚪ Not Started (aguardando escolha)

---

## Opção A — W06-003: Captação dos insumos faltantes

### Objective

Ingerir os três insumos que hoje impedem 4 dos 10 indicadores de produzir valor, e mapear `ebitda` se for possível obtê-lo por período.

| Insumo | Destrava | Origem provável |
|---|---|---|
| `shares_outstanding` | `pe`, `pb` | módulo `defaultKeyStatistics` |
| `ebit` (+ alíquota efetiva) | `roic` | já vem em `incomeStatementHistory` — apenas não mapeado |
| proventos por ação | `dy` | módulo à parte, forma desconhecida |

### Context

W06-002 implementou e testou as 10 fórmulas; elas retornam `None` só por falta de insumo. Assim que os campos chegarem, os indicadores passam a produzir valor sem alteração no módulo de cálculo — há teste provando isso para cada um.

### Custo em requisições à Brapi

**Zero adicional.** Módulos extras entram no mesmo `GET /quote` que a sync de fundamentals já faz; só o payload cresce. O plano gratuito tem cota mensal limitada, então isso importa.

### Requirements

1. Estender `BrapiFundamentalsProvider` com os módulos novos, mantendo o parsing defensivo.
2. Migration `004` para as colunas novas em `fundamentals` (`NUMERIC(24,4)` para valores monetários; `shares_outstanding` também é `NUMERIC`, não é moeda mas exige precisão inteira grande).
3. Popular `IndicatorInputs.shares_outstanding` / `.ebit` / `.dividends_per_share` em `_inputs_from`.
4. **Decidir e documentar a origem da alíquota efetiva** para o ROIC — ADR-014 proíbe presumir 34% (ver `_nopat`).
5. Recomputar indicadores exige apagar as linhas antigas ou uma política de recomputação — hoje `compute_and_store_indicators` pula período já gravado (ADR-013). **Decidir isso explicitamente**, não contornar.

### Constraints

- Não confirmar o mapeamento contra resposta real = repetir o débito do W05-001/W06-001. Se não houver rede, **considere fazer a opção B antes**.
- Não presumir alíquota, não derivar EBITDA com convenção de sinal não verificada (ADR-013).

---

## Opção B — Wave 07: Quant Engine (Returns & Risk)

### Objective

`app/quant/returns.py` e `app/quant/risk.py`: os cálculos financeiros centrais do produto, sobre as séries de `asset_prices` já armazenadas.

- **returns.py** — retorno diário, semanal, mensal, trimestral, YTD, anual, CAGR.
- **risk.py** — volatilidade, beta, maximum drawdown, Sharpe, Sortino.

### Context

Primeiro módulo em `app/quant/`, que o AGENTS.md §24 define como o lugar de **todo** cálculo financeiro. Estabelece o padrão para benchmark (W08), recomendação (W09) e backtesting (W13).

`app/quant/` ainda não existe. `compute_indicators` (W06-002) e `compute_positions` (W04) são os moldes de função pura a seguir.

### Relevant Files

- `backend/app/domain/fundamentals/indicators.py` — molde mais recente de cálculo puro com política de dado faltante
- `backend/app/domain/portfolio/service.py` — molde de replay determinístico em `Decimal`
- `backend/app/data/models/assets.py` — `AssetPrice`, a fonte das séries
- `docs/roadmap.md` §19 — especificação da Wave 7
- `AGENTS.md` §24–§27 (quant, retornos, retorno de carteira, risco) e §128 (DoD quant)

### Requirements

1. Funções puras, sem I/O, em `app/quant/`, separadas da persistência.
2. **Cada métrica com fórmula, periodicidade e metodologia documentadas** (AGENTS.md §25/§27/§128).
3. Distinguir retorno do ativo, retorno da carteira e variação patrimonial (§26) — com aportes intermediários, `(atual − inicial)/inicial` **não** é rentabilidade.
4. Anualização explícita (252 pregões? 365 dias?) — documentar a convenção escolhida.
5. Dado faltante e série curta demais tratados explicitamente; seguir a política do ADR-014.
6. Testes com casos conhecidos: entrada conhecida → resultado esperado conhecido, não apenas "não quebra" (§68).

### Constraints

- **Não** implementar benchmark (W08), scoring (W09) nem backtesting (W13).
- Nenhuma chamada externa; consome só o que está no banco.
- Decidir onde `float` passa a ser aceitável na fronteira com numpy/pandas e **documentar** (AGENTS.md §17, ADR-003).

---

## Definition of Done (vale para a opção escolhida)

- [ ] Cálculo puro, determinístico, com cada fórmula documentada
- [ ] Dado faltante tratado conforme [ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md)
- [ ] Testes com valores conhecidos + edge cases
- [ ] `pytest` verde (baseline 184 + novos), sem regressão
- [ ] `ruff check` e `black --check` limpos nos arquivos alterados
- [ ] `docs/PROJECT_STATUS.md` e a memória atualizados
- [ ] Commit convencional em inglês com o ID da task
