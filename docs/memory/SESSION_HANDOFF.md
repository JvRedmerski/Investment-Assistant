# Session Handoff

## Last Updated

2026-08-18

## Last Completed Work

**Wave 07 — Quant Engine — concluída.** Quatro entregas nesta sessão, em ordem.

### 1. W06-004 — Pendências herdadas da Wave 06 (`1bff119`)

Duas pendências, dois desfechos inesperados.

**Recomputar indicadores: a pendência não existia.** Não havia banco algum — sem container, sem volume Docker, sem SQLite. Ao subir o Postgres, o volume foi criado do zero e todas as tabelas vieram com **0 linhas**. A pendência vinha sendo propagada desde a W06-003 sobre uma hipótese nunca conferida.

**Migrations: o Alembic nunca havia rodado.** `migrations/env.py` chamava `context.is_offline()`, que não existe (é `is_offline_mode()`), e abortava com `AttributeError`. A "validação estrutural" da W06-003 não pegou porque `alembic heads`/`history` não carregam o `env.py`. Corrigido; `001`→`004` aplicadas em PostgreSQL 16 real.

**Parser: metade validada, metade bloqueada.** Market data está correto para FII (HGLG11), ETF (BOVA11) e banco (ITUB4) — mesma forma da PETR4, 0 barras rejeitadas. Fundamentals ficou impossível de validar: os módulos de demonstrativos **saíram do plano gratuito da Brapi** (403), um dia depois de funcionarem.

### 2. W06-005 — Correção do `adjusted_close` (`f3a433d`, [ADR-016](../decisions/ADR-016-unadjusted-bars-are-not-stored.md))

A validação revelou que a Brapi deixa `adjustedClose: null` na sessão fechada mais recente. O parser preenchia com o `close` — o que, somado à idempotência de `sync_daily_history`, **congelaria um ajuste inventado para sempre**, na coluna de que a W07 calcula todo retorno.

Corrigido **antes de qualquer ingestão**, porque o banco estava vazio. Depois seria irreversível: `adjustedClose == close` é comum e legítimo em dia sem provento, então não há como auditar quais valores vieram do fallback.

### 3. W07-001 — `app/quant/returns.py` (`8e92d10`)

`simple_return`, `period_returns` (diário/semanal ISO/mensal/trimestral/anual), `total_return`, `ytd_return`, `cagr`. 47 testes.

### 4. W07-002 — `app/quant/risk.py` (último commit)

`standard_deviation`, `downside_deviation`, `volatility`, `max_drawdown`, `beta`, `sharpe`, `sortino`. 54 testes.

## Current State

- `pytest` → **316 passed**. `ruff`/`black` limpos nos arquivos alterados. Árvore limpa.
- **Wave 07 🟢 concluída.** 8 de 33 waves (W00–W07). Próxima: **Wave 08 — Benchmark Engine**.
- **PostgreSQL 16 no ar**, schema `004`, banco **vazio** de propósito. `docker compose down` para derrubar.
- Todo o Quant Engine é puro e sem I/O, e foi inteiramente desenvolvido sem dado ingerido.

## Important Details

### As duas decisões estruturais da wave ([ADR-017](../decisions/ADR-017-annualisation-and-numeric-type.md))

**Anualização: 365 dias corridos para retorno, 252 pregões para dispersão.** Não é meio-termo — são grandezas diferentes. Retorno composto acumula sobre tempo decorrido (feriado não suspende juro); desvio-padrão é estatística *por observação*. Misturá-las erra todo Sharpe por `√(365/252) ≈ 1,20` **sem sintoma visível no resultado**. Por isso `PERIODS_PER_YEAR` mora em `risk.py`, e há um teste que falha se alguém "simplificar" importando `DAYS_PER_YEAR`.

**`numpy` não entra no Quant Engine.** O ADR-017 previu que `risk.py` precisaria de `float`. Levantando operação por operação, nenhuma das cinco métricas exige: `Decimal.sqrt()` existe, potência fracionária já estava verificada, e não há matriz, inversão nem função transcendental. O argumento decisivo é **determinismo** (regra 113), não magnitude: soma em `float` depende da ordem dos termos, e essa divergência atravessa uma raiz e uma divisão até virar um Sharpe que não reproduz.

**A expectativa de "usar numpy no quant" está revogada, não pendente.** Se uma wave futura precisar de álgebra matricial de verdade — matriz de covariância para volatilidade de carteira, Markowitz — a pergunta volta e deve ser decidida ali, com o mesmo critério: qual operação concreta `Decimal` não cobre.

