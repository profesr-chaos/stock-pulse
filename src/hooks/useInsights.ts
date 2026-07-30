import { useQuery } from '@tanstack/react-query';

import { STALE_TIME } from '@/config/api';
import { getMovers, getSentimentHistory, getTrending } from '@/services/insightsApi';

export const useTrending = (days = 3) =>
  useQuery({
    queryKey: ['insights', 'trending', days],
    queryFn: () => getTrending(days),
    staleTime: STALE_TIME.insights,
  });

export const useMovers = (days = 3) =>
  useQuery({
    queryKey: ['insights', 'movers', days],
    queryFn: () => getMovers(days),
    staleTime: STALE_TIME.insights,
  });

export const useSentimentHistory = (symbol: string | null, days = 30) =>
  useQuery({
    queryKey: ['insights', 'sentiment', symbol, days],
    queryFn: () => getSentimentHistory(symbol as string, days),
    enabled: Boolean(symbol),
    staleTime: STALE_TIME.insights,
  });
