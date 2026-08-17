# ADR-009 — Quant Engine determinístico no backend; IA apenas explica

## Status

Accepted (2026-08-09) — decisão fundacional do projeto

## Context

O sistema produz recomendações de alocação financeira. Um LLM consegue gerar um texto convincente recomendando qualquer coisa, inclusive com números inventados. Se a IA calculasse ou decidisse, as recomendações seriam não reproduzíveis, não auditáveis e não backtestáveis — e o usuário não teria como distinguir uma análise sólida de uma alucinação fluente.

## Decision

Separação rígida:

- **Quant Engine (backend, determinístico)** calcula tudo que é número: retornos, CAGR, volatilidade, beta, drawdown, Sharpe, Sortino, scores, pesos-alvo, resultados de backtest. Mesma entrada → mesma saída, sempre.
- **AI Engine** recebe resultados **já calculados** e produz explicação em linguagem natural. Nunca calcula, nunca decide, nunca altera um número, nunca preenche dado ausente. Sem dado: `Data unavailable.`

A IA fica atrás de uma interface `AIProvider` (mesmo padrão do [ADR-004](ADR-004-market-data-provider-abstraction.md)), com implementações Gemini e Ollama intercambiáveis.

Pesos e fórmulas de score são explícitos, versionados em código e **nunca escondidos dentro de prompts**.

## Evidence

- `AGENTS.md` §2, §3, §24, §30, §40, §43, §44, §111, §113 — a regra mais repetida do contrato.
- `docs/PROJECT_STATUS.md` → Technical Decisions, 2026-08-09.
- Estado atual: `app/quant/` e `app/integrations/ai/` **ainda não existem** (Waves 07 e 12). Nenhuma linha de código de IA foi escrita — o que significa que esta decisão ainda não foi violada, e é a hora de mantê-la.
- A precedência já está estabelecida: `compute_positions` (W04) e `validate_daily_bars` (W05) são funções puras, determinísticas, testadas com valores conhecidos.

## Alternatives

- Usar o LLM para gerar recomendações diretamente — rejeitado categoricamente: não é reproduzível, não é auditável, não é backtestável.
- Usar o LLM para preencher dados faltantes — proibido (AGENTS.md §44).

## Consequences

- ✅ Toda recomendação pode ser reconstruída: quais dados, qual versão do algoritmo, qual score, qual configuração, qual timestamp (AGENTS.md §112).
- ✅ Backtest e walk-forward são possíveis, porque o motor é determinístico.
- ✅ Trocar o provedor de IA (ou desligá-lo) não muda nenhum número.
- ⚠️ Mais trabalho: cada métrica precisa de fórmula documentada, periodicidade definida, tratamento de dado faltante e teste com caso conhecido (AGENTS.md §128).
- ⚠️ Ao chegar na Wave 12, resista à tentação de pedir ao modelo "que analise" — ele só recebe o resultado pronto e escreve o texto.
