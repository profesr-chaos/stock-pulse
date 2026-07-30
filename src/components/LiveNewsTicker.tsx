import { Newspaper } from 'lucide-react';
import { useEffect, useRef } from 'react';

import { useLatestHeadlines } from '@/hooks/useStockNews';
import { formatAge, sentimentDotClass, sentimentTextClass } from '@/lib/format';

/** The newest watchlist headlines, scrolling. Was a hard-coded array. */
const LiveNewsTicker = () => {
  const { data: headlines = [], isLoading } = useLatestHeadlines(20);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || headlines.length === 0) return;

    let frame: number;
    let position = 0;
    const speed = 0.5;

    const animate = () => {
      position += speed;
      // The list is rendered twice, so resetting at the halfway point loops
      // seamlessly.
      if (position >= element.scrollWidth / 2) position = 0;
      element.scrollLeft = position;
      frame = requestAnimationFrame(animate);
    };

    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [headlines.length]);

  if (isLoading || headlines.length === 0) {
    return null;
  }

  const looped = [...headlines, ...headlines];

  return (
    <div className="rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border/30 bg-card/80">
        <Newspaper className="w-3.5 h-3.5 text-primary" />
        <span className="text-xs font-semibold text-foreground uppercase tracking-wider">
          Latest headlines
        </span>
      </div>
      <div
        ref={scrollRef}
        className="flex items-center gap-8 px-4 py-3 overflow-hidden whitespace-nowrap"
      >
        {looped.map((article, index) => (
          <a
            key={`${article.id}-${index}`}
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 shrink-0 hover:opacity-80 transition-opacity"
          >
            <span className={`w-1.5 h-1.5 rounded-full ${sentimentDotClass(article.sentiment)}`} />
            <span className="text-xs font-bold text-primary">{article.short_name}</span>
            <span className={`text-xs ${sentimentTextClass(article.sentiment)}`}>
              {article.title}
            </span>
            <span className="text-[10px] text-muted-foreground/60">
              {article.source_domain ?? article.source} · {formatAge(article.publish_time)}
            </span>
          </a>
        ))}
      </div>
    </div>
  );
};

export default LiveNewsTicker;
