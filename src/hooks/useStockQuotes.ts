import { useQuery } from '@tanstack/react-query';

import { STALE_TIME } from '@/config/api';
import { getStockQuotes } from '@/services/stockApi';

/**
 * Quotes for the given symbols.
 *
 * Polling is deliberately gentle: prices are refreshed hourly server-side from
 * free sources, so a 15-second refetch (what this used to do) would just make
 * requests that return the same numbers.
 */
export const useStockQuotes = (symbols: string[]) =>
  useQuery({
    queryKey: ['quotes', [...symbols].sort().join(',')],
    queryFn: () => getStockQuotes(symbols),
    enabled: symbols.length > 0,
    staleTime: STALE_TIME.quotes,
    refetchInterval: STALE_TIME.quotes,
  });
