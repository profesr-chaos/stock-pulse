import { AlertTriangle, TrendingDown, TrendingUp } from 'lucide-react';
import type { ReactNode } from 'react';

import { Skeleton } from '@/components/ui/skeleton';
import { useTrending } from '@/hooks/useInsights';
import { formatPercent } from '@/lib/format';
import type { TrendingStock } from '@/types/stock';

/**
 * Real coverage stats for the watchlist, replacing the hard-coded
 * "NVDA - 1243 mentions" mock this component used to ship.
 *
 * With no other users there is no crowd to measure, so "most covered" means
 * "most articles we actually collected" - honest, and still useful.
 */
const TrendingStocksPanel = () => {
  const { data, isLoading } = useTrending(3);

  if (isLoading) {
    return (
      <div className="rounded-xl p-5 grid grid-cols-1 md:grid-cols-3 gap-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-full" />
          </div>
        ))}
      </div>
    );
  }

  const columns: { label: string; icon?: ReactNode; rows: TrendingStock[]; empty: string }[] = [
    {
      label: 'Most covered (3 days)',
      rows: data?.mostDiscussed ?? [],
      empty: 'No articles collected yet',
    },
    {
      label: 'Most positive sentiment',
      icon: <TrendingUp className="w-3 h-3 text-emerald-500" />,
      rows: data?.mostPositive ?? [],
      empty: 'Not enough scored articles',
    },
    {
      label: 'Negative sentiment shifts',
      icon: <AlertTriangle className="w-3 h-3 text-red-500" />,
      rows: data?.negativeSpikes ?? [],
      empty: 'Nothing turning negative',
    },
  ];

  const sentimentClass = (score: number) =>
    score > 0.2 ? ' text-emerald-500' : score < -0.2 ? ' text-red-500' : '';

  return (
    <div className="rounded-xl p-5">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
        {columns.map((column) => (
          <div key={column.label} className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
              {column.icon}
              {column.label}
            </p>
            {column.rows.length === 0 ? (
              <p className="text-xs text-muted-foreground/60 py-2">{column.empty}</p>
            ) : (
              column.rows.map((row) => (
                <div
                  key={`${column.label}-${row.symbol}`}
                  className="flex items-center justify-between py-1.5 px-2 rounded-lg hover:bg-accent/50 transition-colors"
                  title={row.name ?? row.symbol}
                >
                  <div className="min-w-0">
                    <span className="text-sm font-semibold text-foreground">{row.symbol}</span>
                    <span className="text-xs text-muted-foreground ml-1.5">
                      {row.articleCount} {row.articleCount === 1 ? 'article' : 'articles'}
                      {row.avgSentiment !== null && (
                        <span className={sentimentClass(row.avgSentiment)}>
                          {' · '}
                          {row.avgSentiment > 0 ? '+' : ''}
                          {row.avgSentiment.toFixed(2)}
                        </span>
                      )}
                    </span>
                  </div>
                  {row.changePercent !== null && (
                    <span
                      className={`text-xs font-medium flex items-center gap-0.5 shrink-0 ${
                        row.changePercent >= 0 ? 'text-emerald-500' : 'text-red-500'
                      }`}
                    >
                      {row.changePercent >= 0 ? (
                        <TrendingUp className="w-3 h-3" />
                      ) : (
                        <TrendingDown className="w-3 h-3" />
                      )}
                      {formatPercent(row.changePercent)}
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default TrendingStocksPanel;
