# Investment Assistant — Roadmap Completo

## 1. Visão do projeto

### Objetivo

Construir uma plataforma pessoal de análise de investimentos que:

- permita cadastrar os ativos já existentes na carteira;
- acompanhe preços e indicadores históricos;
- acompanhe rentabilidade diária, mensal, anual e de longo prazo;
- compare a carteira com CDI, IBOV e outros benchmarks;
- analise risco e diversificação;
- considere perfil de investidor conservador;
- considere horizontes de curto, médio e longo prazo;
- considere aporte mensal aproximado de R$ 1.000;
- recomende onde o próximo aporte pode fazer mais sentido;
- explique as razões da recomendação;
- faça backtesting das estratégias;
- mantenha histórico das recomendações;
- possua uma tela separada para **sugestões de day trade**, baseada em sinais objetivos e gerenciamento de risco;
- seja executável localmente com Docker;
- possua migrations, testes, versionamento e CI/CD;
- possa ser publicado em produção.

### Princípio fundamental

O sistema não deve tentar prever o mercado de forma determinística.

A arquitetura deve separar:

1. **Dados** — fatos observados.
2. **Quant Engine** — cálculos matemáticos e estatísticos.
3. **Portfolio Engine** — alocação e recomendações de carteira.
4. **Day Trade Engine** — geração de setups intraday.
5. **AI Engine** — interpretação, contextualização e explicação.
6. **Frontend** — visualização e interação.

A IA não deve ser responsável por calcular indicadores financeiros básicos nem por tomar decisões isoladamente.

---

# 2. Escopo funcional

## 2.1 Carteira

O usuário poderá:

- criar carteira;
- adicionar ativos;
- informar quantidade;
- informar preço médio;
- registrar compras;
- registrar vendas;
- registrar dividendos/proventos;
- registrar aportes;
- acompanhar patrimônio;
- acompanhar rentabilidade;
- acompanhar distribuição da carteira.

O sistema deve permitir cadastrar uma posição apenas para fins de acompanhamento, sem necessidade de integração com corretora.

---

## 2.2 Análise de investimentos

O sistema deverá calcular:

### Retorno

- diário;
- semanal;
- mensal;
- trimestral;
- semestral;
- YTD;
- anual;
- 3 anos;
- 5 anos;
- CAGR.

### Risco

- volatilidade;
- beta;
- maximum drawdown;
- Sharpe;
- Sortino;
- VaR, posteriormente;
- correlação.

### Fundamentalistas

Quando disponíveis:

- P/L;
- P/VP;
- EV/EBITDA;
- ROE;
- ROIC;
- margem líquida;
- margem EBITDA;
- crescimento de receita;
- crescimento de lucro;
- dívida/EBITDA;
- dividend yield;
- payout.

---

# 3. Motor de recomendação de carteira

## Objetivo

O sistema não deve perguntar apenas:

> Qual ativo é melhor?

A pergunta principal deve ser:

> Qual alocação melhora a carteira atual considerando perfil, risco, diversificação, horizonte e aporte disponível?

### Entradas

- carteira atual;
- patrimônio;
- aporte mensal;
- perfil;
- horizonte;
- ativos disponíveis;
- indicadores;
- risco;
- benchmarks;
- pesos-alvo.

### Saída

Exemplo:

```text
Aporte mensal: R$ 1.000

R$ 500 → Renda fixa
R$ 300 → ETF internacional
R$ 200 → ITUB4

Prioridade: alta
Confiança quantitativa: 82/100
```

A recomendação deve sempre possuir explicação e fatores de risco.

---

# 4. Perfil conservador

O perfil conservador deve ser usado como restrição do algoritmo, e não apenas como texto exibido na interface.

Exemplos de restrições:

- limite máximo por ativo;
- limite máximo por setor;
- limite máximo de renda variável;
- limite máximo de volatilidade;
- preferência por liquidez;
- preferência por ativos menos voláteis;
- maior peso estrutural em renda fixa;
- redução de concentração.

Os pesos exatos devem ser configuráveis e posteriormente validados por backtesting.

---

# 5. Day Trade

## 5.1 Objetivo

Adicionar uma tela específica para identificar **possíveis oportunidades de day trade**, sem exigir retornos extraordinários.

O objetivo será encontrar setups com:

