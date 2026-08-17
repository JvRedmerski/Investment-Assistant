# Current Task

## Task

**W06-001 — Ingestão de Demonstrativos Financeiros** (Wave 06 — Fundamental Data)

## Status

⚪ Not Started

## Objective

Popular a tabela `fundamentals` com demonstrativos financeiros por ativo e por data de referência, seguindo exatamente o mesmo padrão arquitetural já estabelecido na Wave 05 para market data: provedor externo atrás de uma interface abstrata, ingestão idempotente que nunca sobrescreve histórico, e leitura servida do banco.

## Context

A Wave 05 entregou preços diários. Os motores das waves seguintes dependem de fundamentos:
- W06-002 calcula indicadores derivados (`financial_indicators`: P/L, P/VP, ROE, ROIC, DY…).
- W09 (Recommendation Engine) usa esses indicadores como sub-scores de Quality/Valuation/Growth.

A tabela `fundamentals` já existe no schema desde a Wave 02 (`001_initial_schema`) — nenhum código a escreve ou lê ainda.

Restrição crítica de domínio (AGENTS.md §109, §108): um indicador fundamentalista só pode ser usado em backtest a partir da data em que estava **disponível ao mercado**. Por isso `reference_date` é parte da identidade do registro, e valores históricos nunca podem ser sobrescritos silenciosamente.

## Relevant Areas

- Backend — Integrations (novo provedor externo)
- Backend — Domain (novo serviço de ingestão)
- Backend — API (endpoints de sync/leitura)
- Database (possível migration, ver Requirements)

## Relevant Files

**Padrão a replicar** (leia estes antes de escrever qualquer coisa):
- `backend/app/integrations/market_data/base.py` — como se declara a interface abstrata
- `backend/app/integrations/market_data/brapi.py` — timeout, retry limitado, throttle, parsing defensivo
- `backend/app/integrations/market_data/factory.py` — seleção por `settings.<X>_PROVIDER`
- `backend/app/integrations/market_data/schemas.py` — DTOs Pydantic para dado externo não confiável
- `backend/app/integrations/market_data/data_quality.py` — validador puro e determinístico
- `backend/app/domain/market_data/service.py` — `sync_daily_history`: valida → filtra o que já existe → insere → retorna contagens
- `backend/app/api/routes/assets.py` — mapeamento de exceções do provider para HTTP (404/502/503)
- `backend/app/api/dependencies.py` — `get_market_data_provider` como dependency por request

**A modificar/criar:**
- `backend/app/integrations/fundamentals/` (novo pacote)
- `backend/app/domain/fundamentals/` (novo pacote)
- `backend/app/api/routes/assets.py` (novos endpoints sob `/assets/{ticker}/fundamentals`)
- `backend/app/core/config.py` (settings do novo provedor)
- `backend/app/data/models/fundamentals.py` (só se a decisão de precisão exigir — ver Requirements)
- `backend/tests/test_fundamentals_*.py`

**Referência de domínio:**
- `docs/roadmap.md` §18 (Wave 6) e §9 (schema `fundamentals`)
- `AGENTS.md` §19 (dado externo não confiável), §20 (data quality), §21 (abstrair fornecedor), §22 (falha de API), §29 (quais fundamentos), §109 (data de disponibilidade)

## Requirements

1. Interface abstrata `FundamentalsProvider` em `app/integrations/fundamentals/base.py`; nenhum código de domínio importa a implementação concreta.
2. Implementação concreta via `httpx` com timeout, retry **limitado** (nunca infinito) e distinção entre erro transitório e permanente — espelhando `BrapiProvider`.
3. DTOs Pydantic para a resposta externa; nunca assumir que um campo existe (`revenue`, `ebitda`, `net_income`, `equity`, `debt`, `cash`, `free_cash_flow` são todos nullable no model).
4. Serviço de ingestão idempotente: `(asset_id, reference_date)` já armazenado **não** é sobrescrito; retorna contagens de fetched/inserted/skipped/rejected.
5. Endpoint de sync (único que chama o provedor) + endpoint de leitura que **nunca** chama o provedor.
6. Exceções do provider mapeadas para HTTP com o envelope `{"error":{"code","message"}}`.
7. **Decidir e documentar** se as colunas de `fundamentals` (hoje `Float`) devem ir para `NUMERIC` — são valores monetários de balanço (AGENTS.md §17). Se sim, criar migration Alembic `003_*` e atualizar o model. Se não, justificar (ex.: agregados de balanço em escala de milhões onde precisão decimal não é crítica) e registrar como decisão.

## Constraints

- **Não implementar W06-002** (cálculo de indicadores derivados) nesta task.
- **Não** tocar em Quant Engine, Recommendation Engine ou frontend.
- **Não** criar tabela nova — `fundamentals` já existe no schema.
- **Não** alterar migrations já aplicadas; se schema mudar, nova migration (AGENTS.md §14/§15).
- Manter o envelope de erro padrão e a autenticação via `get_current_user` em todos os endpoints novos.
- Timezone: qualquer "hoje" calculado explicitamente em UTC (AGENTS.md §18).
- **Bloqueio conhecido**: pode não haver acesso de rede para validar o parser contra a API real. Se for o caso, implementar defensivamente, testar com `httpx.MockTransport` e **documentar a lacuna explicitamente** — mesmo tratamento dado ao `BrapiProvider` (ADR-004). Nunca afirmar que foi validado.

## Definition of Done

- [ ] `FundamentalsProvider` abstrato + implementação concreta + factory
- [ ] DTOs Pydantic validando a resposta externa
- [ ] Serviço de ingestão idempotente (não sobrescreve `reference_date` existente)
- [ ] Endpoints de sync e leitura, autenticados, com erros mapeados
- [ ] Decisão sobre precisão numérica tomada e registrada (+ migration se aplicável)
- [ ] Testes unitários do parser (incluindo campos ausentes/nulos e erros do provedor) e do serviço de ingestão
- [ ] Testes de integração HTTP com provider fake via `dependency_overrides` (nenhum teste toca rede)
- [ ] `pytest` verde (baseline 95 + novos), sem regressão
- [ ] `ruff check` e `black --check` limpos nos arquivos alterados
- [ ] `docs/PROJECT_STATUS.md` atualizado (task + notas + validação)
- [ ] `docs/memory/PROJECT_STATUS.md`, `CURRENT_TASK.md` e `SESSION_HANDOFF.md` atualizados
- [ ] Commit: `feat: add fundamental data ingestion (W06-001)`
