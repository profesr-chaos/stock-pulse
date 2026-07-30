import { Moon, RefreshCw, Sun, TrendingUp } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { API_BASE_URL } from '@/config/api';
import { toast } from '@/hooks/use-toast';

const Header = () => {
  const { theme, setTheme } = useTheme();
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);

  // Kicks a server-side re-scrape of every followed stock, then re-reads
  // everything once the background job has had a moment to write.
  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const response = await fetch(`${API_BASE_URL}/refresh`, { method: 'POST' });
      if (!response.ok) throw new Error(response.statusText);
      toast({
        title: 'Refreshing',
        description: 'Scraping the latest prices and news in the background.',
      });
      window.setTimeout(() => queryClient.invalidateQueries(), 8_000);
    } catch (error) {
      toast({
        title: 'Could not reach the API',
        description: `Is the backend running on ${API_BASE_URL}?`,
        variant: 'destructive',
      });
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <header className="border-b border-border/50 bg-card/50 backdrop-blur-xl sticky top-0 z-50">
      <div className="container mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10 glow-effect">
              <TrendingUp className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight">StockPulse</h1>
              <p className="text-xs text-muted-foreground">Your stocks, all the news</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
              className="gap-2"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="rounded-full"
            >
              <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
              <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
              <span className="sr-only">Toggle theme</span>
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
