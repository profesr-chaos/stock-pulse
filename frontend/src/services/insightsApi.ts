import type { Mover, SentimentHistory, Trending } from '@/types/stock';

import { apiFetch } from './api';

export const getTrending = (days = 3): Promise<Trending> =>
  apiFetch<Trending>('/insights/trending', { params: { days } });

/**
 * Watchlist stocks by absolute price move.
 *
 * The defaults must match index.html's preload query, or `boot` would hand
 * back a response the caller did not ask for.
 */
export const getMovers = (days = 3, limit = 30, boot?: 'movers'): Promise<Mover[]> =>
  apiFetch<{ results: Mover[] }>('/insights/movers', { params: { days, limit }, boot })
    .then((data) => data.results);

export const getSentimentHistory = (symbol: string, days = 30): Promise<SentimentHistory[]> =>
  apiFetch<{ results: SentimentHistory[] }>(
    `/insights/sentiment/${encodeURIComponent(symbol)}`,
    { params: { days } },
  ).then((data) => data.results);