- liquidez;
- volatilidade adequada;
- relação risco/retorno aceitável;
- entrada objetiva;
- stop objetivo;
- alvo objetivo;
- volume compatível;
- confirmação por indicadores;
- risco máximo controlado.

A tela não deve simplesmente mostrar "compre agora".

Ela deve apresentar:

> **Setup candidato**

e explicar os critérios que fizeram o ativo aparecer.

---

# 5.2 Universo inicial

Começar com ativos altamente líquidos.

Priorizar:

- ações com alto volume;
- ETFs líquidos;
- contratos futuros líquidos, caso sejam incluídos posteriormente.

Não começar com ativos de baixa liquidez.

---

# 5.3 Dados necessários

Para day trade, dados diários não são suficientes.

Idealmente:

- candles de 1 minuto;
- 5 minutos;
- 15 minutos;
- volume;
- OHLC;
- negócios, quando disponível;
- VWAP;
- máxima/mínima do dia;
- abertura;
- fechamento anterior.

A fonte de dados intraday deve ser avaliada separadamente porque APIs gratuitas frequentemente possuem limitações de atraso, histórico ou frequência.

---

# 5.4 Indicadores iniciais

Não utilizar dezenas de indicadores.

Começar com:

- VWAP;
- EMA 9;
- EMA 21;
- RSI;
- ATR;
- volume relativo;
- máxima/mínima do dia;
- abertura;
- suporte/resistência;
- tendência em timeframe maior.

---

# 5.5 Setups iniciais

Implementar poucos setups e mensurá-los.

### Setup A — Rompimento com volume

Condições possíveis:

```text
Preço rompe resistência
+
volume relativo elevado
+
tendência favorável
+
distância até stop aceitável
```

Saída:

```text
Entrada
Stop
Alvo 1
Alvo 2
Risco/Retorno
```

### Setup B — Pullback em tendência

```text
Tendência definida
+
correção
+
retorno para região relevante
+
confirmação
```

### Setup C — VWAP

```text
Preço acima/abaixo da VWAP
+
tendência
+
volume
+
confirmação de candle
```

### Setup D — Reversão controlada

Só implementar após validar os setups anteriores.

Reversão é mais suscetível a falsos sinais.

---

# 5.6 Score do setup

Cada oportunidade receberá score.

Exemplo:

```text
Liquidez             20%
Tendência             20%
Volume                20%
Risco/Retorno         20%
Confirmação           20%
```

Resultado:

```text
PETR4

Setup: Pullback
Score: 84/100

Entrada: R$ XX,XX
Stop:    R$ XX,XX
Alvo:    R$ XX,XX

Risco/Retorno: 1:2,1

Volume relativo: 1,8x
Tendência: favorável
VWAP: favorável
```

Os valores acima são apenas ilustrativos.

---

# 5.7 Gestão de risco

Essa será uma das partes mais importantes.

O sistema deve permitir definir:

```text
Capital destinado a day trade
Risco máximo por operação
Risco máximo diário
Número máximo de operações
```

Exemplo:

```text
Capital: R$ 10.000
Risco por operação: 0,5%
Risco máximo: R$ 50
```

Se a distância entre entrada e stop for:

```text
R$ 0,50
```

A quantidade máxima teórica será:

```text
R$ 50 / R$ 0,50 = 100 unidades
```

O sistema deve ainda considerar custos, tamanho mínimo de lote e regras específicas do instrumento.

---

# 5.8 Limite de perda diária

Adicionar um "circuit breaker".

Exemplo:

```text
Perda máxima diária: 2%
```

Ao atingir o limite:

```text
DAY TRADE BLOQUEADO
```

O sistema não deve incentivar recuperação de perdas.

---

# 5.9 Day Trade Score ≠ recomendação garantida

A tela deve mostrar:

```text
Oportunidade detectada
```

e não:

```text
Lucro garantido
```

Cada setup deve guardar:

- horário;
- ativo;
- timeframe;
- entrada;
- stop;
- alvo;
- score;
- indicadores;
- resultado posterior.

Isso permite medir a assertividade real.

---

# 5.10 Métricas do Day Trade Engine

Não usar somente "percentual de acerto".

Medir:

- win rate;
- loss rate;
- payoff;
- profit factor;
- expectancy;
- média de ganho;
- média de perda;
- drawdown;
- Sharpe;
- retorno líquido;
- custos;
- slippage;
- quantidade de operações;
- MAE;
- MFE.

