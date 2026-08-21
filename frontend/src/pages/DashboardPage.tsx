/**
 * The screen the whole project was built to produce (roadmap §23).
 *
 * It answers, in order: how much do I have, is it beating the CDI, how
 * much risk am I carrying, what is it made of, and where does the next
 * R$ 1.000 go. Every number is fetched already computed — this file
 * contains no arithmetic beyond turning a fraction into a bar width
 * (rule 73).
 *
 * ## What it refuses to do
 *
 * **It does not fill a gap.** Where the backend answers `null` the tile
 * shows a dash and, where there is one, the reason. A volatility that
 * could not be computed is not a calm portfolio.
 *
 * **It does not present a partial total as a whole one.** Both the
 * positions endpoint and the target model report what their totals leave
 * out, and both warnings are on this screen. A patrimônio covering three
 * of four holdings, shown without comment, is the most expensive kind of
 * plausible number.
 *
 * **It does not tell anyone what will happen.** Rule 56: the language is
 * "abaixo do peso-alvo", never "vai subir".
 */

import { useState } from 'react';
import { AlertTriangle, ArrowRight } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';

import { CompositionBars, PerformanceChart, WealthChart } from '@/components/charts';
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
  useBenchmarkComparison,
  usePortfolioSeries,
  usePositions,
  useRebalance,
  useRebalancePlan,
} from '@/hooks/queries';
import { useSelectedPortfolio } from '@/layouts/AppLayout';
import type { PortfolioSeries } from '@/types/api';
import { cn } from '@/lib/cn';
import {
  decimal,
  money,
  percent,
  points,
  shortDate,
  staleness,
} from '@/lib/format';

const BENCHMARKS = ['CDI', 'IBOV'] as const;

function WealthPanel({ data }: { data: PortfolioSeries }) {
  const first = data.wealth[0];
  const last = data.wealth[data.wealth.length - 1];
  return (
    <>
      <WealthChart points={data.wealth} />
      <ChartCaption
        period={`${shortDate(first.date)} – ${shortDate(last.date)}`}
        unit="Valor de mercado das posições"
        currency={data.currency}
        sources={data.sources}
        updated={last.date}
      />
    </>
  );
}


