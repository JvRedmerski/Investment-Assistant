# ADR-013 — Fundamentals: só anual, restatement não sobrescreve, nada de TTM

## Status

Accepted (2026-08-17, Wave 06)

## Context

Demonstrativos financeiros só têm valor num backtest se respeitarem a data em que a informação estava disponível ao mercado (AGENTS.md §108/§109). Três armadilhas apareceram ao implementar a ingestão, todas capazes de corromper silenciosamente qualquer análise histórica futura.

## Decision

### 1. Apenas demonstrativos anuais

`fundamentals` identifica a linha por `(asset_id, reference_date)` e **não tem coluna de período**. Um exercício anual encerrado em 31/12/2024 e o 4º trimestre de 2024 reportam a mesma data-fim: duas linhas indistinguíveis com significados diferentes.

Ingestão trimestral fica adiada até o schema conseguir diferenciá-las.

### 2. `reference_date` já armazenado nunca é sobrescrito

Uma empresa pode reexpressar (restate) um exercício anterior, e o provedor passará a servir o número corrigido para a mesma data-fim. Substituir o valor guardado reescreveria o que o sistema "sabia" à época.

Tratar reexpressão corretamente exige um schema que comporte mais de uma versão do mesmo período (com a data em que cada versão passou a ser conhecida). Enquanto isso não existe, o primeiro valor gravado permanece.

### 3. `ebitda` e `free_cash_flow` ficam `NULL`

> ⚠️ **A justificativa original desta seção estava errada.** Ver "Correção" abaixo. A decisão (`NULL`) se mantém, mas por outro motivo.

~~A Brapi expõe esses dois campos apenas no módulo `financialData`, que é um snapshot trailing-twelve-months sem data-fim de período.~~

Derivá-los (EBITDA de EBIT + depreciação, FCF de fluxo operacional − capex) depende de convenções de sinal e rotulagem que não podem ser verificadas sem uma resposta real da API. Um número silenciosamente errado é pior que um `NULL` honesto (AGENTS.md §44).

---

## Correção — 2026-08-17 (W06-003), após validação contra a API real

A primeira versão deste ADR foi escrita sem acesso de rede, a partir da documentação. Uma única chamada real (`GET /quote/PETR4`, 16 períodos anuais) mostrou que:

**O item 3 estava errado sobre onde o EBITDA vive.** A Brapi expõe `cleanEbitda` **por período**, dentro de `incomeStatementHistory` — não apenas como snapshot TTM. Porém o campo é **idêntico a `ebit` nos 16 períodos**: nenhuma depreciação/amortização é somada de volta. Ou seja, não é EBITDA.

Conclusão: `ebitda` continua `NULL`, agora por evidência (`cleanEbitda` é uma cópia de `ebit`) em vez de por suposição sobre a estrutura da API. `debt_ebitda` e `ebitda_margin` seguem bloqueados.

**Os itens 1 e 2 se confirmaram.** As linhas trazem um discriminador `type` (`"yearly"`), o que valida a preocupação com mistura de períodos — o parser agora filtra explicitamente por ele em vez de assumir. A política de não sobrescrever reexpressões permanece.

**Correção relacionada:** a simetria "indicadores também nunca são sobrescritos", herdada deste ADR pela W06-002, foi revista — ver [ADR-015](ADR-015-indicator-recomputation.md). Fatos reportados continuam imutáveis; valores derivados podem ser recomputados sob demanda.

**Lição registrada:** dois campos (`totalStockholderEquity`, `totalDebt`) foram mapeados a partir da documentação e são `null` em 100% dos períodos reais, o que deixou `equity`, `debt` e, por consequência, `roe` silenciosamente `None`. Nenhum teste pegou isso, porque todos os testes usavam payloads que eu mesmo escrevi com os nomes que eu supunha corretos. **Mock construído sobre uma suposição não verifica a suposição.** Existe agora um teste de regressão com a resposta real (`test_regression_against_the_real_petr4_response`).

## Evidence

- `backend/app/integrations/fundamentals/base.py` — `get_annual_statements`, com a limitação de escopo na docstring do módulo.
- `backend/app/domain/fundamentals/service.py` — docstring sobre semântica de cache/restatement; consulta `existing_dates` e pula.
- `backend/app/integrations/fundamentals/brapi.py` — tabela de mapeamento de campos; `ebitda=None`, `free_cash_flow=None` com a justificativa inline.
- `backend/tests/test_fundamentals_service.py::test_existing_reference_date_is_skipped_and_never_overwritten` — sincroniza `revenue=100`, depois sincroniza `revenue=999` para o mesmo período, e asserta que o valor armazenado continua `100`.
- `backend/tests/test_brapi_fundamentals_provider.py::test_ebitda_and_free_cash_flow_are_none_not_fabricated`.
- `AGENTS.md` §44, §108, §109.

## Alternatives

- Ingerir trimestral e anual na mesma tabela — rejeitado: produz linhas ambíguas.
- Adicionar coluna `period` agora — fora do escopo do W06-001; é a evolução natural quando houver necessidade real de trimestral.
- Upsert (sobrescrever com o valor reexpresso) — rejeitado: destrói o histórico point-in-time e torna backtests não reproduzíveis.
- Preencher EBITDA/FCF com o snapshot TTM — rejeitado: look-ahead.

## Consequences

- ✅ Cada linha armazenada tem significado inequívoco e pertence ao período sob o qual está gravada.
- ✅ Backtests futuros podem confiar em `reference_date`.
- ⚠️ **`ebitda` e `free_cash_flow` estarão sempre `NULL` com o provedor atual.** A W06-002 precisa tratar ausência explicitamente em `debt_ebitda` e `ebitda_margin` — nunca assumir zero.
- ⚠️ Reexpressões ficam invisíveis ao sistema. Registrado como Future Work; exigirá schema versionado por período.
- ⚠️ Sem dados trimestrais, indicadores TTM não são calculáveis a partir desta tabela.
