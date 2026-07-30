import { AlertCircle, ChevronDown } from 'lucide-react';
import { useState } from 'react';

import EditPieDialog from '@/components/EditPieDialog';
import Header from '@/components/Header';
import LiveNewsTicker from '@/components/LiveNewsTicker';
import NewsFeed from '@/components/NewsFeed';
import StockPie from '@/components/StockPie';
import StockSearch from '@/components/StockSearch';
import TopMoversSentiment from '@/components/TopMoversSentiment';
import TrendingStocksPanel from '@/components/TrendingStocksPanel';
import WatchlistTicker from '@/components/WatchlistTicker';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Skeleton } from '@/components/ui/skeleton';
import { API_BASE_URL } from '@/config/api';
import { useWatchlist } from '@/hooks/useWatchlist';

const Index = () => {
  const { watchlist, addStock, removeStock, isInWatchlist, loading, error } = useWatchlist();
  const [editPieOpen, setEditPieOpen] = useState(false);
  const [trendingOpen, setTrendingOpen] = useState(true);
  const [moversOpen, setMoversOpen] = useState(true);

  const hasStocks = watchlist.length > 0;

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        {/* The API is local, so a failed watchlist load almost always means the
            backend isn't running. Say so, rather than showing an empty page. */}
        {error && (
          <div className="mb-8 rounded-xl border border-destructive/30 bg-destructive/10 p-4 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-semibold text-destructive">Cannot reach the Stocky API</p>
              <p className="text-muted-foreground mt-1">
                Expected it at <code className="font-mono">{API_BASE_URL}</code>. Start it with{' '}
                <code className="font-mono">python main.py</code> in stocky-backend.
              </p>
              <p className="text-muted-foreground/70 mt-1 text-xs">{error}</p>
            </div>
          </div>
        )}

        {loading && !error && (
          <section className="mb-8 space-y-4">
            <Skeleton className="h-24 rounded-xl" />
            <Skeleton className="h-64 rounded-xl" />
          </section>
        )}

        {/* Hero — only when nothing is followed yet */}
        {!loading && !hasStocks && (
          <section className="mb-12 animate-fade-in relative z-40">
            <div className="p-8 md:p-12 text-center">
              <h1 className="text-4xl md:text-5xl font-bold mb-4 tracking-tight">
                All the news for <span className="gradient-text">your stocks</span>
              </h1>
              <p className="text-lg text-muted-foreground mb-8">
                Add a stock or fund and Stocky pulls a month of prices and news for it, deduplicated
                across sources.
              </p>
              <StockSearch onAddStock={addStock} isInWatchlist={isInWatchlist} />
            </div>
          </section>
        )}

        {/* Compact dashboard once there is a watchlist */}
        {hasStocks && (
          <section className="mb-8 animate-fade-in">
            <div className="flex items-center gap-6">
              <StockPie stocks={watchlist} onClick={() => setEditPieOpen(true)} />
              <div className="flex-1 min-w-0">
                <WatchlistTicker stocks={watchlist} />
              </div>
            </div>
          </section>
        )}

        {hasStocks && (
          <section className="mb-6 animate-fade-in" style={{ animationDelay: '100ms' }}>
            <LiveNewsTicker />
          </section>
        )}

        {hasStocks && (
          <>
            <section className="mb-6 animate-fade-in" style={{ animationDelay: '150ms' }}>
              <Collapsible open={trendingOpen} onOpenChange={setTrendingOpen}>
                <CollapsibleTrigger className="flex items-center justify-between w-full py-2 group cursor-pointer">
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    Coverage &amp; Sentiment
                  </h3>
                  <ChevronDown
                    className={`w-4 h-4 text-muted-foreground transition-transform duration-200 ${
                      trendingOpen ? 'rotate-180' : ''
                    }`}
                  />
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <TrendingStocksPanel />
                </CollapsibleContent>
              </Collapsible>
            </section>

            <section className="mb-8 animate-fade-in" style={{ animationDelay: '200ms' }}>
              <Collapsible open={moversOpen} onOpenChange={setMoversOpen}>
                <CollapsibleTrigger className="flex items-center justify-between w-full py-2 group cursor-pointer">
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    Top Movers
                  </h3>
                  <ChevronDown
                    className={`w-4 h-4 text-muted-foreground transition-transform duration-200 ${
                      moversOpen ? 'rotate-180' : ''
                    }`}
                  />
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <TopMoversSentiment />
                </CollapsibleContent>
              </Collapsible>
            </section>
          </>
        )}

        <section
          className="animate-slide-up relative z-0"
          style={{ animationDelay: hasStocks ? '0ms' : '250ms' }}
        >
          <NewsFeed watchlist={watchlist} />
        </section>
      </main>

      <EditPieDialog
        open={editPieOpen}
        onOpenChange={setEditPieOpen}
        stocks={watchlist}
        onAddStock={addStock}
        onRemoveStock={removeStock}
      />

      <footer className="border-t border-border/50 mt-16">
        <div className="container mx-auto px-4 py-6 text-center text-sm text-muted-foreground">
          <p>StockPulse • prices and news scraped from free sources</p>
        </div>
      </footer>
    </div>
  );
};

export default Index;
