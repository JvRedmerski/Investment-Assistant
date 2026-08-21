# Session Handoff

## Last Updated

2026-08-21

## Last Completed Work

### Wave 12 — AI Engine, 3/3 (`c7643af`, `47ee85a`, `6d0b315`)

A wave que transformou "a IA não calcula" de promessa em mecanismo. O
[ADR-009](../decisions/ADR-009-quant-deterministic-ai-explains.md) decidiu isso em
2026-08-09 e não disse *como* — não havia código de IA para dizer. Agora há.

| task | entrega |
|---|---|
| **W12-001** | `AIProvider` + `GeminiProvider` + `OllamaProvider` + `DisabledAIProvider`, sobre o transporte compartilhado ([ADR-029](../decisions/ADR-029-ai-provider-speaks-rest.md)) |
| **W12-002** | `app/domain/ai/` — fact pack, prompts versionados, guard ([ADR-030](../decisions/ADR-030-fact-pack-and-the-hallucination-guard.md)) |
| **W12-003** | `POST /portfolios/{id}/explain/{performance,contribution-plan,scores/{ticker}}` |

### Como a garantia funciona, e por que ela não é um prompt

Um prompt **pede**; ele não **garante**. Três mecanismos, nesta ordem:

1. **Não há o que calcular.** O modelo recebe um fact pack — lista fechada e plana de
   valores já calculados, com rótulo, unidade, string renderizada e endpoint de origem.
   Sem série, sem componente, sem linha de banco. `facts.py` é a **cintura estreita**:
   tudo que o modelo verá passa por ali, então a regra vive em um lugar legível em vez de
   depender de disciplina espalhada.
2. **Não há o que arredondar.** Arredondar é calcular. `formatting.py` é o espelho exato
   de `frontend/src/lib/format.ts`, incluindo `ROUND_HALF_UP` porque é o gêmeo Python do
   half-expand do ECMA-402. O modelo recebe `12,4%` e copia — a frase e o painel citam a
   **mesma string**.
3. **O que sobrar é apontado.** `guard.py` confronta todo número do texto com o conjunto
   fechado de figuras que o backend escreveu (valor renderizado, valor canônico e
   **rótulo** — "nota de 0 a 100" torna `0` e `100` citáveis). O que não casar volta em
   `unverified_figures`.

**Reportar em vez de rejeitar foi decisão, não preguiça.** Rejeitar faria a confiabilidade
do recurso depender de como o modelo redigiu uma frase: o usuário veria erro no lugar da
explicação, a chamada seria repetida, e a repetição é outro sorteio. Filtro com falso
positivo é filtro que alguém desliga. Reportar mantém a falha visível e grudada no
artefato — a mesma escolha que o motor de score faz com `coverage`.

### Os dois defeitos que a wave achou em si mesma

Os dois eram de **desenho**, e os dois apareceram rodando um teste escrito para outra
coisa — o teste que proíbe o prompt de introduzir número que não seja fato (regra 43).

1. **`key` e `source` estavam sendo renderizados dentro do prompt.** Servem ao leitor, não
   ao modelo, e mandá-los punha os dígitos de `/api/v1/portfolios/1` na frente de um
   modelo instruído a citar só o que recebeu. Hoje viajam só na `Explanation`.
2. **O prompt de sistema trazia `"12,4%"` como exemplo** de como citar um valor — um
   número plausível presente em toda requisição, pronto para vazar. Virou `"X,Y%"`, e um
   teste agora proíbe qualquer coisa com a forma `\d,\d` ali.

Um terceiro achado, sobre o contrato e não sobre o código: meus testes de rota assumiam o
envelope de erro sob `detail`, quando a regra 72 o põe no topo. **O teste é que estava
errado** — conferir de que lado está o erro continua valendo.

## Current State

- `pytest` → **944 passed** (859 → 944), verificado em 2026-08-21. `ruff` e `black` limpos
  nos arquivos alterados.
