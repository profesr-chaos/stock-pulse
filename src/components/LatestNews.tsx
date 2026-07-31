import TickerTag from '@/components/TickerTag';
import { useLatestNews, type SymbolFilter } from '@/hooks/useStockNews';
import { formatAgeLong } from '@/lib/format';

interface LatestNewsProps {
  filter: SymbolFilter;
  onSelectSymbol: (symbol: string) => void;
}

/**
 * Straight recency, no images — the counterweight to Trending's ranking, and
 * the cheapest section on the page to render.
 */
const LatestNews = ({ filter, onSelectSymbol }: LatestNewsProps) => {
  const { data: articles = [], isLoading, isError } = useLatestNews(filter);

  return (
    <section className="mt-8">
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
            <a href={article.url} target="_blank" rel="noopener noreferrer">
              <h3 className="ft-headline text-[17px] leading-snug">{article.title}</h3>
            </a>
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
