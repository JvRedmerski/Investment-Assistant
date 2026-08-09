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
|  & Recommendations |    | (Pandas/NumPy/TA)  |    | (Gemini / Ollama) |
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

## 🚀 Stack Tecnológica

- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, Lucide React, Recharts.
- **Backend**: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, HTTPX, Pytest.
- **Quant Computing**: NumPy, Pandas, SciPy, scikit-learn.
- **Banco de Dados**: PostgreSQL 16.
- **AI Integration**: Abstração `AIProvider` (`GeminiProvider`, `OllamaProvider`).
- **Containerização & CI/CD**: Docker, Docker Compose, GitHub Actions.

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

---

## 🧪 Testes Automatizados

```bash
# Executar testes unitários e de integração no Backend
cd backend
pytest -v
```

---

## 📄 Documentação e Acompanhamento

- **[PROJECT_STATUS.md](file:///C:/Users/joao/Investment-Assistant/docs/PROJECT_STATUS.md)** — Fonte oficial do progresso das tarefas e estado operacional do projeto.
- **[roadmap.md](file:///C:/Users/joao/Investment-Assistant/docs/roadmap.md)** — Visão completa do ciclo de vida do projeto dividido em 33 Waves (W00 a W32).
- **[AGENTS.md](file:///C:/Users/joao/Investment-Assistant/AGENTS.md)** — Regras técnicas, decisões arquiteturais e contrato dos agentes.

---

## 📜 Licença

Este projeto está licenciado sob a licença MIT - veja o arquivo [LICENSE](file:///C:/Users/joao/Investment-Assistant/LICENSE) para mais detalhes.
