# Backend Architecture

> Camada 2. Leia quando a task tocar o backend.
> Estado em 2026-08-17. Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0.

## Estrutura real

```
backend/
├── app/
│   ├── main.py                 App FastAPI, CORS, exception handler global, registro de routers
│   ├── api/
│   │   ├── dependencies.py     get_current_user · get_{market_data,historical_price,fundamentals,benchmark}_provider
│   │   └── routes/             health · auth · assets · portfolios · benchmarks
│   ├── core/
│   │   ├── config.py           Settings (pydantic-settings, lê .env) → singleton `settings`
│   │   ├── security.py         hash/verify de senha (bcrypt) · create/decode de JWT (PyJWT)
│   │   └── logging.py          setup_logging()
│   ├── domain/                 users · portfolio · assets · market_data · fundamentals · benchmarks · recommendations · ai
│   │   ├── <área>/             schemas.py (Pydantic) + service.py (regra de negócio)
│   │   ├── recommendations/    + scoring.py e allocation.py — puros, no molde do app/quant/
│   │   └── ai/                 facts · formatting · prompting · guard · service + prompts/*.txt (versionados)
│   ├── quant/                  returns.py · risk.py — puro, sem I/O, tudo em Decimal
│   ├── integrations/
│   │   ├── http.py             RetryingJsonClient — transporte compartilhado (retry/throttle)
│   │   ├── market_data/        base · schemas · exceptions · brapi · cotahist · factory · data_quality
│   │   ├── fundamentals/       base · schemas · exceptions · factory · brapi · cvm · identity · composite
│   │   ├── benchmarks/         base · schemas · exceptions · bcb · brapi_index · factory
│   │   └── ai/                 base · schemas · exceptions · gemini · ollama · factory
│   └── data/
│       ├── database.py         engine · SessionLocal · Base · get_db · utc_now
│       └── models/             users · assets · portfolio · fundamentals · benchmarks · recommendations · daytrade
├── migrations/versions/        001_initial_schema … 007_shares_outstanding
├── tests/                      plano, sem subpastas
├── pyproject.toml              deps + config de pytest/ruff
└── alembic.ini
```

**Ainda não existem** (previstos no AGENTS.md §6, waves futuras): `app/workers/` (W17), `app/domain/daytrade/` (W15+), `app/integrations/intraday/` (W15).

**`app/data/repositories/` não existe e não está previsto** — não é pendência: as rotas recebem a `Session` do SQLAlchemy por injeção e os services a consomem direto ([ADR-011](../decisions/ADR-011-no-repository-layer.md)). O AGENTS.md §6 foi corrigido para dizer isso.

### Onde o cálculo mora

`app/quant/` é **puro**: sem I/O, sem relógio, sem banco. Recebe séries e devolve números.
`app/domain/<área>/` é quem carrega dado do banco, monta as séries e chama o `app.quant` —
nunca reimplementa uma fórmula. `benchmarks/comparison.py` é o exemplo canônico: é um módulo
de comparação que **não calcula nada**. Quando um módulo de domínio precisa de uma conta,
a conta pertence ao `app/quant/`, e o módulo de domínio pertence à camada que a alimenta.

O mesmo corte se repete **dentro** de um domínio quando a regra é grande o bastante: em
`recommendations/`, `scoring.py` e `allocation.py` são puros e determinísticos, e `service.py`
só carrega do banco e delega. `allocation.py` importa as constantes de teto direto das escalas
de `scoring.py` em vez de redeclará-las — quando dois módulos precisam do mesmo limiar, um lê
o do outro, para que não exista uma segunda cópia livre para divergir.

Dentro de um domínio, cálculo puro e I/O ficam em arquivos separados — `fundamentals/indicators.py`
(puro) contra `fundamentals/service.py` (I/O); `benchmarks/{series,comparison}.py` e
`portfolio/performance.py` (puros) contra `benchmarks/service.py` (I/O).

## Fluxo de uma requisição

```
HTTP → CORSMiddleware
     → rota (api/routes/*.py)
        ├─ Depends(get_current_user)   → 401 se JWT inválido/expirado/órfão
        ├─ Depends(get_db)             → Session por request, fechada no finally
        ├─ Depends(get_<x>_provider)   → integração externa, fechada no finally
        ├─ Pydantic valida o body      → 422 automático do FastAPI
        ├─ resolve ownership           → 404 se não pertencer ao usuário
        ├─ chama domain/<área>/service.py
        └─ retorna response_model
     → HTTPException?  → handler global em main.py → {"error":{"code","message"}}
```

