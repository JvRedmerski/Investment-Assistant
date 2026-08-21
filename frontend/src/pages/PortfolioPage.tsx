/**
 * Positions and transactions for the selected portfolio.
 *
 * The first screen in this project that shows real money, and every
 * number on it was computed by the backend — the page does no
 * arithmetic at all (rule 73).
 *
 * ## Absence and partial coverage are shown, not smoothed over
 *
 * `/positions` reports `market_value: null` for a holding nobody has a
 * price for, and totals named `valued_*` because they cover only the
 * priced rows. Both come through to the screen: the row shows a dash and
 * a reason, and the header says how much of the portfolio the total
 * leaves out. Rendering an unpriced holding as R$ 0,00 would be a
 * plausible, wrong number about somebody's savings.
 */

import { AlertTriangle } from 'lucide-react';

import {
  Card,
  CoverageNote,
  EmptyNote,
  ErrorNote,
  Spinner,
  Stat,
} from '@/components/ui';
import { usePositions, useTransactions } from '@/hooks/queries';
import { useSelectedPortfolio } from '@/layouts/AppLayout';
import { cn } from '@/lib/cn';
import { money, shortDate, staleness } from '@/lib/format';

const TYPE_LABEL: Record<string, string> = {
  BUY: 'Compra',
  SELL: 'Venda',
  DIVIDEND: 'Provento',
  DEPOSIT: 'Aporte',
  WITHDRAWAL: 'Retirada',
};

export function PortfolioPage() {
  const { selected } = useSelectedPortfolio();
  const positions = usePositions(selected?.id);
  const transactions = useTransactions(selected?.id);

  if (positions.isLoading) return <Spinner />;
  if (positions.error) return <ErrorNote error={positions.error} />;
  if (!positions.data) return null;

  const data = positions.data;
  const stale = staleness(data.oldest_price_date);
  const gain = Number(data.unrealised_pnl);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Valor de mercado"
          value={money(data.valued_market_value)}
          hint={
            data.newest_price_date
              ? `Preços de ${shortDate(data.newest_price_date)}`
              : undefined
          }
        />
        <Stat label="Custo das posições" value={money(data.total_invested)} />
        <Stat
          label="Resultado não realizado"
          value={money(data.unrealised_pnl)}
          tone={gain > 0 ? 'positive' : gain < 0 ? 'negative' : 'neutral'}
          hint={`Sobre ${money(data.valued_invested)} precificados`}
        />
        <Stat
          label="Proventos recebidos"
          value={money(data.total_dividends_received)}
          hint={`Resultado realizado ${money(data.total_realized_pnl)}`}
        />
      </div>

      {data.unvalued_positions > 0 && (
        <CoverageNote>
          <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
          O valor de mercado cobre parte da carteira:{' '}
          <strong>{data.unvalued_positions}</strong>{' '}
          {data.unvalued_positions === 1 ? 'posição' : 'posições'} sem preço
          armazenado, somando {money(data.unvalued_invested)} de custo. Sincronize
          os preços desses ativos para que o total passe a cobrir tudo.
        </CoverageNote>
      )}

      {stale && (
        <CoverageNote>
          O preço mais antigo usado neste total é de{' '}
          {shortDate(data.oldest_price_date)} ({stale}). Os valores não são
          cotação em tempo real.
        </CoverageNote>
      )}

      <Card
        title="Posições"
        subtitle="Quantidade e preço médio derivados do histórico de transações."
      >
        {data.positions.length === 0 ? (
          <EmptyNote>
            Nenhuma posição ainda. Registre uma compra para começar.
          </EmptyNote>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="pb-2 pr-4 font-medium">Ativo</th>
                  <th className="pb-2 pr-4 text-right font-medium">Quantidade</th>
                  <th className="pb-2 pr-4 text-right font-medium">Preço médio</th>
                  <th className="pb-2 pr-4 text-right font-medium">Custo</th>
                  <th className="pb-2 pr-4 text-right font-medium">Cotação</th>
                  <th className="pb-2 pr-4 text-right font-medium">Valor</th>
                  <th className="pb-2 text-right font-medium">Não realizado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {data.positions.map((position) => {
                  const result = Number(position.unrealised_pnl);
                  const unpriced = position.market_value === null;
                  return (
                    <tr key={position.asset_id}>
                      <td className="py-2.5 pr-4 font-medium text-slate-200">
                        {position.ticker}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-slate-300">
                        {Number(position.quantity).toLocaleString('pt-BR')}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-slate-300">
                        {money(position.average_price)}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-slate-300">
                        {money(position.invested_amount)}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-slate-400">
                        {money(position.last_price)}
                        {position.price_date && (
                          <span className="ml-1 text-[11px] text-slate-600">
                            {shortDate(position.price_date)}
                          </span>
                        )}
                      </td>
                      <td
                        className={cn(
                          'py-2.5 pr-4 text-right tabular-nums',
                          unpriced ? 'text-slate-600' : 'text-slate-100',
                        )}
                      >
                        {money(position.market_value)}
                      </td>
                      <td
                        className={cn(
                          'py-2.5 text-right tabular-nums',
                          unpriced && 'text-slate-600',
                          !unpriced && result > 0 && 'text-emerald-400',
                          !unpriced && result < 0 && 'text-rose-400',
                          !unpriced && result === 0 && 'text-slate-300',
                        )}
                      >
                        {money(position.unrealised_pnl)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {data.unvalued_positions > 0 && (
              <p className="mt-3 text-[11px] text-slate-500">
                Um traço em Valor significa que não há preço armazenado para o
                ativo — não que a posição valha zero.
              </p>
            )}
          </div>
        )}
      </Card>

      <Card title="Transações" subtitle="O ledger de onde tudo acima é derivado.">
        {transactions.isLoading ? (
          <Spinner />
        ) : transactions.error ? (
          <ErrorNote error={transactions.error} />
        ) : (transactions.data?.length ?? 0) === 0 ? (
          <EmptyNote>Nenhuma transação registrada.</EmptyNote>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="pb-2 pr-4 font-medium">Data</th>
                  <th className="pb-2 pr-4 font-medium">Tipo</th>
                  <th className="pb-2 pr-4 text-right font-medium">Quantidade</th>
                  <th className="pb-2 pr-4 text-right font-medium">Preço</th>
                  <th className="pb-2 text-right font-medium">Taxas</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {[...(transactions.data ?? [])].reverse().map((tx) => (
                  <tr key={tx.id}>
                    <td className="py-2.5 pr-4 text-slate-300">
                      {shortDate(tx.transaction_date)}
                    </td>
                    <td className="py-2.5 pr-4 text-slate-300">
                      {TYPE_LABEL[tx.type] ?? tx.type}
                    </td>
                    <td className="py-2.5 pr-4 text-right tabular-nums text-slate-300">
                      {Number(tx.quantity).toLocaleString('pt-BR')}
                    </td>
                    <td className="py-2.5 pr-4 text-right tabular-nums text-slate-300">
                      {money(tx.price)}
                    </td>
                    <td className="py-2.5 text-right tabular-nums text-slate-400">
                      {money(tx.fees)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
