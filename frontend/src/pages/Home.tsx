import { Suspense, lazy, useCallback, useMemo, useState } from 'react';

import LatestNews from '@/components/LatestNews';
import NewsRiver from '@/components/NewsRiver';
import PinnedTickers from '@/components/PinnedTickers';
import SearchBar from '@/components/SearchBar';
import TickerStrip from '@/components/TickerStrip';
import Toast from '@/components/Toast';
import TrendingNews from '@/components/TrendingNews';
import TrendingTickers from '@/components/TrendingTickers';
import { API_BASE_URL } from '@/config/api';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useToast } from '@/hooks/useToast';
import { describeChange, type ConfigUpdate } from '@/services/configApi';
import {
  DEFAULT_FILTER,
  isSearching,
  useLatestNews,
  useTrendingNews,
  type FeedFilter,
} from '@/hooks/useStockNews';
import { useLiveUpdates } from '@/hooks/useLiveUpdates';
import { useWatchlist } from '@/hooks/useWatchlist';
import type { NewsArticle } from '@/types/stock';

// Behind a click, so they stay out of the initial bundle entirely.
const EditWatchlistDialog = lazy(() => import('@/components/EditWatchlistDialog'));
const ArticleDialog = lazy(() => import('@/components/ArticleDialog'));
const AiSettingsDialog = lazy(() => import('@/components/AiSettingsDialog'));

