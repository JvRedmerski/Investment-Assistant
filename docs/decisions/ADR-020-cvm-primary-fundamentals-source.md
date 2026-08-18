# ADR-020 — Dados abertos da CVM como fonte primária de demonstrativos, com a Brapi fazendo a ponte de identidade

## Status

Accepted (2026-08-18, Wave 09 / W09-002)

## Context

Em 2026-08-18 os módulos de demonstrativos da Brapi saíram do plano gratuito (HTTP 403). O parser continuava correto e testado — só não tinha mais o que receber. A ingestão de fundamentals ficou **inoperante por plano, não por código**, e com ela três dos seis sub-scores da Wave 09 (Quality, Valuation, Growth).

O `CURRENT_TASK.md` deixou três saídas registradas: assinar o plano Startup (R$ 119,99/mês), migrar para os dados abertos da CVM, ou entregar a wave com os sub-scores ausentes. A W09-001 entregou o motor de scores com **ausência de primeira classe**, o que tornou a terceira opção viável de imediato. Esta decisão resolve o resto.

Havia ainda um problema que nenhuma das três saídas resolvia sozinha: **a CVM não sabe o que é um ticker**. Seus arquivos identificam a empresa apenas por CNPJ, e não têm coluna de ticker alguma.

## Decision

### 1. A CVM é a fonte **primária** de demonstrativos

`CvmFundamentalsProvider` lê os arquivos DFP de https://dados.cvm.gov.br. É a **própria peça entregue ao regulador**, não a leitura que um fornecedor faz dela — aberta, sem token, sem cota, e com mais de uma década de histórico.

Verificado ao vivo: seis exercícios da PETR4 (2020–2025), todos batendo com o que a companhia publicou — lucro de R$ 188,3 bi em 2022, R$ 124,6 bi em 2023, R$ 36,6 bi em 2024.

### 2. A Brapi continua no projeto, e faz a ponte que a CVM não faz

O `summaryProfile` **continua no plano gratuito** — foram os módulos de demonstrativo que saíram — e ele carrega o CNPJ da empresa. Verificado ao vivo: `PETR4` → `33000167000101`.

É esse o ponto exato onde as duas APIs se fundem, e a fusão não é arbitrária:

| | CVM | Brapi |
|---|---|---|
| conhece ticker | **não** | sim |
| conhece CNPJ | sim | sim |
| entrega demonstrativo | sim, o arquivado | não, saiu do plano |
| cobertura | só companhia aberta brasileira | BDR, ETF, emissor estrangeiro |
| custo | livre, sem cota | cota limitada |

Nenhuma das duas responde "o que a PETR4 reportou" sozinha. Juntas, respondem: **identidade pelo fornecedor, números pelo regulador.**

O CNPJ é gravado em `assets.cnpj` (migration `006`) e resolvido **uma vez**: ele não muda, e perguntar custa requisição de uma cota limitada. Um resultado negativo **não** é memorizado — um ativo pode ser cadastrado antes de o fornecedor conhecê-lo, e gravar "não" tornaria isso permanente sem nada na linha explicando por quê.

### 3. Composição por **período inteiro**. Campos nunca são misturados entre fontes.

`CompositeFundamentalsProvider` tenta a CVM e cai para a Brapi. A versão tentadora de "mesclar" preencheria a lacuna de uma fonte com o campo da outra. **Isso foi rejeitado.**

Duas fontes que calculam a mesma grandeza do mesmo arquivo ainda discordam — sobre consolidado versus controladora, sobre o que conta como dívida, sobre qual linha é "receita" para um banco. Emendar o patrimônio de um fornecedor no resultado da CVM produziria uma linha que **nenhum arquivo jamais reportou**, e o ROE derivado dela seria artefato da emenda. Pior: nada a jusante conseguiria perceber — a linha pareceria igual a qualquer outra.

**Falha não é motivo para cair para a outra fonte.** `FundamentalsNotFoundError` significa "esta fonte não tem esse ativo", que é para isso que existe fallback. Timeout ou payload ilegível significa que a fonte quebrou, e usar a outra em silêncio transformaria uma indisponibilidade em **troca invisível de fonte**. Esses propagam.

