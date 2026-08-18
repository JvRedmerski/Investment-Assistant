# Current Task

## Task

**W07-002 — Quant Engine: Risk** (Wave 07)

## Status

⚪ Not Started

## Objective

`app/quant/risk.py` — volatilidade, beta, maximum drawdown, Sharpe e Sortino, sobre as mesmas séries que `returns.py` consome.

## Context

W07-001 entregou `app/quant/returns.py`: `simple_return`, `period_returns` (diário, semanal ISO, mensal, trimestral, anual), `total_return`, `ytd_return` e `cagr`. Funções puras, sem I/O, tudo em `Decimal`. 47 testes com valores conhecidos.

Este módulo é o par do anterior, e é onde vencem as duas amarras deixadas por [ADR-017](../decisions/ADR-017-annualisation-and-numeric-type.md).

## ⚠️ Duas amarras herdadas do ADR-017 — leia antes de escrever código

### 1. `TRADING_DAYS_PER_YEAR = 252`, definido aqui, **não** importado de `returns.py`

`returns.py` define `DAYS_PER_YEAR = Decimal(365)` porque **retorno composto escala com tempo decorrido** — feriado não suspende juro. Volatilidade é outra grandeza: é uma estatística **por observação**, e anualizá-la é multiplicar por `√(observações por ano)` ≈ `√252`.

Reutilizar os 365 aqui infla a volatilidade anualizada em ~19% (`√(365/252) ≈ 1,20`) e, como o Sharpe divide retorno anualizado por volatilidade anualizada, o índice sai errado por um fator constante — **sem que nada no resultado denuncie**. Se um Sharpe futuro parecer estranho por ~1,2, é o primeiro lugar a olhar.

Definir a constante local, com a justificativa ao lado, como `returns.py` faz com a sua.

### 2. A fronteira `Decimal → float` precisa ser decidida e registrada **nesta task**

`returns.py` não tem essa fronteira, de propósito: subtração, divisão e exponenciação fracionária são todas operações determinísticas de `Decimal`, então `float` custaria precisão sem comprar nada. O ADR-017 cobre **apenas a ausência dela em retornos**, e diz explicitamente que a decisão para risco fica em aberto.

Aqui a necessidade é real: desvio-padrão, covariância (beta) e raiz quadrada. A regra 17 do AGENTS.md permite `float` para cálculo estatístico **desde que a decisão seja documentada**. Avaliar antes de importar `numpy`: `Decimal` tem `sqrt()`, e desvio-padrão/covariância são somas, subtrações e divisões — pode ser que `Decimal` baste aqui também. Decidir com o cálculo em mãos, não por expectativa. Registrar em ADR próprio (ou como adendo datado ao ADR-017, se a decisão for simétrica).

## Relevant Areas

- Backend — `app/quant/` (pacote já criado)

## Relevant Files

**Molde direto a seguir** (mesmo pacote, escrito nesta wave):
- `backend/app/quant/returns.py` — política de dado faltante, constantes documentadas com justificativa, `_usable` estabelecendo pré-condições, `PeriodReturn` carregando o intervalo realmente medido
- `backend/tests/test_quant_returns.py` — valores conhecidos calculados à mão + edge cases

**Outros moldes:**
- `backend/app/domain/fundamentals/indicators.py` — função pura com fórmula documentada por indicador
- [ADR-014](../decisions/ADR-014-indicator-missing-data-policy.md) — dado faltante → `None`, vale aqui também

**Leitura obrigatória:**
- `AGENTS.md` §27 (risco: cada métrica com definição, fórmula, periodicidade, tratamento de dados, testes), §17 (dinheiro e precisão), §128 (DoD quant)
- [ADR-017](../decisions/ADR-017-annualisation-and-numeric-type.md) — as duas amarras acima
- `docs/roadmap.md` §19

## Requirements

1. Funções **puras**, sem I/O. Persistência separada.
2. Cada métrica com **definição, fórmula, periodicidade e tratamento de dado faltante** documentados (§27, §128).
3. **Beta e Sharpe exigem referência externa** (série de índice, taxa livre de risco) que **não existe** no sistema — CDI/IBOV é a Wave 08. Projetar a assinatura **recebendo a série de referência como parâmetro** e retornando `None` quando ela não vier, em vez de antecipar a W08.
4. Dado faltante, série curta demais e divisão por zero → `None`, nunca zero nem exceção.
5. Sem look-ahead: aceitar `as_of` e nunca ler além dele (§108), como `returns.py` faz.
6. Testes com **valores conhecidos calculados à mão** (§68), não apenas "não quebra".
7. Reutilizar `period_returns` de `returns.py` para obter a série de retornos — não reimplementar o cálculo de retorno.

## Constraints

- **Não** implementar benchmarks (W08), scoring (W09) nem backtesting (W13).
- **Nenhuma chamada externa.**
- Não adicionar dependências: `numpy`/`pandas`/`scipy` já estão no `pyproject.toml`. Se usar, justificar (§92) — e note que até agora nenhuma foi importada por código algum.
- Distinguir volatilidade **do ativo** de volatilidade **da carteira**: a segunda precisa de covariâncias entre ativos, não é a média das individuais. Se não couber nesta task, registrar em Future Work.

## Definition of Done

- [ ] `app/quant/risk.py`, funções puras e determinísticas
- [ ] Cada métrica com definição, fórmula, periodicidade e dado faltante documentados
- [ ] `TRADING_DAYS_PER_YEAR = 252` local, com justificativa
- [ ] Fronteira `Decimal → float` decidida e registrada (ADR)
- [ ] Beta/Sharpe com assinatura preparada para a série de referência da W08, `None` sem ela
- [ ] Testes com valores conhecidos + edge cases (série vazia, um ponto, gaps, volatilidade zero)
- [ ] `pytest` verde (baseline 262 + novos), sem regressão
- [ ] `ruff check` e `black --check` limpos nos arquivos alterados
- [ ] `docs/PROJECT_STATUS.md` e a memória atualizados
- [ ] Commit: `feat: add quant engine risk module (W07-002)`

---

## Estado do insumo (verificado 2026-08-18)

A tabela `asset_prices` está **vazia** — nunca houve ingestão. Como as funções são puras e sem I/O, isso não bloqueia nada: os testes usam séries construídas à mão, e `returns.py` foi inteiramente desenvolvido assim.

Invariante útil, garantido por [ADR-016](../decisions/ADR-016-unadjusted-bars-are-not-stored.md): **todo `adjusted_close` gravado foi reportado pela fonte**, nenhum é derivado do `close`. Em troca, a série pode ter **lacunas** (a sessão fechada mais recente costuma faltar por ~1 dia). Ou seja: não é preciso desconfiar do valor, mas é preciso tratar buracos — mesma premissa que `returns.py` adotou.
