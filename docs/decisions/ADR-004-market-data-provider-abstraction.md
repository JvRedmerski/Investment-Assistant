# ADR-004 — Provedores externos atrás de interface abstrata + factory

## Status

Accepted (2026-08-17, Wave 05)

## Context

O projeto depende de dados de terceiros: cotações, fundamentos, intraday, IA. Fontes gratuitas mudam de contrato, impõem rate limit e saem do ar. Espalhar chamadas HTTP pelo domínio tornaria a troca de fornecedor uma refatoração global.

## Decision

Toda integração externa segue este padrão de quatro peças:

| Arquivo | Papel |
|---|---|
| `base.py` | ABC com os métodos do domínio (`get_quote`, `get_daily_history`) |
| `schemas.py` | DTOs Pydantic provider-agnósticos (`DailyBar`, `Quote`) |
| `exceptions.py` | exceções tipadas do domínio de integração |
| `<vendor>.py` | implementação concreta (httpx, parsing, retry, throttle) |
| `factory.py` | escolhe a implementação por `settings.<X>_PROVIDER` |

Domínio e rotas dependem **só** do tipo abstrato, injetado por `Depends(get_market_data_provider)`. A implementação concreta é conhecida apenas pela factory.

A implementação concreta é responsável por: timeout configurável, retry **limitado** com backoff exponencial só em falhas transitórias (timeout, erro de conexão, HTTP 429/500/502/503/504), falha imediata em 4xx, throttle opcional entre requisições, e parsing defensivo que nunca assume campo presente.

## Evidence

- `backend/app/integrations/market_data/` — as cinco peças.
- `backend/app/api/dependencies.py` — `get_market_data_provider`, provider fechado no `finally`.
- `backend/app/core/config.py` — `MARKET_DATA_PROVIDER`, `MARKET_DATA_TIMEOUT_SECONDS`, `MARKET_DATA_MAX_RETRIES`, `MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS`.
- `backend/tests/test_brapi_provider.py` (15 casos) e `test_market_data_routes.py` — fake injetado via `dependency_overrides`, zero rede.
- `AGENTS.md` §21, §22, §40 (mesmo padrão exigido para `AIProvider`).

## Alternatives

- Chamar `httpx` direto no service — rejeitado: acopla o domínio ao fornecedor e torna o teste dependente de mock de HTTP.
- Instanciar o provider dentro da rota — rejeitado: impede substituição em teste sem monkeypatch.

## Consequences

- ✅ Trocar de fornecedor toca um arquivo novo e a factory.
- ✅ Testes rodam offline, determinísticos.
- ✅ O mesmo molde serve para fundamentals (W06), intraday (W15) e IA (W12) — **replique-o, não invente outro**.
- ⚠️ **Lacuna aberta**: o parser da Brapi foi escrito a partir da documentação pública e exercitado apenas contra `httpx.MockTransport` — não havia rede de saída no ambiente. Os nomes de campo (`regularMarketPrice`, `historicalDataPrice`) **não foram confirmados** contra a API real. Validar antes de usar em ingestão de produção. Documentado assim, em vez de omitido, por AGENTS.md §124.
- ⚠️ `get_quote()` existe e é testado, mas nenhum endpoint o expõe.
