import { Suspense, lazy, useMemo, useState } from 'react';

import LatestNews from '@/components/LatestNews';
import NewsRiver from '@/components/NewsRiver';
import QuoteLookup from '@/components/QuoteLookup';
import TickerStrip from '@/components/TickerStrip';
import TrendingNews from '@/components/TrendingNews';
import TrendingTickers from '@/components/TrendingTickers';
import { API_BASE_URL } from '@/config/api';
import {
  useLatestNews,
  useTrendingNews,
  type SymbolFilter,
} from '@/hooks/useStockNews';
import { useWatchlist } from '@/hooks/useWatchlist';

// Behind a click, so it stays out of the initial bundle entirely.
const EditWatchlistDialog = lazy(() => import('@/components/EditWatchlistDialog'));

const Home = () => {
  const { watchlist, addStock, removeStock, error } = useWatchlist();
  const [filter, setFilter] = useState<SymbolFilter>(null);
  const [editing, setEditing] = useState(false);

  // Same query keys the two sections use, so this reads their cached results
  // rather than issuing requests of its own.
  const { data: trending } = useTrendingNews(filter);
  const { data: latest } = useLatestNews(filter);
  const shownIds = useMemo(
    () => new Set([...(trending ?? []), ...(latest ?? [])].map((article) => article.id)),
    [trending, latest],
  );

  // A filter is a fresh reading position, not a scroll continuation.
  const select = (symbol: string | null) => {
    setFilter(symbol);
    window.scrollTo({ top: 0 });
  };

  return (
    <div className="min-h-screen bg-paper">
      <TickerStrip stocks={watchlist} onEdit={() => setEditing(true)} onSelect={select} />
      <QuoteLookup filter={filter} onSelect={select} />

      <main className="mx-auto max-w-[1280px] px-3 py-6 md:px-5">
        {/* The API is local, so a failed watchlist load almost always means the
            backend isn't running. Say so, rather than showing an empty page. */}
        {error && (
          <div className="mb-6 border-l-4 border-down bg-paper-tint px-4 py-3 text-sm">
            <p className="font-semibold text-ink-strong">Cannot reach the Stocky API</p>
            <p className="mt-1 text-ink-muted">
              Expected it at <code className="font-mono">{API_BASE_URL}</code>. Start it with{' '}
              <code className="font-mono">python main.py</code> in stocky-backend.
            </p>
          </div>
        )}

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-10">
          <div className="min-w-0">
            <TrendingNews filter={filter} onSelectSymbol={select} />
            <LatestNews filter={filter} onSelectSymbol={select} />
            <NewsRiver filter={filter} shownIds={shownIds} onSelectSymbol={select} />
          </div>

          <TrendingTickers filter={filter} onSelectSymbol={select} />
        </div>
      </main>

      <footer className="mt-8 border-t border-rule">
        <div className="mx-auto max-w-[1280px] px-3 py-6 md:px-5">
          <p className="ft-meta">
            Stock Pulse · prices and news scraped from free sources · no accounts, no tracking
          </p>
        </div>
      </footer>

      {editing && (
        <Suspense fallback={null}>
          <EditWatchlistDialog
            open={editing}
            onOpenChange={setEditing}
            stocks={watchlist}
            onAddStock={addStock}
            onRemoveStock={removeStock}
          />
        </Suspense>
      )}
    </div>
  );
};

export default Home;
