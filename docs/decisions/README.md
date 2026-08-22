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
| [016](ADR-016-unadjusted-bars-are-not-stored.md) | Barra sem `adjusted_close` reportado não é armazenada | Accepted | market data, ingestão, retornos (W07) |
| [017](ADR-017-annualisation-and-numeric-type.md) | Anualização: 365 p/ retorno, 252 p/ dispersão; `Decimal` puro, sem `numpy` | Accepted | quant engine, retornos, risco, Sharpe, numpy |
| [018](ADR-018-benchmark-representation.md) | Benchmark de taxa guarda a taxa publicada (fração), não índice acumulado; CDI anualiza em 252; período incompleto não é gravado | Accepted | benchmarks, CDI, IBOV, IPCA, BCB SGS, Sharpe, beta |
| [019](ADR-019-portfolio-return-is-time-weighted.md) | Rentabilidade de carteira é TWR entregue como índice de cota; beta só contra `INDEX`; razão "% do CDI" só com ambos positivos | Accepted | carteira, rentabilidade, TWR, MWR, aporte, comparação, beta |
| [020](ADR-020-cvm-primary-fundamentals-source.md) | Dados abertos da CVM como fonte primária de demonstrativos; Brapi faz a ponte ticker→CNPJ; composição por período inteiro, nunca campo a campo | Accepted | fundamentals, CVM, Brapi, CNPJ, DFP, EBITDA, composite |
| [021](ADR-021-allocation-ranks-by-coverage-tier.md) | A alocação do aporte ordena por faixa de cobertura antes do score, reusa os tetos do pilar de Diversification, e o plano é derivado a cada leitura | Accepted | recommendation, allocation, coverage, aporte, perfil conservador, rule 31/32/33 |
| [022](ADR-022-provider-plan-limits-are-refused-locally.md) | O bucket de `range` da Brapi é medido de `start` até hoje (a API não aceita data inicial), e uma janela acima do teto do plano é recusada localmente com erro nomeado em vez de truncada em silêncio | Accepted | market data, Brapi, range, plano gratuito, ingestão, rule 32 |
| [023](ADR-023-unadjusted-history-is-stored-as-unadjusted.md) | Histórico sem ajuste é gravado com `adjusted_close` NULL em vez de rejeitado ou preenchido com o `close`; a semântica da ausência pertence à fonte, e um ponto único de passagem mantém a série de retorno só com linhas ajustadas | Accepted | market data, COTAHIST, B3, adjusted close, emenda ADR-016, rule 44 |
| [024](ADR-024-refill-fills-null-columns.md) | Um período de demonstrativo já gravado aceita preenchimento de coluna **nula**, e só dela; valor presente nunca é tocado | Accepted | fundamentals, coluna de demonstrativo nova, ingestão, emenda operacional ao ADR-013 |
| [025](ADR-025-corporate-events-come-from-the-distribution-counter.md) | Evento societário vem do contador de distribuição da B3 (não do marcador), com data e natureza e **sem magnitude** | Accepted | eventos societários, proventos, COTAHIST, série de retorno total, rule 44 |
| [026](ADR-026-corporate-action-magnitude-and-the-completeness-rule.md) | A **magnitude** vem do serviço aberto de eventos da B3, junta pelo ISIN; `adjusted_close` só é derivado onde **toda** sessão contada tem ação dimensionada, com o `ATZ` como única exceção | Accepted | eventos societários, magnitude, retorno total, `adjusted_close`, pilar de Risco, completa ADR-023/ADR-025 |
| [027](ADR-027-target-weight-comes-from-merit.md) | O peso-alvo é proporcional ao **mérito** (o score sem Diversificação), porque um alvo feito do `final_score` recua conforme a carteira se aproxima; concentração vira teto em vez de termo, e o que os tetos não cobrem volta como `unassigned` | Accepted | rebalanceamento, `target_weight`, `weight_gap`, drift, mérito, W10, rule 34 |
| [028](ADR-028-rebalancing-is-cash-flow-only.md) | Rebalancear é dirigir aporte e **nunca vender**; e o portão, a banda e a ordenação rodam sobre a carteira **depois** do aporte, não sobre a de hoje — usar o peso pré-aporte deixava R$ 1.000 parados e afastava a carteira do alvo | Accepted | rebalanceamento, plano de aporte, venda, diluição, W10, rule 34 |
| [029](ADR-029-ai-provider-speaks-rest.md) | O provedor de IA fala REST pelo `RetryingJsonClient` (POST + header de auth); `google-generativeai` é **removido** em vez de usado — SDK descontinuado e transporte paralelo | Accepted | IA, Gemini, Ollama, dependências, transporte HTTP, completa ADR-012 |
| [030](ADR-030-fact-pack-and-the-hallucination-guard.md) | O modelo recebe um **fact pack** já renderizado (nada de série, nada de arredondar) e número sem lastro volta em `unverified_figures` — reportado, nunca rejeitado | Accepted | IA, prompts, explicações, rule 43/44, materializa o ADR-009 |
| [031](ADR-031-a-statement-is-readable-only-after-the-filing-deadline.md) | Um demonstrativo só é legível **três meses** depois do fim do período — o prazo da própria CVM, a data legal mais tardia — e o lag é zero no caminho vivo | Accepted | backtesting, fundamentos, look-ahead, rule 108/109, estende ADR-013 |
| [032](ADR-032-the-backtest-stops-where-the-total-return-series-stops.md) | A janela do backtest começa onde **todo** ativo tem série de retorno total completa, e quem não tem nenhuma é excluído com motivo nomeado | Accepted | backtesting, `adjusted_close`, proventos, janela, rule 59, consome ADR-026 |
| [033](ADR-033-a-truncated-explanation-is-reported-not-discarded.md) | `MAX_TOKENS` é **truncagem, não conclusão**: o provider normaliza para `truncated`, e a explicação cortada é reportada — nunca descartada, nunca aparada até parecer inteira | Accepted | IA, providers, orçamento de tokens, modelo de raciocínio, rule 22/44, aplica ADR-030 |

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
