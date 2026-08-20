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
- **Quant Engine** puro e determinístico: retorno (diário a anual, YTD, CAGR) e risco (volatilidade, max drawdown, beta, Sharpe, Sortino). Sem I/O, inteiramente em `Decimal`.
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
  `adjusted_close` é o preço de retorno total, e **`NULL` significa "esta fonte não calcula
  ajuste"** — nunca um valor copiado do `close`. Um único ponto de passagem garante que linha sem
  ajuste não entre em série de retorno. É o que permite ter décadas de preço aberto sem
  contaminar volatilidade, drawdown e beta com desdobramentos
  ([ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md)).

### Em desenvolvimento
- **Wave EVENTS — eventos societários e proventos**, iniciada em 2026-08-19. Duas tasks
  entregues: os **proventos por exercício** vêm da DMPL da CVM (EVENTS-001, que fechou o `dy` —
  os 10 indicadores passaram a ter valor real), e a **data e a natureza dos eventos
  societários** vêm do arquivo de fim de dia da B3 (EVENTS-002). Falta a **EVENTS-003**: a série
  de retorno total, que é o que destrava o pilar de Risco. Ver
  [CURRENT_TASK.md](CURRENT_TASK.md).

### Planejado (não existe código)
Rebalanceamento → Dashboard → AI Engine → Backtesting/Walk-forward → Day Trade (intraday, setups, risco, paper trading) → Observabilidade/Segurança/CI-CD/Deploy.
Ver [../planning/ROADMAP.md](../planning/ROADMAP.md).

**O frontend continua sendo apenas scaffold** — nenhuma dessas capacidades está exposta em tela. A primeira wave de frontend real é a W11.

## Stack real (o que está de fato em uso)

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2.0 (`Mapped[]`), Alembic, httpx, PyJWT, bcrypt |
| Banco | PostgreSQL 16 (produção/dev via Docker); SQLite in-memory **apenas** em testes |
| Testes/Qualidade | pytest, ruff, black |
| Frontend | React 18, TypeScript, Vite 5, Tailwind CSS, lucide-react |
| Infra | Docker + Docker Compose (postgres, backend, frontend) |

Declarados no `pyproject.toml`/`package.json` mas **ainda não importados por nenhum código**: numpy, pandas, scipy, scikit-learn, google-generativeai, react-router-dom, @tanstack/react-query, recharts, zod, clsx, tailwind-merge.

⚠️ A expectativa de que numpy/pandas/scipy entrariam na Wave 07 **foi revogada, não adiada**: levantando operação por operação, `Decimal` cobre todas as métricas de risco, e o determinismo (regra 113) é argumento para preferi-lo quando é grátis. Ver o adendo ao [ADR-017](../decisions/ADR-017-annualisation-and-numeric-type.md). A pergunta só volta se uma wave precisar de álgebra matricial de verdade (matriz de covariância, Markowitz).

## Arquitetura geral

```
Frontend (React/Vite)
        ↓  REST /api/v1
Backend FastAPI
   ├── api/routes      → HTTP, auth, tradução de erros
   ├── domain/<área>   → schemas Pydantic + service (regra de negócio)
   ├── integrations/   → provedores externos atrás de interface abstrata
   └── data/models     → SQLAlchemy 2.0
        ↓
PostgreSQL  ←  Alembic migrations
```

Domínios conceituais (AGENTS.md §4):
`Market Data → Quant Engine → Portfolio Engine → Recommendation Engine → AI Engine (só explicação)`.
Os quatro primeiros existem; AI Engine ainda não.

## Documentos-âncora do projeto

- [AGENTS.md](../../AGENTS.md) — contrato técnico, 138 regras numeradas. **Prevalece sobre tudo.**
- [docs/roadmap.md](../roadmap.md) — especificação funcional completa e as 33 waves (documento original, extenso).
- [docs/implementation_prompt.md](../implementation_prompt.md) — protocolo de execução autônoma por task.
