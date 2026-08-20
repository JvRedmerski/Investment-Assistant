# Session Handoff

## Last Updated

2026-08-20

## Last Completed Work

### EVENTS-003 — a série de retorno total existe ([ADR-026](../decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md))

Última task da wave EVENTS, e a que fecha a trava de maior retorno do projeto. Faltava uma
palavra — **magnitude** — e a task começou por decidir de onde ela viria.

**A fonte apareceu medindo, e não estava na lista.** O `CURRENT_TASK.md` enumerava três
candidatas (contagem de ações da CVM, provento por pagamento de fonte a decidir, fornecedor
pago). A quarta é o **serviço aberto de eventos corporativos da própria B3**, que publica reais
por ação num provento e fator num desdobramento, sem token e sem cota — o mesmo critério que
escolheu a CVM (ADR-020) e o COTAHIST (ADR-023).

**Nada foi codificado antes de conferir contra dado real:**

| verificação | resultado |
|---|---|
| Datas contra o contador `DISMES`, sinal **independente** da EVENTS-002 | **157/157** em janela (PETR3, PETR4, VALE3, ITUB4, BBAS3) |
| Fatores contra o degrau de preço em cache | **49/50**; o único fora é a IRBR3 a R$ 0,93, onde o degrau não mede nada |

**A junção é o ISIN, e descobrir isso foi o momento decisivo.** A B3 repete um evento de contagem
uma vez por ISIN que o emissor já teve — o 1:2 da BBAS3 chega três vezes. Compondo tudo, o acordo
era 32/50; e **todo** desacordo era uma **potência exata** da resposta certa (2³ na BBAS3, 4³ na
BPAC11, 10³ na CPLE3, 1,1³ na UNIP3). Foi esse padrão que apontou duplicação em vez de fator
errado. Filtrando por `CODISI`: 49/50.

**Duas armadilhas de unidade, ambas já vistas neste projeto sob outro nome.** `factor` é
porcentagem em `DESDOBRAMENTO`/`BONIFICACAO` e **razão crua** em `GRUPAMENTO`, sob um campo só; e
`valueCash` é cotado por `quotedPerShares`, que é **1000 em 332 de 2.305 linhas** — o erro de mil
vezes que o `FATCOT` e o `ESCALA_MOEDA` já tinham tentado.

### A parte difícil não foi a aritmética, foi decidir quando ela pode rodar

Um ajuste feito com *parte* das ações não é uma série mais curta — é uma **errada e plausível**.
Então `adjusted_close` só é derivado onde toda sessão que a bolsa contou como ex tem ação
dimensionada.

**E a completude não pode ser julgada pelo serviço de eventos, porque ele omite.** A ITUB4 foi ex
em **2025-03-18** com o marcador `EB` do arquivo e degrau de **-8,60%**, e o serviço não reporta
ação nenhuma ali. Quem julga é o contador da B3.

**A exceção do `ATZ` foi decisão do dono do projeto, não do implementador.** Sob a regra estrita,
PETR4 ficaria com **28** de 1.495 pregões ajustáveis, VALE3 com 47, MGLU3 com 7 — a wave não
destravaria nada, porque quase todo incremento não dimensionado carrega `ATZ` (*atualização*), em
que nada sai do titular. Medido: **151 incrementos, degrau mediano 1,0028**, e **6 exceções
nomeadas** (dois BDRs, uma cota de fundo, três ações em queda de 15–20%). A pergunta foi
apresentada com esses números e a decisão foi abrir a exceção. Está no ADR-026 §6, marcada como o
único ponto da task em que uma leitura foi preferida por conveniência de cobertura.

### Medido no banco real, depois do sync

| papel | ajustado | leitura |
|---|---|---|
| **PETR4** | 1.495/1.495 | 62 proventos. Volatilidade **41,8%**, drawdown **-63,4%** com fundo em **2020-03-18** — a COVID. Pior sessão ajustada **idêntica** à crua (-29,7% em 2020-03-09): nenhum evento vazou |
| **BBAS3** | 1.495/1.495 | desdobramento 1:2 desfeito; pior sessão 17,1% |
| **ITUB4** | 198/1.495 | **truncada corretamente** em `[2021-10-04, 2025-03-18]` |
| **MGLU3** | 478/1.495 | truncada na subscrição; **grupamento 1:10 desfeito** — 13,5%, não +896% |

O fator de retorno total da PETR4 é 3,43× em seis anos (8,94 → 30,82 ajustado contra 30,70 →
30,82 cru), consistente com ~R$ 39/ação de provento acumulado sobre um papel de ~R$ 30.

