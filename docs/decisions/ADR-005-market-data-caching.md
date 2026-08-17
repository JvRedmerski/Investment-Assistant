# ADR-005 — Sync explícito escreve; leitura nunca chama a API externa

## Status

Accepted (2026-08-17, Wave 05)

## Context

Provedores gratuitos de cotação impõem rate limit rígido. Se abrir uma página disparasse busca de histórico, a cota se esgotaria em minutos e a latência ficaria refém de um terceiro. Além disso, dado histórico já corrigido não deve ser sobrescrito por uma resposta nova e possivelmente pior.

## Decision

Separação estrita entre write-path e read-path:

- **Write-path** — `POST /assets/{ticker}/prices/sync` é o **único** ponto do sistema que chama o provedor. Busca a janela, valida qualidade, insere apenas as datas ainda **não** armazenadas, e retorna `fetched/inserted/skipped_existing/rejected`.
- **Read-path** — `GET /assets/{ticker}/prices` lê exclusivamente de `asset_prices`. Nunca consulta o provedor, nem como fallback em cache miss.

Uma data já armazenada **nunca** é sobrescrita por um sync. Re-pull de correção é deliberadamente deixado como operação manual/futura.

O banco é o cache: não há Redis nem TTL.

## Evidence

- `backend/app/domain/market_data/service.py` — `sync_daily_history`, docstring explicitando a semântica; consulta `existing_dates` e pula.
- `backend/app/api/routes/assets.py` — `list_asset_prices` não recebe `provider` como dependency; é impossível chamar o provedor de lá.
- `backend/tests/test_market_data_routes.py` — teste injeta um provider que lança `AssertionError` se invocado e exercita o read-path, provando a propriedade; outro teste prova idempotência do sync.
- `AGENTS.md` §20, §23.

## Alternatives

- Cache-aside com TTL (busca sob demanda em miss) — rejeitado: reintroduz chamada externa no caminho do usuário e torna a latência imprevisível.
- Upsert no sync (sobrescrever sempre) — rejeitado: apagaria silenciosamente histórico já validado.
- Redis — desnecessário na escala atual; registrado como Future Work.

## Consequences

- ✅ Rate limit respeitado por construção; leitura é rápida e previsível.
- ✅ Sync é idempotente — rodar duas vezes não duplica nem altera nada.
- ✅ Histórico é imutável, o que é pré-requisito para backtest honesto (AGENTS.md §108/§109).
- ⚠️ Ninguém dispara o sync automaticamente ainda — não há scheduler/worker (AGENTS.md §117, wave futura). Hoje é manual via API.
- ⚠️ Se o provedor corrigir uma barra, o sistema mantém a versão antiga. Correção exige intervenção deliberada.
- ⚠️ Aplique o mesmo padrão a fundamentals (W06) e intraday (W15).
