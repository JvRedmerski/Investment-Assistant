# ADR-014 — Indicadores: `None` significa não-computável, nunca zero

## Status

Accepted (2026-08-17, Wave 06)

## Context

`financial_indicators` alimenta os sub-scores de Quality/Valuation/Growth da Wave 09. Um indicador errado ali não fica visível: ele vira um score plausível, que vira uma recomendação plausível, que o usuário não tem como distinguir de uma análise sólida.

Três situações exigiam uma política explícita, porque em todas a saída "conveniente" é enganosa.

## Decision

### 1. Insumo ausente ou denominador zero → `None`

Nunca zero, nunca um default, nunca exceção, nunca infinito. `None` significa **"não computável a partir do que temos"**, e é semanticamente diferente de um zero medido: `net_income = 0` produz `net_margin = 0.0` (a empresa empatou), enquanto `net_income = NULL` produz `net_margin = None` (não sabemos).

Quem consumir esses valores precisa tratar `None` explicitamente — não coalescer para zero.

### 2. Crescimento sobre base negativa ou zero → `None`

Uma empresa que sai de prejuízo de 100 para prejuízo de 50 reportaria "+50% de crescimento de lucro" sob a fórmula usual com `abs()`. Isso lê como boa notícia sobre uma empresa que continua perdendo dinheiro.

Como percentual, crescimento sobre base negativa não é interpretável. O módulo reporta "não computável" e deixa o caso de turnaround para quem tiver contexto para tratá-lo.

### 3. ROIC não presume alíquota de imposto

NOPAT = `ebit × (1 − alíquota efetiva)`. Ambos os insumos são obrigatórios. Adotar a alíquota nominal brasileira (34% = IRPJ 25% + CSLL 9%) como default embutiria uma premissa de modelagem dentro de um número apresentado como medido (AGENTS.md §44).

Quando o EBIT for ingerido, a origem da alíquota vira uma decisão explícita a tomar.

## Evidence

- `backend/app/domain/fundamentals/indicators.py` — `_ratio_decimal`, `_growth`, `_nopat`, com a justificativa em cada docstring.
- `backend/tests/test_fundamental_indicators.py` — `test_zero_numerator_is_a_real_zero_not_none`, `test_zero_denominator_yields_none_not_an_exception`, `test_growth_is_none_from_a_negative_base`, `test_roic_is_none_when_only_ebit_is_supplied`.
- `AGENTS.md` §44 (nunca inventar), §113 (determinismo), §128 (tratamento de dado faltante documentado).

## Alternatives

- Coalescer ausência para zero — rejeitado: torna dado faltante indistinguível de resultado medido e contamina qualquer média ou score.
- Crescimento com `abs(base)` — rejeitado pelo motivo acima; é a convenção mais comum, e é exatamente por isso que precisa estar registrada como decisão consciente.
- Alíquota nominal de 34% como default — rejeitado: premissa disfarçada de medição.
- Levantar exceção em divisão por zero — rejeitado: um período com denominador zero é dado legítimo, não erro de programação.

## Consequences

- ✅ Score construído sobre esses indicadores nunca é alimentado por número inventado.
- ✅ `None` vs `0.0` carrega significado real e testado.
- ⚠️ **A Wave 09 precisa tratar `None` explicitamente** em todo sub-score. Coalescer para zero ali anularia esta decisão.
- ⚠️ Turnarounds (prejuízo → lucro) não têm `profit_growth`. Se isso virar um sinal necessário, crie um indicador próprio com semântica clara em vez de afrouxar `_growth`.
- ⚠️ Com os insumos atuais, 6 dos 10 indicadores são sempre `None` — ver [ADR-013](ADR-013-fundamentals-point-in-time.md) e a task W06-003.
