# ADR-031 — Um demonstrativo só é legível depois do prazo de entrega, não no dia em que o exercício fecha

## Status

Accepted (2026-08-21, W13-003). Estende o [ADR-013](ADR-013-fundamentals-point-in-time.md) (política point-in-time) para o caso que a regra 109 nomeia e que a regra 108 sozinha não cobre.

## Context

O motor de score já se recusa a ler um demonstrativo com `reference_date` posterior à data sendo pontuada. Isso é a regra 108, é a resposta certa para um score exibido **hoje**, e é **insuficiente para um backtest**.

Um exercício social que fecha em 31 de dezembro **não é público em 1º de janeiro**. Ele é arquivado meses depois. Um backtest que pontuasse um ativo em 2 de janeiro de 2025 usando o resultado anual de 2024 estaria negociando sobre um documento que não existia — e o resultado pareceria uma estratégia que funciona.

A regra 109 é escrita exatamente para esta wave:

> *Indicadores fundamentalistas devem respeitar a data em que estavam disponíveis ao mercado quando utilizados em backtests.*

O projeto não armazena a data de arquivamento. A tabela `fundamentals` tem `reference_date` — o fim do período — e nada mais sobre quando aquilo virou público.

## Decision

### 1. Um demonstrativo conta como disponível `PUBLICATION_LAG_MONTHS` após o fim do período que reporta

Três meses, que é **o prazo da própria CVM** para a entrega do DFP. Ou seja: a data **legal mais tardia**, não um palpite sobre a típica.

A direção do erro é escolhida de propósito. Errar para tarde custa ao backtest um pouco de informação; errar para cedo dá a ele informação que ninguém tinha — e é assim que se constrói um backtest que "funciona".

### 2. A regra é uma aproximação, e o valor exato existe

Os arquivos abertos da CVM carregam a data em que cada peça foi **recebida**. Ingerir essa coluna substituiria a regra pelo fato que ela representa. É mudança de schema mais reingestão de todos os exercícios, então está em *Future Work* — e até lá um backtest está lendo *"três meses depois do fim do exercício"*, não *"o dia em que foi arquivado"*.

Isso está dito no docstring do módulo, não só aqui: quem ler o código descobre a aproximação sem precisar achar este ADR.

### 3. O deslocamento de mês gruda no fim do mês, e só pode errar para o lado de segurar

31 de janeiro mais um mês é 28 (ou 29) de fevereiro — não erro, não 3 de março. Escrito à mão em onze linhas em vez de puxar `dateutil`, que é dependência que este projeto não tem e não vale adicionar por isso (regra 92).

`latest_readable_period` é a inversa, e é a forma que um filtro de banco consegue usar: `reference_date <= latest_readable_period(as_of)` seleciona exatamente os períodos já arquivados, sem avaliar um deslocamento por linha. As duas direções podem discordar em um dia numa virada de mês — 31 de março vira público em 30 de junho, e em 30 de junho o filtro ainda diz que o período mais recente legível é 30 de março. A diferença só consegue **segurar** um demonstrativo um dia a mais, nunca soltar um cedo, e um teste percorre uma década de datas afirmando isso.

### 4. O lag é **zero por padrão**, e só o backtest passa o valor real

`score_asset(publication_lag_months=0)` deixa o caminho vivo exatamente como estava (regra 134). Não é conservadorismo: um score exibido hoje lê o demonstrativo mais recente que existe, e é isso que o investidor quer ver. A pergunta *"o que eu saberia naquele dia"* é do backtest.

## Evidence

- `backend/app/domain/backtesting/availability.py` — `PUBLICATION_LAG_MONTHS`, `available_from`, `latest_readable_period`.
- `backend/app/domain/recommendations/service.py::_latest_indicator` — o parâmetro, com o default zero.
- `backend/app/domain/backtesting/universe.py` — quem passa o lag real.
- `backend/tests/test_backtest_universe.py` — a aritmética, a década de datas, e o mesmo ativo lido de dois exercícios diferentes conforme a data.
- `backend/tests/test_backtest_service.py::test_nothing_is_bought_until_the_statement_it_needs_had_been_filed` — a regra ponta a ponta.

**Medido no banco real** (2026-08-21): PETR4 pontua **62,28** em 2025-03-19 lendo o exercício de 2023, e **50,83** em 2025-04-07 — mesma exposição vazia, mesma série de preço — porque o prazo da CVM venceu em 31 de março e o exercício de 2024 (ROE 0,10 contra 0,33; P/L 12,74 contra 3,87) passou a ser legível. Os 11,45 pontos de diferença são a regra 109 funcionando.

## Alternatives

| Alternativa | Por que não |
|---|---|
| **Manter só a regra 108** (`reference_date <= as_of`) | É o look-ahead que a regra 109 proíbe. Compraria em 2 de janeiro com o balanço de dezembro. |
| **Estimar o atraso típico a partir dos dados** | O projeto não tem a data de arquivamento — é justamente o que falta. Estimar a partir do que não se tem é inventar. |
| **Ingerir a data de recebimento da CVM** | É a **resposta certa**, e é o que substitui esta regra. Exige coluna nova e reingestão de todo exercício já gravado; ficou em Future Work em vez de ser feita dentro de uma task de estratégia. |
| **Um atraso por tipo de peça** (DFP 3 meses, ITR 45 dias) | O projeto só ingere anual hoje ([ADR-013](ADR-013-fundamentals-point-in-time.md)). Um mapa de prazos para períodos que não existem seria código sem insumo. |
| **Aplicar o lag também no caminho vivo** | Esconderia do investidor o balanço mais recente que o mercado já leu. O score de hoje e a simulação do passado fazem perguntas diferentes. |

## Consequences

- **Todo backtest começa quieto.** Os primeiros meses de uma janela não compram nada, porque o demonstrativo mais recente ainda não estava arquivado e a cobertura fica abaixo do piso. Isso é a regra funcionando, e um teste afirma que é assim.
- **`GET /portfolios/{id}/scores?as_of=` continua sem lag.** É um caminho que faz pergunta histórica ao motor vivo, e ele responde com o que se sabe hoje. Registrado em Future Work.
- **O número é configurável e viaja com o resultado.** `settings.publication_lag_months` volta em toda resposta de backtest: é premissa de modelagem, e um resultado que não consegue dizer sob qual premissa foi produzido não é reproduzível (regra 113). Passar `0` é possível e reintroduz o look-ahead — deliberadamente, e dito na documentação do parâmetro.
- **Quando a data real da CVM for ingerida, este ADR fica `Superseded`** e o parâmetro vira compatibilidade, não regra.
