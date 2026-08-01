import { describe, expect, it, vi } from 'vitest';

import type { Impact, NewsArticle } from '@/types/stock';

import {
  byImpact,
  formatAge,
  formatPercent,
  formatPrice,
  sentimentBand,
  sentimentTextClass,
} from './format';

describe('formatPrice', () => {
  it('uses the currency the price is actually quoted in', () => {
    // The same company can arrive in dollars, pounds or euros depending on
    // which listing the backend resolved, so the symbol has to follow the data.
    expect(formatPrice(338.19, 'USD')).toBe('$338.19');
    expect(formatPrice(33.24, 'GBP')).toBe('£33.24');
    expect(formatPrice(53.5, 'EUR')).toBe('€53.50');
  });

  it('falls back to the code for currencies with no symbol', () => {
    expect(formatPrice(120.5, 'PLN')).toBe('PLN 120.50');
  });

  it('omits a prefix entirely when the currency is unknown', () => {
    expect(formatPrice(120.5, null)).toBe('120.50');
  });

  it('shows more precision for sub-unit prices', () => {
    expect(formatPrice(0.0421, 'USD')).toBe('$0.0421');
  });

  it('renders a dash rather than NaN when there is no price', () => {
    expect(formatPrice(null, 'USD')).toBe('—');
    expect(formatPrice(undefined, 'USD')).toBe('—');
  });

  it('keeps zero as a real value', () => {
    expect(formatPrice(0, 'USD')).toBe('$0.0000');
  });
});

describe('formatPercent', () => {
  it('signs gains explicitly', () => {
    expect(formatPercent(2.75)).toBe('+2.75%');
    expect(formatPercent(-8.28)).toBe('-8.28%');
    expect(formatPercent(0)).toBe('+0.00%');
  });

  it('handles a missing value', () => {
    expect(formatPercent(null)).toBe('—');
  });
});

describe('formatAge', () => {
  it('summarises recency compactly', () => {
    const now = new Date('2026-07-30T12:00:00Z').getTime();
    vi.spyOn(Date, 'now').mockReturnValue(now);

    expect(formatAge('2026-07-30T11:58:00Z')).toBe('2m');
    expect(formatAge('2026-07-30T09:00:00Z')).toBe('3h');
    expect(formatAge('2026-07-28T12:00:00Z')).toBe('2d');
    expect(formatAge('2026-07-30T12:00:00Z')).toBe('now');

    vi.restoreAllMocks();
  });

  it('is safe on missing or malformed timestamps', () => {
    expect(formatAge(null)).toBe('');
    expect(formatAge('not a date')).toBe('');
  });
});

describe('sentimentBand', () => {
  it('uses the same thresholds as the backend', () => {
    expect(sentimentBand(0.8)).toBe('positive');
    expect(sentimentBand(-0.8)).toBe('negative');
    expect(sentimentBand(0.1)).toBe('neutral');
    expect(sentimentBand(0.2)).toBe('neutral');
    expect(sentimentBand(0.21)).toBe('positive');
  });

  it('treats an unscored article as neutral, not positive', () => {
    expect(sentimentBand(null)).toBe('neutral');
    expect(sentimentTextClass(null)).toContain('muted');
  });
});

describe('byImpact', () => {
  const article = (id: string, impact?: Impact | null) =>
    ({ id, impact } as NewsArticle);

  it('puts the high-impact story on top', () => {
    const sorted = byImpact([
      article('low', 'low'),
      article('high', 'high'),
      article('medium', 'medium'),
    ]);
    expect(sorted.map((a) => a.id)).toEqual(['high', 'medium', 'low']);
  });

  it('ranks an unjudged article with low, not above it', () => {
    const sorted = byImpact([article('unjudged', null), article('medium', 'medium')]);
    expect(sorted.map((a) => a.id)).toEqual(['medium', 'unjudged']);
  });

  it('keeps recency order inside a tier', () => {
    const sorted = byImpact([
      article('newest', 'high'),
      article('older', 'high'),
      article('oldest', 'high'),
    ]);
    expect(sorted.map((a) => a.id)).toEqual(['newest', 'older', 'oldest']);
  });

  it('does not mutate the page it was given', () => {
    const page = [article('low', 'low'), article('high', 'high')];
    byImpact(page);
    expect(page.map((a) => a.id)).toEqual(['low', 'high']);
  });
});
