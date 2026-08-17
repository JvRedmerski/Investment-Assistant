# ADR-002 — Posições derivadas do ledger de transações (custo médio móvel)

## Status

Accepted (2026-08-16, Wave 04)

## Context

Uma carteira precisa expor quantidade detida, preço médio, valor investido, P&L realizado e dividendos por ativo. Havia duas formas: manter uma tabela de posições atualizada a cada transação, ou recalcular a partir do histórico.

Manter `quantity` e `average_price` como valores independentes cria duas fontes de verdade que divergem ao primeiro bug, correção retroativa ou transação fora de ordem.

## Decision

**Não existe tabela de posições.** `app/domain/portfolio/service.py` deriva tudo de `transactions` em tempo de leitura, com replay cronológico e método de **custo médio móvel** (moving-average):

- `BUY` — soma `quantity × price + fees` ao investido e recalcula o preço médio ponderado.
- `SELL` — reduz quantidade; o preço médio dos remanescentes **não muda**; realiza P&L = `proceeds − fees − custo das cotas vendidas`.
- `DIVIDEND` — não altera quantidade nem preço médio; acumula em `dividends_received`.
- `DEPOSIT`/`WITHDRAWAL` — fluxo de caixa da carteira, sem `asset_id`; entram em `compute_net_contributions`.

Ordenação do replay: `(transaction_date, id)` — o `id` como desempate garante determinismo e evita usar informação de uma transação que ainda "não aconteceu".

Posições zeradas com P&L ou dividendos históricos continuam sendo retornadas; posições sem nenhum efeito são omitidas.

## Evidence

- `backend/app/domain/portfolio/service.py` — `compute_positions`, `compute_asset_quantity`, `compute_net_contributions`, com docstring citando a regra.
- `backend/app/api/routes/portfolios.py` — `/positions` chama o service; `POST /transactions` usa `compute_asset_quantity` para barrar venda acima da posição.
- `backend/tests/test_portfolio_service.py` — 11 casos unitários com valores conhecidos.
- Nenhuma tabela de posições em `001_initial_schema`.
- `AGENTS.md` §16.

## Alternatives

- Tabela de posições materializada — rejeitada por exigir mecanismo de consistência (AGENTS.md §16 desaconselha explicitamente).
- FIFO/LIFO em vez de custo médio — não adotado; custo médio é a convenção usada pelo investidor brasileiro para apuração e é o que a task pedia. Migrar exigiria versionar a metodologia.

## Consequences

- ✅ Uma única fonte de verdade; impossível divergir.
- ✅ Função pura, determinística, testável com valores conhecidos, sem I/O.
- ✅ Correções retroativas no ledger se propagam automaticamente.
- ⚠️ Custo O(n) sobre o histórico a cada leitura. Aceitável na escala atual; se virar problema, a saída é cache/snapshot **derivado** (`portfolio_snapshots`), nunca uma tabela de posições autoritativa.
- ⚠️ `compute_positions` é defensivo: um `SELL` maior que a posição é limitado em vez de gerar quantidade negativa. A validação de verdade é feita na rota.
- ⚠️ Não há valor de mercado — só custo. Precificação depende de integrar `asset_prices` (ainda não feito).
