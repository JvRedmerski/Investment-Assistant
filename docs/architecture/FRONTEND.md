# Frontend Architecture

> Camada 2. Leia quando a task tocar o frontend.
> Estado em 2026-08-21: **aplicação real**, desde a W11-003. Antes disso era só uma landing page estática.

## Estrutura real

```
frontend/src/
├── main.tsx              providers: QueryClient → BrowserRouter → AuthProvider
├── App.tsx               tabela de rotas + RequireAuth
├── index.css             Tailwind + .glass-card
├── lib/
│   ├── api.ts            ⭐ a única porta para o backend
│   ├── format.ts         dinheiro, percentual, p.p., datas, defasagem (pt-BR)
│   └── cn.ts             clsx + tailwind-merge
├── types/api.ts          contratos como schemas zod, e os tipos inferidos deles
├── hooks/
│   ├── useAuth.tsx       sessão, token, login/registro/logout
│   └── queries.ts        um hook react-query por endpoint
├── components/
│   ├── ui.tsx            Card · Stat · Badge · ChartCaption · Spinner · ErrorNote · CoverageNote
│   └── charts.tsx        WealthChart · PerformanceChart · CompositionBars (recharts)
├── layouts/AppLayout.tsx shell, navegação e o seletor de carteira (na URL)
└── pages/                LoginPage · DashboardPage · PortfolioPage · AssetsPage
```

⚠️ **`.gitignore` tem `backend/lib/`, ancorado de propósito.** A entrada `lib/` do template Python casa em qualquer profundidade e estava engolindo `frontend/src/lib/` inteiro — o cliente de API não teria sido commitado. Descoberto na W11-003, antes do commit que o teria perdido. Negação não resolve: o git não desce em diretório excluído.

## Comunicação com a API

`src/lib/api.ts` é o **único** ponto de contato, e faz quatro coisas que nenhum outro arquivo repete:

1. prefixa a base URL (`VITE_API_URL`, default `http://localhost:8000/api/v1`);
2. anexa o bearer token;
3. desembrulha o envelope `{"error":{"code","message"}}` (regra 72) num `ApiError` **com o código**, que é no que o chamador ramifica — nunca na mensagem, que é prosa;
4. **valida a resposta** contra um schema `zod`.

**Por que validar tudo.** A regra 10 pede `unknown` + validação explícita em vez de cast. Um cast é uma promessa que o compilador acredita e ninguém confere: renomeie um campo no backend e a tela renderiza `undefined` onde deveria haver um número, em silêncio. É o mesmo argumento que o backend faz sobre dado externo ser hostil (regra 19) — a API é externa a este código também.

Erro de contrato tem classe própria (`ContractError`), distinta de `ApiError`: uma quer dizer *o backend recusou*, a outra *o backend e este cliente discordam sobre o formato da resposta*. Pedem correções diferentes.

**Dinheiro continua `string`.** O backend serializa `Decimal` como string exatamente para não passar por float binário; converter para `number` aqui desfaria isso no único salto em que estava protegido. Os schemas mantêm `string` e `lib/format.ts` é o que transforma em texto legível.

## Estado e roteamento

`@tanstack/react-query` com `staleTime` de 60 s e sem refetch no foco — todo dado vem de leitura do banco que o backend atualiza no próprio ritmo, e abrir tela nunca dispara chamada externa (regra 23). `retryPolicy` **não** repete resposta `4xx`: 404 e 401 são respostas, não falhas.

`react-router-dom` com todas as rotas atrás de `RequireAuth`, que espera `/auth/me` responder antes de decidir — piscar a tela de login para quem está logado é pior que um instante em branco.

A **carteira selecionada vive na URL** (`?portfolio=`), não em estado global: todo endpoint do projeto é escopado a uma carteira, então um link para uma tela carrega a carteira de que ele falava.

## Regras que o frontend cumpre, e onde

| regra | onde |
|---|---|
| §73 — zero lógica financeira no frontend | nenhuma página faz aritmética; `lib/format.ts` só move vírgula |
| §74 — gráfico declara período, unidade, benchmark, moeda, fonte, atualização | `<ChartCaption>` existe para isso não ser esquecido no terceiro gráfico |
| §74 — nada de bonito e ambíguo | `connectNulls={false}` em toda série: vão na valorização é vão de verdade, e ligar os pontos inventaria preço (§44). Composição em barras, não pizza — pizza esconde a distância até o teto |
| §75 — não otimizar prematuramente | o bundle passa de 500 kB por causa do recharts e o aviso do Vite fica de pé; dividir chunk é trabalho da W22 |
| §103/§104 — dado defasado é rotulado | `format.staleness()` + `<CoverageNote>`; a tela de carteira mostra a data do preço mais antigo |
| ADR-014 — ausência é ausência | todo formatador aceita `null` e devolve `—`; `<Stat>` mostra o motivo. **Nunca `?? 0`** |
| §10 — contrato tipado, `zod` para dado externo | `types/api.ts`, validado em `lib/api.ts` |

## Validação

- `npm run build` e `npm run lint` limpos (ESLint 10, `--max-warnings 0`).
- **Os 14 schemas foram validados contra respostas reais** de um backend rodando com o banco de
  desenvolvimento — o mesmo procedimento que o `IMPLEMENTATION_GUIDE` exige de provedor externo,
  aplicado ao contrato da própria API. Não há teste automatizado disso ainda; ver Future Work.

## Comandos

```powershell
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # tsc && vite build
npm run lint
```
