import WatchlistWheel from '@/components/WatchlistWheel';
import { changeClass, formatPercent, formatPrice } from '@/lib/format';
import type { Stock } from '@/types/stock';

interface TickerStripProps {
  stocks: Stock[];
  onEdit: () => void;
  onSelect: (symbol: string) => void;
}

/**
 * The very top of the page: wheel, scrolling quotes, masthead.
 *
 * The marquee is one CSS animation over a doubled list — no scroll listener, no
 * timer, no per-frame React state. The old version ticked a `setInterval` every
 * 30ms and re-rendered the whole strip to move it one pixel; this runs on the
 * compositor and stops entirely under `prefers-reduced-motion`.
 */
const TickerStrip = ({ stocks, onEdit, onSelect }: TickerStripProps) => {
  const quoted = stocks.filter((s) => s.price !== null);
  // Enough of a lap that a long watchlist doesn't sprint past.
  const duration = Math.max(30, quoted.length * 6);

  return (
    <div className="border-b border-rule bg-paper">
      <div className="mx-auto flex h-12 max-w-[1600px] items-center gap-3 px-3 md:px-5">
        <WatchlistWheel stocks={stocks} onClick={onEdit} />

        <div className="group relative min-w-0 flex-1 overflow-hidden">
          {quoted.length === 0 ? (
            <p className="ft-meta">Follow a stock to see its price here.</p>
          ) : (
            <div
              className="flex w-max animate-marquee group-hover:[animation-play-state:paused]"
              style={{ ['--marquee-duration' as string]: `${duration}s` }}
            >
              {/* Doubled so the -50% wrap is seamless. The clone is decorative. */}
              {[0, 1].map((copy) => (
                <div key={copy} className="flex" aria-hidden={copy === 1}>
                  {quoted.map((stock) => (
                    <button
                      key={stock.symbol}
                      type="button"
                      tabIndex={copy === 1 ? -1 : undefined}
                      onClick={() => onSelect(stock.symbol)}
                      className="flex shrink-0 items-baseline gap-2 border-r border-rule-light px-4 text-left hover:bg-paper-tint"
                    >
                      <span className="font-mono text-[11px] font-semibold uppercase tracking-wide text-ink-strong">
                        {stock.symbol}
                      </span>
                      <span className="font-mono text-[11px] text-ink">
                        {formatPrice(stock.price, stock.currencyCode)}
                      </span>
                      <span className={`font-mono text-[11px] ${changeClass(stock.changePercent)}`}>
                        {formatPercent(stock.changePercent)}
                      </span>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        <span className="shrink-0 border-l border-rule pl-3 font-serif text-base font-bold tracking-tight text-ink-strong md:pl-4 md:text-lg">
          Stock&nbsp;Pulse
        </span>
      </div>
    </div>
  );
};

export default TickerStrip;