### Expectancy

Uma métrica importante:

```text
Expectancy =
(win_rate × average_win)
-
(loss_rate × average_loss)
```

Uma estratégia pode ter win rate inferior a 50% e ainda ser positiva se os ganhos forem maiores que as perdas.

---

# 6. Arquitetura

```text
                           USUÁRIO
                              |
                              v
                    +-------------------+
                    | React + TypeScript|
                    +---------+---------+
                              |
                             REST
                              |
                              v
                    +-------------------+
                    |      FastAPI      |
                    +---------+---------+
                              |
          +-------------------+--------------------+
          |                   |                    |
          v                   v                    v
 +----------------+  +------------------+  +-------------+
 | Portfolio      |  | Quant Engine      |  | AI Engine   |
 | Engine         |  |                  |  |             |
 +----------------+  +------------------+  +-------------+
          |                   |                    |
          +-------------------+--------------------+
                              |
                              v
                    +-------------------+
                    |    PostgreSQL     |
                    +---------+---------+
                              ^
                              |
                    +---------+---------+
                    | Data Workers      |
                    +---------+---------+
                              |
              +---------------+----------------+
              |               |                |
              v               v                v
            BRAPI            CVM        Intraday Provider
```

---

# 7. Stack

## Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- React Router
- TanStack Query
- Zod
- Recharts ou biblioteca equivalente

## Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- httpx
- pytest

## Quant

- NumPy
- Pandas
- SciPy
- scikit-learn
- statsmodels
- biblioteca de otimização de portfólio, se necessária

## Banco

- PostgreSQL

## IA

Abstração:

```text
AIProvider
├── GeminiProvider
└── OllamaProvider
```

Inicialmente:

- Gemini Flash para análise textual;
- Ollama + modelo local como alternativa.

## Infra

- Docker
- Docker Compose
- Git
- GitHub
- GitHub Actions
- Nginx, se necessário
- PostgreSQL gerenciado em produção

---

# 8. Estrutura do repositório

```text
investment-assistant/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   └── dependencies.py
│   │   │
│   │   ├── domain/
│   │   │   ├── users/
│   │   │   ├── portfolio/
│   │   │   ├── assets/
│   │   │   ├── recommendations/
│   │   │   └── daytrade/
│   │   │
│   │   ├── quant/
│   │   │   ├── returns.py
│   │   │   ├── risk.py
│   │   │   ├── valuation.py
│   │   │   ├── scoring.py
│   │   │   ├── backtesting.py
│   │   │   └── daytrade.py
│   │   │
│   │   ├── integrations/
│   │   │   ├── brapi/
│   │   │   ├── cvm/
│   │   │   ├── intraday/
│   │   │   └── ai/
│   │   │
│   │   ├── data/
│   │   │   ├── models/
│   │   │   └── repositories/
│   │   │
│   │   └── workers/
│   │       ├── market_data.py
│   │       ├── fundamentals.py
│   │       ├── intraday.py
│   │       └── recommendations.py
│   │
│   ├── migrations/
│   │   └── versions/
│   │
│   ├── tests/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── alembic.ini
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── types/
│   │   └── utils/
│   ├── Dockerfile
│   └── package.json
│
├── docs/
│   ├── architecture.md
│   ├── database.md
│   ├── api.md
│   ├── quant-engine.md
│   ├── recommendation-engine.md
│   ├── daytrade-engine.md
│   ├── backtesting.md
│   └── deployment.md
│
├── scripts/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
└── LICENSE
```

---

# 9. Banco de dados

## users

```text
id
email
password_hash
created_at
updated_at
```

## investor_profiles

```text
id
user_id
risk_profile
monthly_contribution
created_at
updated_at
```

## portfolios

```text
id
user_id
name
created_at
updated_at
```

## assets

```text
id
ticker
name
asset_type
sector
currency
is_active
created_at
updated_at
```

## asset_prices

```text
id
asset_id
date
open
high
low
close
adjusted_close
volume
source
created_at
```

Constraint:

```text
UNIQUE(asset_id, date)
```

## intraday_prices

```text
id
asset_id
timestamp
timeframe
open
high
low
close
volume
source
created_at
```

Constraint:

```text
UNIQUE(asset_id, timestamp, timeframe)
```

## fundamentals

```text
id
asset_id
reference_date
revenue
ebitda
net_income
equity
debt
cash
free_cash_flow
created_at
```