- **Nenhuma migration**: nada da W12 é gravado (regra 16). Schema segue `012_corporate_actions`.
- `google-generativeai` **removido** do `pyproject.toml` — declarado desde a W00, nunca
  importado, nem instalado no venv, e descontinuado pelo Google
  ([ADR-029](../decisions/ADR-029-ai-provider-speaks-rest.md)).
- `RetryingJsonClient` ganhou `post_json` e `default_headers`, as primeiras capacidades
  novas desde o ADR-012. As 859 asserções anteriores passaram sem alteração.
- **Wave 12 🟢 concluída**, 3/3. Nada iniciado da W13.

## Important Details

### 🔴 O que NÃO foi verificado, e é a primeira coisa a fazer

**Nenhuma chamada real a modelo nenhum aconteceu.** A `GEMINI_API_KEY` é válida, mas a
Gemini API está **desabilitada no projeto Google Cloud dela** — HTTP 403
`SERVICE_DISABLED`, projeto `980912867288`. Não há Ollama local.

**Por isso nenhum teste de regressão de parser foi escrito**, de propósito: um mock
construído sobre suposição não verifica a suposição, reproduz ela. Foi assim que dois
campos da Brapi passaram por 45 testes verdes na W06-003. O procedimento completo está em
[CURRENT_TASK.md](CURRENT_TASK.md).

### Os enganos fáceis de cometer aqui

**`unverified_figures` não é diagnóstico, é leitura obrigatória.** Um cliente que exiba a
prosa e ignore a lista desfaz metade da garantia. Nenhuma tela lê o campo hoje — a W12 é
backend-only por decisão, e isso está em Future Work.

**Tópico novo exige builder novo.** Não existe tópico livre, de propósito: tópico sem
builder é prompt sem fatos, que é exatamente o que o ADR-030 proíbe.

**Não edite um `prompts/*_v1.txt` no lugar.** Wording nova é arquivo `_v2`, porque a versão
viaja em toda `Explanation` — editar em cima deixaria textos já gerados atribuídos a uma
instrução que não existe mais.

**`AI_PROVIDER=none` não é defeito.** É deployment suportado: as rotas respondem 503
`AI_NOT_CONFIGURED` dizendo o que configurar. Explicação é a única feature do projeto que
pode ser desligada sem mudar um número em lugar nenhum.

**Um POST que grava não pode reusar `post_json` cegamente.** O retry dele é seguro porque
geração de texto não cria recurso; um POST que mutasse estado precisa de idempotência
própria.

### As duas capacidades do roadmap §24 que ficaram fora

*Resumir documentos* e *resumir notícias*. Não é falta de tempo: **o projeto não ingere
notícia nem documento** — não há tabela, provedor nem endpoint. Um tópico para eles seria
prompt sem fatos. Está em Future Work; ingerir notícia é uma wave própria.

## Pending Work

1. **Verificar os providers contra uma resposta real** (acima).
2. **Wave 13 — Backtesting**. Ver [CURRENT_TASK.md](CURRENT_TASK.md) e o roadmap §25.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md). Se a Gemini API já estiver habilitada, comece pelo
item 1 — são vinte minutos e ele tira dois módulos do estado "não verificado".

## Relevant Files

- `backend/app/integrations/ai/` — `base` · `schemas` · `exceptions` · `gemini` · `ollama` · `factory`
- `backend/app/domain/ai/facts.py` — a cintura estreita: tudo que o modelo vê passa aqui
- `backend/app/domain/ai/formatting.py` — o espelho de `frontend/src/lib/format.ts`
- `backend/app/domain/ai/guard.py` — o controle que torna a regra 44 verificável
- `backend/app/domain/ai/prompts/*_v1.txt` — os prompts versionados (regra 43)
- `backend/app/integrations/http.py` — `post_json` e `default_headers`
- `backend/app/api/routes/portfolios.py` — as três rotas `explain/*`, no fim do arquivo
- `docs/decisions/ADR-029-*.md` e `ADR-030-*.md`
