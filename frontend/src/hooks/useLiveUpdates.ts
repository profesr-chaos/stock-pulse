import { useEffect } from 'react';

import { useQueryClient } from '@tanstack/react-query';

import { API_BASE_URL } from '@/config/api';

/** ws:// against a plain-HTTP base, wss:// automatically once the API is HTTPS. */
export const WS_URL = `${API_BASE_URL.replace(/^http/, 'ws')}/ws`;

/**
 * Server-pushed cache invalidation.
 *
 * The backend sends one message whenever anything was committed to its
 * database (scheduler refresh, watchlist edit in another tab). Every query is
 * then stale, and react-query refetches whatever is on screen over REST.
 * Reconnects with capped backoff so a backend restart heals itself.
 */
export const useLiveUpdates = () => {
  const queryClient = useQueryClient();

  useEffect(() => {
    let socket: WebSocket;
    let timer: number | undefined;
    let delay = 1_000;
    let unmounted = false;

    const connect = () => {
      socket = new WebSocket(WS_URL);
      socket.onopen = () => {
        delay = 1_000;
      };
      socket.onmessage = () => queryClient.invalidateQueries();
      socket.onclose = () => {
        if (unmounted) return;
        timer = window.setTimeout(connect, delay);
        delay = Math.min(delay * 2, 30_000);
      };
    };
    connect();

    return () => {
      unmounted = true;
      window.clearTimeout(timer);
      socket.close();
    };
  }, [queryClient]);
};
