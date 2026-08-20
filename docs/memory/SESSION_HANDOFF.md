# Session Handoff

## Last Updated

2026-08-20

## Last Completed Work

### DOC-002 — a documentação alcançou o código (2026-08-20)

Sessão sem alteração de código. As duas primeiras tasks da wave EVENTS estavam entregues e
commitadas (`f330a4c`, `a4700d2`), com `PROJECT_CONTEXT.md` e `BACKEND.md` já atualizados, mas o
resto da documentação ainda descrevia o projeto como *"entre waves, wave PRICE concluída"* —
inclusive dando o `dy` como pendente quando ele já tinha fonte.

Direção da correção seguiu o CLAUDE.md §3: **o código é a fonte de verdade**, então quem mudou
foi o documento.

**Escritos os dois ADRs que as tasks produziram e que não existiam:**

- **[ADR-024](../decisions/ADR-024-refill-fills-null-columns.md)** — período já gravado aceita
  preenchimento de coluna **nula**, e só dela.
- **[ADR-025](../decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md)** —
  evento societário vem do contador de distribuição da B3, com data e natureza e **sem
  magnitude**.

**Atualizados:** índice de ADRs, `DATABASE.md` (migration `011` e a coluna nova), `API.md`
(`?refill=true` e `refilled`; os 10 indicadores com insumo), `BACKEND.md` (o padrão de "coluna de
demonstrativo nova e o dado que já está gravado"; ADR-025 linkado), `ROADMAP.md`,
`docs/PROJECT_STATUS.md` (ledger) e as quatro camadas de memória.

**Achados de documentação estagnada, corrigidos junto:** o `ROADMAP.md` **nunca registrou a wave
PRICE** — as duas waves inseridas agora constam numa seção própria — e listava como pendentes
seis itens já fechados (aplicar migrations em Postgres real, recomputar indicadores, lint do
backend, `npm run lint`, drift do `alembic check`, destino da ingestão de fundamentals). O ledger
também não tinha entrada de *Technical Decision* para o ADR-023, escrito na sessão anterior.

---

### Wave EVENTS — eventos societários e proventos (2026-08-19, 2 de 3 tasks)

Segunda wave **inserida fora da ordem do roadmap**, pelo mesmo critério da PRICE: destrava mais
coisa do que a wave seguinte da fila.

### EVENTS-001 — proventos por exercício, da DMPL da CVM (`f330a4c`, [ADR-024](../decisions/ADR-024-refill-fills-null-columns.md))

`dy` era o último indicador com fórmula escrita (desde a W06-002) e nenhuma fonte. O fornecedor
só publica `dividendYield` como **snapshot de hoje, sem data-fim**, e aplicá-lo a um balanço de
2020 é a violação de *point-in-time* que as regras 108/109 proíbem. A **DMPL** reporta por
exercício e datada nele, num arquivo que o projeto **já baixa**.

Três detalhes decidem se o número está certo, e os três foram conferidos contra o arquivo real:

1. **A coluna.** Toda conta da DMPL se repete uma vez por coluna de patrimônio — `CD_CONTA`
   sozinho seleciona oito linhas. Só `Patrimônio Líquido` é lida; a irmã `Consolidado` soma o
   pago a não-controladores (R$ 302 mi na PETR4 em 2024), sobre o qual o acionista não tem
   direito. Mesma distinção que faz `net_income` ser `3.11.01` e não `3.11`.
2. **O sinal.** Distribuição é débito; a peça escreve negativo, e a grandeza é o módulo.
3. **O que fica de fora.** `5.04.11` (*dividendos prescritos*) é dinheiro não reclamado voltando
   à companhia — estorno de período anterior, não distribuição negativa deste (R$ 316 mi na
   PETR4 em 2024).

Dividendos e JCP são **somados**: declarantes dividem diferentemente e vários reportam o
*payout* inteiro sob um código só.

**A armadilha operacional que a task expôs vale mais que a coluna.** Período gravado é congelado
com os campos que o código conhecia no dia da ingestão (ADR-013), então os seis exercícios da
PETR4 já no banco ficariam com a coluna vazia **para sempre**, e o `dy` nunca sairia de `None`.
As duas colunas anteriores (`ebit` na W06-003, `shares_outstanding` na W09-003) só funcionaram
por terem chegado a um banco **vazio** — ninguém percebeu. Daí `?refill=true`, que preenche
coluna `NULL` e **só** ela; valor presente jamais é tocado, então reexpressão continua sem porta
de entrada.

Medido no banco real, após preencher seis períodos:

| exercício | distribuído | DPS | preço | `dy` |
|---|---|---|---|---|
| 2020-12-31 | R$ 4,41 bi | 0,34 | 28,34 | 0,01 |
| **2022-12-31** | **R$ 224,06 bi** | 17,18 | 24,50 | **0,70** |
| 2024-12-31 | R$ 100,90 bi | 7,83 | 36,19 | 0,22 |

Os 70% de 2022 não são erro de parsing — é o *payout* que a Petrobras de fato fez no ano
recorde. **686 testes** (era 672); migration `011` aplicada em PostgreSQL 16 real.

### EVENTS-002 — em que pregão o papel foi ex, dito pela bolsa (`a4700d2`, [ADR-025](../decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md))

O arquivo de fim de dia responde isso num campo que o parser de preço já lia e descartava. Só
que **não onde parece**.

**O marcador do `ESPECI` é janela de exibição, não evento**, e as duas falhas foram medidas no
arquivo real de 2024: ele **persiste** (~8 pregões — um dividendo seria contado oito vezes) e
**decai** (`EDJ` → `EJ`, que lido como texto parece marcador novo: **132 sessões** no ano).
Detectar por início de sequência também não fecha — a BBAS3 exibe `ON  EDJ NM` em 12, 13 e
14/06 enquanto o contador vai **323, 323, 324**: duas distribuições sob marcador imóvel. Esse
caso virou teste, com os três registros verbatim.

O sinal exato é o **`DISMES`**, contador de distribuição do próprio papel. Conferido no sentido
inverso no arquivo inteiro de 2024 — **2.230 papéis, 7.312 incrementos**: nunca decresceu,
atravessa a virada do ano (ITUB4 345 → 346 em 2025-01-02), e só **13 letras de ex- apareceram
sem incremento**, **nenhuma movendo preço em 25% ou mais**.

**Duas letras mudaram de nome por evidência**, não por gosto:

- `EB` **não é "bonificação"**: carrega o desdobramento 1:2 da BBAS3 (56,46 → 27,91), o 10:1 da
  NVDC34 **e** a bonificação de 4,5% da MGLU3 em 2025 (9,35 → 8,94). Nomear pelo ato jurídico
  afirmaria uma distinção que o arquivo não faz → `BONUS_OR_SPLIT`.
- `R` **não é "rendimento"**: é rendimento de fundo em 3.544 eventos de 2024, mas também cai em
  ação ao lado de outro provento (PETR4 com `EDR`, VIVT3 com `ERJ`). O que todos compartilham é
  dinheiro saindo com a contagem intacta → `OTHER_DISTRIBUTION`.

Letra sem evidência e incremento sem marcador (7,5% de 2024) viram `UNCLASSIFIED`, nunca palpite
(§44), e o `ESPECI` cru fica **verbatim** para revisar classificação sem reler dezenas de GB.
`CorporateEventProvider` é interface própria pela mesma razão que partiu `MarketDataProvider` na
PRICE-001. **701 testes**; 20 fixtures conferidas byte a byte.

## Current State

- `pytest` → **701 passed** (672 → 686 → 701), verificado em 2026-08-20. `ruff check .` e
  `black --check .` limpos no repositório inteiro.
- 🔴 **Docker desligado** — `docker compose up -d postgres` antes de qualquer coisa que toque o
  banco. Com ele no ar, schema **`011`**.
- **Wave EVENTS 🟡 em andamento**, 2/3. Nenhuma task com código pela metade.

## Important Details

### O que ainda falta é uma palavra: **magnitude**

O pilar de Risco continua ausente e a cobertura do score continua em **0,75**. Não é falta de
preço (1.495 pregões no banco) nem mais falta de **data** do evento (a EVENTS-002 entregou). É
falta do **fator** de desdobramento/grupamento e do **valor do provento por pagamento**. O
arquivo da B3 registra que houve distribuição e jamais quanto, e derivar o tamanho do degrau de
preço é a heurística que o ADR-023 rejeitou.

### O que mudou e reabre uma alternativa antes rejeitada

O ADR-023 descartou derivar o ajuste da contagem de ações da CVM **por granularidade**: ela é
anual e "um desdobramento precisa da **data** do evento". **Essa objeção caiu.** A data existe
agora. A combinação (razão entre contagens de exercícios + data carimbada pela B3) é a primeira
candidata a avaliar na EVENTS-003 — mas precisa ser **verificada contra caso conhecido** (MGLU3
1:10 em 2024-05-27, BBAS3 1:2 em 2024-04-16) antes de virar código.

### O engano fácil de cometer aqui

`dy` existir **não** move o score: nenhum pilar consome `dy`. O ganho é o conjunto de
indicadores ficar completo, não a cobertura. Quem move a cobertura é a EVENTS-003.

### Lições de método destas tasks

- **Medir o sinal antes de confiar nele.** O marcador de ex- é o campo óbvio e teria produzido
  oito eventos por dividendo. Só uma varredura do arquivo inteiro mostrou o contador como o
  sinal exato — e mostrou também, no sentido inverso, **o que se perde** ao escolhê-lo (13
  casos, nenhum relevante).
- **Nomear pelo que se observa, não pelo que se supõe.** `BONUS_OR_SPLIT` e
  `OTHER_DISTRIBUTION` são feios de propósito: cada um afirma exatamente o que a fonte sustenta.
- **Uma coluna nova num banco vazio não prova nada.** `ebit` e `shares_outstanding` passaram
  batidos por sorte de cronologia; a terceira coluna encontrou dado gravado e expôs a armadilha.
- **Documentação atrasa em silêncio.** Duas tasks commitadas, e quatro documentos ainda diziam
  "entre waves". O ledger e a memória não se atualizam sozinhos ao fim de uma task — a wave
  seguinte herda a versão errada.

## Pending Work

**EVENTS-003 — série de retorno total**, com a decisão de fonte da magnitude antes do código.
Ver [CURRENT_TASK.md](CURRENT_TASK.md). Depois que a wave fechar:
`docs/history/COMPLETED_TASKS.md` recebe a wave EVENTS (ainda não recebeu, porque a wave não
fechou), e a **Wave 10 — Rebalanceamento** volta a ser a próxima do roadmap.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md), e antes de decidir a fonte da magnitude reler o
[ADR-023](../decisions/ADR-023-unadjusted-history-is-stored-as-unadjusted.md) — ele enumera as
alternativas e o motivo nomeado de cada rejeição, e uma dessas objeções expirou.

## Relevant Files

- `backend/app/integrations/fundamentals/cvm.py` — `_distributions`, a leitura da DMPL
- `backend/app/domain/fundamentals/service.py` — `sync_annual_statements(refill=...)`, `_refill_missing`
- `backend/migrations/versions/011_dividends_paid.py`
- `backend/app/integrations/market_data/cotahist.py` — `get_corporate_events`, `_kinds_in`
- `backend/app/integrations/market_data/{base,schemas}.py` — `CorporateEventProvider`, `CorporateEvent`
- `backend/tests/test_cotahist_provider.py` — inclui o caso BBAS3 (323/323/324) verbatim
- `backend/tests/test_fundamentals_service.py` — o `refill` que não sobrescreve
- `docs/decisions/ADR-024-refill-fills-null-columns.md`, `docs/decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md`
