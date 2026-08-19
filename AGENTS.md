# Investment Assistant — Agent Operating Instructions

> Este documento é o contrato técnico e operacional do projeto.
> 
> Todo agente de IA que trabalhar neste repositório DEVE ler e respeitar este arquivo antes de modificar qualquer código.
> 
> Em caso de conflito entre uma instrução deste arquivo e uma solicitação pontual, este arquivo prevalece, exceto quando o usuário explicitamente determinar uma mudança arquitetural.

---

# 1. IDENTIDADE DO PROJETO

## 1.1 Nome

**Investment Assistant**

## 1.2 Objetivo

Construir uma plataforma pessoal de análise e acompanhamento de investimentos com foco inicial no mercado brasileiro, especialmente ativos negociados na B3.

O sistema deve:

- acompanhar uma carteira existente;
    
- permitir cadastrar ativos apenas para acompanhamento;
    
- registrar transações;
    
- acompanhar patrimônio;
    
- acompanhar rentabilidade;
    
- comparar desempenho com benchmarks;
    
- analisar risco;
    
- analisar fundamentos;
    
- analisar diversificação;
    
- considerar perfil de investidor conservador;
    
- considerar horizonte de investimento;
    
- considerar aportes mensais de aproximadamente R$ 1.000;
    
- sugerir possíveis alocações para novos aportes;
    
- explicar as razões das sugestões;
    
- realizar backtesting;
    
- registrar histórico das recomendações;
    
- disponibilizar uma área separada para oportunidades de day trade;
    
- realizar backtesting das estratégias de day trade;
    
- suportar paper trading;
    
- utilizar IA para interpretação e explicação;
    
- utilizar Docker;
    
- possuir migrations versionadas;
    
- possuir testes automatizados;
    
- possuir CI/CD;
    
- ser preparado para deploy em produção.
    

---

# 2. PRINCÍPIO FUNDAMENTAL

Este projeto é um **sistema de análise e pesquisa financeira**.

Ele NÃO deve ser tratado como:

- sistema de promessa de rentabilidade;
    
- sistema de previsão determinística do mercado;
    
- sistema de execução automática de ordens;
    
- consultor financeiro autônomo;
    
- sistema que garante lucro.
    

O sistema deve produzir:

```text
Dados
    ↓
Análises
    ↓
Scores
    ↓
Regras
    ↓
Recomendações
    ↓
Explicações
```

Nunca:

```text
IA
    ↓
"Compre isso"
```

sem evidências quantitativas.

---

# 3. PRINCÍPIO MAIS IMPORTANTE

## A IA NÃO É O MOTOR QUANTITATIVO

A IA deve ser utilizada principalmente para:

- interpretar resultados;
    
- explicar métricas;
    
- resumir informações;
    
- contextualizar riscos;
    
- produzir explicações em linguagem natural;
    
- auxiliar o usuário a entender os dados.
    

A IA NÃO deve ser responsável por:

- calcular Sharpe;
    
- calcular drawdown;
    
- calcular CAGR;
    
- calcular volatilidade;
    
- definir diretamente pesos de carteira;
    
- inventar dados;
    
- decidir operações com base exclusivamente em linguagem natural;
    
- alterar dados quantitativos;
    
- modificar resultados de backtest.
    

Todos os cálculos financeiros devem ser implementados deterministicamente no backend.

---

# 4. PRINCÍPIO DE SEPARAÇÃO DE RESPONSABILIDADES

A arquitetura deve possuir, conceitualmente, os seguintes domínios:

```text
Market Data
    ↓
Quant Engine
    ↓
Portfolio Engine
    ↓
Recommendation Engine

Market Data
    ↓
Intraday Data
    ↓
Day Trade Engine
    ↓
Paper Trading

Recommendation / Quant Results
    ↓
AI Engine
    ↓
Natural Language Explanation
```

Não misturar os domínios sem necessidade.

---

# 5. ARQUITETURA

## 5.1 Stack principal

### Frontend

Em uso hoje:

- React
    
- TypeScript
    
- Vite
    
- Tailwind CSS
    
- lucide-react
    

Declarados no `package.json` e **ainda não importados por código algum** — o frontend é
scaffold (uma página estática, sem rotas e sem estado) até a **W11**, que é a primeira wave
de frontend de verdade:

- React Router (`react-router-dom`)
    
- TanStack Query
    
- Zod
    
- Recharts (a biblioteca de gráficos escolhida)
    
- clsx, tailwind-merge
    

### Backend

- Python
    
- FastAPI
    
- Pydantic
    
- SQLAlchemy
    
- Alembic
    
- httpx
    
- pytest
    

### Quantitative Computing

- NumPy
    
- Pandas
    
- SciPy
    
- scikit-learn
    
- statsmodels quando necessário
    

### Database

- PostgreSQL
    

### Infrastructure

- Docker
    
- Docker Compose
    
- Git
    
- GitHub
    

Previsto e **ainda inexistente** — não há `.github/`, e lint e testes rodam localmente:

- GitHub Actions (**W26**)
    

### AI

A abstração abaixo é a decisão de arquitetura; **ainda não há implementação** — o AI Engine
chega na **W12**.

A integração deve ser abstraída através de:

```python
AIProvider
```

Implementações possíveis:

```text
GeminiProvider
OllamaProvider
```

A implementação concreta pode mudar sem alterar o domínio.

---

# 6. ESTRUTURA DO PROJETO

A estrutura real do repositório é a de baixo. Itens marcados `(previsto)` ainda não
existem e pertencem a waves futuras — o resto está no disco hoje.

