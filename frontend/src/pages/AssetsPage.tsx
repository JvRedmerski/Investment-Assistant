/**
 * The tracked universe. The per-asset screen is W11-005.
 */

import { Link, useSearchParams } from 'react-router-dom';

import { Card, EmptyNote, ErrorNote, Spinner } from '@/components/ui';
import { useAssets } from '@/hooks/queries';

export function AssetsPage() {
  const [params] = useSearchParams();
  const assets = useAssets();

  if (assets.isLoading) return <Spinner />;
  if (assets.error) return <ErrorNote error={assets.error} />;

  return (
    <Card title="Ativos acompanhados" subtitle="Watch-only: nenhuma corretora conectada.">
      {(assets.data?.length ?? 0) === 0 ? (
        <EmptyNote>Nenhum ativo cadastrado.</EmptyNote>
      ) : (
        <ul className="divide-y divide-slate-800/60">
          {assets.data?.map((asset) => (
            <li key={asset.id} className="flex items-center gap-4 py-2.5 text-sm">
              <Link
                to={{ pathname: `/ativos/${asset.ticker}`, search: params.toString() }}
                className="font-medium text-slate-200 hover:text-sky-400"
              >
                {asset.ticker}
              </Link>
              <span className="text-slate-400">{asset.name}</span>
              <span className="ml-auto text-xs text-slate-500">
                {asset.sector ?? 'setor não informado'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
