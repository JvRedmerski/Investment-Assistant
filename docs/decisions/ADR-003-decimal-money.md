# ADR-003 — Valores monetários em `NUMERIC(18,6)` / `Decimal`

## Status

Accepted (2026-08-16)

## Context

O schema original da Wave 02 usava `Float` para quantidade, preço e taxas — violando AGENTS.md §17. Ponto flutuante binário acumula erro em somas de dinheiro, e posições são calculadas somando dezenas de transações.

O schema já estava commitado, então a correção era uma decisão arquitetural sobre trabalho existente. Foi levada ao usuário em vez de decidida sozinha; ele optou por migrar imediatamente em vez de aceitar como dívida.

## Decision

Colunas monetárias usam a constante `MONEY = Numeric(18, 6)`; os models declaram `Mapped[Decimal]`; schemas Pydantic usam `Decimal`; cálculos somam `Decimal`.

Convertidos na migration `002_numeric_money_columns`: `transactions.{quantity,price,fees}` e `asset_prices.{open,high,low,close,adjusted_close}`.

`volume` permanece `Float` — é contagem, não dinheiro.

18 dígitos com 6 casas comporta quantidade fracionária (ETFs/FIIs) e preço em BRL sem arredondamento silencioso.

## Evidence

- `backend/app/data/models/portfolio.py` e `assets.py`: constante `MONEY`, com comentário explicando a escolha.
- `backend/migrations/versions/002_numeric_money_columns.py`.
- `backend/app/domain/portfolio/service.py`: `ZERO = Decimal(0)`, aritmética inteiramente em `Decimal`.
- `backend/tests/test_models.py`: teste de regressão garantindo retorno como `Decimal`, não `float`.

## Alternatives

- Manter `Float` e arredondar na apresentação — rejeitado: o erro já teria ocorrido no acumulado.
- Inteiros em centavos — rejeitado: não comporta quantidade fracionária nem preços com mais de 2 casas.
- Aceitar como dívida técnica — considerado e rejeitado pelo usuário; o custo cresceria a cada wave.

## Consequences

- ✅ Sem drift em somas de posição.
- ✅ Precisão preservada de ponta a ponta (banco → ORM → schema → JSON).
- ⚠️ `Decimal` serializa como **string** no JSON. O frontend precisa tratar isso ao consumir valores monetários.
- ⚠️ Nunca misture `Decimal` com `float` em uma expressão — Python levanta `TypeError`. Ao integrar numpy/pandas no Quant Engine (Wave 07), converta explicitamente na fronteira e documente onde `float` passa a ser aceitável (AGENTS.md §17 permite para estatística, exigindo que a decisão seja registrada).
- ⚠️ Dívida remanescente, adiada de propósito: `intraday_prices` (W15), `portfolio_snapshots` (W11), `investor_profiles.monthly_contribution` (W09).

## Extensão — 2026-08-17 (W06-001): `fundamentals` em `NUMERIC(24,4)`

Migration `003_numeric_fundamentals_columns` estendeu esta decisão às colunas monetárias de `fundamentals`, com **precisão diferente** e por um motivo concreto: são agregados de companhia inteira na casa das centenas de bilhões de BRL. A receita anual da Petrobras (~R$ 5,1 × 10¹¹) consome 12 dos 12 dígitos inteiros que `NUMERIC(18,6)` permite. `STATEMENT_MONEY = Numeric(24, 4)` deixa 20 dígitos inteiros de folga, e 4 casas decimais excedem o que qualquer demonstrativo reporta.

`financial_indicators` permanece `Float` deliberadamente: guarda razões e taxas de crescimento (P/L, ROE, margens), não moeda. A regra 17 permite float onde for adequado desde que a decisão seja registrada — está registrada aqui e na constante `INDICATOR` em `app/data/models/fundamentals.py`.

Decisão escalada ao usuário, como foi a de 2026-08-16. Mesma ressalva: a migration não foi aplicada contra PostgreSQL real.
- ⚠️ A migration ainda não foi aplicada contra PostgreSQL real.