**750 testes** (era 701); migration `012` aplicada em PostgreSQL 16 real, `alembic check` sem
drift, downgrade testado.

---

### EVENTS-001 e EVENTS-002 (2026-08-19)

- **EVENTS-001** (`f330a4c`, [ADR-024](../decisions/ADR-024-refill-fills-null-columns.md)) —
  proventos por exercício da DMPL da CVM, que fecharam o `dy`. A armadilha que a task expôs vale
  mais que a coluna: período gravado é congelado com os campos que o código conhecia no dia
  (ADR-013), então os seis exercícios já no banco ficariam vazios **para sempre**. Daí
  `?refill=true`, que preenche coluna `NULL` e só ela.
- **EVENTS-002** (`a4700d2`, [ADR-025](../decisions/ADR-025-corporate-events-come-from-the-distribution-counter.md)) —
  data e natureza pelo contador `DISMES`, nunca pelo marcador do `ESPECI`, que é janela de
  exibição de ~8 pregões e ainda decai (`EDJ` → `EJ`, 132 sessões em 2024).

## Current State

- `pytest` → **750 passed** (701 → 750), verificado em 2026-08-20. `ruff check` e `black --check`
  limpos.
- ✅ **Docker no ar**, schema **`012`**.
- **Wave EVENTS 🟢 concluída**, 3/3. Nenhuma task com código pela metade.
- No banco real: PETR4, ITUB4, BBAS3 e MGLU3, 1.495 pregões cada, com `adjusted_close` derivado.

## Important Details

### O que o pilar de Risco passou a ter, e o que ele ainda não tem

Tem insumo real para papel com eventos completos. **Não** tem para papel cujos eventos ninguém
dimensionou — e isso é o desenho, com a lacuna voltando **nomeada e datada** em `unaccounted`.
Continua faltando **subscrição**: a B3 a publica numa lista própria, com percentual e preço de
exercício, e dimensioná-la exige um **modelo do valor do direito**, não uma medição. Foi o que
cortou a MGLU3.

### O engano fácil de cometer aqui

`adjusted_close` **não é recomputado**. O preenchimento só toca coluna nula (ADR-024), então uma
correção tardia da B3 sobre data já ajustada não é reaplicada. Recomputar exige limpar a coluna
antes — operação manual deliberada.

E um papel recém-cadastrado **não** ganha risco só com o backfill de preço: o
`corporate-actions/sync` tem que rodar depois.

### Lições de método desta task

- **A alternativa certa pode não estar na lista.** As três candidatas registradas eram razoáveis
  e todas piores do que uma quarta que só apareceu porque a pergunta "o que a própria bolsa
  publica?" foi feita de novo.
- **Um padrão no erro vale mais que o erro.** O acordo de 32/50 não dizia nada; que **todo**
  desacordo fosse uma potência exata do valor certo dizia tudo — e apontou para a chave de
  junção, não para a fórmula.
- **Medir o que se perde, não só o que se acerta.** A varredura do `ATZ` só é confiável porque
  contou também as 6 exceções, em vez de parar no número que confirmava a hipótese.
- **Quando a decisão é de produto, ela é do dono.** A exceção do `ATZ` não era uma leitura mais
  correta da fonte, era uma escolha entre cobertura e rigor, com números dos dois lados.

## Pending Work

**Wave 10 — Rebalanceamento**, na ordem do roadmap. Ver [CURRENT_TASK.md](CURRENT_TASK.md).

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md) e
[../planning/ROADMAP.md](../planning/ROADMAP.md) para a Wave 10. O score que ela consome está
completo pela primeira vez.

## Relevant Files

- `backend/app/integrations/market_data/b3_corporate_actions.py` — o adaptador e suas medições
- `backend/app/integrations/market_data/base.py` — as quatro ABCs
- `backend/app/integrations/market_data/schemas.py` — `CorporateAction`, `SecurityIdentity`, `CorporateEventKind.NOMINAL_UPDATE`
- `backend/app/domain/market_data/adjustment.py` — aritmética + regra de completude
- `backend/app/domain/market_data/corporate_actions.py` — ingestão e ex-date
- `backend/migrations/versions/012_corporate_actions.py`
- `backend/tests/test_b3_corporate_actions.py`, `test_price_adjustment.py`, `test_corporate_action_routes.py`
- `docs/decisions/ADR-026-corporate-action-magnitude-and-the-completeness-rule.md`
