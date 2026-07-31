import * as Dialog from '@radix-ui/react-dialog';
import { useMutation } from '@tanstack/react-query';
import { ExternalLink, Sparkles, X } from 'lucide-react';

import NewsImage from '@/components/NewsImage';
import {
  formatAgeLong,
  formatSentiment,
  sentimentDotClass,
  sentimentTextClass,
} from '@/lib/format';
import { getArticleAiSummary } from '@/services/newsApi';
import type { NewsArticle } from '@/types/stock';

interface ArticleDialogProps {
  article: NewsArticle | null;
  onOpenChange: (open: boolean) => void;
  onSelectSymbol: (symbol: string) => void;
}

/**
 * The enlarged read of one article.
 *
 * Most articles have no stored description — barely 9% do, because the majority
 * arrive as a Google News redirect with no summary behind it. So the body is
 * whatever we actually hold, and the AI summary is an explicit button rather
 * than an automatic fetch: it spends tokens, and spending them on every card a
 * reader happens to click is not a decision this dialog should make for them.
 *
 * Lazy-loaded like the watchlist editor, so it costs nothing until a click.
 */
const ArticleDialog = ({ article, onOpenChange, onSelectSymbol }: ArticleDialogProps) => {
  const summarise = useMutation({
    mutationFn: (id: number) => getArticleAiSummary(id),
  });

  // Prefer whatever the article already carries; the mutation result is only
  // ever an addition to it, never a replacement.
  const stored = article?.description || article?.ai_summary || null;
  const generated = summarise.data?.ai_summary ?? null;
  const body = stored ?? generated;

  return (
    <Dialog.Root open={article !== null} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink-strong/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[88vh] w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col border border-ink-strong bg-paper">
          {article && (
            <>
              <div className="flex items-start justify-between gap-4 border-b border-rule px-5 py-3">
                <p className="ft-meta">
                  {article.source} · {formatAgeLong(article.publish_time)}
                </p>
                <Dialog.Close
                  className="-mr-1 -mt-1 shrink-0 p-1 text-ink-muted hover:text-ink-strong"
                  aria-label="Close article"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </Dialog.Close>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
                <Dialog.Title className="ft-headline text-[24px] leading-tight md:text-[28px]">
                  {article.title}
                </Dialog.Title>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      onSelectSymbol(article.short_name);
                      onOpenChange(false);
                    }}
                    className="ft-chip hover:bg-paper-tint"
                  >
                    <span className="font-semibold text-ftblue">{article.short_name}</span>
                    <span className="sr-only"> — filter the feed to this ticker</span>
                  </button>

                  {article.sentiment !== null && (
                    <span className="ft-chip">
                      <span
                        className={`inline-block h-1.5 w-1.5 rounded-full ${sentimentDotClass(article.sentiment)}`}
                        aria-hidden="true"
                      />
                      <span className={sentimentTextClass(article.sentiment)}>
                        {formatSentiment(article.sentiment)}
                      </span>
                      <span className="text-ink-muted">sentiment</span>
                    </span>
                  )}
                </div>

                {article.image && (
                  <div className="mt-4 aspect-[16/9] w-full overflow-hidden">
                    <NewsImage src={article.image} alt="" priority />
                  </div>
                )}

                {/* Radix wants a description for the dialog's accessible
                    name; when there is no text this stays visually hidden
                    rather than rendering an empty paragraph. */}
                <Dialog.Description asChild>
                  {body ? (
                    <p className="mt-4 whitespace-pre-line text-[15px] leading-relaxed text-ink">
                      {body}
                    </p>
                  ) : (
                    <p className="sr-only">No summary is stored for this article.</p>
                  )}
                </Dialog.Description>

                {!stored && (
                  <div className="mt-4 border-t border-rule-light pt-4">
                    {!generated && (
                      <p className="text-sm text-ink-muted">
                        No summary was published with this article.
                      </p>
                    )}
                    <button
                      type="button"
                      onClick={() => summarise.mutate(article.id)}
                      disabled={summarise.isPending || generated !== null}
                      className="mt-2 inline-flex items-center gap-2 border border-ink-strong px-3 py-1.5 text-xs font-semibold uppercase tracking-wide hover:bg-paper-tint disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                      {summarise.isPending
                        ? 'Summarising…'
                        : generated
                          ? 'Summarised'
                          : 'Summarise with AI'}
                    </button>
                    {summarise.isError && (
                      <p className="mt-2 text-sm text-down">
                        Could not summarise this one — the AI key may not be set.
                      </p>
                    )}
                  </div>
                )}
              </div>

              <div className="border-t border-rule px-5 py-3">
                <a
                  href={article.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 text-sm font-semibold text-ftblue hover:underline"
                >
                  Read the full article at {article.source_domain ?? article.source}
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                </a>
              </div>
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};

export default ArticleDialog;
