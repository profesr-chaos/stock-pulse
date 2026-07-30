import { ArrowDownRight, ArrowUpRight } from 'lucide-react';

import { Skeleton } from '@/components/ui/skeleton';
import { useMovers } from '@/hooks/useInsights';
import { formatPercent, formatPrice } from '@/lib/format';

/**
 * Watchlist stocks by size of price move, with how their news sentiment has
 * shifted against the preceding fortnight. Previously a hard-coded array.
 */
const TopMoversSentiment = () => {
  const { data: movers = [], isLoading } = useMovers(3);

  if (isLoading) {
    return (
      <div className="rounded-xl p-5 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-24 rounded-lg" />
        ))}
      </div>
    );
  }

  if (movers.length === 0) {
    return (
      <div className="rounded-xl p-5 text-sm text-muted-foreground">
        Add stocks to your watchlist to see how they are moving.
      </div>
    );
  }

  return (
    <div className="rounded-xl p-5">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 pt-2">
        {movers.map((mover) => {
          const isUp = (mover.changePercent ?? 0) >= 0;
          return (
            <div
              key={mover.symbol}
              className={`rounded-lg border p-3 transition-colors ${
                isUp
                  ? 'border-emerald-500/20 bg-emerald-500/5 hover:bg-emerald-500/10'
                  : 'border-red-500/20 bg-red-500/5 hover:bg-red-500/10'
              }`}
              title={mover.name ?? mover.symbol}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-bold text-foreground truncate">{mover.symbol}</span>
                {isUp ? (
                  <ArrowUpRight className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                ) : (
                  <ArrowDownRight className="w-3.5 h-3.5 text-red-500 shrink-0" />
                )}
              </div>
              <p className="text-xs text-muted-foreground mb-2 truncate">
                {formatPrice(mover.price, mover.currencyCode)}
              </p>
              <div className="flex items-center justify-between gap-1">
                <span
                  className={`text-xs font-semibold ${isUp ? 'text-emerald-500' : 'text-red-500'}`}
                >
                  {formatPercent(mover.changePercent)}
                </span>
                {mover.sentimentDelta !== null ? (
                  <span
                    className={`text-[10px] font-medium ${
                      mover.sentimentDelta >= 0 ? 'text-emerald-500' : 'text-red-500'
                    }`}
                    title={`News sentiment vs the previous fortnight (${mover.articleCount} articles)`}
                  >
                    {mover.sentimentDelta >= 0 ? '↑' : '↓'}{' '}
                    {Math.abs(mover.sentimentDelta).toFixed(2)}
                  </span>
                ) : (
                  <span className="text-[10px] text-muted-foreground/60">
                    {mover.articleCount || 0} art.
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default TopMoversSentiment;
