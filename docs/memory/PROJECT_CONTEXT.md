# Project Context — Investment Assistant

## Propósito

Investidor pessoa física, perfil conservador, mercado brasileiro (B3), aportes mensais de ~R$ 1.000.
O problema: **não há como saber, com evidência quantitativa, onde o próximo aporte melhora a carteira** — nem se a carteira atual está batendo o CDI, nem quanto risco ela carrega.

Planilhas não respondem isso. Ferramentas comerciais respondem com caixa-preta.

## Objetivo principal

Um sistema de **análise e pesquisa financeira** que produz:

```
Dados → Análises → Scores → Regras → Recomendações → Explicações
```

Nunca `IA → "compre isso"`. Todo número é calculado deterministicamente no backend; a IA apenas traduz números em linguagem natural.

O produto final deve responder: *Como está minha carteira? Estou batendo o CDI? Quanto risco assumo? Onde colocar o próximo R$ 1.000? Por quê? Isso funcionou historicamente?*

**Não é**: promessa de rentabilidade, previsão de mercado, execução de ordens, consultor autônomo.

## Principais capacidades

### Implementado
- Autenticação de usuários (registro, login, JWT, rota protegida).
- Cadastro de ativos para acompanhamento (watch-only, sem corretora).
- CRUD de carteiras, escopadas por usuário.
- Ledger de transações (`BUY`, `SELL`, `DIVIDEND`, `DEPOSIT`, `WITHDRAWAL`).
- Motor de posições consolidadas derivado do ledger (quantidade, preço médio, P&L realizado, dividendos) — determinístico, custo médio móvel.
- Integração de market data abstraída, com **duas fontes que respondem perguntas diferentes**: o fornecedor (`MarketDataProvider` / `BrapiProvider`) cota ao vivo e ajusta, mas serve ~63 pregões no plano gratuito; a **série COTAHIST da B3** (`DailyHistoryProvider` / `B3CotahistProvider`) é aberta, sem cota, e vai décadas atrás. Ingestão diária idempotente com cache local e validação de qualidade.
- Ingestão de demonstrativos financeiros anuais (`FundamentalsProvider` / `BrapiFundamentalsProvider`), com validação de qualidade e política point-in-time.
- Indicadores fundamentalistas derivados: as 10 fórmulas estão implementadas e testadas, e **as 10 têm insumo real**. `pe`/`pb` existem no banco desde a ingestão do COTAHIST (PETR4: P/L 12,74 e P/VP 1,27 em 2024) e o `dy` — o último que faltava — desde a EVENTS-001 (0,22 em 2024; 0,70 em 2022). O caminho foi de **5 `None` → 1 → nenhum**; ver Known Issues em [PROJECT_STATUS.md](PROJECT_STATUS.md).
- **Quant Engine** puro e determinístico: retorno (diário a anual, YTD, CAGR) e risco (volatilidade, max drawdown, beta, Sharpe, Sortino). Sem I/O, inteiramente em `Decimal`. Desde a EVENTS-003 as métricas de risco **têm insumo real** — PETR4 mede volatilidade de 41,8% e drawdown de -63,4% (a COVID) sobre seis anos de série ajustada.
- **Benchmarks**: CDI, IPCA e Selic pelo Banco Central (SGS, aberto e sem cota) e IBOV pelo provedor de market data, atrás de interface abstrata. Ingestão idempotente, com rejeição de período ainda não encerrado.
- **Comparativo carteira × benchmark**: a carteira vira um índice **time-weighted** (valor de cota) derivado do ledger, o que neutraliza aportes e a torna comparável a um índice. Responde "estou batendo o CDI?" com retorno, excesso, volatilidade, drawdown, beta, Sharpe e Sortino.

- **Demonstrativos financeiros pelos dados abertos da CVM** — a peça entregue ao regulador, aberta e sem cota — com a Brapi fazendo a ponte ticker→CNPJ que a CVM não faz. Fontes compostas: um período vem inteiro de uma fonte só, nunca campo a campo.
- **Sub-scores de ativo decomponíveis** (Quality, Valuation, Growth, Risk, Diversification), relativos à carteira, com fórmula versionada e **ausência de primeira classe**: pilar sem dado é ausente, nunca estimado, e o score reporta que fração da fórmula ele cobre.

- **Alocação do aporte mensal** — a resposta a "onde colocar o próximo R$ 1.000". Ordena por **faixa de cobertura antes do score**, porque ordenar por score puro favorece sistematicamente quem tem menos dado; respeita tetos por ativo e por setor lidos das próprias escalas do score; todo limite é configurável; e cada exclusão e cada corte de valor vêm com motivo nomeado. Nada é gravado — o plano é derivado, como as posições.