## Padrões a seguir

### 1. Toda integração externa atrás de uma interface abstrata
`integrations/<área>/base.py` define a ABC; `factory.py` escolhe a implementação a partir de `settings.<X>_PROVIDER`; `dependencies.py` expõe como `Depends`. Domínio e rotas **só** conhecem o tipo abstrato. Testes substituem via `app.dependency_overrides` — nunca mockam `httpx`. (AGENTS.md §21, [ADR-004](../decisions/ADR-004-market-data-provider-abstraction.md))

### Duas fontes de preço, duas interfaces

`market_data/base.py` define **quatro** ABCs, e a separação não é cerimônia: `DailyHistoryProvider`
serve barras diárias fechadas; `MarketDataProvider` herda dela e acrescenta a cotação ao vivo;
`CorporateEventProvider` e `CorporateActionProvider` (abaixo) respondem outras perguntas e não
herdam de nenhuma das duas.

A série COTAHIST da B3 é arquivo de fim de dia — ela **não cota**, e implementar `get_quote` ali
significaria devolver o fechamento de ontem com carimbo de agora. Por isso `B3CotahistProvider`
implementa só a interface estreita, e `sync_daily_history` pede só ela: ingestão precisa de barras
fechadas e de mais nada.

Duas propriedades declaradas pela fonte atravessam o sistema:

- **`reports_adjusted_close`** — decide o que um `adjusted_close` ausente significa. Fornecedor
  que ajusta: "ainda não publicou", a barra é rejeitada e entra completa no sync seguinte
  (ADR-016). Fonte que nunca ajusta: a barra é gravada com `NULL`
  ([ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md)).
- **`source_name`** — gravado em cada linha de `asset_prices`. Com duas fontes na mesma tabela e
  só uma delas ajustando, uma linha que não diz de onde veio não é interpretável.

### A terceira interface: em que pregão o papel foi ex

`CorporateEventProvider` (mesmo `base.py`) é **ortogonal** às duas de preço, e por isso é ABC
separada em vez de método na `DailyHistoryProvider`: fornecedor de cotação não sabe dizer em que
pregão um papel passou a negociar sem um direito, e obrigá-lo a implementar isso o obrigaria a
responder mal. É a mesma razão que partiu as duas primeiras na PRICE-001. Só o
`B3CotahistProvider` a implementa, lendo o **mesmo arquivo já baixado** — nenhuma requisição nova.

O que ela devolve é **data e natureza, nunca magnitude**: o arquivo registra que houve
distribuição e jamais o tamanho dela ([ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md)).

A detecção é pelo **`DISMES`** — o contador de distribuição do próprio papel — e **não** pelo
marcador do `ESPECI`. O marcador é uma janela de exibição de ~8 pregões, não um evento, e ainda
encolhe (`EDJ` → `EJ`) parecendo um evento novo. Medido no arquivo de 2024 inteiro: a BBAS3
exibe `ON  EDJ NM` em 12, 13 e 14/06 enquanto o contador vai **323, 323, 324** — duas
distribuições sob um marcador imóvel. Se for mexer aqui, leia antes o
[ADR-025](../decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md) e o
docstring de `cotahist.py`: eles trazem as medições que sustentam a escolha.

A mesma interface também responde `get_security_identity`: o **ISIN** e a **classe** impressos
nos registros do próprio papel. Estão ali porque é neles que uma ação societária é arquivada — e
porque adivinhar a classe pelo dígito final do ticker funcionaria para PETR4 e falharia para
TAEE11 (`UNT`).

### A quarta interface: quanto o evento valeu

`CorporateActionProvider` carrega o que a terceira se recusa a inventar — a **magnitude**: reais
por ação num provento, ações-depois-por-ação-antes num desdobramento. É a EVENTS-003, e o
[ADR-026](../decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md) traz as
medições inteiras.

Fonte: o serviço aberto de eventos corporativos da própria B3, sem token e sem cota, atrás de
`B3CorporateActionProvider`. **O adaptador é fino de propósito** — é o backend JSON das páginas
da B3, com parâmetros em base64 no *path* e sem contrato publicado, então a interface é a costura:
se o endpoint mudar, quebra um arquivo, e a degradação é para **magnitude ausente** — o estado
anterior a esta task — e nunca para número errado.

