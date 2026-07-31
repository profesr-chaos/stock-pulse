import { useMemo } from 'react';

import { useMovers } from './useInsights';
import { useWatchlist } from './useWatchlist';

/**
 * Symbol → today's price move, for the ticker chips scattered through the feed.
 *
 * Both sources are already fetched for the panels above the fold, so this is a
 * join over the query cache rather than a request of its own. A symbol missing
 * from the map has no quote yet — the chip then shows the ticker alone rather
 * than inventing a zero.
 */
export const useMoves = (): Map<string, number> => {
  const { watchlist } = useWatchlist();
  const { data: movers } = useMovers();

  return useMemo(() => {
    const moves = new Map<string, number>();
    for (const stock of watchlist) {
      if (stock.changePercent !== null && stock.changePercent !== undefined) {
        moves.set(stock.symbol, stock.changePercent);
      }
    }
    for (const mover of movers ?? []) {
      if (mover.changePercent !== null && mover.changePercent !== undefined) {
        moves.set(mover.symbol, mover.changePercent);
      }
    }
    return moves;
  }, [watchlist, movers]);
};
