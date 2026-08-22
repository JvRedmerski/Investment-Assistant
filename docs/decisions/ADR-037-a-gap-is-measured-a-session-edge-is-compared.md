# ADR-037 — Buraco se mede; borda de sessão se compara

## Status

Accepted (2026-08-22, W15-003). Aplica ao intraday a mesma linha do
[ADR-023](ADR-023-unadjusted-history-is-stored-as-unadjusted.md): o que é observado é
reportado como observação, e o que exigiria uma suposição não é reportado como se fosse medida.

## Context

O escopo da W15 (roadmap §27) pede **detecção de gaps**, e a regra 20 lista `gaps` entre as
verificações obrigatórias. O `CURRENT_TASK` foi explícito sobre o padrão: *pregão com buraco de
dez minutos é dado que precisa dizer que está furado, não série mais curta*.

A pergunta que isso deixa em aberto é o que conta como buraco. Duas coisas parecem a mesma e não
são:

1. **Falta barra entre duas que chegaram.** Duas barras consecutivas da mesma sessão separadas
   por mais de um `timeframe` têm algo faltando no meio, e quanto é aritmética.
2. **A sessão começou tarde ou terminou cedo.** Isso não se mede pelas barras que chegaram — a
   primeira barra entregue é simplesmente a primeira barra entregue.

Dizer que a segunda é buraco exigiria conhecer o horário de pregão da B3 **naquela data**. Este
projeto não tem esse calendário e a fonte não o publica.

### O que a chamada real mostrou, e que derrubou o desenho óbvio

Capturando um mês de barras de 15 minutos da PETR4, 21 das 22 sessões vão de 10:15 a 16:45, com
27 barras numa grade limpa de `:00/:15/:30/:45`. A vigésima segunda, **2026-07-31**, tem 16
barras, começa às 13:01 e está numa grade de `:01/:16/:31/:46`.

Duas conclusões, e a segunda é a que importa:

- O desenho óbvio — exigir que barras de 15 minutos caiam na grade — teria **rejeitado as 16
  barras** daquele pregão. São preços reais. Uma sessão genuinamente curta teria sido reportada
  como sessão malformada.
- Dentro do dia a cadência é perfeita: 900 segundos entre barras consecutivas, zero buracos. O
  que falta está **antes da primeira barra**, que é exatamente a metade não mensurável.

E há um confundidor a mais, também medido: os baldes de range são ancorados no instante do
pedido, então a sessão mais antiga de um lote começa onde a janela começou. Uma captura de um
dia de barras de 1 minuto abriu às 10:19 puramente porque era 24 horas antes da requisição.

## Decision

### 1. Buraco é entre barras entregues, dentro de uma sessão

`INTRA_SESSION_GAP`, com a contagem exata do que falta. Não precisa de calendário nem de
suposição, e a fronteira noturna nunca é buraco — 17 horas entre a última barra de terça e a
primeira de quarta é o mercado fechado.

### 2. Sessão curta é comparada com as vizinhas do mesmo lote, nunca com um horário presumido

`SHORT_SESSION` afirma: *esta sessão traz 16 barras onde a sessão típica deste lote traz 27*.
A frase é verdadeira quer a bolsa tenha aberto tarde, quer tenha havido leilão, quer o
fornecedor tenha perdido linhas — e **não pretende saber qual**.

A referência é a **moda** das contagens, não o máximo: uma sessão com uma barra a mais faria
todas as outras parecerem curtas. Empate desempata para a contagem maior, escrito no código para
não depender de ordem de dicionário (regra 113).

A primeira e a última sessão do lote ficam fora da comparação **e** da referência: as duas são
cortadas pela janela do pedido e não por dado faltante. Com menos de três sessões não sai
comparação nenhuma — mesma postura do walk-forward, que recusa tirar média de um fold só.

### 3. Nada de verificação de alinhamento de grade

Registrado como decisão explícita, e não como omissão, porque é a tentação que o dado real
desarmou. O que a fonte garante é cadência entre barras consecutivas; a **fase** não é garantida
e varia por sessão.

### 4. O fuso da bolsa é um offset fixo, não uma zona IANA

O agrupamento em sessões é feito em hora local, porque *a qual pregão um instante pertence* é
pergunta de mercado local. Hoje a B3 cabe inteira dentro de um dia UTC, mas isso é coincidência
do offset e não propriedade de sessão.

`EXCHANGE_TIMEZONE` é `UTC-03:00` fixo. O Brasil aboliu o horário de verão em 2019 e o
fornecedor serve no máximo três meses de intraday, então o offset é constante para **toda data
que este projeto consegue alcançar**.

`ZoneInfo("America/Sao_Paulo")` codificaria a regra em vez da constante, mas precisa da base
IANA, que o Windows não traz: levanta `ZoneInfoNotFoundError` na máquina de desenvolvimento
enquanto funciona dentro do contêiner Linux. O mesmo código agruparia sessões de forma diferente
conforme onde rodasse — e a alternativa seria a dependência `tzdata`, sem justificativa
(regra 92) para um ganho que nenhuma data alcançável exercita.

⚠️ **O que invalida isto**: o Brasil reinstituir horário de verão, ou o projeto adquirir
intraday anterior a 2019. Qualquer um dos dois significa trocar a constante por uma zona real e
assumir a dependência.

## Consequences

**Positivas**

- Um buraco reportado é um fato, não uma inferência. Sobre 529 barras reais: zero erros e
  exatamente um aviso, `SHORT_SESSION` em 2026-07-31.
- Barras fora de fase são preservadas. Sobre 43 sessões do balde `3mo`, o mesmo pregão aparece
  com 17 barras contra 28 típicas — o aviso sobrevive à troca de partição.
- O comportamento é idêntico no Windows e no contêiner.

**Negativas, e assumidas**

- ⚠️ Sessão curta **na borda** do lote não é reportada. É o preço de não gerar falso positivo em
  toda primeira sessão, que a âncora móvel garantiria.
- ⚠️ Um lote em que a maioria das sessões esteja truncada moveria a moda e faria a sessão íntegra
  parecer longa. Nenhum aviso sai daí — `SHORT_SESSION` só dispara para baixo —, mas a referência
  seria a errada.
- `SHORT_SESSION` não distingue abertura tardia de perda de dado. Distinguir exige o calendário
  de pregões da B3, que é dado que o projeto não tem.

## Alternatives considered

**Codificar o horário de pregão da B3 (10:00–17:00) e medir contra ele.** Daria a resposta
absoluta que a comparação por pares não dá. Rejeitada por duas razões que se somam: o horário
mudou ao longo dos anos e tem exceções (véspera de feriado, leilão, circuit breaker), então a
constante estaria errada em silêncio nos casos que mais importam; e o próprio dado desmente a
leitura ingênua — os baldes curtos abrem às 10:15 e o `3mo` às 10:00 para **as mesmas sessões**,
de modo que nem a fonte concorda consigo sobre onde a sessão começa.

**Rejeitar barras fora da grade.** Testada contra o dado real e descartada por ele: teria
descartado as 16 barras de 2026-07-31.

**Reportar sessão curta como erro, não aviso.** Rejeitada porque a sessão curta pode ser o
mercado, não a fonte. Erro significa barra não gravada, e não gravar preços reais para sinalizar
uma incerteza sobre o horário seria mascarar dado — o oposto do que a regra 20 pede.
