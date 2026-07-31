/** Display helpers shared across components. */

const SYMBOLS: Record<string, string> = {
  USD: '$', EUR: '€', GBP: '£', CHF: 'CHF ', JPY: '¥',
  CAD: 'CA$', AUD: 'A$', SEK: 'kr ', NOK: 'kr ', DKK: 'kr ',
};

/**
 * Price with the right currency symbol.
 *
 * The currency matters: the same company can be quoted in dollars, pounds or
 * euros depending on which listing the price came from, and the backend already
 * converts minor units (LSE pence) to major ones.
 */
export const formatPrice = (
  value: number | null | undefined,
  currency: string | null | undefined,
): string => {
  if (value === null || value === undefined) return '—';
  const prefix = SYMBOLS[currency ?? ''] ?? (currency ? `${currency} ` : '');
  const decimals = Math.abs(value) < 1 ? 4 : 2;
  return `${prefix}${value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
};

export const formatPercent = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
};

/** Compact relative age: 5m, 3h, 2d. */
export const formatAge = (iso: string | null | undefined): string => {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60_000));
  if (minutes < 1) return 'now';
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
};

/** Longer relative age for datelines: "31 min ago", "2 hr ago", "3 days ago". */
export const formatAgeLong = (iso: string | null | undefined): string => {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60_000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? 'yesterday' : `${days} days ago`;
};

/** Up/down colour. The sign is always printed too, so colour is never the
 *  only channel carrying the direction. */
export const changeClass = (value: number | null | undefined): string => {
  if (value === null || value === undefined || value === 0) return 'text-ink-muted';
  return value > 0 ? 'text-up' : 'text-down';
};

export type SentimentBand = 'positive' | 'negative' | 'neutral';

export const sentimentBand = (score: number | null | undefined): SentimentBand => {
  if (score === null || score === undefined) return 'neutral';
  if (score > 0.2) return 'positive';
  if (score < -0.2) return 'negative';
  return 'neutral';
};

export const sentimentTextClass = (score: number | null | undefined): string =>
  ({
    positive: 'text-up',
    negative: 'text-down',
    neutral: 'text-ink-muted',
  })[sentimentBand(score)];

export const sentimentDotClass = (score: number | null | undefined): string =>
  ({
    positive: 'bg-up',
    negative: 'bg-down',
    neutral: 'bg-ink-muted',
  })[sentimentBand(score)];
