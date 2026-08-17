# ADR-011 — Sem camada de repositório; rotas usam `Session` diretamente

## Status

Accepted — *rationale original não documentado; inferido da implementação atual*

## Context

`AGENTS.md` §6 lista `backend/app/data/repositories/` na estrutura preferencial do projeto. Esse diretório **nunca foi criado**. Uma sessão futura que leia o AGENTS.md e depois o código encontrará a divergência e pode "corrigi-la" criando repositórios — introduzindo um segundo padrão de acesso a dados no meio do desenvolvimento.

Este ADR existe para registrar o padrão real e evitar essa correção acidental.

## Decision

Não há camada de repositório. O acesso a dados é feito assim:

- **Rotas** recebem `Session` via `Depends(get_db)` e fazem as queries de CRUD e de ownership diretamente com a API do SQLAlchemy.
- **Services** de domínio recebem `Session` (ou uma lista de entidades já carregadas) como parâmetro e nunca criam sessão própria.
- Services de cálculo puro (ex.: `compute_positions`) **não** recebem `Session` — operam sobre entidades já carregadas, o que os mantém puros e testáveis sem banco.

## Evidence

- `backend/app/api/routes/portfolios.py` e `assets.py` — `db.query(...)`, `db.get(...)`, `db.add/commit/refresh` diretamente na rota.
- `backend/app/domain/market_data/service.py` — `sync_daily_history(db: Session, provider, asset, start, end)`.
- `backend/app/domain/portfolio/service.py` — recebe `list[Transaction]`, sem `Session`.
- `backend/app/data/` contém apenas `database.py` e `models/`.
- `AGENTS.md` §6 diverge; este ADR documenta a realidade.

## Alternatives

- Criar `data/repositories/` conforme AGENTS.md §6 — adicionaria uma camada de indireção que hoje não resolve problema nenhum: as queries são simples e cada uma tem um único chamador. Contraria AGENTS.md §101 (simples > complexo) e §9 (mudança mínima).
- Migrar para repositórios agora — rejeitado: refatoração ampla, fora do escopo de qualquer wave atual.

## Consequences

- ✅ Menos indireção; a query fica visível ao lado da regra que a usa.
- ✅ Services de cálculo permanecem puros e testáveis sem banco.
- ⚠️ Lógica de query pode duplicar entre rotas. Se uma mesma query aparecer em três lugares, extraia um helper no `service.py` do domínio — **não** crie uma camada de repositório completa sem discutir com o usuário antes.
- ⚠️ Rotas ficam mais longas; a compensação é o helper de ownership por recurso (`_get_owned_portfolio`, `_get_asset_by_ticker`).
- ⚠️ Divergência conhecida e aceita em relação ao AGENTS.md §6. **Não "corrija" a estrutura sem aprovação explícita do usuário.**
