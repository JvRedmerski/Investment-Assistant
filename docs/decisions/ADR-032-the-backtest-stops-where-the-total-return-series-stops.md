# ADR-032 — Onde a série de retorno total para, o backtest para junto; e o que não tem série nenhuma é excluído com nome

## Status

Accepted (2026-08-21, W13-005). Consome o [ADR-026](ADR-026-corporate-action-magnitude-and-the-completeness-rule.md), que é de onde vem a regra de completude, e o [ADR-023](ADR-023-unadjusted-history-is-stored-as-unadjusted.md), que é de onde vem a coluna nula.

## Context

`adjusted_close` só existe onde o ajuste é **completo**: toda sessão que o contador da B3 marcou ex precisa de uma ação dimensionada por trás, senão a série termina ali ([ADR-026](ADR-026-corporate-action-magnitude-and-the-completeness-rule.md)). Um ajuste feito com parte dos eventos não é uma série mais curta, é uma **errada e plausível**.

A `CURRENT_TASK` da wave deixou isso como requisito explícito: *"onde não é, ela para, e o backtest tem que parar junto em vez de medir preço cru"*.

Só que a truncagem não é apenas um problema de **medição**. Uma sessão marcada ex sem ação por trás é uma **distribuição que este projeto não consegue dimensionar** — e a simulação credita dinheiro por distribuição. Rodar através dela produz uma carteira que recebeu menos caixa do que o investidor receberia. O resultado seria **errado**, não apenas não-mensurável.

Medido no banco real (2026-08-21), os quatro ativos acompanhados:

| ticker | pregões | com ajuste | última sessão sem |
|---|---|---|---|
| BBAS3 | 1.495 | 1.495 | — |
| PETR4 | 1.495 | 1.495 | — |
| MGLU3 | 1.495 | 478 | 2024-02-01 |
| ITUB4 | 1.495 | **198** | 2025-03-18 |

## Decision

### 1. A janela começa onde **todo** ativo do universo tem série completa, e o resultado diz quem a limitou

Conservador de propósito: a alternativa é uma execução que parece mais longa e está silenciosamente sem proventos. `window.bounded_by` nomeia o ativo, porque *"por que meu backtest de dez anos cobriu quatro?"* tem que ser respondível a partir do próprio resultado.

Com os quatro ativos acima, ITUB4 empurra a janela para 2025-03-19. Com PETR4 e BBAS3 apenas, ela roda os seis anos inteiros.

### 2. "Completa" é **depois do último buraco**, não "a partir do primeiro valor"

Uma série pode ser ajustada, interrompida e ajustada de novo — números do fornecedor para as sessões recentes sentados acima de sessões que ninguém nunca derivou. A parte antes do último buraco **tem valores e mesmo assim não é uma série de retorno total**.

Então a regra é: a última sessão com `adjusted_close` nulo, e a primeira depois dela.

### 3. Ativo sem série nenhuma é **excluído com motivo nomeado**, não deixado limitar a janela até o nada

`NO_TOTAL_RETURN_SERIES`. É a mesma decisão que excluir um ativo sem preço nenhum (`NO_PRICES`): mantê-lo tornaria **todo** backtest impossível em vez de tornar **um** deles menor.

Isso não é o viés de sobrevivência da regra 59, que é sobre reconstruir o passado a partir dos vencedores de hoje. A exclusão aqui é por **ausência de dado**, é nominal, e viaja na resposta: `excluded` lista ticker e motivo. Um universo que o leitor não consegue ver seria o problema; um que ele lê linha a linha não é.

### 4. A janela só é reportada como limitada quando algo além do **calendário** a moveu

Este é o defeito que a execução contra o banco real encontrou. Ninguém negocia em 1º de janeiro, então um pedido a partir do dia 1º começa no dia 2 — e `bounded_by` estava nomeando um ativo por isso. O campo existe para o caso honesto; dispará-lo por um feriado torna o caso honesto ilegível.

A comparação passou a ser contra **a primeira sessão que o universo de fato tem**, não contra a data pedida.

### 5. A simulação continua rodando em preço **bruto**; quem exige série ajustada é a medição

Não é contradição com o item 1. A simulação executa e valoriza no fechamento que o mercado imprimiu, com proventos chegando à parte como caixa — é o mundo do investidor, e é a única combinação que não conta duas vezes. O que a janela protege é a **integridade dos proventos**, e o `adjusted_close` é o sinal disponível para ela: as duas coisas param pelo mesmo motivo.

## Evidence

- `backend/app/domain/backtesting/service.py` — `_testable_universe`, `_complete_from`, `_first_session_from`, `NO_PRICES`, `NO_TOTAL_RETURN_SERIES`.
- `backend/app/domain/backtesting/schemas.py::ExcludedAssetResponse` / `BacktestWindowResponse`.
- `backend/tests/test_backtest_service.py` — a série interrompida e retomada, os dois motivos de exclusão, o feriado que não nomeia ninguém.
- Verificado no banco real: universo dos quatro → janela em 2025-03-19, `bounded_by: ITUB4`; PETR4+BBAS3 → 2020-01-02, `bounded_by: None`.

## Alternatives

| Alternativa | Por que não |
|---|---|
| **Medir em preço bruto onde falta ajuste** | É o que a `CURRENT_TASK` proíbe e o que o [ADR-023](ADR-023-unadjusted-history-is-stored-as-unadjusted.md) já tinha decidido para a série de retorno. O grupamento 1:10 da MGLU3 apareceria como sessão de +896%. |
| **Excluir o ativo em vez de encurtar a janela** (como regra geral) | Muda **a estratégia** sendo testada, silenciosamente: o universo é entrada do plano, e um universo menor produz outro plano. Adotado apenas onde encurtar não é opção — ativo sem série alguma. |
| **Data de entrada por ativo** (cada um entra quando fica mensurável) | Um universo que cresce no meio da execução é mais fiel e é também mais máquina: exige o alocador reordenando sobre conjuntos diferentes a cada mês, e aproxima o viés que a regra 59 vigia. Fica para a W14, que já move janelas por construção. |
| **Deixar o chamador escolher entre truncar e excluir** | Uma opção a mais na API para uma pergunta que tem resposta conservadora certa. O chamador já pode obter o efeito passando outro `tickers`. |
| **Nulo em `adjusted_close` tratado como "sem eventos"** | É exatamente o preenchimento por suposição que o [ADR-024](ADR-024-refill-fills-null-columns.md) e a regra 44 recusam. |

## Consequences

- **Uma série quebrada custa a janela inteira, não só o ativo.** ITUB4 reduz um backtest de seis anos a nove meses. É caro, é visível, e o conserto é a montante: dimensionar os eventos que faltam (a subscrição continua fora — [ADR-026](ADR-026-corporate-action-magnitude-and-the-completeness-rule.md)).
- **O universo testado é parte do que foi medido**, e volta na resposta. Comparar dois backtests exige comparar `universe` e `window` antes dos números.
- **A W14 herda isto e vai apertá-lo**: validação walk-forward move janelas por definição, e uma janela que já começa truncada tem menos espaço para ser dividida em treino/validação/teste.
