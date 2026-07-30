import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { API_BASE_URL } from '@/config/api';

import { ApiError, apiFetch } from './api';

const mockFetch = vi.fn();

beforeEach(() => {
  mockFetch.mockReset();
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

describe('apiFetch', () => {
  it('builds the URL against the configured base', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ results: [] }));
    await apiFetch('/watchlist');
    expect(mockFetch.mock.calls[0][0].toString()).toBe(`${API_BASE_URL}/watchlist`);
  });

  it('serialises query params and drops empty ones', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ results: [] }));
    await apiFetch('/news', {
      params: { symbols: 'AAPL,TSLA', days: 14, since: undefined, sentiment: null, limit: '' },
    });
    const url = mockFetch.mock.calls[0][0] as URL;
    expect(url.searchParams.get('symbols')).toBe('AAPL,TSLA');
    expect(url.searchParams.get('days')).toBe('14');
    expect(url.searchParams.has('since')).toBe(false);
    expect(url.searchParams.has('sentiment')).toBe(false);
    expect(url.searchParams.has('limit')).toBe(false);
  });

  it('sends no auth header, because the API has no accounts', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ results: [] }));
    await apiFetch('/watchlist');
    const init = mockFetch.mock.calls[0][1];
    expect(JSON.stringify(init?.headers ?? {})).not.toMatch(/authorization/i);
  });

  it('posts a JSON body with the right content type', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
    await apiFetch('/watchlist', { method: 'POST', body: { symbol: 'AAPL' } });
    const init = mockFetch.mock.calls[0][1];
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe('{"symbol":"AAPL"}');
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json');
  });

  it("surfaces the server's detail message so the UI can explain the failure", async () => {
    mockFetch.mockResolvedValue(jsonResponse({ detail: 'AAPL is already on the watchlist' }, 409));
    await expect(apiFetch('/watchlist')).rejects.toThrow('AAPL is already on the watchlist');
  });

  it('flags a 409 as a conflict so adding a duplicate is not shown as an error', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ detail: 'already there' }, 409));
    const error = (await apiFetch('/watchlist').catch((e) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.isConflict).toBe(true);
    expect(error.isUnavailable).toBe(false);
  });

  it('flags a 503 as unavailable, which means a missing optional API key', async () => {
    mockFetch.mockResolvedValue(jsonResponse({ detail: 'AI summaries need a DSEEK API key' }, 503));
    const error = (await apiFetch('/news/1/ai-summary').catch((e) => e)) as ApiError;
    expect(error.isUnavailable).toBe(true);
  });

  it('flattens FastAPI validation error lists', async () => {
    mockFetch.mockResolvedValue(
      jsonResponse({ detail: [{ msg: 'value is not a valid integer' }, { msg: 'field required' }] }, 422),
    );
    await expect(apiFetch('/news')).rejects.toThrow(
      'value is not a valid integer, field required',
    );
  });

  it('falls back to the status text on a non-JSON error body', async () => {
    mockFetch.mockResolvedValue(new Response('gateway blew up', { status: 502, statusText: 'Bad Gateway' }));
    await expect(apiFetch('/news')).rejects.toThrow('Bad Gateway');
  });

  it('propagates a network failure rather than swallowing it', async () => {
    mockFetch.mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(apiFetch('/watchlist')).rejects.toThrow('Failed to fetch');
  });

  it('handles a 204 with no body', async () => {
    mockFetch.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiFetch('/watchlist/AAPL', { method: 'DELETE' })).resolves.toBeUndefined();
  });
});
