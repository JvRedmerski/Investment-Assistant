# Current Task

## Task

**W08-001 — Benchmark Engine: CDI, IBOV, IPCA** (Wave 08)

## Status

⚪ Not Started

## Objective

Séries de benchmark ingeridas e comparáveis com a carteira: CDI, IBOV, IPCA e outros configuráveis (`docs/roadmap.md` §20, AGENTS.md §28).

## Context

A Wave 07 fechou o Quant Engine com `returns.py` e `risk.py` — 101 testes, tudo puro e determinístico.

**Esta wave é o que desbloqueia três métricas já escritas.** `beta`, `sharpe` e `sortino` existem, estão testadas, e retornam `None` hoje por um motivo só: recebem a referência externa como parâmetro e ninguém tem o que passar. Não é código a escrever — é dado a ingerir:

- `beta(series, benchmark=None, ...)` → precisa de uma série de preços do IBOV
- `sharpe(series, risk_free_rate=None, ...)` → precisa da taxa CDI
- `sortino(series, risk_free_rate=None, ...)` → idem

## ⚠️ Duas coisas que a W07 deixou amarradas

### 1. `risk_free_rate` é uma taxa **anual**, e é de-anualizada geometricamente

`sharpe`/`sortino` esperam `Decimal("0.1075")` para 10,75% ao ano, e convertem internamente com `(1 + taxa) ** (1/períodos_por_ano) - 1` (ver `_periodic_rate`). Se a ingestão do CDI produzir taxa diária, **não** passar direto — ou converter para anual, ou revisar a assinatura de forma explícita e documentada.

Cuidado com a armadilha que já pegou um teste na W07: 200% ao ano de-anualiza para ~0,44% ao dia. Uma taxa que parece absurda ao ano pode ser irrelevante ao dia, e vice-versa.

### 2. O benchmark entra como série de **preços**, não de retornos

`beta` recebe `list[PricePoint]` de propósito: ele alinha ativo e benchmark **pelas datas em comum antes** de calcular retornos. Passar retornos prontos reintroduziria exatamente o bug que esse desenho evita — um retorno do ativo que cobre 2 dias (por lacuna) sendo regredido contra um intervalo diferente do benchmark.

Para o CDI, que é uma taxa acumulada e não um preço, isso exige decidir como representá-lo: série de índice acumulado (o natural, e compatível com `PricePoint`) ou algo próprio. **Decidir e registrar** — provavelmente cabe ADR.

## Relevant Areas

- Backend — nova integração em `app/integrations/` (provedor de benchmarks, atrás de interface abstrata)
- Backend — `app/domain/benchmarks/` (ingestão + leitura)
- Backend — possivelmente migration para a tabela de séries de benchmark

## Relevant Files

**Moldes de integração externa** (o padrão está maduro, siga-o):
- `backend/app/integrations/market_data/base.py` + `brapi.py` + `factory.py` — interface abstrata, implementação, factory
- `backend/app/integrations/http.py` — `RetryingJsonClient`, transporte compartilhado (timeout/retry/throttle) já usado pelas duas integrações existentes
- `backend/app/integrations/market_data/data_quality.py` — validação antes de gravar
- `backend/app/domain/market_data/service.py` — `sync_daily_history` idempotente

**Consumidores desta wave:**
- `backend/app/quant/risk.py` — `beta`, `sharpe`, `sortino`, e o helper `_periodic_rate`
- `backend/app/quant/returns.py` — `PricePoint`, `usable_series`

**Leitura obrigatória:**
- `docs/roadmap.md` §20 (Wave 8), `AGENTS.md` §28 (benchmarks)
- [ADR-016](../decisions/ADR-016-unadjusted-bars-are-not-stored.md) — não fabricar dado ausente; vale para qualquer série nova
- [ADR-017](../decisions/ADR-017-annualisation-and-numeric-type.md) — anualização e `Decimal`; o CDI é uma taxa anual, então a convenção importa aqui

## Requirements

1. Provedor externo **atrás de interface abstrata**, como `MarketDataProvider` (AGENTS.md §6 e o padrão do projeto). Reutilizar `RetryingJsonClient`.
2. **Validar contra uma resposta real antes de escrever a bateria de mocks.** Esta é a lição mais caras do projeto até agora: na W06-003, dois campos errados passaram por 45 testes verdes porque todo mock foi escrito com os nomes de campo que se supunham corretos. Um mock construído sobre uma suposição não verifica a suposição.
3. Ingestão idempotente, e **nunca fabricar** valor ausente (ADR-016).
4. Comparações carteira × CDI, carteira × IBOV, carteira × benchmark escolhido.
5. Reutilizar o Quant Engine — **não** reimplementar cálculo de retorno ou de risco.
6. Testes com valores conhecidos.

## Constraints

- **Cota da Brapi é limitada e o plano gratuito aceita 1 ativo por requisição.** Definir `MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS` no `.env` antes de qualquer ingestão em lote.
- **A Brapi pode não servir CDI/IPCA.** Fontes alternativas prováveis: API do Banco Central (SGS, aberta e sem cota) para CDI e IPCA; IBOV possivelmente via Brapi (`^BVSP`). Confirmar antes de assumir.
- Não implementar scoring (W09) nem backtesting (W13).
- Não adicionar dependências sem justificar (§92).

## Definition of Done

- [ ] Provedor de benchmarks atrás de interface abstrata + factory
- [ ] Parser **validado contra resposta real** antes dos mocks, com teste de regressão fixando os valores reais
- [ ] Ingestão idempotente + validação de qualidade
- [ ] CDI utilizável por `sharpe`/`sortino`; IBOV utilizável por `beta`
- [ ] Convenção de representação do CDI decidida e registrada (índice acumulado vs. taxa)
- [ ] Comparações carteira × benchmark
- [ ] Testes com valores conhecidos + edge cases
- [ ] `pytest` verde (baseline 316 + novos), sem regressão
- [ ] `ruff check` e `black --check` limpos nos arquivos alterados
- [ ] `docs/PROJECT_STATUS.md` e a memória atualizados
- [ ] Commit: `feat: add benchmark ingestion (W08-001)`

---

## Estado do ambiente (verificado 2026-08-18)

- **PostgreSQL 16 no ar**, schema em `004`, banco **vazio** — nenhuma ingestão foi feita ainda. `docker compose up -d postgres` se estiver parado.
- Para rodar Alembic do host, sobrescrever a URL (o `.env` aponta para o host `postgres`, da rede Docker):
  `DATABASE_URL="postgresql://investment_user:investment_pass_dev@localhost:5432/investment_assistant" .venv/Scripts/python.exe -m alembic upgrade head`
- Rodar Python de `backend/` **não** carrega o `.env` da raiz (`env_file=".env"` é relativo ao cwd) e `BRAPI_TOKEN` fica vazio em silêncio.
- **`alembic check` falha** por drift pré-existente (unique constraint + unique index duplicados em `assets.ticker` e `users.email`) — não é regressão desta wave.
