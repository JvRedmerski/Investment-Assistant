# ADR-029 — O provedor de IA fala REST pelo transporte compartilhado; o SDK do Google é descartado

## Status

Accepted (2026-08-21, Wave 12)

## Context

`google-generativeai>=0.4.1` está declarado no `pyproject.toml` desde a Wave 00, **nunca foi importado por nenhuma linha de código** e nem sequer está instalado no venv atual. A Wave 12 é a primeira que teria motivo para usá-lo.

Três fatos apurados antes de decidir:

1. **É o SDK que o Google descontinuou** em favor de `google-genai`. Adotá-lo agora não é adotar uma biblioteca, é adotar uma migração já anunciada.
2. **Ele traz o próprio transporte**: cliente HTTP, política de retry, backoff e hierarquia de exceções próprias. Usá-lo faria da IA a **única** integração do projeto fora do `RetryingJsonClient` — e, portanto, a única cujo timeout, retry e throttle são de outra pessoa (AGENTS.md §22).
3. **A requisição que este projeto faz é um POST com três campos**: `systemInstruction`, `contents` e `generationConfig`. Não há streaming, não há function calling, não há upload de arquivo, não há sessão. O AI Engine explica números já calculados (ADR-009) e nada mais.

O [ADR-012](ADR-012-shared-http-transport.md) já tinha previsto este momento: ele nomeia "IA (W12)" como um dos quatro provedores que compartilhariam o transporte, e foi escrito justamente para que o quarto não recomeçasse do zero.

## Decision

**`GeminiProvider` e `OllamaProvider` falam REST direto, pelo `RetryingJsonClient`.** O `google-generativeai` é **removido** do `pyproject.toml` em vez de mantido sem uso.

Para isso, o transporte compartilhado ganhou duas capacidades — as primeiras desde o ADR-012:

- **`post_json(path, payload)`**, com a mesma política de retry do `get_json`. Retentar é seguro aqui porque uma geração de texto não cria recurso nem muda estado: o custo de uma retentativa são tokens. Um POST que mutasse estado **não** pode reusar este método sem tratamento de idempotência, e o docstring diz isso.
- **`default_headers`**, porque o Google autentica por header. A chave vai em `x-goog-api-key` e **não** no `?key=` que os quickstarts mostram: chave em URL vaza para log de acesso, cache de proxy e mensagem de erro.

Remover a dependência é parte da decisão, não um efeito colateral. Uma dependência declarada, descontinuada e não importada é documentação errada: a próxima sessão leria o `pyproject.toml` e concluiria que o projeto usa o SDK.

## Evidence

- `backend/app/integrations/ai/gemini.py` e `ollama.py` — só URL e parsing, como o ADR-012 prevê.
- `backend/app/integrations/http.py` — `post_json`, `_request`, `default_headers`.
- `backend/tests/test_ai_factory.py` — POST envia corpo e `Content-Type`, headers vão em toda requisição, e **GET continua sem corpo** depois do refactor.
- As 859 asserções pré-existentes passaram sem alteração após a mudança no transporte compartilhado (a suíte foi 859 → 944 apenas com testes novos).
- `AGENTS.md` §8, §22, §40, §41, §92; ADR-004, ADR-012.

## Alternatives

- **Usar `google-generativeai`** — rejeitado: descontinuado, e transporte paralelo ao do resto do projeto.
- **Usar `google-genai` (o sucessor)** — rejeitado por §92: é uma dependência nova para economizar ~40 linhas de parsing, e ela reintroduz o mesmo transporte paralelo. A pergunta volta se a wave precisar de streaming, function calling ou upload — aí o SDK paga por si.
- **Manter `google-generativeai` declarado "para depois"** — rejeitado: dependência não usada é afirmação falsa sobre o sistema, e esta em particular envelheceu.

## Consequences

- ✅ Uma política de resiliência para **todas** as integrações, IA inclusive. Ajustar retry continua sendo um lugar só.
- ✅ Uma dependência a menos, e a que sobrou não é uma que já nasce para migrar.
- ✅ `OllamaProvider` sai quase de graça: mesmo transporte, outra URL, outro parsing (AGENTS.md §42 — a arquitetura não depende de API proprietária).
- ⚠️ O formato da resposta do Gemini passa a ser responsabilidade nossa. Se o Google mudar `v1beta`, quem conserta somos nós — e é por isso que o parsing está isolado em um módulo só, com o formato documentado no docstring.
- 🔴 **O parser do Gemini ainda não foi verificado contra uma resposta real.** A chave em `.env` é válida, mas a Gemini API está desabilitada no projeto Google Cloud dela (HTTP 403 `SERVICE_DISABLED`). Pelo procedimento do `IMPLEMENTATION_GUIDE`, **nenhum teste de regressão foi escrito sobre essas suposições** — um mock construído sobre suposição não verifica a suposição, reproduz ela (a lição da W06-003). O mesmo vale para o `OllamaProvider`, que não tem servidor local para responder. Ver *Known Issues* em [docs/PROJECT_STATUS.md](../PROJECT_STATUS.md).
