# Investment Assistant

Plataforma pessoal de análise e acompanhamento de investimentos com foco no mercado brasileiro (B3), quantitativamente orientada e integrada com assistente analítico de IA para explicações em linguagem natural.

---

## 📌 Objetivo do Projeto

Construir um sistema completo de pesquisa e gestão patrimonial para investidores de perfil conservador e moderado, capaz de:
- Acompanhar uma carteira de investimentos existente e registrar transações (compras, vendas, dividendos, aportes).
- Avaliar rentabilidade diária/mensal/anual/CAGR e comparar com benchmarks (**CDI**, **IBOV**, **IPCA**).
- Analisar risco (volatilidade, Beta, Maximum Drawdown, Sharpe, Sortino) e diversificação.
- Sugerir alocações inteligentes para novos aportes mensais (~R$ 1.000) considerando perfil conservador e rebalanceamento.
- Disponibilizar um módulo de **Day Trade** para identificação de setups intraday com rigoroso gerenciamento de risco e paper trading.
- Explicar todas as análises quantitativas em linguagem natural via integração com **IA** (Gemini / Ollama), sem depender da IA para cálculos numéricos.

> ⚠️ Esta é a visão completa do produto, não o estado atual. O que já existe está na
> seção [Estado atual](#-estado-atual).

---

## 🏗 Arquitetura do Sistema

```text
                                  USUÁRIO
                                     |
                                     v
                        +--------------------------+
                        |   Frontend (React + TS)  |
                        +------------+-------------+
                                     |
                                    REST
                                     |
                                     v
                        +--------------------------+
                        |  Backend FastAPI (Python)|
                        +------------+-------------+
                                     |
           +-------------------------+-------------------------+
           |                         |                         |
           v                         v                         v
+--------------------+    +--------------------+    +--------------------+
|  Portfolio Engine  |    |    Quant Engine    |    |     AI Engine      |
|  & Recommendations |    |  (Decimal puro)    |    | (Gemini / Ollama)  |
|                    |    |                    |    |    (previsto)      |
+--------------------+    +--------------------+    +--------------------+
           |                         |                         |
           +-------------------------+-------------------------+
                                     |
                                     v
                        +--------------------------+
                        |    PostgreSQL Database   |
                        +--------------------------+
```

---

## 📊 Estado atual

**10 de 33 waves concluídas (W00–W09).** Fonte da verdade:
[docs/memory/PROJECT_STATUS.md](docs/memory/PROJECT_STATUS.md).

| Área | Estado |
|---|---|
| Backend — auth, carteiras, ledger, posições derivadas | 🟢 implementado |
| Market data (Brapi) e demonstrativos (CVM + Brapi) | 🟢 implementado |
| Quant Engine (retorno e risco) e benchmarks (CDI/IPCA/Selic/IBOV) | 🟢 implementado |
| Sub-scores de ativo e alocação do aporte mensal | 🟢 implementado |
| Rebalanceamento, AI Engine, backtesting, day trade | ⚪ não iniciado |
| **Frontend** | 🟡 **scaffold** — uma página estática de status, sem rotas, sem estado e sem telas de produto. A primeira wave de frontend real é a **W11** |

Suíte do backend: **596 testes passando**.

---

## 🚀 Stack Tecnológica

**Em uso hoje:**

- **Frontend**: React 18, TypeScript, Vite 5, Tailwind CSS, lucide-react.
- **Backend**: Python 3.11+, FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2.0, Alembic, HTTPX, PyJWT, bcrypt, Pytest, ruff, black.
- **Quant Computing**: `decimal.Decimal` da biblioteca padrão — puro e determinístico, sem I/O.
- **Banco de Dados**: PostgreSQL 16 (SQLite in-memory apenas nos testes).
- **Containerização**: Docker, Docker Compose.

**Declarado nos manifestos e ainda não importado por código algum:**

- Frontend: `react-router-dom`, `@tanstack/react-query`, `zod`, `recharts`, `clsx`, `tailwind-merge` — entram na **W11**.
- Backend: `numpy`, `pandas`, `scipy`, `scikit-learn`, `google-generativeai`.
- **AI Integration**: a abstração `AIProvider` (`GeminiProvider`, `OllamaProvider`) é a decisão de arquitetura, **ainda sem implementação** — chega na W12.
- **CI/CD**: não há pipeline; `.github/` não existe. Lint e testes rodam localmente.

> Sobre NumPy/Pandas/SciPy: a expectativa de adotá-los na Wave 07 foi **revogada, não adiada** —
> `Decimal` cobre todas as métricas de retorno e risco com determinismo exato. Ver o adendo ao
> [ADR-017](docs/decisions/ADR-017-annualisation-and-numeric-type.md).

---

## 🛠 Requisitos Pré-requisitos

- **Node.js** >= 18.x
- **Python** >= 3.11
- **Docker** e **Docker Compose**
- **Git**

---

## 🚦 Como Executar o Projeto

### 1. Clonar o repositório e configurar variáveis
```bash
git clone https://github.com/JvRedmerski/Investment-Assistant.git
cd Investment-Assistant
cp .env.example .env
```

### 2. Executar via Docker Compose (Recomendado)
```bash
docker compose up --build
```
Acesse:
- **Frontend**: http://localhost:5173
- **Backend API Docs**: http://localhost:8000/docs
- **PostgreSQL**: `localhost:5432`

---

## 🗄 Banco de Dados & Migrations

O projeto utiliza **Alembic** para versionamento de schema no PostgreSQL:

```bash
# Executar migrations
cd backend
alembic upgrade head

# Criar nova migration
alembic revision --autogenerate -m "descrição da alteração"
```

Rodando **fora** do Docker, o `DATABASE_URL` do `.env` aponta para o host `postgres` da rede
do Compose e precisa ser sobrescrito:

```powershell
cd backend
$env:DATABASE_URL="postgresql://investment_user:investment_pass_dev@localhost:5432/investment_assistant"
.venv\Scripts\python.exe -m alembic upgrade head
```

---

## 🧪 Testes Automatizados

```powershell
# Backend (virtualenv em backend/.venv)
cd backend
.venv\Scripts\python.exe -m pytest -q      # 596 passed
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m black --check .
```

```bash
# Frontend
cd frontend
npm install
npm run lint      # ESLint 10 (flat config) + typescript-eslint + react-hooks
npm run build     # tsc && vite build
```

O frontend ainda não tem testes automatizados.

---

## 📄 Documentação e Acompanhamento

- **[CLAUDE.md](CLAUDE.md)** — Protocolo de sessão para agentes de IA. Ponto de entrada da memória do projeto.
- **[docs/memory/](docs/memory/)** — Memória persistente: contexto, estado atual, tarefa atual e handoff de sessão.
- **[docs/architecture/](docs/architecture/)** — Documentação técnica por área (system overview, backend, frontend, database, API).
- **[docs/decisions/](docs/decisions/)** — Architecture Decision Records.
- **[docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)** — Ledger detalhado do progresso task-a-task.
- **[docs/roadmap.md](docs/roadmap.md)** — Visão completa do ciclo de vida do projeto dividido em 33 Waves (W00 a W32).
- **[AGENTS.md](AGENTS.md)** — Regras técnicas, decisões arquiteturais e contrato dos agentes.

---

## 📜 Licença

Este projeto está licenciado sob a licença MIT - veja o arquivo [LICENSE](LICENSE) para mais detalhes.
