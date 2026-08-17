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
- Integração de market data abstraída (`MarketDataProvider` / `BrapiProvider`), ingestão de histórico diário OHLCV com cache local e validação de qualidade de dados.

### Em desenvolvimento
- Nada em progresso. Wave 05 fechada; Wave 06 (Fundamental Data) ainda não iniciada.

### Planejado (não existe código)
Fundamentos → Quant Engine (retornos/risco) → Benchmarks (CDI/IBOV/IPCA) → Recommendation Engine → Rebalanceamento → Dashboard → AI Engine → Backtesting/Walk-forward → Day Trade (intraday, setups, risco, paper trading) → Observabilidade/Segurança/CI-CD/Deploy.
Ver [../planning/ROADMAP.md](../planning/ROADMAP.md).

## Stack real (o que está de fato em uso)

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2.0 (`Mapped[]`), Alembic, httpx, PyJWT, bcrypt |
| Banco | PostgreSQL 16 (produção/dev via Docker); SQLite in-memory **apenas** em testes |
| Testes/Qualidade | pytest, ruff, black |
| Frontend | React 18, TypeScript, Vite 5, Tailwind CSS, lucide-react |
| Infra | Docker + Docker Compose (postgres, backend, frontend) |

Declarados no `pyproject.toml`/`package.json` mas **ainda não importados por nenhum código**: numpy, pandas, scipy, scikit-learn, google-generativeai, react-router-dom, @tanstack/react-query, recharts, zod, clsx, tailwind-merge.

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

Domínios conceituais (AGENTS.md §4), a maioria ainda não construída:
`Market Data → Quant Engine → Portfolio Engine → Recommendation Engine → AI Engine (só explicação)`.

## Documentos-âncora do projeto

- [AGENTS.md](../../AGENTS.md) — contrato técnico, 138 regras numeradas. **Prevalece sobre tudo.**
- [docs/roadmap.md](../roadmap.md) — especificação funcional completa e as 33 waves (documento original, extenso).
- [docs/implementation_prompt.md](../implementation_prompt.md) — protocolo de execução autônoma por task.
