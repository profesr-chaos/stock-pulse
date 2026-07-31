import { describe, expect, it } from 'vitest';

import type { NewsArticle } from '@/types/stock';

import { LATEST_SHOWN, diversify } from './useStockNews';

let nextId = 1;

const article = (symbol: string, domain: string): NewsArticle => ({
  id: nextId++,
  short_name: symbol,
  title: `${symbol} story ${nextId}`,
  url: `https://${domain}/${nextId}`,
  publish_time: '2026-07-31T10:00:00Z',
  source: domain,
  source_domain: domain,
  source_url: null,
  source_type: 'GOOGLE_NEWS',
  relevance: 'direct',
  lang: 'en',
  image: null,
  description: null,
  sentiment: null,
  ai_summary: null,
});

describe('diversify', () => {
  it('keeps the incoming order', () => {
    const input = [article('AAPL', 'reuters.com'), article('TSLA', 'ft.com')];
    expect(diversify(input, true).map((a) => a.id)).toEqual(input.map((a) => a.id));
  });

  it('stops one filing wire from owning the column', () => {
    // The real failure: marketbeat posts a near-identical NVDA holdings story
    // every few minutes, and straight recency showed ten of them in a row.
    const flood = Array.from({ length: 20 }, () => article('NVDA', 'marketbeat.com'));
    const kept = diversify([...flood, article('AAPL', 'reuters.com')], true);

    expect(kept.filter((a) => a.source_domain === 'marketbeat.com')).toHaveLength(2);
    expect(kept.some((a) => a.source_domain === 'reuters.com')).toBe(true);
  });

  it('stops one ticker from owning the column', () => {
    const input = [
      ...Array.from({ length: 8 }, (_, i) => article('NVDA', `wire${i}.com`)),
      article('AAPL', 'reuters.com'),
    ];
    const kept = diversify(input, true);

    expect(kept.filter((a) => a.short_name === 'NVDA')).toHaveLength(3);
    expect(kept.at(-1)?.short_name).toBe('AAPL');
  });

  it('lifts the per-ticker cap when the reader filtered to that ticker', () => {
    // Capping by symbol while filtered to one symbol would trim the very
    // column the reader asked for.
    const input = Array.from({ length: 8 }, (_, i) => article('NVDA', `wire${i}.com`));
    expect(diversify(input, false)).toHaveLength(8);
    expect(diversify(input, true)).toHaveLength(3);
  });

  it('never returns more than the column shows', () => {
    const input = Array.from({ length: 60 }, (_, i) => article(`SYM${i}`, `wire${i}.com`));
    expect(diversify(input, true)).toHaveLength(LATEST_SHOWN);
  });

  it('falls back to the source name when there is no domain', () => {
    const noDomain = () => ({ ...article('AAPL', 'x.com'), source_domain: null, source: 'Wire' });
    const kept = diversify([noDomain(), noDomain(), noDomain()], false);
    expect(kept).toHaveLength(2);
  });
});
