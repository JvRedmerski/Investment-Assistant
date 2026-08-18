# ADR-017 — Anualização em dias corridos, e `Decimal` sem fronteira `float` no módulo de retornos

## Status

Accepted (2026-08-18, Wave 07 / W07-001)

## Context

O Quant Engine é a base de tudo que vem depois: benchmarks (W08), scores de recomendação (W09), backtesting (W13). Uma convenção errada aqui não aparece como bug — aparece como um número plausível em toda wave seguinte. Duas decisões estavam pendentes desde o handoff da Wave 06, ambas listadas na DoD da task.

### 1. Convenção de anualização: 252 pregões ou 365 dias corridos?

As duas convenções circulam na literatura como se fossem alternativas para a mesma pergunta. Não são.

### 2. Onde `float` passa a ser aceitável?

A regra 17 do AGENTS.md exige `Decimal` para valores monetários e permite `float` "para cálculos estatísticos onde floating point seja adequado, **desde que a decisão seja documentada**". Preços são `Decimal`; `numpy`/`pandas`/`scipy` estão no `pyproject.toml` desde a Wave 00 e nunca foram importados. A expectativa registrada no handoff era que a W07 introduzisse essa fronteira.

## Decision

### 1. Retornos anualizam em **dias corridos (ACT/365 fixo)**; volatilidade anualizará em **252 pregões**

Não é um meio-termo: as duas convenções respondem a perguntas diferentes, e a escolha decorre de qual grandeza está sendo escalada.

- **Retorno composto escala com tempo decorrido.** Um investimento mantido de janeiro a julho rendeu ao longo de seis meses de mundo — independentemente de quantos pregões a B3 abriu no período. Feriado não suspende juro, não suspende inflação e não suspende CDI. O denominador correto é calendário. `DAYS_PER_YEAR = 365`.

- **Volatilidade escala com número de observações.** O desvio-padrão de retornos diários é uma estatística *por observação*; anualizá-lo é multiplicar por `√(observações por ano)`, e um ano tem ~252 pregões, não 365. Usar 365 ali infla a volatilidade em ~19% (`√(365/252) ≈ 1.20`).

**A consequência importante é que misturar as duas corrompe silenciosamente o Sharpe**, que divide um retorno anualizado por uma volatilidade anualizada. Se as duas pontas usarem relógios diferentes, o índice fica errado por um fator constante — e nada no resultado denuncia isso. Por isso a constante mora em `returns.py` com a justificativa escrita ao lado, e `risk.py` (W07-002) definirá a sua própria, explicitamente, em vez de importar esta.

**365 fixo, não 365,25**: a diferença de dia bissexto move um retorno anualizado em muito menos de um ponto-base ao longo de uma década — ordens de magnitude abaixo do ruído dos próprios preços — e um divisor fixo mantém o resultado reprodutível sem consultar calendário.

Vale registrar que **o teste pegou o autor errando exatamente esse ponto**: o caso conhecido de CAGR foi escrito assumindo que 2024-01-01 → 2026-01-01 fossem 730 dias. São 731 — 2024 é bissexto. O teste falhou, e o intervalo foi trocado por um sem ano bissexto. É a evidência de que os casos são de fato calculados à mão e conferidos, e não ajustados ao que o código produziu.

### 2. `returns.py` não tem fronteira `float`. Tudo é `Decimal`.

A fronteira que a regra 17 antecipa **não foi introduzida nesta task, porque não era necessária**. Retorno exige subtração, divisão e — só no CAGR — exponenciação fracionária. Todas as três são operações de `Decimal`, determinísticas na precisão do contexto ativo (28 dígitos significativos por padrão):

```python
>>> (Decimal(2) ** (Decimal(1) / Decimal(2)) - 1)
Decimal('0.414213562373095048801688724')
```

Converter para `float` custaria precisão sem comprar nada. E os valores são **compostos adiante** — a comparação com benchmark da W08 e o backtester da W13 vão encadeá-los — então arredondar nesta fronteira propagaria erro para baixo.

A conversão para `float` continua acontecendo onde o número é **persistido ou serializado**, como `financial_indicators` já faz (ADR-003).

A fronteira `float` **será** necessária em `risk.py`, para desvio-padrão, covariância (beta) e as raízes quadradas de Sharpe/Sortino. Essa decisão pertence à W07-002, onde a necessidade é real e pode ser justificada com o cálculo concreto em mãos. Antecipá-la aqui seria importar `numpy` para satisfazer uma expectativa documentada, não uma necessidade.

## Evidence

- `backend/app/quant/returns.py` — `DAYS_PER_YEAR` e `MIN_ANNUALISATION_DAYS`, cada um com a justificativa na própria docstring; seção "`Decimal`, and why there is no `float` here".
- `backend/tests/test_quant_returns.py` — `test_cagr_of_a_doubling_over_two_years` (730 dias exatos, sem ano bissexto), `test_cagr_over_exactly_one_year_equals_the_simple_return`, `test_cagr_is_none_for_a_span_too_short_to_annualise`.
- `AGENTS.md` §17 (dinheiro e precisão), §24 (quant engine), §25 (retornos), §113 (determinismo), §128 (DoD quant: fórmula, periodicidade, dado faltante, timezone).

## Alternatives

- **252 pregões para tudo** — rejeitado. Anualizar um retorno por número de pregões trata feriado como se o dinheiro parasse de render. Sobre 6 meses, o erro no expoente chega a ~45%.
- **365 dias corridos para tudo** — rejeitado. Infla a volatilidade anualizada em ~19% e, por consequência, subestima o Sharpe na mesma proporção.
- **365,25 dias** — rejeitado por precisão espúria: o ganho é sub-ponto-base e o custo é um divisor que depende de qual década se está medindo.
- **Anualizar sem piso mínimo de janela** — rejeitado. CAGR extrapola o período para um ano; sobre 2 dias, +3% viram ~+25.000%. Daí `MIN_ANNUALISATION_DAYS = 30`, heurística documentada no mesmo espírito do `ABSURD_MOVE_THRESHOLD` da qualidade de market data.
- **Introduzir `float`/`numpy` já em `returns.py`, por consistência com `risk.py`** — rejeitado. Seria perder precisão para uniformizar, e adotar dependência antes de ter o cálculo que a exige (regra 92, e a regra de foco 134).
- **Retornar `float` na saída pública, como `IndicatorSet` faz** — rejeitado. `IndicatorSet` é a fronteira de **persistência**; `returns.py` entrega valores para outro código puro consumir e encadear.

## Consequences

- ✅ Retorno e volatilidade anualizam em relógios explicitamente escolhidos, com o motivo escrito onde a constante vive — o erro de Sharpe por relógios misturados fica difícil de cometer sem ler a justificativa contrária.
- ✅ Nenhuma perda de precisão em `returns.py`, e nenhuma dependência nova.
- ⚠️ **`risk.py` (W07-002) precisa definir seu próprio `TRADING_DAYS_PER_YEAR = 252`** e **não** reutilizar `DAYS_PER_YEAR`. Se um Sharpe futuro parecer estranho por um fator ~1,2, é aqui que se olha primeiro.
- ⚠️ A fronteira `Decimal → float` continua **em aberto** para a W07-002, que deve registrá-la (a regra 17 exige documentação, e este ADR não a cobre — cobre apenas a ausência dela em retornos).
- ⚠️ CAGR sobre janelas menores que 30 dias corridos retorna `None`. Um consumidor que queira "retorno do mês" deve usar `period_returns(..., MONTHLY)` ou `total_return`, que não anualizam.
