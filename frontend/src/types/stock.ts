/** Mirrors routes/schemas.py on the backend. */

export interface Stock {
  symbol: string;
  name: string | null;
  type: string | null;
  /** Yahoo's coarse bucket, e.g. "Industrials". Null for funds and indices. */
  sector: string | null;
  /** Yahoo's precise bucket, e.g. "Aerospace & Defense". */
  industry: string | null;
  /** Currency the price is actually quoted in, not the catalogue's guess. */
  currencyCode: string | null;
  /** Yahoo exchange code of the resolved listing, e.g. NMS, LSE, GER. */
  exchange: string | null;
  yahooSymbol: string | null;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  priceUpdatedAt: string | null;
}

/** 'direct' names the stock; 'related' is sector context from a curated feed. */
export type Relevance = 'direct' | 'related';

export interface NewsArticle {
  /** UUIDv7 — time-ordered, so it sorts chronologically as well as uniquely. */
  id: string;
  short_name: string;
  title: string;
  url: string;
  /** ISO 8601 UTC, always. */
  publish_time: string;
  source: string;
  source_domain: string | null;
  source_url: string | null;
  source_type: string | null;
  relevance: Relevance;
  lang: string | null;
  image: string | null;
  description: string | null;
  /** -1 … 1, or null when not yet scored. */
  sentiment: number | null;
  ai_summary: string | null;
  /** The stock's price move. Only set on /news/trending, which ranks by it. */
  movePercent?: number | null;
}

export interface PricePoint {
  ts: string;
  close: number;
}

export interface PriceSeries {
  symbol: string;
  currency: string | null;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  points: PricePoint[];
}

export interface TrendingStock {
  symbol: string;
  name: string | null;
  articleCount: number;
  avgSentiment: number | null;
  changePercent: number | null;
}

export interface Trending {
  mostDiscussed: TrendingStock[];
  mostPositive: TrendingStock[];
  negativeSpikes: TrendingStock[];
}

export interface Mover {
  symbol: string;
  name: string | null;
  price: number | null;
  currencyCode: string | null;
  changePercent: number | null;
  sentiment: number | null;
  sentimentDelta: number | null;
  articleCount: number;
}

export interface SentimentHistory {
  short_name: string;
  date: string;
  avg_sentiment: number | null;
  article_count: number;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
}

export interface AISummary {
  id?: number;
  symbol?: string;
  ai_summary: string;
  cached: boolean;
}

export interface SourceCount {
  source: string;
  article_count: number;
}

/**
 * One filterable sector. `level` is 'group' for Yahoo's eleven coarse buckets
 * and 'industry' for the precise ones — both are offered, because "Industrials"
 * is too broad to mean space and "Aerospace & Defense" is too narrow to browse.
 */
export interface Sector {
  sector: string;
  level: 'group' | 'industry';
  group: string | null;
  stockCount: number;
}

// ─── List wrappers ─────────────────────────────────────────
export interface StockListResponse {
  results: Stock[];
}

export interface SectorListResponse {
  results: Sector[];
}

export interface NewsListResponse {
  results: NewsArticle[];
}
