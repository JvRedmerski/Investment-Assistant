# Frontend Architecture

> Camada 2. Leia quando a task tocar o frontend.
> Estado em 2026-08-19: **scaffold apenas**. Não há aplicação de produto ainda.

## Aviso importante

O que existe é uma landing page estática que exibe o status do backend e descreve a arquitetura planejada. O `README.md` e o `docs/PROJECT_STATUS.md` marcavam o frontend como "🟢 COMPLETED"; ambos foram corrigidos para **🟡 SCAFFOLD** em 2026-08-19, porque o rótulo anterior lia-se como produto entregue. A primeira wave de frontend de verdade é a **W11**.

Nenhuma funcionalidade do backend (login, carteiras, transações, posições, preços) está exposta na UI.

## Estrutura real

```
frontend/
├── index.html
├── src/
│   ├── main.tsx            React 18 createRoot + StrictMode
│   ├── App.tsx             página única, JSX estático + fetch de /health
│   ├── index.css           Tailwind + classe utilitária .glass-card
│   └── services/
│       └── api.ts          API_URL + fetchHealth()
├── vite.config.ts          alias `@` → ./src, host 0.0.0.0, porta 5173
├── tailwind.config.js · postcss.config.js
├── tsconfig.json · tsconfig.node.json
├── package.json
└── Dockerfile
```

**Não existem** (previstos no AGENTS.md §6): `components/`, `pages/`, `hooks/`, `types/`, `utils/`, `layouts/`.

## Roteamento

Não existe. `react-router-dom` está no `package.json` mas não é importado por nenhum arquivo.

## Gerenciamento de estado

Não existe. `@tanstack/react-query` está instalado mas não é usado; `App.tsx` usa `useState` + `useEffect` diretamente.

## Comunicação com a API

`src/services/api.ts` é o único ponto de contato:

```ts
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
export async function fetchHealth(): Promise<HealthResponse>
```

`fetch` nativo, tipagem manual via interface, erro convertido em `Error` com mensagem em português. Não há interceptor, não há injeção de `Authorization`, não há tratamento do envelope `{"error":{"code","message"}}` do backend.

## Dependências instaladas mas não utilizadas

`react-router-dom`, `@tanstack/react-query`, `recharts`, `zod`, `clsx`, `tailwind-merge`.
Elas indicam a intenção arquitetural registrada no AGENTS.md §5.1 — use-as quando a Wave 11 (Dashboard) começar, em vez de adicionar equivalentes.

## Padrões esperados quando o frontend for construído (Wave 11+)

Ainda não estabelecidos em código; derivados do AGENTS.md:

- TypeScript estrito; evitar `any`, preferir `unknown` + validação explícita (§10).
- Todo contrato de API tipado; usar `zod` para validar resposta externa (§10).
- **Zero lógica financeira no frontend** (§73/§24) — nenhum cálculo de retorno, risco ou score. O frontend só apresenta o que o backend calculou.
- Gráficos devem deixar explícitos período, unidade, benchmark, moeda, fonte e data de atualização (§74).
- Linguagem da UI: "setup detectado", "sinal quantitativo". Nunca "vai subir", "lucro garantido" (§56).
- Dado defasado deve ser rotulado como tal, nunca apresentado como tempo real (§103/§104).

## Baseline verificado (2026-08-21, abertura da W11)

`npm run build` e `npm run lint` **passam limpos**. O `eslint.config.js` existe e o ESLint 10 está nas `devDependencies` desde a FIX-001 (2026-08-19) — este documento afirmava o contrário até a abertura da Wave 11, e o código é a fonte de verdade (CLAUDE.md §3).

Build de referência: 1.484 módulos, `index.js` 154 kB (49 kB gzip).

## Comandos

```powershell
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # tsc && vite build
```
