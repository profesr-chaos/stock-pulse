import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createElement, type ReactNode } from 'react';

import { useLiveUpdates } from './useLiveUpdates';

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  constructor() {
    FakeSocket.instances.push(this);
  }
}

describe('useLiveUpdates', () => {
  let client: QueryClient;

  const render = () =>
    renderHook(() => useLiveUpdates(), {
      wrapper: ({ children }: { children: ReactNode }) =>
        createElement(QueryClientProvider, { client }, children),
    });

  beforeEach(() => {
    FakeSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeSocket);
    vi.useFakeTimers();
    client = new QueryClient();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('invalidates every query when the server pushes a change', () => {
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    render();

    FakeSocket.instances[0].onmessage?.();

    expect(invalidate).toHaveBeenCalledTimes(1);
  });

  it('reconnects after a drop, and stops for good on unmount', () => {
    const { unmount } = render();

    FakeSocket.instances[0].onclose?.();
    vi.advanceTimersByTime(1_000);
    expect(FakeSocket.instances).toHaveLength(2);

    unmount();
    expect(FakeSocket.instances[1].close).toHaveBeenCalled();
    FakeSocket.instances[1].onclose?.();
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(2);
  });
});