## financial_indicators

```text
id
asset_id
reference_date
pe
pb
roe
roic
dy
debt_ebitda
net_margin
ebitda_margin
revenue_growth
profit_growth
created_at
```

## transactions

```text
id
portfolio_id
asset_id
type
quantity
price
fees
transaction_date
created_at
```

Tipos:

```text
BUY
SELL
DIVIDEND
DEPOSIT
WITHDRAWAL
```

## portfolio_snapshots

```text
id
portfolio_id
date
total_value
cash_value
return_daily
return_monthly
return_ytd
return_yearly
created_at
```

## recommendations

```text
id
portfolio_id
asset_id
recommendation_type
score
confidence
target_weight
suggested_amount
horizon
reason
created_at
```

## daytrade_setups

```text
id
asset_id
strategy
timeframe
detected_at
entry_price
stop_price
target_price
risk_reward
score
status
reason
created_at
```

## daytrade_results

```text
id
setup_id
exit_price
exit_timestamp
result
pnl
pnl_percent
costs
slippage
created_at
```

---

# 10. Migrations

Usar Alembic.

Fluxo:

```bash
alembic revision --autogenerate -m "create assets"
alembic upgrade head
```

Toda alteração estrutural deve gerar migration.

Nunca depender de alterações manuais em produção.

Exemplo:

```text
001_initial_schema
002_create_assets
003_create_prices
004_create_portfolios
005_create_transactions
006_create_fundamentals
007_create_recommendations
008_create_intraday_prices
009_create_daytrade_setups
```

---

# 11. Git e versionamento

Branches:

```text
main
develop
feature/*
fix/*
refactor/*
```

Exemplos:

```text
feature/portfolio-crud
feature/market-data
feature/daytrade-engine
fix/intraday-import
```

Commits:

```text
feat: add portfolio positions
feat: add intraday candle ingestion
fix: prevent duplicated market prices
refactor: isolate recommendation engine
test: add drawdown tests
docs: document day trade scoring
```

---

# 12. Wave 0 — Especificação

## Objetivo

Definir o produto antes do código.

## Entregáveis

- documento de visão;
- requisitos funcionais;
- requisitos não funcionais;
- arquitetura inicial;
- stack;
- riscos;
- limitações;
- definição de MVP.

## Critério de conclusão

Ser possível explicar o sistema em poucos minutos e saber o que está fora do escopo.

---

# 13. Wave 1 — Foundation

## Implementar

- Git;
- GitHub;
- estrutura de pastas;
- Docker;
- Docker Compose;
- PostgreSQL;
- FastAPI;
- React;
- health check;
- `.env`;
- `.env.example`.

## Teste

```text
docker compose up
```

Deve iniciar:

```text
frontend
backend
postgres
```

---

# 14. Wave 2 — Database

## Implementar

- SQLAlchemy;
- Alembic;
- models;
- migrations;
- repositories;
- seed inicial.

## Testar

- migration limpa;
- migration incremental;
- rollback quando aplicável;
- constraints;
- índices;
- foreign keys.

---

# 15. Wave 3 — Authentication

Implementar:

- cadastro;
- login;
- hash de senha;
- JWT;
- refresh token, se necessário;
- proteção de endpoints;
- logout/invalidação quando aplicável.

---

# 16. Wave 4 — Portfolio

Implementar:

- criação de carteira;
- cadastro de ativos;
- posições;
- transações;
- aportes;
- cálculo do preço médio;
- patrimônio.

### Regra importante

Posições devem ser derivadas das transações sempre que possível.

---

# 17. Wave 5 — Market Data

Implementar:

- integração com provedor;
- busca de cotações;
- histórico;
- dividendos;
- atualização incremental;
- validação;
- retry;
- rate limiting;
- logs.

### Data quality

Detectar:

- preços duplicados;
- datas ausentes;
- valores nulos;
- outliers;
- mudanças de ticker;
- dados inconsistentes.

---

# 18. Wave 6 — Fundamental Data

Integrar dados públicos disponíveis.

Implementar:

- importação;
- normalização;
- versionamento por data de referência;
- indicadores derivados.

Não sobrescrever cegamente valores históricos.

---

# 19. Wave 7 — Quant Engine

Implementar:

### Returns

```text
daily_return
monthly_return
yearly_return
cagr
```