```text
investment-assistant/
│
├── AGENTS.md
├── CLAUDE.md                       # protocolo operacional de sessão
├── README.md
├── LICENSE
├── docker-compose.yml
├── .env.example
├── .gitignore
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   └── dependencies.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── logging.py
│   │   │
│   │   ├── domain/                 # schemas Pydantic + service, por área
│   │   │   ├── users/
│   │   │   ├── portfolio/
│   │   │   ├── assets/
│   │   │   ├── market_data/
│   │   │   ├── fundamentals/
│   │   │   ├── benchmarks/
│   │   │   ├── recommendations/
│   │   │   └── daytrade/           (previsto — W15+)
│   │   │
│   │   ├── quant/
│   │   │   ├── returns.py
│   │   │   ├── risk.py
│   │   │   ├── valuation.py        (previsto)
│   │   │   ├── scoring.py          (previsto)
│   │   │   ├── portfolio.py        (previsto)
│   │   │   └── backtesting.py      (previsto — W13)
│   │   │
│   │   ├── integrations/
│   │   │   ├── http.py             # transporte HTTP compartilhado
│   │   │   ├── market_data/
│   │   │   ├── fundamentals/
│   │   │   ├── benchmarks/
│   │   │   ├── intraday/           (previsto — W15)
│   │   │   └── ai/                 (previsto — W12)
│   │   │
│   │   ├── data/
│   │   │   ├── database.py
│   │   │   └── models/
│   │   │
│   │   └── workers/                (previsto — W17, scheduler)
│   │
│   ├── migrations/
│   │   └── versions/
│   │
│   ├── tests/                      # plano, sem subpastas
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── alembic.ini
│
├── frontend/
│   ├── src/
│   │   ├── services/
│   │   ├── components/             (previsto — W11)
│   │   ├── pages/                  (previsto — W11)
│   │   ├── hooks/                  (previsto — W11)
│   │   ├── types/                  (previsto — W11)
│   │   ├── utils/                  (previsto — W11)
│   │   └── layouts/                (previsto — W11)
│   ├── Dockerfile
│   └── package.json
│
└── docs/
    ├── PROJECT_STATUS.md           # ledger detalhado, task-a-task
    ├── roadmap.md                  # especificação funcional, 33 waves
    ├── implementation_prompt.md
    ├── memory/                     # PROJECT_CONTEXT · PROJECT_STATUS · CURRENT_TASK · SESSION_HANDOFF
    ├── architecture/               # SYSTEM_OVERVIEW · BACKEND · FRONTEND · DATABASE · API
    ├── decisions/                  # ADR-001 … ADR-0NN
    ├── planning/                   # ROADMAP · IMPLEMENTATION_GUIDE
    └── history/                    # COMPLETED_TASKS
```

Três ausências são deliberadas, não pendências:

- **`data/repositories/` não existe e não está previsto.** As rotas recebem a `Session`
  do SQLAlchemy por injeção e os services a consomem direto — decisão registrada em
  [ADR-011](docs/decisions/ADR-011-no-repository-layer.md).
- **Não há `CHANGELOG.md` na raiz.** O histórico entregue vive em
  `docs/history/COMPLETED_TASKS.md` (nível wave) e em `docs/PROJECT_STATUS.md`
  (nível task).
- **`tests/` é plano.** As categorias da §67 (unit, integration, regression, e2e) são
  conceituais; nunca foram diretórios.

Não alterar essa estrutura de maneira significativa sem justificativa.

---

# 7. REGRAS DE DESENVOLVIMENTO

## 7.1 Antes de modificar código

Sempre:

1. Ler `AGENTS.md`.
    
2. Ler `docs/memory/PROJECT_STATUS.md` (estado em uma página) e, se precisar de detalhe
   task-a-task, `docs/PROJECT_STATUS.md`.
    
3. Ler documentação relevante em `/docs`.
    
4. Inspecionar o código existente.
    
5. Identificar dependências da alteração.
    
6. Verificar testes existentes.
    
7. Planejar a alteração.
    

Não começar a editar arquivos imediatamente.

---

# 8. NÃO REIMPLEMENTAR O QUE JÁ EXISTE

Antes de criar:

- service;
    
- repository;
    
- utility;
    
- hook;
    
- componente;
    
- cálculo;
    
- integração;
    

procurar se já existe implementação equivalente.

Evitar:

```text
calculateReturn()
calculatePortfolioReturn()
calculateInvestmentReturn()
getReturn()
```

quando uma abstração comum poderia existir.

Preferir:

```text
quant/returns.py
```

com funções claramente definidas.

---

# 9. PRINCÍPIO DE MUDANÇA MÍNIMA

Ao implementar uma task:

- alterar somente o necessário;
    
- evitar refatorações não solicitadas;
    
- não modificar arquitetura sem necessidade;
    
- não atualizar dependências aleatoriamente;
    
- não alterar configurações de produção sem motivo.
    

Se uma mudança estrutural for necessária:

1. explicar;
    
2. documentar;
    
3. implementar;
    
4. testar.
    

---

# 10. TYPESCRIPT

Utilizar TypeScript estritamente.

Evitar:

```typescript
any
```

quando houver alternativa.

Preferir:

```typescript
unknown
```

e validação explícita.

Todos os contratos de API devem possuir tipos.

Utilizar Zod quando apropriado para validar dados externos.

---

# 11. PYTHON

Seguir:

- type hints;
    
- funções pequenas;
    
- classes somente quando agregarem valor;
    
- tratamento explícito de erros;
    
- logging;
    
- testes.
    

Evitar funções gigantes.

Preferir:

```text
route
service
domain
integration
```

com responsabilidades claras.

Note que **não há camada `repository`** neste projeto: a rota recebe a `Session` do
SQLAlchemy por injeção de dependência e o service a consome direto
([ADR-011](docs/decisions/ADR-011-no-repository-layer.md)).

---

# 12. BANCO DE DADOS

O banco oficial é:

```text
PostgreSQL
```

Não utilizar SQLite como banco principal de produção.

SQLite pode ser utilizado em testes isolados somente quando tecnicamente adequado.

---

# 13. MODELO DE DADOS

As principais entidades são:

```text
users
investor_profiles
portfolios
assets
asset_prices
intraday_prices
fundamentals
financial_indicators
transactions
portfolio_snapshots
recommendations
daytrade_setups
daytrade_results
```

---

# 14. MIGRATIONS

Toda alteração de schema DEVE utilizar Alembic.

Nunca:

- alterar tabela manualmente;
    
- modificar schema sem migration;
    
- apagar migration existente já aplicada;
    
- recriar histórico de migrations.
    

Fluxo:

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

Toda migration deve ser revisada manualmente.

Autogenerate NÃO é considerado infalível.

---

# 15. REGRAS DE MIGRATION

Uma migration deve:

- possuir nome descritivo;
    
- possuir upgrade;
    
- possuir downgrade quando possível;
    
- preservar dados existentes;
    
- evitar operações destrutivas sem necessidade.
    

Exemplo:

```text
001_initial_schema
002_create_assets
003_create_asset_prices
004_create_portfolios
005_create_transactions
006_create_fundamentals
007_create_recommendations
008_create_intraday_prices
009_create_daytrade_setups
```

Nunca apagar migrations antigas para "limpar" o histórico.

---

# 16. TRANSAÇÕES FINANCEIRAS

As posições devem ser derivadas das transações sempre que possível.

Exemplo:

```text
BUY
SELL
DIVIDEND
DEPOSIT
WITHDRAWAL
```

Evitar armazenar simultaneamente:

```text
quantity
average_price
```

como valores independentes sem mecanismo de consistência.

A fonte de verdade deve ser claramente definida.

---

# 17. DINHEIRO E PRECISÃO

