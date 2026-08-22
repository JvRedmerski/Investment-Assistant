# ADR-033 — `MAX_TOKENS` é truncagem, não conclusão; e uma explicação truncada é reportada, nunca descartada nem remendada

## Status

Accepted (2026-08-22, verificação da W12-001). Aplica a [ADR-030](ADR-030-fact-pack-and-the-hallucination-guard.md), de onde vem o princípio *reportado, nunca rejeitado*, ao segundo jeito de uma explicação sair incompleta.

## Context

A W12 entregou os dois providers de IA como código **explicitamente não verificado**: a `GEMINI_API_KEY` era válida, mas a API estava desabilitada no projeto Google Cloud dela, e todas as chamadas voltavam 403 `SERVICE_DISABLED`. Por decisão registrada, **nenhum teste de regressão de parser foi escrito** — um mock construído sobre suposição reproduz a suposição em vez de verificá-la (`docs/planning/IMPLEMENTATION_GUIDE.md`, a cicatriz da W06-003).

Em **2026-08-22** a API respondeu. O contrato `v1beta` publicado bateu **nome por nome** — `candidates[0].content.parts[]`, `finishReason`, `usageMetadata.promptTokenCount`, `usageMetadata.candidatesTokenCount` e `modelVersion` todos como documentados. Diferente da Brapi, nenhum campo estava com o nome errado.

O que a chamada real mudou foi outra coisa inteira: **`gemini-flash-latest` resolve para `gemini-3.7-flash`, um modelo de raciocínio**, e o raciocínio dele é cobrado contra o mesmo `maxOutputTokens` que a prosa.

Medido, com um fact pack realista de plano de aporte (28 fatos, prompts reais do projeto):

| `maxOutputTokens` | `finishReason` | pensamento | prosa | usado | resultado |
|---|---|---|---|---|---|
| **1.024** (o padrão de então) | `MAX_TOKENS` | 981 | 39 | **99%** | frase cortada em `"...entre três ativos:"` |
| 2.048 | `STOP` | 1.383 | 295 | 81% | explicação completa |

O defeito não é a truncagem em si — é o que o código fazia com ela. `_COMPLETE` continha `{"STOP", "MAX_TOKENS"}`, então:

- `MAX_TOKENS` contava como término normal;
- o texto não estava vazio, então o guarda de `Completion.text` não disparava;
- **o fragmento chegava ao leitor como uma explicação pronta**, terminando num dois-pontos que promete uma lista que nunca vem.

E acontecia no **valor padrão**, com um pack **comum** — não numa borda. O comentário do próprio `AI_MAX_OUTPUT_TOKENS` afirmava o contrário: *"A truncated explanation comes back with a finish_reason saying so rather than silently ending mid-sentence."* Vinha com o `finishReason`, sim; ninguém olhava.

Uma segunda divergência apareceu junto: `usageMetadata.thoughtsTokenCount` **não** está incluído em `candidatesTokenCount`. `output_tokens` reportava 153 numa requisição que produziu 701 tokens de saída faturáveis.

## Decision

### 1. `MAX_TOKENS` sai de `_COMPLETE`

`_COMPLETE = frozenset({"STOP"})`. Só há um jeito de um modelo terminar porque acabou de dizer o que tinha a dizer.

### 2. A truncagem é normalizada **no provider**, e o domínio nunca aprende o vocabulário do fornecedor

`Completion` ganha `truncated: bool`. A Gemini escreve `MAX_TOKENS`, o Ollama escreve `length`, e o próximo fornecedor escreverá uma terceira coisa. `finish_reason` continua guardando a string crua para a trilha de auditoria; `truncated` é o mesmo fato no único vocabulário sobre o qual o domínio pode agir.

Traduzir isso na camada de integração é o que a regra 22 pede. Um domínio que comparasse `finish_reason` contra literais de fornecedor quebraria no primeiro provider novo — silenciosamente, porque a comparação simplesmente deixaria de casar.

### 3. Uma explicação truncada é **reportada**, nunca descartada nem remendada

`Explanation.truncated` viaja até a API, ao lado de `unverified_figures`, e o log é ruidoso de propósito.

**Não descartada**, porque o texto está correto até onde vai e levantar exceção gastaria uma das 20 chamadas diárias do free tier para não entregar nada.

**Não remendada**, e essa é a metade que importa mais: nada de reticências, nada de desculpa acrescentada, nada de cortar até o último ponto final. Aparar até a última frase inteira produziria um texto que *parece* completo — exatamente o defeito, agora com uma etapa a mais para escondê-lo.