const Home = () => {
  useLiveUpdates();
  const { watchlist, addStock, removeStock, error } = useWatchlist();
  const [filter, setFilter] = useState<FeedFilter>(DEFAULT_FILTER);
  const [editing, setEditing] = useState(false);
  const [reading, setReading] = useState<NewsArticle | null>(null);
  const [aiSettingsOpen, setAiSettingsOpen] = useState(false);

  const { config, saving, update } = useAppConfig();
  const { message: toast, show: showToast, dismiss: dismissToast } = useToast();

  // The toast reports what the server confirmed, not what was clicked: a write
  // that failed must not announce a change that did not happen.
  const changeAiSetting = useCallback(
    async (patch: ConfigUpdate) => {
      try {
        const message = describeChange(patch, await update(patch));
        if (message) showToast(message);
      } catch {
        showToast('Could not save that — is the API running?');
      }
    },
    [update, showToast],
  );

  const searching = isSearching(filter);

  // Same query keys the two sections use, so this reads their cached results
  // rather than issuing requests of its own.
  const { data: trending } = useTrendingNews(filter);
  const { data: latest } = useLatestNews(filter);
  // Keyed on url, not id: the same story is stored once per ticker it names,
  // so id-based matching lets the river repeat what Trending already led with.
  const shownUrls = useMemo(
    () => new Set([...(trending ?? []), ...(latest ?? [])].map((article) => article.url)),
    [trending, latest],
  );

  // Ad-hoc quote watching in the rail. Session state on purpose: a pin is a
  // temporary look at a ticker, not a change to what gets followed and
  // scraped, so it is deliberately not persisted anywhere.
  const [pinned, setPinned] = useState<string[]>([]);

  const pin = useCallback(
    (symbol: string) => setPinned((current) =>
      current.includes(symbol) ? current : [...current, symbol]),
    [],
  );
  const unpin = useCallback(
    (symbol: string) => setPinned((current) => current.filter((s) => s !== symbol)),
    [],
  );

  // Any filter change is a fresh reading position, not a scroll continuation.
  const change = useCallback((patch: Partial<FeedFilter>) => {
    setFilter((current) => ({ ...current, ...patch }));
    window.scrollTo({ top: 0 });
  }, []);

  const selectSymbol = useCallback(
    (symbol: string | null) => change({ symbol, query: '' }),
    [change],
  );

  const clear = useCallback(() => {
    setFilter(DEFAULT_FILTER);
    window.scrollTo({ top: 0 });
  }, []);

  return (
    <div className="min-h-screen bg-paper">
      <TickerStrip
        stocks={watchlist}
        onEdit={() => setEditing(true)}
        onSelect={selectSymbol}
        onOpenAiSettings={() => setAiSettingsOpen(true)}
        grading={config?.scrapingGradesImpact ?? false}
      />
      <SearchBar filter={filter} onChange={change} onClear={clear} />

      <main className="mx-auto max-w-[1600px] px-3 py-6 md:px-5">
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

        {/*
          Yahoo's three-column masthead: Trending leads, Latest runs down the
          middle beside it, tickers sit on the right rail, and the river picks
          up underneath across the first two.

          The third column only appears at 1400px. Splitting three ways at the
          `xl` 1280 breakpoint leaves the lead under 560px, which is too narrow
          for the hero's headline-beside-image split — it stacks and the section
          gets taller than the two-column version it replaced. Below 1400 the
          page stays as it was: Latest under Trending, tickers on the right.

          Placement is explicit rather than by source order, because the two
          layouts disagree about where Latest and the river belong.
        */}
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px] min-[1400px]:grid-cols-[minmax(0,1fr)_280px_320px]">
          {/* A search answers with one ranked list. Keeping Trending and Latest
              on screen would show three lists where two ignore the search. */}
          {!searching && (
            <>
              <div className="min-w-0 lg:col-start-1 lg:row-start-1">
                <TrendingNews
                  filter={filter}
                  onSelectSymbol={selectSymbol}
                  onOpenArticle={setReading}
                />
              </div>

              <div className="min-w-0 lg:col-start-1 lg:row-start-2 min-[1400px]:col-start-2 min-[1400px]:row-start-1 min-[1400px]:border-l min-[1400px]:border-rule min-[1400px]:pl-6">
                <LatestNews
                  filter={filter}
                  onSelectSymbol={selectSymbol}
                  onOpenArticle={setReading}
                />
              </div>
            </>
          )}

          <div
            className={`min-w-0 lg:col-start-1 min-[1400px]:col-start-1 ${
              searching
                ? 'lg:row-start-1 min-[1400px]:col-span-2 min-[1400px]:row-start-1'
                : 'lg:row-start-3 min-[1400px]:col-span-2 min-[1400px]:row-start-2'
            }`}
          >
            <NewsRiver
              filter={filter}
              shownUrls={shownUrls}
              onSelectSymbol={selectSymbol}
              onOpenArticle={setReading}
            />
          </div>

          {/*
            The rail spans every row so it can stay pinned the whole way down.
            As a single-row item it was only as tall as Trending, and `sticky`
            stops at the bottom of its containing block — so it unpinned at the
            first divider and scrolled away with the page.
          */}
          <div className="lg:col-start-2 lg:row-start-1 lg:row-span-3 min-[1400px]:col-start-3 min-[1400px]:row-span-2">
            <div className="lg:sticky lg:top-4">
              <PinnedTickers
                pinned={pinned}
                onPin={pin}
                onUnpin={unpin}
                onSelectSymbol={selectSymbol}
              />
              <TrendingTickers filter={filter.symbol} onSelectSymbol={selectSymbol} />
            </div>
          </div>
        </div>
      </main>

      <footer className="mt-8 border-t border-rule">
        <div className="mx-auto max-w-[1600px] px-3 py-6 md:px-5">
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

      {reading && (
        <Suspense fallback={null}>
          <ArticleDialog
            article={reading}
            onOpenChange={(open) => !open && setReading(null)}
            onSelectSymbol={selectSymbol}
          />
        </Suspense>
      )}

      {aiSettingsOpen && (
        <Suspense fallback={null}>
          <AiSettingsDialog
            open={aiSettingsOpen}
            onOpenChange={setAiSettingsOpen}
            config={config}
            saving={saving}
            onToggle={changeAiSetting}
            toast={toast}
            onDismissToast={dismissToast}
          />
        </Suspense>
      )}

      {/* While the settings dialog is open it renders the toast itself, inside
          its portal — see AiSettingsDialog. Rendering it here as well would
          duplicate the message; rendering it only there would drop it the
          moment the dialog closes. The message lives up here either way, so it
          survives the handover. */}
      {!aiSettingsOpen && <Toast message={toast} onDismiss={dismissToast} />}
    </div>
  );
};

export default Home;
