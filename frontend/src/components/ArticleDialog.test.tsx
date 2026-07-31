import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { NewsArticle } from '@/types/stock';

import ArticleDialog from './ArticleDialog';

const summarise = vi.fn();

vi.mock('@/services/newsApi', () => ({
  getArticleAiSummary: (id: number) => summarise(id),
}));

const ARTICLE: NewsArticle = {
  id: 42,
  short_name: '6RJ0',
  title: 'Rocket Lab wins a $981M Space Force contract',
  url: 'https://stocktwits.com/rklb-contract',
  publish_time: '2026-07-31T09:00:00Z',
  source: 'Stocktwits',
  source_domain: 'stocktwits.com',
  source_url: null,
  source_type: 'FINVIZ',
  relevance: 'direct',
  lang: 'en',
  image: null,
  description: null,
  sentiment: 0.62,
  ai_summary: null,
};

const show = (overrides: Partial<NewsArticle> = {}) => {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <ArticleDialog
        article={{ ...ARTICLE, ...overrides }}
        onOpenChange={onOpenChange}
        onSelectSymbol={vi.fn()}
      />
    </QueryClientProvider>,
  );
  return { onOpenChange };
};

describe('ArticleDialog', () => {
  it('always offers a way out to the original source', () => {
    // The dialog replaced the headline's outbound link, so if this goes
    // missing the article becomes unreachable rather than merely unstyled.
    show();
    const link = screen.getByRole('link', { name: /Read the full article/ });
    expect(link).toHaveAttribute('href', ARTICLE.url);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('shows the stored description when there is one', () => {
    show({ description: 'The contract covers up to 20 launches.' });
    expect(screen.getByText('The contract covers up to 20 launches.')).toBeInTheDocument();
  });

  it('does not offer to summarise what already has a summary', () => {
    show({ description: 'Already summarised upstream.' });
    expect(screen.queryByRole('button', { name: /Summarise/ })).toBeNull();
  });

  it('says so plainly when nothing was published with the article', () => {
    // 91% of stored articles land here, so this is the common case, not an edge.
    show();
    expect(screen.getByText(/No summary was published/)).toBeInTheDocument();
  });

  it('only spends tokens when asked', async () => {
    summarise.mockResolvedValueOnce({ ai_summary: 'A short AI summary.', cached: false });
    show();
    expect(summarise).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Summarise/ }));
    await waitFor(() => expect(screen.getByText('A short AI summary.')).toBeInTheDocument());
    expect(summarise).toHaveBeenCalledWith(42);
  });

  it('reports a failed summary instead of looking stuck', async () => {
    summarise.mockRejectedValueOnce(new Error('no api key'));
    show();
    fireEvent.click(screen.getByRole('button', { name: /Summarise/ }));
    await waitFor(() => expect(screen.getByText(/Could not summarise/)).toBeInTheDocument());
  });

  it("shows the article's own sentiment, not the stock's", () => {
    show();
    expect(screen.getByText('+0.62')).toBeInTheDocument();
  });
});