### Risk

```text
volatility
beta
drawdown
sharpe
sortino
```

### Fundamental

```text
valuation
quality
growth
dividends
```

### Portfolio

```text
weights
concentration
correlation
```

Criar testes unitários para cada cálculo.

---

# 20. Wave 8 — Benchmark Engine

Implementar:

- CDI;
- IBOV;
- IPCA;
- outros benchmarks configuráveis.

Comparações:

```text
Portfolio vs CDI
Portfolio vs IBOV
Portfolio vs benchmark escolhido
```

---

# 21. Wave 9 — Portfolio Recommendation Engine

Criar pipeline:

```text
Dados
 ↓
Quality Score
 ↓
Valuation Score
 ↓
Growth Score
 ↓
Risk Score
 ↓
Diversification Score
 ↓
Portfolio Fit Score
 ↓
Final Score
 ↓
Allocation
```

O resultado deve ser determinístico.

---

# 22. Wave 10 — Rebalanceamento

Calcular:

```text
peso atual
peso alvo
desvio
```

Exemplo:

```text
ITUB4
Atual: 4%
Alvo: 8%
Gap: +4 p.p.
```

O algoritmo deve priorizar ativos que:

- estejam abaixo do alvo;
- tenham score adequado;
- não violem restrições;
- melhorem a diversificação.

---

# 23. Wave 11 — Interface principal

Criar:

### Dashboard

- patrimônio;
- rentabilidade;
- CDI;
- IBOV;
- composição;
- risco;
- evolução;
- próximo aporte.

### Portfolio

- posições;
- transações;
- performance.

### Asset

- cotação;
- fundamentos;
- histórico;
- score.

---

# 24. Wave 12 — AI Engine

Criar interface:

```text
AIProvider
```

Implementações:

```text
GeminiProvider
OllamaProvider
```

A IA poderá:

- explicar recomendações;
- resumir documentos;
- resumir notícias;
- apontar riscos qualitativos;
- transformar métricas em linguagem natural.

A IA não deve alterar os dados quantitativos.

---

# 25. Wave 13 — Backtesting

Implementar motor que simule:

- aportes mensais;
- compra;
- venda;
- dividendos;
- rebalanceamento;
- custos;
- benchmark.

Métricas:

- CAGR;
- retorno acumulado;
- drawdown;
- volatilidade;
- Sharpe;
- Sortino;
- alpha;
- beta.

---

# 26. Wave 14 — Walk-forward validation

Dividir:

```text
Train
Validation
Test
```

Executar períodos móveis.

Objetivo:

- evitar overfitting;
- validar pesos;
- validar regras;
- medir estabilidade.

---

# 27. Wave 15 — Day Trade Data

Esta wave começa o módulo intraday.

## Requisitos

Obter dados com resolução suficiente.

Inicialmente:

```text
1m
5m
15m
```

Criar:

```text
intraday_prices
```

Implementar:

- ingestão;
- normalização;
- armazenamento;
- atualização;
- detecção de gaps;
- controle de timezone.

---

# 28. Wave 16 — Day Trade Engine

Implementar indicadores:

```text
VWAP
EMA 9
EMA 21
RSI
ATR
Relative Volume
High/Low
Support/Resistance
```

Depois implementar os setups:

```text
Breakout
Pullback
VWAP
```

Cada setup deve ser uma função/regra independente.

Exemplo conceitual:

```text
evaluate_breakout(asset, candles)
evaluate_pullback(asset, candles)
evaluate_vwap(asset, candles)
```

---

# 29. Wave 17 — Day Trade Risk Engine

Entrada:

```text
capital
risk_per_trade
daily_loss_limit
entry
stop
target
fees
```

Saída:

```text
max_position_size
risk_amount
potential_profit
potential_loss
risk_reward
```

Adicionar:

- limite diário;
- limite de operações;
- limite por ativo;
- bloqueio após drawdown diário.

---

# 30. Wave 18 — Day Trade Dashboard

Criar página:

```text
DAY TRADE
```

### Resumo

```text
Mercado
Horário
Volatilidade
```

### Oportunidades

```text
Ativo
Setup
Direção
Entrada
Stop
Alvo
R/R
Score
```

### Exemplo

```text
PETR4

LONG

Entrada: R$ XX,XX
Stop:    R$ XX,XX
Alvo:    R$ XX,XX

R/R: 1:2,0
Score: 84
```

