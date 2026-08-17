# ADR-001 — PostgreSQL como banco principal, SQLite apenas em testes

## Status

Accepted (2026-08-09)

## Context

Sistema com transações financeiras, precisão decimal e séries históricas longas. Era necessário escolher um banco e definir se testes poderiam usar algo mais leve.

## Decision

PostgreSQL 16 é o banco oficial para dev e produção. SQLite é permitido **exclusivamente** em testes isolados, onde o schema é criado e derrubado por teste.

## Evidence

- `docker-compose.yml`: serviço `postgres:16-alpine` com healthcheck.
- `backend/app/core/config.py`: `DATABASE_URL` apontando para Postgres; driver `psycopg2-binary` no `pyproject.toml`.
- `backend/tests/conftest.py`: engine SQLite in-memory com `StaticPool`, com comentário explícito citando a regra.
- `AGENTS.md` §12 formaliza a regra.

## Alternatives

- SQLite também em dev — rejeitado: divergência de tipos (`NUMERIC`, enums, constraints) mascararia bugs que só apareceriam em produção.

## Consequences

- ✅ Consistência relacional e `NUMERIC` nativo para dinheiro.
- ✅ Testes rápidos, sem dependência de container.
- ⚠️ Testes **não** validam comportamento específico do Postgres. Migrations em especial precisam de verificação contra Postgres real — a `002_numeric_money_columns` ainda não teve essa verificação.
- ⚠️ Ao escrever código, evite SQL específico de um dialeto sem testar em ambos.