### 4. O mapeamento de contas, e como cada uma foi conferida

`CD_CONTA` é código estruturado e padronizado entre declarantes. Conferido contra o DFP 2024 da PETR4, cujos números são públicos:

| campo | código | PETR4 2024 |
|---|---|---|
| `revenue` | `3.01` | R$ 490,8 bi |
| `ebit` | `3.05` | R$ 137,2 bi |
| `income_before_tax` | `3.07` | R$ 54,7 bi |
| `income_tax_expense` | `3.08` | R$ −17,7 bi |
| `net_income` | `3.11.01` | R$ 36,6 bi |
| `equity` | `2.03` − `2.03.09` | R$ 366,0 bi |
| `debt` | `2.01.04` + `2.02.01` | R$ 373,5 bi |
| `cash` | `1.01.01` | R$ 20,3 bi |

**`net_income` é `3.11.01`, não `3.11`.** O segundo é o resultado consolidado **incluindo minoritários** (R$ 37,0 bi na PETR4), e cruzá-lo com um patrimônio da controladora inflaria o ROE pela fatia que o acionista não possui. O patrimônio é líquido dos minoritários pela mesma razão: numerador e denominador precisam descrever os **mesmos donos**. O ROE resultante dá 10,0%, que é o publicado.

**EBITDA é derivado, e o código diz isso.** Nenhum arquivo reporta EBITDA — não é norma contábil. Derivado como `EBIT + |D&A|`, com D&A vindo da DVA em `7.04.01`, presente em 450 das 467 empresas do arquivo de 2024. Na PETR4 dá R$ 204,2 bi, que é o que a companhia reporta. O valor absoluto é deliberado: a DVA apresenta retenções como dedução, então D&A chega negativo em 433 empresas, zero em 16 e **positivo em 3** — o sinal é convenção de apresentação, a magnitude é a grandeza. Onde `7.04.01` falta, `ebitda` fica `None`.

Isso **não** é o "EBITDA ajustado" de uma companhia, que exclui o que aquela companhia resolveu chamar de não recorrente. É a aritmética não ajustada, idêntica para todo declarante — que é o que a torna comparável.

**`free_cash_flow` não é derivado.** A DFC dá investimento líquido (`6.02`), não capex, e os dois diferem por aquisições e aplicações financeiras. Separar capex exige subconta cujo código varia por declarante, então fica `None` em vez de aproximado (regra 44).

### 5. Quatro colunas que mudam a resposta

- **`ESCALA_MOEDA`** é `MIL` na maioria e `UNIDADE` em algumas (550 de 32.776 linhas do DRE 2024). Ignorar subestima a empresa em mil vezes.
- **`ORDEM_EXERC`** é `ÚLTIMO` ou `PENÚLTIMO`: todo arquivo traz o ano anterior como comparativo. Só `ÚLTIMO` é lido — o comparativo é a visão **reexpressa** de um arquivo posterior, e o ano anterior já tem o arquivo dele com o que foi efetivamente arquivado.
- **`VERSAO`** incrementa quando a peça é reentregue. Vence a maior. Ler todas dobraria cada número; ler a primeira reportaria o que a empresa já corrigiu.
- **Só os arquivos `_con_`** (consolidado). Os `_ind_` reportam a controladora isolada, então uma holding apareceria quase sem receita.

### 6. O ano é baixado uma vez e fica em cache

A unidade de recuperação é um ZIP de ~13 MB por exercício, com **todas as companhias** — não há como pedir uma só. O cache não é otimização: é o que torna o acesso por ticker viável. Sem ele, pontuar vinte ativos baixaria os mesmos 13 MB vinte vezes.

Um ano já em disco nunca é rebaixado, o que o congela como foi buscado. Pegar correções republicadas significa apagar o arquivo — ato deliberado, nunca disparado por um caminho de leitura.

## Evidence