Nunca utilizar `float` indiscriminadamente para valores monetários críticos.

Para valores financeiros que exigem precisão decimal, preferir:

```text
Decimal
```

ou tipos `NUMERIC/DECIMAL` no PostgreSQL.

Para cálculos estatísticos onde floating point seja adequado, documentar a decisão.

---

# 18. TIMEZONE

O mercado brasileiro possui regras específicas de horário.

Nunca assumir timezone implicitamente.

Armazenar timestamps de forma consistente.

Preferência:

```text
UTC no banco
timezone explícito na apresentação
```

Conversões devem ser feitas na camada adequada.

---

# 19. MARKET DATA

Os dados de mercado devem ser tratados como dados externos não confiáveis.

Nunca assumir que:

- todos os campos existem;
    
- o preço é válido;
    
- a API sempre responde;
    
- o ticker existe;
    
- não existem gaps;
    
- não existem duplicidades.
    

Sempre validar.

---

# 20. DATA QUALITY

Verificar:

- valores nulos;
    
- preços negativos;
    
- OHLC inválido;
    
- volume inválido;
    
- datas duplicadas;
    
- timestamps duplicados;
    
- gaps;
    
- mudanças de ticker;
    
- dados fora de ordem;
    
- valores absurdos.
    

Exemplo:

```text
low <= open
low <= close
high >= open
high >= close
```

Quando aplicável.

---

# 21. FONTES DE DADOS

A aplicação deve abstrair fornecedores.

Não acoplar o domínio diretamente a uma API.

Preferir:

```text
MarketDataProvider
```

com implementação:

```text
BrapiProvider
```

ou outra fonte.

O domínio deve conhecer:

```text
MarketDataProvider
```

e não:

```text
requests.get("...")
```

espalhado pela aplicação.

---

# 22. API FAILURE

Toda integração externa deve considerar:

- timeout;
    
- retry;
    
- rate limit;
    
- HTTP errors;
    
- resposta incompleta;
    
- resposta inválida;
    
- indisponibilidade.
    

Não utilizar retry infinito.

---

# 23. CACHING

Quando apropriado:

- evitar chamadas repetidas;
    
- respeitar rate limits;
    
- armazenar dados históricos localmente.
    

A API externa não deve ser consultada toda vez que o usuário abre a mesma página.

---

# 24. QUANT ENGINE

Todos os cálculos financeiros devem ficar no Quant Engine.

Exemplos:

```text
returns.py
risk.py
valuation.py
portfolio.py
scoring.py
backtesting.py
```

O frontend nunca deve calcular indicadores financeiros relevantes.

---

# 25. RETORNOS

Implementar separadamente:

```text
daily return
weekly return
monthly return
quarterly return
YTD
annual return
CAGR
```

Documentar exatamente a metodologia utilizada.

---

# 26. RETORNO DA CARTEIRA

Não confundir:

```text
retorno do ativo
```

com:

```text
retorno da carteira
```

e:

```text
variação patrimonial
```

Aportes e retiradas precisam ser tratados corretamente.

Para carteiras com fluxos de caixa, considerar metodologias adequadas como:

- Time-Weighted Return;
    
- Money-Weighted Return / IRR;
    

quando aplicável.

Não chamar simplesmente:

```text
(current_value - initial_value) / initial_value
```

de "rentabilidade da carteira" quando existirem aportes intermediários.

---

# 27. RISCO

Implementar:

```text
volatility
beta
maximum drawdown
Sharpe
Sortino
```

Posteriormente:

```text
VaR
CVaR
```

quando houver justificativa.

Cada métrica deve possuir:

- definição;
    
- fórmula;
    
- periodicidade;
    
- tratamento de dados;
    
- testes.
    

---

# 28. BENCHMARKS

Suportar inicialmente:

```text
CDI
IBOV
IPCA
```

quando dados adequados estiverem disponíveis.

Comparar:

```text
Portfolio vs CDI
Portfolio vs IBOV
Portfolio vs benchmark
```

Não comparar métricas incompatíveis sem normalização.

---

# 29. FUNDAMENTOS

Quando disponíveis, analisar:

```text
P/L
P/VP
EV/EBITDA
ROE
ROIC
Dividend Yield
Payout
Margem líquida
Margem EBITDA
Crescimento de receita
Crescimento de lucro
Dívida/EBITDA
Fluxo de caixa
```

Não utilizar um indicador isoladamente para definir recomendação.

---

# 30. SCORE DE ATIVOS

O score deve ser decomponível.

Exemplo:

```text
Quality Score
Valuation Score
Growth Score
Risk Score
Dividend Score
Portfolio Fit Score
```

Depois:

```text
Final Score
```

A fórmula deve ser explícita e versionada.

Nunca esconder pesos importantes dentro de prompts de IA.

---

# 31. RECOMENDAÇÃO DE CARTEIRA

A pergunta principal do sistema é:

> "Qual novo aporte melhora minha carteira atual?"

Não:

> "Qual ativo possui maior score?"

A recomendação deve considerar:

- carteira atual;
    
- exposição existente;
    
- concentração;
    
- correlação;
    
- risco;
    
- perfil;
    
- horizonte;
    
- aporte disponível;
    
- peso-alvo;
    
- valuation;
    
- qualidade;
    
- crescimento;
    
- liquidez.
    

---

# 32. PERFIL CONSERVADOR

O sistema deve tratar "conservador" como restrição quantitativa.

Exemplos:

- limite por ativo;
    
- limite por setor;
    
- limite de renda variável;
    
- limite de volatilidade;
    
- preferência por liquidez;
    
- diversificação;
    
- menor concentração.
    

Os pesos exatos devem ser configuráveis.

Não assumir que todos os investidores conservadores possuem exatamente a mesma alocação.

---

# 33. APORTE MENSAL

O sistema deve suportar:

```text
monthly_contribution
```

Valor inicial esperado:

```text
R$ 1.000
```

Mas esse valor deve ser configurável.

O algoritmo deve responder:

> "Dado meu patrimônio atual e R$ 1.000 de novo aporte, onde esse dinheiro melhora a carteira?"

---

# 34. REBALANCEAMENTO

Calcular:

```text
current_weight
target_weight
weight_gap
```

Exemplo:

```text
Atual: 4%
Alvo: 8%
Gap: +4 p.p.
```

A recomendação deve priorizar ativos que:

- estejam abaixo do peso-alvo;
    
- sejam adequados ao perfil;
    
- tenham score aceitável;
    
- reduzam concentração;
    
- respeitem limites.
    

---

# 35. HORIZONTES

As recomendações devem possuir:

```text
SHORT_TERM
MEDIUM_TERM
LONG_TERM
```

