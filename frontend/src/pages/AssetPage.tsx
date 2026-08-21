/**
 * One asset: price, fundamentals, history and score (roadmap §23).
 *
 * The score panel is the reason this screen exists rather than being a
 * row on the assets list. A single number between 0 and 100 invites
 * exactly the reading the project refuses — that it ranks assets — so
 * here it is always shown decomposed, with its coverage next to it and
 * the missing pillars named.
 *
 * ## Coverage is shown before the score, not after it
 *
 * `scoring.py` says it plainly: two scores resting on different amounts
 * of evidence are not comparable, however alike the numbers look. This
 * project's own database has ITUB4 at 92.5 on 40% coverage — the highest
 * figure in the universe, assembled from the only two pillars that never
 * go missing. A screen that shows 92.5 in large type and the coverage in
 * a footnote has reproduced the trap the backend spent a wave defusing.
 */

import { useParams } from 'react-router-dom';

import { PriceChart } from '@/components/charts';
import {
  Badge,
  Card,
  ChartCaption,
  CoverageNote,
  EmptyNote,
  ErrorNote,
  Spinner,
  Stat,
} from '@/components/ui';
import {
  useAssetPrices,
  useAssets,
  useCorporateActions,
  useIndicators,
  useRebalance,
  useScores,
} from '@/hooks/queries';
import { useSelectedPortfolio } from '@/layouts/AppLayout';
import { decimal, money, percent, points, shortDate } from '@/lib/format';
import type { SubScore } from '@/types/api';

const PILLAR_LABEL: Record<string, string> = {
  quality: 'Qualidade',
  valuation: 'Preço',
  growth: 'Crescimento',
  risk: 'Risco',
  diversification: 'Diversificação',
};

/**
 * Read off `CorporateActionKind`, not guessed.
 *
 * The first draft of this map invented `STOCK_DIVIDEND` and
 * `NOMINAL_UPDATE`, neither of which the backend emits, and missed
 * `INCOME` and `BONUS`, which the real database is full of. Checking the
 * enum took a minute; the fallback below is what kept it from being
 * silent in the meantime.
 */
const ACTION_LABEL: Record<string, string> = {
  CASH_DIVIDEND: 'Dividendo',
  INTEREST_ON_CAPITAL: 'JCP',
  INCOME: 'Rendimento',
  CAPITAL_RETURN: 'Restituição de capital',
  BONUS: 'Bonificação',
  SPLIT: 'Desdobramento',
  REVERSE_SPLIT: 'Grupamento',
};

/** Indicators are ratios; the multiples are dimensionless. */
const INDICATORS: { key: keyof Indicators; label: string; kind: 'pct' | 'x' }[] = [
  { key: 'roe', label: 'ROE', kind: 'pct' },
  { key: 'roic', label: 'ROIC', kind: 'pct' },
  { key: 'net_margin', label: 'Margem líquida', kind: 'pct' },
  { key: 'ebitda_margin', label: 'Margem EBITDA', kind: 'pct' },
  { key: 'dy', label: 'Dividend yield', kind: 'pct' },
  { key: 'revenue_growth', label: 'Cresc. receita', kind: 'pct' },
  { key: 'profit_growth', label: 'Cresc. lucro', kind: 'pct' },
  { key: 'pe', label: 'P/L', kind: 'x' },
  { key: 'pb', label: 'P/VP', kind: 'x' },
  { key: 'debt_ebitda', label: 'Dívida/EBITDA', kind: 'x' },
];

type Indicators = {
  roe: number | null;
  roic: number | null;
  net_margin: number | null;
  ebitda_margin: number | null;
  dy: number | null;
  revenue_growth: number | null;
  profit_growth: number | null;
  pe: number | null;
  pb: number | null;
  debt_ebitda: number | null;
};

