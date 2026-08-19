# Session Handoff

## Last Updated

2026-08-19

## Last Completed Work

### DOC-001 — Inconsistências documentação × código, zeradas

A lista que vivia em `docs/memory/PROJECT_STATUS.md` como "registradas, **não corrigidas**"
foi percorrida inteira. Eram **8 catalogadas**; a verificação contra o código encontrou mais
**9**, e as 17 foram corrigidas.

A direção da correção foi sempre a mesma, e é a regra do CLAUDE.md §3: **o código é a fonte de
verdade**, então quem mudou foi o documento. Nenhum arquivo `.py` ou `.tsx` foi tocado —
`pytest` continua em 596, que é exatamente o resultado esperado.

O que mudou de fato:

- **`AGENTS.md`** — a árvore da §6 passou a descrever o repositório que existe, marcando
  `(previsto)` o que pertence a waves futuras. §5.1, §7.1, §11, §67, §93, §94, §127, §131 e o
  Wave Execution Protocol foram alinhados aos caminhos reais.
- **Três ausências viraram declarações, não pendências**: `data/repositories/` (ADR-011),
  `docs/waves/` e `CHANGELOG.md`. Esse era o risco concreto — uma sessão futura ler o
  AGENTS.md, ver o diretório faltando e "consertar" criando um segundo padrão de acesso a
  dados no meio do desenvolvimento. O ADR-011 já previa exatamente isso.
- **`README.md`** — ganhou uma seção *Estado atual* honesta (10/33 waves, frontend em
  **🟡 scaffold**), separou a stack em uso da declarada-e-não-importada, e deixou de
  anunciar CI/CD que não existe e um Quant Engine em Pandas/NumPy que foi revogado.
- **`.env.example`** — `ACCESS_TOKEN_EXPIRE_MINUTES` de `115200` (80 dias) para `11520`
  (8 dias, o default do código), e toda a configuração das Waves 06–09 documentada.
- **`CLAUDE.md`** — baseline de testes de 205 para 596.
- **`docs/PROJECT_STATUS.md`** — o *Architecture Status* ainda dava o Quant Engine como
  `NOT_STARTED`.

**O achado com consequência prática**: o `.env.example` parava na Wave 05 e por isso omitia
`MARKET_DATA_MIN_REQUEST_INTERVAL_SECONDS` e `FUNDAMENTALS_MIN_REQUEST_INTERVAL_SECONDS` —
justamente as duas chaves que a Known Issue nº 13 manda ajustar **antes** de qualquer ingestão
em lote, contra uma API com cota mensal. Quem copiasse o exemplo não teria como saber que os
botões existem.

---

### Wave 09 (sessão anterior)

**Wave 09 concluída** — quatro tasks. Duas já estavam entregues (W09-001, W09-002); esta
sessão fechou as outras duas, e a segunda delas é o que a wave inteira existia para produzir.

### W09-003 — Ações em circulação por exercício (`c1e0796`)

Era o último insumo que faltava para `pe` e `pb`, e portanto para o pilar de **Valuation** —
o único dos cinco ainda sem dado nenhum. O dado já estava no arquivo que o projeto **já
baixava**: `dfp_cia_aberta_composicao_capital_{ano}.csv`, integralizadas menos tesouraria.

**O que mudou o desenho da task**: o arquivo **não tem coluna de escala**, e os declarantes
não concordam sobre a unidade. Medido nos exercícios de 2020 a 2025, cerca de **um terço
escreve a contagem em milhares** e o resto em unidades, sem marcador nenhum — e a mesma
empresa alterna entre um ano e outro. A Petrobras escreve `13.044.497` em 2020 e
`13.044.496.930` em 2021.

Engolir isso não daria um erro pequeno. Contagem mil vezes menor → LPA mil vezes maior →
P/L mil vezes menor, e numa escala **invertida** o P/L absurdamente baixo **clampa em 100**.
As leituras mais quebradas iriam para o **topo** do ranking que a alocação consome.

Então a unidade é **reconciliada contra o LPA do próprio arquivo** (`3.99.*`, que é lido
**cru** — `ESCALA_MOEDA` não se aplica a valor por ação, embora a linha venha marcada `MIL`).
Aceita a unidade que fecha; ausente quando nenhuma fecha, ou quando a empresa não publica LPA.
Tolerância larga de propósito (fator 5 para cada lado): o LPA é média ponderada do ano e por
classe, a contagem é o total na data de fechamento — só precisa separar unidades, e 5 está
duas ordens de grandeza longe de 1.000.

Validado contra número público: **PETR4 dá LPA de R$ 2,84**, que é o publicado; VALE3 7,40
contra 7,39; MGLU3 0,61. As séries reproduzem eventos societários reais — desdobramento da
WEGE3 em 2021, bonificação da PSSA3, grupamento da MGLU3 em 2024.

### W09-004 — Alocação do aporte mensal ([ADR-021](../decisions/ADR-021-allocation-ranks-by-coverage-tier.md))

`app/domain/recommendations/allocation.py`, puro e determinístico, e
`GET /portfolios/{id}/contribution-plan`.

- **Ordena por faixa de cobertura antes do score.** Ordenar por `final_score` é o desenho
  óbvio e erra **numa direção só**: os pilares que somem são os fundamentalistas, e o que
  sobrevive a toda lacuna é Diversification, que vale ~100 para o que a carteira ainda não
  tem. Um ativo sem demonstrativo chega com score alto feito dos dois pilares que nunca
  estiveram em dúvida. Piso de 0,50, faixas de 0,25 — dentro da faixa o score decide, entre
  faixas nunca.