Não utilizar o mesmo modelo indiscriminadamente para todos os horizontes.

---

# 36. EXPLICABILIDADE

Toda recomendação deve explicar:

```text
Por que?
```

Exemplo:

```text
O ativo foi selecionado porque:

1. está abaixo do peso-alvo;
2. possui score de qualidade elevado;
3. melhora a diversificação;
4. possui valuation compatível;
5. apresenta risco compatível com o perfil.
```

A explicação deve ser derivada dos dados reais.

---

# 37. CONFIDENCE SCORE

Diferenciar:

```text
score
```

de:

```text
confidence
```

Score:

> qualidade/adequação do ativo.

Confidence:

> qualidade e quantidade das evidências disponíveis.

Não apresentar "82% de confiança" como se fosse probabilidade de lucro.

Preferir linguagem como:

```text
Quantitative confidence: 82/100
```

com explicação.

---

# 38. HISTÓRICO DAS RECOMENDAÇÕES

Toda recomendação deve ser armazenada.

Registrar:

```text
timestamp
asset
score
confidence
suggested_amount
target_weight
horizon
reason
```

Isso permitirá avaliar posteriormente:

```text
O sistema estava certo?
```

---

# 39. NÃO APAGAR RECOMENDAÇÕES ANTIGAS

Recomendações são dados históricos.

Não sobrescrever silenciosamente.

Uma nova recomendação deve gerar novo registro ou versionamento apropriado.

---

# 40. AI ENGINE

A IA deve ficar atrás de uma interface:

```python
class AIProvider:
    ...
```

Nunca acoplar o domínio diretamente ao Gemini.

---

# 41. GEMINI

O Gemini pode ser utilizado para:

- explicações;
    
- resumo;
    
- interpretação;
    
- análise textual;
    
- contextualização.
    

Nunca enviar para o modelo:

- credenciais;
    
- tokens;
    
- dados desnecessários;
    
- informações sensíveis.
    

---

# 42. OLLAMA

O sistema deve poder utilizar um modelo local posteriormente.

A arquitetura não deve depender exclusivamente de uma API proprietária.

---

# 43. PROMPTS

Prompts importantes devem ficar versionados.

Exemplo:

```text
prompts/
    portfolio_explanation_v1.txt
    risk_explanation_v1.txt
```

Não esconder lógica de negócio importante dentro de prompts.

---

# 44. IA E ALUCINAÇÃO

A IA nunca deve inventar:

- preço;
    
- indicador;
    
- balanço;
    
- resultado;
    
- notícia;
    
- recomendação quantitativa.
    

Se não houver dado:

```text
Data unavailable.
```

Nunca preencher com informação inventada.

---

# 45. DAY TRADE

O módulo de day trade é separado do módulo de investimento de longo prazo.

Não compartilhar cegamente:

```text
scores
```

ou:

```text
estratégias
```

entre eles.

---

# 46. OBJETIVO DO DAY TRADE

O objetivo não é encontrar:

```text
lucro máximo
```

O objetivo é encontrar:

```text
setups com expectativa matemática potencialmente positiva
+
risco controlado
+
liquidez adequada
```

---

# 47. DADOS INTRADAY

Preferir:

```text
1m
5m
15m
```

quando disponíveis.

Dados diários não devem ser utilizados como se fossem intraday.

---

# 48. INDICADORES INICIAIS

Utilizar inicialmente:

```text
VWAP
EMA 9
EMA 21
RSI
ATR
Relative Volume
High of Day
Low of Day
Support
Resistance
```

Não adicionar dezenas de indicadores sem evidência de benefício.

---

# 49. SETUPS

Começar com:

```text
Breakout
Pullback
VWAP
```

Reversão somente posteriormente.

Cada estratégia deve ser implementada separadamente.

Exemplo:

```python
evaluate_breakout()
evaluate_pullback()
evaluate_vwap()
```

---

# 50. REGRAS DE SETUP

Toda estratégia deve possuir:

```text
Entry
Stop
Target
Invalidation
Risk
Reward
Filters
```

Não criar estratégias vagas.

---

# 51. DAY TRADE SCORE

Exemplo conceitual:

```text
Liquidity              20%
Trend                  20%
Volume                 20%
Risk/Reward             20%
Confirmation            20%
```

Os pesos devem ser configuráveis.

O score não significa:

```text
80% de chance de ganhar
```

---

# 52. DAY TRADE RISK ENGINE

Parâmetros:

```text
capital
risk_per_trade
daily_loss_limit
max_trades
entry
stop
target
fees
slippage
```

Calcular:

```text
max_position_size
risk_amount
potential_loss
potential_profit
risk_reward
```

---

# 53. RISCO POR OPERAÇÃO

Exemplo:

```text
Capital = R$10.000
Risk = 0,5%
```

Então:

```text
Max risk = R$50
```

Se:

```text
Entry = R$20
Stop = R$19,50
```

Risco por unidade:

```text
R$0,50
```

Quantidade teórica:

```text
50 / 0,50 = 100
```

Sempre considerar:

- lote;
    
- custos;
    
- slippage;
    
- regras do ativo.
    

---

# 54. DAILY CIRCUIT BREAKER

Se:

```text
daily_loss >= daily_loss_limit
```

o sistema deve:

```text
bloquear novos setups/operações
```

No paper trading.

Nunca incentivar:

```text
recuperar prejuízo
```

---

# 55. DAY TRADE UI

A página:

```text
/daytrade
```

deve mostrar:

```text
Ativo
Setup
Direção
Entrada
Stop
Alvo
R/R
Score
Volume
VWAP
Tendência
Horário
Status
```

---

# 56. LINGUAGEM DA INTERFACE

Preferir:

```text
Setup detectado
Oportunidade potencial
Sinal quantitativo
```

Evitar:

```text
Lucro garantido
Operação certa
Compra obrigatória
Vai subir
Vai cair
```

---

# 57. BACKTESTING

Todo algoritmo quantitativo importante deve ser testável historicamente.

Backtester deve suportar:

- preço;
    
- volume;
    
- custos;
    
- slippage;
    
- entrada;
    
- saída;
    
- stop;
    
- target;
    
- posição;
    
- capital;
    
- drawdown.
    

---

# 58. LOOK-AHEAD BIAS

CRÍTICO.

Nunca utilizar informação que não estava disponível no momento da decisão.

Exemplo proibido:

```text
Usar fechamento do dia
para decidir uma entrada
no início daquele mesmo dia.
```

Todos os indicadores devem respeitar a ordem temporal.

---

# 59. SURVIVORSHIP BIAS

Quando possível, backtests devem considerar ativos que existiam no período analisado, inclusive casos de:

