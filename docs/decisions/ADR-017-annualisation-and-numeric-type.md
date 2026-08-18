# ADR-017 — Anualização em dias corridos, e `Decimal` sem fronteira `float` no Quant Engine

## Status

Accepted (2026-08-18, Wave 07 / W07-001), estendido por adendo em 2026-08-18 (W07-002)

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

> ⚠️ **Esta previsão não se confirmou.** A W07-002 levantou operação por operação e concluiu que `Decimal` cobre todas as cinco métricas de risco. Ver o [adendo de 2026-08-18](#adendo--2026-08-18-w07-002-a-fronteira-decimal--float-não-existe) ao final; o parágrafo acima fica como registro do que se esperava, não como orientação.

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
- ✅ ~~`risk.py` precisa definir seu próprio 252~~ — **cumprido na W07-002**: `PERIODS_PER_YEAR` mora em `risk.py` e há um teste (`test_dispersion_annualises_on_trading_sessions_not_calendar_days`) que falha se alguém trocá-lo por `DAYS_PER_YEAR`.
- ✅ ~~A fronteira `Decimal → float` continua em aberto~~ — **resolvida no adendo abaixo (2026-08-18)**: não existe fronteira; o Quant Engine inteiro fica em `Decimal`.
- ⚠️ CAGR sobre janelas menores que 30 dias corridos retorna `None`. Um consumidor que queira "retorno do mês" deve usar `period_returns(..., MONTHLY)` ou `total_return`, que não anualizam.

---

## Adendo — 2026-08-18 (W07-002): a fronteira `Decimal → float` não existe

Este ADR previu que `risk.py` precisaria de `float`, porque desvio-padrão, covariância e raiz quadrada são "estatística", e a regra 17 abre essa porta desde que a decisão seja registrada. A decisão foi tomada com o cálculo em mãos, e é a oposta da esperada.

**Nenhuma das cinco métricas exige `float`.** Levantando operação por operação:

| métrica | operações necessárias | `Decimal` cobre? |
|---|---|---|
| volatilidade | somas, subtrações, divisão, `sqrt` | sim |
| maximum drawdown | comparações, divisão | sim |
| beta | somas, produtos, divisão | sim |
| Sharpe | as de volatilidade + potência fracionária (de-anualizar a taxa) | sim |
| Sortino | idem, filtrando as observações abaixo do alvo | sim |

`Decimal.sqrt()` existe e é corretamente arredondado; potência fracionária já havia sido verificada na W07-001. Não há matriz, não há inversão, não há função transcendental. Nada aqui pede `numpy`.

**Então o Quant Engine fica inteiramente em `Decimal`, e `numpy`/`scipy` seguem sem nenhum import no projeto.**

O argumento decisivo não é precisão de dinheiro — são frações adimensionais, e `float` daria conta da magnitude. É **determinismo** (regra 113): uma soma em `float` depende da ordem dos termos, então a mesma série somada em ordem diferente pode divergir no último bit, e essa divergência atravessa uma raiz quadrada e uma divisão até virar um Sharpe que não reproduz. `Decimal` a 28 dígitos significativos não deriva ao longo de alguns milhares de observações. Quando o determinismo é grátis, não há motivo para abrir mão dele.

Consequência para as waves seguintes: **a expectativa de "usar numpy no quant" deve ser considerada revogada**, não pendente. Se uma wave futura precisar de álgebra matricial de verdade — a matriz de covariância para volatilidade de carteira, ou otimização de Markowitz — aí a fronteira volta a ser uma pergunta legítima, e deve ser decidida naquele momento com o mesmo critério: qual operação concreta `Decimal` não cobre.

Registra-se também o que **não** foi implementado: **volatilidade de carteira**. Ela não é a média das volatilidades dos ativos — precisa da matriz de covariâncias e dos pesos das posições, porque ativos pouco correlacionados cancelam risco entre si. Depende dos pesos, que vêm do motor de posições, então pertence à análise de carteira e não a este módulo. Está em Future Work. **Não aproximar por média** — seria inventar um número (regra 44).