Duas armadilhas moram no adaptador e ambas foram medidas antes de virar código:

- **A junção é o ISIN.** A B3 repete um evento de contagem uma vez por ISIN que o emissor já teve;
  o desdobramento 1:2 da BBAS3 chega três vezes. Compor as três dá 2³ = 8,0 contra um degrau real
  de 2,02 — e **todo** desacordo visto na validação era uma potência exata da resposta certa.
- **`factor` significa duas coisas.** Porcentagem em `DESDOBRAMENTO`/`BONIFICACAO`, razão crua em
  `GRUPAMENTO`. E `valueCash` é cotado por `quotedPerShares`, que é 1000 em 332 de 2.305 linhas —
  o mesmo erro de mil vezes que o `FATCOT` e o `ESCALA_MOEDA` já tentaram.

### Onde `adjusted_close` nasce, e a regra que decide se ele pode nascer

`domain/market_data/adjustment.py` é puro e sem I/O: recebe barras, ações e eventos, devolve
números. Ajuste retroativo, do mais novo para o mais antigo — o último fechamento é a verdade e
nunca é tocado.

A aritmética é fácil; a honestidade não. **Uma série ajustada com *parte* das ações não é uma
série de retorno mais curta, é uma errada e plausível.** Então a completude é julgada pelo
**contador da B3**, não pelo serviço de eventos — que demonstravelmente omite: a ITUB4 foi ex em
2025-03-18 com marcador `EB` e degrau de -8,60%, e o serviço não reporta nada ali. Toda sessão
contada precisa de ação dimensionada; a mais recente que não tiver é um piso, e nada antes dela é
ajustável. A lacuna volta **nomeada e datada** na resposta do sync.

A única exceção é o `ATZ` (`CorporateEventKind.NOMINAL_UPDATE`): incremento em que nada sai do
titular, logo não há magnitude a faltar. Sem ela a PETR4 teria 28 de 1.495 pregões ajustáveis.

`domain/market_data/corporate_actions.py` faz a ingestão e resolve a **ex-date**: a B3 publica a
data-com, e o pregão seguinte é procurado no calendário **realmente gravado** para o ativo, não
somando um dia e pulando fim de semana — um feriado poria o ajuste numa data que nunca negociou.
O preenchimento só toca coluna **nula**, pela mesma regra do ADR-024.

### O ponto único da série de retorno

`app/domain/market_data/series.py` é o **único** lugar que transforma linha de `asset_prices` em
`PricePoint`, e ele descarta linha sem `adjusted_close`. Nenhum consumidor lê a coluna direto.

É isso que torna a coluna nula segura: sem esse ponto de passagem, cada chamador teria que lembrar
de filtrar, e esquecer significaria alimentar o `app.quant` com preço bruto — em que um
desdobramento aparece como uma sessão de centenas de por cento. Se você precisar de série de
retorno, chame `adjusted_price_points` / `adjusted_closes_by_asset`; não monte a sua.

A resiliência HTTP não é reescrita por provedor: `integrations/http.py` (`RetryingJsonClient`) concentra timeout, retry limitado, backoff e throttle, recebendo as classes de exceção de cada integração. Um provedor concreto escreve apenas URL e parsing. ([ADR-012](../decisions/ADR-012-shared-http-transport.md))

### A camada que explica, e o que ela é proibida de fazer

`app/domain/ai/` é a Wave 12, e o desenho inteiro dela existe para tornar
*estrutural* uma regra que antes era só uma promessa: a IA não calcula
(§3, §24, [ADR-009](../decisions/ADR-009-quant-deterministic-ai-explains.md)).

O modelo nunca vê o banco, nem uma série, nem os componentes de um score.
Ele vê um **fact pack**: lista fechada e plana de valores já calculados, cada
um com rótulo, unidade, a string **já renderizada** e o endpoint de origem
([ADR-030](../decisions/ADR-030-fact-pack-and-the-hallucination-guard.md)).

