import { useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { useEffect, useState } from 'react';

import ComboBox, { type ComboOption } from '@/components/ComboBox';
import { useSentiments } from '@/hooks/useSentiments';
import { useStockSearch } from '@/hooks/useStockSearch';
import { STALE_TIME } from '@/config/api';
import {
  changeClass,
  formatPercent,
  formatPrice,
  formatSentiment,
  sentimentTextClass,
} from '@/lib/format';
import { getStockQuotes } from '@/services/stockApi';

interface PinnedTickersProps {
  pinned: string[];
  onPin: (symbol: string) => void;
  onUnpin: (symbol: string) => void;
  onSelectSymbol: (symbol: string) => void;
}

/**
 * Ad-hoc quote watching, above the rail's own rankings.
 *
 * Searches the whole catalogue, not just the watchlist, so a ticker can be
 * watched without following it — the point is a temporary look, not a change
 * to what gets scraped. Nothing here is persisted: pins last as long as the
 * page does, which is what "temporary" means and why there is no API for it.
 *
 * Quotes come from /stocks/quotes, which serves whatever is stored. A ticker
 * nobody follows has never been scraped, so it can legitimately come back with
 * no price — that shows as a dash rather than being hidden, or pinning would
 * look broken instead of empty.
 */
const PinnedTickers = ({ pinned, onPin, onUnpin, onSelectSymbol }: PinnedTickersProps) => {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const sentiments = useSentiments();

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 180);
    return () => window.clearTimeout(timer);
  }, [query]);

  const { data: matches = [] } = useStockSearch(debounced);

  const { data: quotes = [] } = useQuery({
    queryKey: ['pinnedQuotes', pinned],
    queryFn: () => getStockQuotes(pinned),
    enabled: pinned.length > 0,
    staleTime: STALE_TIME.search,
  });

  const options: ComboOption[] = matches
    .filter((stock) => !pinned.includes(stock.symbol))
    .slice(0, 8)
    .map((stock) => ({ value: stock.symbol, label: stock.symbol, hint: stock.name }));

  // Render from `pinned` rather than from `quotes`, so a symbol appears the
  // instant it is pinned instead of after the request lands.
  const bySymbol = new Map(quotes.map((quote) => [quote.symbol, quote]));

  return (
    <section className="mb-6">
      <div className="ft-section">
        <h2 className="ft-section-title">Pinned tickers</h2>
        <p className="ft-meta mt-1">Watch a quote without following it</p>
      </div>

      <div className="mt-3">
        <ComboBox
          label="Search for a ticker to pin"
          placeholder="Pin a ticker…"
          query={query}
          onQueryChange={setQuery}
          options={options}
          onSelect={onPin}
          emptyHint={`Nothing in the catalogue matches “${query.trim()}”.`}
        />
      </div>

      {pinned.length > 0 && (
        <ul className="mt-3 border border-rule">
          {pinned.map((symbol) => {
            const quote = bySymbol.get(symbol);
            const sentiment = sentiments.get(symbol);
            return (
              <li
                key={symbol}
                className="flex items-center border-b border-rule-light last:border-0"
              >
                <button
                  type="button"
                  onClick={() => onSelectSymbol(symbol)}
                  className="flex min-w-0 flex-1 items-center justify-between gap-3 px-3 py-2 text-left hover:bg-paper-tint"
                >
                  <span className="min-w-0">
                    <span className="block font-mono text-xs font-semibold text-ftblue">
                      {symbol}
                    </span>
                    <span className="block truncate text-[11px] text-ink-muted">
                      {quote?.name ?? 'Loading…'}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="block font-mono text-xs text-ink-strong">
                      {formatPrice(quote?.price, quote?.currencyCode)}
                    </span>
                    <span
                      className={`block font-mono text-[11px] ${changeClass(quote?.changePercent)}`}
                    >
                      {formatPercent(quote?.changePercent)}
                      {sentiment !== undefined && (
                        <span className={`ml-1.5 ${sentimentTextClass(sentiment)}`}>
                          {formatSentiment(sentiment)}
                        </span>
                      )}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => onUnpin(symbol)}
                  className="shrink-0 self-stretch px-2 text-ink-muted hover:bg-paper-tint hover:text-down"
                  aria-label={`Unpin ${symbol}`}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};

export default PinnedTickers;
