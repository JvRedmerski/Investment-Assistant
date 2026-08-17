# Implementation Guide

> Camada 4. Como implementar uma task neste projeto.
> Regras completas: [../../AGENTS.md](../../AGENTS.md) (138 seções numeradas). Este guia é o extrato operacional.

## Princípios arquiteturais

1. **Correção antes de tudo.** A ordem de evolução do projeto é `Correctness → Tests → Quantitative Validation → Explainability → Performance → Automation`. Nunca invertida (AGENTS.md §136).
2. **Determinismo.** O motor quantitativo produz a mesma saída para a mesma entrada. Exceções precisam ser documentadas (§113).
3. **A IA não calcula.** Ver [ADR-009](../decisions/ADR-009-quant-deterministic-ai-explains.md).
4. **Dado externo é hostil.** Valide sempre: campo ausente, preço inválido, gap, duplicidade, API fora do ar (§19/§20).
5. **Dado histórico é imutável.** Preços, fundamentos e recomendações já gravados não são sobrescritos (§20/§39/§109).
6. **Sem look-ahead.** Nunca use informação indisponível no momento da decisão. Isso vale para backtest e também para a ordem de replay do ledger (§58/§108).
7. **Mudança mínima.** Altere só o necessário; não refatore o que não faz parte da task (§9/§134).
8. **Simples, testável, explicável** > complexo e esperto (§101/§135).

## Estratégia de implementação de uma task

```
1. Ler docs/memory/CURRENT_TASK.md
2. Ler a seção correspondente em docs/roadmap.md e as regras do AGENTS.md citadas
3. Ler o código do padrão análogo já existente  ← o passo mais importante
4. Planejar: o que criar, o que modificar, o que pode quebrar
5. Implementar seguindo o padrão existente
6. Escrever testes (valores conhecidos, não "não explode")
7. pytest → ruff → black nos arquivos alterados
8. Atualizar docs/PROJECT_STATUS.md e a memória (ver CLAUDE.md §5)
9. Commit: <tipo>: <descrição em inglês> (<TASK-ID>)
```

**Nunca comece escrevendo código.** Sempre encontre primeiro o padrão análogo — este projeto tem padrões fortes e consistentes; replicá-los vale mais do que qualquer solução nova.

## Padrões estabelecidos (replicar, não reinventar)

| Precisa de… | Copie o padrão de |
|---|---|
| Integração externa nova | `app/integrations/fundamentals/` (base + schemas + exceptions + vendor + factory), delegando resiliência a `app/integrations/http.py` |
| Serviço de ingestão | `app/domain/market_data/service.py` (`sync_daily_history`) |
| Validador de qualidade | `app/integrations/market_data/data_quality.py` (função pura, report com errors/warnings) |
| Cálculo financeiro | `app/domain/portfolio/service.py` (`compute_positions`: puro, `Decimal`, sem I/O) |
| Endpoints CRUD escopados | `app/api/routes/portfolios.py` (helper de ownership + 404) |
| Schemas de request/response | `app/domain/<área>/schemas.py` (`ConfigDict(from_attributes=True)` nos responses) |
| Dependency de integração | `app/api/dependencies.py` (`get_market_data_provider`) |
| Teste com provider fake | `tests/test_market_data_routes.py` (`dependency_overrides`, zero rede) |
| Teste de cálculo | `tests/test_portfolio_service.py` (valores conhecidos, edge cases) |

## Convenções de código

**Python** — type hints em tudo; funções pequenas; classe só quando agrega valor; erro tratado explicitamente; nada de `except: pass`. Sintaxe moderna: `X | None`, `list[X]` (não `Optional`/`List` — os arquivos antigos que ainda usam são dívida conhecida). `Decimal` para dinheiro. UTC explícito para datas.

**TypeScript** — modo estrito; evitar `any`, preferir `unknown` + validação; todo contrato de API tipado; `zod` para dado externo.

**Commits** — Conventional Commits em inglês: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `perf:`. Um commit por task concluída.

## Definition of Done

### Geral (AGENTS.md §127)
- [ ] Código implementado e funcionando
- [ ] Testes criados e executados
- [ ] Lint e format limpos **nos arquivos alterados**
- [ ] Migration criada quando o schema mudou
- [ ] `docs/PROJECT_STATUS.md` atualizado
- [ ] Memória atualizada (`CURRENT_TASK`, `SESSION_HANDOFF`, `PROJECT_STATUS`)

### Adicional para Quant (§128)
- [ ] Fórmula documentada · periodicidade definida · timezone considerado
- [ ] Caso conhecido testado (entrada conhecida → resultado conhecido esperado)
- [ ] Edge cases e dado faltante tratados

### Adicional para Recommendation (§130)
- [ ] Score determinístico e versionado · evidências armazenadas · risco · horizonte · portfolio fit · reason · timestamp · versão do algoritmo

### Adicional para Day Trade (§129)
- [ ] Entry, stop, target, risk definidos · fees e slippage considerados · backtest disponível · look-ahead auditado · paper trading disponível

Uma wave só é 🟢 quando **todas** as tasks obrigatórias passam nos critérios. Havendo bloqueio: 🔴. Implementado mas pendente de revisão: ⚠️.

## Proibições absolutas

Nunca: inventar dados de mercado ou resultado de backtest · remover teste para o build passar · desabilitar lint sem justificativa · usar `any` para esconder erro de tipo · commitar secret · alterar migration já aplicada · ignorar erro silenciosamente · usar look-ahead · mascarar dado ausente · colocar lógica financeira crítica no frontend · usar IA como substituto do Quant Engine · implementar ordens reais em corretora.

## Quando algo dá errado

```
Reproduzir → Identificar causa → Corrigir a causa → Teste de regressão → Rodar a suíte → Documentar
```

Nunca contorne o sintoma.

## Quando não souber

Não invente. Consulte a documentação oficial da dependência. Se a incerteza permanecer — por exemplo, um parser que não pôde ser validado contra a API real — **implemente defensivamente e documente a lacuna explicitamente** no `PROJECT_STATUS.md` e no ADR correspondente (§124). Foi exatamente assim que a lacuna do `BrapiProvider` foi tratada; siga o mesmo procedimento.

## Quando o pedido quebrar a arquitetura

Não implemente de imediato: explique o impacto → proponha alternativa → se o usuário confirmar, registre um ADR e só então implemente (§125).
