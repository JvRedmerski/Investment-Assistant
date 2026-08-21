/**
 * The charts, and the rules they are drawn under (AGENTS.md rule 74).
 *
 * Rule 74 is blunt: *"Não criar gráficos visualmente bonitos mas
 * financeiramente ambíguos."* Three things follow from it here.
 *
 * **A series is never smoothed or interpolated.** The backend leaves a
 * date out when the portfolio could not be valued that day, and that gap
 * is real — inventing a point to make a line continuous is fabricating a
 * price (rule 44). Recharts is told to connect nothing across nulls.
 *
 * **Two lines that mean different things never share an axis** unless
 * they are the same unit. The wealth chart plots BRL against BRL; the
 * performance chart plots two rebased indices, both starting at 100 on
 * the same day because `align` put them there.
 *
 * **Every chart carries its caption.** `<ChartCaption>` states period,
 * unit, currency, benchmark, source and how fresh the data is, which is
 * the six things rule 74 names.
 */

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { money, shortDate } from '@/lib/format';

const AXIS = {
  stroke: '#475569',
  fontSize: 11,
  tickLine: false,
  axisLine: false,
} as const;

const TOOLTIP_STYLE = {
  backgroundColor: '#0f172a',
  border: '1px solid #1e293b',
  borderRadius: '0.5rem',
  fontSize: '12px',
} as const;

function tickDate(value: string): string {
  return shortDate(value).slice(0, 5);
}

/**
 * Patrimônio over time, with the money put in underneath it.
 *
 * The second line is the entire point of the first one. A curve that
 * doubled because R$ 1.000 arrived every month is visually identical to
 * one that doubled on returns; drawing the contributions under it is
 * what tells them apart, and is why the backend returns both.
 */
export function WealthChart({
  points,
}: {
  points: { date: string; value: string; invested: string }[];
}) {
  const data = points.map((point) => ({
    date: point.date,
    valor: Number(point.value),
    aportado: Number(point.invested),
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={data} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="wealth" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#1e293b" vertical={false} />
        <XAxis dataKey="date" tickFormatter={tickDate} {...AXIS} minTickGap={40} />
        <YAxis
          {...AXIS}
          width={70}
          tickFormatter={(value: number) =>
            value >= 1000 ? `${Math.round(value / 1000)}k` : String(value)
          }
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelFormatter={(label: string) => shortDate(label)}
          formatter={(value: number, name: string) => [money(String(value)), name]}
        />
        <Area
          type="linear"
          dataKey="valor"
          stroke="#38bdf8"
          strokeWidth={2}
          fill="url(#wealth)"
          connectNulls={false}
          dot={false}
          name="Valor de mercado"
        />
        <Area
          type="linear"
          dataKey="aportado"
          stroke="#64748b"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          fill="none"
          connectNulls={false}
          dot={false}
          name="Aportado"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/**
 * The portfolio's time-weighted index against a benchmark.
 *
 * Both series arrive rebased to the same level on the same date, so the
 * comparison is honest by construction rather than by the reader
 * checking two start dates in a caption.
 */
export function PerformanceChart({
  index,
  benchmark,
  benchmarkName,
}: {
  index: { date: string; value: string }[];
  benchmark: { date: string; value: string }[];
  benchmarkName?: string | null;
}) {
  const byDate = new Map<string, { date: string; carteira?: number; bench?: number }>();
  for (const point of index) {
    byDate.set(point.date, { date: point.date, carteira: Number(point.value) });
  }
  for (const point of benchmark) {
    const existing = byDate.get(point.date) ?? { date: point.date };
    existing.bench = Number(point.value);
    byDate.set(point.date, existing);
  }
  const data = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#1e293b" vertical={false} />
        <XAxis dataKey="date" tickFormatter={tickDate} {...AXIS} minTickGap={40} />
        <YAxis {...AXIS} width={50} domain={['auto', 'auto']} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelFormatter={(label: string) => shortDate(label)}
          formatter={(value: number, name: string) => [value.toFixed(2), name]}
        />
        <Line
          type="linear"
          dataKey="carteira"
          stroke="#38bdf8"
          strokeWidth={2}
          dot={false}
          connectNulls={false}
          name="Carteira"
        />
        {benchmark.length > 0 && (
          <Line
            type="linear"
            dataKey="bench"
            stroke="#a78bfa"
            strokeWidth={2}
            dot={false}
            connectNulls={false}
            name={benchmarkName ?? 'Benchmark'}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}

/**
 * Composition, as bars rather than a pie.
 *
 * A pie makes two nearby slices indistinguishable and hides the one
 * number that matters here — how close a holding is to the concentration
 * ceiling. Bars against a common axis show that at a glance.
 */
export function CompositionBars({
  rows,
}: {
  rows: { label: string; weight: number; amount: string | null }[];
}) {
  const max = Math.max(...rows.map((row) => row.weight), 0.2);
  return (
    <ul className="space-y-2.5">
      {rows.map((row) => (
        <li key={row.label} className="text-sm">
          <div className="flex items-baseline justify-between gap-3">
            <span className="font-medium text-slate-200">{row.label}</span>
            <span className="tabular-nums text-slate-400">
              {(row.weight * 100).toLocaleString('pt-BR', {
                minimumFractionDigits: 1,
                maximumFractionDigits: 1,
              })}
              % · {money(row.amount)}
            </span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-sky-500"
              style={{ width: `${Math.min((row.weight / max) * 100, 100)}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}


/**
 * One asset's close over time.
 *
 * The **unadjusted** close, and the caption says so. The adjusted series
 * is a total-return price and would show a 2020 position at a fraction
 * of what the shares changed hands for — right for measuring return,
 * wrong for a chart labelled "preço".
 */
export function PriceChart({
  points,
}: {
  points: { date: string; close: string }[];
}) {
  const data = points.map((point) => ({
    date: point.date,
    fechamento: Number(point.close),
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#1e293b" vertical={false} />
        <XAxis dataKey="date" tickFormatter={tickDate} {...AXIS} minTickGap={50} />
        <YAxis {...AXIS} width={55} domain={['auto', 'auto']} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelFormatter={(label: string) => shortDate(label)}
          formatter={(value: number) => [money(String(value)), 'Fechamento']}
        />
        <Line
          type="linear"
          dataKey="fechamento"
          stroke="#38bdf8"
          strokeWidth={1.5}
          dot={false}
          connectNulls={false}
          name="Fechamento"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
