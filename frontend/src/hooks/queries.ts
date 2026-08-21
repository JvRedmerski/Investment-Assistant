/**
 * Every read the app makes, as a react-query hook.
 *
 * One hook per endpoint, each naming its schema, so a screen never
 * builds a URL or decides a cache key. The keys are structured
 * `[resource, id, ...params]` so invalidating a portfolio's data after a
 * transaction is one call rather than a list of strings to keep in sync.
 *
 * ## Nothing here retries a refusal
 *
 * A 404 on someone else's portfolio and a 401 on an expired session are
 * both answers, not failures. Retrying them wastes time and delays the
 * screen that should be shown instead, so only genuine transport
 * failures are retried.
 */

import { useQuery, type UseQueryOptions } from '@tanstack/react-query';

import { ApiError, request } from '@/lib/api';
import {
  assetListSchema,
  assetPriceListSchema,
  corporateActionListSchema,
  indicatorListSchema,
  benchmarkComparisonSchema,
  contributionPlanSchema,
  portfolioListSchema,
  portfolioSeriesSchema,
  positionsSchema,
  rebalancePlanSchema,
  rebalanceSchema,
  scoresSchema,
  transactionListSchema,
  type Asset,
  type AssetPrice,
  type BenchmarkComparison,
  type CorporateAction,
  type Indicator,
  type ContributionPlan,
  type Portfolio,
  type PortfolioSeries,
  type Positions,
  type Rebalance,
  type RebalancePlan,
  type Scores,
  type Transaction,
} from '@/types/api';

type Options<T> = Omit<UseQueryOptions<T, Error>, 'queryKey' | 'queryFn'>;

/** Retry transport trouble; never retry an answer. */
export function retryPolicy(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400) return false;
  return failureCount < 2;
}

export function usePortfolios(options?: Options<Portfolio[]>) {
  return useQuery({
    queryKey: ['portfolios'],
    queryFn: () => request('/portfolios', portfolioListSchema),
    ...options,
  });
}

export function useAssets(options?: Options<Asset[]>) {
  return useQuery({
    queryKey: ['assets'],
    queryFn: () => request('/assets', assetListSchema),
    ...options,
  });
}

export function usePositions(
  portfolioId: number | undefined,
  options?: Options<Positions>,
) {
  return useQuery({
    queryKey: ['portfolio', portfolioId, 'positions'],
    queryFn: () => request(`/portfolios/${portfolioId}/positions`, positionsSchema),
    enabled: portfolioId !== undefined,
    ...options,
  });
}

export function useTransactions(
  portfolioId: number | undefined,
  options?: Options<Transaction[]>,
) {
  return useQuery({
    queryKey: ['portfolio', portfolioId, 'transactions'],
    queryFn: () =>
      request(`/portfolios/${portfolioId}/transactions`, transactionListSchema),
    enabled: portfolioId !== undefined,
    ...options,
  });
}

export function usePortfolioSeries(
  portfolioId: number | undefined,
  benchmark?: string,
  options?: Options<PortfolioSeries>,
) {
  return useQuery({
    queryKey: ['portfolio', portfolioId, 'series', benchmark ?? null],
    queryFn: () =>
      request(`/portfolios/${portfolioId}/series`, portfolioSeriesSchema, {
        params: { benchmark },
      }),
    enabled: portfolioId !== undefined,
    ...options,
  });
}

export function useBenchmarkComparison(
  portfolioId: number | undefined,
  code: string,
  options?: Options<BenchmarkComparison>,
) {
  return useQuery({
    queryKey: ['portfolio', portfolioId, 'benchmark', code],
    queryFn: () =>
      request(
        `/portfolios/${portfolioId}/benchmarks/${code}`,
        benchmarkComparisonSchema,
      ),
    enabled: portfolioId !== undefined,
    ...options,
  });
}

export function useScores(
  portfolioId: number | undefined,
  options?: Options<Scores>,
) {
  return useQuery({
    queryKey: ['portfolio', portfolioId, 'scores'],
    queryFn: () => request(`/portfolios/${portfolioId}/scores`, scoresSchema),
    enabled: portfolioId !== undefined,
    ...options,
  });
}

export function useContributionPlan(
  portfolioId: number | undefined,
  options?: Options<ContributionPlan>,
) {
  return useQuery({
    queryKey: ['portfolio', portfolioId, 'contribution-plan'],
    queryFn: () =>
      request(`/portfolios/${portfolioId}/contribution-plan`, contributionPlanSchema),
    enabled: portfolioId !== undefined,
    ...options,
  });
}

export function useRebalance(
  portfolioId: number | undefined,
  options?: Options<Rebalance>,
) {
  return useQuery({
    queryKey: ['portfolio', portfolioId, 'rebalance'],
    queryFn: () => request(`/portfolios/${portfolioId}/rebalance`, rebalanceSchema),
    enabled: portfolioId !== undefined,
    ...options,
  });
}

export function useRebalancePlan(
  portfolioId: number | undefined,
  options?: Options<RebalancePlan>,
) {
  return useQuery({
    queryKey: ['portfolio', portfolioId, 'rebalance-plan'],
    queryFn: () =>
      request(`/portfolios/${portfolioId}/rebalance-plan`, rebalancePlanSchema),
    enabled: portfolioId !== undefined,
    ...options,
  });
}


export function useAssetPrices(
  ticker: string | undefined,
  start?: string,
  options?: Options<AssetPrice[]>,
) {
  return useQuery({
    queryKey: ['asset', ticker, 'prices', start ?? null],
    queryFn: () =>
      request(`/assets/${ticker}/prices`, assetPriceListSchema, {
        params: { start },
      }),
    enabled: ticker !== undefined,
    ...options,
  });
}

export function useIndicators(
  ticker: string | undefined,
  options?: Options<Indicator[]>,
) {
  return useQuery({
    queryKey: ['asset', ticker, 'indicators'],
    queryFn: () => request(`/assets/${ticker}/indicators`, indicatorListSchema),
    enabled: ticker !== undefined,
    ...options,
  });
}

export function useCorporateActions(
  ticker: string | undefined,
  options?: Options<CorporateAction[]>,
) {
  return useQuery({
    queryKey: ['asset', ticker, 'corporate-actions'],
    queryFn: () =>
      request(`/assets/${ticker}/corporate-actions`, corporateActionListSchema),
    enabled: ticker !== undefined,
    ...options,
  });
}