- exclusão;
    
- mudança;
    
- fusão;
    
- falência;
    
- alteração de ticker.
    

Não utilizar apenas os vencedores atuais para reconstruir o passado.

---

# 60. OVERFITTING

Não ajustar parâmetros até obter o melhor resultado histórico sem validação.

Evitar:

```text
RSI = 31.7
EMA = 13.42
Volume = 1.83
```

sem justificativa.

Preferir parâmetros simples e robustos.

---

# 61. OUT-OF-SAMPLE

Todo modelo relevante deve possuir:

```text
Training
Validation
Test
```

ou metodologia equivalente.

Nunca utilizar todo o histórico para calibrar e validar simultaneamente.

---

# 62. WALK-FORWARD

Quando aplicável:

```text
Train
→ Validate
→ Test
→ Move window
→ Repeat
```

A estratégia deve ser avaliada quanto à estabilidade.

---

# 63. MÉTRICAS DO BACKTEST

Não usar somente:

```text
win rate
```

Medir:

```text
Total Return
CAGR
Volatility
Maximum Drawdown
Sharpe
Sortino
Win Rate
Average Win
Average Loss
Profit Factor
Expectancy
Number of Trades
Fees
Slippage
```

---

# 64. EXPECTANCY

Utilizar:

```text
Expectancy =
(win_rate × average_win)
-
(loss_rate × average_loss)
```

Uma estratégia pode possuir win rate inferior a 50% e ainda ser positiva.

---

# 65. PAPER TRADING

Antes de qualquer integração com corretora:

```text
Signal
 ↓
Simulated Entry
 ↓
Monitoring
 ↓
Simulated Exit
 ↓
Result
```

Nenhuma ordem real deve ser enviada.

---

# 66. CORRETORA

Não implementar integração de ordens reais na V1.

Se futuramente solicitada:

1. discutir riscos;
    
2. criar sandbox;
    
3. implementar paper trading;
    
4. implementar limites;
    
5. exigir confirmação explícita;
    
6. nunca ativar automaticamente.
    

---

# 67. TESTES

Todo código novo relevante deve possuir testes.

Categorias:

```text
unit
integration
regression
e2e
```

São categorias **conceituais**, não diretórios: `backend/tests/` é plano, um arquivo
`test_<área>.py` por área.

---

# 68. TESTES QUANTITATIVOS

Para indicadores financeiros, criar casos conhecidos.

Exemplo:

```text
Entrada conhecida
→ Resultado esperado conhecido
```

Não testar apenas:

```text
function does not crash
```

Testar valores.

---

# 69. REGRESSION TESTS

Backtests importantes devem possuir datasets fixos.

Se uma alteração mudar:

```text
profit factor
CAGR
drawdown
```

o agente deve investigar.

Nunca atualizar o snapshot simplesmente para fazer o teste passar.

---

# 70. API

Endpoints devem seguir REST quando adequado.

Exemplos:

```text
GET /api/assets
GET /api/assets/{ticker}
GET /api/portfolio
POST /api/portfolio/transactions
GET /api/recommendations
GET /api/daytrade/setups
GET /api/daytrade/history
```

---

# 71. CONTRATOS DE API

Mudanças breaking devem ser evitadas.

Se necessárias:

- documentar;
    
- atualizar frontend;
    
- atualizar testes;
    
- atualizar documentação.
    

---

# 72. ERROS DA API

Retornar respostas consistentes.

Exemplo:

```json
{
  "error": {
    "code": "ASSET_NOT_FOUND",
    "message": "Asset was not found."
  }
}
```

Não retornar stack traces em produção.

---

# 73. FRONTEND

O frontend deve ser responsável por:

- apresentação;
    
- interação;
    
- filtros;
    
- navegação;
    
- visualização.
    

Não deve possuir lógica financeira crítica.

---

# 74. GRÁFICOS

Os gráficos devem deixar claro:

- período;
    
- unidade;
    
- benchmark;
    
- moeda;
    
- fonte;
    
- atualização.
    

Não criar gráficos visualmente bonitos mas financeiramente ambíguos.

---

# 75. PERFORMANCE

Não otimizar prematuramente.

Primeiro:

```text
correctness
```

Depois:

```text
performance
```

Quando necessário:

- indexes;
    
- caching;
    
- pagination;
    
- batch processing;
    
- async;
    
- background workers.
    

---

# 76. WORKERS

Processos pesados devem poder executar em background:

```text
market data ingestion
fundamental ingestion
intraday ingestion
recommendation calculation
backtesting
```

Não bloquear request HTTP longo sem necessidade.

---

# 77. LOGGING

Logs estruturados devem conter:

```text
timestamp
level
service
request_id
operation
error
```

Nunca logar:

- passwords;
    
- tokens;
    
- secrets;
    
- dados sensíveis.
    

---

# 78. OBSERVABILIDADE

Adicionar:

```text
/health
/ready
```

Verificar:

- backend;
    
- database;
    
- workers;
    
- integrações essenciais.
    

---

# 79. CONFIGURAÇÃO

Todas as configurações externas devem utilizar environment variables.

Exemplo:

```text
DATABASE_URL
JWT_SECRET
GEMINI_API_KEY
MARKET_DATA_API_KEY
```

Nunca hardcodar secrets.

---

# 80. .ENV

Nunca commitar:

```text
.env
```

Commitar:

```text
.env.example
```

com placeholders.

---

# 81. DOCKER

O projeto deve ser executável via:

```bash
docker compose up
```

Desenvolvimento deve ser reproduzível.

---

# 82. DOCKER SERVICES

Inicialmente:

```text
frontend
backend
postgres
```

Posteriormente:

```text
worker
scheduler
nginx
```

quando necessário.

---

# 83. DOCKERFILE

Preferir:

- imagens oficiais;
    
- versões fixadas quando apropriado;
    
- builds pequenos;
    
- multi-stage build para frontend;
    
- usuário não-root em produção quando possível.
    

---

# 84. CI/CD

Pipeline mínimo:

```text
Lint
 ↓
Tests
 ↓
Build
 ↓
Docker Build
 ↓
Security Checks
 ↓
Deploy
```

Não permitir merge com testes críticos quebrados.

---

# 85. GIT

Branches:

```text
main
develop
feature/*
fix/*
refactor/*
```

---

# 86. COMMITS

Preferir Conventional Commits:

```text
feat:
fix:
refactor:
test:
docs:
chore:
perf:
```

Exemplo:

```text
feat: add portfolio transaction endpoint
```

---

# 87. PULL REQUEST

Toda PR relevante deve explicar:

```text
What changed?
Why?
How tested?
Potential risks?
```

