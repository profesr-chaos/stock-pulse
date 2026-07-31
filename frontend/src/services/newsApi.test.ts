import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { getNews, getTrendingNews } from './newsApi';

const mockFetch = vi.fn();

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockResolvedValue(
    new Response(JSON.stringify({ results: [] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => vi.unstubAllGlobals());

const requestedUrl = () => new URL(mockFetch.mock.calls[0][0].toString());

describe('news queries', () => {
  it('sends the ticker filter to the server rather than filtering locally', async () => {
    // The whole point of the search box: it must reach the entire news
    // table, not narrow the articles already rendered on the page.
    await getNews({ symbols: ['TSLA'] });
    const url = requestedUrl();
    expect(url.pathname).toBe('/news');
    expect(url.searchParams.get('symbols')).toBe('TSLA');
  });

  it('omits the symbol param entirely when nothing is filtered', async () => {
    // No symbols means "the watchlist", which the backend assembles itself.
    await getNews({ days: 14 });
    expect(requestedUrl().searchParams.has('symbols')).toBe(false);
  });

  it('pages the river by offset', async () => {
    await getNews({ limit: 20, offset: 40 });
    const url = requestedUrl();
    expect(url.searchParams.get('limit')).toBe('20');
    expect(url.searchParams.get('offset')).toBe('40');
  });

  it('sends offset 0 as a real value, not a dropped falsy one', async () => {
    // apiFetch skips undefined/null/'' — 0 must survive, or the first page
    // would silently become "no offset" and any later change to the default
    // would go unnoticed.
    await getNews({ offset: 0 });
    expect(requestedUrl().searchParams.get('offset')).toBe('0');
  });

  it('asks the trending endpoint for its own ranking', async () => {
    await getTrendingNews({ days: 2, perStock: 3, limit: 12 });
    const url = requestedUrl();
    expect(url.pathname).toBe('/news/trending');
    expect(url.searchParams.get('per_stock')).toBe('3');
  });

  it('searches the server, not the loaded page', async () => {
    // A client-side search could only ever match the ~50 articles already
    // fetched, while looking like it searched everything stored.
    await getNews({ q: 'launch failure' });
    expect(requestedUrl().searchParams.get('q')).toBe('launch failure');
  });

  it('sorts on the server, not the loaded page', async () => {
    await getNews({ sort: 'sentiment' });
    expect(requestedUrl().searchParams.get('sort')).toBe('sentiment');
  });

  it('sends the sector filter to the server', async () => {
    await getNews({ sector: 'Aerospace & Defense' });
    expect(requestedUrl().searchParams.get('sector')).toBe('Aerospace & Defense');
  });

  it('drops an empty search rather than sending q=', async () => {
    // `q=` would be a search for the empty string; omitting it is the
    // difference between "no filter" and "match nothing".
    await getNews({ q: '', sector: '' });
    const url = requestedUrl();
    expect(url.searchParams.has('q')).toBe(false);
    expect(url.searchParams.has('sector')).toBe(false);
  });

  it('narrows the lead section by sector too', async () => {
    // A filter that reordered the feed but left the hero on an unrelated
    // stock would read as the filter having failed.
    await getTrendingNews({ sector: 'Industrials' });
    expect(requestedUrl().searchParams.get('sector')).toBe('Industrials');
  });
});
