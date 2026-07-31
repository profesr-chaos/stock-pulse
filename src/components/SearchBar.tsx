import { Search, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import ComboBox, { type ComboOption } from '@/components/ComboBox';
import { useSectors } from '@/hooks/useSectors';
import { useWatchlist } from '@/hooks/useWatchlist';
import type { FeedFilter, SortKey } from '@/hooks/useStockNews';

interface SearchBarProps {
  filter: FeedFilter;
  onChange: (patch: Partial<FeedFilter>) => void;
  onClear: () => void;
}

const SORTS: { value: SortKey; label: string }[] = [
  { value: 'recent', label: 'Most recent' },
  { value: 'sentiment', label: 'Highest sentiment' },
  { value: 'coverage', label: 'Most news articles' },
  { value: 'symbol', label: 'By ticker (A–Z)' },
];

const controlClass =
  'border border-rule bg-paper py-1.5 pl-2 pr-6 text-xs text-ink focus:border-ftblue focus:outline-none';

/**
 * The feed's control surface: news search, ticker filter, sector, sort.
 *
 * The text box searches *news* and nothing else. It used to double as a ticker
 * jump, which made Enter ambiguous — the same keystroke either searched or
 * navigated depending on an invisible highlight. Choosing a ticker is now its
 * own control, and searching a ticker's name still finds that ticker's stories
 * because the query matches the symbol column too.
 *
 * Every control resolves server-side. Filtering or sorting in the browser could
 * only ever touch the page already fetched, while looking like it covered
 * everything stored.
 */
const SearchBar = ({ filter, onChange, onClear }: SearchBarProps) => {
  const [text, setText] = useState(filter.query);
  const [tickerQuery, setTickerQuery] = useState('');
  const { data: sectors = [] } = useSectors();
  const { watchlist } = useWatchlist();

  // Keep the box in step when the filter is cleared from elsewhere on the page.
  useEffect(() => setText(filter.query), [filter.query]);

  // Filtered here rather than through /stocks/search: this list is the
  // watchlist, which is already loaded, and it must stay the watchlist — the
  // catalogue holds 15k instruments with no stored news between them.
  const tickerOptions: ComboOption[] = useMemo(() => {
    const term = tickerQuery.trim().toLowerCase();
    return watchlist
      .filter(
        (stock) =>
          !term ||
          stock.symbol.toLowerCase().includes(term) ||
          (stock.name ?? '').toLowerCase().includes(term),
      )
      .map((stock) => ({ value: stock.symbol, label: stock.symbol, hint: stock.name }));
  }, [watchlist, tickerQuery]);

  const runSearch = () => onChange({ query: text.trim() });

  const activeFilters = [filter.symbol, filter.sector, filter.query.trim()].filter(Boolean);

  return (
    <div className="border-b border-rule bg-paper">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-2 px-3 py-2 md:gap-3 md:px-5">
        <div className="relative w-full min-w-0 max-w-md flex-1">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted"
            aria-hidden="true"
          />
          <input
            type="search"
            aria-label="Search news"
            autoComplete="off"
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                runSearch();
              }
            }}
            // A search input's native clear button empties the field but fires
            // no Enter, so commit on change-to-empty or the results would stay
            // up with nothing in the box.
            onInput={(event) => {
              if ((event.target as HTMLInputElement).value === '') onChange({ query: '' });
            }}
            placeholder="Search news"
            className="w-full border border-rule bg-paper py-1.5 pl-8 pr-3 text-sm text-ink placeholder:text-ink-muted focus:border-ftblue focus:outline-none"
          />
        </div>

        {/* A div, not a label: <button> is labelable, so wrapping the chip in
            a <label> would rename it "Ticker" and throw away the ticker and
            the clear hint its own content provides. The ComboBox carries its
            own aria-label, so nothing here needs the association. */}
        <div className="flex shrink-0 items-center gap-1.5">
          <span className="text-[11px] uppercase tracking-wide text-ink-muted">Ticker</span>
          {filter.symbol ? (
            <button
              type="button"
              onClick={() => onChange({ symbol: null })}
              className="flex items-center gap-1.5 border border-ink-strong px-2 py-1 text-xs hover:bg-paper-tint"
            >
              <span className="font-mono font-semibold text-ftblue">{filter.symbol}</span>
              <X className="h-3 w-3" aria-hidden="true" />
              <span className="sr-only">— clear the ticker filter</span>
            </button>
          ) : (
            <ComboBox
              label="Filter news by stock ticker"
              placeholder="All tickers"
              query={tickerQuery}
              onQueryChange={setTickerQuery}
              options={tickerOptions}
              onSelect={(symbol) => onChange({ symbol })}
              emptyHint="No followed stock matches that."
              className="w-40"
            />
          )}
        </div>

        <label className="flex shrink-0 items-center gap-1.5">
          <span className="text-[11px] uppercase tracking-wide text-ink-muted">Sector</span>
          <select
            value={filter.sector ?? ''}
            onChange={(event) => onChange({ sector: event.target.value || null })}
            className={controlClass}
          >
            <option value="">All sectors</option>
            {sectors.map((sector) => (
              <option key={`${sector.level}:${sector.sector}`} value={sector.sector}>
                {/* Indented so the precise industries read as children of the
                    coarse buckets they sit under, in a plain select. */}
                {sector.level === 'industry' ? '  ' : ''}
                {sector.sector} ({sector.stockCount})
              </option>
            ))}
          </select>
        </label>

        <label className="flex shrink-0 items-center gap-1.5">
          <span className="text-[11px] uppercase tracking-wide text-ink-muted">Sort</span>
          <select
            value={filter.sort}
            onChange={(event) => onChange({ sort: event.target.value as SortKey })}
            className={controlClass}
          >
            {SORTS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        {activeFilters.length > 0 && (
          <button
            type="button"
            onClick={onClear}
            className="flex shrink-0 items-center gap-1.5 border border-ink-strong px-2 py-1 text-xs hover:bg-paper-tint"
          >
            <span className="font-mono font-semibold">{activeFilters.join(' · ')}</span>
            <span className="text-ink-muted">clear all</span>
            <X className="h-3 w-3" aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
};

export default SearchBar;
