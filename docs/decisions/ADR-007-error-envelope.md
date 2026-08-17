# ADR-007 — Envelope de erro global `{"error": {"code", "message"}}`

## Status

Accepted (2026-08-16, Wave 03)

## Context

O FastAPI serializa `HTTPException` como `{"detail": ...}`. Sem padronização, cada rota poderia inventar seu formato, e o frontend teria que adivinhar a forma do erro. AGENTS.md §72 exige resposta consistente com um `code` legível por máquina, e §72 também proíbe vazar stack trace.

## Decision

Handler global em `app/main.py` captura **todo** `HTTPException` e normaliza:

```json
{ "error": { "code": "ASSET_NOT_FOUND", "message": "Asset PETR4 was not found." } }
```

Se a rota passar `detail` já no formato de envelope, ele é preservado (é assim que o `code` específico é definido). Caso contrário, o handler emite `code: "HTTP_ERROR"`.

## Evidence

- `backend/app/main.py` — `@app.exception_handler(HTTPException)`, com comentário citando a regra.
- Todas as rotas em `api/routes/` levantam `HTTPException(detail={"error": {...}})`.
- Códigos em uso: `INVALID_CREDENTIALS`, `ASSET_NOT_FOUND`, `ASSET_ALREADY_EXISTS`, `PORTFOLIO_NOT_FOUND`, `INSUFFICIENT_POSITION`, `MARKET_DATA_TICKER_NOT_FOUND`, `MARKET_DATA_UNAVAILABLE`, `MARKET_DATA_INVALID_RESPONSE`.

## Alternatives

- Deixar o `detail` padrão do FastAPI — rejeitado: sem `code` estável, o cliente teria que casar strings de mensagem.
- Middleware em vez de exception handler — desnecessário; o handler cobre o caso.

## Consequences

- ✅ Contrato de erro uniforme e estável para o frontend.
- ✅ Headers da exceção (ex.: `WWW-Authenticate`) são preservados.
- ⚠️ **Erros de validação do Pydantic (422) não passam por aqui** — mantêm o formato nativo do FastAPI com `detail` como lista. O frontend precisa lidar com as duas formas, ou um handler de `RequestValidationError` precisa ser adicionado numa wave de hardening.
- ⚠️ Exceções não-HTTP não tratadas continuam produzindo o 500 padrão do Starlette. Antes de produção (W24), adicionar handler genérico que não vaze stack trace.
