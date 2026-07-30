import type {
  AISummary,
  NewsArticle,
  NewsListResponse,
  Relevance,
  SourceCount,
} from '@/types/stock';

import { apiFetch } from './api';

export interface NewsQuery {
  /** Omit to get the whole watchlist's feed in one call. */
  symbols?: string[];
  days?: number;
  since?: string;
  sentiment?: 'positive' | 'negative' | 'neutral';
  relevance?: Relevance;
  limit?: number;
}

export const getNews = (query: NewsQuery = {}, signal?: AbortSignal): Promise<NewsArticle[]> =>
  apiFetch<NewsListResponse>('/news', {
    signal,
    params: {
      symbols: query.symbols?.length ? query.symbols.join(',') : undefined,
      days: query.days,
      since: query.since,
      sentiment: query.sentiment,
      relevance: query.relevance,
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