### Histórico

Mostrar:

- setups detectados;
- resultado;
- win rate;
- profit factor;
- expectancy;
- drawdown.

---

# 31. Wave 19 — Day Trade Backtesting

Cada setup deve poder ser testado isoladamente.

Exemplo:

```text
Breakout
2019–2026
```

Comparar:

```text
Win rate
Profit factor
Expectancy
Drawdown
Retorno líquido
```

Depois combinar setups.

---

# 32. Wave 20 — Paper Trading

Antes de qualquer utilização real:

```text
Detectou setup
 ↓
registrou sinal
 ↓
simulou entrada
 ↓
monitorou stop/alvo
 ↓
registrou resultado
```

Nenhuma ordem real será enviada.

Criar relatório semanal/mensal.

---

# 33. Wave 21 — Testes automatizados

## Unit

- indicadores;
- scores;
- cálculos de posição;
- risk engine;
- setups.

## Integration

- API;
- banco;
- ETL.

## E2E

- login;
- carteira;
- recomendação;
- day trade.

## Backtest regression

Criar datasets fixos e garantir que mudanças no código não alterem resultados históricos sem motivo.

---

# 34. Wave 22 — Frontend avançado

Adicionar:

- filtros;
- gráficos interativos;
- comparação;
- drill-down;
- tooltips;
- explicações;
- histórico;
- alertas.

Páginas:

```text
/login
/dashboard
/portfolio
/assets
/assets/:ticker
/recommendations
/daytrade
/backtests
/settings
```

---

# 35. Wave 23 — Observabilidade

Implementar:

- logs estruturados;
- request ID;
- métricas;
- health checks;
- erro de ETL;
- erro de API;
- falhas do scheduler;
- latência.

Endpoints:

```text
/health
/ready
```

---

# 36. Wave 24 — Segurança

Implementar:

- HTTPS;
- JWT;
- hashing;
- CORS;
- rate limiting;
- validação Pydantic;
- secrets;
- proteção contra SQL injection;
- headers de segurança;
- controle de acesso.

Nunca armazenar:

- senha da corretora;
- token de corretora;
- dados bancários.

---

# 37. Wave 25 — Docker Production

Separar:

```text
Dockerfile.dev
Dockerfile.prod
```

Containers:

```text
nginx
frontend
backend
worker
scheduler
postgres
```

Para produção, preferir PostgreSQL gerenciado.

---

# 38. Wave 26 — CI/CD

GitHub Actions:

```text
push
 ↓
lint
 ↓
unit tests
 ↓
integration tests
 ↓
frontend build
 ↓
docker build
 ↓
security checks
 ↓
deploy
```

Pull Request deve bloquear merge se os testes falharem.

---

# 39. Wave 27 — Deploy

## Frontend

Opção:

```text
Vercel
```

## Backend

Opções:

```text
Azure
Render
Railway
VM
```

## Database

Preferir:

```text
Managed PostgreSQL
```

## Worker

Deploy separado do backend quando necessário.

---

# 40. Wave 28 — Migrations em produção

Pipeline:

```text
Deploy
 ↓
backup
 ↓
alembic upgrade head
 ↓
start application
```

Nunca executar migration manualmente sem versionamento.

---

# 41. Wave 29 — Backup e recuperação

Implementar:

- backup diário;
- retenção;
- teste periódico de restore;
- documentação de recovery.

Objetivo:

```text
RPO definido
RTO definido
```

---

# 42. Wave 30 — Paper Trading completo

Executar o sistema por período prolongado.

Registrar:

### Carteira

- recomendação;
- aporte;
- resultado;
- benchmark.

### Day trade

- setup;
- horário;
- entrada;
- stop;
- alvo;
- resultado;
- custos;
- slippage.

Não avaliar apenas quantidade de acertos.

---

# 43. Wave 31 — Validação do sistema

## Carteira

Avaliar:

- CAGR;
- retorno;
- drawdown;
- Sharpe;
- comparação com CDI;
- consistência.

## Day trade

Avaliar:

- win rate;
- profit factor;
- expectancy;
- drawdown;
- retorno líquido;
- estabilidade por período.

Uma estratégia não deve ser considerada válida apenas porque funcionou em um período.

---

# 44. Wave 32 — V1.0

A V1.0 estará pronta quando:

- aplicação estiver publicada;
- autenticação funcionar;
- carteira funcionar;
- dados forem atualizados automaticamente;
- indicadores forem calculados;
- recomendações forem explicáveis;
- backtests forem reproduzíveis;
- day trade possuir paper trading;
- migrations estiverem versionadas;
- CI/CD estiver funcionando;
- backups existirem;
- documentação estiver completa.

---

# 45. Roadmap resumido

```text
W0  Produto
 ↓
W1  Foundation
 ↓
W2  Database
 ↓
W3  Authentication
 ↓
W4  Portfolio
 ↓
W5  Market Data
 ↓
W6  Fundamentals
 ↓
W7  Quant Engine
 ↓
W8  Benchmarks
 ↓
W9  Recommendation Engine
 ↓
W10 Rebalancing
 ↓
W11 Dashboard
 ↓
W12 AI
 ↓
W13 Backtesting
 ↓
W14 Walk-forward
 ↓
W15 Intraday Data
 ↓
W16 Day Trade Engine
 ↓
W17 Day Trade Risk
 ↓
W18 Day Trade Dashboard
 ↓
W19 Day Trade Backtesting
 ↓
W20 Paper Trading
 ↓
W21 Tests
 ↓
W22 Frontend avançado
 ↓
W23 Observability
 ↓
W24 Security
 ↓
W25 Docker Production
 ↓
W26 CI/CD
 ↓
W27 Deploy
 ↓
W28 Production Migrations
 ↓
W29 Backup
 ↓
W30 Paper Trading completo
 ↓
W31 Validação
 ↓
W32 V1.0
```

---

# 46. Prioridade recomendada

Não desenvolver tudo simultaneamente.

## Primeiro

```text
Carteira
+
Market Data
+
Quant Engine
```

## Depois

```text
Recommendation Engine
+
Backtesting
```

## Depois

```text
AI
```

## Depois

```text
Day Trade
```

## Finalmente

```text
Deploy
+
Paper Trading
+
Validação
```

Isso evita gastar semanas criando uma interface bonita para um algoritmo que ainda não foi validado.

---

# 47. Princípio para as recomendações

A plataforma deve diferenciar:

```text
"Ativo interessante"
```

de:

```text
"Ativo interessante para esta carteira agora"
```

E também:

```text
"Setup intraday detectado"
```

de:

```text
"Operação garantida"
```

O sistema deve sempre mostrar:

- dados utilizados;
- critérios;
- score;
- risco;
- horizonte;
- limitações;
- histórico de desempenho da estratégia.

---

# 48. Resultado final esperado

Ao abrir a aplicação:

```text
==================================================
              INVESTMENT ASSISTANT
==================================================

Patrimônio:              R$ XX.XXX
Aporte mensal:           R$ 1.000
Perfil:                  Conservador

Retorno 12M:             XX%
CDI 12M:                 XX%
IBOV 12M:                XX%

--------------------------------------------------
MINHA CARTEIRA
--------------------------------------------------

Renda fixa              XX%
Ações                   XX%
FIIs                    XX%
Exterior                XX%

--------------------------------------------------
PRÓXIMO APORTE
--------------------------------------------------

R$ XXX → Ativo A
R$ XXX → Ativo B
R$ XXX → Renda fixa

--------------------------------------------------
OPORTUNIDADES DAY TRADE
--------------------------------------------------

PETR4    LONG     Score 84
VALE3    SHORT    Score 79

--------------------------------------------------
RISCO
--------------------------------------------------

Volatilidade             XX%
Max Drawdown              XX%
Sharpe                    X.XX

==================================================
```

O projeto terá, portanto, dois motores diferentes:

```text
LONG TERM
    ↓
Portfolio Recommendation Engine

INTRADAY
    ↓
Day Trade Engine
```

Eles devem compartilhar infraestrutura de dados, mas **não devem compartilhar cegamente as mesmas regras de decisão**.

---

# 49. Regra final de segurança do produto

Antes de utilizar qualquer recomendação com dinheiro real:

1. testar em dados históricos;
2. testar fora da amostra;
3. fazer walk-forward;
4. executar paper trading;
5. medir custos e slippage;
6. avaliar drawdown;
7. verificar estabilidade;
8. somente então considerar uso real.

A plataforma deve ser tratada como um sistema de análise e pesquisa, e não como uma promessa de rentabilidade.