- **Quando um papel foi ex, dito pela própria bolsa.** O arquivo de fim de dia marca a sessão
  em que o papel passou a negociar sem um direito, e isso é lido como **observação, não
  interpretação**: data e natureza (dividendo, JCP, bonificação/desdobramento, grupamento,
  subscrição), **nunca magnitude** — o arquivo registra que houve distribuição e jamais o
  tamanho dela. A detecção é pelo contador de distribuição do papel, não pelo marcador, que é
  uma janela de exibição de ~8 pregões e não um evento.

- **Preço não ajustado é armazenado como não ajustado.** `close` é o que o mercado imprimiu;
  `adjusted_close` é o preço de retorno total, e **`NULL` significa "ninguém calculou ajuste para
  esta linha"** — nunca um valor copiado do `close`. Um único ponto de passagem garante que linha
  sem ajuste não entre em série de retorno
  ([ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md)).

- **A série de retorno total, e a regra que decide se ela pode existir.** A **magnitude** de cada
  evento — reais por ação num provento, fator num desdobramento — vem do serviço aberto de
  eventos da própria B3, e `adjusted_close` é derivado do preço bruto já armazenado. Só que ele é
  derivado **apenas onde o ajuste é completo**: toda sessão que o contador da bolsa marcou ex
  precisa de uma ação dimensionada, senão a série para ali. Um ajuste feito com parte dos eventos
  não é uma série mais curta, é uma **errada e plausível**. Medido: PETR4 com 1.495 de 1.495
  pregões ajustados e a pior sessão ajustada idêntica à crua; ITUB4 corretamente truncada por um
  evento que a B3 não reporta
  ([ADR-026](../decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md)).

- **Para onde a carteira deveria ir, e o que fazer com o aporte para chegar lá.** O peso-alvo
  sai do **mérito** — o score sem o pilar que lê a própria carteira —, porque um alvo feito do
  `final_score` **recua conforme a carteira se aproxima dele** (medido: PETR4 escorrega de 76,72
  para 65,47 só por ser detida até 20%, com os quatro pilares de mérito constantes). Concentração
  não some: vira **teto**, que é onde ela não se auto-referencia
  ([ADR-027](../decisions/ADR-027-target-weight-comes-from-merit.md)).

  O plano que fecha os gaps **nunca vende** — corrige por diluição, com o aporte mensal — e
  raciocina sobre a carteira que o aporte **cria**, não sobre a de hoje. As duas leituras podem
  discordar sobre o mesmo ativo, de propósito
  ([ADR-028](../decisions/ADR-028-rebalancing-is-cash-flow-only.md)).

- **Valor de mercado, e a evolução da carteira no tempo.** `quantity × close` — nunca o preço
  ajustado, que é preço de retorno total e valorizaria uma posição de 2020 por uma fração do que
  as ações renderiam. Ativo sem preço deixa a **linha** ausente, não o total, e o total diz o que
  cobre (`valued_market_value`, `unvalued_positions`). A evolução vem em **duas curvas**:
  patrimônio em BRL com a linha de aporte por baixo, e o índice **time-weighted** recortado à
  janela que compartilha com o benchmark.

- **Uma interface web de verdade** (desde a W11): Dashboard, Carteira, Ativos e Ativo, sobre
  rotas, react-query e um cliente tipado que **valida toda resposta com `zod`**. Zero aritmética
  no cliente (regra 73). Ausência é desenhada como ausência, cobertura parcial vem rotulada, e
  todo gráfico declara período, unidade, moeda, benchmark, fonte e atualização (regra 74).

- **A camada que explica, e que é impedida de calcular.** A IA recebe um **fact pack** —
  lista fechada de valores já computados, cada um com rótulo, unidade, a string **já
  renderizada** e o endpoint de origem — e nunca uma série, um componente ou uma linha de
  banco. Não há o que calcular, e arredondar (que também é calcular) é feito no backend,
  com o espelho exato do formatador do frontend: o texto e o painel citam a **mesma
  string**. Depois da geração, todo número do texto é confrontado com esse conjunto
  fechado, e o que não casar volta em `unverified_figures` — **reportado, nunca
  rejeitado**, porque um filtro com falso positivo é um filtro que alguém desliga
  ([ADR-030](../decisions/ADR-030-fact-pack-and-the-hallucination-guard.md)). Três
  perguntas têm explicação hoje: *estou batendo o CDI?*, *por que o aporte vai para esses
  ativos?* e *o que esse score está medindo?*. Gemini ou Ollama local, atrás da mesma
  interface — ou nenhum dos dois, que é um deployment suportado.