export function DashboardPage() {
  const [params] = useSearchParams();
  const { selected } = useSelectedPortfolio();
  const [benchmark, setBenchmark] = useState<(typeof BENCHMARKS)[number]>('CDI');

  const positions = usePositions(selected?.id);
  const series = usePortfolioSeries(selected?.id, benchmark);
  const comparison = useBenchmarkComparison(selected?.id, benchmark);
  const rebalance = useRebalance(selected?.id);
  const plan = useRebalancePlan(selected?.id);

  if (positions.isLoading) return <Spinner />;
  if (positions.error) return <ErrorNote error={positions.error} />;
  if (!positions.data) return null;

  const money_ = positions.data;
  const gain = Number(money_.unrealised_pnl);
  const subject = series.data?.subject;
  const stale = staleness(money_.oldest_price_date);

  return (
    <div className="space-y-6">
      {/* -- how much do I have ------------------------------------- */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Patrimônio"
          value={money(money_.valued_market_value)}
          hint={
            money_.newest_price_date
              ? `Fechamento de ${shortDate(money_.newest_price_date)}`
              : 'Sem preço armazenado'
          }
        />
        <Stat
          label="Resultado não realizado"
          value={money(money_.unrealised_pnl)}
          tone={gain > 0 ? 'positive' : gain < 0 ? 'negative' : 'neutral'}
          hint={`Sobre ${money(money_.valued_invested)} precificados`}
        />
        <Stat
          label="Rentabilidade da carteira"
          value={percent(subject?.total_return)}
          hint={
            subject?.start_date
              ? `Desde ${shortDate(subject.start_date)} · time-weighted`
              : undefined
          }
          missingReason="Histórico insuficiente para medir retorno."
        />
        <Stat
          label={`Excesso sobre o ${benchmark}`}
          value={points(comparison.data?.excess_return)}
          tone={
            Number(comparison.data?.excess_return) > 0
              ? 'positive'
              : Number(comparison.data?.excess_return) < 0
                ? 'negative'
                : 'neutral'
          }
          hint={
            comparison.data
              ? `${benchmark} rendeu ${percent(comparison.data.benchmark.total_return)}`
              : undefined
          }
          missingReason={`Sem série do ${benchmark} no período. Sincronize o benchmark.`}
        />
      </div>

      {money_.unvalued_positions > 0 && (
        <CoverageNote>
          <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />O patrimônio acima
          cobre parte da carteira: <strong>{money_.unvalued_positions}</strong>{' '}
          {money_.unvalued_positions === 1 ? 'posição' : 'posições'} sem preço
          armazenado, somando {money(money_.unvalued_invested)} de custo.
        </CoverageNote>
      )}
      {stale && (
        <CoverageNote>
          O preço mais antigo usado é de {shortDate(money_.oldest_price_date)} (
          {stale}). Estes valores não são cotação em tempo real.
        </CoverageNote>
      )}

      {/* -- evolução ------------------------------------------------ */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card
          title="Evolução do patrimônio"
          subtitle="A linha tracejada é o quanto foi aportado — a diferença entre as duas é o que rendeu."
        >
          {series.isLoading ? (
            <Spinner />
          ) : series.error ? (
            <ErrorNote error={series.error} />
          ) : (series.data?.wealth.length ?? 0) === 0 ? (
            <EmptyNote>
              Nada para desenhar ainda: registre transações e sincronize os preços
              dos ativos.
            </EmptyNote>
          ) : (
            <WealthPanel data={series.data!} />
          )}
        </Card>

        <Card
          title="Rentabilidade contra o benchmark"
          subtitle="Índice time-weighted: aporte não conta como rentabilidade."
          action={
            <div className="flex gap-1">
              {BENCHMARKS.map((code) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => setBenchmark(code)}
                  className={cn(
                    'rounded-md px-2 py-1 text-xs',
                    benchmark === code
                      ? 'bg-slate-800 text-slate-100'
                      : 'text-slate-500 hover:text-slate-300',
                  )}
                >
                  {code}
                </button>
              ))}
            </div>
          }
        >
          {series.isLoading ? (
            <Spinner />
          ) : (series.data?.index.length ?? 0) === 0 ? (
            <EmptyNote>
              Sem janela comum entre a carteira e o {benchmark}. Sincronize o
              benchmark no período da carteira.
            </EmptyNote>
          ) : (
            <>
              <PerformanceChart
                index={series.data!.index}
                benchmark={series.data!.benchmark_index}
                benchmarkName={series.data!.benchmark_name}
              />
              <ChartCaption
                period={`${shortDate(series.data!.base_date)} – ${shortDate(
                  series.data!.end_date,
                )}`}
                unit={`Índice, base ${decimal(series.data!.base)} na data inicial`}
                benchmark={series.data!.benchmark_name}
                sources={series.data!.sources}
                updated={series.data!.end_date}
              />
            </>
          )}
        </Card>
      </div>

      {/* -- risco e composição -------------------------------------- */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card
          title="Risco"
          subtitle="Medido sobre a série de retorno total da carteira."
        >
          <div className="grid grid-cols-2 gap-4">
            <Stat
              label="Volatilidade anual"
              value={percent(subject?.volatility)}
              missingReason="Poucas observações para estimar."
            />
            <Stat
              label="Máximo drawdown"
              value={percent(subject?.max_drawdown)}
              missingReason="Poucas observações para estimar."
            />
            <Stat
              label="Sharpe"
              value={decimal(comparison.data?.sharpe)}
              hint={
                comparison.data?.risk_free_rate
                  ? `Livre de risco: ${percent(comparison.data.risk_free_rate)}`
                  : undefined
              }
              missingReason="Sem taxa livre de risco no período."
            />
            <Stat
              label="Beta"
              value={decimal(comparison.data?.beta)}
              missingReason={
                benchmark === 'CDI'
                  ? 'Beta só faz sentido contra um índice, não contra o CDI.'
                  : 'Sem série do índice no período.'
              }
            />
          </div>
        </Card>

        <Card
          title="Composição"
          subtitle="Peso a custo de aquisição, como o motor de score o mede."
        >
          {(rebalance.data?.targets.length ?? 0) === 0 ? (
            <EmptyNote>Nenhuma posição para compor.</EmptyNote>
          ) : (
            <CompositionBars
              rows={(rebalance.data?.targets ?? [])
                .filter((target) => Number(target.current_weight) > 0)
                .sort(
                  (a, b) => Number(b.current_weight) - Number(a.current_weight),
                )
                .map((target) => ({
                  label: target.ticker,
                  weight: Number(target.current_weight),
                  amount:
                    money_.positions.find(
                      (position) => position.asset_id === target.asset_id,
                    )?.market_value ?? null,
                }))}
            />
          )}
          {rebalance.data && Number(rebalance.data.untracked_weight) > 0 && (
            <CoverageNote>
              {percent(rebalance.data.untracked_weight)} da carteira está em ativos
              que não aparecem acima.
            </CoverageNote>
          )}
        </Card>
      </div>

      {/* -- onde vai o próximo aporte -------------------------------- */}
      <Card
        title="Próximo aporte"
        subtitle="Onde o dinheiro do mês fecha mais desvio, sem estourar os limites do perfil."
        action={
          <Link
            to={{ pathname: '/carteira', search: params.toString() }}
            className="flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300"
          >
            Ver carteira <ArrowRight className="h-3 w-3" />
          </Link>
        }
      >
        {plan.isLoading ? (
          <Spinner />
        ) : plan.error ? (
          <ErrorNote error={plan.error} />
        ) : !plan.data ? null : plan.data.allocations.length === 0 ? (
          <div className="space-y-3">
            <EmptyNote>
              Nada a alocar de {money(plan.data.contribution)} este mês.
            </EmptyNote>
            <ul className="space-y-1.5 text-xs text-slate-500">
              {plan.data.skipped.slice(0, 5).map((item) => (
                <li key={item.ticker}>
                  <span className="font-medium text-slate-400">{item.ticker}</span>{' '}
                  — {item.detail}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-slate-500">
              De {money(plan.data.contribution)},{' '}
              {money(plan.data.allocated)} têm destino e{' '}
              {money(plan.data.unallocated)} não — os limites de concentração não
              deixam ir mais longe este mês.
            </p>
            <ul className="divide-y divide-slate-800/60">
              {plan.data.allocations.map((item) => (
                <li
                  key={item.ticker}
                  className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2.5 text-sm"
                >
                  <span className="font-medium text-slate-200">{item.ticker}</span>
                  <Badge tone="positive">{money(item.amount)}</Badge>
                  <span className="text-xs text-slate-500">
                    {percent(item.current_weight)} → {percent(item.weight_after)} de
                    um alvo de {percent(item.target_weight)}
                  </span>
                  <span className="w-full text-xs text-slate-600">{item.detail}</span>
                </li>
              ))}
            </ul>
            <p className="text-[11px] text-slate-600">
              Plano derivado a cada leitura, nunca gravado. Nada aqui vende: posição
              acima do alvo é corrigida por diluição nos aportes seguintes.
            </p>
          </div>
        )}
      </Card>

      {rebalance.data && Number(rebalance.data.unassigned) > 0 && (
        <CoverageNote>
          {percent(rebalance.data.unassigned)} da carteira não tem peso-alvo: os
          ativos acompanhados que o modelo consegue pontuar não cobrem mais que{' '}
          {percent(rebalance.data.assigned)} sob os tetos de concentração. Aumentar
          essa cobertura é cadastrar setor e sincronizar demonstrativos, não afrouxar
          o modelo.
        </CoverageNote>
      )}
    </div>
  );
}
