# ADR-015 — Indicadores derivados podem ser recomputados; fatos reportados não

## Status

Accepted (2026-08-17, Wave 06)

## Context

O [ADR-013](ADR-013-fundamentals-point-in-time.md) estabeleceu que um `reference_date` já armazenado nunca é sobrescrito. A W06-002 aplicou a mesma regra a `financial_indicators`, por simetria.

A W06-003 mostrou que essa simetria estava errada. Ao corrigir dois bugs de mapeamento e ingerir EBIT, os indicadores já gravados ficaram **desatualizados e errados** — `roe` estava `None` porque `equity` nunca era preenchido. Sem uma forma de recomputar, a única saída seria mexer no banco à mão, exatamente o que o AGENTS.md §14 proíbe.

## Decision

Distinguir os dois tipos de dado:

| | `fundamentals` | `financial_indicators` |
|---|---|---|
| natureza | **fato reportado** pela fonte | **função pura** de insumos + código |
| sobrescrita | nunca | permitida, sob demanda |

`compute_and_store_indicators(db, asset, recompute=True)` descarta os indicadores do ativo e os reconstrói. Exposto como `POST /assets/{ticker}/indicators/compute?recompute=true`.

**Opt-in, nunca automático.** O padrão continua pulando períodos já computados.

Os demonstrativos crus não são tocados em nenhum caso — nada que a fonte reportou se perde, e uma recomputação é sempre reversível rodando de novo.

## Rationale

Preservar um indicador calculado com uma fórmula errada não é preservar história: é preservar um bug. O valor não é uma observação sobre o mundo, é o resultado de `f(insumos, versão do código)` — e quando `f` é corrigida, o valor antigo simplesmente deixou de ser o que a fórmula produz.

O fato reportado é diferente: `revenue = 497.549.000.000 em 2025-12-31` é o que a fonte publicou. Substituí-lo apagaria o que o sistema sabia à época.

## Evidence

- `backend/app/domain/fundamentals/service.py` — `compute_and_store_indicators(..., recompute)`, com o raciocínio na docstring; usa `delete(synchronize_session="fetch")` para não deixar linhas removidas no identity map da sessão.
- `backend/app/api/routes/assets.py` — query param `recompute`.
- `backend/tests/test_indicators_service.py` — `test_recompute_rebuilds_rows_from_current_inputs`, `test_recompute_without_it_leaves_a_stale_row_untouched`, `test_recompute_does_not_touch_the_raw_statements`.

## Alternatives

- **Nunca recomputar** — rejeitado: obrigaria a alterar o banco manualmente após qualquer correção de fórmula, violando §14.
- **Sempre recomputar** — rejeitado: torna cada chamada cara e destrói silenciosamente valores que alguém pode estar comparando; a intenção deve ser explícita.
- **Versionar indicadores** (guardar todas as versões com a versão do algoritmo) — é o caminho correto quando o histórico de recomendações depender disso (AGENTS.md §111/§112), mas é escopo da Wave 09. Registrado como Future Work.

## Consequences

- ✅ Correção de fórmula ou chegada de insumo novo se propaga com uma chamada.
- ✅ Demonstrativos permanecem imutáveis; a garantia do ADR-013 continua valendo onde importa.
- ⚠️ **Não há versionamento**: recomputar descarta o valor anterior sem registro. Quando a Wave 09 passar a armazenar recomendações baseadas em indicadores, será preciso versionar (§111/§112) para que uma recomendação antiga continue auditável.
- ⚠️ `recompute=true` é destrutivo por ativo. Não há confirmação; é responsabilidade de quem chama.
