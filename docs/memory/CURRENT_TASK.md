# Current Task

## Task

**Duas coisas, e a primeira é curta.**

1. 🔴 **Fechar a verificação da W12-001** — os dois providers de IA são código **não
   verificado** até que uma chamada real aconteça. Ver *O que ficou pendente* abaixo.
2. ⚪ **Wave 13 — Backtesting** (roadmap §25, AGENTS.md §35).

## Status

🟢 **A Wave 12 fechou em 2026-08-21**, 3 de 3 tasks, e não há código pela metade em lugar
nenhum. `pytest -q` → **944 passed**.

---

## O que a Wave 12 entregou

| task | entrega |
|---|---|
| **W12-001** | `AIProvider` + `GeminiProvider` + `OllamaProvider` + `DisabledAIProvider`, todos sobre o transporte compartilhado ([ADR-029](../decisions/ADR-029-ai-provider-speaks-rest.md)) |
| **W12-002** | O domínio que explica: fact pack, prompts versionados e o guard ([ADR-030](../decisions/ADR-030-fact-pack-and-the-hallucination-guard.md)) |
| **W12-003** | `POST /portfolios/{id}/explain/{performance,contribution-plan,scores/{ticker}}` |

### O ponto inteiro da wave, em uma frase

**"A IA não calcula" deixou de ser confiança e virou mecanismo.** O modelo nunca vê o
banco, uma série ou os componentes de um score — vê um **fact pack**: lista fechada de
valores já calculados, cada um com rótulo, unidade, a string **já renderizada** e o
endpoint de origem. Não há o que calcular. Arredondar também é calcular, então quem
arredonda é `app/domain/ai/formatting.py`, que é o espelho exato de
`frontend/src/lib/format.ts` — o texto e o painel citam a **mesma string**.

E depois da geração, `guard.py` confronta todo número do texto com o conjunto fechado de
figuras que o backend escreveu. O que não casar volta em `unverified_figures`.

### Os dois defeitos que a wave achou em si mesma

Nenhum foi de digitação; os dois eram de desenho, e os dois apareceram **rodando o teste
que eu tinha escrito para outra coisa**:

1. **As URLs de origem estavam sendo renderizadas dentro do prompt.** `key` e `source`
   servem ao leitor, não ao modelo — e mandá-los punha os dígitos de
   `/api/v1/portfolios/1` na frente de um modelo instruído a citar só o que recebeu. Hoje
   viajam só na `Explanation`, que é onde a rastreabilidade é consultada (§91, §112).
2. **O prompt de sistema trazia `"12,4%"` como exemplo** de como citar um valor — um
   número plausível em toda requisição, pronto para vazar para uma explicação onde não
   significa nada. Virou `"X,Y%"`, e um teste agora proíbe qualquer coisa com a forma
   `\d,\d` ali.

---

## O que ficou pendente, e é a primeira coisa a fazer

🔴 **Nenhuma chamada real a modelo nenhum aconteceu.**

- A `GEMINI_API_KEY` no `.env` é **válida**, mas a Gemini API está **desabilitada no
  projeto Google Cloud dela**. Toda chamada responde HTTP 403 `SERVICE_DISABLED`, com a
  URL de ativação do projeto `980912867288` no corpo.
- Não há Ollama instalado, então o `OllamaProvider` está igualmente sem verificação.

**Consequência deliberada**: nenhum teste de regressão de parser foi escrito. Um mock
construído sobre suposição não verifica a suposição — reproduz ela. Foi assim que dois
campos da Brapi passaram por 45 testes verdes na W06-003.

**Procedimento quando houver acesso** (`docs/planning/IMPLEMENTATION_GUIDE.md`):

1. Habilitar a API no console do Google Cloud.
2. **Uma** chamada real. Salvar a resposta.
3. Conferir nome por nome: `candidates[0].content.parts[]`, `finishReason`,
   `usageMetadata.promptTokenCount`, `candidatesTokenCount`, `modelVersion`.
4. Corrigir `gemini.py` no que divergir, e **só então** escrever o teste de regressão, no
   molde de `tests/test_brapi_fundamentals_provider.py::test_regression_against_the_real_petr4_response`.
5. Rodar ponta a ponta contra o banco real e **ler a explicação gerada** — não só conferir
   que veio 200. É o passo que achou os dois erros de janela da W11.

O que **já** foi observado ao vivo é o envelope de erro do Google, e ele está documentado
no docstring de `gemini.py`.

---

## O que a W13 tem que respeitar

- **Retorno total, não preço bruto.** A série ajustada existe onde o ajuste é completo
  ([ADR-026](../decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md));
  onde não é, ela para, e o backtest tem que parar junto em vez de medir preço cru.
- **Sem look-ahead** (§58, §108). Vale para a ordem de replay do ledger, não só para o
  preço.
- **Determinismo** (§113): mesma entrada, mesmo resultado de backtest, sempre.
- ⚠️ **O ledger ainda não conhece evento societário** — desdobramento muda quantidade em
  custódia sem gerar transação. Está em Future Work e é pré-requisito honesto de um
  backtest que carregue posição através de um evento.

## O que já está pronto — não reimplemente

Todo o backend das waves 00–12 e as quatro telas. Contrato completo em
[../architecture/API.md](../architecture/API.md); a camada de IA em
[../architecture/BACKEND.md](../architecture/BACKEND.md).

## Estado do ambiente (verificado 2026-08-21)

- ✅ `pytest -q` → **944 passed** (era 859). `ruff` e `black` limpos nos arquivos alterados.
- ✅ **Nenhuma migration nova**: nada da W12 é gravado (regra 16).
- ✅ `AI_PROVIDER=none` é um deployment suportado — as rotas respondem 503
  `AI_NOT_CONFIGURED` com a mensagem dizendo o que configurar.
- Banco real: carteira `Local` (id 1) sem transação; PETR4 com setor e fundamentos, os
  outros três sem. 1.495 pregões para os quatro papéis.
- Rodar a app: `docker compose up -d postgres`, depois
  `cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000` e
  `cd frontend && npm run dev`.
