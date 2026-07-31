import Headline from '@/components/Headline';
import TickerTag from '@/components/TickerTag';
import { useLatestNews, type FeedFilter } from '@/hooks/useStockNews';
import { formatAgeLong } from '@/lib/format';
import type { NewsArticle } from '@/types/stock';

interface LatestNewsProps {
  filter: FeedFilter;
  onSelectSymbol: (symbol: string) => void;
  onOpenArticle: (article: NewsArticle) => void;
}

/**
 * Straight recency, no images — the counterweight to Trending's ranking, and
 * the cheapest section on the page to render.
 *
 * Carries no top margin of its own: above 1400px this is the middle column and
 * has to line up with Trending's rule, so the page grid owns the spacing.
 * Headlines are sized for that ~280px column, not for the full width.
 */
const LatestNews = ({ filter, onSelectSymbol, onOpenArticle }: LatestNewsProps) => {
  const { data: articles = [], isLoading, isError } = useLatestNews(filter);

  return (
    <section>
      <div className="ft-section">
        <h2 className="ft-section-title">Latest</h2>
      </div>

      {isLoading && <div className="mt-3 h-[560px] w-full bg-paper-tint" aria-busy="true" />}

      {!isLoading && articles.length === 0 && (
        <p className="mt-3 text-sm text-ink-muted">
          {isError ? 'Could not load the latest headlines.' : 'Nothing published recently.'}
        </p>
      )}

      <ul className="mt-2">
        {articles.map((article) => (
          <li key={article.id} className="border-b border-rule-light py-3 last:border-0">
            <h3 className="ft-headline text-[15px] leading-snug">
              <Headline article={article} onOpen={onOpenArticle} />
            </h3>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
              <p className="ft-meta">
                {article.source} · {formatAgeLong(article.publish_time)}
              </p>
              <TickerTag symbol={article.short_name} onSelect={onSelectSymbol} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
};

export default LatestNews;