| módulo | papel |
|---|---|
| `facts.py` | a cintura estreita — **tudo** que o modelo verá passa por aqui. Um builder por tópico, cada um lendo um objeto de resposta já pronto |
| `formatting.py` | o espelho de `frontend/src/lib/format.ts`. Arredondar é calcular, então quem arredonda é o backend, e arredonda **igual à tela** |
| `prompting.py` | carrega os prompts versionados de `prompts/*.txt` e renderiza o pack em dois blocos rotulados: disponível e indisponível |
| `guard.py` | depois da geração, confronta todo número do texto com o conjunto fechado de figuras que o backend escreveu. O que não casar volta em `unverified_figures` |
| `service.py` | os quatro passos, nesta ordem: pack → prompt → provedor → guard |

Três consequências que valem lembrar antes de mexer:

- **Fato ausente fica no pack**, com traço, sob o cabeçalho que diz o que
  aquele bloco é. Removê-lo deixa o modelo livre para supor que o número não
  importava — e é aí que ele preenche a lacuna (§44).
- **Pack sem nenhum valor não chega ao provedor.** Vira frase fixa, `model:
  "none"`, zero requisição gasta.
- **`key` e `source` não vão no prompt.** Servem ao leitor, viajam na
  `Explanation`, e mandá-los colocaria os dígitos de `/api/v1/portfolios/1`
  na frente de um modelo instruído a citar só o que recebeu (§91).

Tópico novo exige builder novo. Não existe tópico livre, de propósito:
tópico sem builder é prompt sem fatos.

### Uma coluna de demonstrativo nova e o dado que já está gravado

Período gravado é congelado ([ADR-013](../decisions/ADR-013-fundamentals-point-in-time.md)) — o que
protege contra reexpressão silenciosa e, como efeito colateral, deixa **toda coluna nova nascer
vazia** para o que já está no banco. `ebit` (W06-003) e `shares_outstanding` (W09-003) escaparam
disso por acidente de cronologia: chegaram a um banco vazio.

`sync_annual_statements(..., refill=True)` — `?refill=true` na rota — preenche coluna que está
`NULL` e **só** ela; valor presente nunca é tocado, então reexpressão continua sem porta de
entrada ([ADR-024](../decisions/ADR-024-refill-fills-null-columns.md)). A varredura percorre
`REPORTED_FIELD_NAMES`, então uma coluna futura entra sozinha — o que você precisa fazer ao
adicionar uma é **acrescentá-la àquela tupla**, não escrever caminho novo no service.

### 2. Dado externo validado duas vezes
DTO Pydantic na fronteira (tipos/obrigatoriedade) **e** validador de qualidade de domínio (regras de negócio: OHLC coerente, preço positivo, duplicidade). O validador é uma função pura, sem I/O, testada com valores conhecidos. (AGENTS.md §19/§20)

### 3. Falha de integração é explícita e tipada
`integrations/<área>/exceptions.py` define exceções próprias (`TickerNotFoundError`, `MarketDataUnavailableError`, `InvalidMarketDataResponseError`). A rota — e só ela — traduz para HTTP:

| Exceção | HTTP | code |
|---|---|---|
| `TickerNotFoundError` | 404 | `MARKET_DATA_TICKER_NOT_FOUND` |
| `MarketDataUnavailableError` | 503 | `MARKET_DATA_UNAVAILABLE` |
| `InvalidMarketDataResponseError` | 502 | `MARKET_DATA_INVALID_RESPONSE` |
| `FundamentalsNotFoundError` | 404 | `FUNDAMENTALS_NOT_FOUND` |
| `FundamentalsUnavailableError` | 503 | `FUNDAMENTALS_UNAVAILABLE` |
| `InvalidFundamentalsResponseError` | 502 | `FUNDAMENTALS_INVALID_RESPONSE` |

Retry é **limitado** e só para falhas transitórias (timeout, erro de conexão, HTTP 429/5xx) com backoff exponencial; 4xx falha imediatamente. Nunca retry infinito. (AGENTS.md §22)

### 4. Dinheiro é `Decimal`
Colunas monetárias são `NUMERIC(18,6)` (constante `MONEY` em `data/models/portfolio.py` e `assets.py`); schemas usam `Decimal`; cálculos somam `Decimal`, nunca `float`. (AGENTS.md §17, [ADR-003](../decisions/ADR-003-decimal-money.md))

### 5. Timezone explícito
`utc_now()` em `data/database.py` para defaults; `datetime.now(UTC).date()` quando a rota precisa de "hoje". Nunca `datetime.now()` sem tz. (AGENTS.md §18)

