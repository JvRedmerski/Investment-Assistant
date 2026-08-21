/**
 * The dashboard. Built in W11-004; this is the shell it fills.
 *
 * Deliberately not a mock: it shows the two numbers that already exist
 * end to end rather than placeholder art, so the route is honest about
 * what the system can currently answer.
 */

import { Card, ErrorNote, Spinner, Stat } from '@/components/ui';
import { usePositions } from '@/hooks/queries';
import { useSelectedPortfolio } from '@/layouts/AppLayout';
import { money } from '@/lib/format';

export function DashboardPage() {
  const { selected } = useSelectedPortfolio();
  const positions = usePositions(selected?.id);

  if (positions.isLoading) return <Spinner />;
  if (positions.error) return <ErrorNote error={positions.error} />;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Stat
          label="Patrimônio"
          value={money(positions.data?.valued_market_value)}
          hint={selected?.name}
        />
        <Stat
          label="Custo das posições"
          value={money(positions.data?.total_invested)}
        />
        <Stat
          label="Resultado não realizado"
          value={money(positions.data?.unrealised_pnl)}
        />
      </div>

      <Card title="Rentabilidade, benchmarks, composição, risco e próximo aporte">
        <p className="text-sm text-slate-500">
          Em construção (W11-004). Os dados já existem na API — evolução em{' '}
          <code className="text-slate-400">/portfolios/&#123;id&#125;/series</code>,
          comparativo em <code className="text-slate-400">/benchmarks/&#123;code&#125;</code>,
          score em <code className="text-slate-400">/scores</code> e o próximo
          aporte em <code className="text-slate-400">/rebalance-plan</code>.
        </p>
      </Card>
    </div>
  );
}
