# Session Handoff

## Last Updated

2026-08-18

## Last Completed Work

**Wave 09 em andamento**: duas tasks entregues, e juntas elas destravaram o que estava parado
desde que a Brapi fechou os demonstrativos.

### W09-001 — Motor de sub-scores (`26afb34`)

Cinco pilares — Quality, Valuation, Growth, Risk, Diversification — compostos num score final,
em `app/domain/recommendations/scoring.py`. Puro e determinístico.

- Cada pilar devolve **seus componentes** já na escala 0–100 e os nomes dos insumos que faltaram,
  então "por que isso é 62?" se responde só olhando o resultado (§30).
- Todo limiar é constante nomeada ao lado do motivo de ter aquele valor, e
  `SCORING_FORMULA_VERSION` identifica o conjunto. Nada de peso escondido em prompt de IA.
- **Ausência é resposta de primeira classe**: pilar sem dado é `None`, nunca zero nem 50
  "neutro", e fica **de fora da média** em vez de puxá-la para baixo.
- `compose` renormaliza sobre os pilares que existem e **reporta `coverage`**.
- Score é **relativo à carteira** (§31): Diversification lê a concentração atual.
- `GET /portfolios/{id}/scores`.

### W09-002 — Fonte CVM, com a Brapi fazendo a ponte (`d92b93f`, [ADR-020](../decisions/ADR-020-cvm-primary-fundamentals-source.md))

A ingestão de fundamentals **voltou a funcionar**, de graça e com mais histórico do que o
fornecedor jamais deu.

- `CvmFundamentalsProvider` lê os DFP de dados.cvm.gov.br — a peça entregue ao regulador.
- `CompositeFundamentalsProvider` põe a CVM na frente e a Brapi atrás (BDR, ETF, emissor estrangeiro).
- `assets.cnpj` (migration `006`) + `StoredCnpjResolver`: o CNPJ é resolvido **uma vez**.

## Current State

- `pytest` → **542 passed** (449 → 499 → 542). `ruff`/`black` limpos nos arquivos alterados.
- Wave 09: W09-001 🟢, W09-002 🟢, **W09-003 (alocação) pendente**.
- **PostgreSQL 16 no ar, schema `006`**, com CDI/IPCA/IBOV **e** 6 exercícios de demonstrativos
  e indicadores da PETR4 vindos da CVM.
- Cache da CVM em `var/cvm/` (gitignored), exercícios 2020–2025.

## Important Details

### A fusão das duas APIs, e por que ela não é arbitrária

|  | CVM | Brapi |
|---|---|---|
| conhece ticker | **não** | sim |
| conhece CNPJ | sim | sim |
| entrega demonstrativo | sim, o arquivado | não, saiu do plano |
| cobertura | só companhia aberta brasileira | BDR, ETF, emissor estrangeiro |
| custo | livre, sem cota | cota limitada |

Os arquivos da CVM **não têm coluna de ticker** — só CNPJ. O `summaryProfile` da Brapi
**continuou gratuito** (foram os módulos de demonstrativo que saíram) e traz exatamente esse CNPJ:
`PETR4` → `33000167000101`, verificado ao vivo.

Nenhuma das duas responde "o que a PETR4 reportou" sozinha. **Identidade pelo fornecedor, números
pelo regulador.**

### O que foi recusado, e por quê

**Mesclar campo a campo entre as fontes.** Duas fontes discordam sobre consolidado versus
controladora, sobre o que conta como dívida, sobre qual linha é "receita" num banco. Emendar o
patrimônio de uma no resultado da outra produziria uma linha que **nenhum arquivo jamais
reportou**, e nada a jusante perceberia. Um período vem inteiro de uma fonte só.

**Cair para a outra fonte quando a primeira falha.** "Não tenho esse ativo" é para isso que
existe fallback. Timeout ou payload ilegível é a fonte quebrada, e usar a outra em silêncio
transformaria indisponibilidade em **troca invisível de fonte**.

### Detalhes do DFP que mudam a resposta

- **`net_income` é `3.11.01`, não `3.11`.** O segundo inclui minoritários (R$ 37,0 bi na PETR4
  contra R$ 36,6 bi), e cruzá-lo com patrimônio da controladora infla o ROE pela fatia que o
  acionista não possui. O patrimônio é líquido dos minoritários pela mesma razão. O ROE dá os
  **10,0% publicados**.
