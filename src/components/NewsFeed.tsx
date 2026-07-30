import { useMemo, useState, useCallback } from 'react';
import { Sparkles, RefreshCw, Bot, ArrowUpDown } from 'lucide-react';
import { Stock, NewsArticle } from '@/types/stock';
import { useStockNews } from '@/hooks/useStockNews';
import LatestNewsSidebar from './LatestNewsSidebar';
import { useTheme } from 'next-themes';
import previewDark from '@/assets/preview-dark.png';
import previewLight from '@/assets/preview-light.png';
import FocusSection from './FocusSection';
import FeaturedNewsCard from './FeaturedNewsCard';
import SecondaryNewsRow from './SecondaryNewsRow';
import NewsDetailDialog from './NewsDetailDialog';
import AiStockSummaryDialog from './AiStockSummaryDialog';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface NewsFeedProps {
  watchlist: Stock[];
}

const NewsFeed = ({ watchlist }: NewsFeedProps) => {
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [shuffleKey, setShuffleKey] = useState(0);
  const [isShaking, setIsShaking] = useState(false);
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [aiSummaryOpen, setAiSummaryOpen] = useState(false);
  const [sortBy, setSortBy] = useState<string>('date');
  const [filterStock, setFilterStock] = useState<string>('all');
  const [filterSentiment, setFilterSentiment] = useState<string>('all');
  const [filterRelevance, setFilterRelevance] = useState<string>('all');

  const symbols = useMemo(() => watchlist.map((s) => s.symbol), [watchlist]);
  const { data: allNews = [], isLoading, refetch } = useStockNews(symbols);

  const handleArticleClick = useCallback((article: NewsArticle) => {
    setSelectedArticle(article);
    setDialogOpen(true);
  }, []);

  // Filtered and sorted news
  const shuffledMainNews = useMemo(() => {
    let filtered = selectedCategories.length > 0
      ? allNews.filter((article) =>
          selectedCategories.includes(article.source_domain ?? article.source),
        )
      : [...allNews];

    // Filter by stock
    if (filterStock !== 'all') {
      filtered = filtered.filter((a) => a.short_name === filterStock);
    }

    // Hide sector context that never names the stock
    if (filterRelevance === 'direct') {
      filtered = filtered.filter((a) => a.relevance === 'direct');
    }

    // Filter by sentiment
    if (filterSentiment !== 'all') {
      filtered = filtered.filter((a) => {
        if (a.sentiment === null) return filterSentiment === 'neutral';
        if (filterSentiment === 'positive') return a.sentiment > 0.2;
        if (filterSentiment === 'negative') return a.sentiment < -0.2;
        if (filterSentiment === 'neutral') return a.sentiment >= -0.2 && a.sentiment <= 0.2;
        return true;
      });
    }

    // Sort
    if (sortBy === 'date') {
      filtered.sort((a, b) => new Date(b.publish_time).getTime() - new Date(a.publish_time).getTime());
    } else if (sortBy === 'stock') {
      filtered.sort((a, b) => a.short_name.localeCompare(b.short_name));
    } else if (sortBy === 'sentiment') {
      // Most positive first. sentiment is a number in [-1, 1]; the previous
      // version indexed a string map with it, so this sort never did anything.
      filtered.sort((a, b) => (b.sentiment ?? 0) - (a.sentiment ?? 0));
    } else if (sortBy === 'source') {
      filtered.sort((a, b) =>
        (a.source_domain ?? a.source).localeCompare(b.source_domain ?? b.source),
      );
    }

    // Shuffle on top if requested
    if (shuffleKey > 0 && sortBy === 'date') {
      for (let i = filtered.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [filtered[i], filtered[j]] = [filtered[j], filtered[i]];
      }
    }

    return filtered;
  }, [allNews, selectedCategories, shuffleKey, sortBy, filterStock, filterSentiment, filterRelevance]);

  const handleRefresh = useCallback(() => {
    setIsShaking(true);
    setShuffleKey((prev) => prev + 1);
    // Also refetch from API when not using mock data
    refetch();

    setTimeout(() => {
      setIsShaking(false);
    }, 500);
  }, [refetch]);

  // Show more articles - split for layout
  const featuredArticle = shuffledMainNews[0];
  const secondFeatured = shuffledMainNews[1];
  const thirdFeatured = shuffledMainNews[2];
  const fourthFeatured = shuffledMainNews[3];
  const secondaryArticles = shuffledMainNews.slice(4, 7);
  const additionalFeatured = shuffledMainNews.slice(7, 13);
  const sidebarArticles = allNews;
  const { resolvedTheme } = useTheme();

  if (watchlist.length === 0) {
    return (
      <div className="glass-card p-8 md:p-12">
        <div className="flex flex-col md:flex-row gap-8 items-center">
          {/* Left: Text */}
          <div className="md:w-5/12 text-left shrink-0">
            <div className="w-16 h-16 mb-4 rounded-2xl bg-primary/10 flex items-center justify-center">
              <Sparkles className="w-8 h-8 text-primary" />
            </div>
            <h3 className="text-xl font-semibold mb-2">Start tracking stocks</h3>
            <p className="text-muted-foreground">
              Search and add stocks to your watchlist to see the latest news and market updates
            </p>
          </div>

          {/* Right: Preview Image */}
          <div className="md:w-7/12 min-w-0">
            <div className="rounded-xl border border-border/30 shadow-lg overflow-hidden">
              <img
                src={resolvedTheme === 'light' ? previewLight : previewDark}
                alt="StockPulse dashboard preview showing stock tracking and news feed"
                className="w-full h-auto"
                loading="lazy"
              />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        <div className="lg:col-span-3 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Skeleton className="md:col-span-2 h-64 rounded-xl" />
            <div className="space-y-4">
              <Skeleton className="h-[7.5rem] rounded-xl" />
              <Skeleton className="h-[7.5rem] rounded-xl" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <Skeleton className="h-32 rounded-xl" />
            <Skeleton className="h-32 rounded-xl" />
            <Skeleton className="h-32 rounded-xl" />
          </div>
        </div>
        <div>
          <Skeleton className="h-96 rounded-xl" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        {/* Main News Container */}
        <div className="lg:col-span-3 glass-card border border-border/50 rounded-xl overflow-hidden">
          {/* Controls - sticky at top */}
          <div className="sticky top-0 z-10 bg-card/95 backdrop-blur-md border-b border-border/50 px-6 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <Select value={sortBy} onValueChange={setSortBy}>
                  <SelectTrigger className="w-[130px] h-9 text-xs border-border/50">
                    <ArrowUpDown className="w-3.5 h-3.5 mr-1.5 shrink-0" />
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="date">Date</SelectItem>
                    <SelectItem value="stock">Stock</SelectItem>
                    <SelectItem value="sentiment">Sentiment</SelectItem>
                    <SelectItem value="source">Source</SelectItem>
                  </SelectContent>
                </Select>

                <Select value={filterStock} onValueChange={setFilterStock}>
                  <SelectTrigger className="w-[130px] h-9 text-xs border-border/50">
                    <SelectValue placeholder="All Stocks" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Stocks</SelectItem>
                    {watchlist.map((s) => (
                      <SelectItem key={s.symbol} value={s.symbol}>{s.symbol}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select value={filterSentiment} onValueChange={setFilterSentiment}>
                  <SelectTrigger className="w-[140px] h-9 text-xs border-border/50">
                    <SelectValue placeholder="All Sentiment" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Sentiment</SelectItem>
                    <SelectItem value="positive">Positive</SelectItem>
                    <SelectItem value="neutral">Neutral</SelectItem>
                    <SelectItem value="negative">Negative</SelectItem>
                  </SelectContent>
                </Select>

                <Select value={filterRelevance} onValueChange={setFilterRelevance}>
                  <SelectTrigger className="w-[150px] h-9 text-xs border-border/50">
                    <SelectValue placeholder="All Coverage" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Coverage</SelectItem>
                    <SelectItem value="direct">Names the stock</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setAiSummaryOpen(true)}
                  className="gap-2 border-primary/30 hover:border-primary hover:bg-primary/10 transition-all"
                >
                  <Bot className="w-4 h-4" />
                  AI Summary
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRefresh}
                  className="gap-2 border-primary/30 hover:border-primary hover:bg-primary/10 transition-all"
                >
                  <RefreshCw className={`w-4 h-4 ${isShaking ? 'animate-spin' : ''}`} />
                  Refresh
                </Button>
              </div>
            </div>
          </div>

          {/* Scrollable news content */}
          <div className="max-h-[80vh] overflow-y-auto scrollbar-hide px-6 py-6 space-y-6">
            {/* Featured Grid - Asymmetric layout */}
            {shuffledMainNews.length > 0 && (
              <div className={`grid grid-cols-1 md:grid-cols-3 gap-4 ${isShaking ? 'animate-shake' : ''}`}>
                {featuredArticle && (
                  <div className="md:col-span-2">
                    <FeaturedNewsCard article={featuredArticle} size="large" onArticleClick={handleArticleClick} />
                  </div>
                )}
                <div className="space-y-4">
                  {secondFeatured && (
                    <FeaturedNewsCard article={secondFeatured} size="small" onArticleClick={handleArticleClick} />
                  )}
                  {thirdFeatured && (
                    <FeaturedNewsCard article={thirdFeatured} size="small" onArticleClick={handleArticleClick} />
                  )}
                </div>
              </div>
            )}

            {/* Secondary Row */}
            {secondaryArticles.length > 0 && (
              <div className={isShaking ? 'animate-shake' : ''}>
                <SecondaryNewsRow articles={secondaryArticles} onArticleClick={handleArticleClick} />
              </div>
            )}

            {/* Third featured section */}
            {fourthFeatured && shuffledMainNews.length > 4 && (
              <div className={`grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-border/30 pt-6 ${isShaking ? 'animate-shake' : ''}`}>
                <FeaturedNewsCard article={fourthFeatured} size="medium" onArticleClick={handleArticleClick} />
                {shuffledMainNews[5] && (
                  <div className="space-y-4">
                    <FeaturedNewsCard article={shuffledMainNews[5]} size="small" onArticleClick={handleArticleClick} />
                    {shuffledMainNews[6] && (
                      <FeaturedNewsCard article={shuffledMainNews[6]} size="small" onArticleClick={handleArticleClick} />
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Additional articles section */}
            {additionalFeatured.length > 0 && (
              <div className={`border-t border-border/30 pt-6 space-y-6 ${isShaking ? 'animate-shake' : ''}`}>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {additionalFeatured[0] && (
                    <FeaturedNewsCard article={additionalFeatured[0]} size="medium" onArticleClick={handleArticleClick} />
                  )}
                  {additionalFeatured[1] && (
                    <FeaturedNewsCard article={additionalFeatured[1]} size="medium" onArticleClick={handleArticleClick} />
                  )}
                  {additionalFeatured[2] && (
                    <FeaturedNewsCard article={additionalFeatured[2]} size="medium" onArticleClick={handleArticleClick} />
                  )}
                </div>
                {additionalFeatured.length > 3 && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {additionalFeatured.slice(3).map((article) => (
                      <FeaturedNewsCard key={article.id} article={article} size="medium" onArticleClick={handleArticleClick} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar - independent, aligned with top of news container */}
        <div className="space-y-8">
          <div className="glass-card p-4">
            <LatestNewsSidebar articles={sidebarArticles} onArticleClick={handleArticleClick} />
          </div>
          <div className="glass-card p-4">
            <FocusSection
              articles={allNews}
              selectedCategories={selectedCategories}
              onCategorySelect={setSelectedCategories}
            />
          </div>
        </div>
      </div>

      <NewsDetailDialog
        article={selectedArticle}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />

      <AiStockSummaryDialog
        open={aiSummaryOpen}
        onOpenChange={setAiSummaryOpen}
        stocks={watchlist}
      />
    </div>
  );
};

export default NewsFeed;
