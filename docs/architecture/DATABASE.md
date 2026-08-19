# Database

> Camada 2. Leia quando a task tocar models, schema ou migrations.
> Estado em 2026-08-17.

## Banco e ORM

- **PostgreSQL 16** é o banco oficial (imagem `postgres:16-alpine` no compose). SQLite é permitido **apenas** em testes isolados ([ADR-001](../decisions/ADR-001-postgresql.md)).
- **SQLAlchemy 2.0**, estilo declarativo tipado: `class Base(DeclarativeBase)`, colunas como `Mapped[T] = mapped_column(...)`.
- Engine/session em `app/data/database.py`: `create_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=APP_ENV=="development")`, `SessionLocal`, dependency `get_db`, helper `utc_now()`.
- Driver: `psycopg2-binary`.

## Migrations

- **Alembic**, `backend/alembic.ini` + `backend/migrations/`.
- Migrations existentes:
  - `001_initial_schema` — as 13 tabelas.
  - `002_numeric_money_columns` — converte `transactions.{quantity,price,fees}` e `asset_prices.{open,high,low,close,adjusted_close}` de `FLOAT` para `NUMERIC(18,6)`.
  - `003_numeric_fundamentals_columns` — converte as sete colunas monetárias de `fundamentals` de `FLOAT` para `NUMERIC(24,4)`.
  - `004_fundamentals_income_detail` — adiciona `ebit`, `income_before_tax` e `income_tax_expense` a `fundamentals`.
  - `005_benchmark_values` — cria `benchmark_values` (séries de CDI/IBOV/IPCA/Selic) em `NUMERIC(24,12)`.
  - `006_assets_cnpj` — adiciona `assets.cnpj`, o elo entre as duas fontes de demonstrativos.
  - `007_shares_outstanding` — adiciona `fundamentals.shares_outstanding` (`NUMERIC(20,0)`), a contagem por exercício que destravou `pe` e `pb`.
  - `008_numeric_contribution` — converte `investor_profiles.monthly_contribution` de `FLOAT` para `NUMERIC(18,6)`. Era a última coluna monetária **com consumidor** ainda em float; o alocador da W09 divide exatamente esse valor.
  - `009_drop_dup_uniques` — remove as `UniqueConstraint` redundantes de `assets.ticker` e `users.email`. A `001` criou constraint **e** índice único para a mesma coluna, enquanto o model declara só o índice — o que fazia `alembic check` acusar drift em toda execução e inutilizava a checagem como guarda em CI. A unicidade continua garantida pelo índice único.
    ⚠️ O `revision` é curto de propósito: `alembic_version.version_num` é `varchar(32)`, e um id mais longo falha **depois** de o schema já ter sido aplicado.
- Todas foram **escritas manualmente**, não por autogenerate.

```powershell
cd backend
alembic upgrade head
alembic revision --autogenerate -m "descrição"   # sempre revisar o resultado à mão
```

Regras invioláveis (AGENTS.md §14/§15): nunca alterar tabela fora de migration; nunca editar migration já aplicada; nunca recriar histórico; toda migration precisa de `upgrade` e, quando possível, `downgrade`.

✅ **`001`→`005` aplicadas contra PostgreSQL 16 real** (2026-08-18). Para isso foi preciso corrigir `migrations/env.py`, que chamava `context.is_offline()` (o correto é `is_offline_mode()`) e abortava com `AttributeError` — ou seja, **o Alembic nunca havia executado** antes disso. `alembic heads`/`history` não carregam `env.py`, e é por isso que a "validação estrutural" anterior não pegou o erro. Lição: validado estruturalmente não é validado.

## Entidades (13 tabelas)

Agrupadas por domínio; `id` serial PK e `created_at` são universais e foram omitidos.

### Usuário
| Tabela | Campos-chave | Usada por código? |
|---|---|---|
| `users` | `email` (unique), `password_hash`, `updated_at` | ✅ auth |
| `investor_profiles` | `user_id` (unique), `risk_profile` (enum CONSERVATIVE/MODERATE/AGGRESSIVE), `monthly_contribution` | ❌ ainda não |

### Ativos e preços
| Tabela | Campos-chave | Usada? |
|---|---|---|
| `assets` | `ticker` (unique, index), `name`, `asset_type`, `sector`, `currency`, `is_active`, `cnpj` | ✅ |
| `asset_prices` | `asset_id`, `date`, OHLC + `adjusted_close` (`NUMERIC`), `volume` (`Float`), `source` | ✅ |
| `intraday_prices` | `asset_id`, `timestamp`, `timeframe` (1m/5m/15m), OHLCV (`Float`) | ❌ Wave 15 |

### Benchmarks
| Tabela | Campos-chave | Usada? |
|---|---|---|
| `benchmark_values` | `benchmark_code` + `date` (unique), `value` (`NUMERIC(24,12)`), `source` | ✅ |

Sem tabela `benchmarks`: o catálogo (código, nome, tipo, periodicidade, fonte, id da série na
fonte) vive em **código**, em `app/domain/benchmarks/catalog.py`. A definição de um benchmark
não é dado de usuário — é fato revisável sobre uma fonte externa, e controle de versão é melhor
lar para isso do que um seed que dois ambientes podem divergir. Daí `benchmark_code` ser string
e não foreign key.

`value` significa coisas diferentes conforme o `kind` do catálogo: **fração** por período para
um benchmark `RATE` (CDI a 0,00043739) e **nível** para um `INDEX` (IBOV a 166784). Nunca ler a
tabela sem consultar a definição — é por isso que todo caminho de leitura passa por
`app/domain/benchmarks/series.py`. Nenhum índice acumulado é armazenado: acumular depende da
data-base que o consumidor pede ([ADR-018](../decisions/ADR-018-benchmark-representation.md)).

