/**
 * The handful of pieces every screen is built from.
 *
 * Deliberately small and unstyled-by-configuration: this wave needs a
 * legible dashboard, not a design system. Wave 22 is where the frontend
 * gets ambitious.
 *
 * ## `Stat` renders absence, and says why
 *
 * A tile with no value shows a dash and, where the caller supplies one,
 * the reason it is missing. That is rule 44 as a component: an absent
 * volatility is not a calm one, and a screen that renders `0,0%` for
 * "not enough history" states something false.
 */

import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';
import { ABSENT } from '@/lib/format';

export function Card({
  title,
  subtitle,
  action,
  children,
  className,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        'rounded-xl border border-slate-800 bg-slate-900/60 p-5',
        className,
      )}
    >
      {(title || action) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && (
              <h2 className="text-sm font-semibold text-slate-200">{title}</h2>
            )}
            {subtitle && (
              <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
            )}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = 'neutral',
  missingReason,
}: {
  label: string;
  value: string;
  hint?: ReactNode;
  tone?: 'neutral' | 'positive' | 'negative';
  /** Shown instead of `hint` when `value` is absent. */
  missingReason?: string;
}) {
  const absent = value === ABSENT;
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p
        className={cn(
          'mt-1 text-2xl font-semibold tabular-nums',
          absent && 'text-slate-600',
          !absent && tone === 'positive' && 'text-emerald-400',
          !absent && tone === 'negative' && 'text-rose-400',
          !absent && tone === 'neutral' && 'text-slate-100',
        )}
      >
        {value}
      </p>
      {absent && missingReason ? (
        <p className="mt-1 text-xs text-amber-500/80">{missingReason}</p>
      ) : (
        hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>
      )}
    </div>
  );
}

export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'neutral' | 'positive' | 'negative' | 'warning';
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium',
        tone === 'neutral' && 'bg-slate-800 text-slate-300',
        tone === 'positive' && 'bg-emerald-500/10 text-emerald-400',
        tone === 'negative' && 'bg-rose-500/10 text-rose-400',
        tone === 'warning' && 'bg-amber-500/10 text-amber-400',
      )}
    >
      {children}
    </span>
  );
}

/**
 * The line under a chart that says what it is showing.
 *
 * Rule 74 asks a chart to state its período, unidade, benchmark, moeda,
 * fonte and atualização. Making that a component rather than a habit is
 * what keeps it from being forgotten on the third chart.
 */
export function ChartCaption({
  period,
  unit,
  benchmark,
  currency,
  sources,
  updated,
}: {
  period?: string;
  unit?: string;
  benchmark?: string | null;
  currency?: string;
  sources?: string[];
  updated?: string | null;
}) {
  const parts = [
    period && `Período: ${period}`,
    unit && `Unidade: ${unit}`,
    currency && `Moeda: ${currency}`,
    benchmark && `Benchmark: ${benchmark}`,
    sources?.length && `Fonte: ${sources.join(', ')}`,
    updated && `Atualizado até ${updated}`,
  ].filter(Boolean);

  if (parts.length === 0) return null;
  return (
    <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
      {parts.join(' · ')}
    </p>
  );
}

export function Spinner({ label = 'Carregando…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-8 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-700 border-t-sky-400" />
      {label}
    </div>
  );
}

/**
 * A failed request, shown as what it was.
 *
 * The backend's own message is displayed rather than a generic one:
 * "Sector Bancos is at or above the 40.0% ceiling" tells the investor
 * something, and "algo deu errado" does not.
 */
export function ErrorNote({ error }: { error: unknown }) {
  const message =
    error instanceof Error ? error.message : 'Erro desconhecido.';
  return (
    <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-4 text-sm text-rose-300">
      {message}
    </div>
  );
}

export function EmptyNote({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-slate-800 p-6 text-center text-sm text-slate-500">
      {children}
    </p>
  );
}

/**
 * A warning that the numbers on screen do not cover everything.
 *
 * Used wherever the backend reports a partial answer — unpriced
 * positions, an unassigned share of the target — because the whole
 * design of those endpoints is that the gap comes back named, and a
 * screen that drops it undoes that.
 */
export function CoverageNote({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-300">
      {children}
    </p>
  );
}
