# Architecture Decision Records

> Camada 3 da memória. Consulte **apenas** o ADR relacionado à área que você vai alterar.

Um ADR existe aqui porque a decisão (a) teve alternativas reais, (b) afeta arquitetura, e (c) confundiria uma sessão futura que a encontrasse sem contexto.

**Antes de contrariar um ADR**: explique o impacto e proponha alternativa ao usuário (AGENTS.md §125). Se a mudança for aprovada, crie um ADR novo e marque o antigo como `Superseded` — não edite o histórico.

| # | Decisão | Status | Consulte quando for mexer em |
|---|---|---|---|
| [001](ADR-001-postgresql.md) | PostgreSQL como banco principal; SQLite só em testes | Accepted | banco, testes, deploy |
| [002](ADR-002-positions-derived-from-ledger.md) | Posições derivadas do ledger de transações, custo médio móvel | Accepted | carteira, posições, performance |
| [003](ADR-003-decimal-money.md) | Valores monetários em `NUMERIC(18,6)` / `Decimal` | Accepted | qualquer coluna ou cálculo com dinheiro |
| [004](ADR-004-market-data-provider-abstraction.md) | Provedores externos atrás de interface abstrata + factory | Accepted | qualquer integração externa nova |
| [005](ADR-005-market-data-caching.md) | Sync explícito escreve; leitura nunca chama a API externa | Accepted | ingestão de dados, endpoints de leitura |
| [006](ADR-006-bcrypt-pyjwt.md) | `bcrypt` + `PyJWT` diretos, sem passlib/python-jose | Accepted | auth, dependências |
| [007](ADR-007-error-envelope.md) | Envelope de erro global `{"error":{"code","message"}}` | Accepted | qualquer endpoint novo |
| [008](ADR-008-refresh-without-refresh-token.md) | Refresh reemite a partir de access token válido | Accepted | auth, segurança (W24) |
| [009](ADR-009-quant-deterministic-ai-explains.md) | Quant determinístico no backend; IA só explica | Accepted | qualquer cálculo financeiro ou uso de IA |
| [010](ADR-010-404-over-403.md) | 404 em vez de 403 para recurso de outro usuário | Accepted | rotas escopadas por usuário |
| [011](ADR-011-no-repository-layer.md) | Sem camada de repositório; rotas usam `Session` direto | Accepted | acesso a dados |
| [012](ADR-012-shared-http-transport.md) | Transporte HTTP (retry/throttle) compartilhado entre integrações | Accepted | qualquer provedor externo novo |
| [013](ADR-013-fundamentals-point-in-time.md) | Fundamentals: só anual, restatement não sobrescreve, nada de TTM | Accepted | fundamentos, indicadores, backtesting |
| [014](ADR-014-indicator-missing-data-policy.md) | Indicadores: `None` = não-computável, nunca zero | Accepted | indicadores, scoring (W09), quant |
| [015](ADR-015-indicator-recomputation.md) | Derivados podem ser recomputados; fatos reportados não | Accepted | indicadores, correção de fórmula, W09 |

## Template

```markdown
# ADR-XXX — Nome

## Status
Accepted / Proposed / Superseded by ADR-YYY

## Context
Qual problema precisava ser resolvido.

## Decision
O que foi escolhido.

## Evidence
Onde essa decisão está materializada (arquivo, config, dependência).

## Alternatives
Alternativas reais. Não inventar as que nunca foram consideradas.

## Consequences
Ganhos e restrições que isso impõe.
```