A escala de 12 casas é maior que a `NUMERIC(18,6)` do dinheiro de propósito: uma taxa diária
arredondada em 6 casas perde dois dígitos significativos, e o erro compõe 252 vezes por ano.

### Carteira
| Tabela | Campos-chave | Usada? |
|---|---|---|
| `portfolios` | `user_id`, `name` | ✅ |
| `transactions` | `portfolio_id`, `asset_id` (nullable), `type` (enum), `quantity`/`price`/`fees` (`NUMERIC`), `transaction_date` | ✅ |
| `portfolio_snapshots` | `portfolio_id`, `date`, `total_value`, `cash_value`, retornos diário/mensal/YTD/anual (`Float`) | ❌ Wave 11 |

### Fundamentos
| Tabela | Campos-chave | Usada? |
|---|---|---|
| `fundamentals` | `asset_id`, `reference_date`, `revenue`, `ebitda`, `net_income`, `equity`, `debt`, `cash`, `free_cash_flow`, `ebit`, `income_before_tax`, `income_tax_expense` (todos nullable, `NUMERIC(24,4)`) + `shares_outstanding` (nullable, `NUMERIC(20,0)`) | ✅ W06-001/003, `shares_outstanding` na W09-003 — só demonstrativos **anuais** |
| `financial_indicators` | `asset_id`, `reference_date`, `pe`, `pb`, `roe`, `roic`, `dy`, `debt_ebitda`, `net_margin`, `ebitda_margin`, `revenue_growth`, `profit_growth` (`Float`, deliberado — são razões, não moeda) | ✅ W06-002/003 — 5 dos 10 populados; os demais `NULL` por limitação evidenciada da fonte |

### Recomendações e Day Trade
| Tabela | Campos-chave | Usada? |
|---|---|---|
| `recommendations` | `portfolio_id`, `asset_id`, `recommendation_type`, `score`, `confidence`, `target_weight`, `suggested_amount`, `horizon`, `reason` | ❌ Wave 09 |
| `daytrade_setups` | `asset_id`, `strategy`, `timeframe`, `detected_at`, `entry_price`, `stop_price`, `target_price`, `risk_reward`, `score`, `status`, `reason` | ❌ Wave 16 |
| `daytrade_results` | `setup_id` (unique), `exit_price`, `exit_timestamp`, `result`, `pnl`, `pnl_percent`, `costs`, `slippage` | ❌ Wave 19 |

## Relacionamentos importantes

```
users 1─1 investor_profiles          (CASCADE)
users 1─N portfolios                 (CASCADE)
portfolios 1─N transactions          (CASCADE)
portfolios 1─N portfolio_snapshots   (CASCADE)
portfolios 1─N recommendations       (CASCADE)
assets 1─N asset_prices              (CASCADE)
assets 1─N intraday_prices           (CASCADE)
assets 1─N fundamentals / financial_indicators / recommendations
transactions ─N─1 assets             (SET NULL — a transação sobrevive à remoção do ativo)
daytrade_setups 1─1 daytrade_results (CASCADE)
```

**Não existe tabela de posições.** Posições são derivadas de `transactions` em tempo de leitura ([ADR-002](../decisions/ADR-002-positions-derived-from-ledger.md)).

## Convenções

- **Dinheiro**: constante `MONEY = Numeric(18, 6)`, duplicada em `models/portfolio.py` e `models/assets.py`. 18 dígitos, 6 decimais — comporta quantidade fracionária e preço em BRL sem drift. `volume` fica `Float` (não é dinheiro). Em `models/fundamentals.py`, `STATEMENT_MONEY = Numeric(24, 4)`: agregados de companhia inteira precisam de mais dígitos inteiros e menos decimais. ([ADR-003](../decisions/ADR-003-decimal-money.md))
- **Contagem de ações**: `SHARE_COUNT = Numeric(20, 0)` em `models/fundamentals.py` — não é dinheiro nem razão, é inteiro exato (nenhum arquivo da CVM de 2020 a 2025 reporta fração de ação). `NULL` ali significa que a contagem declarada **não pôde ser reconciliada** com o LPA do próprio arquivo, nunca zero ações.
- **`NULL` ≠ zero**: em `fundamentals`, um item de linha nulo significa "não reportado"; em `financial_indicators`, significa "não computável". Nunca leia como zero nem substitua por default ([ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md)).
- **Timestamps**: `DateTime` sem timezone no banco, sempre preenchido com `utc_now()` (UTC explícito). Conversão para horário local é responsabilidade da apresentação (AGENTS.md §18).
- **Unicidade e índices**: `uq_asset_price_date (asset_id, date)`, `uq_intraday_timestamp_timeframe (asset_id, timestamp, timeframe)`, `idx_transactions_portfolio_asset`, `idx_fundamentals_asset_refdate`, `idx_indicators_asset_refdate`, `idx_snapshot_portfolio_date`.
- **Enums**: `TransactionTypeEnum` e `RiskProfileEnum` são `str, enum.Enum` do Python mapeados com `SQLEnum` — o valor persistido é o nome em maiúsculas.
- **Dado histórico é imutável**: preços, fundamentos e recomendações já gravados nunca são sobrescritos por uma nova ingestão; insere-se apenas o que falta (AGENTS.md §20/§39/§109).

## Dívida conhecida — colunas monetárias ainda em `Float`

Conversão deliberadamente adiada para a wave que for usar cada tabela:

| Coluna | Wave |
|---|---|
| `intraday_prices` OHLC | W15 |
| `portfolio_snapshots.total_value`, `.cash_value` | W11 |
| `investor_profiles.monthly_contribution` | W09 |

(`fundamentals` foi convertida na W06-001; `financial_indicators` permanece `Float` por decisão, não por dívida.)
