# ADR-012 — Transporte HTTP compartilhado entre integrações

## Status

Accepted (2026-08-17, Wave 06)

## Context

[ADR-004](ADR-004-market-data-provider-abstraction.md) fixou o molde de integração externa e mandou replicá-lo. Ao construir o segundo provedor (fundamentals), ficou claro que "replicar o molde" incluiria copiar ~60 linhas idênticas de resiliência: laço de retry limitado, backoff exponencial, classificação de status transitório vs. permanente, throttle de rate limit e parsing de JSON.

Com intraday (W15) e IA (W12) ainda por vir, isso seriam quatro cópias da mesma lógica — exatamente o anti-padrão que AGENTS.md §8 nomeia.

## Decision

O laço de resiliência vive em `app/integrations/http.py` (`RetryingJsonClient`) e é compartilhado por todos os provedores. As **classes de exceção são injetadas**, então cada integração mantém seu próprio vocabulário de erro: quem chama `market_data` continua vendo `MarketDataUnavailableError`, quem chama `fundamentals` vê `FundamentalsUnavailableError`.

Cada provedor concreto fica responsável apenas por: a forma da URL do fornecedor e o parsing da resposta.

Timeout, número de tentativas e intervalo mínimo continuam configuráveis **por integração** (`MARKET_DATA_*` e `FUNDAMENTALS_*`), porque as cadências são diferentes — preço é diário, demonstrativo é trimestral.

## Evidence

- `backend/app/integrations/http.py` — `RetryingJsonClient`, `RETRYABLE_STATUS_CODES`, `backoff_seconds`.
- `backend/app/integrations/market_data/brapi.py` e `app/integrations/fundamentals/brapi.py` — ambos delegam ao mesmo transporte.
- Os 15 testes pré-existentes de `BrapiProvider` continuam passando após a migração, sem alteração de asserção (só o alvo do `patch` de `time.sleep`/`time.monotonic` mudou de módulo, porque é onde o `sleep` passou a morar).
- `AGENTS.md` §8 e §22.

## Alternatives

- Copiar o laço em cada provedor — rejeitado: quatro cópias divergiriam, e um ajuste de política de retry teria que ser feito em quatro lugares.
- Uma classe base `BrapiClient` compartilhada pelos dois provedores Brapi — rejeitado: acopla ao fornecedor, não ao problema; não serviria a um provedor de intraday ou de IA que não seja Brapi.
- Usar uma biblioteca de retry (`tenacity`) — rejeitado: dependência nova para ~60 linhas que já existiam e já eram testadas (AGENTS.md §92).

## Consequences

- ✅ Uma política de resiliência, um lugar para ajustá-la, um conjunto de testes que a exercita.
- ✅ O próximo provedor (intraday, IA) escreve só URL + parsing.
- ⚠️ Testes que precisem interceptar `time.sleep`/`time.monotonic` devem fazer patch em `app.integrations.http.time`, não no módulo do provedor.
- ⚠️ Uma mudança no transporte afeta **todas** as integrações de uma vez. Rode a suíte inteira, não só os testes do provedor que motivou a mudança.
