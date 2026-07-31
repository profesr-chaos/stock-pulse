import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useCallback } from 'react';

import { STALE_TIME } from '@/config/api';
import { getNews, getTrendingNews } from '@/services/newsApi';
import type { NewsArticle } from '@/types/stock';

/**
 * The whole feed is driven by one optional symbol filter.
 *
 * `null` means "the watchlist", which the backend assembles server-side in a
 * single request. A symbol means "this ticker across the entire news table",
 * which is also server-side — filtering never reduces an already-rendered list.
 */
export type SymbolFilter = string | null;

const asSymbols = (filter: SymbolFilter) => (filter ? [filter] : undefined);

/** Only the unfiltered first render may claim index.html's preloaded response. */
const bootable = <K extends string>(filter: SymbolFilter, key: K) =>
  filter === null ? key : undefined;

/** Lead section: ranked by how far the stock moved. */
export const useTrendingNews = (filter: SymbolFilter = null) =>
  useQuery({
    queryKey: ['news', 'trending', filter],
    queryFn: ({ signal }) =>
      getTrendingNews(
        { symbols: asSymbols(filter), days: 2, perStock: 3, limit: 12 },
        signal,
        bootable(filter, 'trending'),
      ),
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

  for (const article of articles) {
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
export const useLatestNews = (filter: SymbolFilter = null) => {
  // Filtering to one ticker makes the per-symbol cap self-defeating: it would
  // trim the very column the reader just asked to see.
  const select = useCallback(
    (articles: NewsArticle[]) => diversify(articles, filter === null),
    [filter],
  );

  return useQuery({
    queryKey: ['news', 'latest', filter],
    queryFn: ({ signal }) =>
      getNews(
        { symbols: asSymbols(filter), days: 14, relevance: 'direct', limit: LATEST_FETCH },
        signal,
        bootable(filter, 'latest'),
      ),
    select,
    staleTime: STALE_TIME.news,
  });
};

export const RIVER_PAGE_SIZE = 20;

/**
 * The infinite-scroll river below the fold.
 *
 * Pages by offset over a total ordering, so the only way to run out is for the
 * database to actually be exhausted — a short page is the end, not a hiccup.
 *
 * It deliberately starts at offset 0 rather than skipping past the sections
 * above it. Latest fetches LATEST_FETCH articles and prints a filtered subset,
 * so an offset large enough to avoid repeats would also make everything it
 * filtered out unreachable — articles the database has and no scroll could
 * ever reach. Overlap is removed by id at render time instead, which costs
 * nothing and cannot hide anything.
 */
export const useNewsRiver = (filter: SymbolFilter = null) =>
  useInfiniteQuery({
    queryKey: ['news', 'river', filter],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) =>
      getNews(
        {
          symbols: asSymbols(filter),
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
