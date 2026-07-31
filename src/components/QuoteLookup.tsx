import { Search, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { useStockSearch } from '@/hooks/useStockSearch';
import type { SymbolFilter } from '@/hooks/useStockNews';

interface QuoteLookupProps {
  filter: SymbolFilter;
  onSelect: (symbol: string | null) => void;
}

/**
 * Yahoo's quote lookup, in Yahoo's position.
 *
 * Picking a ticker filters the feed by re-querying the server — the whole news
 * table, not the articles already on screen — so a symbol with coverage but no
 * card rendered yet still resolves.
 *
 * Hand-rolled rather than pulled from cmdk + popover: it is one input and one
 * list, and the two libraries together cost more than the component does.
 */
const QuoteLookup = ({ filter, onSelect }: QuoteLookupProps) => {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // The catalogue is local and fast, but not fast enough to deserve a request
  // per keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 180);
    return () => window.clearTimeout(timer);
  }, [query]);

  const { data: results = [] } = useStockSearch(debounced);
  const options = results.slice(0, 8);

  useEffect(() => setActive(0), [debounced]);

  // Click-away. Blur alone would fire before the option's click handler.
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const choose = (symbol: string) => {
    onSelect(symbol);
    setQuery('');
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') return setOpen(false);
    if (!open || options.length === 0) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((i) => (i + 1) % options.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((i) => (i - 1 + options.length) % options.length);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      choose(options[active].symbol);
    }
  };

  return (
    <div className="border-b border-rule bg-paper">
      <div className="mx-auto flex max-w-[1280px] items-center gap-3 px-3 py-2 md:px-5">
        <div ref={containerRef} className="relative w-full max-w-md">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted"
            aria-hidden="true"
          />
          <input
            type="text"
            role="combobox"
            aria-expanded={open && options.length > 0}
            aria-controls="quote-lookup-list"
            aria-activedescendant={open && options.length ? `quote-option-${active}` : undefined}
            aria-label="Quote lookup — filter the news feed by ticker"
            autoComplete="off"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
            placeholder="Quote lookup"
            className="w-full border border-rule bg-paper py-1.5 pl-8 pr-3 text-sm text-ink placeholder:text-ink-muted focus:border-ftblue focus:outline-none"
          />

          {open && options.length > 0 && (
            <ul
              id="quote-lookup-list"
              role="listbox"
              className="absolute left-0 right-0 top-full z-30 max-h-72 overflow-y-auto border border-ink-strong bg-paper"
            >
              {options.map((stock, index) => (
                <li
                  key={stock.symbol}
                  id={`quote-option-${index}`}
                  role="option"
                  aria-selected={index === active}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => choose(stock.symbol)}
                  className={`flex cursor-pointer items-baseline gap-2 border-b border-rule-light px-3 py-2 last:border-0 ${
                    index === active ? 'bg-paper-tint' : ''
                  }`}
                >
                  <span className="font-mono text-xs font-semibold text-ftblue">{stock.symbol}</span>
                  <span className="truncate text-xs text-ink-muted">{stock.name}</span>
                  {stock.exchange && (
                    <span className="ml-auto shrink-0 font-mono text-[10px] uppercase text-ink-muted">
                      {stock.exchange}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {filter && (
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="flex shrink-0 items-center gap-1.5 border border-ink-strong px-2 py-1 text-xs hover:bg-paper-tint"
          >
            <span className="font-mono font-semibold">{filter}</span>
            <span className="text-ink-muted">clear filter</span>
            <X className="h-3 w-3" aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
};

export default QuoteLookup;
