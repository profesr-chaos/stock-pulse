import { useCallback, useEffect, useRef } from 'react';

import NewsImage from '@/components/NewsImage';
import TickerTag from '@/components/TickerTag';
import { useNewsRiver, type SymbolFilter } from '@/hooks/useStockNews';
import { formatAgeLong } from '@/lib/format';

interface NewsRiverProps {
  filter: SymbolFilter;
  /** Ids already printed by Trending and Latest, dropped rather than repeated. */
  shownIds: Set<number>;
  onSelectSymbol: (symbol: string) => void;
}

/**
 * "More news" — one article per row, paged forever.
 *
 * The sentinel sits 800px below the last row, so the next page is in flight
 * before the reader reaches the end and the list never visibly stalls. The
 * server pages by offset over a total ordering, so the only way to stop is for
 * the database to actually be out of articles.
 */
const NewsRiver = ({ filter, shownIds, onSelectSymbol }: NewsRiverProps) => {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading, isError } =
    useNewsRiver(filter);

  const sentinel = useRef<HTMLDivElement | null>(null);
  const load = useRef(fetchNextPage);
  load.current = fetchNextPage;

  const setSentinel = useCallback((node: HTMLDivElement | null) => {
    sentinel.current = node;
  }, []);

  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasNextPage || isFetchingNextPage) return;

    const observer = new IntersectionObserver(
      ([entry]) => entry.isIntersecting && load.current(),
      { rootMargin: '800px 0px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, data?.pages.length]);

  const articles = (data?.pages.flat() ?? []).filter((article) => !shownIds.has(article.id));

  return (
    <section className="mt-10">
      <div className="ft-section">
        <h2 className="ft-section-title">More news</h2>
      </div>

      {isLoading && <div className="mt-3 h-64 w-full bg-paper-tint" aria-busy="true" />}
      {isError && <p className="mt-3 text-sm text-ink-muted">Could not load more news.</p>}

      <ul className="mt-2">
        {articles.map((article) => (
          <li key={article.id} className="border-b border-rule-light">
            <article className="flex items-start gap-4 py-4">
              {article.image && (
                <a
                  href={article.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hidden h-[70px] w-[124px] shrink-0 overflow-hidden sm:block"
                  tabIndex={-1}
                  aria-hidden="true"
                >
                  <NewsImage src={article.image} alt="" />
                </a>
              )}
              <div className="min-w-0 flex-1">
                <a href={article.url} target="_blank" rel="noopener noreferrer">
                  <h3 className="ft-headline text-lg leading-snug">{article.title}</h3>
                </a>
                {article.description && (
                  <p className="mt-1 line-clamp-2 text-sm text-ink-muted">{article.description}</p>
                )}
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <p className="ft-meta">
                    {article.source} · {formatAgeLong(article.publish_time)}
                  </p>
                  <TickerTag symbol={article.short_name} onSelect={onSelectSymbol} />
                </div>
              </div>
            </article>
          </li>
        ))}
      </ul>

      <div ref={setSentinel} className="py-6 text-center">
        {isFetchingNextPage && <p className="ft-meta">Loading more…</p>}
        {!hasNextPage && articles.length > 0 && (
          <p className="ft-meta">That&rsquo;s everything we have stored.</p>
        )}
        {/* Only "empty" once paging has actually finished — an early page can
            be entirely filtered out by shownIds while more are still coming. */}
        {!isLoading && !isError && !hasNextPage && articles.length === 0 && (
          <p className="text-sm text-ink-muted">No further articles.</p>
        )}
      </div>
    </section>
  );
};

export default NewsRiver;
