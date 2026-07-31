import { useMemo } from 'react';

import { useMovers } from '@/hooks/useInsights';
import { changeClass, formatPercent, formatPrice } from '@/lib/format';
import type { Mover } from '@/types/stock';

interface TrendingTickersProps {
  filter: string | null;
  onSelectSymbol: (symbol: string) => void;
}

const ROWS = 6;

const MoverRow = ({
  mover,
  active,
  onSelect,
}: {
  mover: Mover;
  active: boolean;
  onSelect: (symbol: string) => void;
}) => (
  <li className="border-b border-rule-light last:border-0">
    <button
      type="button"
      onClick={() => onSelect(mover.symbol)}
      aria-current={active ? 'true' : undefined}
      className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-paper-tint ${
        active ? 'bg-paper-tint' : ''
      }`}
    >
      <span className="min-w-0">
        <span className="block font-mono text-xs font-semibold text-ftblue">{mover.symbol}</span>
        <span className="block truncate text-[11px] text-ink-muted">{mover.name ?? '—'}</span>
      </span>
      <span className="shrink-0 text-right">
        <span className="block font-mono text-xs text-ink-strong">
          {formatPrice(mover.price, mover.currencyCode)}
        </span>
        <span className={`block font-mono text-[11px] ${changeClass(mover.changePercent)}`}>
          {formatPercent(mover.changePercent)}
        </span>
      </span>
    </button>
  </li>
);

/**
 * Top gainers and losers — the two halves of one ranked list.
 *
 * Scope is the watchlist, because that is the only universe with stored
 * quotes. Calling it a market-wide leaderboard would be a lie the data cannot
 * back.
 */
const TrendingTickers = ({ filter, onSelectSymbol }: TrendingTickersProps) => {
  const { data: movers = [], isLoading, isError } = useMovers();

  const { gainers, losers } = useMemo(() => {
    const priced = movers.filter(
      (m) => m.changePercent !== null && m.changePercent !== undefined,
    );
    return {
      gainers: priced
        .filter((m) => (m.changePercent as number) > 0)
        .sort((a, b) => (b.changePercent as number) - (a.changePercent as number))
        .slice(0, ROWS),
      losers: priced
        .filter((m) => (m.changePercent as number) < 0)
        .sort((a, b) => (a.changePercent as number) - (b.changePercent as number))
        .slice(0, ROWS),
    };
  }, [movers]);

  return (
    <aside className="lg:sticky lg:top-4">
      <div className="ft-section">
        <h2 className="ft-section-title">Trending tickers</h2>
        <p className="ft-meta mt-1">Biggest moves on your watchlist</p>
      </div>

      {isLoading && <div className="mt-3 h-[430px] w-full bg-paper-tint" aria-busy="true" />}
      {isError && <p className="mt-3 text-sm text-ink-muted">Could not load movers.</p>}

      {!isLoading && !isError && (
        <div className="mt-3 space-y-4">
          <div className="border border-rule">
            <h3 className="border-b border-rule bg-paper-tint px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-ink-strong">
              Top gainers
            </h3>
            {gainers.length === 0 ? (
              <p className="px-3 py-3 text-xs text-ink-muted">Nothing up today.</p>
            ) : (
              <ul>
                {gainers.map((mover) => (
                  <MoverRow
                    key={mover.symbol}
                    mover={mover}
                    active={filter === mover.symbol}
                    onSelect={onSelectSymbol}
                  />
                ))}
              </ul>
            )}
          </div>

          <div className="border border-rule">
            <h3 className="border-b border-rule bg-paper-tint px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-ink-strong">
              Top losers
            </h3>
            {losers.length === 0 ? (
              <p className="px-3 py-3 text-xs text-ink-muted">Nothing down today.</p>
            ) : (
              <ul>
                {losers.map((mover) => (
                  <MoverRow
                    key={mover.symbol}
                    mover={mover}
                    active={filter === mover.symbol}
                    onSelect={onSelectSymbol}
                  />
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </aside>
  );
};

export default TrendingTickers;
