import { useQuery } from '@tanstack/react-query';

import { STALE_TIME } from '@/config/api';
import { getPriceHistory } from '@/services/stockApi';

/**
 * Daily closes for the last `days`, plus intraday snapshots for days the daily
 * feed hasn't closed yet — so the most recent part of the line shows movement
 * within the day.
 */
export const usePriceHistory = (symbol: string | null, days = 30) =>
  useQuery({
    queryKey: ['prices', symbol, days],
    queryFn: () => getPriceHistory(symbol as string, days),
    enabled: Boolean(symbol),
    staleTime: STALE_TIME.prices,
  });