- **A estratégia medida contra o passado, sem deixá-la enxergar o futuro.** O backtest não
  testa *uma* estratégia: replaya **a** estratégia — `allocate_contribution`, a mesma função pura
  que `/contribution-plan` chama hoje. E a saída da simulação são linhas de `Transaction`, então
  `compute_positions`, `value_series` e `performance_index` medem um backtest com **exatamente** o
  código que mede a carteira do investidor; uma segunda contabilidade seria um segundo conjunto de
  bugs. Três formas de olhar o futuro ficam **fora de alcance**, não desencorajadas: a decisão só
  recebe os fechamentos da própria sessão e preenche na seguinte; um demonstrativo só é legível
  três meses depois do fim do período, que é o prazo da CVM
  ([ADR-031](../decisions/ADR-031-a-statement-is-readable-only-after-the-filing-deadline.md)); e a
  janela para onde a série de retorno total para, porque sessão marcada ex sem ação dimensionada é
  provento que a simulação não sabe pagar
  ([ADR-032](../decisions/ADR-032-the-backtest-stops-where-the-total-return-series-stops.md)).
  Custo é modelado e **slippage é medido** — o intervalo entre decidir e preencher, somado do que
  aconteceu, em vez de uma taxa inventada.

### Em desenvolvimento
- **Nenhuma wave em andamento.** A próxima é a **Wave 14 — Walk-Forward Validation**. Ver
  [CURRENT_TASK.md](CURRENT_TASK.md), que também lista a verificação pendente da W12.

### Planejado (não existe código)
Walk-forward → Day Trade (intraday, setups, risco, paper trading) → Observabilidade/Segurança/CI-CD/Deploy.
Ver [../planning/ROADMAP.md](../planning/ROADMAP.md).

As capacidades acima estão **expostas em tela** desde a W11. O que continua sem interface: **backtesting e IA, que existem no backend e não em tela** (as duas waves são backend-only por decisão; o roadmap põe `/backtests` na W22), e day trade, que ainda não existe em lugar nenhum.

## Stack real (o que está de fato em uso)

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2.0 (`Mapped[]`), Alembic, httpx, PyJWT, bcrypt |
| Banco | PostgreSQL 16 (produção/dev via Docker); SQLite in-memory **apenas** em testes |
| Testes/Qualidade | pytest, ruff, black |
| Frontend | React 18, TypeScript, Vite 5, Tailwind CSS, lucide-react, react-router-dom, @tanstack/react-query, recharts, zod, clsx, tailwind-merge |
| Infra | Docker + Docker Compose (postgres, backend, frontend) |

Declarados no `pyproject.toml` mas **ainda não importados por nenhum código**: numpy, pandas, scipy, scikit-learn. As seis do frontend que estavam nessa lista entraram em uso na W11.

⚠️ `google-generativeai` **saiu da lista porque saiu do projeto** (W12): estava declarado desde a W00, nunca foi importado, nem estava instalado no venv, e é o SDK que o Google descontinuou em favor de `google-genai`. A IA fala REST pelo mesmo transporte compartilhado de todas as outras integrações ([ADR-029](../decisions/ADR-029-ai-provider-speaks-rest.md)). **A W12 não adicionou nenhuma dependência.**

⚠️ A expectativa de que numpy/pandas/scipy entrariam na Wave 07 **foi revogada, não adiada**: levantando operação por operação, `Decimal` cobre todas as métricas de risco, e o determinismo (regra 113) é argumento para preferi-lo quando é grátis. Ver o adendo ao [ADR-017](../decisions/ADR-017-annualisation-and-numeric-type.md). A pergunta só volta se uma wave precisar de álgebra matricial de verdade (matriz de covariância, Markowitz).

## Arquitetura geral

```
Frontend (React/Vite)
        ↓  REST /api/v1
Backend FastAPI
   ├── api/routes      → HTTP, auth, tradução de erros
   ├── domain/<área>   → schemas Pydantic + service (regra de negócio)
   ├── integrations/   → provedores externos atrás de interface abstrata (inclusive IA)
   └── data/models     → SQLAlchemy 2.0
        ↓
PostgreSQL  ←  Alembic migrations
```

Domínios conceituais (AGENTS.md §4):
`Market Data → Quant Engine → Portfolio Engine → Recommendation Engine → AI Engine (só explicação)`.
Os cinco existem desde a W12; desde a W13 há um sexto, o **Backtesting Engine**, que não é uma nova contabilidade — é o replay que consome os outros.

## Documentos-âncora do projeto

- [AGENTS.md](../../AGENTS.md) — contrato técnico, 138 regras numeradas. **Prevalece sobre tudo.**
- [docs/roadmap.md](../roadmap.md) — especificação funcional completa e as 33 waves (documento original, extenso).
- [docs/implementation_prompt.md](../implementation_prompt.md) — protocolo de execução autônoma por task.
