# Session Handoff

## Last Updated

2026-08-18

## Last Completed Work

**W06-004 — Manutenção pré-Wave 07: ambiente Postgres real e validação multi-tipo do parser.**

Sessão de resolução de pendências, não de wave nova. As duas pendências herdadas da Wave 06 terminaram com desfechos opostos ao esperado.

### 1. Recomputar indicadores desatualizados → **a pendência não existia**

Antes de rodar qualquer coisa, verifiquei o estado real: **não havia banco algum.** Sem container, sem volume Docker, sem arquivo SQLite. Ao subir o Postgres, o volume foi *criado do zero* e todas as tabelas vieram com **0 linhas**.

Nunca houve indicador gravado — logo, nada para recomputar. A pendência vinha sendo propagada de handoff em handoff desde a W06-003 com base numa hipótese ("se algum ativo já foi processado, então..."), nunca conferida contra o estado real.

### 2. Migrations em PostgreSQL real → **o Alembic nunca havia rodado**

Ao tentar `alembic upgrade head`, erro imediato: `AttributeError: module 'alembic.context' has no attribute 'is_offline'`. O `migrations/env.py` chamava `context.is_offline()`; a API correta é `is_offline_mode()`.

Isso significa que **nenhuma migration jamais executou** — nem online, nem offline. A "validação estrutural" registrada na W06-003 (`alembic heads`/`history`) não pegou o erro porque **esses comandos leem o diretório de scripts e não carregam o `env.py`**.

Corrigido (uma linha). As migrations `001`→`004` foram então aplicadas com sucesso em PostgreSQL 16 real. 14 tabelas criadas, `alembic current` → `004` (head).

### 3. Validar o parser com FII, ETF e banco → **metade validada, metade bloqueada**

- **Market data: correto para as três classes.** HGLG11 (FII), BOVA11 (ETF) e ITUB4 (banco) devolvem exatamente a mesma forma de resposta da PETR4. 22 barras cada, **0 rejeitadas, 0 avisos** pelo `validate_daily_bars`; `get_quote` correto nos três. Fixado em `test_regression_against_real_responses_per_asset_type`.
- **Fundamentals: impossível validar.** Os módulos `incomeStatementHistory`/`balanceSheetHistory` **saíram do plano gratuito da Brapi** — HTTP 403: *"O plano Startup (R$ 119,99/mês) libera esses módulos. Módulos disponíveis hoje: summaryProfile."* Em **2026-08-17**, um dia antes, a mesma chamada trouxe 16 períodos da PETR4.

## Current State

- `pytest` → **211 passed** (baseline 205 + 6 novos). `ruff`/`black` limpos nos arquivos alterados.
- **PostgreSQL 16 no ar** (`docker compose up -d postgres`), schema em `004`. O container segue rodando.
- Banco **vazio de propósito** — nenhuma ingestão foi feita.
- Alterações no código: `backend/migrations/env.py` (1 linha) e `backend/tests/test_brapi_provider.py` (testes de regressão).

## Important Details

- **Uma pendência operacional não verificada é ruído.** A de recomputação atravessou dois handoffs sem que ninguém checasse se havia dado gravado. Antes de propagar pendência de estado, conferir o estado.
- **"Validado estruturalmente" não é validado.** `alembic heads`/`history` deram sinal verde num `env.py` que não executava. O mesmo padrão de erro da W06-003 (mock que confirma a própria suposição), noutra roupagem.
- **Cota da Brapi: 5 requisições nesta sessão.** Tentei batelar os 3 tickers numa única chamada — o plano gratuito **recusa mais de 1 ativo por requisição**. A 2ª revelou o 403 dos módulos. As 3 últimas validaram as séries de preço. Ingestão em lote custa **1 requisição por ticker**; não há batching.
- **Rodar Python de `backend/` não carrega o `.env` da raiz** (`env_file=".env"` é relativo ao cwd), e `BRAPI_TOKEN` fica vazio em silêncio. Nos meus probes li o `.env` da raiz explicitamente.
- **Para rodar Alembic do host**, sobrescrever a URL — o `.env` aponta para o host `postgres` (rede do Docker), que não resolve fora dela:
  `DATABASE_URL="postgresql://investment_user:investment_pass_dev@localhost:5432/investment_assistant" .venv/Scripts/python.exe -m alembic upgrade head`
- Payloads reais salvos em scratchpad (`brapi_HGLG11.json`, `brapi_BOVA11.json`, `brapi_ITUB4.json`) — os valores relevantes já estão fixados nos testes, então não é preciso regastar cota.

## Pending Work

**Wave 07 — Quant Engine** (`app/quant/returns.py` e `risk.py`). Sem bloqueio; zero requisições externas. Ver [CURRENT_TASK.md](CURRENT_TASK.md).

⚠️ **Ler antes de começar a W07** — defeito que ataca exatamente o insumo da wave: a Brapi devolve `adjustedClose: null` para a sessão fechada mais recente e preenche depois. O parser cai para `close` ([`brapi.py:157-159`](../../backend/app/integrations/market_data/brapi.py#L157-L159)) e `sync_daily_history` **nunca sobrescreve** uma data já gravada. Uma barra ingerida nessa janela guarda `close` como `adjusted_close` **para sempre** — e se houve provento naquela data, todo retorno calculado sobre ela fica errado em silêncio. A W07 usa `adjusted_close` por especificação. Corrigir antes de qualquer ingestão em lote.

Decisão de produto em aberto: **o que fazer com fundamentals** agora que os módulos saíram do plano gratuito — assinar o Startup, migrar para dados abertos da CVM, ou adiar a Wave 09.

Pendências de fundo: drift que faz `alembic check` falhar (constraint + index únicos duplicados); validar o parser de fundamentals com BDR e banco (bloqueado por plano).

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md), `docs/roadmap.md` §19 e `AGENTS.md` §24–§27, e usar `app/domain/fundamentals/indicators.py` como molde de cálculo puro.

Duas decisões esperam na W07: a **convenção de anualização** (252 pregões vs. 365 dias) e a **fronteira `Decimal` → `float`** ao entrar em numpy/pandas — a regra 17 permite float para estatística desde que registrado, então provavelmente cabe um ADR.

## Relevant Files

- `backend/app/domain/fundamentals/indicators.py` — molde de cálculo puro com política de dado faltante
- `backend/app/data/models/assets.py` — `AssetPrice`; usar `adjusted_close` para retornos (ver o alerta acima)
- `backend/app/domain/market_data/service.py` — `sync_daily_history`, onde vive a idempotência que congela o `adjusted_close`
- `backend/tests/test_fundamental_indicators.py` — molde de teste com valores conhecidos
- `backend/tests/test_brapi_provider.py` — testes de regressão com respostas reais de FII/ETF/banco
- `docs/roadmap.md` §19 — especificação da Wave 7
