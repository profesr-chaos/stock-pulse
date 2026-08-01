import { useCallback, useEffect, useRef, useState } from 'react';

import Headline from '@/components/Headline';
import ImpactTag from '@/components/ImpactTag';
import NewsImage from '@/components/NewsImage';
import TickerTag from '@/components/TickerTag';
import {
  dedupeByUrl,
  isSearching,
  useNewsRiver,
  RIVER_PAGE_SIZE,
  type FeedFilter,
} from '@/hooks/useStockNews';
import { byImpact, formatAgeLong } from '@/lib/format';
import type { NewsArticle } from '@/types/stock';

/**
 * Holds a flag on for a minimum time after it clears.
 *
 * The API is local, so a page of 50 comes back in about 20ms — the spinner
 * would mount and unmount inside a single frame and the list would appear to
 * jump. This keeps it on screen long enough to read as loading. It delays
 * nothing: the articles render the moment they arrive, only the spinner
 * lingers.
 *
 * ponytail: a fixed floor, not a fade. If the API ever gets slow enough that
 * the floor stops mattering, delete it rather than tuning it.
 */
const useMinimumDuration = (active: boolean, ms = 400): boolean => {
  const [held, setHeld] = useState(active);

  useEffect(() => {
    if (active) {
      setHeld(true);
      return;
    }
    const timer = window.setTimeout(() => setHeld(false), ms);
    return () => window.clearTimeout(timer);
  }, [active, ms]);

  return held;
};

interface NewsRiverProps {
  filter: FeedFilter;
  /** Urls already printed by Trending and Latest, dropped rather than repeated. */
  shownUrls: Set<string>;
  onSelectSymbol: (symbol: string) => void;
  onOpenArticle: (article: NewsArticle) => void;
}

/**
 * "More news" — one article per row, paged forever. Doubles as the results
 * list when a search is running, which is why the heading is a prop of state
 * rather than a constant.
 *
 * The server pages by offset over a total ordering, so the only way to stop is
 * for the database to actually be out of articles.
 */
const NewsRiver = ({ filter, shownUrls, onSelectSymbol, onOpenArticle }: NewsRiverProps) => {
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

    // Fires as the sentinel enters the viewport rather than 800px early. The
    // earlier trigger made the next batch arrive before the reader could reach
    // the end, so the list simply never appeared to load — which is the thing
    // that reads as jarring, not the wait.
    const observer = new IntersectionObserver(
      ([entry]) => entry.isIntersecting && load.current(),
      { rootMargin: '120px 0px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, data?.pages.length]);

  const showSpinner = useMinimumDuration(isFetchingNextPage);
  const searching = isSearching(filter);
  // Each page is triaged as it arrives — high impact to the top of its own
  // batch — then the batches are concatenated in arrival order. Sorting after
  // the flatten would reorder stories the reader has already scrolled past
  // every time a new page lands.
  const articles = dedupeByUrl(
    (data?.pages ?? []).flatMap((page) => byImpact(page)).filter(
      // A search is its own complete list — nothing above it to repeat.
      (article) => searching || !shownUrls.has(article.url),
    ),
  );

  return (
    <section className="min-[1400px]:mt-2">
      <div className="ft-section">
        <h2 className="ft-section-title">{searching ? 'Results' : 'More news'}</h2>
        {searching && (
          <p className="ft-meta mt-1">
            {articles.length}
            {hasNextPage ? '+' : ''} matching {articles.length === 1 ? 'story' : 'stories'} for
            &ldquo;{filter.query.trim()}&rdquo;
          </p>
        )}
      </div>

      {isLoading && <div className="mt-3 h-64 w-full bg-paper-tint" aria-busy="true" />}
      {isError && <p className="mt-3 text-sm text-ink-muted">Could not load more news.</p>}

      <ul className="mt-2">
        {articles.map((article) => (
          <li key={article.id} className="border-b border-rule-light">
            <article className="flex items-start gap-4 py-4">
              {article.image && (
                <button
                  type="button"
                  onClick={() => onOpenArticle(article)}
                  className="hidden h-[70px] w-[124px] shrink-0 overflow-hidden sm:block"
                  tabIndex={-1}
                  aria-hidden="true"
                >
                  <NewsImage src={article.image} alt="" />
                </button>
              )}
              <div className="min-w-0 flex-1">
                <h3 className="ft-headline text-lg leading-snug">
                  <Headline article={article} onOpen={onOpenArticle} />
                </h3>
                {article.description && (
                  <p className="mt-1 line-clamp-2 text-sm text-ink-muted">{article.description}</p>
                )}
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <p className="ft-meta">
                    {article.source} · {formatAgeLong(article.publish_time)}
                  </p>
                  <TickerTag symbol={article.short_name} onSelect={onSelectSymbol} />
                  <ImpactTag impact={article.impact} />
                </div>
              </div>
            </article>
          </li>
        ))}
      </ul>

      <div ref={setSentinel} className="py-8 text-center" aria-live="polite">
        {showSpinner && (
          <p className="flex items-center justify-center gap-2 ft-meta">
            <span
              className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-rule border-t-ink-strong"
              aria-hidden="true"
            />
            Loading the next {RIVER_PAGE_SIZE}…
          </p>
        )}
        {!hasNextPage && articles.length > 0 && (
          <p className="ft-meta">That&rsquo;s everything we have stored.</p>
        )}
        {/* Only "empty" once paging has actually finished — an early page can
            be entirely filtered out by shownUrls while more are still coming. */}
        {!isLoading && !isError && !hasNextPage && articles.length === 0 && (
          <p className="text-sm text-ink-muted">
            {searching
              ? `Nothing stored matches “${filter.query.trim()}”.`
              : 'No further articles.'}
          </p>
        )}
      </div>
    </section>
  );
};

export default NewsRiver;
