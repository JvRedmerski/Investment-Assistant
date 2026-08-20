# ADR-024 — Um período já gravado aceita preenchimento de coluna nula, e só dela

## Status

Accepted (2026-08-19, EVENTS-001). **Emenda operacional ao [ADR-013](ADR-013-fundamentals-point-in-time.md)**, que continua valendo integralmente para o que ele proíbe.

## Context

O ADR-013 estabeleceu que um período de demonstrativo, uma vez gravado, **não é reescrito**: o primeiro valor lido para um `reference_date` é o que fica. É a defesa contra reexpressão silenciosa — a empresa republica 2022 e o banco passaria a contar outra história sem ninguém saber.

A consequência operacional só apareceu na EVENTS-001. Um período gravado fica **congelado com os campos que o código conhecia no dia da ingestão**. Toda coluna nova de demonstrativo nasce, portanto, permanentemente vazia para o dado que já está no banco — mesmo quando a fonte reportava aquele número desde sempre e ninguém tinha aprendido a lê-lo.

As duas colunas anteriores não expuseram isso por acidente de cronologia: `ebit` (W06-003) e `shares_outstanding` (W09-003) chegaram a um banco **vazio**. A `dividends_paid` chegou a um banco com **seis exercícios da PETR4 já gravados** — os mesmos que a wave PRICE tinha acabado de usar para destravar `pe`/`pb`. Sem uma saída, esses seis exercícios ficariam com a coluna vazia para sempre e o `dy` **nunca** produziria valor, com a DMPL da CVM dizendo o número o tempo todo.

A pergunta não é "podemos reescrever o período?" — é "o que fazer com uma coluna que ninguém nunca leu?".

## Decision

`sync_annual_statements(db, provider, asset, refill=True)` — exposto como `?refill=true` no `POST /assets/{ticker}/fundamentals/sync` — **preenche as colunas que estão `NULL` em períodos já gravados, e apenas essas**.

Três invariantes, e é a terceira que separa isto de uma revogação do ADR-013:

1. **Valor presente jamais é tocado.** `_refill_missing` pula toda coluna que já tem conteúdo, sem comparar, sem logar diferença, sem decidir qual é o melhor. Uma reexpressão continua estruturalmente incapaz de entrar por aqui.
2. **`NULL` no fonte não apaga nada.** Se a fonte não reporta o campo, o `NULL` gravado permanece `NULL`.
3. **Fora do `refill`, o comportamento é exatamente o do ADR-013.** O default é `False`; o caminho normal de sync continua sendo "insere o que não existe, pula o que existe".

O resultado é contado à parte (`refilled`) e devolvido na resposta, porque preencher coluna vazia e inserir período são operações diferentes e uma contagem única esconderia qual aconteceu.

## Evidence

- `backend/app/domain/fundamentals/service.py` — `sync_annual_statements(refill=...)` e `_refill_missing`, que itera `REPORTED_FIELD_NAMES` e só escreve sobre `None`.
- `backend/app/integrations/fundamentals/schemas.py` — `REPORTED_FIELD_NAMES`, a lista única que impede a checagem de sair de sincronia com o schema quando uma coluna nova entra.
- `backend/app/api/routes/assets.py` — o parâmetro `refill` na rota; `backend/app/domain/fundamentals/schemas.py` — o campo `refilled` na resposta.
- `backend/tests/test_fundamentals_service.py` — inclui o caso que importa: coluna com valor **não** é sobrescrita nem quando a fonte traz outro número.
- Medido no banco real: seis exercícios da PETR4 preenchidos, e o `dy` saiu de `None` para 0,22 em 2024 e 0,70 em 2022.

## Alternatives

- **Apagar o período e reingerir** — rejeitado. É reescrita com outro nome: perde a distinção entre "ninguém tinha lido este campo" e "a empresa mudou o que disse", que é precisamente a distinção que o ADR-013 existe para preservar.
- **Sobrescrever tudo a cada sync** — rejeitado. Revoga o ADR-013 e deixa a reexpressão entrar em silêncio, sem nenhum registro de que o número mudou.
- **Migration de backfill** — rejeitado. Uma migration não chama provedor externo (AGENTS.md §15); o dado teria de ser embutido no arquivo de migration, o que congelaria valores de uma empresa dentro do histórico de schema.
- **Não fazer nada e aceitar a coluna vazia** — rejeitado por consequência medida: `dy` ficaria permanentemente `None` no único ativo com dado real, e o problema voltaria idêntico na próxima coluna nova.
- **Coluna versionada por período (a solução completa)** — não rejeitada, **adiada**: é o desenho que resolve reexpressão de verdade, e continua sendo o caminho registrado no ADR-013. O `refill` não a substitui nem a atrapalha, porque não escreve onde ela decidiria.

## Consequences

- ✅ **O `dy` existe no banco real.** Foi o último dos 10 indicadores sem insumo; os dez passaram a produzir valor.
- ✅ Uma coluna de demonstrativo nova deixa de exigir banco vazio para valer. O procedimento é `?refill=true` uma vez, depois seguir normal.
- ✅ A checagem percorre `REPORTED_FIELD_NAMES`, então uma coluna futura entra no `refill` sozinha, sem alterar o service.
- ⚠️ **Reexpressão continua sem solução**, e continua sendo Known Issue. Este ADR não a resolve nem a piora.
- ⚠️ `refill` é ação explícita de quem opera, nunca automática, e gasta uma leitura da fonte como qualquer sync. Rodar sem necessidade não corrompe nada — só não faz nada.
