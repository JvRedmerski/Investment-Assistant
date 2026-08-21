# ADR-030 — O modelo recebe um fact pack renderizado, e número sem lastro é reportado, não rejeitado

## Status

Accepted (2026-08-21, Wave 12)

## Context

O [ADR-009](ADR-009-quant-deterministic-ai-explains.md) decidiu que a IA **não calcula e não decide**. Ele não disse *como* isso é garantido, porque na época não havia código de IA. Chegando à W12, "garantir" precisou virar mecanismo, e três perguntas concretas apareceram:

1. **O que exatamente o modelo recebe?** Se ele receber a carteira, a série de preços ou os componentes de um score, ele *pode* calcular — e um LLM que pode calcular vai calcular, com resultado plausível e errado.
2. **Quem arredonda?** Mandar `0.12384` e pedir "explique" é pedir ao modelo que arredonde. Arredondar é calcular. E um `12%` no texto ao lado de um `12,4%` no painel é a mesma classe de defeito que a W11-004 corrigiu — o número da tela e o número do texto discordando.
3. **O que fazer quando ele inventa mesmo assim?** A regra 44 proíbe inventar. Um prompt *pede*; não *garante*.

## Decision

### O modelo recebe um fact pack, e só isso

Uma lista fechada e plana de valores **já calculados**, cada um com rótulo, unidade, a string já renderizada e o endpoint de origem (`app/domain/ai/schemas.py`). Construída por um builder por tópico, em `app/domain/ai/facts.py`, que é a **cintura estreita** da wave: tudo que o modelo verá passa por ali.

Não há série, não há componente, não há linha de banco. Não há o que calcular.

### Quem arredonda é o backend, e ele arredonda igual à tela

`app/domain/ai/formatting.py` é o espelho de `frontend/src/lib/format.ts`: mesmos separadores, mesmos dígitos, e `ROUND_HALF_UP` porque é o gêmeo Python do half-expand do ECMA-402. O modelo recebe `12,4%` e é instruído a copiar. A frase e o painel citam a **mesma string**.

### Ausência viaja como ausência

Fato sem valor **fica no pack**, com traço, sob um cabeçalho próprio que diz o que aquela lista significa. Removê-lo deixaria o modelo livre para supor que o número não era interessante. Pack em que **nada** foi calculado nem chega ao provedor: vira uma frase fixa e não gasta requisição (a regra 44 em código).

### Número sem lastro é reportado, não rejeitado

Depois da geração, `app/domain/ai/guard.py` extrai todo token numérico do texto e o confronta com o conjunto fechado de figuras que o backend escreveu (valor renderizado, valor canônico e **rótulo** — "nota de 0 a 100" torna `0` e `100` citáveis). O que não casar volta em `Explanation.unverified_figures`, ao lado da prosa, e sai como `WARNING` no log.

## Evidence

- `backend/app/domain/ai/{schemas,facts,formatting,guard,prompting,service}.py`.
- `backend/tests/test_ai_guard.py` — pega o número inventado (`4,8%` de "inflação"), pega o número **derivado** pelo modelo (`2,35 vezes o CDI`), e **não** pega `12,40%` contra um fato `12,4%`, que é a mesma quantidade.
- `backend/tests/test_ai_prompting.py::test_no_prompt_introduces_a_figure_that_is_not_a_fact` — a regra 43 virou teste: um prompt que crescesse "o teto por ativo é 20%" falha aqui.
- `backend/tests/test_ai_formatting.py` — os valores esperados são os de `format.ts`, incluindo o arredondamento half-away-from-zero.
- `AGENTS.md` §3, §24, §30, §43, §44, §91, §112, §113.

## Alternatives

- **Rejeitar a resposta com número sem lastro** (levantar erro) — rejeitado, e foi a primeira ideia. Faria a confiabilidade do recurso depender de como o modelo redigiu uma frase: o usuário veria erro no lugar da explicação, a chamada seria repetida, e a repetição é outro sorteio não determinístico. Pior, um filtro estrito tem falso positivo (um ordinal, um ano, "os 5 pilares"), e controle que dá alarme falso é controle que alguém desliga. Reportar mantém a falha **visível e grudada no artefato** — a mesma escolha que o motor de score faz com `coverage`.
- **Mandar o valor cru e deixar o modelo formatar** — rejeitado: arredondar é calcular (§3), e o texto passaria a discordar do painel.
- **Omitir os fatos ausentes do prompt** — rejeitado: silêncio lê-se como "não era relevante", e é exatamente aí que o modelo preenche a lacuna.
- **Mandar `key` e `source` no prompt** — rejeitado: o modelo não usa nenhum dos dois, e `GET /api/v1/portfolios/1/...` coloca dígitos soltos na frente de um modelo instruído a citar só os números que recebeu. A rastreabilidade (§112) viaja na `Explanation`, que é onde um leitor a consulta. §91 pede o mínimo; aqui o mínimo também é o prompt mais seguro.

## Consequences

- ✅ A afirmação "a IA não calcula" deixou de ser confiança e virou estrutura: não há insumo para calcular, e o que sair fora do conjunto é apontado.
- ✅ Toda explicação é auditável sozinha: ela carrega os fatos que a produziram, cada um com o endpoint de origem e a versão do prompt (`system_v1+topico_v1`).
- ✅ O texto e a tela citam a mesma string, por construção.
- ⚠️ `unverified_figures` **não vazio não bloqueia a resposta**. Quem consumir a API precisa exibir essa lista; uma tela que a ignorar desfaz metade desta decisão. A W12 é backend-only, então isso está em Future Work para a wave de frontend.
- ⚠️ O guard tem falso positivo por desenho — um número escrito por extenso em prosa ("os 3 primeiros") pode ser apontado. É o preço de não ter falso negativo, e é suportável justamente porque o resultado é um relatório e não uma rejeição.
- ⚠️ Cada tópico novo precisa de um builder novo. Não há tópico livre, de propósito: tópico sem builder é prompt sem fatos.
