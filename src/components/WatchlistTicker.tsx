import { useEffect, useRef, useState } from 'react';

import { usePriceHistory } from '@/hooks/usePriceHistory';
import { formatAge, formatPercent, formatPrice } from '@/lib/format';
import type { Stock } from '@/types/stock';

interface WatchlistTickerProps {
  stocks: Stock[];
}

/**
 * A 30-day price line, drawn as an inline SVG.
 *
 * Deliberately not a charting library: it is one path from a list of closes,
 * and recharts is already pulled in for the pie without needing to be pulled
 * into a 60px sparkline.
 */
const Sparkline = ({ symbol, positive }: { symbol: string; positive: boolean }) => {
  const { data } = usePriceHistory(symbol, 30);
  const points = data?.points ?? [];

  if (points.length < 2) {
    return <div className="w-16 h-8" />;
  }

  const closes = points.map((p) => p.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;

  const path = closes
    .map((close, index) => {
      const x = (index / (closes.length - 1)) * 60;
      // SVG y grows downward, so invert.
      const y = 28 - ((close - min) / span) * 24;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <svg width="60" height="32" viewBox="0 0 60 32" className="shrink-0" aria-hidden="true">
      <path
        d={path}
        fill="none"
        strokeWidth="1.5"
        className={positive ? 'stroke-emerald-500' : 'stroke-red-500'}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
};

const WatchlistTicker = ({ stocks }: WatchlistTickerProps) => {
  const [offset, setOffset] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (stocks.length <= 3) return;

    const interval = setInterval(() => {
      if (contentRef.current && containerRef.current) {
        const contentWidth = contentRef.current.scrollWidth / 2;
        setOffset((previous) => (previous + 1 >= contentWidth ? 0 : previous + 1));
      }
    }, 30);

    return () => clearInterval(interval);
  }, [stocks.length]);

  if (stocks.length === 0) return null;

  const displayStocks = stocks.length > 3 ? [...stocks, ...stocks] : stocks;

  return (
    <div ref={containerRef} className="overflow-hidden glass-card py-3 px-4">
      <div
        ref={contentRef}
        className="flex gap-4 transition-none"
        style={{
          transform: stocks.length > 3 ? `translateX(-${offset}px)` : 'none',
          width: 'fit-content',
        }}
      >
        {displayStocks.map((stock, index) => {
          const isPositive = (stock.changePercent ?? 0) >= 0;
          return (
            <div
              key={`${stock.symbol}-${index}`}
              className="flex items-center justify-between gap-3 px-4 py-3 bg-card/80 backdrop-blur-sm border border-border/50 rounded-xl shrink-0 min-w-[260px]"
              title={`${stock.name ?? stock.symbol}${
                stock.exchange ? ` · ${stock.exchange}` : ''
              }${stock.priceUpdatedAt ? ` · updated ${formatAge(stock.priceUpdatedAt)} ago` : ''}`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center shrink-0">
                  <span className="stock-ticker text-xs font-bold text-primary">
                    {stock.symbol.slice(0, 2)}
                  </span>
                </div>
                <div className="flex flex-col min-w-0">
                  <span className="stock-ticker font-semibold text-sm text-foreground">
                    {stock.symbol}
                  </span>
                  {/* Currency comes from the resolved listing, so a London line
                      shows pounds and a US one dollars. */}
                  <span className="text-xs text-muted-foreground">
                    {formatPrice(stock.price, stock.currencyCode)}
                  </span>
                </div>
              </div>

              <Sparkline symbol={stock.symbol} positive={isPositive} />

              <div
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold shrink-0 ${
                  isPositive ? 'bg-success/20 text-success' : 'bg-destructive/20 text-destructive'
                }`}
              >
                {formatPercent(stock.changePercent)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default WatchlistTicker;
