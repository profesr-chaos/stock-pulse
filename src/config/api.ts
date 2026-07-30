/**
 * API configuration.
 *
 * One base URL, no keys, no auth headers — the backend is a local personal
 * tool. Override with VITE_API_URL if you ever run it elsewhere.
 */
export const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:5000';

/** How long a query's data is considered fresh, in ms. */
export const STALE_TIME = {
  /** Prices refresh hourly server-side, so polling harder achieves nothing. */
  quotes: 60_000,
  news: 60_000,
  search: 30_000,
  insights: 120_000,
  prices: 300_000,
} as const;
