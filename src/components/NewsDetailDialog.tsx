import { useState } from 'react';
import { ExternalLink, TrendingUp, TrendingDown, Minus, Clock, Bot, Loader2, Sparkles } from 'lucide-react';
import { NewsArticle } from '@/types/stock';
import { formatDistanceToNow } from 'date-fns';
import { getArticleAiSummary } from '@/services/newsApi';
import StreamingText from './StreamingText';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface NewsDetailDialogProps {
  article: NewsArticle | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const NewsDetailDialog = ({ article, open, onOpenChange }: NewsDetailDialogProps) => {
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const handleGetAiSummary = async () => {
    if (!article) return;
    setAiLoading(true);
    setAiError(null);
    try {
      const result = await getArticleAiSummary(article.id);
      setAiSummary(result.ai_summary);
    } catch (e) {
      if (e instanceof Error && e.message === 'upgrade_required') {
        setAiError('This feature requires a pro subscription');
      } else {
        setAiError(e instanceof Error ? e.message : 'Failed to fetch AI summary');
      }
    } finally {
      setAiLoading(false);
    }
  };

  const handleOpenChange = (value: boolean) => {
    onOpenChange(value);
    if (!value) {
      setAiSummary(null);
      setAiError(null);
    }
  };

  if (!article) return null;

  // sentiment is a number: > 0.2 positive, < -0.2 negative, else neutral
  const getSentimentType = () => {
    if (article.sentiment === null) return 'neutral';
    if (article.sentiment > 0.2) return 'positive';
    if (article.sentiment < -0.2) return 'negative';
    return 'neutral';
  };

  const sentimentType = getSentimentType();

  const getSentimentIcon = () => {
    switch (sentimentType) {
      case 'positive': return <TrendingUp className="w-4 h-4 text-success" />;
      case 'negative': return <TrendingDown className="w-4 h-4 text-destructive" />;
      default:         return <Minus className="w-4 h-4 text-muted-foreground" />;
    }
  };

  const getSentimentLabel = () => {
    switch (sentimentType) {
      case 'positive': return 'Positive Outlook';
      case 'negative': return 'Negative Outlook';
      default:         return 'Neutral';
    }
  };

  const getSentimentBg = () => {
    switch (sentimentType) {
      case 'positive': return 'bg-success/10 text-success border-success/20';
      case 'negative': return 'bg-destructive/10 text-destructive border-destructive/20';
      default:         return 'bg-muted text-muted-foreground border-border';
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-2xl glass-card border-primary/20">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              {article.source}
            </span>
            {article.source_domain && article.source_domain !== article.source && (
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
                {article.source_domain}
              </span>
            )}
          </div>
          <DialogTitle className="text-xl md:text-2xl font-bold leading-tight text-foreground">
            {article.title}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Meta info row */}
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="stock-ticker font-semibold text-primary bg-primary/10 px-2 py-0.5 rounded">
              {article.short_name}
            </span>
            <span className="text-muted-foreground">{article.source}</span>
            <span className="flex items-center gap-1 text-muted-foreground">
              <Clock className="w-3.5 h-3.5" />
              {formatDistanceToNow(new Date(article.publish_time), { addSuffix: true })}
            </span>
          </div>

          {/* Sentiment badge */}
          <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border ${getSentimentBg()}`}>
            {getSentimentIcon()}
            <span className="text-xs font-medium">{getSentimentLabel()}</span>
            {article.sentiment !== null && (
              <span className="text-xs opacity-70">({article.sentiment.toFixed(2)})</span>
            )}
          </div>

          {/* Description */}
          {article.description && (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-foreground uppercase tracking-wider">Summary</h4>
              <p className="text-muted-foreground leading-relaxed">
                {article.description}
              </p>
            </div>
          )}

          {/* AI Summary Section */}
          <div className="space-y-3">
            {!aiSummary && !aiLoading && (
              <Button
                variant="outline"
                onClick={handleGetAiSummary}
                className="w-full gap-2 border-primary/30 hover:border-primary hover:bg-primary/10"
              >
                <Bot className="w-4 h-4" />
                Get AI Summary
              </Button>
            )}

            {aiLoading && (
              <div className="flex items-center justify-center py-4 gap-2 rounded-lg bg-primary/5 border border-primary/20">
                <Loader2 className="w-4 h-4 animate-spin text-primary" />
                <span className="text-sm text-muted-foreground">Generating AI summary…</span>
              </div>
            )}

            {aiError && (
              <div className="rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-destructive text-sm">
                {aiError}
              </div>
            )}

            {aiSummary && (
              <div className="rounded-lg bg-primary/5 border border-primary/20 p-4 space-y-2">
                <div className="flex items-center gap-2 text-sm font-semibold text-primary">
                  <Sparkles className="w-3.5 h-3.5" />
                  AI Summary
                </div>
                <p className="text-sm text-foreground leading-relaxed whitespace-pre-line">
                  <StreamingText text={aiSummary}/>
                </p>
              </div>
            )}
          </div>

          {/* Read full article button */}
          <div className="pt-4 border-t border-border/30">
            <Button asChild className="w-full gap-2">
              <a href={article.url} target="_blank" rel="noopener noreferrer">
                Read Full Article
                <ExternalLink className="w-4 h-4" />
              </a>
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default NewsDetailDialog;