---

# 88. SEGURANÇA

Implementar:

- password hashing;
    
- JWT;
    
- CORS;
    
- rate limiting;
    
- validation;
    
- secure headers;
    
- parameterized queries;
    
- secret management.
    

---

# 89. AUTENTICAÇÃO

Nunca armazenar senha em texto puro.

Preferir algoritmo de hashing apropriado.

Nunca armazenar:

```text
password
```

diretamente.

---

# 90. DADOS DO USUÁRIO

O sistema deve coletar somente os dados necessários.

Não armazenar:

- credenciais bancárias;
    
- senhas de corretora;
    
- cartões;
    
- informações desnecessárias.
    

---

# 91. IA E PRIVACIDADE

Enviar para a IA somente o mínimo necessário.

Quando possível:

```text
dados agregados
```

em vez de dados pessoais.

---

# 92. DEPENDÊNCIAS

Antes de adicionar uma biblioteca:

1. verificar se já existe solução;
    
2. avaliar manutenção;
    
3. avaliar segurança;
    
4. avaliar tamanho;
    
5. justificar necessidade.
    

Não adicionar dependência para tarefas triviais.

---

# 93. DOCUMENTAÇÃO

Atualizar documentação quando houver alteração significativa.

Arquivos principais:

```text
README.md
CLAUDE.md                          # protocolo de sessão
docs/memory/PROJECT_CONTEXT.md     # o que é o projeto
docs/memory/PROJECT_STATUS.md      # onde o projeto está
docs/memory/CURRENT_TASK.md        # o que fazer agora
docs/memory/SESSION_HANDOFF.md     # como retomar a sessão
docs/PROJECT_STATUS.md             # ledger detalhado task-a-task
docs/architecture/SYSTEM_OVERVIEW.md
docs/architecture/BACKEND.md
docs/architecture/FRONTEND.md
docs/architecture/DATABASE.md
docs/architecture/API.md
docs/decisions/ADR-XXX-*.md
docs/planning/ROADMAP.md
docs/planning/IMPLEMENTATION_GUIDE.md
docs/history/COMPLETED_TASKS.md
```

Os documentos por engine previstos originalmente (`quant-engine.md`,
`recommendation-engine.md`, `daytrade-engine.md`, `backtesting.md`, `deployment.md`)
**não existem**; o conteúdo equivalente está em `docs/architecture/BACKEND.md` e nos ADRs.

---

# 94. PROJECT_STATUS.md

O ledger detalhado é `docs/PROJECT_STATUS.md` (task-a-task) e o resumo em uma página é
`docs/memory/PROJECT_STATUS.md`. Não existe `PROJECT_STATUS.md` na raiz.

Sempre atualizar após concluir uma Wave ou Task significativa.

Formato:

```markdown
# Project Status

## Current Wave

Wave X

## Completed

- [x] Task A
- [x] Task B

## In Progress

- [ ] Task C

## Blocked

None

## Next

Task D
```

---

# 95. ROADMAP

O roadmap oficial está em:

```text
docs/roadmap.md
```

Waves principais:

```text
W0  Product
W1  Foundation
W2  Database
W3  Authentication
W4  Portfolio
W5  Market Data
W6  Fundamentals
W7  Quant Engine
W8  Benchmarks
W9  Recommendation Engine
W10 Rebalancing
W11 Dashboard
W12 AI
W13 Backtesting
W14 Walk-forward
W15 Intraday Data
W16 Day Trade Engine
W17 Day Trade Risk
W18 Day Trade Dashboard
W19 Day Trade Backtesting
W20 Paper Trading
W21 Tests
W22 Advanced Frontend
W23 Observability
W24 Security
W25 Docker Production
W26 CI/CD
W27 Deploy
W28 Production Migrations
W29 Backup
W30 Full Paper Trading
W31 Validation
W32 V1.0
```

---

# 96. ORDEM DE IMPLEMENTAÇÃO

Não pular diretamente para IA ou Day Trade.

Ordem recomendada:

```text
Foundation
 ↓
Database
 ↓
Portfolio
 ↓
Market Data
 ↓
Quant
 ↓
Benchmark
 ↓
Recommendation
 ↓
Backtesting
 ↓
AI
 ↓
Intraday
 ↓
Day Trade
 ↓
Paper Trading
 ↓
Production
```

---

# 97. MVP

O MVP deve conter:

```text
Authentication
Portfolio
Asset tracking
Market data
Returns
Risk metrics
Benchmark
Basic recommendation engine
Dashboard
```

Não é necessário implementar Day Trade antes do MVP.

---

# 98. V1

A V1 deve conter:

```text
MVP
+
Fundamentals
+
Advanced recommendation
+
Backtesting
+
AI explanation
+
Day Trade
+
Paper Trading
+
CI/CD
+
Deploy
```

---

# 99. NÃO IMPLEMENTAR AINDA

Não implementar sem solicitação explícita:

- execução real de ordens;
    
- integração direta com corretora;
    
- alavancagem automática;
    
- opções complexas;
    
- derivativos complexos;
    
- trading de alta frequência;
    
- modelos de deep learning complexos;
    
- reinforcement learning;
    
- previsão de preço como objetivo principal.
    

---

# 100. MACHINE LEARNING

Machine Learning só deve ser adicionado quando:

1. houver dataset suficiente;
    
2. houver baseline quantitativo;
    
3. houver hipótese clara;
    
4. houver validação;
    
5. houver explicação do benefício.
    

Não utilizar ML apenas porque "IA é melhor".

---

# 101. REGRA CONTRA COMPLEXIDADE DESNECESSÁRIA

Preferir:

```text
Simple + Testable + Explainable
```

a:

```text
Complex + Black Box
```

---

# 102. RECOMENDAÇÕES E RESPONSABILIDADE

Toda recomendação deve possuir:

```text
Score
Evidence
Risk
Horizon
Reason
Data timestamp
```

Não produzir recomendação sem dados suficientes.

---

# 103. DADOS DESATUALIZADOS

Se os dados forem antigos:

```text
Data delayed / stale
```

deve ser exibido.

Nunca fingir que os dados são em tempo real.

---

# 104. DAY TRADE — DADOS ATRASADOS

Se o provedor possuir delay:

```text
REAL-TIME
```

não deve ser exibido.

Usar:

```text
Delayed
```

ou:

```text
Last updated: HH:MM
```

---

# 105. ASSERTIVIDADE

Nunca medir o sistema apenas por:

```text
"quantas recomendações acertaram?"
```

Para carteira:

- retorno;
    
- risco;
    
- drawdown;
    
- benchmark;
    
- consistência.
    

Para day trade:

