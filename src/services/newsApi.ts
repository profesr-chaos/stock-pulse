import type {
  AISummary,
  NewsArticle,
  NewsListResponse,
  Relevance,
  SourceCount,
} from '@/types/stock';

import { apiFetch, type BootKey } from './api';

export interface NewsQuery {
  /**
   * Omit to get the whole watchlist's feed in one call. Naming a symbol
   * filters the entire news table server-side, not just the loaded page —
   * a ticker you don't follow still returns whatever is stored for it.
   */
  symbols?: string[];
  days?: number;
  since?: string;
  sentiment?: 'positive' | 'negative' | 'neutral';
  relevance?: Relevance;
  limit?: number;
  offset?: number;
}

export const getNews = (
  query: NewsQuery = {},
  signal?: AbortSignal,
  boot?: BootKey,
): Promise<NewsArticle[]> =>
  apiFetch<NewsListResponse>('/news', {
    signal,
    boot,
    params: {
      symbols: query.symbols?.length ? query.symbols.join(',') : undefined,
      days: query.days,
      since: query.since,
      sentiment: query.sentiment,
      relevance: query.relevance,
      limit: query.limit,
      offset: query.offset,
    },
  }).then((data) => data.results);

export interface TrendingNewsQuery {
  symbols?: string[];
  days?: number;
  perStock?: number;
  limit?: number;
}

/** Articles ordered by the size of their stock's price move, biggest first. */
export const getTrendingNews = (
  query: TrendingNewsQuery = {},
  signal?: AbortSignal,
  boot?: BootKey,
): Promise<NewsArticle[]> =>
  apiFetch<NewsListResponse>('/news/trending', {
    signal,
    boot,
    params: {
      symbols: query.symbols?.length ? query.symbols.join(',') : undefined,
      days: query.days,
      per_stock: query.perStock,
      limit: query.limit,
    },
  }).then((data) => data.results);

export const getLatestHeadlines = (limit = 20): Promise<NewsArticle[]> =>
  apiFetch<NewsListResponse>('/news/latest', { params: { limit } })
    .then((data) => data.results);

export const getNewsSources = (days = 14): Promise<SourceCount[]> =>
  apiFetch<{ results: SourceCount[] }>('/news/sources', { params: { days } })
    .then((data) => data.results);

/** POST because generating a summary can spend API tokens. */
export const getArticleAiSummary = (id: number): Promise<AISummary> =>
  apiFetch<AISummary>(`/news/${id}/ai-summary`, { method: 'POST' });

export const getStockAiSummary = (symbol: string, days = 7): Promise<AISummary> =>
  apiFetch<AISummary>(`/news/stock/${encodeURIComponent(symbol)}/ai-summary`, {
    method: 'POST',
    params: { days },
  });
