# Current Task

## Task

**W11-003 — Fundação do frontend.** Terceira das seis tasks da **Wave 11 — Dashboard**
(roadmap §23), e o ponto em que a wave finalmente toca React.

## Status

🟡 **Em andamento.** As duas tasks de backend (W11-001 e W11-002) estão entregues; nada de
frontend começou.

---

## A wave em seis tasks

O roadmap §23 pede três telas — Dashboard, Carteira e Ativo. Duas tasks de backend vêm antes
delas, porque pedem números que **o backend ainda não produz** e que a regra 73 proíbe calcular
no frontend.

| task | entrega | por quê |
|---|---|---|
| ✅ **W11-001** | Valor de mercado e P&L não realizado nas posições | "Patrimônio" é a manchete do dashboard e não existia: `/positions` era custo basis |
| ✅ **W11-002** | A **série** de evolução da carteira sobre a API | o comparativo devolvia só métricas resumidas. **Expôs e corrigiu um erro de unidade** que deixava o índice negativo |
| **W11-003** | Fundação do frontend: rotas, react-query, cliente tipado com envelope de erro e token, `zod`, layout, login e rota protegida | sem autenticação no cliente, nenhuma tela busca nada |
| **W11-004** | Tela **Dashboard** | patrimônio, rentabilidade, CDI, IBOV, composição, risco, evolução, próximo aporte |
| **W11-005** | Tela **Carteira** | posições, transações, performance |
| **W11-006** | Tela **Ativo** | cotação, fundamentos, histórico, score |

---

## W11-001 — as decisões que a task tem que tomar

### Qual preço vale uma posição

**`close`, nunca `adjusted_close`.** O próprio `market_data/series.py` já diz por quê: `close` é
o que o mercado imprimiu e é o insumo certo para qualquer pergunta *pontual*; `adjusted_close` é
preço de retorno total e só vale para série de retorno. Valorizar posição com preço ajustado
reportaria um valor inventado para qualquer data que não a última.

### O que fazer quando falta preço — e aqui há dois precedentes que se contradizem

- `performance_index._value_on` devolve `None` para o **dia inteiro** se *um* ativo não tem preço:
  série time-weighted com constituintes diferentes em duas datas não é uma série mais curta, é
  outra carteira.
- `recommendations/service.py` escolheu **custo basis** justamente para não deixar o pilar inteiro
  ausente quando um ativo não tem preço.

Os dois estão certos nos seus contextos, e nenhum dos dois serve aqui. Uma tabela de posições
pede **ausência por linha**: a linha sem preço aparece com `market_value: null`, e o total diz o
que cobre. Nome do campo faz o trabalho — `valued_market_value`, e não `total_market_value` —,
mais `unvalued_positions` e `unvalued_invested` para dimensionar o buraco.

### Defasagem é rótulo, não nota de rodapé (regras 103/104)

Cada linha carrega `price_date`; o total carrega a data mais **antiga** e a mais **nova** entre os
preços usados. Um patrimônio que mistura preço de hoje com preço de três meses atrás precisa
dizer isso.

## O que já está pronto — não reimplemente

- `compute_positions` (`app/domain/portfolio/service.py`) — posições consolidadas, puro.
- `performance_index` (`app/domain/portfolio/performance.py`) — índice time-weighted; `_value_on`
  já é a aritmética de valorizar um dia, mas com política de ausência diferente e de propósito.
- `app/domain/market_data/series.py` — o ponto único que separa `close` de `adjusted_close`.
- `GET /portfolios/{id}/positions` em `app/api/routes/portfolios.py`, com o helper de posse.

## Divergências entre documentação e código encontradas na abertura da wave

O código é a fonte de verdade (CLAUDE.md §3); as duas serão corrigidas na wave:

1. `docs/architecture/FRONTEND.md` diz que `npm run lint` está quebrado. **Não está** — a FIX-001
   (2026-08-19) instalou ESLint 10 e o `eslint.config.js` existe. `npm run lint` e `npm run build`
   passam limpos.
2. O docstring de `get_portfolio_positions` diz que valor de mercado depende da "Wave 05, not yet
   implemented". A W05 está concluída desde então.

## Estado do ambiente (verificado 2026-08-21)

- ✅ `pytest -q` → **815 passed**. `ruff check .` e `black --check .` limpos.
- ✅ Frontend: `npm run build` e `npm run lint` passam. Baseline: 1.484 módulos, 154 kB.
- ✅ Docker no ar, schema **`012_corporate_actions`** (head).
- Banco real: carteira `Local` (id 1) **sem transação**; PETR4 com setor e fundamentos, os outros
  três sem. Preço: 1.495 pregões para os quatro papéis.
