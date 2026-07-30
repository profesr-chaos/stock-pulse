import { Check, Loader2, Plus, Search } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from '@/hooks/use-toast';
import { useStockSearch } from '@/hooks/useStockSearch';
import { ApiError } from '@/services/api';
import type { Stock } from '@/types/stock';

interface StockSearchProps {
  onAddStock: (stock: Stock) => Promise<void>;
  isInWatchlist: (symbol: string) => boolean;
}

const StockSearch = ({ onAddStock, isInWatchlist }: StockSearchProps) => {
  const [query, setQuery] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);

  const { data: stocks = [], isLoading } = useStockSearch(query);
  const showResults = isFocused && (stocks.length > 0 || isLoading);

  // No sign-in or upgrade prompts left: everything is available, so the only
  // failures worth reporting are "already following" and the API being down.
  const handleAddStock = async (stock: Stock) => {
    setAdding(stock.symbol);
    try {
      await onAddStock(stock);
      toast({
        title: `Following ${stock.symbol}`,
        description: 'Fetching a month of prices and news in the background.',
      });
      setQuery('');
    } catch (error) {
      const isConflict = error instanceof ApiError && error.isConflict;
      toast({
        title: isConflict ? 'Already on your watchlist' : 'Could not add that stock',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: isConflict ? 'default' : 'destructive',
      });
    } finally {
      setAdding(null);
    }
  };

  return (
    <div className="relative w-full max-w-xl mx-auto z-50">
      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
        <Input
          type="text"
          placeholder="Search stocks or funds by symbol or name..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setTimeout(() => setIsFocused(false), 200)}
          className="pl-12 pr-4 py-6 text-base bg-secondary/50 border-border/50 focus:border-primary/50 focus:ring-primary/20 rounded-xl"
        />
      </div>

      {showResults && (
        <div className="absolute top-full left-0 right-0 mt-2 glass-card p-2 max-h-80 overflow-y-auto z-50 animate-fade-in">
          {isLoading ? (
            <div className="space-y-2 p-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-3 p-3">
                  <Skeleton className="w-10 h-10 rounded-lg" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-4 w-16" />
                    <Skeleton className="h-3 w-32" />
                  </div>
                  <Skeleton className="h-8 w-16 rounded-md" />
                </div>
              ))}
            </div>
          ) : (
            stocks.map((stock) => {
              const inWatchlist = isInWatchlist(stock.symbol);
              const isBusy = adding === stock.symbol;
              return (
                <div
                  key={stock.symbol}
                  className="flex items-center justify-between p-3 rounded-lg hover:bg-accent/50 transition-colors cursor-pointer"
                  onClick={() => !inWatchlist && !isBusy && handleAddStock(stock)}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                      <span className="stock-ticker font-semibold text-primary">
                        {stock.symbol.slice(0, 2)}
                      </span>
                    </div>
                    <div className="min-w-0">
                      <p className="font-medium stock-ticker">{stock.symbol}</p>
                      <p className="text-sm text-muted-foreground truncate">
                        {stock.name}
                        {stock.exchange && (
                          <span className="text-xs text-muted-foreground/60">
                            {' '}
                            · {stock.exchange}
                          </span>
                        )}
                      </p>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant={inWatchlist ? 'secondary' : 'default'}
                    className="gap-1.5 shrink-0"
                    disabled={inWatchlist || isBusy}
                  >
                    {isBusy ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : inWatchlist ? (
                      <>
                        <Check className="w-4 h-4" />
                        Added
                      </>
                    ) : (
                      <>
                        <Plus className="w-4 h-4" />
                        Add
                      </>
                    )}
                  </Button>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};

export default StockSearch;
