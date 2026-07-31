import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useCallback } from 'react';

import { STALE_TIME } from '@/config/api';
import { getNews, getTrendingNews, type SortKey } from '@/services/newsApi';
import type { NewsArticle } from '@/types/stock';

export type { SortKey };

/**
 * Everything the feed is filtered and ordered by, in one object.
 *
 * All four fields resolve server-side. That is the whole point: a search or a
 * sort applied in the browser can only ever see the page already loaded, so it
 * would silently mean "sort these fifty" while looking like "sort everything".
 */
export interface FeedFilter {
  /** A single ticker, across the entire news table — not just the watchlist. */
  symbol: string | null;
  /** Free text, matched against headline, summary and ticker. */
  query: string;
  /** Sector or industry name. */
  sector: string | null;
  sort: SortKey;
}

export const DEFAULT_FILTER: FeedFilter = {
  symbol: null,
  query: '',
  sector: null,
  sort: 'recent',
};

/** A search replaces the curated sections with one ranked result list. */
export const isSearching = (filter: FeedFilter) => filter.query.trim().length > 0;

const isDefault = (filter: FeedFilter) =>
  !filter.symbol && !filter.query && !filter.sector && filter.sort === 'recent';

const asSymbols = (filter: FeedFilter) => (filter.symbol ? [filter.symbol] : undefined);

/**
 * Only the untouched first render may claim index.html's preloaded response.
 *
 * The preload fires before React boots and hard-codes the default query string,
 * so handing it to a filtered view would answer a search with the unfiltered
 * feed — right shape, wrong articles, and no error to notice it by.
 */
const bootable = <K extends string>(filter: FeedFilter, key: K) =>
  isDefault(filter) ? key : undefined;

/**
 * One story, one row — whichever ticker it came in under.
 *
 * `news` stores a row per (article, stock) pair, so a Yahoo piece naming both
 * Apple and Microsoft is two rows with two ids and two tickers. Every section
 * here keys on id, which cannot see that, and the result is the same headline
 * printed twice in a row under different tags. The url is what actually
 * identifies a story, so that is what de-duplication has to use.
 */
export const dedupeByUrl = (articles: NewsArticle[]): NewsArticle[] => {
  const seen = new Set<string>();
  const kept: NewsArticle[] = [];
  for (const article of articles) {
    if (seen.has(article.url)) continue;
    seen.add(article.url);
    kept.push(article);
  }
  return kept;
};

/** Lead section: ranked by how far the stock moved. */
export const useTrendingNews = (filter: FeedFilter = DEFAULT_FILTER) =>
  useQuery({
    queryKey: ['news', 'trending', filter.symbol, filter.sector],
    queryFn: ({ signal }) =>
      getTrendingNews(
        {
          symbols: asSymbols(filter),
          sector: filter.sector ?? undefined,
          days: 2,
          perStock: 3,
          limit: 12,
        },
        signal,
        bootable(filter, 'trending'),
      ),
    select: dedupeByUrl,
    // Not keyed on sort: this section's order *is* the price move, which is
    // what the heading promises. Nor on query — a search hides it entirely.
    enabled: !isSearching(filter),
    staleTime: STALE_TIME.news,
  });

/**
 * How many articles Latest pulls to fill its column, and how many survive.
 *
 * The gap is the de-duplication below. The river resumes at LATEST_FETCH, not
 * at LATEST_SHOWN, so the two never overlap.
 */
export const LATEST_FETCH = 40;
export const LATEST_SHOWN = 14;

/**
 * Recency is the right ordering and a terrible column on its own.
 *
 * One filing wire posts a near-identical "X acquires N shares of NVIDIA"
 * story every few minutes, so a straight `ORDER BY publish_time` fills the
 * whole column with one publisher covering one ticker. Capping each keeps the
 * ordering intact and the column readable.
 *
 * ponytail: caps, not similarity clustering. If a second wire starts doing the
 * same thing under rotating domains, this stops working and the fix belongs in
 * services/dedup.py, not here.
 */
const PER_SOURCE = 2;
const PER_SYMBOL = 3;

export const diversify = (articles: NewsArticle[], capSymbols: boolean): NewsArticle[] => {
  const bySource = new Map<string, number>();
  const bySymbol = new Map<string, number>();
  const kept: NewsArticle[] = [];

  for (const article of dedupeByUrl(articles)) {
    if (kept.length >= LATEST_SHOWN) break;
    const source = article.source_domain ?? article.source;
    const sourceCount = bySource.get(source) ?? 0;
    const symbolCount = bySymbol.get(article.short_name) ?? 0;
    if (sourceCount >= PER_SOURCE) continue;
    if (capSymbols && symbolCount >= PER_SYMBOL) continue;
    bySource.set(source, sourceCount + 1);
    bySymbol.set(article.short_name, symbolCount + 1);
    kept.push(article);
  }
  return kept;
};

/** The recency column beneath Trending. */
export const useLatestNews = (filter: FeedFilter = DEFAULT_FILTER) => {
  // Filtering to one ticker makes the per-symbol cap self-defeating: it would
  // trim the very column the reader just asked to see.
  const select = useCallback(
    (articles: NewsArticle[]) => diversify(articles, filter.symbol === null),
    [filter.symbol],
  );

  return useQuery({
    queryKey: ['news', 'latest', filter.symbol, filter.sector],
    queryFn: ({ signal }) =>
      getNews(
        {
          symbols: asSymbols(filter),
          sector: filter.sector ?? undefined,
          days: 14,
          relevance: 'direct',
          limit: LATEST_FETCH,
        },
        signal,
        bootable(filter, 'latest'),
      ),
    select,
    // Like Trending, this section is defined by its ordering — "Latest" sorted
    // by sentiment would be a mislabelled list.
    enabled: !isSearching(filter),
    staleTime: STALE_TIME.news,
  });
};

export const RIVER_PAGE_SIZE = 50;

/**
 * The infinite-scroll river below the fold, and the results list for a search.
 *
 * Pages by offset over a total ordering, so the only way to run out is for the
 * database to actually be exhausted — a short page is the end, not a hiccup.
 *
 * It deliberately starts at offset 0 rather than skipping past the sections
 * above it. Latest fetches LATEST_FETCH articles and prints a filtered subset,
 * so an offset large enough to avoid repeats would also make everything it
 * filtered out unreachable — articles the database has and no scroll could
 * ever reach. Overlap is removed by url at render time instead, which costs
 * nothing and cannot hide anything.
 */
export const useNewsRiver = (filter: FeedFilter = DEFAULT_FILTER) =>
  useInfiniteQuery({
    // Every field is in the key: changing the sort has to refetch from offset 0
    // rather than append differently-ordered rows to the pages already held.
    queryKey: ['news', 'river', filter.symbol, filter.query, filter.sector, filter.sort],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) =>
      getNews(
        {
          symbols: asSymbols(filter),
          q: filter.query.trim() || undefined,
          sector: filter.sector ?? undefined,
          sort: filter.sort,
          days: 90,
          limit: RIVER_PAGE_SIZE,
          offset: (pageParam as number) * RIVER_PAGE_SIZE,
        },
        signal,
      ),
    // Judge the end from the raw page, never from the de-duplicated view: a
    // page that is short only because its rows appeared above would otherwise
    // stop the river early.
    getNextPageParam: (lastPage: NewsArticle[], allPages) =>
      lastPage.length < RIVER_PAGE_SIZE ? undefined : allPages.length,
    staleTime: STALE_TIME.news,
  });
