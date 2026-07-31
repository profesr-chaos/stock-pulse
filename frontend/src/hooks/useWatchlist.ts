import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';

import { ApiError } from '@/services/api';
import {
  addToWatchlist,
  getWatchlist,
  removeFromWatchlist,
  reorderWatchlist,
} from '@/services/watchlistApi';
import type { Stock } from '@/types/stock';

export const WATCHLIST_KEY = ['watchlist'] as const;

/**
 * The watchlist, owned by the server.
 *
 * It used to live half in localStorage and half in the API depending on
 * whether a token existed. With no accounts there is one source of truth, so
 * mutations simply invalidate the query.
 *
 * Adding also kicks a background backfill server-side, so prices and the first
 * articles for a new stock land a few seconds later — hence the delayed
 * refetch.
 */
export const useWatchlist = () => {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: WATCHLIST_KEY,
    queryFn: () => getWatchlist('watchlist'),
    staleTime: 30_000,
  });

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: WATCHLIST_KEY });
    queryClient.invalidateQueries({ queryKey: ['news'] });
    queryClient.invalidateQueries({ queryKey: ['insights'] });
  }, [queryClient]);

  const addMutation = useMutation({
    mutationFn: (stock: Stock) => addToWatchlist(stock.symbol),
    onSuccess: () => {
      invalidate();
      window.setTimeout(invalidate, 6_000);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (symbol: string) => removeFromWatchlist(symbol),
    onMutate: async (symbol: string) => {
      // Optimistic: removal is instant and trivially reversible.
      await queryClient.cancelQueries({ queryKey: WATCHLIST_KEY });
      const previous = queryClient.getQueryData<Stock[]>(WATCHLIST_KEY);
      queryClient.setQueryData<Stock[]>(
        WATCHLIST_KEY,
        (current) => current?.filter((s) => s.symbol !== symbol) ?? [],
      );
      return { previous };
    },
    onError: (_error, _symbol, context) => {
      if (context?.previous) queryClient.setQueryData(WATCHLIST_KEY, context.previous);
    },
    onSettled: invalidate,
  });

  const reorderMutation = useMutation({
    mutationFn: (symbols: string[]) => reorderWatchlist(symbols),
    onMutate: async (symbols: string[]) => {
      await queryClient.cancelQueries({ queryKey: WATCHLIST_KEY });
      const previous = queryClient.getQueryData<Stock[]>(WATCHLIST_KEY);
      queryClient.setQueryData<Stock[]>(WATCHLIST_KEY, (current) =>
        symbols
          .map((symbol) => current?.find((s) => s.symbol === symbol))
          .filter((s): s is Stock => Boolean(s)),
      );
      return { previous };
    },
    onError: (_error, _symbols, context) => {
      if (context?.previous) queryClient.setQueryData(WATCHLIST_KEY, context.previous);
    },
    onSettled: invalidate,
  });

  const watchlist = query.data ?? [];

  return {
    watchlist,
    symbols: watchlist.map((s) => s.symbol),
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
    isAdding: addMutation.isPending,
    /** Rejects with an ApiError; `isConflict` means it was already there. */
    addStock: (stock: Stock) => addMutation.mutateAsync(stock),
    removeStock: (symbol: string) => removeMutation.mutateAsync(symbol),
    reorder: (symbols: string[]) => reorderMutation.mutateAsync(symbols),
    isInWatchlist: (symbol: string) => watchlist.some((s) => s.symbol === symbol),
  };
};

export { ApiError };