- **Os tetos de 20%/40% são as próprias escalas do score** (`ASSET_WEIGHT_SCALE.at_zero`),
  não uma segunda cópia livre para divergir.
- **Todo limite é configurável** (§32) e a política volta dentro da resposta.
- **Nada é gravado**: o plano é derivado a cada leitura, como as posições.
- Toda exclusão tem motivo nomeado (`COVERAGE_BELOW_MINIMUM`, `ASSET_LIMIT_REACHED`, …) e
  toda alocação diz qual regra a limitou (`limited_by`) e quanto de folga havia.

## Current State

- `pytest` → **596 passed** (542 → 555 → 596). `ruff`/`black` limpos nos arquivos alterados.
- **Documentação e código estão alinhados**: a seção *Inconsistências documentação × código*
  do `PROJECT_STATUS.md` da memória está zerada, e agora registra o que foi corrigido.
- **Wave 09 🟢 concluída.** 10 de 33 waves.
- **PostgreSQL 16 no ar, schema `007`**, com CDI/IPCA/IBOV e 6 exercícios da PETR4 pela CVM,
  agora com contagem de ações.
- **`asset_prices` está vazia.**

## Important Details

### O resultado medido no banco real, e o que ele revela

```
PETR4: score 92,63  cobertura 0,55
  quality 97,8 | valuation None | growth 76,7 | risk None | diversification 100
plano: aporte R$ 1.000 → R$ 200 na PETR4 (limitado pelo teto de 20%), R$ 800 sem destino
```

Duas leituras importantes:

1. **`pe`/`pb` estão destravados no código e continuam ausentes no banco** — por falta de
   **preço histórico**, não de contagem de ações. `_price_on_or_before` exige preço na data
   de referência ou antes, e o teto de 3 meses da Brapi não alcança nenhum fechamento de
   exercício passado. Mesma causa do `risk` ausente.
2. **R$ 800 sem destino é a resposta correta**, não uma falha: com um único ativo acompanhado,
   o teto de 20% não deixa R$ 1.000 caber. O plano reporta em vez de forçar.

### O defeito que o teste escrito à mão pegou desta vez

`MAX_POSITIONS = 3` tornava o **primeiro** aporte estruturalmente inexecutável. Na carteira
vazia a base **é** o próprio aporte, então o teto de 20% vale R$ 200 por ativo — três fatias
deixariam R$ 400 parados, todo mês, por meses. Corrigido para **5**, que é
`1 / MAX_ASSET_WEIGHT` e não é coincidência: uma carteira no teto em toda posição tem
exatamente cinco.

O erro não estava na aritmética; estava em escolher dois números que não podiam valer ao
mesmo tempo. Só apareceu porque o caso "carteira vazia" foi escrito como teste em vez de
assumido como trivial.

### Lições de método desta sessão

- **Validar contra número público de novo pagou.** O LPA da Petrobras (R$ 2,84) é
  difícil de acertar por acidente com a contagem errada, e foi ele que expôs a bagunça de
  unidades do `composicao_capital` — que nenhuma validação de schema pegaria, porque todos
  os valores são inteiros válidos.
- **A fonte aberta ensina o que o mock nunca ensinaria**, de novo: um arquivo sem coluna de
  escala, com um terço dos declarantes numa unidade e dois terços em outra.
- **Cobertura só vira defeito quando alguém age sobre o ranking.** No `scoring.py` ela era um
  aviso no docstring; na alocação ela decide para onde vai dinheiro, e o viés tem direção
  conhecida.

## Pending Work

**Nenhuma task em andamento.** A decisão da próxima está em [CURRENT_TASK.md](CURRENT_TASK.md):
Wave 10 (rebalanceamento, a ordem do roadmap) ou **histórico de preços de fonte aberta
(COTAHIST da B3)**, fora da ordem — que é a recomendação, porque é o que hoje trava mais coisa
ao mesmo tempo: `pe`/`pb` no banco real, o pilar de Risco, `beta`/`sharpe` com janela decente
e o backtesting inteiro da W13.

Pendências de fundo, sem mudança: `range` da Brapi limitado a 3 meses; `alembic check` falha
por drift; lint pré-existente; `get_quote()` não exposto; proventos nunca ingeridos;
`npm run lint` quebrado no frontend; bancos e seguradoras com plano de contas diferente no DFP.

Novas desta sessão: `dy` continua ausente e tem caminho conhecido (DMPL, `5.04.06`/`5.04.07`)
mas nenhum pilar o consome hoje; ativo sem setor cadastrado não recebe aporte por padrão;
a carteira não tem caixa modelado, e a alocação deixa o resto implicitamente em caixa.

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md) e escolher entre as duas opções ali. Se for a Wave 10,
ler também `docs/roadmap.md` §22 e `AGENTS.md` §34 — e note que **peso-alvo não existe em
lugar nenhum** hoje, que é a pergunta de verdade da wave.

## Relevant Files

- `backend/app/domain/recommendations/allocation.py` — o alocador, puro
- `backend/app/domain/recommendations/{scoring,service,schemas}.py`
- `backend/app/integrations/fundamentals/cvm.py` — inclui a reconciliação de unidade
- `backend/tests/test_contribution_allocation.py` — 28 testes com valores à mão
- `backend/tests/test_contribution_plan_routes.py` — 13 testes ponta a ponta
- `docs/decisions/ADR-021-allocation-ranks-by-coverage-tier.md`
