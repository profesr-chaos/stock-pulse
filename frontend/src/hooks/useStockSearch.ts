import { useQuery } from '@tanstack/react-query';

import { STALE_TIME } from '@/config/api';
import { getPopularStocks, searchStocks } from '@/services/stockApi';

/** Search results, or the watchlist plus best-covered stocks when empty. */
export const useStockSearch = (query: string) => {
  const trimmed = query.trim();
  return useQuery({
    queryKey: ['stockSearch', trimmed],
    queryFn: ({ signal }) =>
      trimmed ? searchStocks(trimmed, signal) : getPopularStocks(),
    staleTime: STALE_TIME.search,
    placeholderData: (previous) => previous,
  });
};
