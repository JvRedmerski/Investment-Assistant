/**
 * Turning the backend's numbers into something a person reads.
 *
 * The only arithmetic in this file is moving a decimal point, and that is
 * deliberate: rule 73 puts financial calculation on the backend, and the
 * line is easier to hold when the frontend's number code is all in one
 * place and all of it is presentation.
 *
 * ## Absence is rendered, never filled in
 *
 * The backend sends `null` for a quantity it could not compute, and it
 * means "unknown" rather than zero (ADR-014). Every formatter here
 * accepts `null` and returns a dash, so a screen cannot accidentally
 * turn an absent volatility into a reassuring 0,0%. If you find yourself
 * writing `?? 0` at a call site, that is the bug this paragraph is about.
 */

const BRL = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
});

const DECIMAL = new Intl.NumberFormat('pt-BR', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const DATE = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short' });

/** What an absent value looks like. One dash, everywhere. */
export const ABSENT = '—';

/**
 * Money as `R$ 1.234,56`.
 *
 * Takes the string the backend sent. The conversion to `number` happens
 * here and nowhere else — at the point of display, after every decision
 * that depended on the value has already been made on the backend.
 */
export function money(value: string | null | undefined): string {
  if (value === null || value === undefined) return ABSENT;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? BRL.format(parsed) : ABSENT;
}

/** A fraction as `12,3%`. `0.123` becomes `12,3%`. */
export function percent(
  value: string | null | undefined,
  digits = 1,
): string {
  if (value === null || value === undefined) return ABSENT;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return ABSENT;
  return `${(parsed * 100).toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

/**
 * A gap in percentage points, signed: `+4,0 p.p.`
 *
 * Percentage points rather than percent, because a weight gap is the
 * difference between two percentages and calling that "4%" is the
 * ambiguity rule 74 warns about.
 */
export function points(value: string | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return ABSENT;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return ABSENT;
  const scaled = parsed * 100;
  const sign = scaled > 0 ? '+' : '';
  return `${sign}${scaled.toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} p.p.`;
}

/** A plain number with two decimals, for scores and ratios. */
export function decimal(value: string | null | undefined): string {
  if (value === null || value === undefined) return ABSENT;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? DECIMAL.format(parsed) : ABSENT;
}

/** An ISO date as `21/08/2026`. */
export function shortDate(value: string | null | undefined): string {
  if (!value) return ABSENT;
  const [year, month, day] = value.slice(0, 10).split('-').map(Number);
  if (!year || !month || !day) return ABSENT;
  return DATE.format(new Date(year, month - 1, day));
}

/**
 * How stale a date is, in plain words.
 *
 * Rules 103/104: data that is not live has to say so. A price from three
 * months ago is not wrong, but a screen that shows it next to today's
 * date without comment is.
 */
export function staleness(value: string | null | undefined): string | null {
  if (!value) return null;
  const [year, month, day] = value.slice(0, 10).split('-').map(Number);
  if (!year || !month || !day) return null;
  const then = new Date(year, month - 1, day);
  const now = new Date();
  const days = Math.floor((now.getTime() - then.getTime()) / 86_400_000);
  if (days <= 1) return null;
  if (days < 7) return `há ${days} dias`;
  if (days < 60) return `há ${Math.floor(days / 7)} semanas`;
  return `há ${Math.floor(days / 30)} meses`;
}
