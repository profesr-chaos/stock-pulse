import { useState } from 'react';
import { Bot, Loader2, Sparkles } from 'lucide-react';
import { Stock } from '@/types/stock';
import { getStockAiSummary } from '@/services/newsApi';
import { ApiError } from '@/services/api';
import { AISummary } from '@/types/stock';
import StreamingText from './StreamingText';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface AiStockSummaryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  stocks: Stock[];
}

const AiStockSummaryDialog = ({ open, onOpenChange, stocks }: AiStockSummaryDialogProps) => {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [summary, setSummary] = useState<AISummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSelectStock = async (symbol: string) => {
    setSelectedSymbol(symbol);
    setSummary(null);
    setError(null);
    setIsLoading(true);

    try {
      const result = await getStockAiSummary(symbol);
      setSummary(result);
    } catch (e) {
      // The only reason this can be unavailable now is a missing DSEEK key;
      // everything else is a genuine failure worth showing verbatim.
      if (e instanceof ApiError && e.isUnavailable) {
        setError('AI summaries need a DeepSeek API key. Set DSEEK in the backend .env file.');
      } else {
        setError(e instanceof Error ? e.message : 'Failed to fetch AI summary');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = (value: boolean) => {
    onOpenChange(value);
    if (!value) {
      setSelectedSymbol(null);
      setSummary(null);
      setError(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-2xl glass-card border-primary/20">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl font-bold">
            <Bot className="w-5 h-5 text-primary" />
            AI News Summary
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-5">
          {/* Stock selector */}
          <div>
            <p className="text-sm text-muted-foreground mb-3">Select a stock to get an AI-powered summary of recent news:</p>
            <div className="flex flex-wrap gap-2">
              {stocks.map((stock) => (
                <Button
                  key={stock.symbol}
                  variant={selectedSymbol === stock.symbol ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => handleSelectStock(stock.symbol)}
                  disabled={isLoading}
                  className="gap-1.5"
                >
                  <span className="font-mono font-semibold">{stock.symbol}</span>
                  <span className="text-xs opacity-70">{stock.name}</span>
                </Button>
              ))}
            </div>
          </div>

          {/* Summary content */}
          {isLoading && (
            <div className="flex items-center justify-center py-10 gap-3">
              <Loader2 className="w-5 h-5 animate-spin text-primary" />
              <span className="text-muted-foreground">Generating AI summary for {selectedSymbol}…</span>
            </div>
          )}

          {error && (
            <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-4 text-destructive text-sm">
              {error}
            </div>
          )}

          {summary && !isLoading && (
            <div className="rounded-lg bg-primary/5 border border-primary/20 p-5 space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                <Sparkles className="w-4 h-4" />
                AI Summary — {selectedSymbol}
              </div>
              <p className="text-foreground leading-relaxed whitespace-pre-line">
                <StreamingText text={summary.ai_summary}/>
              </p>
            </div>
          )}

          {!selectedSymbol && !isLoading && (
            <div className="text-center py-8 text-muted-foreground">
              <Bot className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p>Choose a stock above to generate a summary</p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default AiStockSummaryDialog;
