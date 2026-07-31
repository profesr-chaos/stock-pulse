import { useQuery } from '@tanstack/react-query';

import { STALE_TIME } from '@/config/api';
import { getMovers, getSentimentHistory, getTrending } from '@/services/insightsApi';

export const useTrending = (days = 3) =>
  useQuery({
    queryKey: ['insights', 'trending', days],
    queryFn: () => getTrending(days),
    staleTime: STALE_TIME.insights,
  });

/** Everything the Trending Tickers panel needs; gainers and losers are the
 *  two halves of the same ranked list, so one request covers both. */
export const useMovers = (days = 3, limit = 30) =>
  useQuery({
    queryKey: ['insights', 'movers', days, limit],
    queryFn: () => getMovers(days, limit, days === 3 && limit === 30 ? 'movers' : undefined),
    staleTime: STALE_TIME.insights,
  });

export const useSentimentHistory = (symbol: string | null, days = 30) =>
  useQuery({
    queryKey: ['insights', 'sentiment', symbol, days],
    queryFn: () => getSentimentHistory(symbol as string, days),
    enabled: Boolean(symbol),
    staleTime: STALE_TIME.insights,
  });
