import { useQuery } from '@tanstack/react-query';

import { STALE_TIME } from '@/config/api';
import { getLatestHeadlines, getNews, type NewsQuery } from '@/services/newsApi';

/**
 * News for the given symbols. With none, the backend returns the whole
 * watchlist's feed in one request rather than one request per stock.
 */
export const useStockNews = (symbols: string[], query: Omit<NewsQuery, 'symbols'> = {}) =>
  useQuery({
    queryKey: ['news', 'feed', [...symbols].sort().join(','), query],
    queryFn: ({ signal }) => getNews({ symbols, ...query }, signal),
    enabled: symbols.length > 0,
    staleTime: STALE_TIME.news,
  });

/** Newest watchlist headlines, for the ticker strip. */
export const useLatestHeadlines = (limit = 20) =>
  useQuery({
    queryKey: ['news', 'latest', limit],
    queryFn: () => getLatestHeadlines(limit),
    staleTime: STALE_TIME.news,
    refetchInterval: 120_000,
  });