### 6. Erro nunca é silenciado
Rejeições de qualidade de dados são logadas (`logger.warning`) e contabilizadas na resposta (`rejected`), não descartadas em silêncio. (AGENTS.md §122)

## Autenticação

- `core/security.py`: `bcrypt` para hash de senha, `PyJWT` HS256 para tokens. Sem passlib, sem python-jose ([ADR-006](../decisions/ADR-006-bcrypt-pyjwt.md)).
- JWT carrega `sub` = user id (string). `decode_access_token` retorna `None` em token inválido/expirado.
- `get_current_user` (em `api/dependencies.py`): decodifica, converte `sub` para int, carrega o `User`; qualquer falha → 401 `INVALID_CREDENTIALS` com header `WWW-Authenticate: Bearer`.
- `POST /auth/refresh` reemite a partir de um access token **ainda válido**; não há refresh token dedicado ([ADR-008](../decisions/ADR-008-refresh-without-refresh-token.md)).
- `OAuth2PasswordBearer` é usado só para o botão *Authorize* do Swagger; a autenticação real é o header Bearer.

## Configuração

Tudo em `core/config.py` (`pydantic-settings`, `env_file=".env"`, `case_sensitive=True`, `extra="ignore"`), exposto como singleton `settings`. Nunca leia `os.environ` diretamente; nunca hardcode secret.

Grupos: app (`APP_NAME`, `APP_ENV`, `API_V1_STR`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`) · banco (`DATABASE_URL`, `POSTGRES_*`) · CORS · market data (`MARKET_DATA_PROVIDER`, `BRAPI_TOKEN`, `BRAPI_BASE_URL`, `MARKET_DATA_TIMEOUT_SECONDS`, `MARKET_DATA_MAX_RETRIES`, `MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS`) · fundamentals (`FUNDAMENTALS_PROVIDER`, `FUNDAMENTALS_TIMEOUT_SECONDS`, `FUNDAMENTALS_MAX_RETRIES`, `FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS` — knobs próprios porque a cadência é diferente, ainda que o fornecedor e o rate limit sejam os mesmos) · IA (`AI_PROVIDER` — `gemini` | `ollama` | `none` —, `GEMINI_API_KEY`, `GEMINI_BASE_URL`, `GEMINI_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `AI_TIMEOUT_SECONDS`, `AI_MAX_RETRIES`, `AI_MIN_REQUEST_INTERVAL_SECONDS`, `AI_TEMPERATURE`, `AI_MAX_OUTPUT_TOKENS`). **Nenhuma dessas pode mudar um número em lugar nenhum** (ADR-009): o pior que um valor errado aqui faz é deixar a explicação indisponível.

## Testes

- `tests/conftest.py`: engine SQLite in-memory único (`StaticPool`), compartilhado pela sessão; `app.dependency_overrides[get_db]`; fixture autouse cria e derruba o schema a cada teste; fixture `client` = `TestClient`.
- Integração externa é substituída por fake via `dependency_overrides` — **nenhum teste toca a rede**. O teste de read-path chega a injetar um provider que lança `AssertionError` se chamado, provando que a leitura não consulta a API.
- Testes de cálculo financeiro usam valores conhecidos, não apenas "não explode" (AGENTS.md §68).
- Para interceptar `time.sleep`/`time.monotonic` do laço de retry, faça patch em `app.integrations.http.time` (não no módulo do provedor).
- Baseline: **140 passed**.

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check <arquivos alterados>
.venv\Scripts\python.exe -m black --check <arquivos alterados>
```

`ruff` está configurado com `line-length = 100`, `ignore = ["B008"]` (falso positivo do `Depends()`), `F821` ignorado em `data/models/*` (referências `Mapped["X"]` resolvidas em runtime) e `UP007/UP035` em `migrations/versions/*` (template do Alembic).

## Pontos de atenção para alterações futuras

- **Não** introduza um segundo padrão de acesso a dados sem antes ler [ADR-011](../decisions/ADR-011-no-repository-layer.md).
- **Não** chame provedor externo fora de um endpoint de sync explícito.
- Ao criar um novo domínio, replique exatamente o par `schemas.py` + `service.py`; o service recebe `Session` como parâmetro, não a cria.
- `main.py` registra o router de health **duas vezes** (em `/` e em `/api/v1`) — intencional: o frontend consome `/api/v1/health` e o Docker healthcheck usa `/health`.
