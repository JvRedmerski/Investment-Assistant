# ADR-008 — `/auth/refresh` reemite a partir de um access token válido

## Status

Accepted (2026-08-16, Wave 03)

## Context

A Wave 03 pedia um endpoint de refresh. O roadmap trata refresh token como "se necessário". Um refresh token dedicado exige armazenamento, rotação, revogação e detecção de reuso — infraestrutura considerável para uma aplicação pessoal de usuário único que ainda nem tem tela de login.

## Decision

`POST /api/v1/auth/refresh` exige um **access token ainda válido** (via `get_current_user`) e reemite um novo access token. Não há refresh token dedicado, nem persistência, nem rotação.

## Evidence

- `backend/app/api/routes/auth.py` — `refresh_access_token(current_user: User = Depends(get_current_user))`.
- Nenhuma tabela de tokens em `001_initial_schema`.
- `AGENTS.md` §101 (preferir simples e explicável a complexo).

## Alternatives

- Refresh token dedicado, persistido e rotacionado — a forma correta para produção multiusuário; adiada por não haver necessidade real ainda.
- Nenhum refresh (só relogin) — rejeitado: a Wave 03 pedia o endpoint.

## Consequences

- ✅ Implementação simples, sem estado, sem tabela nova.
- ⚠️ **Se o access token expirar, não há como renovar** — o usuário precisa fazer login de novo. Mitigado hoje por um TTL longo (8 dias por padrão no código; o `.env.example` chega a sugerir 80 dias).
- ⚠️ Não há revogação: um token vazado é válido até expirar. TTL longo agrava isso.
- ⚠️ **Revisitar na Wave 24 (Security Hardening)**: encurtar o TTL do access token e introduzir refresh token dedicado antes de qualquer exposição pública. Se isso for feito, este ADR passa a `Superseded`.
