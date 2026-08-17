# ADR-006 — `bcrypt` e `PyJWT` diretos, sem passlib/python-jose

## Status

Accepted (2026-08-16, Wave 03)

## Context

O `pyproject.toml` original declarava `passlib[bcrypt]` e `python-jose[cryptography]` — o par convencional em tutoriais de FastAPI. Ao implementar a autenticação, constatou-se que `python-jose` nunca chegou a ser importado e que `passlib` está sem manutenção ativa.

## Decision

Usar `bcrypt` e `PyJWT` diretamente em `app/core/security.py`. `passlib` e `python-jose` foram removidos do `pyproject.toml`.

## Evidence

- `backend/app/core/security.py` — importa `bcrypt` e `jwt` (PyJWT).
- `backend/pyproject.toml` — `pyjwt`, `bcrypt`, `email-validator`; sem passlib/python-jose.
- `backend/tests/test_security.py` — 7 casos: hash/verify, criação, decodificação, expiração, adulteração.
- `AGENTS.md` §92 (justificar dependência) e §89 (nunca armazenar senha em texto puro).

## Alternatives

- Manter `passlib` como camada de abstração de algoritmo — rejeitado: abstração que não estava sendo usada, sobre uma lib sem manutenção; o projeto usa um único algoritmo.
- `argon2` em vez de bcrypt — não avaliado nesta decisão; bcrypt atende e é o que já estava declarado.

## Consequences

- ✅ Duas dependências a menos, ambas mantidas ativamente.
- ✅ Sem dependências fantasma no manifesto.
- ⚠️ Trocar o algoritmo de hash exige tocar `security.py` diretamente (sem camada de abstração) e planejar rehash dos usuários existentes.
- ⚠️ bcrypt trunca senhas acima de 72 bytes — verificar se há guarda antes de alterar o fluxo de registro.
