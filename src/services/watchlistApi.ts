import type { Stock, StockListResponse } from '@/types/stock';

import { apiFetch } from './api';

export const getWatchlist = (): Promise<Stock[]> =>
  apiFetch<StockListResponse>('/watchlist').then((data) => data.results);

/**
 * Follow a stock. The backend starts a month-long price and news backfill in
 * the background, so the feed fills in shortly after this resolves.
 */
export const addToWatchlist = (symbol: string): Promise<void> =>
  apiFetch('/watchlist', { method: 'POST', body: { symbol } });

export const removeFromWatchlist = (symbol: string): Promise<void> =>
  apiFetch(`/watchlist/${encodeURIComponent(symbol)}`, { method: 'DELETE' });

export const reorderWatchlist = (symbols: string[]): Promise<void> =>
  apiFetch('/watchlist/reorder', { method: 'PUT', body: { symbols } });

export const refreshStock = (symbol: string): Promise<void> =>
  apiFetch(`/watchlist/${encodeURIComponent(symbol)}/refresh`, { method: 'POST' });
