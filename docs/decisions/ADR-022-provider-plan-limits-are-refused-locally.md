# ADR-022 — O limite de histórico do provedor é recusado localmente, e o `range` é ancorado em hoje

## Status

Accepted (2026-08-19, manutenção FIX-001)

## Context

A Brapi não expõe histórico por intervalo de datas. Expõe um conjunto fixo de *buckets*
(`1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `max`), e **todo bucket termina em hoje** —
não existe parâmetro de data inicial. O plano gratuito ainda recusa qualquer bucket acima de
`3mo` com HTTP 400 `INVALID_RANGE`.

O código da Wave 05 escolhia o bucket pelo **tamanho da janela pedida**:

```python
days = (end - start).days      # ← errado: mede o intervalo, não o alcance
```

Isso produz dois defeitos distintos, e o menos visível é o pior.

**1. Janela grande demais para o plano.** Uma janela de um ano mapeava para `1y`, que o plano
recusa. A requisição era gasta — contra uma cota mensal — para receber um 400, que subia pela
pilha como `MarketDataUnavailableError`/`InvalidMarketDataResponseError`: uma falha genérica de
provedor, três camadas longe da causa real, que é o plano contratado. Este defeito **estava
documentado** nos Known Issues desde a W08.

**2. Janela no passado.** Este não estava documentado, e é o grave. Como o bucket era medido
pelo intervalo, pedir duas semanas do trimestre passado mandava `range=5d`. Cinco dias contados
de **hoje** não contêm um único pregão de três meses atrás. O parser recebia barras válidas, o
filtro `start <= bar.date <= end` descartava todas, e `sync_daily_history` gravava zero linhas
e reportava sucesso. **Nenhum erro, nenhum log, nenhuma linha errada — apenas ausência
silenciosa**, que é o modo de falha mais caro num pipeline de ingestão.

O defeito sobreviveu à suíte porque os mocks devolvem o mesmo payload independentemente do
`range` enviado. Nenhum teste olhava para o parâmetro que estava sendo montado errado.

## Decision

Duas mudanças, ambas em `_brapi_range_for`:

1. **O bucket é medido de `start` até hoje**, não de `start` até `end`. É o alcance que decide
   se a requisição pode conter a janela pedida, porque é assim que a API funciona.

2. **O teto do plano é configuração (`BRAPI_MAX_RANGE`, default `3mo`) e a recusa é local.**
   Acima do teto, `HistoryWindowTooLargeError` é levantada **antes** de qualquer I/O, e a rota
   a traduz para **HTTP 400 `MARKET_DATA_WINDOW_TOO_LARGE`** com a mensagem dizendo quantos dias
   foram pedidos, qual o teto e qual variável o levanta.

400, não 502: quem precisa mudar é a requisição, não o provedor.

## Evidence

- `backend/app/integrations/market_data/brapi.py` — `_BRAPI_RANGES`, `_brapi_range_for`.
- `backend/app/integrations/market_data/exceptions.py` — `HistoryWindowTooLargeError`.
- `backend/app/core/config.py` — `BRAPI_MAX_RANGE`; documentado em `.env.example`.
- `backend/app/api/routes/assets.py` — tradução para `MARKET_DATA_WINDOW_TOO_LARGE`.
- `backend/tests/test_brapi_provider.py` — inclui o caso que expõe o defeito silencioso
  (`test_range_bucket_is_measured_from_today_not_from_the_window_span`).

## Alternatives

- **Truncar em silêncio para o maior bucket permitido.** Rejeitada: devolver três meses a quem
  pediu um ano é dado faltando sem aviso, exatamente o que a regra "nunca mascare problemas"
  proíbe. O chamador não teria como distinguir "o mercado não negociou" de "o plano não deixou".
- **Deixar o 400 da API subir como está.** É o comportamento anterior. Custa uma requisição de
  cota mensal para descobrir algo que já se sabia antes de sair, e chega ao usuário como
  indisponibilidade do provedor — que é falso, e manda investigar o lugar errado.
- **Fixar o teto em `3mo` no código.** Rejeitada por não sobreviver a uma mudança de plano:
  seria uma constante que ninguém lembraria de alterar ao contratar o plano pago. É uma
  propriedade da conta, não da API — logo, configuração (regra 32).

## Consequences

- Uma janela acima do teto agora **falha rápido, de graça e com mensagem acionável**, em vez de
  gastar cota para produzir um erro que aponta para o lugar errado.
- Uma janela no passado dentro do alcance **volta a funcionar**. Antes devolvia vazio calado.
- O teto continua sendo do plano: isto **não** amplia o histórico disponível, e o `range` segue
  ancorado em hoje. A restrição de ~63 pregões permanece, e com ela a dependência que trava
  `pe`/`pb` no banco real, o pilar de Risco e o backtesting da W13. A saída real continua sendo
  uma fonte aberta de preços (COTAHIST da B3), como a W09-002 fez com os demonstrativos.
- Testes que usavam datas fixas passaram a ser ancorados em datas relativas a hoje — o que a
  API sempre exigiu, e que fixtures de calendário escondiam.
