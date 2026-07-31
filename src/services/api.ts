import { API_BASE_URL } from '@/config/api';

/**
 * One fetch wrapper for the whole app.
 *
 * No auth headers: the backend has no accounts. Errors carry the server's
 * `detail` message so the UI can show why something failed rather than a bare
 * status code.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /** The stock is already on the watchlist. */
  get isConflict() {
    return this.status === 409;
  }

  /** A feature that needs an optional API key the backend doesn't have. */
  get isUnavailable() {
    return this.status === 503;
  }
}

/** The above-the-fold requests index.html starts before the bundle boots. */
export type BootKey = 'watchlist' | 'trending' | 'latest' | 'movers';

declare global {
  interface Window {
    __BOOT__?: Partial<Record<BootKey, Promise<unknown>>>;
    __BOOT_BASE__?: string;
  }
}

/**
 * Claim a preloaded response, once.
 *
 * Only valid while the app is pointed at the origin the preload used, and only
 * for the first render — after that the query has real params and has to ask
 * the server itself.
 */
const takeBoot = <T>(key: BootKey): Promise<T> | null => {
  const boot = window.__BOOT__;
  if (!boot?.[key] || window.__BOOT_BASE__ !== API_BASE_URL) return null;
  const promise = boot[key] as Promise<T>;
  delete boot[key];
  return promise;
};

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  params?: Record<string, string | number | undefined | null>;
  signal?: AbortSignal;
  /** Serve the first call from index.html's preload if it is still unclaimed. */
  boot?: BootKey;
}

export const apiFetch = async <T>(path: string, options: RequestOptions = {}): Promise<T> => {
  const { method = 'GET', body, params, signal, boot } = options;

  if (boot) {
    const preloaded = takeBoot<T>(boot);
    // A failed preload is not a failed request — fall through and ask properly.
    if (preloaded) return preloaded.catch(() => apiFetch<T>(path, { ...options, boot: undefined }));
  }

  const url = new URL(`${API_BASE_URL}${path}`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value));
      }
    }
  }

  const response = await fetch(url, {
    method,
    signal,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
};

const errorMessage = async (response: Response): Promise<string> => {
  try {
    const body = await response.json();
    // FastAPI puts the reason in `detail`; validation errors make it a list.
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail)) {
      return body.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join(', ');
    }
  } catch {
    /* not JSON — fall through to the status text */
  }
  return response.statusText || `Request failed (${response.status})`;
};