O leitor precisa distinguir dois jeitos de um texto acabar cedo. Acabar porque os **fatos** acabaram é honesto e completo. Acabar porque o **orçamento** acabou não é nem uma coisa nem outra — e da prosa sozinha os dois são indistinguíveis.

### 4. Pensamento e prosa são contados separadamente, e nunca somados

`Completion` ganha `thinking_tokens`. Somar os dois reportaria uma resposta quatro vezes mais longa que a lida; omitir o pensamento subdeclararia o custo. As duas perguntas são legítimas e cada uma tem seu campo. `None` continua significando *não medido* — o Ollama não reporta raciocínio, e para ele `None` é a resposta verdadeira.

### 5. `AI_MAX_OUTPUT_TOKENS` sobe de 1.024 para 4.096

Com folga deliberada, não no valor medido. O raciocínio **cresce com o espaço que recebe** (981 → 1.383 quando o orçamento dobrou), mas a fração consumida **cai** (99% → 81%), e truncagem só custa alguma coisa quando o orçamento se esgota por inteiro. Dimensionar no limite medido seria dimensionar para o pack que eu testei em vez de para os que existem.

## Consequences

- ✅ O defeito que servia frase cortada como explicação pronta está fechado, com teste de regressão sobre payload capturado.
- ✅ `GeminiProvider` sai do estado **não verificado**: `tests/test_gemini_provider.py`, 11 testes, todos construídos depois da chamada real.
- ✅ A mensagem de erro do orçamento totalmente esgotado nomeia `AI_MAX_OUTPUT_TOKENS`. *"Returned no text"* mandava o operador procurar defeito no prompt, onde ele não estava.
- ⚠️ **`Explanation.truncated` é aditivo no contrato da API** e tem default `False`. Nenhum cliente existente quebra; o frontend ainda não desenha o rótulo, porque explicação não tem tela (a W12 é backend-only por decisão, e o roadmap põe IA em tela mais adiante).
- ⚠️ **O `OllamaProvider` continua não verificado**, agora com uma suposição a mais e nomeada: `done_reason == "length"`. Não há servidor Ollama nesta máquina, então **nenhum teste de regressão foi escrito para ele** — a mesma disciplina que produziu este ADR. A lacuna está registrada no docstring do módulo.
- ⚠️ **A chave é free tier: 20 requisições/dia** para `gemini-3.7-flash` (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`), e o modelo devolve 503 `"high demand"` com frequência. Isso muda o custo de cada chamada desperdiçada, que é parte do argumento do item 3.

## Alternatives considered

**Levantar `AIResponseBlockedError` na truncagem.** Rejeitada por dois motivos: o nome mente (nada foi bloqueado), e joga fora uma resposta parcialmente útil **e** a chamada metered que a produziu. É também o inverso exato do princípio que a [ADR-030](ADR-030-fact-pack-and-the-hallucination-guard.md) fixou — *um filtro com falso positivo é um filtro que alguém desliga*.

**Aparar o texto até a última frase completa.** Rejeitada, e é a alternativa mais tentadora. Produz saída bonita e é a que mais esconde: o leitor recebe um texto que termina bem e não tem como saber que o argumento parou no meio. Esconder a truncagem com mais processamento é pior que a truncagem.

**Só subir `AI_MAX_OUTPUT_TOKENS` e não tratar o caso.** Rejeitada: reduz a probabilidade e não fecha nada. O tamanho do pack varia com a carteira, o raciocínio varia com a pergunta, e um orçamento maior é justamente o que faz o modelo pensar mais. Um caso que fica raro sem ficar impossível é um caso que ninguém vai reconhecer quando aparecer.

**Limitar o raciocínio por `thinkingConfig`.** Testada ao vivo e rejeitada **por medição**: `thinkingBudget: 0` foi aceito com HTTP 200 e **ignorado** — o modelo pensou 398 tokens assim mesmo. `thinkingLevel: "low"` foi igualmente aceito e produziu 436. Um botão que o fornecedor aceita e não honra é pior que botão nenhum: ele documenta uma garantia que não existe.

**Somar pensamento e prosa em `output_tokens`.** Rejeitada: responderia à pergunta de custo e destruiria a de tamanho, e as duas aparecem em auditoria.

## Related

- [ADR-030](ADR-030-fact-pack-and-the-hallucination-guard.md) — de onde vem *reportado, nunca rejeitado*.
- [ADR-029](ADR-029-ai-provider-speaks-rest.md) — por que este módulo fala REST e conhece o formato do fio.
- `docs/planning/IMPLEMENTATION_GUIDE.md` — o procedimento de verificação contra resposta real, e a W06-003 que o originou.
