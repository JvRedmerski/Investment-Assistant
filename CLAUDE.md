# CLAUDE.md — Protocolo Operacional de Sessão

> Este arquivo define **como trabalhar** neste repositório.
> As regras de engenharia do projeto estão em [AGENTS.md](AGENTS.md) (contrato técnico, prevalece em caso de conflito).
> A memória persistente está em [docs/memory/](docs/memory/).

---

## 1. Inicialização de sessão (leitura mínima obrigatória)

Leia, nesta ordem, **apenas** estes arquivos antes de qualquer trabalho:

1. [docs/memory/PROJECT_CONTEXT.md](docs/memory/PROJECT_CONTEXT.md) — o que é o projeto.
2. [docs/memory/PROJECT_STATUS.md](docs/memory/PROJECT_STATUS.md) — onde o projeto está.
3. [docs/memory/CURRENT_TASK.md](docs/memory/CURRENT_TASK.md) — o que fazer agora.
4. [docs/memory/SESSION_HANDOFF.md](docs/memory/SESSION_HANDOFF.md) — como retomar a última sessão.

Isso é suficiente para saber o que fazer. **Não leia o repositório inteiro.**

---

## 2. Carregamento sob demanda (só quando a tarefa exigir)

| Se a tarefa envolve… | Leia |
|---|---|
| Visão geral de componentes / fluxo de dados | [docs/architecture/SYSTEM_OVERVIEW.md](docs/architecture/SYSTEM_OVERVIEW.md) |
| Backend, camadas, services, integrações | [docs/architecture/BACKEND.md](docs/architecture/BACKEND.md) |
| Frontend React/Vite | [docs/architecture/FRONTEND.md](docs/architecture/FRONTEND.md) |
| Models, migrations, schema | [docs/architecture/DATABASE.md](docs/architecture/DATABASE.md) |
| Endpoints, contratos, erros, auth | [docs/architecture/API.md](docs/architecture/API.md) |
| Alterar área arquitetural já decidida | [docs/decisions/README.md](docs/decisions/README.md) → o ADR específico |
| Planejar wave / entender ordem de entrega | [docs/planning/ROADMAP.md](docs/planning/ROADMAP.md) |
| Padrões de implementação e DoD | [docs/planning/IMPLEMENTATION_GUIDE.md](docs/planning/IMPLEMENTATION_GUIDE.md) |
| Saber o que já foi entregue | [docs/history/COMPLETED_TASKS.md](docs/history/COMPLETED_TASKS.md) |
| Detalhe task-a-task de uma wave passada | [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) (ledger detalhado) |
| Regra de engenharia específica (nº da regra) | [AGENTS.md](AGENTS.md) — vá direto à seção numerada |

Depois disso, inspecione **apenas** os arquivos de código listados em `CURRENT_TASK.md`.

Fluxo: `LEITURA MÍNIMA → CONTEXTO ESPECÍFICO → CÓDIGO RELEVANTE → IMPLEMENTAR`.
Nunca: `LER TUDO → ENTENDER TUDO → COMEÇAR`.

---

## 3. Regras de trabalho

- **O código é a fonte de verdade.** Documentação é checkpoint, não prova. Se divergirem, confie no código e registre a divergência.
- **Preserve a arquitetura existente.** Camadas: `api/routes` → `domain/<área>/service` → `data/models`. Integrações externas sempre atrás de uma interface abstrata em `app/integrations/`.
- **Não crie padrões paralelos.** Antes de escrever um service/utility/schema, procure o equivalente já existente.
- **Não adicione dependências** sem justificar (AGENTS.md §92). Verifique se já existe no `pyproject.toml` / `package.json`.
- **Não refatore fora do escopo.** Problema encontrado fora da task → registre em *Future Work* no `docs/PROJECT_STATUS.md` e siga (AGENTS.md §134).
- **Uma wave por vez** (AGENTS.md §133). Não antecipe waves futuras.
- **Consulte o ADR antes de alterar uma decisão arquitetural.** Se precisar contrariá-lo, explique o impacto e proponha alternativa antes de implementar (AGENTS.md §125), e crie um ADR novo marcando o antigo como `Superseded`.
- **Nunca mascare problemas**: não remova testes, não desabilite lint, não use `any`, não mocke o que deveria ser real.
- **Cálculo financeiro sempre determinístico no backend.** A IA só explica; nunca calcula, nunca decide (AGENTS.md §3).

---

## 4. Validação antes de considerar algo pronto

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q          # baseline atual: 95 passed
.venv\Scripts\python.exe -m ruff check <arquivos alterados>
.venv\Scripts\python.exe -m black --check <arquivos alterados>
```

Lint/format são verificados **nos arquivos alterados** — o repositório tem findings pré-existentes fora do escopo (ver `Known Issues`).

---

## 5. Atualização da memória

Atualize **após** mudança significativa (task concluída, decisão tomada, wave fechada):

| Arquivo | Quando |
|---|---|
| `docs/memory/CURRENT_TASK.md` | sempre que a task atual mudar |
| `docs/memory/SESSION_HANDOFF.md` | ao encerrar a sessão |
| `docs/memory/PROJECT_STATUS.md` | ao concluir task/wave, ou ao descobrir issue real |
| `docs/PROJECT_STATUS.md` | detalhe da task concluída (AGENTS.md §94 — obrigatório) |
| `docs/history/COMPLETED_TASKS.md` | ao concluir uma wave |
| `docs/decisions/ADR-XXX-*.md` | ao tomar decisão arquitetural com alternativas reais |
| `docs/architecture/*.md` | só quando a estrutura/padrão mudar, não a cada arquivo novo |
| `docs/memory/PROJECT_CONTEXT.md` | raramente — só se propósito/stack mudar |

**Não** atualize documentação para alterações triviais (renomear variável, ajustar comentário, corrigir typo).

---

## 6. Commit

Conventional Commits, mensagem em inglês, um commit por task concluída (implementation_prompt §15):

```
feat: add fundamental data ingestion (W06-001)
```
