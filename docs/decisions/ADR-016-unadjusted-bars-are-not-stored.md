# ADR-016 — Uma barra sem `adjusted_close` reportado não é armazenada

## Status

Accepted (2026-08-18, manutenção pré-Wave 07) — **emendado pelo
[ADR-023](ADR-023-unadjusted-history-is-stored-as-unadjusted.md)**
(2026-08-19).

> A decisão abaixo **continua valendo para a fonte que ela descreve**: um
> fornecedor que calcula ajuste e ainda não o publicou está reportando um
> atraso, e a barra segue sendo rejeitada para que o sync seguinte a
> insira completa. O que o ADR-023 acrescenta é uma fonte que a premissa
> deste ADR não previa — o COTAHIST da B3 **nunca** publica ajuste, por
> ser o registro de negociação da bolsa. Ali a ausência é permanente, e a
> rejeição descartaria décadas de histórico aberto em vez de adiar um
> pregão. A distinção passou a ser declarada pela fonte
> (`reports_adjusted_close`), e a alternativa que este ADR rejeitou —
> relaxar a coluna para `NULL` — foi aceita lá, com a objeção que ele
> levantou respondida por um ponto único de passagem.

## Context

A Brapi devolve `adjustedClose: null` para a **sessão fechada mais recente** e publica o valor ajustado depois. Verificado em dados reais em 2026-08-18: nulo para 2026-08-17 em HGLG11 (FII), BOVA11 (ETF) e ITUB4 (banco) — os três, na mesma data. Não é anomalia de um ativo; é o comportamento normal da fonte.

O parser tratava isso caindo para o `close`:

```python
adjusted_close = raw.get("adjustedClose")
if adjusted_close is None:
    adjusted_close = raw["close"]     # ← removido
```

Isoladamente, parece um default inofensivo. Combinado com duas outras propriedades do sistema, não é:

1. `sync_daily_history` é idempotente por **nunca sobrescrever** uma data já armazenada (ADR-002 / Wave 05). Uma vez gravado, o valor não é revisitado.
2. A Wave 07 calcula **todos os retornos a partir de `adjusted_close`**, precisamente porque proventos e desdobramentos distorcem a série de preço bruto.

Portanto, uma barra ingerida durante a janela em que o ajuste ainda é nulo grava `close` como `adjusted_close` **permanentemente** — inclusive depois de a fonte publicar o valor real. Se houve provento ou desdobramento naquela data, o ajuste é exatamente o que não deveria ser ignorado, e todo retorno calculado sobre aquele intervalo fica errado **em silêncio**.

O modo de falha é o pior possível: não há exceção, não há log, a coluna está preenchida com um número plausível, e o erro só apareceria como uma rentabilidade ligeiramente errada meses depois.

Vale notar que **igualdade não distingue os dois casos**: em dia sem provento, `adjustedClose == close` legitimamente (verificado: BOVA11 em 2026-07-20, ambos 170.3). Não há como, depois do fato, saber se um valor gravado veio da fonte ou do fallback.

## Decision

**O parser reporta o que a fonte reportou.** `DailyBar.adjusted_close` passa a ser `Decimal | None`; `None` significa "a fonte não informou ajuste".

**O validador de qualidade rejeita a barra**, com o código `MISSING_ADJUSTED_CLOSE`. Decidir o que é seguro gravar já é a responsabilidade de `validate_daily_bars`, e a rejeição entra na contabilidade e nos logs que já existem.

Como `sync_daily_history` só grava `report.valid_bars`, o serviço não precisou mudar. Passa a valer o invariante: **toda barra em `valid_bars` tem `adjusted_close` reportado pela fonte**, então gravar na coluna `NOT NULL` é seguro sem checagem adicional.

**A propriedade que torna a rejeição segura é a autocorreção**: como a data nunca é gravada, ela não entra em `existing_dates`, e o próximo sync a insere normalmente quando a fonte publicar o ajuste. Nada se perde — apenas se adia. Na prática o atraso é de uma sessão.

## Evidence

- `backend/app/integrations/market_data/brapi.py` — `_parse_bar`, sem fabricação.
- `backend/app/integrations/market_data/data_quality.py` — `MISSING_ADJUSTED_CLOSE`.
- `backend/tests/test_market_data_service.py::test_unadjusted_bar_is_not_stored_and_lands_on_a_later_sync` — prova a autocorreção ponta a ponta: primeiro sync rejeita, segundo grava `37.90` (ajuste real, diferente do `close` `38.50`).
- `backend/tests/test_data_quality.py::test_bar_without_an_adjusted_close_is_rejected_not_backfilled_from_close`.
- `backend/tests/test_brapi_provider.py::test_regression_against_real_responses_per_asset_type` — fixa o nulo real de 2026-08-17 nos três tipos de ativo.
- `AGENTS.md` §44 (nunca inventar um número), §19 (market data é dado externo não confiável); [ADR-014](ADR-014-indicator-missing-data-policy.md) (ausente → `None`, nunca um default).

## Alternatives

- **Manter o fallback para `close`** — rejeitado. É um default substituindo uma medição, o que a §44 e o ADR-014 proíbem em texto explícito. O ADR-014 foi escrito para indicadores, mas a razão é idêntica: um número inventado é indistinguível de um medido depois de gravado.
- **Gravar e sobrescrever depois, quando o ajuste for publicado** — rejeitado por não ser implementável de forma confiável sem mudança de schema. Exigiria uma coluna de proveniência (`adjusted_close_is_fabricated`) para saber quais linhas revisitar, já que `adjusted_close == close` é comum e legítimo. Guardar proveniência de um valor que não deveria existir é resolver o problema errado.
- **Relaxar a coluna para `NULL` e gravar a barra sem ajuste** — rejeitado. Empurraria o tratamento de nulo para todo consumidor do preço, incluindo cada função de retorno da Wave 07, em troca de guardar uma barra que estará disponível completa no dia seguinte.
- **Emitir apenas um aviso e gravar** — rejeitado. Aviso em log não impede o valor errado de ser congelado; só documenta que foi.

## Consequences

- ✅ Nenhum ajuste inventado entra na série que a Wave 07 usa para calcular retornos.
- ✅ `valid_bars` carrega um invariante testado, então o caminho de gravação não precisa checar nulo.
- ✅ Autocorreção: nenhuma intervenção manual, nenhum backfill, nenhuma requisição extra além do sync normal seguinte.
- ⚠️ **A sessão fechada mais recente pode faltar no histórico** até a fonte publicar o ajuste — tipicamente um dia. Quem precisar do preço corrente deve usar `get_quote()`, que é a via correta para isso e não depende de ajuste.
- ⚠️ Se a fonte **nunca** publicar o ajuste de alguma data, ela fica permanentemente ausente. É um buraco honesto e visível na série, não um valor errado invisível — e as funções da Wave 07 precisam tratar buracos de qualquer forma.
- ⚠️ `rejected_count` agora inclui barras rejeitadas por esse motivo. Um `rejected: 1` rotineiro no sync do dia é esperado, não sinal de problema de qualidade.
