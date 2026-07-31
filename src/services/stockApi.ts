import type {
  PriceSeries,
  Sector,
  SectorListResponse,
  Stock,
  StockListResponse,
} from '@/types/stock';

import { apiFetch } from './api';

export const searchStocks = (query: string, signal?: AbortSignal): Promise<Stock[]> =>
  apiFetch<StockListResponse>('/stocks/search', { params: { q: query }, signal })
    .then((data) => data.results);

/** Sectors that actually hold a followed stock — the filter menu. */
export const getSectors = (): Promise<Sector[]> =>
  apiFetch<SectorListResponse>('/stocks/sectors').then((data) => data.results);

export const getPopularStocks = (): Promise<Stock[]> =>
  apiFetch<StockListResponse>('/stocks/popular').then((data) => data.results);

export const getStockQuotes = (symbols: string[]): Promise<Stock[]> => {
  if (symbols.length === 0) return Promise.resolve([]);
  return apiFetch<StockListResponse>('/stocks/quotes', {
    params: { symbols: symbols.join(',') },
  }).then((data) => data.results);
};

export const getStock = (symbol: string): Promise<Stock> =>
  apiFetch<Stock>(`/stocks/${encodeURIComponent(symbol)}`);

export const getPriceHistory = (symbol: string, days = 30): Promise<PriceSeries> =>
  apiFetch<PriceSeries>(`/stocks/${encodeURIComponent(symbol)}/prices`, { params: { days } });