export function AssetPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const { selected } = useSelectedPortfolio();

  const assets = useAssets();
  const prices = useAssetPrices(ticker);
  const indicators = useIndicators(ticker);
  const actions = useCorporateActions(ticker);
  const scores = useScores(selected?.id);
  const rebalance = useRebalance(selected?.id);

  const asset = assets.data?.find((item) => item.ticker === ticker);
  const score = scores.data?.scores.find((item) => item.ticker === ticker);
  const target = rebalance.data?.targets.find((item) => item.ticker === ticker);
  const latest = indicators.data?.[indicators.data.length - 1];
  const lastBar = prices.data?.[prices.data.length - 1];

  if (assets.isLoading) return <Spinner />;
  if (assets.error) return <ErrorNote error={assets.error} />;
  if (!asset) return <EmptyNote>Ativo {ticker} não está cadastrado.</EmptyNote>;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-xl font-semibold text-slate-100">{asset.ticker}</h1>
        <span className="text-sm text-slate-400">{asset.name}</span>
        <Badge>{asset.sector ?? 'setor não informado'}</Badge>
        {!asset.is_active && <Badge tone="warning">inativo</Badge>}
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Último fechamento"
          value={money(lastBar?.close)}
          hint={
            lastBar
              ? `${shortDate(lastBar.date)} · ${lastBar.source}`
              : undefined
          }
          missingReason="Nenhum preço armazenado. Rode o backfill."
        />
        <Stat
          label="Peso na carteira"
          value={percent(target?.current_weight)}
          hint={selected?.name}
        />
        <Stat
          label="Peso-alvo"
          value={target?.excluded ? '—' : percent(target?.target_weight)}
          hint={target && !target.excluded ? target.detail : undefined}
          missingReason={target?.detail}
        />
        <Stat
          label="Distância do alvo"
          value={target?.excluded ? '—' : points(target?.weight_gap)}
          hint={target?.status === 'UNDER' ? 'Abaixo do alvo' : undefined}
          missingReason="Sem alvo, logo sem distância até ele."
        />
      </div>

      {/* -- histórico ---------------------------------------------- */}
      <Card
        title="Histórico de preço"
        subtitle="Fechamento não ajustado — o que o mercado imprimiu."
      >
        {prices.isLoading ? (
          <Spinner />
        ) : prices.error ? (
          <ErrorNote error={prices.error} />
        ) : (prices.data?.length ?? 0) === 0 ? (
          <EmptyNote>
            Sem histórico armazenado. Use{' '}
            <code>POST /assets/{asset.ticker}/prices/backfill</code>.
          </EmptyNote>
        ) : (
          <>
            <PriceChart points={prices.data!} />
            <ChartCaption
              period={`${shortDate(prices.data![0].date)} – ${shortDate(
                lastBar!.date,
              )}`}
              unit="Fechamento não ajustado"
              currency="BRL"
              sources={[...new Set(prices.data!.map((bar) => bar.source))]}
              updated={lastBar!.date}
            />
          </>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* -- score ------------------------------------------------- */}
        <Card
          title="Score"
          subtitle="Relativo a esta carteira: o pilar de Diversificação lê o que você já tem."
        >
          {scores.isLoading ? (
            <Spinner />
          ) : !score ? (
            <EmptyNote>Sem score para este ativo.</EmptyNote>
          ) : (
            <div className="space-y-4">
              <CoverageNote>
                Este score se apoia em{' '}
                <strong>{percent(score.coverage)}</strong> da fórmula. Dois scores
                com coberturas diferentes <strong>não são comparáveis</strong>,
                por mais parecidos que os números pareçam.
              </CoverageNote>

              <div className="flex items-baseline gap-3">
                <span className="text-3xl font-semibold tabular-nums text-slate-100">
                  {decimal(score.final_score)}
                </span>
                <span className="text-xs text-slate-500">
                  de 100 · fórmula {score.formula_version}
                </span>
              </div>

              <ul className="space-y-2">
                {score.sub_scores.map((sub) => (
                  <PillarRow key={sub.name} sub={sub} />
                ))}
              </ul>
            </div>
          )}
        </Card>

        {/* -- fundamentos ------------------------------------------- */}
        <Card
          title="Indicadores fundamentalistas"
          subtitle={
            latest
              ? `Exercício de ${shortDate(latest.reference_date)}`
              : undefined
          }
        >
          {indicators.isLoading ? (
            <Spinner />
          ) : !latest ? (
            <EmptyNote>
              Nenhum demonstrativo ingerido para {asset.ticker}.
            </EmptyNote>
          ) : (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5 text-sm">
              {INDICATORS.map(({ key, label, kind }) => {
                const raw = latest[key];
                return (
                  <div key={key} className="flex items-baseline justify-between">
                    <dt className="text-slate-400">{label}</dt>
                    <dd className="tabular-nums text-slate-200">
                      {raw === null
                        ? '—'
                        : kind === 'pct'
                          ? percent(String(raw))
                          : `${decimal(String(raw))}×`}
                    </dd>
                  </div>
                );
              })}
            </dl>
          )}
          <p className="mt-4 text-[11px] text-slate-600">
            Um traço significa que o indicador não era computável no período —
            nunca zero.
          </p>
        </Card>
      </div>

      {/* -- eventos societários ------------------------------------- */}
      <Card
        title="Eventos societários"
        subtitle="Data e magnitude vindas da própria B3; é o que torna a série de retorno total possível."
      >
        {actions.isLoading ? (
          <Spinner />
        ) : (actions.data?.length ?? 0) === 0 ? (
          <EmptyNote>
            Nenhum evento armazenado. Rode{' '}
            <code>POST /assets/{asset.ticker}/corporate-actions/sync</code> depois
            do backfill.
          </EmptyNote>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="pb-2 pr-4 font-medium">Data-ex</th>
                  <th className="pb-2 pr-4 font-medium">Natureza</th>
                  <th className="pb-2 pr-4 text-right font-medium">Por ação</th>
                  <th className="pb-2 text-right font-medium">Fator</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {[...(actions.data ?? [])]
                  .reverse()
                  .slice(0, 15)
                  .map((action) => (
                    <tr key={action.id}>
                      <td className="py-2 pr-4 text-slate-300">
                        {shortDate(action.ex_date)}
                      </td>
                      <td className="py-2 pr-4 text-slate-300">
                        {ACTION_LABEL[action.kind] ?? action.kind}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums text-slate-300">
                        {money(action.cash_amount)}
                      </td>
                      <td className="py-2 text-right tabular-nums text-slate-300">
                        {action.share_ratio === null
                          ? '—'
                          : `${decimal(action.share_ratio)}×`}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <p className="text-[11px] text-slate-600">
        Carteira em contexto: {selected?.name ?? '—'}. Um score é uma leitura
        quantitativa dos dados armazenados, não uma previsão.
      </p>
    </div>
  );
}

/**
 * One pillar, with its weight and what was missing from it.
 *
 * An absent pillar is drawn as absent — no bar, and the inputs that
 * were unavailable named — because "Risco: —, faltou beta" is an answer
 * and "Risco: 0" is a false statement about an asset.
 */
function PillarRow({ sub }: { sub: SubScore }) {
  const value = sub.value === null ? null : Number(sub.value);
  return (
    <li className="text-sm">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-slate-300">
          {PILLAR_LABEL[sub.name] ?? sub.name}
          <span className="ml-2 text-xs text-slate-600">
            peso {percent(sub.weight, 0)}
          </span>
        </span>
        <span className="tabular-nums text-slate-200">
          {value === null ? '—' : decimal(sub.value)}
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
        {value !== null && (
          <div
            className="h-full rounded-full bg-sky-500"
            style={{ width: `${Math.min(value, 100)}%` }}
          />
        )}
      </div>
      {sub.missing.length > 0 && (
        <p className="mt-1 text-[11px] text-amber-500/80">
          Sem dado para: {sub.missing.join(', ')}
        </p>
      )}
    </li>
  );
}