### Detalhes de projeto que vão importar adiante

- **`beta` recebe séries de preço, não de retorno, de propósito.** Ele alinha ativo e benchmark pelas datas em comum **antes** de calcular retornos. Sem isso, um retorno do ativo cobrindo 2 dias (por lacuna) seria regredido contra um intervalo diferente do benchmark. Há teste para exatamente esse cenário.
- **`risk_free_rate` é anual** e é de-anualizada geometricamente, não dividida por 252.
- **Volatilidade de carteira não foi implementada** e não deve ser aproximada por média das volatilidades — exige matriz de covariâncias e pesos das posições, porque ativos pouco correlacionados cancelam risco. Está em Future Work.

### Lições de método desta sessão

- **Uma pendência operacional não verificada é ruído.** A de recomputação atravessou dois handoffs sem que ninguém checasse se havia dado gravado.
- **"Validado estruturalmente" não é validado.** `alembic heads` deu sinal verde num `env.py` que não executava — o mesmo padrão do erro da W06-003, com outra roupagem.
- **Corrigir dívida antes de existir dado é barato.** A correção do `adjusted_close` foi trivial com o banco vazio e seria irreversível depois.
- **Os testes com valores à mão pegaram dois erros meus**: (a) escrevi o caso de CAGR assumindo 730 dias entre 2024-01-01 e 2026-01-01 — são 731, 2024 é bissexto; (b) esperei Sharpe negativo com `rf=2.0`, esquecendo que 200% ao ano de-anualiza para ~0,44% ao dia. Nos dois casos, um teste escrito a partir da saída do código teria passado.
- **Cota da Brapi: 5 requisições.** O plano gratuito recusa mais de 1 ativo por requisição — **não há batching**, ingestão em lote custa 1 requisição por ticker.

## Pending Work

**Wave 08 — Benchmark Engine** (CDI, IBOV, IPCA). Ver [CURRENT_TASK.md](CURRENT_TASK.md).

É a wave que **desbloqueia `beta`, `sharpe` e `sortino`**: as três estão escritas e testadas, e retornam `None` apenas porque ninguém tem série de referência para passar. Não é código a escrever, é dado a ingerir.

Dois pontos de atenção já registrados no `CURRENT_TASK.md`: a Brapi provavelmente **não serve CDI/IPCA** (a API do Banco Central, SGS, é aberta e sem cota), e o CDI é uma **taxa acumulada, não um preço** — representá-lo como `PricePoint` exige decidir entre índice acumulado e algo próprio, o que provavelmente merece um ADR.

**Regra que vale ouro nesta wave**: validar o parser contra uma resposta real **antes** de escrever a bateria de mocks. Foi assim que dois campos errados passaram por 45 testes verdes na W06-001.

Decisão de produto em aberto, para a W09: **o que fazer com fundamentals** agora que os módulos saíram do plano gratuito — assinar o Startup (R$ 119,99/mês), migrar para dados abertos da CVM, ou adiar a wave.

Pendências de fundo: `alembic check` falha por drift (unique constraint + unique index duplicados em `assets.ticker` e `users.email`); parser de fundamentals sem validação para BDR e banco (bloqueado por plano); lint pré-existente no backend; `get_quote()` implementado mas não exposto; ingestão de proventos nunca feita.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md), `docs/roadmap.md` §20 e `AGENTS.md` §28. Usar `app/integrations/market_data/` como molde de integração (interface abstrata + implementação + factory + `RetryingJsonClient`) e `app/quant/risk.py` para ver exatamente o que as três métricas esperam receber.

## Relevant Files

- `backend/app/quant/risk.py` — `beta`, `sharpe`, `sortino` e `_periodic_rate`: os consumidores desta wave
- `backend/app/quant/returns.py` — `PricePoint`, `usable_series`, e as constantes de anualização
- `backend/app/integrations/market_data/{base,brapi,factory,data_quality}.py` — molde de integração externa
- `backend/app/integrations/http.py` — `RetryingJsonClient` (timeout/retry/throttle) a reutilizar
- `backend/tests/test_quant_risk.py` — molde de teste com valores calculados à mão
- `backend/tests/test_brapi_fundamentals_provider.py` — molde do teste de regressão contra resposta real
- `docs/roadmap.md` §20 — especificação da Wave 8
