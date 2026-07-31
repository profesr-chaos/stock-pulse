import { useQuery } from '@tanstack/react-query';

import { STALE_TIME } from '@/config/api';
import { getSectors } from '@/services/stockApi';

/**
 * The sector filter menu.
 *
 * Only sectors that actually hold a followed stock come back, so the list is
 * short and every entry returns articles. It changes only when the watchlist
 * does, hence the long stale time — this is not feed data.
 */
export const useSectors = () =>
  useQuery({
    queryKey: ['sectors'],
    queryFn: getSectors,
    staleTime: STALE_TIME.search,
  });