- `backend/app/integrations/fundamentals/cvm.py` — provider, mapeamento de contas, cache.
- `backend/app/integrations/fundamentals/identity.py` e `backend/app/domain/fundamentals/identity.py` — a ponte ticker→CNPJ e a memória dela.
- `backend/app/integrations/fundamentals/composite.py` — a regra de período inteiro e a de não cair em falha.
- `backend/migrations/versions/006_assets_cnpj.py` — aplicada em PostgreSQL 16 real.
- `backend/tests/test_cvm_fundamentals_provider.py` — regressão contra as linhas reais do DFP 2024, incluindo o ROE de 10,0%.
- `AGENTS.md` §19, §21, §22, §44, §109; ADR-013 (point-in-time), ADR-014 (dado faltante).

## Alternatives

- **Assinar o plano Startup da Brapi** — rejeitado por ora. Custo recorrente para obter, de segunda mão, o que o regulador publica de graça. Nada impede assinar depois: o composite já tem o lugar.
- **Trocar a Brapi inteiramente pela CVM** — rejeitado. A CVM não cobre BDR, ETF nem emissor estrangeiro, e não conhece ticker. Trocar quebraria a ponte de identidade e a cobertura.
- **Mesclar campo a campo entre as fontes** — rejeitado; ver a decisão 3. Produz linha que nenhum arquivo reportou.
- **Cair para a outra fonte quando a primeira falha** — rejeitado para falha de infraestrutura. Transformaria indisponibilidade em troca silenciosa de fonte.
- **Usar `3.11` (consolidado) como lucro** — rejeitado. Descreve donos diferentes do patrimônio com que seria dividido.
- **Ler os arquivos `_ind_` (controladora)** — rejeitado. Quem compra a ação é dono do grupo.
- **Derivar FCF de `6.01 + 6.02`** — rejeitado. `6.02` não é capex.
- **Baixar o ano a cada consulta, sem cache** — rejeitado. 13 MB por ativo por sync, contra uma fonte pública e gratuita que não merece esse tratamento.
- **Resolver o CNPJ a cada sync** — rejeitado. Gasta cota para reobter um valor que não muda.

## Consequences

- ✅ A ingestão de fundamentals **volta a funcionar**, de graça e com mais histórico do que o fornecedor jamais deu: 6 exercícios da PETR4 na validação, contra os 16 períodos que a Brapi dava antes de fechar.
- ✅ **Quality e Growth deixaram de ser ausentes.** Medido no banco real: os pilares foram de ausentes para 97,8 e 76,7 na PETR4, e a cobertura do score de 40% para 55% — **sem uma linha alterada em `scoring.py`**, que é exatamente o que o desenho da W09-001 prometia.
- ✅ **`ebitda_margin` e `debt_ebitda` saíram do `None`** (Known Issue 9, resolvida em parte): a Brapi copiava `ebit` em `cleanEbitda`; a CVM permite derivar EBITDA de verdade.
- ✅ **Reexpressões passam a ser visíveis** via `VERSAO`, coisa que o fornecedor nunca expôs (Known Issue 11 fica endereçável).
- ⚠️ `pe`, `pb` e `dy` **continuam ausentes**. Faltam ações em circulação por período — e o arquivo `composicao_capital` do próprio DFP as traz, com ações em tesouraria. É o próximo passo natural, e destravaria o pilar de Valuation inteiro.
- ⚠️ Cobertura da CVM é só **companhia aberta brasileira**. FII, ETF e BDR não têm DFP e nunca terão; para eles os pilares fundamentalistas ficam permanentemente ausentes, o que o motor de score já trata como estado normal.
- ⚠️ **Bancos e seguradoras usam plano de contas diferente.** `3.01` do Banco do Brasil é "Receitas de Intermediação Financeira", e `2.01.04` pode não existir. O mapeamento aceita o que houver e deixa `None` no resto, mas os números de um banco merecem conferência antes de virarem score.
- ⚠️ Cada exercício adicional é outro download de ~13 MB em disco. `CVM_FIRST_YEAR` tem default 2020.