- expectancy;
    
- profit factor;
    
- drawdown;
    
- retorno líquido;
    
- estabilidade.
    

---

# 106. RESULTADOS NEGATIVOS

Se uma estratégia não funcionar:

```text
documentar
```

Não esconder.

Estratégias ruins são informação útil.

---

# 107. BACKTEST HONESTO

Sempre considerar:

```text
fees
slippage
liquidity
```

quando os dados permitirem.

Um backtest sem custos não deve ser apresentado como resultado final.

---

# 108. DATA LEAKAGE

É proibido utilizar dados futuros.

Exemplos proibidos:

```text
future close
future fundamental
future ranking
future survivorship universe
```

antes da data em que aquela informação estaria disponível.

---

# 109. FUNDAMENTOS HISTÓRICOS

Indicadores fundamentalistas devem respeitar a data em que estavam disponíveis ao mercado quando utilizados em backtests.

Não utilizar silenciosamente:

```text
valor atual
```

para simular uma decisão histórica.

---

# 110. VERSIONAMENTO DE ESTRATÉGIAS

Estratégias devem possuir versão.

Exemplo:

```text
VWAP_PULLBACK_V1
VWAP_PULLBACK_V2
```

Se a regra mudar significativamente, criar nova versão.

Não alterar uma estratégia histórica sem versionamento.

---

# 111. VERSIONAMENTO DO SCORE

O score também deve ser versionado.

Exemplo:

```text
PORTFOLIO_SCORE_V1
PORTFOLIO_SCORE_V2
```

Isso permite entender por que recomendações antigas foram diferentes.

---

# 112. AUDITORIA

Quando uma recomendação for gerada, deve ser possível reconstruir:

```text
Quais dados foram utilizados?
Qual versão do algoritmo?
Qual score?
Qual configuração?
Qual timestamp?
```

---

# 113. DETERMINISMO

O motor quantitativo deve produzir o mesmo resultado para a mesma entrada.

Exceções devem ser explicitamente documentadas.

A IA pode ser não determinística na linguagem, mas não deve alterar o resultado quantitativo.

---

# 114. FRONTEND — RECOMENDAÇÕES

Mostrar algo semelhante a:

```text
PRÓXIMO APORTE

R$ 500
Renda fixa

R$ 300
ETF internacional

R$ 200
Ativo X

Por quê?

- melhora diversificação;
- está abaixo do peso-alvo;
- score quantitativo adequado;
- risco compatível;
- valuation aceitável.
```

---

# 115. FRONTEND — DAY TRADE

Mostrar:

```text
OPORTUNIDADES

PETR4
LONG
Pullback
Score 84

Entry
Stop
Target
R/R

Reasons:
✓ Trend
✓ Volume
✓ VWAP
✓ Liquidity
```

---

# 116. ALERTAS

Futuramente permitir:

- novo setup;
    
- alteração de score;
    
- ativo atingindo preço;
    
- carteira fora do target;
    
- limite de risco.
    

Não enviar spam.

---

# 117. SCHEDULER

Tarefas periódicas:

```text
Daily:
market data
portfolio snapshot
recommendations

Intraday:
intraday ingestion
setup detection

Weekly:
fundamental update
analysis

Monthly:
portfolio report
```

Horários devem ser configuráveis.

---

# 118. PRODUÇÃO

Produção deve possuir:

```text
HTTPS
Database backup
Monitoring
Logs
Migrations
Health checks
CI/CD
```

---

# 119. DEPLOY

Frontend pode ser hospedado separadamente.

Backend pode utilizar:

```text
Azure
Render
Railway
VM
```

Database preferencialmente:

```text
Managed PostgreSQL
```

---

# 120. BACKUP

Deve existir:

```text
daily backup
retention policy
restore procedure
```

Um backup que nunca foi restaurado/testado não deve ser considerado confiável.

---

# 121. REGRAS PARA O AGENTE

O agente DEVE:

- ler o contexto antes de editar;
    
- preservar arquitetura;
    
- escrever testes;
    
- executar testes;
    
- atualizar documentação;
    
- atualizar status;
    
- explicar mudanças significativas;
    
- evitar dados inventados;
    
- evitar decisões financeiras arbitrárias;
    
- respeitar migrations;
    
- respeitar versionamento.
    

---

# 122. O AGENTE NÃO DEVE

Nunca:

- inventar dados de mercado;
    
- inventar resultados de backtest;
    
- afirmar que uma estratégia é lucrativa sem teste;
    
- remover testes para fazer build passar;
    
- desabilitar validações;
    
- commitar secrets;
    
- alterar migrations aplicadas;
    
- ignorar erros;
    
- usar look-ahead bias;
    
- mascarar dados ausentes;
    
- colocar lógica financeira crítica no frontend;
    
- usar IA como substituto do Quant Engine;
    
- implementar ordens reais sem solicitação explícita.
    

---

# 123. QUANDO HOUVER ERRO

Não simplesmente contornar.

Processo:

```text
Reproduzir
 ↓
Identificar causa
 ↓
Corrigir causa
 ↓
Criar teste de regressão
 ↓
Executar suite
 ↓
Documentar se necessário
```

---

# 124. QUANDO NÃO SOUBER

Não inventar.

Se uma informação externa for necessária:

```text
identificar dependência
consultar documentação oficial quando possível
```

Se ainda houver incerteza:

```text
explicar a incerteza
```

---

# 125. QUANDO O USUÁRIO PEDIR ALGO QUE QUEBRE A ARQUITETURA

Não implementar imediatamente.

Primeiro:

```text
explicar impacto
```

Depois:

```text
propor alternativa
```

Se o usuário confirmar a mudança:

```text
documentar decisão
implementar
```

---

# 126. DECISION LOG

Decisões arquiteturais importantes devem ser registradas.

Criar futuramente:

```text
docs/decisions/
```

Exemplo:

```text
ADR-001-postgresql.md
ADR-002-ai-provider-abstraction.md
ADR-003-portfolio-return-methodology.md
ADR-004-daytrade-paper-trading.md
```

---

# 127. DEFINITION OF DONE

Uma task só está concluída quando:

```text
[ ] Código implementado
[ ] Testes criados
[ ] Testes executados
[ ] Lint executado
[ ] Build executado quando aplicável
[ ] Documentação atualizada
[ ] Migration criada quando necessário
[ ] docs/PROJECT_STATUS.md atualizado
```

---

# 128. DEFINITION OF DONE — QUANT

Além disso:

```text
[ ] Fórmula documentada
[ ] Caso conhecido testado
[ ] Edge cases testados
[ ] Dados faltantes tratados
[ ] Periodicidade documentada
[ ] Timezone considerado
```

