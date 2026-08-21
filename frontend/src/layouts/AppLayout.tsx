/**
 * The shell every signed-in screen sits in.
 *
 * It also owns the portfolio the app is looking at. Every endpoint in
 * this project is scoped to one portfolio, so the choice belongs above
 * the screens rather than being re-made inside each of them — and it
 * lives in the URL (`?portfolio=`) so a link to a screen carries the
 * portfolio it was about.
 */

import { NavLink, Outlet, useSearchParams } from 'react-router-dom';
import { LogOut, TrendingUp } from 'lucide-react';

import { Spinner } from '@/components/ui';
import { usePortfolios } from '@/hooks/queries';
import { useAuth } from '@/hooks/useAuth';
import { cn } from '@/lib/cn';

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/carteira', label: 'Carteira', end: false },
  { to: '/ativos', label: 'Ativos', end: false },
];

/** Reads the portfolio in the URL, defaulting to the first one owned. */
export function useSelectedPortfolio() {
  const [params] = useSearchParams();
  const { data: portfolios } = usePortfolios();
  const fromUrl = Number(params.get('portfolio'));

  const selected =
    portfolios?.find((item) => item.id === fromUrl) ?? portfolios?.[0];

  return { portfolios: portfolios ?? [], selected };
}

export function AppLayout() {
  const { user, signOut } = useAuth();
  const [params, setParams] = useSearchParams();
  const { portfolios, selected } = useSelectedPortfolio();
  const loading = portfolios.length === 0 && selected === undefined;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <div className="flex items-center gap-2 text-sky-400">
            <TrendingUp className="h-5 w-5" />
            <span className="text-sm font-semibold text-slate-100">
              Investment Assistant
            </span>
          </div>

          <nav className="flex items-center gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={{ pathname: item.to, search: params.toString() }}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    'rounded-md px-3 py-1.5 text-sm',
                    isActive
                      ? 'bg-slate-800 text-slate-100'
                      : 'text-slate-400 hover:text-slate-200',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            {portfolios.length > 0 && (
              <select
                value={selected?.id ?? ''}
                onChange={(event) => {
                  const next = new URLSearchParams(params);
                  next.set('portfolio', event.target.value);
                  setParams(next);
                }}
                className="rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-sm text-slate-200"
                aria-label="Carteira"
              >
                {portfolios.map((portfolio) => (
                  <option key={portfolio.id} value={portfolio.id}>
                    {portfolio.name}
                  </option>
                ))}
              </select>
            )}
            <span className="hidden text-xs text-slate-500 sm:inline">
              {user?.email}
            </span>
            <button
              type="button"
              onClick={signOut}
              className="rounded-md p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              aria-label="Sair"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {loading ? <Spinner label="Carregando carteiras…" /> : <Outlet />}
      </main>

      <footer className="mx-auto max-w-7xl px-4 pb-8 text-[11px] leading-relaxed text-slate-600">
        Ferramenta de análise e pesquisa. Não é recomendação de investimento,
        não executa ordens e não promete rentabilidade. Todo número desta tela
        é calculado no backend a partir de dados armazenados.
      </footer>
    </div>
  );
}
