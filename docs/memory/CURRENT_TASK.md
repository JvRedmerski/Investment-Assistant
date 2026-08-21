# Current Task

## Task

**Wave 12 — AI Engine.** A camada que **explica** — e que por contrato **não calcula nada**
(AGENTS.md §3 e §24, [ADR-009](../decisions/ADR-009-quant-deterministic-ai-explains.md)).
Ver roadmap §24.

## Status

⚪ **Não começou.** A Wave 11 fechou em 2026-08-21 com as cinco tasks entregues, e não há código
pela metade em lugar nenhum.

---

## O que a Wave 11 entregou

| task | entrega |
|---|---|
| **W11-001** | Valor de mercado e P&L não realizado nas posições, com ausência **por linha** |
| **W11-002** | `GET /portfolios/{id}/series` — patrimônio e índice time-weighted, alinhados a um benchmark |
| **W11-003** | A **primeira aplicação real de frontend** do projeto, mais a tela de Carteira |
| **W11-004** | A tela **Dashboard** |
| **W11-005** | A tela de **Ativo** |

### As duas correções que a wave encontrou, e como

Nenhuma das duas foi achada por teste. As duas apareceram **rodando o pipeline contra o banco
real e olhando os números** — o passo que o `IMPLEMENTATION_GUIDE` exige de provedor externo, e
que vale igual para lógica pura.

**1. O índice time-weighted misturava moedas** (W11-002). As posições eram valorizadas em
`adjusted_close` e os fluxos entravam em preço **negociado**. Para papel que pagou anos de
provento o ajustado é uma fração do negociado, então cada compra subtraía ~3× o valor que havia
adicionado. Deu **-3,88** contra seis anos reais de PETR4 — valor de cota não pode ser negativo.

**2. O comparativo media duas janelas diferentes** (W11-004). Carteira de 4,7 anos contra CDI
armazenado desde agosto de 2025, e a subtração entre os dois reportada como "excesso":
**+251,5 p.p.** contra os **+7,1 p.p.** reais.

**As duas eram invisíveis para a suíte, e não podiam não ser**: todo fixture de performance
precificava o ativo exatamente ao preço negociado (o único caso em que as moedas coincidem), e o
comparativo sempre recebia séries do mesmo tamanho. **Os testes compartilhavam a premissa
errada** — a mesma lição da W10-003.

---

## O que a W12 tem que respeitar, e é o ponto inteiro dela

- **A IA não calcula nunca.** Ela recebe números já computados e os traduz. Regra 3, regra 24,
  [ADR-009](../decisions/ADR-009-quant-deterministic-ai-explains.md).
- **A IA não decide.** Nada do que ela devolve entra em score, alvo, plano ou ordenação.
- **Determinismo (regra 113) não se aplica ao texto, mas a explicação tem que ser auditável**:
  o número explicado precisa ser rastreável ao endpoint que o produziu.
- Interface abstrata em `app/integrations/ai/`, com `GeminiProvider` e `OllamaProvider` —
  o mesmo desenho de `MarketDataProvider` e `FundamentalsProvider`.
- `google-generativeai` está no `pyproject.toml` e **nunca foi importado**. Antes de escrever
  parser ou mock, fazer **uma chamada real** e olhar a resposta — a lição cara da W06-003, que a
  W11-005 acabou de repetir em miniatura (o mapa de rótulos de evento estava inventado).

## O que já está pronto — não reimplemente

Todo o backend das waves 00–11 e as quatro telas. Os endpoints que a W12 vai explicar:
`/positions`, `/series`, `/benchmarks/{code}`, `/scores`, `/contribution-plan`, `/rebalance` e
`/rebalance-plan`. Contrato completo em [../architecture/API.md](../architecture/API.md);
frontend em [../architecture/FRONTEND.md](../architecture/FRONTEND.md).

## Estado do ambiente (verificado 2026-08-21)

- ✅ `pytest -q` → **859 passed**. `ruff check .` e `black --check .` limpos.
- ✅ Frontend: `npm run build` e `npm run lint` limpos. Bundle 710 kB (203 kB gzip) — o aviso de
  chunk do Vite fica de pé de propósito (regra 75); dividir é trabalho da W22.
- ✅ Docker no ar, schema **`012_corporate_actions`**. **As waves 10 e 11 não criaram migration**:
  nada nelas é gravado.
- Banco real: carteira `Local` (id 1) sem transação; PETR4 com setor e fundamentos, os outros três
  sem. 1.495 pregões para os quatro papéis.
- Rodar a app: `docker compose up -d postgres`, depois
  `cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000` e
  `cd frontend && npm run dev`.
