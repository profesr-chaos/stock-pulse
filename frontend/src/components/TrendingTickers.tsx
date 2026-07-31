import { useMemo } from 'react';

import { useMovers } from '@/hooks/useInsights';
import {
  changeClass,
  formatPercent,
  formatPrice,
  formatSentiment,
  sentimentTextClass,
} from '@/lib/format';
import type { Mover } from '@/types/stock';

interface TrendingTickersProps {
  filter: string | null;
  onSelectSymbol: (symbol: string) => void;
}

const ROWS = 6;

/** What the right-hand column of a row shows: price move, or sentiment. */
type Metric = 'price' | 'sentiment';

const MoverRow = ({
  mover,
  metric,
  active,
  onSelect,
}: {
  mover: Mover;
  metric: Metric;
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
        {metric === 'price' ? (
          <>
            <span className="block font-mono text-xs text-ink-strong">
              {formatPrice(mover.price, mover.currencyCode)}
            </span>
            <span className={`block font-mono text-[11px] ${changeClass(mover.changePercent)}`}>
              {formatPercent(mover.changePercent)}
            </span>
          </>
        ) : (
          <>
            <span className={`block font-mono text-xs ${sentimentTextClass(mover.sentiment)}`}>
              {formatSentiment(mover.sentiment)}
            </span>
            <span className="block font-mono text-[11px] text-ink-muted">
              {mover.articleCount} {mover.articleCount === 1 ? 'story' : 'stories'}
            </span>
          </>
        )}
      </span>
    </button>
  </li>
);

const Panel = ({
  title,
  rows,
  metric,
  empty,
  filter,
  onSelectSymbol,
}: {
  title: string;
  rows: Mover[];
  metric: Metric;
  empty: string;
  filter: string | null;
  onSelectSymbol: (symbol: string) => void;
}) => (
  <div className="border border-rule">
    <h3 className="border-b border-rule bg-paper-tint px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-ink-strong">
      {title}
    </h3>
    {rows.length === 0 ? (
      <p className="px-3 py-3 text-xs text-ink-muted">{empty}</p>
    ) : (
      <ul>
        {rows.map((mover) => (
          <MoverRow
            key={mover.symbol}
            mover={mover}
            metric={metric}
            active={filter === mover.symbol}
            onSelect={onSelectSymbol}
          />
        ))}
      </ul>
    )}
  </div>
);

/**
 * Top gainers and losers — the two halves of one ranked list.
 *
 * Scope is the watchlist, because that is the only universe with stored
 * quotes. Calling it a market-wide leaderboard would be a lie the data cannot
 * back.
 *
 * Not sticky itself: Home pins the whole rail, so that the pinned-ticker panel
 * above this one stays on screen too.
 */
const TrendingTickers = ({ filter, onSelectSymbol }: TrendingTickersProps) => {
  const { data: movers = [], isLoading, isError } = useMovers();

  const { gainers, losers, positive, negative } = useMemo(() => {
    const priced = movers.filter(
      (m) => m.changePercent !== null && m.changePercent !== undefined,
    );
    // Separate filter: a stock can have a quote and no scored coverage, or
    // coverage and no quote. Reusing `priced` here would silently drop the
    // second kind from the sentiment tables.
    const scored = movers.filter((m) => m.sentiment !== null && m.sentiment !== undefined);
    return {
      gainers: priced
        .filter((m) => (m.changePercent as number) > 0)
        .sort((a, b) => (b.changePercent as number) - (a.changePercent as number))
        .slice(0, ROWS),
      losers: priced
        .filter((m) => (m.changePercent as number) < 0)
        .sort((a, b) => (a.changePercent as number) - (b.changePercent as number))
        .slice(0, ROWS),
      positive: scored
        .filter((m) => (m.sentiment as number) > 0)
        .sort((a, b) => (b.sentiment as number) - (a.sentiment as number))
        .slice(0, ROWS),
      negative: scored
        .filter((m) => (m.sentiment as number) < 0)
        .sort((a, b) => (a.sentiment as number) - (b.sentiment as number))
        .slice(0, ROWS),
    };
  }, [movers]);

  return (
    <aside>
      <div className="ft-section">
        <h2 className="ft-section-title">Trending tickers</h2>
        <p className="ft-meta mt-1">Biggest moves on your watchlist</p>
      </div>

      {isLoading && <div className="mt-3 h-[430px] w-full bg-paper-tint" aria-busy="true" />}
      {isError && <p className="mt-3 text-sm text-ink-muted">Could not load movers.</p>}

      {!isLoading && !isError && (
        <div className="mt-3 space-y-4">
          <Panel
            title="Top gainers"
            rows={gainers}
            metric="price"
            empty="Nothing up today."
            filter={filter}
            onSelectSymbol={onSelectSymbol}
          />
          <Panel
            title="Top losers"
            rows={losers}
            metric="price"
            empty="Nothing down today."
            filter={filter}
            onSelectSymbol={onSelectSymbol}
          />

          {/* Sentiment is a different ranking of the same stocks, not a
              different set — a stock can be down on the day and still be the
              best-covered story, which is exactly the divergence worth seeing. */}
          <div className="border-t-2 border-ink-strong pt-3">
            <p className="ft-meta">Ranked by news sentiment instead of price</p>
          </div>
          <Panel
            title="Top sentiment gainers"
            rows={positive}
            metric="sentiment"
            empty="No positive coverage yet."
            filter={filter}
            onSelectSymbol={onSelectSymbol}
          />
          <Panel
            title="Top sentiment losers"
            rows={negative}
            metric="sentiment"
            empty="No negative coverage yet."
            filter={filter}
            onSelectSymbol={onSelectSymbol}
          />
        </div>
      )}
    </aside>
  );
};

export default TrendingTickers;
