import { useState } from 'react';
import { X, Search, Plus, Check } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { Stock } from '@/types/stock';
import { useStockSearch } from '@/hooks/useStockSearch';
import { toast } from '@/hooks/use-toast';
import { ApiError } from '@/services/api';

interface EditPieDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  stocks: Stock[];
  onAddStock: (stock: Stock) => Promise<void>;
  onRemoveStock: (symbol: string) => Promise<void>;
}

// Neon/tech-style colors
const COLORS = [
  'hsl(150, 100%, 50%)',  // neon green
  'hsl(190, 100%, 50%)',  // neon cyan
  'hsl(280, 100%, 65%)',  // neon purple
  'hsl(320, 100%, 60%)',  // neon pink
  'hsl(45, 100%, 50%)',   // neon yellow
  'hsl(200, 100%, 55%)',  // electric blue
  'hsl(0, 100%, 60%)',    // neon red
  'hsl(260, 100%, 70%)',  // lavender neon
];

const EditPieDialog = ({ 
  open, 
  onOpenChange, 
  stocks, 
  onAddStock, 
  onRemoveStock 
}: EditPieDialogProps) => {
  const [searchQuery, setSearchQuery] = useState('');
  const { data: filteredStocks = [], isLoading } = useStockSearch(searchQuery);

  const pieData = stocks.map((stock, index) => ({
    name: stock.symbol,
    value: 1,
    color: COLORS[index % COLORS.length],
  }));

  const emptyData = [{ name: 'Empty', value: 1, color: 'hsl(var(--muted))' }];
  const chartData = stocks.length > 0 ? pieData : emptyData;

  const isInWatchlist = (symbol: string) => stocks.some(s => s.symbol === symbol);

  const handleAddStock = async (stock: Stock) => {
    try {
      await onAddStock(stock);
      setSearchQuery('');
    } catch (error) {
      const isConflict = error instanceof ApiError && error.isConflict;
      toast({
        title: isConflict ? 'Already on your watchlist' : 'Could not add that stock',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: isConflict ? 'default' : 'destructive',
      });
    }
  };

  const showSuggestions = searchQuery.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg bg-card/95 backdrop-blur-xl border-primary/20 max-h-[90vh] flex flex-col shadow-[0_0_40px_rgba(0,255,200,0.15)]">
        <DialogHeader>
          <DialogTitle className="text-center text-lg font-bold bg-gradient-to-r from-primary to-cyan-400 bg-clip-text text-transparent">
            Edit Pie
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col items-center gap-4 py-4 flex-1 overflow-hidden">
          {/* Pie Chart */}
          <div className="relative w-40 h-40 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={75}
                  paddingAngle={stocks.length > 1 ? 3 : 0}
                  dataKey="value"
                  stroke="none"
                >
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-bold">{stocks.length}</span>
              <span className="text-xs text-muted-foreground">Stocks</span>
            </div>
          </div>

          {/* Search Section */}
          <div className="w-full space-y-2 relative">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-primary/70" />
              <Input
                placeholder="Type to search stocks..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 bg-background/50 border-primary/30 focus:border-primary focus:ring-primary/30 placeholder:text-muted-foreground/60"
              />
            </div>
            
            {showSuggestions && (
              <ScrollArea className="h-40 rounded-lg border border-primary/20 bg-background/80 backdrop-blur-sm shadow-[0_0_20px_rgba(0,255,200,0.1)]">
                <div className="p-2 space-y-1">
                  {isLoading ? (
                    <div className="space-y-2 p-2">
                      {[1, 2, 3].map((i) => (
                        <div key={i} className="flex items-center gap-2 p-2.5">
                          <Skeleton className="h-4 w-12" />
                          <Skeleton className="h-3 w-24" />
                        </div>
                      ))}
                    </div>
                  ) : filteredStocks.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">No stocks found</p>
                  ) : (
                    filteredStocks.map((stock) => {
                      const inList = isInWatchlist(stock.symbol);
                      return (
                        <div
                          key={stock.symbol}
                          className={`flex items-center justify-between p-2.5 rounded-lg transition-all ${
                            inList 
                              ? 'bg-primary/10 border border-primary/20' 
                              : 'hover:bg-primary/5 hover:border-primary/10 border border-transparent cursor-pointer'
                          }`}
                          onClick={() => !inList && handleAddStock(stock)}
                        >
                          <div className="flex items-center gap-2">
                            <span className="stock-ticker font-semibold text-sm text-primary">{stock.symbol}</span>
                            <span className="text-xs text-muted-foreground truncate">{stock.name}</span>
                          </div>
                          {inList ? (
                            <Check className="w-4 h-4 text-primary shrink-0" />
                          ) : (
                            <Plus className="w-4 h-4 text-primary/60 shrink-0" />
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </ScrollArea>
            )}
          </div>

          {/* Holdings list */}
          <div className="w-full space-y-3 flex-1 min-h-0">
            <h4 className="text-sm font-semibold text-primary/80 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
              Holdings ({stocks.length})
            </h4>
            <ScrollArea className="h-48">
              <div className="space-y-2 pr-4">
                {stocks.length === 0 ? (
                  <div className="text-center py-8 space-y-2">
                    <div className="w-12 h-12 mx-auto rounded-full bg-primary/10 flex items-center justify-center">
                      <Plus className="w-6 h-6 text-primary/50" />
                    </div>
                    <p className="text-sm text-muted-foreground">
                      No stocks yet. Start typing to search.
                    </p>
                  </div>
                ) : (
                  stocks.map((stock, index) => (
                    <div
                      key={stock.symbol}
                      className="flex items-center justify-between p-3 rounded-lg bg-gradient-to-r from-background/80 to-background/40 border border-primary/10 hover:border-primary/30 transition-all group"
                    >
                      <div className="flex items-center gap-3">
                        <div 
                          className="w-3 h-3 rounded-full shrink-0 shadow-[0_0_8px_currentColor]"
                          style={{ backgroundColor: COLORS[index % COLORS.length], color: COLORS[index % COLORS.length] }}
                        />
                        <div className="min-w-0">
                          <span className="stock-ticker font-semibold text-foreground">{stock.symbol}</span>
                          <p className="text-xs text-muted-foreground truncate">{stock.name}</p>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-red-400 hover:bg-red-500/10 shrink-0 opacity-50 group-hover:opacity-100 transition-opacity"
                        onClick={() => void onRemoveStock(stock.symbol)}
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  ))
                )}
              </div>
            </ScrollArea>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default EditPieDialog;