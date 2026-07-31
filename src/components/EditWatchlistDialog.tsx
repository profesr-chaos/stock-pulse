import * as Dialog from '@radix-ui/react-dialog';
import { Check, Plus, X } from 'lucide-react';
import { useState } from 'react';

import { useStockSearch } from '@/hooks/useStockSearch';
import { ApiError } from '@/services/api';
import type { Stock } from '@/types/stock';

interface EditWatchlistDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  stocks: Stock[];
  onAddStock: (stock: Stock) => Promise<unknown>;
  onRemoveStock: (symbol: string) => Promise<unknown>;
}

/**
 * The wheel's editor. Unchanged in behaviour from the old Edit Pie dialog —
 * search the catalogue, click to follow, X to unfollow — restyled onto FT
 * paper and lazy-loaded, since nobody needs it on first paint.
 *
 * Radix straight, without the shadcn wrapper: the focus trap, the escape key
 * and the aria wiring are worth a dependency; a `cn()` helper over two
 * class-string libraries, for one dialog, is not.
 */
const EditWatchlistDialog = ({
  open,
  onOpenChange,
  stocks,
  onAddStock,
  onRemoveStock,
}: EditWatchlistDialogProps) => {
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const { data: results = [], isFetching } = useStockSearch(query);

  const followed = new Set(stocks.map((s) => s.symbol));

  const add = async (stock: Stock) => {
    setError(null);
    try {
      await onAddStock(stock);
      setQuery('');
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not add that stock — is the API running?',
      );
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink-strong/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col border border-ink-strong bg-paper">
          <div className="flex items-start justify-between gap-3 border-b border-rule px-5 py-4">
            <div>
              <Dialog.Title className="font-serif text-xl font-semibold text-ink-strong">
                Your watchlist
              </Dialog.Title>
              <Dialog.Description className="ft-meta mt-1">
                {stocks.length} followed · adding one pulls a month of prices and news for it
              </Dialog.Description>
            </div>
            <Dialog.Close aria-label="Close" className="p-1 text-ink-muted hover:text-ink-strong">
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          <div className="px-5 py-4">
            <label htmlFor="watchlist-search" className="sr-only">
              Search stocks to follow
            </label>
            <input
              id="watchlist-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search a company or ticker"
              autoComplete="off"
              className="w-full border border-rule bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-ftblue focus:outline-none"
            />

            {error && <p className="mt-2 text-xs text-down">{error}</p>}

            <div className="mt-3 max-h-44 overflow-y-auto border border-rule-light">
              {results.length === 0 ? (
                <p className="px-3 py-4 text-sm text-ink-muted">
                  {isFetching ? 'Searching…' : 'No matches.'}
                </p>
              ) : (
                <ul>
                  {results.map((stock) => {
                    const already = followed.has(stock.symbol);
                    return (
                      <li key={stock.symbol} className="border-b border-rule-light last:border-0">
                        <button
                          type="button"
                          disabled={already}
                          onClick={() => add(stock)}
                          className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-paper-tint disabled:cursor-default disabled:opacity-60"
                        >
                          <span className="min-w-0">
                            <span className="font-mono text-xs font-semibold text-ftblue">
                              {stock.symbol}
                            </span>
                            <span className="ml-2 truncate text-xs text-ink-muted">
                              {stock.name}
                            </span>
                          </span>
                          {already ? (
                            <Check
                              className="h-4 w-4 shrink-0 text-up"
                              aria-label="Already followed"
                            />
                          ) : (
                            <Plus className="h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" />
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto border-t border-rule px-5 py-4">
            <h3 className="ft-meta mb-2 font-semibold uppercase tracking-wide">Following</h3>
            {stocks.length === 0 ? (
              <p className="text-sm text-ink-muted">Nothing followed yet. Search above to start.</p>
            ) : (
              <ul className="divide-y divide-rule-light">
                {stocks.map((stock) => (
                  <li key={stock.symbol} className="flex items-center justify-between gap-3 py-2">
                    <span className="min-w-0">
                      <span className="font-mono text-xs font-semibold text-ink-strong">
                        {stock.symbol}
                      </span>
                      <span className="ml-2 truncate text-xs text-ink-muted">{stock.name}</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => onRemoveStock(stock.symbol)}
                      aria-label={`Unfollow ${stock.symbol}`}
                      className="p-1 text-ink-muted hover:text-down"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};

export default EditWatchlistDialog;