- **`ESCALA_MOEDA`** é `MIL` na maioria e `UNIDADE` em 550 de 32.776 linhas. Ignorar subestima
  em mil vezes.
- **`ORDEM_EXERC`**: só `ÚLTIMO`. O `PENÚLTIMO` é a visão reexpressa, e o ano anterior tem o
  arquivo dele.
- **`VERSAO`**: vence a maior. Ler todas dobraria cada número.
- **EBITDA é derivado** (`EBIT + |D&A|`, D&A em `7.04.01` da DVA). Nenhum arquivo reporta EBITDA.
  O valor absoluto é deliberado: D&A chega negativo em 433 empresas e **positivo em 3**.

### A prova de que o desenho da W09-001 estava certo

Medido no banco real, depois de ingerir a CVM: **Quality e Growth foram de ausentes para 97,8 e
76,7**, e a cobertura do score de **40% para 55%** — **sem uma linha alterada em `scoring.py`**.
Era exatamente o que o desenho prometia.

Também saíram do `None`: `ebitda_margin` e `debt_ebitda`. O fornecedor copiava `ebit` no campo de
EBITDA; a CVM permite derivá-lo de verdade.

### Lições de método desta sessão

- **O teste escrito à mão pegou um defeito meu de novo.** Numa escala **invertida**, um P/L
  negativo é aritmeticamente *menor* que um barato, então clampava no extremo **bom** e marcaria
  **100** — uma empresa que deu prejuízo classificada como a mais barata da bolsa. Clamp não
  protege de inversão. Múltiplo não positivo agora é piso explícito.
- **Validar contra número público é mais forte que validar contra schema.** O mapeamento de
  contas foi conferido contra o que a Petrobras publicou, não contra a documentação da CVM: um
  ROE de 10,0% é difícil de acertar por acidente com o campo errado.
- **A API real ensinou o que nenhum mock ensinaria**, de novo: 404 do SGS significando "janela
  vazia", série inexistente devolvendo HTML com HTTP 200, `range` da Brapi limitado a 3 meses, e
  agora o sinal de D&A sendo convenção de apresentação.

## Pending Work

**W09-003 — algoritmo de alocação do aporte mensal.** Ver [CURRENT_TASK.md](CURRENT_TASK.md).

Duas armadilhas já registradas lá: `coverage` **morde na alocação** (ordenar por `final_score` e
distribuir de cima para baixo favorece sistematicamente quem tem menos dado), e "conservador" é
restrição quantitativa com pesos configuráveis (§32), reutilizando os tetos de 20%/40% que o
pilar de Diversification já usa.

**Antes dele, um passo curto de alto retorno**: ações em circulação por período. É o único item
que falta para `pe`/`pb`/`dy`, o dado já está no arquivo que o projeto **já baixa**
(`composicao_capital`), e `IndicatorInputs` **já tem o campo**. Levaria a cobertura de 55% para 75%.

Pendências de fundo, sem mudança: `range` da Brapi limitado a 3 meses (quebra
`sync_daily_history` acima disso e limita a W13); `alembic check` falha por drift;
lint pré-existente; `get_quote()` não exposto; proventos nunca ingeridos;
`npm run lint` quebrado no frontend.

Novas, da fonte CVM: bancos e seguradoras usam plano de contas diferente e merecem conferência
antes de virar score; FII/ETF/BDR não têm DFP e nunca terão; exercício em cache não é rebaixado.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md), `docs/roadmap.md` §21 e `AGENTS.md` §31/§32/§33.
Usar `score_universe` como entrada — a alocação **combina** o que já existe, não recalcula nada.

## Relevant Files

- `backend/app/domain/recommendations/{scoring,service,schemas}.py` — os cinco pilares
- `backend/app/integrations/fundamentals/{cvm,identity,composite}.py` — a fusão das fontes
- `backend/app/domain/fundamentals/identity.py` — memória do CNPJ
- `backend/tests/test_asset_scoring.py` — molde de teste com valores à mão
- `backend/tests/test_cvm_fundamentals_provider.py` — regressão contra o DFP real
- `docs/decisions/ADR-020-cvm-primary-fundamentals-source.md`
