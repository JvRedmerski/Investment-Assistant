/**
 * The API contract, as schemas rather than as interfaces.
 *
 * Every one of these is validated against the real response at the
 * boundary (`lib/api.ts`), so a rename on the backend surfaces as a
 * named error instead of an `undefined` rendered into a screen about
 * somebody's money.
 *
 * ## Money and other decimals are `string`
 *
 * The backend serialises `Decimal` as a JSON string on purpose — it is
 * the one hop where a value is safe from a binary float. Parsing it into
 * a `number` here would undo that, so it stays a string until
 * `lib/format.ts` renders it. Nothing in this app does arithmetic on
 * these, which is rule 73 restated as a type.
 *
 * ## `nullable` is a fact, not a defensive habit
 *
 * Where a field is `.nullable()` below, the backend genuinely reports
 * "could not be computed" there (ADR-014). Screens must render that
 * absence rather than substitute a zero.
 */

import { z } from 'zod';

/** A `Decimal` as it arrives: a string, and never parsed into a float. */
const money = z.string();

export const tokenSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
});

export const userSchema = z.object({
  id: z.number(),
  email: z.string(),
  created_at: z.string(),
});

export const portfolioSchema = z.object({
  id: z.number(),
  user_id: z.number(),
  name: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const portfolioListSchema = z.array(portfolioSchema);

export const assetSchema = z.object({
  id: z.number(),
  ticker: z.string(),
  name: z.string(),
  asset_type: z.string(),
  sector: z.string().nullable(),
  is_active: z.boolean(),
});

export const assetListSchema = z.array(assetSchema);

export const positionSchema = z.object({
  asset_id: z.number(),
  ticker: z.string(),
  quantity: money,
  average_price: money,
  invested_amount: money,
  realized_pnl: money,
  dividends_received: money,
  last_price: money.nullable(),
  price_date: z.string().nullable(),
  market_value: money.nullable(),
  unrealised_pnl: money.nullable(),
});

export const positionsSchema = z.object({
  portfolio_id: z.number(),
  positions: z.array(positionSchema),
  total_invested: money,
  total_realized_pnl: money,
  total_dividends_received: money,
  net_contributions: money,
  valued_market_value: money,
  valued_invested: money,
  unrealised_pnl: money,
  unvalued_positions: z.number(),
  unvalued_invested: money,
  oldest_price_date: z.string().nullable(),
  newest_price_date: z.string().nullable(),
});

export const transactionSchema = z.object({
  id: z.number(),
  portfolio_id: z.number(),
  asset_id: z.number().nullable(),
  type: z.string(),
  quantity: money,
  price: money,
  fees: money,
  transaction_date: z.string(),
  created_at: z.string(),
});

export const transactionListSchema = z.array(transactionSchema);

const seriesPerformanceSchema = z.object({
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
  observations: z.number(),
  periodicity: z.string(),
  total_return: money.nullable(),
  annualised_return: money.nullable(),
  volatility: money.nullable(),
  max_drawdown: money.nullable(),
});

export const portfolioSeriesSchema = z.object({
  portfolio_id: z.number(),
  currency: z.string(),
  base: money,
  base_date: z.string().nullable(),
  end_date: z.string().nullable(),
  sources: z.array(z.string()),
  generated_at: z.string(),
  wealth: z.array(
    z.object({ date: z.string(), value: money, invested: money }),
  ),
  index: z.array(z.object({ date: z.string(), value: money })),
  benchmark_code: z.string().nullable(),
  benchmark_name: z.string().nullable(),
  benchmark_index: z.array(z.object({ date: z.string(), value: money })),
  subject: seriesPerformanceSchema,
  benchmark: seriesPerformanceSchema.nullable(),
});

export const benchmarkComparisonSchema = z.object({
  benchmark_code: z.string(),
  benchmark_name: z.string(),
  subject: seriesPerformanceSchema,
  benchmark: seriesPerformanceSchema,
  excess_return: money.nullable(),
  return_ratio: money.nullable(),
  beta: money.nullable(),
  sharpe: money.nullable(),
  sortino: money.nullable(),
  risk_free_rate: money.nullable(),
});

const subScoreSchema = z.object({
  name: z.string(),
  value: money.nullable(),
  weight: money,
  components: z.record(z.string(), money),
  missing: z.array(z.string()),
});

export const scoresSchema = z.object({
  portfolio_id: z.number(),
  formula_version: z.string(),
  scores: z.array(
    z.object({
      ticker: z.string(),
      asset_id: z.number(),
      name: z.string(),
      sector: z.string().nullable(),
      formula_version: z.string(),
      final_score: money.nullable(),
      coverage: money,
      sub_scores: z.array(subScoreSchema),
    }),
  ),
});

const policySchema = z.object({
  max_asset_weight: money,
  max_sector_weight: money,
  max_share_per_position: money,
  max_positions: z.number(),
  min_ticket: money,
  min_coverage: money,
  min_score: money,
  coverage_tier_width: money,
  rebalance_band: money,
  require_sector: z.boolean(),
});

export const contributionPlanSchema = z.object({
  portfolio_id: z.number(),
  rules_version: z.string(),
  formula_version: z.string(),
  policy: policySchema,
  contribution: money,
  allocated: money,
  unallocated: money,
  base_value: money,
  allocations: z.array(
    z.object({
      ticker: z.string(),
      asset_id: z.number(),
      name: z.string(),
      sector: z.string().nullable(),
      amount: money,
      rank: z.number(),
      final_score: money,
      coverage: money,
      coverage_tier: z.number(),
      headroom: money,
      limited_by: z.string(),
      weight_before: money,
      weight_after: money,
      sub_scores: z.array(subScoreSchema),
    }),
  ),
  skipped: z.array(
    z.object({
      ticker: z.string(),
      asset_id: z.number(),
      name: z.string(),
      reason: z.string(),
      detail: z.string(),
      final_score: money.nullable(),
      coverage: money,
    }),
  ),
});

export const rebalanceSchema = z.object({
  portfolio_id: z.number(),
  model_version: z.string(),
  formula_version: z.string(),
  policy: policySchema,
  invested: money,
  assigned: money,
  unassigned: money,
  underweight_gap: money,
  overweight_gap: money,
  untracked_weight: money,
  targets: z.array(
    z.object({
      ticker: z.string(),
      asset_id: z.number(),
      name: z.string(),
      sector: z.string().nullable(),
      merit_score: money.nullable(),
      merit_coverage: money,
      current_weight: money,
      target_weight: money,
      weight_gap: money,
      status: z.string(),
      limited_by: z.string().nullable(),
      excluded: z.string().nullable(),
      detail: z.string(),
      final_score: money.nullable(),
      coverage: money,
      sub_scores: z.array(subScoreSchema),
    }),
  ),
});

export const rebalancePlanSchema = z.object({
  portfolio_id: z.number(),
  rules_version: z.string(),
  model_version: z.string(),
  formula_version: z.string(),
  policy: policySchema,
  contribution: money,
  allocated: money,
  unallocated: money,
  base_value: money,
  underweight_before: money,
  underweight_after: money,
  allocations: z.array(
    z.object({
      ticker: z.string(),
      asset_id: z.number(),
      name: z.string(),
      sector: z.string().nullable(),
      amount: money,
      rank: z.number(),
      merit_score: money.nullable(),
      current_weight: money,
      target_weight: money,
      weight_gap: money,
      needed: money,
      limited_by: z.string(),
      weight_after: money,
      gap_after: money,
      detail: z.string(),
    }),
  ),
  skipped: z.array(
    z.object({
      ticker: z.string(),
      asset_id: z.number(),
      name: z.string(),
      reason: z.string(),
      detail: z.string(),
      current_weight: money,
      target_weight: money,
      weight_gap: money,
    }),
  ),
});

export type Token = z.infer<typeof tokenSchema>;
export type User = z.infer<typeof userSchema>;
export type Portfolio = z.infer<typeof portfolioSchema>;
export type Asset = z.infer<typeof assetSchema>;
export type Position = z.infer<typeof positionSchema>;
export type Positions = z.infer<typeof positionsSchema>;
export type Transaction = z.infer<typeof transactionSchema>;
export type PortfolioSeries = z.infer<typeof portfolioSeriesSchema>;
export type BenchmarkComparison = z.infer<typeof benchmarkComparisonSchema>;
export type Scores = z.infer<typeof scoresSchema>;
export type SubScore = z.infer<typeof subScoreSchema>;
export type ContributionPlan = z.infer<typeof contributionPlanSchema>;
export type Rebalance = z.infer<typeof rebalanceSchema>;
export type RebalanceTarget = Rebalance['targets'][number];
export type RebalancePlan = z.infer<typeof rebalancePlanSchema>;