---

# 129. DEFINITION OF DONE — DAY TRADE

Além disso:

```text
[ ] Entry definido
[ ] Stop definido
[ ] Target definido
[ ] Risk definido
[ ] Fees considerados
[ ] Slippage considerado quando possível
[ ] Backtest disponível
[ ] Look-ahead auditado
[ ] Paper trading disponível
```

---

# 130. DEFINITION OF DONE — RECOMMENDATION

Além disso:

```text
[ ] Score determinístico
[ ] Evidências armazenadas
[ ] Risk assessment
[ ] Horizon
[ ] Portfolio fit
[ ] Reason
[ ] Timestamp
[ ] Versão do algoritmo
```

---

# 131. FLUXO PADRÃO DE EXECUÇÃO DO AGENTE

Para cada tarefa:

```text
1. Read AGENTS.md
2. Read docs/memory/PROJECT_STATUS.md
3. Read relevant docs
4. Inspect repository
5. Identify existing implementation
6. Plan
7. Implement
8. Run tests
9. Fix failures
10. Run lint
11. Review changes
12. Update docs
13. Update docs/PROJECT_STATUS.md
14. Summarize
```

---

# 132. FORMATO DE RESPOSTA DO AGENTE

Ao terminar uma task, responder:

```text
## Implemented

- item 1
- item 2

## Tests

- pytest: PASS
- frontend tests: PASS
- lint: PASS

## Files Changed

- file 1
- file 2

## Migration

Created:
migration_name

## Notes

Any relevant observation.

## Next Recommended Task

Task X
```

---

# 133. MODO DE TRABALHO POR WAVE

Não implementar múltiplas Waves simultaneamente sem autorização.

Exemplo:

```text
Current:
Wave 7

Allowed:
Wave 7 tasks

Not allowed:
Wave 12 AI
Wave 16 Day Trade
```

a menos que explicitamente solicitado.

---

# 134. REGRA DE FOCO

Se uma task revelar outro problema:

```text
não expandir automaticamente o escopo
```

Registrar:

```text
TODO
```

e continuar a task atual.

Exceção:

Se o problema impedir a conclusão da task, corrigir.

---

# 135. REGRA DE QUALIDADE

Preferir:

```text
small
testable
typed
documented
deterministic
```

a:

```text
fast
clever
complex
```

---

# 136. PRINCÍPIO FINAL

Este projeto deve evoluir da seguinte maneira:

```text
Correctness
     ↓
Tests
     ↓
Quantitative Validation
     ↓
Explainability
     ↓
Performance
     ↓
Automation
```

Nunca inverter essa ordem.

---

# 137. OBJETIVO FINAL

O produto final deve permitir ao usuário responder:

### Carteira

> "Como está minha carteira?"

### Performance

> "Estou superando ou perdendo para o CDI?"

### Risco

> "Quanto risco estou assumindo?"

### Alocação

> "Onde deveria colocar meu próximo R$ 1.000?"

### Explicação

> "Por que o sistema está sugerindo isso?"

### Day Trade

> "Existem setups quantitativamente interessantes hoje?"

### Validação

> "Essa estratégia realmente funcionou historicamente?"

### Confiabilidade

> "O resultado continua funcionando fora da amostra?"

---

# 138. PRINCÍPIO ABSOLUTO

**O agente deve otimizar para a qualidade da decisão, não para a quantidade de código produzido.**

Código sofisticado não é sucesso.

Uma interface bonita não é sucesso.

Uma IA que produz textos convincentes não é sucesso.

O sucesso é:

```text
Dados confiáveis
+
Cálculos corretos
+
Algoritmos testáveis
+
Backtests honestos
+
Risco controlado
+
Recomendações explicáveis
+
Sistema reproduzível
```

Esse é o padrão de qualidade esperado para todo o projeto.

# WAVE EXECUTION PROTOCOL

O projeto é desenvolvido através de waves sequenciais.

Antes de iniciar qualquer trabalho:

1. Ler `docs/memory/PROJECT_STATUS.md` e `docs/memory/CURRENT_TASK.md`.
    
2. Identificar a wave atual.
    
3. Ler a wave em `docs/roadmap.md` (especificação funcional) e o histórico dela em
   `docs/PROJECT_STATUS.md`. **Não existe `docs/waves/`** — as waves nunca tiveram
   arquivo próprio.
    
4. Verificar o estado real do código.
    
5. Nunca assumir que uma task está concluída apenas porque existe documentação sobre ela.
    

## Regra de Escopo

O agente deve trabalhar somente na wave atual, exceto quando uma dependência técnica mínima for necessária para desbloqueá-la.

Não implementar funcionalidades de waves futuras antecipadamente.

## Task Completion

Uma task somente pode ser marcada como:

```text
[x]
```

quando:

- o código estiver implementado;
    
- o código estiver funcionando;
    
- os testes relevantes estiverem passando;
    
- não houver erro conhecido relacionado à task.
    

## Após Cada Task

Atualizar:

```text
docs/PROJECT_STATUS.md
docs/memory/PROJECT_STATUS.md
docs/memory/CURRENT_TASK.md
```

quando a alteração representar progresso relevante.

## Após Concluir a Wave

Executar:

```text
lint
tests
build
```

quando aplicável.

Depois:

1. atualizar `docs/history/COMPLETED_TASKS.md` (fechamento da wave);
    
2. atualizar `docs/PROJECT_STATUS.md` e `docs/memory/PROJECT_STATUS.md`;
    
3. registrar problemas encontrados;
    
4. registrar decisões arquiteturais;
    
5. identificar dependências da próxima wave.
    

## Não Mascarar Problemas

Nunca:

- remover testes para fazer a build passar;
    
- ignorar erros;
    
- comentar código quebrado;
    
- utilizar `any` para esconder problemas de TypeScript;
    
- desabilitar lint sem justificativa;
    
- mockar uma funcionalidade que deveria ser real apenas para marcar uma task como concluída.
    

## Mudanças Fora do Escopo

Se durante uma wave surgir uma necessidade pertencente a uma wave futura:

não implementar a funcionalidade completa.

Registrar em:

```text
docs/PROJECT_STATUS.md
```

como:

```text
Future Work
```

e continuar a wave atual.

## Definition of Done

Uma wave somente pode ser marcada como:

```text
🟢 Completed
```

quando todas as tasks obrigatórias estiverem concluídas e os critérios de validação forem atendidos.

Se existir um bloqueio:

```text
🔴 Blocked
```

Se houver implementação mas ainda depender de revisão:

```text
⚠️ Needs Review
```

Nunca marcar uma wave como concluída apenas porque o código "parece funcionar".