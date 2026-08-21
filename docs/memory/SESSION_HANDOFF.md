# Session Handoff

## Last Updated

2026-08-21

## Last Completed Work

### Wave 11 — Dashboard, 5/5 (`a96ba18`, `f44b930`, `3da3db1`, `5d9eae0`, e o commit da W11-005)

A wave que tirou o frontend do estado de scaffold. Duas tasks de backend vieram antes das telas,
porque o roadmap §23 pede números que o backend **não produzia** e a regra 73 proíbe calcular no
cliente.

| task | entrega |
|---|---|
| **W11-001** | Valor de mercado e P&L não realizado nas posições |
| **W11-002** | `GET /portfolios/{id}/series` — patrimônio e índice time-weighted, alinhados a um benchmark |
| **W11-003** | A **primeira aplicação real de frontend** do projeto, mais a tela de Carteira |
| **W11-004** | A tela **Dashboard** |
| **W11-005** | A tela de **Ativo** |

### As duas correções que a wave encontrou — e nenhuma foi por teste

As duas apareceram **rodando o pipeline contra o banco real e olhando os números**. É o passo que
o `IMPLEMENTATION_GUIDE` cobra de provedor externo, e vale igual para lógica pura.

**1. O índice time-weighted misturava moedas** (W11-002, corrigido em `performance.py`).
Posições valorizadas em `adjusted_close`, fluxos entrando em preço **negociado**. Para papel que
pagou anos de provento o ajustado é uma fração do negociado, então cada compra subtraía ~3× o
valor que havia adicionado. Contra seis anos reais de PETR4 o índice deu **-3,88** — valor de
cota não pode ser negativo.

Caso mínimo, mesmas operações e mesmo +10% de retorno: fator de ajuste 1 → `100 → 100 → 110`;
fator 3 → `100 → -100 → -110`.

O conserto (`_external_share_flows`) expressa o fluxo em **ações**, valorizadas no mesmo
`adjusted_close` das posições no dia em que é neutralizado. **Efeito colateral bom**: a
aproximação que o módulo documentava como seu ponto fraco sumiu para o caso comum — comprar mais
de algo já detido durante um vão de preço passou a ser exato, porque o preço desconhecido aparece
nos dois sub-períodos e cancela.

**2. O comparativo media duas janelas diferentes** (W11-004, corrigido em `comparison.py`).
Carteira de 4,7 anos contra CDI armazenado desde agosto de 2025, e a subtração entre os dois
reportada como "excesso":

| | antes | depois |
|---|---|---|
| excesso sobre o CDI | **+251,5 p.p.** | **+7,1 p.p.** |
| retorno da carteira | 266,1% (4,7 anos) | 12,4% (a janela do CDI) |
| volatilidade | 58,7% | 22,5% |
| drawdown | -34,3% | -13,4% |

`compare` passou a recortar as duas séries para a janela compartilhada usando o mesmo `align` que
a W11-002 criou para o gráfico. Bônus: **o número do painel passou a bater com o gráfico ao
lado** — índice 100 → 112,38 e retorno 12,4% são a mesma medida.

**As duas eram invisíveis para a suíte, e não podiam não ser**: todo fixture de performance
precificava o ativo exatamente ao preço negociado (o único caso em que as duas moedas coincidem),
e o comparativo sempre recebia séries do mesmo tamanho. **Os testes compartilhavam a premissa
errada** — a mesma lição da W10-003.

### Um terceiro achado, menor mas do mesmo tipo

O `.gitignore` tinha `lib/`, entrada do template Python que casa em qualquer profundidade, e
estava **engolindo `frontend/src/lib/` inteiro** — o cliente de API não teria sido commitado.
Pego antes do commit que o teria perdido. Ancorado em `backend/lib/`; negação não resolve, porque
o git não desce em diretório excluído.

## Current State

- `pytest` → **859 passed** (832 → 859), verificado em 2026-08-21. `ruff check .` e
  `black --check .` limpos.
- Frontend: `npm run build` e `npm run lint` limpos. Bundle 710 kB (203 kB gzip) — o aviso de
  chunk do Vite fica de pé de propósito (regra 75); dividir é trabalho da W22.
- ✅ Commitado; árvore limpa.
- 🔴 **Docker ligado** nesta sessão. Schema **`012_corporate_actions`**, e **nem a W10 nem a W11
  criaram migration** — nada nelas é gravado (regra 16, ADR-002).
- **Wave 11 🟢 concluída**, 5/5. Nada iniciado da W12.

## Important Details

### Os enganos fáceis de cometer aqui

**A tabela de desvio e o plano de rebalanceamento podem discordar sobre o mesmo ativo, e os dois
estão certos** (W10). `/rebalance` mede a carteira de hoje; `/rebalance-plan` mede a carteira que
o aporte cria.

**`/series` e `/benchmarks/{code}` reportam janelas que podem ser mais estreitas que a pedida**,
porque as duas pontas são recortadas para a janela compartilhada. É de propósito, e as datas
voltam na resposta.

**O frontend nunca calcula.** `lib/format.ts` só move vírgula. Se aparecer `?? 0` num call site,
é bug: `null` do backend significa *não computável*, nunca zero.

### O que o frontend ainda não tem

**Nenhum teste automatizado.** Os 14 schemas `zod` foram conferidos à mão contra um backend real
e isso não se repete sozinho. Está em Future Work; pertence à W21, mas vale antes se crescer mais
duas telas.

### Lições de método desta wave

- **Rodar contra o banco real e olhar os números** encontrou dois defeitos de waves anteriores que
  27 testes verdes não encontraram. Não é cerimônia: é o único passo que não compartilha a
  premissa do código.
- **Quando a suíte quebra depois de uma correção, conferir de que lado está o erro.** Três testes
  quebraram nesta wave e os três eram cenários escritos sob a premissa antiga.
- **Mapa escrito por suposição erra.** O `ACTION_LABEL` da tela de Ativo inventava dois rótulos e
  omitia dois que o banco tem aos montes — pego conferindo contra as respostas reais.

## Pending Work

**Wave 12 — AI Engine**. Ver [CURRENT_TASK.md](CURRENT_TASK.md), que lista o contrato que a wave
tem que respeitar: a IA **não calcula** e **não decide** (regra 3, regra 24,
[ADR-009](../decisions/ADR-009-quant-deterministic-ai-explains.md)).

## Next Step

Ler [CURRENT_TASK.md](CURRENT_TASK.md) e o roadmap §24. Antes de escrever parser ou mock do
provedor de IA, fazer **uma chamada real** e olhar a resposta — a lição cara da W06-003.

## Relevant Files

- `backend/app/domain/portfolio/valuation.py` — valor de mercado, ausência por linha
- `backend/app/domain/portfolio/performance.py` — as duas séries, e a regra de unidade do fluxo
- `backend/app/domain/benchmarks/comparison.py` — `align`, e a janela compartilhada
- `backend/app/domain/benchmarks/service.py` — `portfolio_series`
- `frontend/src/lib/api.ts` — a única porta para o backend, com validação `zod`
- `frontend/src/types/api.ts` — o contrato inteiro como schemas
- `frontend/src/pages/` — Login · Dashboard · Carteira · Ativos · Ativo
- `docs/architecture/FRONTEND.md` — a arquitetura do cliente e as regras que ele cumpre
