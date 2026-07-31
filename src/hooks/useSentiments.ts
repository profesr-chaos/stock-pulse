import { useMemo } from 'react';

import { useMovers } from './useInsights';

/**
 * Symbol → average sentiment over the recent window, for the ticker chips.
 *
 * Reads the same /insights/movers response the right rail already fetched, so
 * showing a score beside every ticker on the page costs no extra request.
 *
 * A symbol absent from the map has no scored coverage in the window; the chip
 * then shows the ticker alone rather than implying a neutral 0.00, which is a
 * real reading and would be a lie here.
 */
export const useSentiments = (): Map<string, number> => {
  const { data: movers } = useMovers();

  return useMemo(() => {
    const scores = new Map<string, number>();
    for (const mover of movers ?? []) {
      if (mover.sentiment !== null && mover.sentiment !== undefined) {
        scores.set(mover.symbol, mover.sentiment);
      }
    }
    return scores;
  }, [movers]);
};
