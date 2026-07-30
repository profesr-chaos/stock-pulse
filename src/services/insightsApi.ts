import type { Mover, SentimentHistory, Trending } from '@/types/stock';

import { apiFetch } from './api';

export const getTrending = (days = 3): Promise<Trending> =>
  apiFetch<Trending>('/insights/trending', { params: { days } });

export const getMovers = (days = 3): Promise<Mover[]> =>
  apiFetch<{ results: Mover[] }>('/insights/movers', { params: { days } })
    .then((data) => data.results);

export const getSentimentHistory = (symbol: string, days = 30): Promise<SentimentHistory[]> =>
  apiFetch<{ results: SentimentHistory[] }>(
    `/insights/sentiment/${encodeURIComponent(symbol)}`,
    { params: { days } },
  ).then((data) => data.results);
