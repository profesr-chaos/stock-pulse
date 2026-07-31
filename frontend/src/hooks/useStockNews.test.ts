import { describe, expect, it } from 'vitest';

import type { NewsArticle } from '@/types/stock';

import {
  DEFAULT_FILTER,
  LATEST_SHOWN,
  TRENDING_LIMIT,
  dedupeByUrl,
  diversify,
  trendingQuery,
} from './useStockNews';

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

describe('dedupeByUrl', () => {
  it('keeps the first row of a story and drops the rest', () => {
    const url = 'https://ft.com/one-story';
    const first = { ...article('MSFT', 'ft.com'), url };
    const second = { ...article('AAPL', 'ft.com'), url };
    const other = article('TSLA', 'reuters.com');

    expect(dedupeByUrl([first, second, other]).map((a) => a.id)).toEqual([first.id, other.id]);
  });
});

describe('trendingQuery', () => {
  it('caps one ticker on the unfiltered feed', () => {
    expect(trendingQuery(DEFAULT_FILTER).perStock).toBe(3);
  });

  it('fills the section when the reader filtered to one ticker', () => {
    // The real failure: one article in Trending and a column of white space,
    // while the same ticker had plenty stored.
    const query = trendingQuery({ ...DEFAULT_FILTER, symbol: 'NVDA' });
    expect(query.perStock).toBe(TRENDING_LIMIT);
    expect(query.days).toBeGreaterThan(trendingQuery(DEFAULT_FILTER).days);
  });
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

  it('prints a cross-listed story once, not once per ticker', () => {
    // The real failure: one Yahoo piece named both Apple and Microsoft, so the
    // backend stored two rows, and Latest showed the identical headline twice
    // in a row tagged MSFT +15.51% and AAPL -1.41%.
    const url = 'https://finance.yahoo.com/m/dow-jones-futures';
    const asMsft = { ...article('MSFT', 'finance.yahoo.com'), url };
    const asAapl = { ...article('AAPL', 'finance.yahoo.com'), url };

    expect(diversify([asMsft, asAapl], true)).toHaveLength(1);
  });

  it('falls back to the source name when there is no domain', () => {
    const noDomain = () => ({ ...article('AAPL', 'x.com'), source_domain: null, source: 'Wire' });
    const kept = diversify([noDomain(), noDomain(), noDomain()], false);
    expect(kept).toHaveLength(2);
  });
});
