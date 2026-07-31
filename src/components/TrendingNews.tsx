import Headline from '@/components/Headline';
import NewsImage from '@/components/NewsImage';
import TickerTag from '@/components/TickerTag';
import { useTrendingNews, type FeedFilter } from '@/hooks/useStockNews';
import { formatAgeLong } from '@/lib/format';
import type { NewsArticle } from '@/types/stock';

interface TrendingNewsProps {
  filter: FeedFilter;
  onSelectSymbol: (symbol: string) => void;
  onOpenArticle: (article: NewsArticle) => void;
}

const Meta = ({ article }: { article: NewsArticle }) => (
  <p className="ft-meta mt-1">
    {article.source} · {formatAgeLong(article.publish_time)}
  </p>
);

/**
 * The lead section, ordered by how far each article's stock moved today.
 *
 * The first headline is the LCP element, so its image is the one request on the
 * page marked high priority and everything below it is lazy.
 */
const TrendingNews = ({ filter, onSelectSymbol, onOpenArticle }: TrendingNewsProps) => {
  const { data: articles = [], isLoading, isError } = useTrendingNews(filter);

  // The placeholder is sized to the loaded section, not to a token grey box.
  // Everything here arrives over the network after first paint, so an
  // undersized skeleton buys a fast paint and pays for it in layout shift.
  if (isLoading) {
    return (
      <section aria-busy="true">
        <SectionHeading />
        <div className="mt-3 h-[620px] w-full bg-paper-tint" />
      </section>
    );
  }

  if (isError || articles.length === 0) {
    return (
      <section>
        <SectionHeading />
        <p className="mt-3 text-sm text-ink-muted">
          {isError
            ? 'Could not load trending stories.'
            : filter
              ? `Nothing stored for ${filter} yet.`
              : 'No priced stocks on the watchlist yet — follow one to rank its news.'}
        </p>
      </section>
    );
  }

  // Lead with art when the ranked set has any. Barely 5% of stored articles
  // carry an image — most sources publish through a Google redirect with no
  // og:image behind it — so taking `articles[0]` unconditionally leaves the
  // page's biggest slot empty most of the time. The lead is still one of the
  // top movers' stories; only which of them gets the hero changes.
  const leadIndex = Math.max(articles.findIndex((a) => a.image), 0);
  const lead = articles[leadIndex];
  const rest = articles.filter((_, index) => index !== leadIndex);
  // Only promote a story to a picture card if it has a picture — an imageless
  // "featured" card is indistinguishable from a list row, which reads as a
  // broken grid rather than a hierarchy.
  const featured = rest.filter((article) => article.image).slice(0, 2);
  const featuredIds = new Set(featured.map((article) => article.id));
  const remainder = rest.filter((article) => !featuredIds.has(article.id));

  return (
    <section>
      <SectionHeading />

      {/* FT's lead: text and art side by side on a tinted panel, rather than
          Yahoo's stacked hero — a full-width 16:9 image at this column width
          pushes everything else below the fold. */}
      <article className="mt-3 bg-paper-tint p-4 md:p-6">
        <div className="grid gap-4 md:grid-cols-2 md:items-center md:gap-6">
          <div className="min-w-0">
            <h3 className="ft-headline text-[26px] leading-[1.15] md:text-[34px]">
              <Headline article={lead} onOpen={onOpenArticle} />
            </h3>
            {lead.description && (
              <p className="mt-3 line-clamp-4 text-[15px] leading-snug text-ink">
                {lead.description}
              </p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
              <Meta article={lead} />
              <TickerTag
                symbol={lead.short_name}
                fallbackMove={lead.movePercent}
                onSelect={onSelectSymbol}
              />
            </div>
          </div>

          {lead.image && (
            <button
              type="button"
              onClick={() => onOpenArticle(lead)}
              className="order-first aspect-[16/9] w-full overflow-hidden md:order-none"
              tabIndex={-1}
              aria-hidden="true"
            >
              <NewsImage src={lead.image} alt="" priority />
            </button>
          )}
        </div>
      </article>

      {featured.length > 0 && (
        <div className="mt-6 grid gap-5 border-t border-rule pt-5 sm:grid-cols-2">
          {featured.map((article, index) => (
            <article key={article.id}>
              {article.image && (
                <button
                  type="button"
                  onClick={() => onOpenArticle(article)}
                  className="mb-2 block aspect-[16/9] w-full overflow-hidden"
                  tabIndex={-1}
                  aria-hidden="true"
                >
                  {/* The lead's image shares its row with the headline, so
                      it is only half the panel wide — this one renders at a
                      similar size and can win the LCP outright. Both are
                      above the fold; leaving this one lazy just means the
                      LCP image is discovered late. */}
                  <NewsImage src={article.image} alt="" priority={index === 0} />
                </button>
              )}
              <h4 className="ft-headline text-lg leading-snug">
                <Headline article={article} onOpen={onOpenArticle} />
              </h4>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                <Meta article={article} />
                <TickerTag
                  symbol={article.short_name}
                  fallbackMove={article.movePercent}
                  onSelect={onSelectSymbol}
                />
              </div>
            </article>
          ))}
        </div>
      )}

      {remainder.length > 0 && (
        <ul className="mt-5 grid gap-x-6 border-t border-rule pt-4 sm:grid-cols-2">
          {remainder.map((article) => (
            <li key={article.id} className="border-b border-rule-light py-3 last:border-0">
              <h4 className="ft-headline text-base leading-snug">
                <Headline article={article} onOpen={onOpenArticle} />
              </h4>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                <Meta article={article} />
                <TickerTag
                  symbol={article.short_name}
                  fallbackMove={article.movePercent}
                  onSelect={onSelectSymbol}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};

const SectionHeading = () => (
  <div className="ft-section">
    <h2 className="ft-section-title">Trending</h2>
    <p className="ft-meta mt-1">Ranked by today&rsquo;s price move</p>
  </div>
);

export default TrendingNews;
